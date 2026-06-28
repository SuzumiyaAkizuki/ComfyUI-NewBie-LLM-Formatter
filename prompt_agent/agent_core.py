"""
prompt_agent/agent_core.py
---------------------------
LLM_Prompt_Formatter 的 Agent 核心循环。
"""

from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from prompt_agent.agent_prompts import (
    get_agent_system_prompt,
    get_format_tool_directive,
    LOW_ASSEMBLY_PROMPT,
    QUERY_REWRITE_PROMPT,
)
from prompt_agent.tools import (
    get_tools,
    execute_search_tags,
    execute_get_related_tags,
    execute_get_artist_recommendations,
    execute_get_anima_format,
    execute_get_newbie_format,
)
from prompt_agent.cache import (
    get_baseline_store, compute_edit, normalize as normalize_prompt,
)
from prompt_agent import utils

try:
    import comfy.utils
    import comfy.model_management
    _COMFY_AVAILABLE = True
except ImportError:
    _COMFY_AVAILABLE = False

MAX_ROUNDS = 10

# 信息增量停滞检测：某轮搜索新增的「未见过」标签少于此阈值，记为一次停滞轮
_STAGNATION_MIN_NEW = 3
# 连续停滞轮次达到此值时，提前结束 Agent 探索并强制收尾输出
_STAGNATION_LIMIT = 2
# 单次工具返回中「新标签占比」低于此值时，向模型回灌"该方向已充分覆盖"的提示
_LOW_NOVELTY_RATIO = 0.34
# 搜索结果前 K 名（prompt 字段按匹配强度降序）若命中用户已提供标签，
# 判定为「重搜已覆盖概念」并回灌提示。取小而绝对的 K 以避免弱共现误报。
_PROVIDED_TOPK = 3
# 增量修订续写时的工具轮次上限：局部修订不需要全量轮次
_REVISION_MAX_ROUNDS = 3


def _sanitize_messages_for_gemini(messages):
    """规范化消息格式以兼容 Gemini API（通过 Vercel / OpenRouter 网关时的特殊处理）。

    处理三类 Gemini/Vertex 严格约束（OpenAI 容忍但 Gemini 会报 400）：

    1. assistant 消息携带 tool_calls 时不能同时携带 content。

    2. **单轮内的并行 tool_calls 必须拆分为顺序的「单调用→单响应」回合**（关键）。
       Gemini/Vertex 经网关转换时按 function 名匹配 functionCall / functionResponse，
       一个 model 回合里出现多个（尤其同名，如 3 个 search_tags）functionCall 时，
       会与 functionResponse 数量错配，报：
       "Please ensure that the number of function response parts is equal to the
       number of function call parts of the function call turn."（HTTP 400）。
       这里把 `assistant[call1,call2,call3] + tool(r1)+tool(r2)+tool(r3)` 重写为
       `assistant[call1]+tool(r1) / assistant[call2]+tool(r2) / assistant[call3]+tool(r3)`，
       每个回合只含 1 个 functionCall + 1 个 functionResponse。工具仍是并行执行的，
       这里只调整发送给 API 的历史结构，不影响执行性能与模型语义。

    3. function call turn 之后紧跟的独立 user 文本（如轮次进度提醒）会破坏配对，
       折叠进上一条 tool 消息的 content，保持响应回合纯净。

    返回的是消息的浅拷贝，不会修改调用方持有的原始 messages 列表。
    """
    # Pass 1：移除 assistant+tool_calls 的 content；折叠 tool 后的 user 文本
    sanitized = []
    for m in messages:
        mc = dict(m)
        if mc.get("role") == "assistant" and mc.get("tool_calls"):
            mc.pop("content", None)
        if (mc.get("role") == "user"
                and isinstance(mc.get("content"), str)
                and sanitized and sanitized[-1].get("role") == "tool"):
            prev = sanitized[-1]
            prev_content = prev.get("content") or ""
            prev["content"] = (prev_content + "\n\n" + mc["content"]) if prev_content else mc["content"]
            continue
        sanitized.append(mc)

    # Pass 2：将并行 tool_calls 拆分为顺序的单调用回合
    result = []
    i = 0
    n = len(sanitized)
    while i < n:
        m = sanitized[i]
        tool_calls = m.get("tool_calls") if m.get("role") == "assistant" else None
        if tool_calls and len(tool_calls) > 1:
            # 收集紧随其后的 tool 响应，按 tool_call_id 建立映射
            j = i + 1
            resp_by_id = {}
            while j < n and sanitized[j].get("role") == "tool":
                resp_by_id[sanitized[j].get("tool_call_id")] = sanitized[j]
                j += 1
            # 为每个 call 生成「单调用 assistant + 其响应」一对
            for tc in tool_calls:
                single = dict(m)
                single["tool_calls"] = [tc]
                single.pop("content", None)
                result.append(single)
                resp = resp_by_id.get(tc.get("id"))
                if resp is not None:
                    result.append(resp)
                else:
                    # 理论上不会发生：缺失响应时补占位，确保 1:1 配对
                    result.append({"role": "tool", "tool_call_id": tc.get("id"),
                                   "content": "{}"})
            i = j  # 跳过已消费的 tool 响应
        else:
            result.append(m)
            i += 1
    return result


