"""Low-effort pipeline and Low incremental revision flow."""

import json

from prompt_agent import utils
from prompt_agent.agent_prompts import LOW_ASSEMBLY_PROMPT
from prompt_agent.console import (
    _C, _log, _log_warn, _log_error, _log_section, _log_banner,
)
from prompt_agent.diagnostics import format_agent_error_summary
from prompt_agent.tools import get_tools, execute_search_tags, execute_get_related_tags

try:
    import comfy.utils
    import comfy.model_management
    _COMFY_AVAILABLE = True
except ImportError:
    _COMFY_AVAILABLE = False


def get_output_format_section(agent):
    from prompt_agent.agent_prompts import _NEWBIE_OUTPUT_FORMAT, _ANIMA_OUTPUT_FORMAT
    if agent.mode == "Anima":
        return _ANIMA_OUTPUT_FORMAT
    return _NEWBIE_OUTPUT_FORMAT


def fallback_normal(agent, user_text, image):
    _log_warn("回退为普通模式（无工具调用）")
    from prompt_agent.agent_prompts import get_agent_system_prompt
    system_content, fu, fa = get_agent_system_prompt(
        agent.mode, agent.config,
        model_name=getattr(agent, "model_name", None),
    )
    messages = [{"role": "system", "content": system_content}]
    if fu and fa:
        messages.append({"role": "user", "content": fu})
        messages.append({"role": "assistant", "content": fa})
    user_content = "<user_message>\n" + user_text + "\n</user_message>"
    if image is not None:
        b64 = utils.tensor_to_base64(image)
        messages.append({"role": "user", "content": [
            {"type": "text", "text": user_content},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]})
    else:
        messages.append({"role": "user", "content": user_content})
    try:
        resp = agent._create_completion(
            purpose="回退生成",
            model=agent.model_name, messages=messages,
            temperature=0.7, extra_body=agent._extra_body,
        )
        content = resp.choices[0].message.content or ""
    except Exception as e:
        _log_error(f"回退模式 LLM 调用失败: {format_agent_error_summary(e)}")
        raise
    _log_section("输出解析")
    xml_out, text_out = agent._parse_output(content)
    return xml_out, text_out, content


def batch_search_tags(agent, dimensions):
    """对每个维度执行 search_tags，收集标签。"""
    _log_section("批量搜索标签")
    all_tag_names = []
    tag_cn_map: dict[str, str] = {}
    for dim in dimensions:
        _log(f"  > 搜索：{dim}", _C.GREEN)
        result_str = execute_search_tags(
            query=dim, search_mode="full_scene", show_nsfw=True,
        )
        try:
            data = json.loads(result_str)
            results = data.get("results", [])
            if results:
                _log(f"    找到 {len(results)} 个标签", _C.GREEN)
                for item in results:
                    tag = item.get("tag", "")
                    if tag:
                        all_tag_names.append(tag)
                    cn = (item.get("cn_name") or "").strip()
                    if tag and cn:
                        tag_cn_map[tag] = cn
            else:
                _log("    未找到标签", _C.WARNING)
        except Exception:
            pass
    _log(f"共收集 {len(all_tag_names)} 个标签")
    return all_tag_names, tag_cn_map


