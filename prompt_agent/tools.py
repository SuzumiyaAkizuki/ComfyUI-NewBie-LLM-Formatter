"""
prompt_agent/tools.py
----------------------
search_tags / get_related_tags 工具实现，通过 MCP Streamable HTTP 协议
调用 DanbooruSearch MCP 服务。

MCP 服务地址：https://sakizuki-danboorusearch.hf.space/mcp/mcp
协议：Streamable HTTP（POST JSON-RPC，非 SSE）

依赖：
  pip install httpx

工具定义（TOOLS）在模块加载时通过 load_tools_from_mcp() 从 MCP 服务端动态拉取，
与服务端 tools/list 响应保持一致，无需本地维护描述文本。
拉取失败时回退到内置的 FALLBACK_TOOLS，保证服务可用性。

search_tags 使用 search_mode 预设策略（v2 API）：
  "full_scene"       — 完整场景→提示词
  "concept_explore"  — 模糊概念探索，宽召回
  "subject_describe" — 描述主体以匹配标签
  "precise_lookup"   — 精确查找/拼写纠错

HF Space 冷启动约 30~60 秒，_call_mcp 设置 timeout=90。
"""

from __future__ import annotations

import json
import sys
import threading
import time
import httpx

_MCP_URL_HF = "https://sakizuki-danboorusearch.hf.space/mcp/mcp"
_MCP_URL_MS = "https://sakizuki-danboorusearchonline.ms.show/mcp/mcp"
_TIMEOUT = 90

# 最近一次实际服务的 MCP 端点（仅供 get_active_endpoint / 健康展示）。
# 调用顺序固定 HF 优先、MS 兜底（见 _rpc），不再用它作粘性首选。
_active_url: str = _MCP_URL_HF

# 保护 _active_url 并发写入
_lock = threading.Lock()


def get_active_endpoint() -> str:
    """返回当前活跃的 MCP 端点标识 ('hf' / 'ms')。"""
    return "ms" if _active_url == _MCP_URL_MS else "hf"