def _dump_request_debug(sanitized_messages, tools):
    """API 调用失败时，将实际发送给 API 的完整请求体输出为 debug 日志。"""
    import json as _json
    payload = {
        "model": "(see agent_core.py model_name)",
        "messages": sanitized_messages,
        "tools": tools,
    }
    try:
        blob = _json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except Exception:
        blob = str(payload)
    _log_error("── 请求体 DEBUG DUMP ──")
    print(blob, file=sys.stderr, flush=True)
    _log_error("── DEBUG DUMP END ──")


class _C:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def _log(msg, color=""):
    prefix = f"{_C.BOLD}{_C.BLUE}[Agent]{_C.ENDC}"
    if color:
        print(f"{prefix} {color}{msg}{_C.ENDC}", file=sys.stderr, flush=True)
    else:
        print(f"{prefix} {msg}", file=sys.stderr, flush=True)

def _log_warn(msg):
    _log(f"⚠ {msg}", _C.WARNING)

def _log_error(msg):
    _log(f"✗ {msg}", _C.FAIL)

def _log_ok(msg):
    _log(f"✓ {msg}", _C.GREEN)

def _log_section(title):
    _log(f"── {title} " + "─" * max(0, 50 - len(title)))

def _log_round_header(round_num):
    _log(f"── Round {round_num} " + "─" * max(0, 50 - len(str(round_num)) - 7))

def _log_banner(msg):
    _log("═" * 55)
    _log(msg)
    _log("═" * 55)


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


def _serialize_tool_calls(tool_calls):
    """将 OpenAI tool_calls 对象序列化为 JSON-serializable dict 列表。"""
    if not tool_calls:
        return []
    result = []
    for tc in tool_calls:
        result.append({
            "id": tc.id,
            "type": tc.type,
            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
        })
    return result


def _message_text_from_content_or_reasoning(message):
    """Return visible content, falling back to provider reasoning fields.

    Some OpenAI-compatible gateways return HTTP 200 with empty ``content`` while
    placing the short final payload in ``reasoning``/``reasoning_content``.
    Query rewrite expects machine-readable JSON, so it is safe to try these
    provider fields before treating the response as empty.
    """
    content = getattr(message, "content", None)
    if content and str(content).strip():
        return str(content), "content"
    for attr in ("reasoning", "reasoning_content"):
        value = getattr(message, attr, None)
        if value and str(value).strip():
            return str(value), attr
    return "", "empty"


