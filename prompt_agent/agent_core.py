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
    LOW_ASSEMBLY_PROMPT,
    QUERY_REWRITE_PROMPT,
)
from prompt_agent.tools import (
    get_tools,
    execute_search_tags,
    execute_get_related_tags,
)
from prompt_agent.cache import (
    get_cache, extract_tags_from_output,
    format_cached_tags, cached_tags_plain, build_tag_entry,
)
from prompt_agent import utils

MAX_ROUNDS = 10


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
# Low   = 流水线模式，不走 Agent 循环，无 max_rounds
# Medium = Agent 循环，top_k=5 平衡召回质量与轮次收敛速度
# High   = Agent 循环，top_k=10 宽召回，更多轮次深入探索
_EFFORT_CONFIG = {
    "Low":    {"search_limit": 80, "related_limit": 50, "search_top_k": 8},
    "Medium": {"search_limit": 60, "related_limit": 30, "max_rounds": 8,  "search_top_k": 5},
    "High":   {"search_limit": 80, "related_limit": 50, "max_rounds": 10, "search_top_k": 10},
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


class PromptAgent:
    def __init__(self, api_key, api_url, model_name, mode, thinking, config, effort="Medium"):
        self.api_key = api_key
        self.api_url = api_url
        self.model_name = model_name
        self.mode = mode
        self.thinking = thinking
        self.config = config
        self.effort = effort
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
        try:
            resp = self.llm.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                extra_body=self._extra_body,
            )
            raw = resp.choices[0].message.content.strip()
            raw = raw.strip("```json").strip("```").strip()
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
            _log_warn(f"查询重写失败（已跳过）: {e}")
        return "", []

    def _execute_tool(self, name, args):
        if name == "search_tags":
            args["limit"] = min(int(args.get("limit", 80)), self._effort_cfg["search_limit"])
            top_k_cap = self._effort_cfg.get("search_top_k")
            if top_k_cap is not None:
                args["top_k"] = min(int(args.get("top_k", 5)), top_k_cap)
            elif not args.get("use_segmentation", True):
                args["top_k"] = min(int(args.get("top_k", 20)), args["limit"])
            return execute_search_tags(
                query=args.get("query", ""),
                use_segmentation=bool(args.get("use_segmentation", True)),
                top_k=int(args.get("top_k", 5)),
                limit=int(args.get("limit", 80)),
                popularity_weight=float(args.get("popularity_weight", 0.15)),
                show_nsfw=bool(args.get("show_nsfw", True)),
                include_wiki=bool(args.get("include_wiki", False)),
                category=str(args.get("category", "all")),
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
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)

    def _log_tool_call(self, name, args):
        if name == "search_tags":
            query_str = args.get("query", "")
            params = f"top_k={args.get('top_k', 5)}, limit={args.get('limit', 80)}, segmentation={args.get('use_segmentation', True)}"
            _log(f"  > 搜索标签：{query_str}", _C.GREEN)
            _log(f"    [search_tags] {params}")
        elif name == "get_related_tags":
            tags = args.get("tags", [])
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except Exception:
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
            _log(f"  > 关联推荐：{', '.join(tags[:5])}", _C.GREEN)
            _log(f"    [get_related_tags] tags={len(tags)}, limit={args.get('limit', 30)}")
        else:
            _log(f"  > 调用工具：{name}", _C.GREEN)

    def _log_tool_result(self, name, result_str):
        try:
            data = json.loads(result_str)
            if data.get("found"):
                _log(f"    找到 {len(data.get('tags', []))} 个标签", _C.GREEN)
            elif data.get("error"):
                _log_warn(f"    工具返回错误: {data['error']}")
            else:
                _log("    未找到标签", _C.WARNING)
        except Exception:
            pass

    @staticmethod
    def _collect_cn_from_result(result_str: str) -> dict[str, str]:
        """从工具返回的 JSON 中提取 {tag: cn_name} 映射。"""
        mapping = {}
        try:
            data = json.loads(result_str)
            if data.get("found"):
                for t in data.get("tags", []):
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

    def _get_today(self):
        from datetime import date
        return date.today().strftime("%Y年%m月%d日")

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
                temperature=0.7, max_tokens=2048, extra_body=self._extra_body,
            )
            content = resp.choices[0].message.content or ""
        except Exception as e:
            _log_error(f"回退模式 LLM 调用失败: {e}")
            raise
        _log_section("输出解析")
        return self._parse_output(content)

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
                query=dim, use_segmentation=True, top_k=5, limit=80, show_nsfw=True,
            )
            try:
                data = json.loads(result_str)
                if data.get("found"):
                    tags = data.get("tags", [])
                    _log(f"    找到 {len(tags)} 个标签", _C.GREEN)
                    for t in tags:
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
                        if related_data.get("found"):
                            for t in related_data.get("tags", []):
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
        """Step 4: 整合标签，LLM 组装最终 prompt，解析并缓存结果。
        Returns (xml_out, text_out).
        """
        _log_section("组装最终 prompt")
        from prompt_agent.agent_prompts import get_agent_system_prompt
        output_format = LOW_ASSEMBLY_PROMPT.format(
            output_format_section=self._get_output_format_section(),
            today=self._get_today(),
        )
        _, fewshot_user, fewshot_assistant = get_agent_system_prompt(self.mode, self.config)

        assembly_messages = [{"role": "system", "content": output_format}]
        if fewshot_user and fewshot_assistant:
            assembly_messages.append({"role": "user", "content": fewshot_user})
            assembly_messages.append({"role": "assistant", "content": fewshot_assistant})

        # 缓存注入
        cached = get_cache().lookup(user_text)
        if cached:
            cached_tags = cached_tags_plain(cached["tags"])
            all_tag_names = cached_tags + all_tag_names
            for t in cached["tags"]:
                if isinstance(t, dict) and t.get("c"):
                    if t["t"] not in tag_cn_map:
                        tag_cn_map[t["t"]] = t["c"]
            _log(f"缓存命中: 注入 {len(cached_tags)} 个标签")

        tags_str = ", ".join(all_tag_names)
        user_content = "<user_message>\n" + user_text + "\n</user_message>"
        if user_tags:
            user_content += "\n\n【用户已提供标签（直接信任，禁止搜索）】\n" + user_tags
            user_content += "\n以上标签已由用户提供，禁止调用 search_tags 搜索这些标签或其变体。"
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
                temperature=0.7, max_tokens=2048, extra_body=self._extra_body,
            )
            content = resp.choices[0].message.content or ""
            if resp.usage:
                self._log_token_usage(resp.usage)
        except Exception as e:
            _log_error(f"组装阶段 LLM 调用失败: {e}")
            raise

        _log_section("输出解析")
        xml_out, text_out = self._parse_output(content)

        # 存入缓存
        try:
            plain_tags = extract_tags_from_output(xml_out, self.mode)
            if plain_tags:
                tags_with_cn = [
                    build_tag_entry(t, tag_cn_map.get(t, ""))
                    for t in plain_tags
                ]
                get_cache().store(user_text, tags_with_cn, self.mode)
                _log(f"已缓存 {len(tags_with_cn)} 个标签（含 {len(tag_cn_map)} 个中文参考）")
        except Exception:
            pass  # 缓存写入失败不影响主流程

        _log_banner("Low effort 完成")
        return xml_out, text_out

    # ── Low effort 主流程 ───────────────────────────────────────────

    def _run_low_effort(self, user_text, image=None):
        """Low effort 流水线模式：重写 → 搜索 → 关联 → 组装。"""
        _log_banner("Low effort 流水线模式已启用")
        _log(f"模式: {self.mode} | Effort: Low | MCP: HF (主) / MS (备)")

        # Step 1: 查询重写
        user_tags, dimensions = self._rewrite_query(user_text)
        if not dimensions:
            dimensions = [user_text]
            _log("查询重写未返回结果，使用原始输入")

        # Step 2: 批量搜索标签
        all_tag_names, tag_cn_map = self._batch_search_tags(dimensions)
        if not all_tag_names:
            _log_warn("所有维度均未搜索到标签，回退为普通模式")
            return self._fallback_normal(user_text, image)

        # Step 3: 标签关联探索
        all_tag_names = self._explore_related_tags(all_tag_names, user_text)

        # Step 4: 组装输出
        return self._assemble_low_output(all_tag_names, tag_cn_map, user_text, user_tags, image)

    def run(self, user_text, image=None):
        if self.effort == "Low":
            return self._run_low_effort(user_text, image)

        _log_banner("Agent 模式已启用，开始处理用户输入...")
        _log(f"模式: {self.mode} | Effort: {self.effort} | MCP: HF (主) / MS (备)")

        rewrite_queries = []
        user_tags = ""
        if self._effort_cfg.get("rewrite", True) and len(user_text) > 10:
            user_tags, rewrite_queries = self._rewrite_query(user_text)

        system_content, fewshot_user, fewshot_assistant = get_agent_system_prompt(self.mode, self.config)
        messages = [{"role": "system", "content": system_content}]

        if fewshot_user and fewshot_assistant:
            messages.append({"role": "user", "content": fewshot_user})
            messages.append({"role": "assistant", "content": fewshot_assistant})
            _log("已注入 few-shot 示例")

        user_content = "<user_message>\n" + user_text + "\n</user_message>"

        # 用户已提供标签（来自查询重写）
        if user_tags:
            user_content += "\n\n【用户已提供标签（直接信任，禁止搜索）】\n" + user_tags
            if not rewrite_queries:
                # 所有输入都是用户已有标签，无额外维度需要搜索 → 跳过工具调用
                user_content += (
                    "\n\n用户输入已覆盖全部要素，你不需要调用任何工具。"
                    "禁止调用 search_tags 或 get_related_tags。"
                    "直接将上述标签进行标准化处理（空格→下划线、括号转义等），按 XML 格式整理输出即可。"
                )
            else:
                user_content += (
                    "\n\n搜索边界：上述已有标签已覆盖部分维度（如人设、角色、服装等）。"
                    "你**只需要**搜索以下待搜索维度中提及的内容，**禁止**重新检索已有标签已覆盖的概念。"
                )
            _log(f"检测到用户已提供标签: {len(user_tags.split(','))} 个")
        if rewrite_queries:
            user_content += "\n\n【待搜索维度（仅搜索以下内容，禁止搜索已有标签已覆盖的概念）】\n" + "\n".join("- " + q for q in rewrite_queries)


        # 缓存注入：从相似历史查询中获取的标签
        cached = get_cache().lookup(user_text)
        cached_plain = []
        if cached:
            cached_plain = cached_tags_plain(cached["tags"])
            cached_formatted = format_cached_tags(cached["tags"])
            user_content += (
                "\n\n【已缓存标签（来自相似查询，可直接使用，禁止重复查询）】\n"
                + cached_formatted + "\n"
                + "以下标签来自相似查询的最终结果，已经过大模型验证，确认存在且准确。禁止重复查询可被已缓存标签覆盖的内容。"
                + "标签后方【】内为中文参考，仅供你理解含义，不要将【】内容当作标签的一部分。"
            )
            _log(f"缓存命中: 注入 {len(cached['tags'])} 个标签")
        # user_content += "\n\n【务必调用工具搜索，以获得准确回答】"

        if image is not None:
            b64 = utils.tensor_to_base64(image)
            messages.append({"role": "user", "content": [
                {"type": "text", "text": user_content},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
            ]})
            _log("已附加图片输入（多模态模式）")
        else:
            messages.append({"role": "user", "content": user_content})

        rounds = 0
        total_tokens = 0
        duplicate_tracker = {}
        tag_cn_map: dict[str, str] = {}
        max_rounds = self._effort_cfg["max_rounds"]

        while rounds < max_rounds:
            _log_round_header(rounds + 1)
            _tools = get_tools()
            _log(f"LLM 请求: {len(_tools)} tools available")

            try:
                resp = self.llm.chat.completions.create(
                    model=self.model_name, messages=messages, tools=_tools,
                    tool_choice="auto", temperature=0.7, max_tokens=2048,
                    extra_body=self._extra_body,
                )
            except Exception as e:
                _log_error(f"LLM API 调用失败: {e}")
                raise

            msg = resp.choices[0].message
            content = msg.content or ""
            tool_calls = _serialize_tool_calls(msg.tool_calls)
            finish_reason = resp.choices[0].finish_reason

            if resp.usage:
                total_tokens += resp.usage.total_tokens
                self._log_token_usage(resp.usage)

            if finish_reason == "tool_calls" and tool_calls:
                # 预先解析参数并过滤重复调用
                parsed = []
                for tc in tool_calls:
                    name = tc["function"]["name"]
                    raw_args = tc["function"]["arguments"]
                    try:
                        args = json.loads(raw_args) if raw_args else {}
                    except json.JSONDecodeError:
                        args = {}
                    call_key = name + ":" + json.dumps(args, sort_keys=True)
                    count = duplicate_tracker.get(call_key, 0) + 1
                    duplicate_tracker[call_key] = count
                    if count > 3:
                        _log_warn(f"检测到重复调用 {name}（第{count}次），跳过")
                        continue
                    parsed.append((tc, name, args))
                if not parsed:
                    _log_error("所有 tool_calls 均为重复调用，强制退出循环")
                    break
                # 仅追加未重复的 tool_calls 到 assistant 消息
                filtered_calls = [p[0] for p in parsed]
                messages.append({"role": "assistant", "content": content, "tool_calls": filtered_calls})
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
                    break
                for (tc, name, args), result in zip(parsed, results):
                    self._log_tool_call(name, args)
                    self._log_tool_result(name, result)
                    tag_cn_map.update(self._collect_cn_from_result(result))
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": result})
                rounds += 1
                continue

            _log(f"LLM 输出最终回答 (finish_reason={finish_reason})")
            break
        else:
            _log_error(f"Agent 循环超过最大轮次 ({max_rounds})，强制输出")
            messages.append({"role": "user", "content": "请根据已收集到的标签信息直接输出最终 prompt，禁止再调用任何工具。"})
            try:
                resp = self.llm.chat.completions.create(
                    model=self.model_name, messages=messages, temperature=0.7,
                    max_tokens=2048, extra_body=self._extra_body,
                )
                content = resp.choices[0].message.content or ""
                if resp.usage:
                    total_tokens += resp.usage.total_tokens
                    self._log_token_usage(resp.usage)
            except Exception as e:
                _log_error(f"强制输出 LLM 调用失败: {e}")
                raise

        _log_section("输出解析")
        xml_out, text_out = self._parse_output(content)

        # 存入缓存（带 cn_name）
        try:
            plain_tags = extract_tags_from_output(xml_out, self.mode)
            if plain_tags:
                tags_with_cn = [
                    build_tag_entry(t, tag_cn_map.get(t, ""))
                    for t in plain_tags
                ]
                get_cache().store(user_text, tags_with_cn, self.mode)
                _log(f"已缓存 {len(tags_with_cn)} 个标签（含 {len(tag_cn_map)} 个中文参考）")
        except Exception:
            pass  # 缓存写入失败不影响主流程

        _log_banner(f"Agent 完成 | 总轮次: {rounds + 1} | 总 Token: {total_tokens}")
        return xml_out, text_out

    def _parse_output(self, content):
        if self.mode == "Anima":
            return self._parse_anima_output(content)
        return self._parse_newbie_output(content)

    def _parse_anima_output(self, content):
        _log("Anima 模式: 按 Markdown 标题分割输出")
        prompt_match = re.search(r'##\s*Prompt\s*\n(.*?)(?=##\s*中文解释|\Z)', content, re.DOTALL)
        explanation_match = re.search(r'##\s*中文解释\s*\n(.*)', content, re.DOTALL)

        if prompt_match and explanation_match:
            xml_out = prompt_match.group(1).strip()
            text_out = explanation_match.group(1).strip()
            _log_ok(f"成功按标题分割: Prompt={len(xml_out)} chars, 解释={len(text_out)} chars")
        elif prompt_match:
            xml_out = prompt_match.group(1).strip()
            text_out = ""
            _log_warn("未找到 ## 中文解释 标题，仅提取 Prompt 部分")
        else:
            _log_warn("未找到 ## Prompt 标题，回退到按行分离中英文")
            xml_out, text_out = _split_by_language(content)
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