# 回退用的工具定义，仅在 tools/list 拉取失败时使用
_FALLBACK_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_tags",
            "description": (
                "Search Danbooru tags using natural language and return a ready-to-use prompt. "
                "Chinese recommended. Use search_mode to pick the preset strategy that matches your intent: "
                "'full_scene' for complete scene → prompt (e.g. descriptions of a character in an environment), "
                "'concept_explore' for vague concept exploration with broad recall (e.g. 'cyberpunk clothing', 'bunny ears'), "
                "'subject_describe' for describing a specific subject to find matching tags (e.g. 'blue-haired pilot from EVA'), "
                "'precise_lookup' for precise lookup or spell fix (e.g. 'serafuku', 'thighhigh'). "
                "Use category to filter results by tag type (all/general/copyright/character)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query":       {"type": "string", "description": "Natural language description (Chinese recommended)."},
                    "search_mode": {"type": "string", "description": "Preset strategy: 'full_scene' (scene→prompt), 'concept_explore' (broad recall), 'subject_describe' (subject matching), 'precise_lookup' (spell fix). Default 'full_scene'."},
                    "category":    {"type": "string", "description": "Filter results to a tag category. 'all' (default), 'general' (visual attributes/clothing/pose), 'copyright' (anime/game titles), 'character' (named characters)."},
                    "show_nsfw":   {"type": "boolean", "description": "Include NSFW tags (default True)."},
                    "include_wiki":{"type": "boolean", "description": "Append wiki description per tag (default False). Use for disambiguation or explaining tags."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_related_tags",
            "description": (
                "Co-occurrence-based tag recommendations via NPMI scoring. Call after search_tags "
                "to discover complementary tags (accessories, character features, scene atmosphere). "
                "Multi-tag input returns intersection recommendations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tags":         {"type": "array", "items": {"type": "string"}, "description": "Danbooru tag names to base recommendations on."},
                    "limit":        {"type": "integer", "description": "Max recommendations returned."},
                    "show_nsfw":    {"type": "boolean", "description": "Include NSFW tags."},
                    "include_wiki": {"type": "boolean", "description": "Append wiki description per tag (default False). Use for disambiguation or explaining tags."},
                },
                "required": ["tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_artist_recommendations",
            "description": (
                "Recommend artists who are skilled at drawing the given tags, based on NPMI co-occurrence data. "
                "Given a list of Danbooru tags (e.g. character names, clothing, styles), this tool returns "
                "artists whose works frequently co-occur with those tags on Danbooru, ranked by aggregated NPMI score."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tags":      {"type": "array", "items": {"type": "string"}, "description": "Danbooru tag names to base artist recommendations on."},
                    "limit":     {"type": "integer", "description": "Max artists returned. Default 30."},
                    "min_cooc":  {"type": "integer", "description": "Minimum co-occurrence count per (tag, artist) pair. Default 3."},
                    "show_nsfw": {"type": "boolean", "description": "Include NSFW artist data. Default True."},
                },
                "required": ["tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_anima_format",
            "description": "返回 Anima 文生图模型的 Hybrid 混合提示词格式规范。当用户提到 Anima 提示词/Anima 格式/Anima Prompt/Anima 模型等关键词时，应在搜索标签完成、最终输出前调用此工具，以获取完整的提示词组装规范。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_newbie_format",
            "description": "返回 NewBie 文生图模型的 XML 格式提示词规范。当用户提到 NewBie 提示词/NewBie 格式/NewBie Prompt/NewBie 模型等关键词时，应在搜索标签完成、最终输出前调用此工具，以获取完整的 XML 格式组装规范。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


_HEADERS_BASE = {
    "Content-Type": "application/json",
    "Accept":       "application/json, text/event-stream",
}

def _new_session_id(client: httpx.Client, url: str) -> str:
    """在给定 client 上发送 initialize 握手，返回服务器分配的 session id。

    **关键**：握手与随后的 tools/call 复用同一个 client（同一持久连接），
    使两步落在**同一 HF 副本**。否则 HF 多副本部署下，握手与调用走不同连接、
    被 LB 路由到不同副本，session id 跨副本失配导致请求失败、误判 HF 不可用。
    """
    payload = {
        "jsonrpc": "2.0",
        "id":      0,
        "method":  "initialize",
        "params":  {
            "protocolVersion": "2024-11-05",
            "clientInfo":      {"name": "prompt-agent", "version": "1.0"},
            "capabilities":    {},
        },
    }
    resp = client.post(url, json=payload, headers=_HEADERS_BASE)
    session_id = resp.headers.get("mcp-session-id")
    if not session_id:
        resp.raise_for_status()
        raise RuntimeError("MCP initialize 响应中没有 mcp-session-id header")
    return session_id


def _parse_response(resp: httpx.Response) -> dict:
    """
    解析 MCP 响应，兼容两种格式：
    - application/json：直接 resp.json()
    - text/event-stream：从 data: 行提取第一条 JSON
    """
    ct = resp.headers.get("content-type", "")
    if "text/event-stream" in ct:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        raise RuntimeError("SSE 响应中没有 data: 行")
    return resp.json()


def _rpc(method: str, params: dict, req_id: int = 1) -> dict:
    """握手 + JSON-RPC 调用；二者复用同一连接（同一副本）。

    端点顺序**固定 HF 优先、MS 兜底**——不再用粘性的 _active_url 作首选，
    避免 HF 一次偶发失败后被永久流放到 MS。_active_url 仅记录"最近一次实际服务
    的端点"，供健康展示。
    """
    global _active_url

    last_error = None
    for url in (_MCP_URL_HF, _MCP_URL_MS):
        try:
            # 单次 _rpc 用一个 client，握手与调用共用一条连接 → 同一副本
            with httpx.Client(timeout=_TIMEOUT) as client:
                session_id = _new_session_id(client, url)
                payload = {
                    "jsonrpc": "2.0",
                    "id":      req_id,
                    "method":  method,
                    "params":  params,
                }
                resp = client.post(
                    url,
                    json=payload,
                    headers={**_HEADERS_BASE, "mcp-session-id": session_id},
                )
                resp.raise_for_status()
                rpc_resp = _parse_response(resp)

            if "error" in rpc_resp:
                raise RuntimeError(rpc_resp["error"].get("message", f"{method} 返回错误"))

            if url == _MCP_URL_MS:
                print("[tools] HF 端点本次失败，已回退 MS", file=sys.stderr)
            with _lock:
                _active_url = url  # 记录本次实际服务端点（供健康展示）
            return rpc_resp.get("result", {})

        except Exception as e:
            last_error = e
            continue

    raise last_error


def _probe(url: str, timeout: float = 20) -> dict:
    """
    向单个端点执行一次真实 search_tags 检索（query="1girl", search_mode="precise_lookup"），
    验证 MCP 服务和后端数据库均可用。
    返回 {"ok": bool, "latency_ms": int?, "error": str?}。
    """
    init_payload = {
        "jsonrpc": "2.0",
        "id":      0,
        "method":  "initialize",
        "params":  {
            "protocolVersion": "2024-11-05",
            "clientInfo":      {"name": "prompt-agent-health", "version": "1.0"},
            "capabilities":    {},
        },
    }
    t0 = time.monotonic()
    try:
        # 1. 握手拿 session id
        init_resp = httpx.post(url, json=init_payload, headers=_HEADERS_BASE, timeout=timeout)
        init_resp.raise_for_status()
        session_id = init_resp.headers.get("mcp-session-id")
        if not session_id:
            return {"ok": False, "error": "响应中没有 mcp-session-id"}

        # 2. 真实检索
        call_payload = {
            "jsonrpc": "2.0",
            "id":      1,
            "method":  "tools/call",
            "params":  {
                "name": "search_tags",
                "arguments": {"query": "1girl", "search_mode": "precise_lookup"},
            },
        }
        call_resp = httpx.post(
            url, json=call_payload,
            headers={**_HEADERS_BASE, "mcp-session-id": session_id},
            timeout=timeout,
        )
        call_resp.raise_for_status()
        latency = round((time.monotonic() - t0) * 1000)

        rpc_resp = _parse_response(call_resp)
        if "error" in rpc_resp:
            return {"ok": False, "error": rpc_resp["error"].get("message", "tools/call 返回错误")}

        return {"ok": True, "latency_ms": latency}

    except httpx.TimeoutException:
        return {"ok": False, "error": "超时，服务可能正在冷启动"}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def check_mcp_health(timeout: float = 15) -> dict:
    """
    并发检查 HF 和 MS 两个端点的健康状态。
    返回 {"hf": {...}, "ms": {...}, "active": "hf"|"ms"}。
    """
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        hf_f = pool.submit(_probe, _MCP_URL_HF, timeout)
        ms_f = pool.submit(_probe, _MCP_URL_MS, timeout)
    return {"hf": hf_f.result(), "ms": ms_f.result(), "active": get_active_endpoint()}


def load_tools_from_mcp() -> list[dict]:
    """
    调用 MCP tools/list，将返回的工具定义转换为 OpenAI function calling 格式。
    拉取失败时打印警告并返回 _FALLBACK_TOOLS。
    """
    try:
        result = _rpc("tools/list", {})
        mcp_tools = result.get("tools", [])
        if not mcp_tools:
            raise RuntimeError("tools/list 返回的工具列表为空")

        converted = []
        for t in mcp_tools:
            converted.append({
                "type": "function",
                "function": {
                    "name":        t["name"],
                    "description": t.get("description", ""),
                    "parameters":  t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            })

        print(f"[tools] 已从 MCP 加载 {len(converted)} 个工具定义", file=sys.stderr)
        return converted

    except Exception as e:
        print(f"[tools] tools/list 拉取失败，使用回退定义：{e}", file=sys.stderr)
        return _FALLBACK_TOOLS


# 懒加载：首次调用 get_tools() 时从 MCP 拉取工具定义，后续缓存
_TOOLS_CACHE = None

def get_tools():
    """获取工具定义列表（懒加载，首次调用时从 MCP 拉取）。"""
    global _TOOLS_CACHE
    if _TOOLS_CACHE is None:
        _TOOLS_CACHE = load_tools_from_mcp()
    return _TOOLS_CACHE

TOOLS = []  # 兼容旧 import，实际使用请调用 get_tools()


def _call_mcp(tool_name: str, arguments: dict) -> dict:
    """
    发送 tools/call 请求，429 时指数退避重试（5s → 10s → 20s，最多 3 次）。
    返回解析后的结果 dict，出错时返回 {"error": "..."} 。
    """
    retry_delays = [5, 10, 20]
    last_error = None

    for attempt in range(len(retry_delays) + 1):  # 首次 + 3 次重试
        try:
            result = _rpc("tools/call", {"name": tool_name, "arguments": arguments})

            # MCP tools/call 结果在 result.content 里：list[{type, text}]
            content_blocks = result.get("content", [])
            for block in content_blocks:
                if block.get("type") == "text":
                    try:
                        return json.loads(block["text"])
                    except Exception:
                        return {"raw": block["text"]}

            return {"error": "MCP 返回内容为空"}

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429 and attempt < len(retry_delays):
                delay = retry_delays[attempt]
                print(
                    f"[tools] 429 限流，{delay}s 后重试（第 {attempt + 1}/{len(retry_delays)} 次）…",
                    file=sys.stderr,
                )
                time.sleep(delay)
                last_error = e
                continue
            return {"error": str(e)}
        except httpx.TimeoutException:
            return {"error": "请求超时，DanbooruSearch 服务可能正在冷启动，请稍后重试"}
        except Exception as e:
            return {"error": str(e)}

    return {"error": f"429 限流，已重试 {len(retry_delays)} 次仍失败: {str(last_error)}"}


def execute_search_tags(
    query: str,
    search_mode: str = "full_scene",
    category: str = "all",
    show_nsfw: bool = True,
    include_wiki: bool = False,
) -> str:
    """调用 MCP search_tags，直接透传服务端返回的原始 JSON 字符串。"""
    data = _call_mcp("search_tags", {
        "query":        query,
        "search_mode":  search_mode,
        "category":     category,
        "show_nsfw":    show_nsfw,
        "include_wiki": include_wiki,
    })

    if "error" in data:
        return json.dumps({"error": data["error"]}, ensure_ascii=False)

    return json.dumps(data, ensure_ascii=False, indent=2)


def execute_get_related_tags(
    tags: list[str],
    limit: int = 30,
    show_nsfw: bool = True,
    include_wiki: bool = False,
) -> str:
    """调用 MCP get_related_tags，直接透传服务端返回的原始 JSON 字符串。"""
    if not tags:
        return json.dumps({"error": "tags 列表为空"}, ensure_ascii=False)

    data = _call_mcp("get_related_tags", {
        "tags":         tags,
        "limit":        limit,
        "show_nsfw":    show_nsfw,
        "include_wiki": include_wiki,
    })

    if "error" in data:
        return json.dumps({"error": data["error"]}, ensure_ascii=False)

    return json.dumps(data, ensure_ascii=False, indent=2)


def execute_get_artist_recommendations(
    tags: list[str],
    limit: int = 30,
    min_cooc: int = 3,
    show_nsfw: bool = True,
) -> str:
    """调用 MCP get_artist_recommendations，直接透传服务端返回的原始 JSON 字符串。"""
    if not tags:
        return json.dumps({"error": "tags 列表为空"}, ensure_ascii=False)

    data = _call_mcp("get_artist_recommendations", {
        "tags":      tags,
        "limit":     limit,
        "min_cooc":  min_cooc,
        "show_nsfw": show_nsfw,
    })

    if "error" in data:
        return json.dumps({"error": data["error"]}, ensure_ascii=False)

    return json.dumps(data, ensure_ascii=False, indent=2)


def execute_get_anima_format() -> str:
    """调用 MCP get_anima_format，获取 Anima 模型的提示词格式规范。"""
    data = _call_mcp("get_anima_format", {})

    if "error" in data:
        return json.dumps({"error": data["error"]}, ensure_ascii=False)

    # MCP 返回的 raw 文本直接透传
    if "raw" in data:
        return data["raw"]
    return json.dumps(data, ensure_ascii=False, indent=2)


def execute_get_newbie_format() -> str:
    """调用 MCP get_newbie_format，获取 NewBie 模型的提示词格式规范。"""
    data = _call_mcp("get_newbie_format", {})

    if "error" in data:
        return json.dumps({"error": data["error"]}, ensure_ascii=False)

    # MCP 返回的 raw 文本直接透传
    if "raw" in data:
        return data["raw"]
    return json.dumps(data, ensure_ascii=False, indent=2)