def explore_related_tags(agent, all_tag_names, user_text):
    """让 LLM 选择标签调用 get_related_tags 进行一次关联探索。"""
    _log_section("标签关联探索")
    tools_related = [t for t in get_tools() if t["function"]["name"] == "get_related_tags"]
    tags_preview = ", ".join(all_tag_names[:60])
    if len(all_tag_names) > 60:
        tags_preview += f", ... (共 {len(all_tag_names)} 个)"

    step3_system = (
        "你是提示词标签专家。以下是搜索到的标签集合。\n"
        "你可以调用 get_related_tags 工具来发现与这些标签共现的补充标签。\n"
        "选择你认为对画面构建最有价值的 5-10 个标签传入工具。调用一次即可。\n\n"
        "标签集合：" + tags_preview
    )
    step3_messages = [
        {"role": "system", "content": step3_system},
        {"role": "user", "content": user_text},
    ]

    try:
        resp = agent._create_completion(
            purpose="标签关联探索",
            model=agent.model_name, messages=step3_messages,
            tools=tools_related, tool_choice="auto",
            temperature=0.7,
            extra_body=agent._extra_body,
        )
        msg = resp.choices[0].message
        if resp.usage:
            agent._log_token_usage(resp.usage)

        if msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {}
                if name != "get_related_tags":
                    _log_warn(f"Low effort 不允许调用 {name}，跳过")
                    continue
                args["limit"] = min(int(args.get("limit", 30)), 50)
                agent._log_tool_call(name, args)
                result = execute_get_related_tags(
                    tags=args.get("tags", []),
                    limit=int(args.get("limit", 30)),
                    show_nsfw=bool(args.get("show_nsfw", True)),
                    include_wiki=bool(args.get("include_wiki", False)),
                )
                agent._log_tool_result(name, result)
                try:
                    related_data = json.loads(result)
                    for item in related_data.get("results", []):
                        tag = item.get("tag", "")
                        if tag:
                            all_tag_names.append(tag)
                except Exception:
                    pass
    except Exception as e:
        _log_warn(
            f"Step 3 LLM 调用失败（已跳过关联探索）: "
            f"{format_agent_error_summary(e)}"
        )

    _log(f"最终标签集合: {len(all_tag_names)} 个")
    return all_tag_names


def assemble_low_output(agent, all_tag_names, tag_cn_map, user_text, user_tags, image):
    """整合标签，LLM 组装最终 prompt 并解析。"""
    _log_section("组装最终 prompt")
    from prompt_agent.agent_prompts import get_agent_system_prompt
    output_format = LOW_ASSEMBLY_PROMPT.format(
        output_format_section=agent._get_output_format_section(),
    )
    _, fewshot_user, fewshot_assistant = get_agent_system_prompt(
        agent.mode, agent.config,
        model_name=getattr(agent, "model_name", None),
    )

    assembly_messages = [{"role": "system", "content": output_format}]
    if fewshot_user and fewshot_assistant:
        assembly_messages.append({"role": "user", "content": fewshot_user})
        assembly_messages.append({"role": "assistant", "content": fewshot_assistant})

    tags_str = ", ".join(all_tag_names)
    user_content = "<user_message>\n" + user_text + "\n</user_message>"
    if user_tags:
        user_content += "\n\n【用户已提供标签（直接信任，禁止检索）】\n" + user_tags
        user_content += "\n以上标签已由用户提供，直接使用，禁止检索这些标签或其变体。"
    user_content += "\n\n【预搜索标签集合】\n" + tags_str

    if image is not None:
        b64 = utils.tensor_to_base64(image)
        assembly_messages.append({"role": "user", "content": [
            {"type": "text", "text": user_content},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
        ]})
    else:
        assembly_messages.append({"role": "user", "content": user_content})

    try:
        resp = agent._create_completion(
            purpose="最终提示词组装",
            model=agent.model_name, messages=assembly_messages,
            temperature=0.7, extra_body=agent._extra_body,
        )
        content = resp.choices[0].message.content or ""
        if resp.usage:
            agent._log_token_usage(resp.usage)
    except Exception as e:
        _log_error(f"组装阶段 LLM 调用失败: {format_agent_error_summary(e)}")
        raise

    _log_section("输出解析")
    xml_out, text_out = agent._parse_output(content)
    _log_banner("Low effort 完成")
    return xml_out, text_out, content


