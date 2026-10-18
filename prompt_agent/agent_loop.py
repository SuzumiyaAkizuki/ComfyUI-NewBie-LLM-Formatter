"""Medium/High Agent tool loop and convergence guards."""

import json
from concurrent.futures import ThreadPoolExecutor

from prompt_agent import utils
from prompt_agent.console import (
    _C, _log, _log_warn, _log_error, _log_round_header,
)
from prompt_agent.diagnostics import (
    format_agent_error_summary, write_agent_error_log as _default_error_writer,
)
from prompt_agent.message_protocol import (
    _sanitize_messages_for_gemini, _serialize_tool_calls, _plain_data,
    _assistant_tool_message,
)
from prompt_agent.tools import get_tools

try:
    import comfy.utils
    import comfy.model_management
    _COMFY_AVAILABLE = True
except ImportError:
    _COMFY_AVAILABLE = False


_STAGNATION_MIN_NEW = 3
_STAGNATION_LIMIT = 2
_LOW_NOVELTY_RATIO = 0.34
_PROVIDED_TOPK = 3


def complete_moss_output(agent, messages, content=None):
    """Use the shared tool protocol for final compilation, without tag exploration."""
    from prompt_agent.output_contract import parse_envelope
    messages = list(messages)
    failures = []
    response = None
    request_args = None

    def deliver(raw):
        _, explanation = parse_envelope(raw)
        compiled = getattr(agent, "_moss_compiled_prompt", None)
        if not isinstance(compiled, str) or not compiled.strip():
            raise ValueError("尚未成功调用 compile_moss_prompt")
        return json.dumps({"xml_out": compiled, "text_out": explanation}, ensure_ascii=False)

    if content is not None:
        try:
            return deliver(content)
        except ValueError:
            pass
        messages.append({"role": "assistant", "content": content})
    messages.append({"role": "user", "content":
        "最后必须调用 compile_moss_prompt 编译本次完整草稿（caption 也必须编译）。"
        "保留 Danbooru 标签和用户要求；如缺少规范，先调用 get_moss_image_format。"
        "得到成功结果后输出 xml_out/text_out JSON，xml_out 必须逐字等于最近的成功编译结果。"
        "禁止直接输出未编译草稿或自行修改编译结果；本阶段不要重新搜索标签。"})
    available = [t for t in agent._get_available_tools() if t["function"]["name"] in {
        "get_moss_image_format", "compile_moss_prompt", "convert_moss_bbox"}]
    if "compile_moss_prompt" not in {t["function"]["name"] for t in available}:
        raise RuntimeError("MOSS 缺少 compile_moss_prompt 工具，无法交付最终提示词")
    for _ in range(6):
        if _COMFY_AVAILABLE:
            comfy.model_management.throw_exception_if_processing_interrupted()
        compiled = getattr(agent, "_moss_compiled_prompt", None)
        request_args = dict(model=agent.model_name,
            messages=_sanitize_messages_for_gemini(messages, getattr(agent, "model_name", None)),
            temperature=0.7, extra_body=agent._extra_body)
        if not compiled:
            # After a premature final answer, require the missing compiler call.
            choice = {"type": "function", "function": {"name": "compile_moss_prompt"}} if failures else "auto"
            request_args.update(tools=available, tool_choice=choice)
        response = agent._create_completion(purpose="MOSS 最终编译", **request_args)
        msg = response.choices[0].message
        if response.usage:
            agent._moss_final_tokens = getattr(agent, "_moss_final_tokens", 0) + response.usage.total_tokens
            agent._log_token_usage(response.usage)
        calls = _serialize_tool_calls(getattr(msg, "tool_calls", None))
        content = msg.content or ""
        if calls:
            messages.append(_assistant_tool_message(content, calls, msg))
            for call in calls:
                name = call["function"]["name"]
                try:
                    if name not in {t["function"]["name"] for t in available}:
                        raise ValueError("最终编译阶段不允许该工具")
                    args = json.loads(call["function"]["arguments"] or "{}")
                    agent._log_tool_call(name, args)
                    result = agent._execute_tool(name, args)
                    agent._log_tool_result(name, result)
                except Exception as error:
                    agent._raise_if_interrupted(error)
                    failures.append({"tool": name, "error": str(error)})
                    _log_warn(f"MOSS 编译工具失败: {format_agent_error_summary(error)}")
                    result = json.dumps({"error": str(error)}, ensure_ascii=False)
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
            continue
        try:
            return deliver(content)
        except ValueError as error:
            failures.append({"stage": "final_output", "error": str(error)})
            _log_warn(f"MOSS 最终输出尚不可交付: {error}")
        messages.extend([{"role": "assistant", "content": content}, {"role": "user", "content":
            "最终回答无效：请先成功编译本次草稿，再把工具返回值原样放入 xml_out，中文解释放入 text_out。"}])
    error = ValueError("MOSS 最终编译/JSON 输出失败: " + (str(failures[-1]) if failures else "未返回最终 JSON"))
    _default_error_writer(error,
        context={"purpose": "MOSS finalization", "model": getattr(agent, "model_name", None),
                 "mode": "MOSS", "failures": failures},
        completion_args=request_args, completion_response=_plain_data(response))
    raise error


