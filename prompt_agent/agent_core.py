"""
prompt_agent/agent_core.py
---------------------------
LLM_Prompt_Formatter 的 Agent 编排入口与兼容门面。
"""

from __future__ import annotations

import json
import re
import sys
import time
from itertools import chain
from types import SimpleNamespace

from openai import OpenAI

from prompt_agent.agent_prompts import (
    get_agent_system_prompt,
    get_format_tool_directive,
    QUERY_REWRITE_PROMPT,
)
from prompt_agent.tools import (
    get_tools,  # 兼容旧测试与外部 patch 入口；实际循环由 agent_loop 使用
    execute_search_tags,
    execute_get_related_tags,
    execute_get_artist_recommendations,
    execute_get_artist_profile,
    execute_get_anima_format,
    execute_get_newbie_format,
)
from prompt_agent.cache import (
    get_baseline_store, compute_edit, normalize as normalize_prompt,
)
from prompt_agent.agent_trace import emit_agent_trace
from prompt_agent import utils
from prompt_agent.console import (
    _C, _log, _log_warn, _log_error, _log_ok, _log_section,
    _log_banner,
)
from prompt_agent.diagnostics import (
    _ERROR_DIR, _redact_url, format_agent_error_summary,
    write_agent_error_log as _write_agent_error_log,
)
from prompt_agent.message_protocol import (
    _sanitize_messages_for_gemini, _serialize_tool_calls, _plain_data,
    _reasoning_text_from_details, _message_text_from_content_or_reasoning,
    _assistant_tool_message, _usage_summary,
)
from prompt_agent.output_parser import (
    parse_output, parse_anima_output, parse_newbie_output,
)
from prompt_agent.low_pipeline import (
    get_output_format_section, fallback_normal, batch_search_tags,
    explore_related_tags, assemble_low_output, run_low_effort,
    run_low_continuation,
)
from prompt_agent.agent_loop import force_final_output, run_agent_loop

try:
    import comfy.utils
    import comfy.model_management
    _COMFY_AVAILABLE = True
except ImportError:
    _COMFY_AVAILABLE = False

MAX_ROUNDS = 10

# 增量修订续写时的工具轮次上限：局部修订不需要全量轮次
_REVISION_MAX_ROUNDS = 3
# 同一节点连续续写达到此次数后，下一次小改自动完整重跑，避免长期局部修订漂移
_MAX_CONSECUTIVE_CONTINUATIONS = 5
# Agent LLM 请求失败后的指数退避：首次请求之外再重试 3 次。
_COMPLETION_RETRY_DELAYS = (1, 2, 4)
class _StreamUnavailableError(RuntimeError):
    """Raised only when a streaming request fails before its first chunk."""


def write_agent_error_log(
        error, *, context=None, completion_args=None, completion_response=None,
        log_path=None):
    """兼容旧入口，并允许测试/调用方继续 patch agent_core._ERROR_DIR。"""
    return _write_agent_error_log(
        error,
        context=context,
        completion_args=completion_args,
        completion_response=completion_response,
        log_path=log_path,
        error_dir=_ERROR_DIR,
    )


# _repair_xml, _clean_prompt, _split_by_language 已迁移至 prompt_agent.utils
# 以下保留薄封装以保持模块内 _log_* 日志前缀风格兼容

def _repair_xml(xml_string):
    result = utils.repair_xml(xml_string)
    return result


def _clean_prompt(xml_content, gemma_prompt):
    result = utils.clean_prompt(xml_content, gemma_prompt)
    return result


def _split_by_language(text):
    return utils.split_by_language(text)


# Effort 级别配置
# Low   = 流水线模式，不走 Agent 循环，用 full_scene 批量搜索
# Medium = Agent 循环，默认 full_scene 平衡召回质量与轮次收敛速度
# High   = Agent 循环，默认 full_scene，更多轮次深入探索 + wiki 释义
_EFFORT_CONFIG = {
    "Low":    {"search_mode": "full_scene", "related_limit": 50},
    "Medium": {"search_mode": "full_scene", "related_limit": 30, "max_rounds": 8},
    "High":   {"search_mode": "full_scene", "related_limit": 50, "max_rounds": 10, "include_wiki": True},
}