def run_low_effort(agent, user_text, image=None):
    """Low effort 流水线模式：重写 → 搜索 → 关联 → 组装。"""
    _log_banner("Low effort 流水线模式已启用")
    _log(f"模式: {agent.mode} | Effort: Low | MCP: HF (主) / MS (备)")

    pbar = comfy.utils.ProgressBar(4, node_id=agent.unique_id) if _COMFY_AVAILABLE else None

    def _tick(step):
        if _COMFY_AVAILABLE:
            comfy.model_management.throw_exception_if_processing_interrupted()
        if pbar:
            pbar.update_absolute(step)

    user_tags, dimensions = agent._rewrite_query(user_text, image=image)
    if not dimensions:
        dimensions = [user_text]
        _log("查询重写未返回结果，使用原始输入")
    provided_list, _ = agent._collect_provided_tags(user_text, user_tags)
    user_tags = ", ".join(provided_list)
    if provided_list:
        _log(f"确定性抽取到用户已提供标签 {len(provided_list)} 个，将禁止检索")
    _tick(1)

    all_tag_names, tag_cn_map = agent._batch_search_tags(dimensions)
    if not all_tag_names:
        _log_warn("所有维度均未搜索到标签，回退为普通模式")
        return agent._fallback_normal(user_text, image)
    _tick(2)

    all_tag_names = agent._explore_related_tags(all_tag_names, user_text)
    _tick(3)

    result = agent._assemble_low_output(
        all_tag_names, tag_cn_map, user_text, user_tags, image,
    )
    _tick(4)
    return result


def run_low_continuation(agent, user_text, baseline, edit):
    """Low 增量修订：搜索变更词后在上一轮输出基础上单次修订。"""
    _log_banner("Low 增量修订：在上一轮结果基础上修订")
    _log(f"改动：{edit['instruction']}")

    candidate_tags = []
    for term in edit.get("new_terms", []):
        result = execute_search_tags(query=term, search_mode="full_scene", show_nsfw=True)
        names = agent._extract_tag_list(result)
        if names:
            candidate_tags.extend(names)
            _log(f"  > 搜索变更词：{term} → {len(names)} 个候选", _C.GREEN)
        else:
            _log(f"  > 搜索变更词：{term} → 未找到", _C.WARNING)
    seen = set()
    candidate_tags = [t for t in candidate_tags if not (t in seen or seen.add(t))]

    if agent.mode == "Anima":
        fmt_hint = "必须保留 `## Prompt` 和 `## 中文解释` 两个标题；`## 中文解释` 写完整设计说明。"
    else:
        fmt_hint = "保留同样的 `<img>` XML 代码块及其后的中文翻译。"
    revise_directive = (
        "用户在上一轮提示词（见上文 user 消息）的基础上做了修改。"
        "修改后的完整提示词如下：\n"
        "<user_message>\n" + user_text + "\n</user_message>"
    )
    if candidate_tags:
        revise_directive += "\n\n为本次改动检索到的候选标签（按需选用）：\n" + ", ".join(candidate_tags)
    revise_directive += (
        "\n\n请对比修改前后的两段提示词，在上一轮输出的基础上进行**最小化修订**："
        "只改动与变化直接相关的标签，"
        "其余标签与上一轮输出逐字保持一致。直接输出修订后的完整结果。"
        + fmt_hint
        + "禁止新增任何额外标题或说明段（如「改动说明」），禁止输出关于你做了哪些改动的解释。"
    )

    output_format = LOW_ASSEMBLY_PROMPT.format(
        output_format_section=agent._get_output_format_section(),
    )
    messages = [
        {"role": "system", "content": output_format},
        {"role": "user", "content": "<user_message>\n" + baseline["raw_input"] + "\n</user_message>"},
        {"role": "assistant", "content": baseline["output"]},
        {"role": "user", "content": revise_directive},
    ]
    try:
        resp = agent._create_completion(
            purpose="增量修订",
            model=agent.model_name, messages=messages,
            temperature=0.7, extra_body=agent._extra_body,
        )
        content = resp.choices[0].message.content or ""
        if resp.usage:
            agent._log_token_usage(resp.usage)
    except Exception as e:
        _log_error(f"Low 修订 LLM 调用失败: {format_agent_error_summary(e)}")
        raise

    _log_section("输出解析")
    xml_out, text_out = agent._parse_output(content)
    _log_banner("Low 增量修订完成")
    return xml_out, text_out, content