def _usage_summary(usage):
    if not usage:
        return "usage=n/a"
    prompt_tokens = getattr(usage, "prompt_tokens", "?")
    completion_tokens = getattr(usage, "completion_tokens", "?")
    total_tokens = getattr(usage, "total_tokens", "?")
    return f"usage={prompt_tokens}+{completion_tokens}={total_tokens}"


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
        self._extra_body = get_platform_settings(self.api_url, self.model_name, False)

    def _log_token_usage(self, usage):
        if usage:
            _log(f"Token: {usage.prompt_tokens} input + {usage.completion_tokens} output = {usage.total_tokens} used")

    def _rewrite_query(self, question):
        _log_section("查询重写")
        prompt = QUERY_REWRITE_PROMPT.format(question=question)

        # 尝试两次：第一次带 extra_body，第二次去掉 reasoning 参数
        extra_body_list = [self._extra_body]
        if self._extra_body.get("reasoning"):
            extra_body_list.append({k: v for k, v in self._extra_body.items() if k != "reasoning"})

        for attempt, extra_body in enumerate(extra_body_list):
            raw = None
            try:
                resp = self.llm.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=10240,
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
                    _log_warn(f"查询重写失败（{e}），去掉 reasoning 参数重试...")
                    continue
                _log_warn(f"查询重写失败（已跳过）: {e}")
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
            results = data.get("results", [])
            if results:
                _log(f"    找到 {len(results)} 个标签", _C.GREEN)
            elif data.get("error"):
                _log_warn(f"    工具返回错误: {data['error']}")
            else:
                _log("    未找到标签", _C.WARNING)
        except Exception:
            pass

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
        except Exception:
            pass
        return mapping

    def _get_output_format_section(self):
        from prompt_agent.agent_prompts import _NEWBIE_OUTPUT_FORMAT, _ANIMA_OUTPUT_FORMAT
        if self.mode == "Anima":
            return _ANIMA_OUTPUT_FORMAT
        return _NEWBIE_OUTPUT_FORMAT

    def _fallback_normal(self, user_text, image):
        _log_warn("回退为普通模式（无工具调用）")
        from prompt_agent.agent_prompts import get_agent_system_prompt
        system_content, fu, fa = get_agent_system_prompt(self.mode, self.config)
        messages = [{"role": "system", "content": system_content}]
        if fu and fa:
            messages.append({"role": "user", "content": fu})
            messages.append({"role": "assistant", "content": fa})
        messages.append({"role": "user", "content": "<user_message>\n" + user_text + "\n</user_message>"})
        try:
            resp = self.llm.chat.completions.create(
                model=self.model_name, messages=messages,
                temperature=0.7, max_tokens=10240, extra_body=self._extra_body,
            )
            content = resp.choices[0].message.content or ""
        except Exception as e:
            _log_error(f"回退模式 LLM 调用失败: {e}")
            raise
        _log_section("输出解析")
        xml_out, text_out = self._parse_output(content)
        return xml_out, text_out, content

    # ── Low effort 子步骤（从 _run_low_effort 拆分） ─────────────────

    def _batch_search_tags(self, dimensions):
        """Step 2: 对每个维度执行 search_tags，收集标签。
        Returns (all_tag_names, tag_cn_map).
        """
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
                    for t in results:
                        tag = t.get("tag", "")
                        if tag:
                            all_tag_names.append(tag)
                        cn = (t.get("cn_name") or "").strip()
                        if tag and cn:
                            tag_cn_map[tag] = cn
                else:
                    _log("    未找到标签", _C.WARNING)
            except Exception:
                pass
        _log(f"共收集 {len(all_tag_names)} 个标签")
        return all_tag_names, tag_cn_map

    def _explore_related_tags(self, all_tag_names, user_text):
        """Step 3: LLM 选择标签调用 get_related_tags 进行关联探索。
        Returns 更新后的 all_tag_names 列表。
        """
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
            resp = self.llm.chat.completions.create(
                model=self.model_name, messages=step3_messages,
                tools=tools_related, tool_choice="auto",
                temperature=0.7, max_tokens=500,
                extra_body=self._extra_body,
            )
            msg = resp.choices[0].message
            if resp.usage:
                self._log_token_usage(resp.usage)

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
                    self._log_tool_call(name, args)
                    result = execute_get_related_tags(
                        tags=args.get("tags", []),
                        limit=int(args.get("limit", 30)),
                        show_nsfw=bool(args.get("show_nsfw", True)),
                        include_wiki=bool(args.get("include_wiki", False)),
                    )
                    self._log_tool_result(name, result)
                    try:
                        related_data = json.loads(result)
                        for t in related_data.get("results", []):
                            tag = t.get("tag", "")
                            if tag:
                                all_tag_names.append(tag)
                    except Exception:
                        pass
        except Exception as e:
            _log_warn(f"Step 3 LLM 调用失败（已跳过关联探索）: {e}")

        _log(f"最终标签集合: {len(all_tag_names)} 个")
        return all_tag_names

    def _assemble_low_output(self, all_tag_names, tag_cn_map, user_text, user_tags, image):
        """Step 4: 整合标签，LLM 组装最终 prompt 并解析。
        Returns (xml_out, text_out, content)。
        """
        _log_section("组装最终 prompt")
        from prompt_agent.agent_prompts import get_agent_system_prompt
        output_format = LOW_ASSEMBLY_PROMPT.format(
            output_format_section=self._get_output_format_section(),
        )
        _, fewshot_user, fewshot_assistant = get_agent_system_prompt(self.mode, self.config)

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
            resp = self.llm.chat.completions.create(
                model=self.model_name, messages=assembly_messages,
                temperature=0.7, max_tokens=10240, extra_body=self._extra_body,
            )
            content = resp.choices[0].message.content or ""
            if resp.usage:
                self._log_token_usage(resp.usage)
        except Exception as e:
            _log_error(f"组装阶段 LLM 调用失败: {e}")
            raise

        _log_section("输出解析")
        xml_out, text_out = self._parse_output(content)

        _log_banner("Low effort 完成")
        return xml_out, text_out, content

    # ── Low effort 主流程 ───────────────────────────────────────────

    def _run_low_effort(self, user_text, image=None):
        """Low effort 流水线模式：重写 → 搜索 → 关联 → 组装。"""
        _log_banner("Low effort 流水线模式已启用")
        _log(f"模式: {self.mode} | Effort: Low | MCP: HF (主) / MS (备)")

        pbar = comfy.utils.ProgressBar(4, node_id=self.unique_id) if _COMFY_AVAILABLE else None

        def _tick(step):
            if _COMFY_AVAILABLE:
                comfy.model_management.throw_exception_if_processing_interrupted()
            if pbar:
                pbar.update_absolute(step)

        # Step 1: 查询重写 + 确定性抽取已提供标签（不依赖重写 LLM 的 [已有] 识别）
        user_tags, dimensions = self._rewrite_query(user_text)
        if not dimensions:
            dimensions = [user_text]
            _log("查询重写未返回结果，使用原始输入")
        provided_list, _ = self._collect_provided_tags(user_text, user_tags)
        user_tags = ", ".join(provided_list)
        if provided_list:
            _log(f"确定性抽取到用户已提供标签 {len(provided_list)} 个，将禁止检索")
        _tick(1)

        # Step 2: 批量搜索标签
        all_tag_names, tag_cn_map = self._batch_search_tags(dimensions)
        if not all_tag_names:
            _log_warn("所有维度均未搜索到标签，回退为普通模式")
            return self._fallback_normal(user_text, image)
        _tick(2)

        # Step 3: 标签关联探索
        all_tag_names = self._explore_related_tags(all_tag_names, user_text)
        _tick(3)

        # Step 4: 组装输出
        result = self._assemble_low_output(all_tag_names, tag_cn_map, user_text, user_tags, image)
        _tick(4)
        return result

    def _force_final_output(self, messages):
        """收尾：要求模型基于已收集标签直接输出，禁止再调工具。

        返回 (content, total_tokens)。复用于两种收尾场景：
        max_rounds 耗尽、以及信息增量停滞提前结束。
        """
        if _COMFY_AVAILABLE:
            comfy.model_management.throw_exception_if_processing_interrupted()
        messages.append({
            "role": "user",
            "content": "请根据已收集到的标签信息直接输出最终 prompt，禁止再调用任何工具。",
        })
        try:
            resp = self.llm.chat.completions.create(
                model=self.model_name,
                messages=_sanitize_messages_for_gemini(messages),
                temperature=0.7, max_tokens=10240, extra_body=self._extra_body,
            )
            content = resp.choices[0].message.content or ""
            forced_tokens = resp.usage.total_tokens if resp.usage else 0
            if resp.usage:
                self._log_token_usage(resp.usage)
        except Exception as e:
            _log_error(f"强制输出 LLM 调用失败: {e}")
            raise
        return content, forced_tokens

    def run(self, user_text, image=None, force_full_run=False):
        # ── 基线判定（所有 effort 通用）：复用 / 续写 / 冷跑 ──
        baseline = get_baseline_store().get(self.unique_id)
        if force_full_run:
            _log("Force full Agent run enabled: ignoring incremental baseline for this run.")
            decision, edit = ("cold", None)
        else:
            decision, edit = self._decide_baseline(baseline, user_text, image)
        if decision == "reuse":
            return self._parse_output(baseline["output"])

        # Low effort：流水线冷跑 / 增量修订续写
        if self.effort == "Low":
            if decision == "continue":
                xml_out, text_out, content = self._run_low_continuation(user_text, baseline, edit)
            else:
                xml_out, text_out, content = self._run_low_effort(user_text, image)
            self._store_baseline(user_text, content, image,
                                 baseline.get("format_spec") if baseline else None)
            return xml_out, text_out

        # Agent 模式：续写 / 冷跑
        _log_banner("Agent 模式已启用，开始处理用户输入...")
        _log(f"模式: {self.mode} | Effort: {self.effort} | MCP: HF (主) / MS (备)")
        if decision == "continue":
            build = self._build_continuation(baseline, edit, user_text)
        else:
            build = self._build_cold_run(user_text, image)
        messages, max_rounds, provided_norm = build

        content, rounds, total_tokens, captured_spec = self._run_agent_loop(
            messages, max_rounds, provided_norm,
        )

        _log_section("输出解析")
        xml_out, text_out = self._parse_output(content)

        # 压平存档：本次结果成为下次 diff 的基线（每节点只存上一次）。
        # 格式规范：本轮抓到的优先，否则沿用上一轮基线的（跨续写链保留，不重复调 MCP）。
        fmt_spec = captured_spec or (baseline.get("format_spec") if baseline else None)
        self._store_baseline(user_text, content, image, fmt_spec)

        _log_banner(f"Agent 完成 | 总轮次: {rounds + 1} | 总 Token: {total_tokens}")
        return xml_out, text_out

    def _decide_baseline(self, baseline, user_text, image):
        """基线判定（所有 effort 通用）。返回 (decision, edit)：
        decision ∈ {"reuse", "continue", "cold"}；continue 时附带 edit。
        """
        if not (baseline and image is None
                and baseline.get("mode") == self.mode
                and not baseline.get("has_image")
                and baseline.get("output")):
            return ("cold", None)
        if normalize_prompt(user_text) == baseline.get("norm_input"):
            _log_ok("输入与上次完全一致，直接复用上次结果（零调用）")
            return ("reuse", None)
        edit = compute_edit(baseline["raw_input"], user_text)
        _log(f"与上次 diff：变更块={edit['blocks']}，相似度={edit['ratio']:.2f}")
        if edit["blocks"] == 0:
            # 仅标点/空白变化，无实义 token 改动 → 标签集合不变，直接复用
            _log_ok("仅标点/空白变化，无实义改动，直接复用上次结果（零调用）")
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
        """Low 增量修订：对变更词做一次 full_scene 搜索（单轮、无关联探索），
        LLM 在上一轮输出基础上单次修订。Returns (xml_out, text_out, content)。
        """
        _log_banner("Low 增量修订：在上一轮结果基础上修订")
        _log(f"改动：{edit['instruction']}")

        # 仅对新增/替换后的目标词做全场景搜索（full_scene，无 get_related_tags 关联）
        candidate_tags = []
        for term in edit.get("new_terms", []):
            result = execute_search_tags(query=term, search_mode="full_scene", show_nsfw=True)
            names = self._extract_tag_list(result)
            if names:
                candidate_tags.extend(names)
                _log(f"  > 搜索变更词：{term} → {len(names)} 个候选", _C.GREEN)
            else:
                _log(f"  > 搜索变更词：{term} → 未找到", _C.WARNING)
        seen = set()
        candidate_tags = [t for t in candidate_tags if not (t in seen or seen.add(t))]

        if self.mode == "Anima":
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
            output_format_section=self._get_output_format_section(),
        )
        messages = [
            {"role": "system", "content": output_format},
            {"role": "user", "content": "<user_message>\n" + baseline["raw_input"] + "\n</user_message>"},
            {"role": "assistant", "content": baseline["output"]},
            {"role": "user", "content": revise_directive},
        ]
        try:
            resp = self.llm.chat.completions.create(
                model=self.model_name, messages=messages,
                temperature=0.7, max_tokens=10240, extra_body=self._extra_body,
            )
            content = resp.choices[0].message.content or ""
            if resp.usage:
                self._log_token_usage(resp.usage)
        except Exception as e:
            _log_error(f"Low 修订 LLM 调用失败: {e}")
            raise

        _log_section("输出解析")
        xml_out, text_out = self._parse_output(content)
        _log_banner("Low 增量修订完成")
        return xml_out, text_out, content

    def _build_cold_run(self, user_text, image):
        """冷跑路径：构造完整初始消息（查询重写、已提供标签、格式指令、图片）。
        Returns (messages, max_rounds, provided_norm)。
        """
        max_rounds = self._effort_cfg["max_rounds"]

        rewrite_queries = []
        user_tags = ""
        if self._effort_cfg.get("rewrite", True) and len(user_text) > 10:
            user_tags, rewrite_queries = self._rewrite_query(user_text)

        system_content, fewshot_user, fewshot_assistant = get_agent_system_prompt(
            self.mode, self.config, max_rounds=max_rounds,
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
            if not rewrite_queries:
                # 所有输入都是用户已有标签，无额外维度需要搜索 → 跳过工具调用
                user_content += (
                    "\n\n上述标签已覆盖全部要素，无需调用任何工具。"
                    "直接将上述标签标准化（空格→下划线、括号转义等）后按格式要求输出即可。"
                )
            else:
                user_content += (
                    "\n\n上述标签已覆盖部分维度（如人设、角色、服装等），直接信任、禁止检索；"
                    "你**只需要**检索下方【待搜索维度】中的内容。"
                )
            _log(f"已注入禁止检索的已提供标签: {len(provided_list)} 个")
        if rewrite_queries:
            user_content += "\n\n【待搜索维度（仅检索以下内容，禁止检索已覆盖概念）】\n" + "\n".join("- " + q for q in rewrite_queries)

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

    def _store_baseline(self, user_text, content, image, format_spec=None):
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
                "format_spec": format_spec,
            })
        except Exception:
            pass  # 基线写入失败不影响主流程

    def _run_agent_loop(self, messages, max_rounds, provided_norm):
        """执行 Agent 工具循环。Returns (content, rounds, total_tokens)。"""
        pbar = comfy.utils.ProgressBar(max_rounds, node_id=self.unique_id) if _COMFY_AVAILABLE else None

        rounds = 0
        total_tokens = 0
        duplicate_tracker = {}
        tag_cn_map: dict[str, str] = {}
        seen_tags: set[str] = set()      # 累计已见过的标签，用于信息增量统计
        stagnant_rounds = 0              # 连续低信息增量轮次计数
        stagnated = False                # 因停滞而提前结束的标志
        content = ""
        captured_format = None           # 本轮抓到的 get_*_format 规范，随基线保留供续写复用

        while rounds < max_rounds:
            if _COMFY_AVAILABLE:
                comfy.model_management.throw_exception_if_processing_interrupted()
            _log_round_header(rounds + 1)
            _tools = get_tools()
            _log(f"LLM 请求: {len(_tools)} tools available, {len(messages)} messages")

            _messages = _sanitize_messages_for_gemini(messages)
            try:
                resp = self.llm.chat.completions.create(
                    model=self.model_name, messages=_messages, tools=_tools,
                    tool_choice="auto", temperature=0.7, max_tokens=10240,
                    extra_body=self._extra_body,
                )
            except Exception as e:
                _log_error(f"LLM API 调用失败: {e}")
                _dump_request_debug(_messages, _tools)
                raise

            msg = resp.choices[0].message
            content = msg.content or ""
            tool_calls = _serialize_tool_calls(msg.tool_calls)
            finish_reason = resp.choices[0].finish_reason

            if resp.usage:
                total_tokens += resp.usage.total_tokens
                self._log_token_usage(resp.usage)

            if finish_reason == "tool_calls" and tool_calls:
                if content and content.strip():
                    _log(f"LLM 工具调用附带 content: {content[:200]}{'...' if len(content) > 200 else ''}", _C.WARNING)
                # 预先解析参数并过滤重复调用
                parsed = []
                skipped = []
                for tc in tool_calls:
                    name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}
                    # 守卫：search_tags 查询命中用户已提供标签 → 不执行，回灌"已提供"提示
                    if name == "search_tags":
                        qn = utils.normalize_tag(str(args.get("query", "")))
                        if qn and qn in provided_norm:
                            _log_warn(f"搜索查询「{args.get('query', '')}」命中用户已提供标签，跳过执行")
                            skipped.append((tc, json.dumps(
                                {"skipped": "user_provided",
                                 "note": "该标签用户已提供，禁止重复搜索，直接使用用户提供的版本即可。"},
                                ensure_ascii=False)))
                            continue
                    call_key = name + ":" + json.dumps(args, sort_keys=True)
                    count = duplicate_tracker.get(call_key, 0) + 1
                    duplicate_tracker[call_key] = count
                    if count > 3:
                        _log_warn(f"检测到重复调用 {name}（第{count}次），跳过执行")
                        skipped.append((tc, json.dumps({"skipped": "duplicate"}, ensure_ascii=False)))
                        continue
                    parsed.append((tc, name, args))
                if not parsed:
                    # 所有 tool_calls 均为重复：仍需添加 assistant+tool 消息，
                    # 否则上一轮遗留的 tool_calls 无对应 response 会导致 API 400
                    messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                    for tc in tool_calls:
                        messages.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": json.dumps({"skipped": "duplicate"}, ensure_ascii=False)})
                    _log_error("所有 tool_calls 均为重复调用，强制退出循环")
                    break
                # 全量 tool_calls 放入 assistant 消息，确保与后续 tool response 一一对应
                messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
                # 并行执行所有工具调用（HTTP I/O，无 GIL 竞争）
                try:
                    with ThreadPoolExecutor(max_workers=min(len(parsed), 8)) as pool:
                        futures = [
                            pool.submit(self._execute_tool, name, args)
                            for _, name, args in parsed
                        ]
                        results = []
                        for f in futures:
                            try:
                                results.append(f.result(timeout=60))
                            except Exception as e:
                                _log_error(f"工具调用超时或异常: {e}")
                                results.append(json.dumps(
                                    {"found": False, "error": str(e)},
                                    ensure_ascii=False,
                                ))
                except Exception as e:
                    _log_error(f"并行工具调用失败: {e}")
                    # 为所有未响应的 tool_calls 添加错误 response，保证一一对应
                    for tc, _, _ in parsed:
                        messages.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": json.dumps({"error": str(e)}, ensure_ascii=False)})
                    for tc, skip_content in skipped:
                        messages.append({"role": "tool", "tool_call_id": tc["id"],
                                         "content": skip_content})
                    break
                # 非重复调用：写入实际结果，并统计本轮信息增量
                round_returned: set[str] = set()  # 本轮所有搜索/关联返回的标签
                for (tc, name, args), result in zip(parsed, results):
                    self._log_tool_call(name, args)
                    self._log_tool_result(name, result)
                    tag_cn_map.update(self._collect_cn_from_result(result))
                    if name in ("get_anima_format", "get_newbie_format"):
                        captured_format = result  # 保留格式规范供续写复用
                    if name in ("search_tags", "get_related_tags"):
                        returned_list = self._extract_tag_list(result)
                        returned = set(returned_list)
                        if returned:
                            # 已覆盖概念重搜检测：结果前 K 名（按匹配强度降序）命中用户
                            # 已提供标签 → 说明在搜用户已覆盖的概念（即使 query 是中文，
                            # 也能通过返回的英文强匹配标签命中）。弱共现排在后面不会误报。
                            if provided_norm:
                                top_hit = [
                                    t for t in returned_list[:_PROVIDED_TOPK]
                                    if utils.normalize_tag(t) in provided_norm
                                ]
                                if top_hit:
                                    result = result + (
                                        f"\n\n[系统提示] 本次结果中排名最靠前的标签 "
                                        f"{', '.join(top_hit)} 属于用户已提供标签，"
                                        f"说明你正在搜索用户已覆盖的概念。用户已提供的标签禁止重复检索，"
                                        f"请勿再搜索该概念，转向尚未覆盖的维度或直接输出。"
                                    )
                            # 新标签 = 既不在历史已见、也不在本轮更早调用里
                            new_in_call = returned - seen_tags - round_returned
                            round_returned |= returned
                            # 新增占比过低：在该 tool 结果末尾回灌停滞信号给模型
                            if len(new_in_call) / len(returned) < _LOW_NOVELTY_RATIO:
                                result = result + (
                                    f"\n\n[系统提示] 本次返回 {len(returned)} 个标签，"
                                    f"其中仅 {len(new_in_call)} 个为新标签，其余均已在先前轮次出现。"
                                    f"该主题/维度已充分覆盖，请勿换措辞重复搜索同一主题，"
                                    f"转向尚未覆盖的维度，或直接输出最终结果。"
                                )
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                # 被跳过的调用（重复 / 命中已提供标签）：写入占位 response，保证一一对应
                for tc, skip_content in skipped:
                    messages.append({"role": "tool", "tool_call_id": tc["id"],
                                     "content": skip_content})

                # 信息增量停滞检测：连续多轮搜索几乎无新标签 → 提前收尾
                round_new = len(round_returned - seen_tags)
                round_had_search = len(round_returned) > 0
                seen_tags |= round_returned
                if round_had_search and round_new < _STAGNATION_MIN_NEW:
                    stagnant_rounds += 1
                    _log_warn(
                        f"低信息增量轮次（本轮新增 {round_new} 个标签），"
                        f"停滞计数 {stagnant_rounds}/{_STAGNATION_LIMIT}"
                    )
                else:
                    stagnant_rounds = 0

                rounds += 1
                if pbar:
                    pbar.update_absolute(rounds)

                if stagnant_rounds >= _STAGNATION_LIMIT:
                    _log_warn("连续低信息增量，提前结束探索，进入收尾输出")
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

        # 因信息增量停滞而提前跳出：同样强制收尾输出
        if stagnated:
            content, forced_tokens = self._force_final_output(messages)
            total_tokens += forced_tokens

        return content, rounds, total_tokens, captured_format

    def _parse_output(self, content):
        if self.mode == "Anima":
            return self._parse_anima_output(content)
        return self._parse_newbie_output(content)

    def _parse_anima_output(self, content):
        _log("Anima 模式: 按 Markdown 标题分割输出")
        # 标题统一用 #{2,} 容忍层级差异（模型偶尔写 ### 而非 ##）。
        # Prompt 段：## Prompt 到「下一个标题行」或结尾——用通用标题边界，避免第二段标题
        # 被改写（如 ### 中文解释 / ## 改动说明）时 Prompt 段把它整段吸入。
        prompt_match = re.search(r'#{2,}\s*Prompt\s*\n(.*?)(?=\n#{2,}|\Z)', content, re.DOTALL)
        # 解释段：优先「中文解释」标题；缺失时回退为「第二个标题之后的正文」，
        # 兼容续写偶尔把标题写成「改动说明」等的情况。
        explanation_match = re.search(r'#{2,}\s*中文解释\s*\n(.*)', content, re.DOTALL)
        expl_text = explanation_match.group(1) if explanation_match else None
        if expl_text is None:
            headings = list(re.finditer(r'(?m)^#{2,}[^\n]*\n', content))
            if len(headings) >= 2:  # headings[0]=Prompt 标题, headings[1]=解释段标题
                expl_text = content[headings[1].end():]
                _log_warn("第二个标题非「中文解释」，已按位置回退提取解释段")

        if prompt_match and expl_text is not None:
            xml_out = utils.strip_code_fences(prompt_match.group(1))
            text_out = utils.strip_code_fences(expl_text)
            _log_ok(f"成功按标题分割: Prompt={len(xml_out)} chars, 解释={len(text_out)} chars")
        elif prompt_match:
            xml_out = utils.strip_code_fences(prompt_match.group(1))
            text_out = ""
            _log_warn("未找到解释段标题，仅提取 Prompt 部分")
        else:
            _log_warn("未找到 ## Prompt 标题，回退到按行分离中英文")
            xml_out, text_out = _split_by_language(content)
            xml_out = utils.strip_code_fences(xml_out)
            if not xml_out:
                _log_warn("Anima 模式未检测到英文内容，返回完整响应")
                xml_out = content
        return xml_out, text_out

    def _parse_newbie_output(self, content):
        _log("NewBie 模式: 提取 XML 代码块")
        xml_content, text_content = utils.parse_newbie_content(content)
        # 补充 warning 日志（utils 不处理日志）
        if not re.search(r"", content, re.DOTALL):
            if "<img>" in content and "</img>" in content:
                pass  # 走 <img> 标签提取路径
            elif "<img>" in content:
                _log_warn("回复可能被截断")
            else:
                _log_warn("未检测到 <img> 标签")

        gemma_prompt = self.config.get(
            "gemma_prompt",
            "You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>\n",
        )
        xml_content = _clean_prompt(xml_content, gemma_prompt)
        return xml_content, text_content
