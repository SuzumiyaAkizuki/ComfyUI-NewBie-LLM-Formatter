"""Provider-compatible message normalization and reasoning replay helpers."""

from types import SimpleNamespace


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


def _serialize_tool_calls(tool_calls):
    """序列化 tool_calls，并保留网关附加的 thought signature 等字段。"""
    if not tool_calls:
        return []
    result = []
    for tc in tool_calls:
        if hasattr(tc, "model_dump"):
            item = tc.model_dump(exclude_none=True)
        else:
            item = {
                "id": tc.id,
                "type": tc.type,
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for key, value in vars(tc).items():
                if key not in ("index", "id", "type", "function") and value is not None:
                    item[key] = _plain_data(value)
            for key, value in vars(tc.function).items():
                if key not in ("name", "arguments") and value is not None:
                    item["function"][key] = _plain_data(value)
        item.pop("index", None)
        result.append(_plain_data(item))
    return result


def _plain_data(value):
    """Convert SDK response models into request-safe plain Python data."""
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        return {key: _plain_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_data(item) for item in value]
    if hasattr(value, "__dict__"):
        return {
            key: _plain_data(item)
            for key, item in vars(value).items()
            if item is not None
        }
    return value


def _reasoning_text_from_details(details):
    """Extract displayable text without changing reasoning_details replay data."""
    parts = []
    for item in _plain_data(details) or []:
        if not isinstance(item, dict):
            continue
        text = item.get("text") or item.get("summary")
        if text:
            parts.append(str(text))
    return "".join(parts)


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


def _assistant_tool_message(content, tool_calls, source_message=None):
    """Build assistant history with one canonical provider reasoning field.

    DeepSeek requires ``reasoning_content`` on tool-call turns. OpenRouter and
    other compatible gateways may instead return ``reasoning`` or structured
    ``reasoning_details`` (including encrypted/signature-bearing blocks).

    Some gateways expose the same reasoning through two or three aliases at
    once. Replaying all aliases duplicates the same chain in the next request,
    so prefer the lossless structured representation and send exactly one.
    """
    message = {"role": "assistant", "content": content, "tool_calls": tool_calls}
    for field in ("reasoning_details", "reasoning_content", "reasoning"):
        value = getattr(source_message, field, None)
        if value is not None and (not isinstance(value, str) or value.strip()):
            message[field] = _plain_data(value)
            break
    return message


def _usage_summary(usage):
    if not usage:
        return "usage=n/a"
    prompt_tokens = getattr(usage, "prompt_tokens", "?")
    completion_tokens = getattr(usage, "completion_tokens", "?")
    total_tokens = getattr(usage, "total_tokens", "?")
    return f"usage={prompt_tokens}+{completion_tokens}={total_tokens}"


def build_stream_message(content, tool_calls, reasoning_content, reasoning,
                         reasoning_details):
    """Construct the lightweight message namespace used by stream aggregation."""
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls or None,
        reasoning_content=reasoning_content or None,
        reasoning=reasoning or None,
        reasoning_details=reasoning_details or None,
    )