def force_final_output(agent, messages):
    """要求模型基于已收集标签直接输出，禁止再调工具。"""
    if getattr(agent, "mode", None) == "MOSS":
        before = getattr(agent, "_moss_final_tokens", 0)
        content = complete_moss_output(agent, messages)
        return content, getattr(agent, "_moss_final_tokens", 0) - before
    if _COMFY_AVAILABLE:
        comfy.model_management.throw_exception_if_processing_interrupted()
    messages.append({
        "role": "user",
        "content": "请根据已收集到的标签信息直接输出最终 prompt，禁止再调用任何工具。",
    })
    try:
        resp = agent._create_completion(
            purpose="强制收尾",
            model=agent.model_name,
            messages=_sanitize_messages_for_gemini(
                messages, getattr(agent, "model_name", None),
            ),
            temperature=0.7, extra_body=agent._extra_body,
        )
        content = resp.choices[0].message.content or ""
        forced_tokens = resp.usage.total_tokens if resp.usage else 0
        if resp.usage:
            agent._log_token_usage(resp.usage)
    except Exception as e:
        _log_error(f"强制输出 LLM 调用失败: {format_agent_error_summary(e)}")
        raise
    return content, forced_tokens


def run_agent_loop(agent, messages, max_rounds, provided_norm,
                   error_writer=_default_error_writer, tools_provider=get_tools):
    """执行 Agent 工具循环。Returns (content, rounds, total_tokens, format)。"""
    self = agent
    pbar = comfy.utils.ProgressBar(max_rounds, node_id=self.unique_id) if _COMFY_AVAILABLE else None

    rounds = 0
    total_tokens = 0
    duplicate_tracker = {}
    tag_cn_map: dict[str, str] = {}
    seen_tags: set[str] = set()
    stagnant_rounds = 0
    stagnated = False
    content = ""
    captured_format = None

    while rounds < max_rounds:
        if _COMFY_AVAILABLE:
            comfy.model_management.throw_exception_if_processing_interrupted()
        _log_round_header(rounds + 1)
        self._trace(
            "round",
            status="running",
            title="深度思考中..." if getattr(self, "thinking", False) else "思考中...",
            summary=f"Round {rounds + 1}/{max_rounds}",
            details={
                "round": rounds + 1,
                "max_rounds": max_rounds,
                "phase": "thinking",
                "thinking_enabled": bool(getattr(self, "thinking", False)),
            },
        )
        available_tools = tools_provider()
        _log(f"LLM 请求: {len(available_tools)} tools available, {len(messages)} messages")

        sanitized_messages = _sanitize_messages_for_gemini(
            messages, getattr(self, "model_name", None),
        )
        request_args = {
            "model": self.model_name,
            "messages": sanitized_messages,
            "tools": available_tools,
            "tool_choice": "auto",
            "temperature": 0.7,
            "extra_body": self._extra_body,
        }
        resp = None
        try:
            resp = self._create_completion(
                purpose=f"Agent Round {rounds + 1}",
                **request_args,
            )
            choices = getattr(resp, "choices", None) or []
            if not choices:
                raise ValueError("LLM API 返回了空 choices。")
            msg = choices[0].message
            content = msg.content or ""
            tool_calls = _serialize_tool_calls(msg.tool_calls)
            finish_reason = choices[0].finish_reason

            if resp.usage:
                total_tokens += resp.usage.total_tokens
                self._log_token_usage(resp.usage)
        except Exception as e:
            self._raise_if_interrupted(e)
            log_path = getattr(e, "_agent_error_log_path", None)
            if not log_path:
                log_path = error_writer(
                    e,
                    context=self._completion_error_context(
                        f"Agent Round {rounds + 1}", 1,
                        phase="response_processing",
                    ),
                    completion_args=request_args,
                    completion_response=_plain_data(resp),
                )
            _log_warn(
                f"第 {rounds + 1} 轮无法继续（请求重试耗尽或响应无法解析），"
                "改用当前已收集的信息直接作答"
            )
            self._trace(
                "round_recovery",
                status="warning",
                title="Direct final answer",
                summary=f"Round {rounds + 1} 失败，基于已有信息收尾",
                details={
                    "round": rounds + 1,
                    "error_type": type(e).__name__,
                    "log_path": log_path,
                },
            )
            content, forced_tokens = self._force_final_output(messages)
            total_tokens += forced_tokens
            return content, rounds, total_tokens, captured_format

        if finish_reason == "tool_calls" and tool_calls:
            assistant_note = content.strip() if content else ""
            if assistant_note:
                _log(
                    f"LLM 工具调用附带 content: {assistant_note[:200]}"
                    f"{'...' if len(assistant_note) > 200 else ''}",
                    _C.WARNING,
                )
            parsed = []
            skipped = []
            for tool_call in tool_calls:
                name = tool_call["function"]["name"]
                raw_args = tool_call["function"]["arguments"]
                try:
                    args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError:
                    args = {}
                if name == "search_tags":
                    qn = utils.normalize_tag(str(args.get("query", "")))
                    if qn and qn in provided_norm:
                        _log_warn(f"搜索查询「{args.get('query', '')}」命中用户已提供标签，跳过执行")
                        skipped.append((tool_call, json.dumps(
                            {"skipped": "user_provided",
                             "note": "该标签用户已提供，禁止重复搜索，直接使用用户提供的版本即可。"},
                            ensure_ascii=False)))
                        continue
                call_key = name + ":" + json.dumps(args, sort_keys=True)
                count = duplicate_tracker.get(call_key, 0) + 1
                duplicate_tracker[call_key] = count
                if count > 3:
                    _log_warn(f"检测到重复调用 {name}（第{count}次），跳过执行")
                    skipped.append((tool_call, json.dumps(
                        {"skipped": "duplicate"}, ensure_ascii=False,
                    )))
                    continue
                parsed.append((tool_call, name, args))
            if not parsed:
                messages.append(_assistant_tool_message(content, tool_calls, msg))
                for tool_call in tool_calls:
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call["id"],
                        "content": json.dumps({"skipped": "duplicate"}, ensure_ascii=False),
                    })
                _log_error("所有 tool_calls 均为重复调用，强制退出循环")
                break

            messages.append(_assistant_tool_message(content, tool_calls, msg))
            for tool_call, name, args in parsed:
                tool_details = {
                    "round": rounds + 1,
                    "tool_call_id": tool_call["id"],
                    "arguments": args,
                }
                if assistant_note:
                    tool_details["message"] = assistant_note
                self._trace(
                    "tool",
                    status="running",
                    title=name,
                    summary=self._tool_trace_summary(name, args),
                    details=tool_details,
                )

            try:
                with ThreadPoolExecutor(max_workers=min(len(parsed), 8)) as pool:
                    futures = [
                        pool.submit(self._execute_tool, name, args)
                        for _, name, args in parsed
                    ]
                    results = []
                    for future in futures:
                        try:
                            results.append(future.result(timeout=60))
                        except Exception as e:
                            _log_error(
                                f"工具调用超时或异常: {format_agent_error_summary(e)}"
                            )
                            results.append(json.dumps(
                                {"found": False, "error": str(e)},
                                ensure_ascii=False,
                            ))
            except Exception as e:
                _log_error(f"并行工具调用失败: {format_agent_error_summary(e)}")
                for tool_call, _, _ in parsed:
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call["id"],
                        "content": json.dumps({"error": str(e)}, ensure_ascii=False),
                    })
                for tool_call, skip_content in skipped:
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call["id"],
                        "content": skip_content,
                    })
                break

            round_returned: set[str] = set()
            for (tool_call, name, args), result in zip(parsed, results):
                self._log_tool_call(name, args)
                self._log_tool_result(name, result)
                result_details = {
                    "round": rounds + 1,
                    "tool_call_id": tool_call["id"],
                    "arguments": args,
                    "result": self._compact_tool_result(result),
                }
                if assistant_note:
                    result_details["message"] = assistant_note
                self._trace(
                    "tool",
                    status="success",
                    title=name,
                    summary=self._tool_result_summary(name, result),
                    details=result_details,
                )
                tag_cn_map.update(self._collect_cn_from_result(result))
                if name in ("get_anima_format", "get_newbie_format", "get_moss_image_format"):
                    captured_format = result
                if name in ("search_tags", "get_related_tags"):
                    returned_list = self._extract_tag_list(result)
                    returned = set(returned_list)
                    if returned:
                        if provided_norm:
                            top_hit = [
                                tag for tag in returned_list[:_PROVIDED_TOPK]
                                if utils.normalize_tag(tag) in provided_norm
                            ]
                            if top_hit:
                                result = result + (
                                    f"\n\n[系统提示] 本次结果中排名最靠前的标签 "
                                    f"{', '.join(top_hit)} 属于用户已提供标签，"
                                    f"说明你正在搜索用户已覆盖的概念。用户已提供的标签禁止重复检索，"
                                    f"请勿再搜索该概念，转向尚未覆盖的维度或直接输出。"
                                )
                        new_in_call = returned - seen_tags - round_returned
                        round_returned |= returned
                        if len(new_in_call) / len(returned) < _LOW_NOVELTY_RATIO:
                            result = result + (
                                f"\n\n[系统提示] 本次返回 {len(returned)} 个标签，"
                                f"其中仅 {len(new_in_call)} 个为新标签，其余均已在先前轮次出现。"
                                f"该主题/维度已充分覆盖，请勿换措辞重复搜索同一主题，"
                                f"转向尚未覆盖的维度，或直接输出最终结果。"
                            )
                messages.append({
                    "role": "tool", "tool_call_id": tool_call["id"], "content": result,
                })
            for tool_call, skip_content in skipped:
                messages.append({
                    "role": "tool", "tool_call_id": tool_call["id"],
                    "content": skip_content,
                })

            round_new = len(round_returned - seen_tags)
            round_had_search = len(round_returned) > 0
            seen_tags |= round_returned
            if round_had_search and round_new < _STAGNATION_MIN_NEW:
                stagnant_rounds += 1
                _log_warn(
                    f"低信息增量轮次（本轮新增 {round_new} 个标签），"
                    f"停滞计数 {stagnant_rounds}/{_STAGNATION_LIMIT}"
                )
                self._trace(
                    "notice",
                    status="warning",
                    title="Low novelty",
                    summary=f"本轮新增 {round_new} 个标签",
                    details={"stagnant_rounds": stagnant_rounds},
                )
            else:
                stagnant_rounds = 0

            rounds += 1
            if pbar:
                pbar.update_absolute(rounds)

            if stagnant_rounds >= _STAGNATION_LIMIT:
                _log_warn("连续低信息增量，提前结束探索，进入收尾输出")
                self._trace(
                    "notice",
                    status="warning",
                    title="Early finish",
                    summary="连续低信息增量，提前收尾",
                )
                stagnated = True
                break

            remaining = max_rounds - rounds
            progress_msg = f"【轮次进度】第 {rounds}/{max_rounds} 轮，剩余 {remaining} 轮。"
            messages.append({"role": "user", "content": progress_msg})
            continue

        _log(f"LLM 输出最终回答 (finish_reason={finish_reason})")
        break
    else:
        _log_error(f"Agent 循环超过最大轮次 ({max_rounds})，强制输出")
        content, forced_tokens = self._force_final_output(messages)
        total_tokens += forced_tokens

    if stagnated:
        content, forced_tokens = self._force_final_output(messages)
        total_tokens += forced_tokens

    if getattr(self, "mode", None) == "MOSS":
        before = getattr(self, "_moss_final_tokens", 0)
        content = complete_moss_output(self, messages, content)
        total_tokens += getattr(self, "_moss_final_tokens", 0) - before
    return content, rounds, total_tokens, captured_format
