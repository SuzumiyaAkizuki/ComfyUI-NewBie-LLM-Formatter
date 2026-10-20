"""Shared final JSON contract and OpenAI-compatible response format selection."""
import json
from urllib.parse import urlparse

MARKER = "[FINAL_OUTPUT_JSON]"

def output_instruction(mode):
    value = ("可直接使用的 MOSS 提示词字符串（支持 Danbooru 标签与自然语言；Layout 时为已完成的模型输入）"
             if mode == "MOSS" else "完整 <img> XML 字符串" if mode == "NewBie" else "可直接使用的完整 Anima 提示词字符串（标签与英文自然语言）")
    return (MARKER + "\n最终回答必须是一个合法 JSON 对象，恰好包含 xml_out 和 text_out 两个字符串字段。"
            "xml_out 为" + value + "；text_out 为中文解释及所需翻译。"
            '示例：{"xml_out":"...","text_out":"中文说明"}。'
            "换行、双引号和反斜杠必须按 JSON 标准转义；不得添加 JSON 外的文字、Markdown 标题或代码围栏。"
            "此契约优先于配置示例、缓存规范和格式工具中对外层输出包装的要求；其中的提示词内容结构仍须遵守。"
            "工具调用阶段照常调用工具，仅最终回答遵循此 JSON 契约。"
            "\n\n## 中文说明与翻译（由本节点规定）\n"
            + ("text_out 必须包含最终 XML 中 caption 的完整中文翻译。" if mode == "NewBie" else
               "text_out 分点解释实际采用的标签、构图、空间关系和光照设计，并完整翻译最终提示词中的英文自然语言。")
            + ("Layout 还必须说明本次草稿的画布宽高，提醒生成工作流使用相同尺寸。" if mode == "MOSS" else "")
            + "只解释最终成品，使用中立、简洁的中文；不得输出思考过程、改动清单或无关背景。"
            "上述说明全部放入 text_out，不向 xml_out 加入翻译、接口字段、解释文字或展示用代码围栏。")

SCHEMA = {"type": "object", "properties": {
    "xml_out": {"type": "string"}, "text_out": {"type": "string"}},
    "required": ["xml_out", "text_out"], "additionalProperties": False}

def response_format_settings(api_url, model_name="", *, has_tools=False):
    host = (urlparse(api_url).hostname or "").lower()
    def domain(name):
        return host == name or host.endswith("." + name)
    if has_tools:
        # Tool selection and final-answer schemas are separate request phases.
        return {}
    if "deepseek" in model_name.lower() and any(domain(d) for d in ("openrouter.ai", "vercel.com", "vercel.sh")):
        # A gateway accepting JSON Schema does not establish model-level support.
        return {"response_format": {"type": "json_object"}}
    if any(domain(d) for d in ("openrouter.ai", "googleapis.com", "vercel.com", "vercel.sh", "openai.com")):
        return {"response_format": {"type": "json_schema", "json_schema": {
            "name": "prompt_output", "strict": True, "schema": SCHEMA}}}
    if any(domain(d) for d in ("deepseek.com", "moonshot.cn", "moonshot.ai", "xiaomimimo.com")):
        return {"response_format": {"type": "json_object"}}
    # Anthropic's OpenAI compatibility ignores response_format; unknown proxies use prompts.
    return {}

def format_rejected(error):
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    msg = str(error).lower()
    return status in (400, 422) and any(k in msg for k in (
        "response_format", "json_schema", "structured output")) and any(k in msg for k in (
        "unsupported", "not support", "not available", "unknown", "unrecognized", "not allowed", "invalid parameter"))

def parse_envelope(content):
    def unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError("输出 JSON 存在重复字段: " + key)
            obj[key] = value
        return obj
    try:
        payload = json.loads(content, object_pairs_hook=unique_object)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("最终输出不是有效 JSON（可能被截断）；要求 xml_out/text_out 两个字符串字段") from error
    if not isinstance(payload, dict) or set(payload) != {"xml_out", "text_out"}:
        raise ValueError("最终 JSON 必须恰好包含 xml_out 和 text_out")
    if not all(isinstance(payload[k], str) for k in payload):
        raise ValueError("xml_out 和 text_out 必须都是字符串")
    if not payload["xml_out"].strip():
        raise ValueError("xml_out 不能为空")
    return payload["xml_out"], payload["text_out"]


def normalize_fewshot(content, mode):
    """Migrate old user examples at the configuration boundary, never parse replies as Markdown."""
    if not content:
        return content
    try:
        parse_envelope(content)
        return content
    except ValueError:
        from prompt_agent import utils
        if mode in ("Anima", "MOSS"):
            import re
            match = re.search(r"(?m)^#{2,}\s*中文解释\s*$", content)
            prompt, explanation = (content[:match.start()], content[match.end():]) if match else (content, "")
            prompt = re.sub(r"^\s*#{2,}\s*Prompt\s*\n", "", prompt)
            prompt = utils.strip_code_fences(prompt)
        else:
            prompt, explanation = utils.parse_newbie_content(content)
        return json.dumps({"xml_out": prompt.strip(), "text_out": explanation.strip()}, ensure_ascii=False)