class PromptAgent:
    def __init__(self, api_key, api_url, model_name, mode, thinking, config, effort="Medium", unique_id=None):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.mode = mode
        self.thinking = thinking
        self.config = config
        self.effort = effort
        self.unique_id = unique_id
        self._effort_cfg = _EFFORT_CONFIG.get(effort, _EFFORT_CONFIG["Medium"])
        self.llm = OpenAI(api_key=api_key, base_url=api_url)
        from LLM_Node import get_platform_settings
        self._extra_body = get_platform_settings(self.api_url, self.model_name, self.thinking)
        # 查询重写是结构化预处理任务，无论主 Agent 是否开启思考，始终使用
        # thinking=False 对应的平台参数，避免在 JSON 拆解阶段消耗推理预算。
        self._rewrite_extra_body = get_platform_settings(
            self.api_url, self.model_name, False,
        )

    def _trace(self, event, status="info", title="", summary="", details=None):
        emit_agent_trace(
            self.unique_id,
            event,
            status=status,
            title=title,
            summary=summary,
            details=details,
        )

    def _log_token_usage(self, usage):
        if usage:
            _log(f"Token: {usage.prompt_tokens} input + {usage.completion_tokens} output = {usage.total_tokens} used")

    @staticmethod
    def _strip_inline_thinking(message):
        """Remove legacy <think> blocks from visible content and return their text."""
        content = getattr(message, "content", None) or ""
        matches = re.findall(r"<think>(.*?)</think>", content, flags=re.DOTALL | re.IGNORECASE)
        if not matches:
            return ""
        message.content = re.sub(
            r"<think>.*?</think>", "", content,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        return "\n".join(part.strip() for part in matches if part.strip())

    @staticmethod
    def _reasoning_fields(message):
        """Yield visible reasoning fields in provider-preference order."""
        for field in ("reasoning_content", "reasoning"):
            value = getattr(message, field, None)
            if value and str(value).strip():
                yield field, str(value)
        details = getattr(message, "reasoning_details", None)
        detail_text = _reasoning_text_from_details(details)
        if detail_text.strip():
            yield "reasoning_details", detail_text

    def _log_non_stream_reasoning(self, response, purpose):
        """Show provider-returned reasoning when streaming is unavailable."""
        choices = getattr(response, "choices", None) or []
        if not choices:
            return
        message = choices[0].message
        displayed = False
        for field, reasoning in self._reasoning_fields(message):
            if displayed:
                break
            _log_section(f"模型思考 · {purpose} · {field}")
            print(reasoning, file=sys.stderr, flush=True)
            displayed = True
        inline = self._strip_inline_thinking(message)
        if inline and not displayed:
            _log_section(f"模型思考 · {purpose} · <think>")
            print(inline, file=sys.stderr, flush=True)
            displayed = True
        if not displayed:
            _log_warn(f"{purpose} 已启用思考，但模型/网关未返回可显示的思考内容")

    def _consume_completion_stream(self, stream, purpose):
        """Aggregate an OpenAI-compatible stream while printing reasoning live."""
        content_parts = []
        reasoning_parts = {"reasoning_content": [], "reasoning": []}
        reasoning_details = []
        tool_call_parts = {}
        finish_reason = None
        usage = None
        display_field = None
        displayed_any = False

        iterator = iter(stream)
        try:
            first_chunk = next(iterator)
        except StopIteration:
            first_chunk = None
        except Exception as error:
            raise _StreamUnavailableError(str(error)) from error

        for chunk in chain(() if first_chunk is None else (first_chunk,), iterator):
            chunk_usage = getattr(chunk, "usage", None)
            if chunk_usage is not None:
                usage = chunk_usage
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            choice = choices[0]
            if getattr(choice, "finish_reason", None) is not None:
                finish_reason = choice.finish_reason
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue

            content = getattr(delta, "content", None)
            if content:
                content_parts.append(str(content))

            for field in ("reasoning_content", "reasoning"):
                part = getattr(delta, field, None)
                if not part:
                    continue
                part = str(part)
                reasoning_parts[field].append(part)
                if display_field is None:
                    display_field = field
                    _log_section(f"模型思考 · {purpose} · {field}")
                if display_field == field:
                    print(part, end="", file=sys.stderr, flush=True)
                    displayed_any = True

            details = getattr(delta, "reasoning_details", None)
            if details:
                plain_details = _plain_data(details)
                reasoning_details.extend(plain_details)
                detail_text = _reasoning_text_from_details(plain_details)
                if detail_text and display_field is None:
                    display_field = "reasoning_details"
                    _log_section(f"模型思考 · {purpose} · reasoning_details")
                if detail_text and display_field == "reasoning_details":
                    print(detail_text, end="", file=sys.stderr, flush=True)
                    displayed_any = True

            for tool_delta in getattr(delta, "tool_calls", None) or []:
                index = getattr(tool_delta, "index", None)
                if index is None:
                    index = len(tool_call_parts)
                state = tool_call_parts.setdefault(index, {
                    "id": "", "type": "function", "name": "", "arguments": "",
                    "extras": {}, "function_extras": {},
                })
                if getattr(tool_delta, "id", None):
                    state["id"] = tool_delta.id
                if getattr(tool_delta, "type", None):
                    state["type"] = tool_delta.type
                function = getattr(tool_delta, "function", None)
                if function is not None:
                    if getattr(function, "name", None):
                        state["name"] += function.name
                    if getattr(function, "arguments", None):
                        state["arguments"] += function.arguments
                plain_delta = _plain_data(tool_delta)
                if isinstance(plain_delta, dict):
                    for key, value in plain_delta.items():
                        if key not in ("index", "id", "type", "function") and value is not None:
                            state["extras"][key] = value
                    plain_function = plain_delta.get("function")
                    if isinstance(plain_function, dict):
                        for key, value in plain_function.items():
                            if key not in ("name", "arguments") and value is not None:
                                state["function_extras"][key] = value

        if displayed_any:
            print(file=sys.stderr, flush=True)

        tool_calls = []
        for index in sorted(tool_call_parts):
            state = tool_call_parts[index]
            tool_calls.append(SimpleNamespace(
                id=state["id"],
                type=state["type"],
                function=SimpleNamespace(
                    name=state["name"],
                    arguments=state["arguments"],
                    **state["function_extras"],
                ),
                **state["extras"],
            ))

        message = SimpleNamespace(
            content="".join(content_parts),
            tool_calls=tool_calls or None,
            reasoning_content="".join(reasoning_parts["reasoning_content"]) or None,
            reasoning="".join(reasoning_parts["reasoning"]) or None,
            reasoning_details=reasoning_details or None,
        )
        inline = self._strip_inline_thinking(message)
        if inline and not displayed_any:
            _log_section(f"模型思考 · {purpose} · <think>")
            print(inline, file=sys.stderr, flush=True)
            displayed_any = True
        if not displayed_any:
            _log_warn(f"{purpose} 已启用思考，但模型/网关未返回可显示的思考内容")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
            usage=usage,
        )

    def _completion_error_context(self, purpose, attempt, phase="request"):
        return {
            "purpose": purpose,
            "phase": phase,
            "attempt": attempt,
            "max_attempts": len(_COMPLETION_RETRY_DELAYS) + 1,
            "model": getattr(self, "model_name", None),
            "api_url": _redact_url(getattr(self, "api_url", None)),
            "mode": getattr(self, "mode", None),
            "effort": getattr(self, "effort", None),
            "thinking": bool(getattr(self, "thinking", False)),
            "unique_id": getattr(self, "unique_id", None),
        }

    @staticmethod
    def _raise_if_interrupted(error):
        if (_COMFY_AVAILABLE
                and isinstance(error, comfy.model_management.InterruptProcessingException)):
            raise error

    def _create_completion_once(self, *, purpose="LLM", **kwargs):
        """执行一次逻辑请求，并保留 thinking 流式到非流式的兼容回退。"""
        if not getattr(self, "thinking", False):
            return self.llm.chat.completions.create(**kwargs)

        try:
            stream = self.llm.chat.completions.create(stream=True, **kwargs)
        except Exception as stream_error:
            self._raise_if_interrupted(stream_error)
            log_path = write_agent_error_log(
                stream_error,
                context=self._completion_error_context(
                    purpose, 1, phase="streaming_compatibility_fallback",
                ),
                completion_args={**kwargs, "stream": True},
            )
            log_hint = f"；完整诊断: {log_path}" if log_path else ""
            _log_warn(
                f"{purpose} 流式请求不可用，回退非流式: "
                f"{format_agent_error_summary(stream_error)}{log_hint}"
            )
            response = self.llm.chat.completions.create(**kwargs)
            self._log_non_stream_reasoning(response, purpose)
            return response

        # A few compatibility layers ignore stream=True and return a normal response.
        choices = getattr(stream, "choices", None)
        if choices and getattr(choices[0], "message", None) is not None:
            self._log_non_stream_reasoning(stream, purpose)
            return stream
        try:
            return self._consume_completion_stream(stream, purpose)
        except _StreamUnavailableError as stream_error:
            log_path = write_agent_error_log(
                stream_error,
                context=self._completion_error_context(
                    purpose, 1, phase="stream_consumption_compatibility_fallback",
                ),
                completion_args={**kwargs, "stream": True},
            )
            log_hint = f"；完整诊断: {log_path}" if log_path else ""
            _log_warn(
                f"{purpose} 流式响应不可用，回退非流式: "
                f"{format_agent_error_summary(stream_error)}{log_hint}"
            )
            response = self.llm.chat.completions.create(**kwargs)
            self._log_non_stream_reasoning(response, purpose)
            return response

    def _create_completion(self, *, purpose="LLM", **kwargs):
        """统一 LLM 调用入口：失败后按 1s/2s/4s 指数退避重试三次。"""
        log_path = None
        max_attempts = len(_COMPLETION_RETRY_DELAYS) + 1
        for attempt in range(1, max_attempts + 1):
            if _COMFY_AVAILABLE:
                comfy.model_management.throw_exception_if_processing_interrupted()
            try:
                return self._create_completion_once(purpose=purpose, **kwargs)
            except Exception as error:
                self._raise_if_interrupted(error)
                log_path = write_agent_error_log(
                    error,
                    context=self._completion_error_context(purpose, attempt),
                    completion_args=kwargs,
                    log_path=log_path,
                )
                summary = format_agent_error_summary(error)
                log_hint = f"；完整诊断: {log_path}" if log_path else ""
                if attempt >= max_attempts:
                    _log_error(
                        f"{purpose} 请求失败，三次重试均未恢复: {summary}{log_hint}"
                    )
                    raise

                delay = _COMPLETION_RETRY_DELAYS[attempt - 1]
                _log_warn(
                    f"{purpose} 请求失败: {summary}；{delay}s 后进行第 "
                    f"{attempt}/{len(_COMPLETION_RETRY_DELAYS)} 次重试{log_hint}"
                )
                self._trace(
                    "retry",
                    status="warning",
                    title="LLM retry",
                    summary=f"{purpose} · {delay}s 后重试",
                    details={
                        "purpose": purpose,
                        "retry": attempt,
                        "max_retries": len(_COMPLETION_RETRY_DELAYS),
                        "delay_seconds": delay,
                        "error_type": type(error).__name__,
                        "status_code": getattr(
                            getattr(error, "response", None), "status_code", None,
                        ),
                        "log_path": log_path,
                    },
                )
                time.sleep(delay)

        raise RuntimeError("unreachable")

    def _rewrite_query(self, question, image=None):
        _log_section("查询重写")
        prompt = QUERY_REWRITE_PROMPT.format(question=question)
        user_content = prompt
        if image is not None:
            b64 = utils.tensor_to_base64(image)
            user_content = [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ]

        # 查询重写强制关闭思考，不继承主 Agent 的 reasoning/thinking 设置。
        # 测试或旧式手工构造的 PromptAgent 可能没有该属性，此时安全回退为空参数。
        rewrite_extra_body = getattr(self, "_rewrite_extra_body", {})
        # 尝试两次：第一次显式关闭 reasoning，若网关不接受该参数则去掉后重试。
        extra_body_list = [rewrite_extra_body]
        if rewrite_extra_body.get("reasoning"):
            extra_body_list.append({
                k: v for k, v in rewrite_extra_body.items() if k != "reasoning"
            })

        for attempt, extra_body in enumerate(extra_body_list):
            raw = None
            try:
                resp = self._create_completion(
                    purpose="查询重写",
                    model=self.model_name,
                    messages=[{"role": "user", "content": user_content}],
                    temperature=0.3,
                    extra_body=extra_body,
                )
                choice = resp.choices[0]
                raw, source = _message_text_from_content_or_reasoning(choice.message)
                if source != "content" and source != "empty":
                    _log(f"查询重写使用 {source} 字段解析响应")
                if not raw or not raw.strip():
                    finish_reason = getattr(choice, "finish_reason", "unknown")
                    _log_warn(
                        f"查询重写空响应详情: finish_reason={finish_reason}, "
                        f"{_usage_summary(getattr(resp, 'usage', None))}"
                    )
                    if attempt == 0 and len(extra_body_list) > 1:
                        _log_warn("查询重写返回空响应，去掉 reasoning 参数重试...")
                        continue
                    _log_warn("查询重写 LLM 返回空响应，跳过重写")
                    return "", []
                raw = raw.strip().strip("```json").strip("```").strip()
                variants = json.loads(raw)
                if isinstance(variants, list):
                    user_tags = ""
                    dimensions = []
                    for v in variants:
                        v = str(v).strip()
                        if not v:
                            continue
                        if v.startswith("[已有]"):
                            user_tags = v.replace("[已有]", "").strip()
                            _log(f"  [已有] 用户标签: {user_tags[:80]}...")
                        else:
                            dimensions.append(v)
                    _log(f"用户输入拆解为 {len(dimensions)} 个搜索维度 + {'已有标签' if user_tags else '无已有标签'}")
                    for i, q in enumerate(dimensions, 1):
                        _log(f"  {i}. {q}")
                    return user_tags, dimensions
            except Exception as e:
                if attempt == 0 and len(extra_body_list) > 1:
                    _log_warn(
                        f"查询重写失败（{format_agent_error_summary(e)}），"
                        "去掉 reasoning 参数重试..."
                    )
                    continue
                _log_warn(f"查询重写失败（已跳过）: {format_agent_error_summary(e)}")
                if raw is not None:
                    _log_warn(f"LLM 响应体: {raw[:500]}")
        return "", []

    def _execute_tool(self, name, args):
        if name == "search_tags":
            # 若 LLM 未指定 search_mode / include_wiki，使用当前 effort 级别的默认值
            default_mode = self._effort_cfg.get("search_mode", "full_scene")
            default_wiki = self._effort_cfg.get("include_wiki", False)
            return execute_search_tags(
                query=str(args.get("query", "")),
                search_mode=str(args.get("search_mode", default_mode)),
                category=str(args.get("category", "all")),
                show_nsfw=bool(args.get("show_nsfw", True)),
                include_wiki=bool(args.get("include_wiki", default_wiki)),
            )
        elif name == "get_related_tags":
            args["limit"] = min(int(args.get("limit", 30)), self._effort_cfg["related_limit"])
            tags = args.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            return execute_get_related_tags(
                tags=tags,
                limit=int(args.get("limit", 30)),
                show_nsfw=bool(args.get("show_nsfw", True)),
                include_wiki=bool(args.get("include_wiki", False)),
            )
        elif name == "get_artist_recommendations":
            tags = args.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            return execute_get_artist_recommendations(
                tags=tags,
                limit=int(args.get("limit", 30)),
                min_cooc=int(args.get("min_cooc", 3)),
                show_nsfw=bool(args.get("show_nsfw", True)),
            )
        elif name == "get_artist_profile":
            return execute_get_artist_profile(
                artist_name=str(args.get("artist_name", "")),
                top_n=int(args.get("top_n", 20)),
                show_nsfw=bool(args.get("show_nsfw", True)),
            )
        elif name == "get_anima_format":
            return execute_get_anima_format()
        elif name == "get_newbie_format":
            return execute_get_newbie_format()
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

    def _log_tool_call(self, name, args):
        if name == "search_tags":
            query_str = args.get("query", "")
            mode = args.get("search_mode", "full_scene")
            _log(f"  > 搜索标签：{query_str}", _C.GREEN)
            _log(f"    [search_tags] mode={mode}, category={args.get('category', 'all')}")
        elif name == "get_related_tags":
            tags = args.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            _log(f"  > 关联推荐：{', '.join(tags[:5])}", _C.GREEN)
            _log(f"    [get_related_tags] tags={len(tags)}, limit={args.get('limit', 30)}")
        elif name == "get_artist_recommendations":
            tags = args.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            _log(f"  > 画师推荐：{', '.join(tags[:5])}", _C.GREEN)
            _log(f"    [get_artist_recommendations] tags={len(tags)}, limit={args.get('limit', 30)}")
        elif name == "get_artist_profile":
            artist_name = str(args.get("artist_name", "")).strip()
            _log(f"  > 画师画像：{artist_name}", _C.GREEN)
            _log(f"    [get_artist_profile] top_n={args.get('top_n', 20)}")
        elif name == "get_anima_format":
            _log(f"  > 获取 Anima 格式规范", _C.GREEN)
        elif name == "get_newbie_format":
            _log(f"  > 获取 NewBie 格式规范", _C.GREEN)
        else:
            _log(f"  > 调用工具：{name}", _C.GREEN)

    def _log_tool_result(self, name, result_str):
        if name in ("get_anima_format", "get_newbie_format"):
            _log(f"    格式规范已获取 ({len(result_str)} chars)", _C.GREEN)
            return
        try:
            data = json.loads(result_str)
            if name == "get_artist_profile":
                if data.get("artist"):
                    top_tags = data.get("top_tags", [])
                    _log(f"    画师 {data['artist']}：{len(top_tags)} 个常见标签", _C.GREEN)
                elif data.get("error"):
                    _log_warn(f"    工具返回错误: {data['error']}")
                else:
                    _log("    未找到唯一画师", _C.WARNING)
                return
            results = data.get("results", [])
            if results:
                _log(f"    找到 {len(results)} 个标签", _C.GREEN)
            elif data.get("error"):
                _log_warn(f"    工具返回错误: {data['error']}")
            else:
                _log("    未找到标签", _C.WARNING)
        except Exception:
            pass

    def _tool_trace_summary(self, name, args):
        if name == "search_tags":
            return str(args.get("query", "")).strip()
        if name == "get_related_tags":
            tags = args.get("tags", [])
            if isinstance(tags, str):
                return tags[:120]
            return ", ".join(map(str, tags[:4]))
        if name == "get_artist_recommendations":
            tags = args.get("tags", [])
            if isinstance(tags, str):
                return tags[:120]
            return f"{len(tags)} tags"
        if name == "get_artist_profile":
            return str(args.get("artist_name", "")).strip()
        if name in ("get_anima_format", "get_newbie_format"):
            return "读取输出格式规范"
        return ""

    def _tool_result_summary(self, name, result_str):
        if name in ("get_anima_format", "get_newbie_format"):
            return f"{len(result_str)} chars"
        try:
            data = json.loads(result_str)
        except Exception:
            return f"{len(result_str)} chars"
        if data.get("error"):
            return str(data["error"])[:140]
        if name == "get_artist_profile":
            artist = data.get("artist")
            top_tags = data.get("top_tags", [])
            if artist:
                return f"{artist}: {len(top_tags)} common tags"
            candidates = data.get("candidates", [])
            if isinstance(candidates, list) and candidates:
                return f"{len(candidates)} artist candidates"
            return "artist not found"
        results = data.get("results", [])
        if isinstance(results, list) and results:
            return f"{len(results)} tags"
        prompt = data.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return f"{len([t for t in prompt.split(',') if t.strip()])} prompt tags"
        return "完成"

    def _compact_tool_result(self, result_str):
        try:
            data = json.loads(result_str)
        except Exception:
            return {"text": result_str[:1200]}
        compact = {}
        for key in ("prompt", "error", "skipped", "note"):
            value = data.get(key)
            if value:
                compact[key] = str(value)[:1200]
        for key in ("artist", "input", "matched_by", "post_count"):
            if key in data:
                compact[key] = data[key]
        results = data.get("results")
        if isinstance(results, list):
            compact["results"] = results[:8]
            compact["result_count"] = len(results)
        top_tags = data.get("top_tags")
        if isinstance(top_tags, list):
            compact["top_tags"] = top_tags[:8]
            compact["top_tag_count"] = len(top_tags)
        candidates = data.get("candidates")
        if isinstance(candidates, list):
            compact["candidates"] = candidates[:8]
        return compact or {"text": result_str[:1200]}

    @staticmethod
    def _extract_tag_list(result_str: str) -> list[str]:
        """保序提取标签列表。`prompt` 字段按 MCP 端打分降序排列，
        顺序即匹配强度，供"已覆盖概念重搜"的前 K 名判据使用。
        缺失时回退到 `results[].tag`。
        """
        try:
            data = json.loads(result_str)
        except Exception:
            return []
        prompt = data.get("prompt")
        if isinstance(prompt, str) and prompt.strip():
            return [t.strip() for t in prompt.split(",") if t.strip()]
        return [
            (t.get("tag") or "").strip()
            for t in data.get("results", [])
            if (t.get("tag") or "").strip()
        ]

    @staticmethod
    def _extract_tag_names(result_str: str) -> set[str]:
        """从工具返回中提取标签名集合，用于信息增量统计（顺序无关）。"""
        return set(PromptAgent._extract_tag_list(result_str))

    @staticmethod
    def _collect_cn_from_result(result_str: str) -> dict[str, str]:
        """从工具返回的 JSON 中提取 {tag: cn_name} 映射。"""
        mapping = {}
        try:
            data = json.loads(result_str)
            for t in data.get("results", []):
                tag = (t.get("tag") or "").strip()
                cn = (t.get("cn_name") or "").strip()
                if tag and cn:
                    mapping[tag] = cn
            for t in data.get("top_tags", []):
                tag = (t.get("tag") or "").strip()
                cn = (t.get("cn_name") or "").strip()
                if tag and cn:
                    mapping[tag] = cn
        except Exception:
            pass
        return mapping

    def _get_output_format_section(self):
        return get_output_format_section(self)

    def _fallback_normal(self, user_text, image):
        return fallback_normal(self, user_text, image)

    # ── Low effort 子步骤（从 _run_low_effort 拆分） ─────────────────

    def _batch_search_tags(self, dimensions):
        return batch_search_tags(self, dimensions)

    def _explore_related_tags(self, all_tag_names, user_text):
        return explore_related_tags(self, all_tag_names, user_text)

    def _assemble_low_output(self, all_tag_names, tag_cn_map, user_text, user_tags, image):
        return assemble_low_output(
            self, all_tag_names, tag_cn_map, user_text, user_tags, image,
        )

    # ── Low effort 主流程 ───────────────────────────────────────────

    def _run_low_effort(self, user_text, image=None):
        return run_low_effort(self, user_text, image)

    def _force_final_output(self, messages):
        return force_final_output(self, messages)

    def run(self, user_text, image=None, force_full_run=False):
        self._trace(
            "start",
            status="running",
            title="Agent started",
            summary=f"{self.effort} · {self.mode}",
            details={"effort": self.effort, "mode": self.mode},
        )
        # ── 基线判定（所有 effort 通用）：复用 / 续写 / 冷跑 ──
        baseline = get_baseline_store().get(self.unique_id)
        if force_full_run:
            _log("Force full Agent run enabled: ignoring incremental baseline for this run.")
            self._trace(
                "path",
                status="warning",
                title="Force full run",
                summary="忽略增量基线，本次完整运行",
            )
            decision, edit = ("cold", None)
        else:
            decision, edit = self._decide_baseline(baseline, user_text, image)
        previous_continuations = int((baseline or {}).get("continuation_count") or 0)
        continuation_count = previous_continuations + 1 if decision == "continue" else 0
        if decision == "continue" and previous_continuations >= _MAX_CONSECUTIVE_CONTINUATIONS:
            _log(
                f"连续原位修改已达 {previous_continuations} 次，"
                "本次自动完整重跑以刷新基线。"
            )
            self._trace(
                "path",
                status="warning",
                title="Auto full run",
                summary=f"连续原位修改 {previous_continuations} 次后自动全量重跑",
                details={
                    "path": "cold",
                    "reason": "continuation_limit",
                    "continuation_count": previous_continuations,
                },
            )
            decision, edit = ("cold", None)
            continuation_count = 0
        if decision == "reuse":
            self._trace(
                "complete",
                status="success",
                title="Reused previous result",
                summary="零调用复用上次输出",
                details={"path": "reuse"},
            )
            return self._parse_output(baseline["output"])

        # Low effort：流水线冷跑 / 增量修订续写
        if self.effort == "Low":
            if decision == "continue":
                self._trace(
                    "path",
                    status="running",
                    title="Low continuation",
                    summary="增量修订路径",
                    details={"path": "continue", "edit": edit},
                )
                xml_out, text_out, content = self._run_low_continuation(user_text, baseline, edit)
            else:
                self._trace(
                    "path",
                    status="running",
                    title="Low cold run",
                    summary="完整流水线路径",
                    details={"path": "cold"},
                )
                xml_out, text_out, content = self._run_low_effort(user_text, image)
            self._store_baseline(
                user_text,
                content,
                image,
                baseline.get("format_spec") if baseline else None,
                continuation_count=continuation_count,
            )
            self._trace(
                "complete",
                status="success",
                title="Agent complete",
                summary="Low effort 输出已解析",
            )
            return xml_out, text_out

        # Agent 模式：续写 / 冷跑
        _log_banner("Agent 模式已启用，开始处理用户输入...")
        _log(f"模式: {self.mode} | Effort: {self.effort} | MCP: HF (主) / MS (备)")
        if decision == "continue":
            self._trace(
                "path",
                status="running",
                title="Continuation",
                summary=f"变更块 {edit['blocks']} · 相似度 {edit['ratio']:.2f}",
                details={"path": "continue", "edit": edit},
            )
            build = self._build_continuation(baseline, edit, user_text)
        else:
            self._trace(
                "path",
                status="running",
                title="Cold run",
                summary="完整 Agent 探索",
                details={"path": "cold"},
            )
            build = self._build_cold_run(user_text, image)
        messages, max_rounds, provided_norm = build

        content, rounds, total_tokens, captured_spec = self._run_agent_loop(
            messages, max_rounds, provided_norm,
        )

        _log_section("输出解析")
        self._trace("parse", status="running", title="Parsing output", summary=self.mode)
        xml_out, text_out = self._parse_output(content)

        # 压平存档：本次结果成为下次 diff 的基线（每节点只存上一次）。
        # 格式规范：本轮抓到的优先，否则沿用上一轮基线的（跨续写链保留，不重复调 MCP）。
        fmt_spec = captured_spec or (baseline.get("format_spec") if baseline else None)
        self._store_baseline(
            user_text,
            content,
            image,
            fmt_spec,
            continuation_count=continuation_count,
        )

        _log_banner(f"Agent 完成 | 总轮次: {rounds + 1} | 总 Token: {total_tokens}")
        self._trace(
            "complete",
            status="success",
            title="Agent complete",
            summary=f"{rounds + 1} 轮 · {total_tokens} tokens",
            details={"rounds": rounds + 1, "tokens": total_tokens},
        )
        return xml_out, text_out

    def _decide_baseline(self, baseline, user_text, image):
        """基线判定（所有 effort 通用）。返回 (decision, edit)：
        decision ∈ {"reuse", "continue", "cold"}；continue 时附带 edit。
        """
        if not (baseline
                and baseline.get("mode") == self.mode
                and baseline.get("output")):
            return ("cold", None)
        if image is None:
            if baseline.get("has_image"):
                return ("cold", None)
        else:
            current_fingerprint = utils.image_fingerprint(image)
            if not (baseline.get("has_image")
                    and baseline.get("image_fingerprint")
                    and current_fingerprint == baseline.get("image_fingerprint")):
                return ("cold", None)
        if normalize_prompt(user_text) == baseline.get("norm_input"):
            _log_ok("输入与上次完全一致，直接复用上次结果（零调用）")
            self._trace("path", status="success", title="Reuse", summary="输入与上次完全一致")
            return ("reuse", None)
        edit = compute_edit(baseline["raw_input"], user_text)
        _log(f"与上次 diff：变更块={edit['blocks']}，相似度={edit['ratio']:.2f}")
        if edit["blocks"] == 0:
            # 仅标点/空白变化，无实义 token 改动 → 标签集合不变，直接复用
            _log_ok("仅标点/空白变化，无实义改动，直接复用上次结果（零调用）")
            self._trace("path", status="success", title="Reuse", summary="仅标点/空白变化")
            return ("reuse", None)
        if edit["continue"]:
            return ("continue", edit)
        return ("cold", None)

    def _collect_provided_tags(self, user_text, rewrite_user_tags):
        """合并确定性抽取（正则）与查询重写的 [已有] 标记，返回 (provided_list, provided_norm)。
        确定性抽取不依赖重写 LLM，确保 LLM 漏标时已提供标签列表仍完整。
        """
        provided_list = utils.extract_provided_tags(user_text)
        provided_norm = {utils.normalize_tag(t) for t in provided_list}
        if rewrite_user_tags:
            for t in rewrite_user_tags.split(","):
                t = t.strip()
                tn = utils.normalize_tag(t)
                if t and tn not in provided_norm:
                    provided_list.append(t)
                    provided_norm.add(tn)
        return provided_list, provided_norm

    def _run_low_continuation(self, user_text, baseline, edit):
        return run_low_continuation(self, user_text, baseline, edit)

    def _build_cold_run(self, user_text, image):
        """冷跑路径：构造完整初始消息（查询重写、已提供标签、格式指令、图片）。
        Returns (messages, max_rounds, provided_norm)。
        """
        max_rounds = self._effort_cfg["max_rounds"]

        rewrite_queries = []
        user_tags = ""
        # Medium / High 的文本输入由首轮 Agent 直接完成查询规划，避免在
        # Agent 本身还会理解一次用户需求的情况下额外调用一遍重写 LLM。
        # 图片输入仍需要独立的多模态重写；Low effort 则走
        # _run_low_effort()，继续保留原有查询重写流水线。
        rewrite_performed = image is not None
        if rewrite_performed:
            user_tags, rewrite_queries = self._rewrite_query(user_text, image=image)
        else:
            _log("无图片输入：跳过独立查询重写，由首轮 Agent 直接规划搜索")

        system_content, fewshot_user, fewshot_assistant = get_agent_system_prompt(
            self.mode, self.config, max_rounds=max_rounds,
            model_name=getattr(self, "model_name", None),
        )
        messages = [{"role": "system", "content": system_content}]

        if fewshot_user and fewshot_assistant:
            messages.append({"role": "user", "content": fewshot_user})
            messages.append({"role": "assistant", "content": fewshot_assistant})
            _log("已注入 few-shot 示例")

        user_content = "<user_message>\n" + user_text + "\n</user_message>"

        # 用户已提供标签：确定性抽取（正则）+ 查询重写的 [已有] 标记，取并集。
        provided_list, provided_norm = self._collect_provided_tags(user_text, user_tags)
        provided_str = ", ".join(provided_list)
        if provided_list:
            _log(f"确定性抽取到用户已提供标签 {len(provided_list)} 个，将禁止重复检索")

        if provided_str:
            user_content += "\n\n【用户已提供标签（直接信任，禁止检索）】\n" + provided_str
            if rewrite_queries:
                user_content += (
                    "\n\n上述标签已覆盖部分维度（如人设、角色、服装等），直接信任、禁止检索；"
                    "你**只需要**检索下方【待搜索维度】中的内容。"
                )
            else:
                # 未执行重写时，不能仅凭“存在已有标签”断定原始输入已覆盖
                # 全部要素；交由 Agent 从原始 user_message 判断剩余检索范围。
                user_content += (
                    "\n\n请自行判断原始输入中是否还有未被上述标签覆盖的自然语言需求。"
                    "若有，只检索尚未覆盖的内容；若确认输入完全由已有标签构成，则无需搜索。"
                )
            _log(f"已注入禁止检索的已提供标签: {len(provided_list)} 个")
        if rewrite_queries:
            user_content += "\n\n【待搜索维度（仅检索以下内容，禁止检索已覆盖概念）】\n" + "\n".join("- " + q for q in rewrite_queries)
        elif not rewrite_performed:
            user_content += (
                "\n\n【搜索规划】本次未执行独立查询重写。"
                "请在首轮直接理解 <user_message>，识别尚未覆盖的搜索维度，"
                "并按系统工作流规划并行检索。"
            )

        # 注入格式工具调用指令（根据 mode 动态选择）
        user_content += get_format_tool_directive(self.mode)

        if image is not None:
            b64 = utils.tensor_to_base64(image)
            messages.append({"role": "user", "content": [
                {"type": "text", "text": user_content},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ]})
            _log("已附加图片输入（多模态模式）")
        else:
            messages.append({"role": "user", "content": user_content})

        return messages, max_rounds, provided_norm

    def _build_continuation(self, baseline, edit, user_text):
        """增量修订续写：把上次(提示词→输出)作为对话上文，再给出本轮修改后的
        完整提示词，让模型自行对比两段文本、做最小化修订（before/after，
        不再注入 difflib 的祈使指令——后者在无标点连写/重排/同义整改时易过抓或自相矛盾）。
        Returns (messages, max_rounds, provided_norm)。
        """
        _log_banner("增量修订模式：在上一轮结果基础上续写")
        # _log(f"改动(仅日志，不喂模型)：{edit['instruction']}")
        max_rounds = _REVISION_MAX_ROUNDS
        system_content, _, _ = get_agent_system_prompt(
            self.mode, self.config, max_rounds=max_rounds,
            model_name=getattr(self, "model_name", None),
        )
        # 复用上一轮已抓取、随基线保留的格式规范（不额外调 MCP），
        # 否则续写只能模仿上一轮输出，易偏离标题/结构（如 ### 中文解释、改动说明）。
        spec = baseline.get("format_spec")
        if spec:
            system_content += (
                "\n\n# 输出格式规范（权威参考，标题与整体结构必须严格遵守）\n\n" + spec
            )
        if self.mode == "Anima":
            fmt_hint = (
                "必须保留 `## Prompt` 和 `## 中文解释` 两个标题；"
                "`## 中文解释` 段照常写完整的中文设计说明（针对最终成品，不是改动清单）。"
            )
        else:
            fmt_hint = "保留同样的 `<img>` XML 代码块及其后的中文翻译。"
        revise_directive = (
            "用户在上一轮提示词（见上文 user 消息）的基础上做了修改。"
            "修改后的完整提示词如下：\n"
            "<user_message>\n" + user_text + "\n</user_message>\n\n"
            "请对比修改前后的两段提示词，找出发生变化的部分，"
            "在上一轮输出的基础上进行**最小化修订**："
            "只改动与变化直接相关的标签，其余标签与上一轮输出逐字保持一致。"
            "新出现的维度可调用工具检索；未改动、已确定的维度禁止改动、禁止重新检索。\n\n"
            "**输出要求（严格）**：直接输出修订后的**完整结果**，结构与标题必须与上一轮输出逐字一致。"
            + fmt_hint
            + "禁止新增任何额外标题或说明段（例如「改动说明」「修改说明」），"
            "禁止输出任何关于你做了哪些改动的解释。"
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": "<user_message>\n" + baseline["raw_input"] + "\n</user_message>"},
            {"role": "assistant", "content": baseline["output"]},
            {"role": "user", "content": revise_directive},
        ]
        # 续写不启用已提供标签机制（模型在做修订，而非首轮检索）
        return messages, max_rounds, set()

    def _store_baseline(self, user_text, content, image, format_spec=None, continuation_count=0):
        """压平：把本次(提示词→最终输出)存为新基线，供下次 diff 续写。

        format_spec 随基线保留（不丢弃格式规范），续写时直接复用，避免重复调 MCP。
        """
        if not content or not content.strip():
            return
        try:
            get_baseline_store().put(self.unique_id, {
                "norm_input": normalize_prompt(user_text),
                "raw_input": user_text,
                "output": content,
                "mode": self.mode,
                "has_image": image is not None,
                "image_fingerprint": utils.image_fingerprint(image) if image is not None else None,
                "format_spec": format_spec,
                "continuation_count": int(continuation_count or 0),
            })
        except Exception:
            pass  # 基线写入失败不影响主流程

    def _run_agent_loop(self, messages, max_rounds, provided_norm):
        return run_agent_loop(
            self, messages, max_rounds, provided_norm,
            error_writer=write_agent_error_log,
            tools_provider=get_tools,
        )

    def _parse_output(self, content):
        return parse_output(self.mode, content, self.config)

    def _parse_anima_output(self, content):
        return parse_anima_output(content)

    def _parse_newbie_output(self, content):
        return parse_newbie_output(content, self.config)
