"""Anima and NewBie final-output parsing."""

import re

from prompt_agent import utils
from prompt_agent.console import _log, _log_ok, _log_warn


def parse_output(mode, content, config):
    if mode == "Anima":
        return parse_anima_output(content)
    return parse_newbie_output(content, config)


def parse_anima_output(content):
    _log("Anima 模式: 按 Markdown 标题分割输出")
    prompt_match = re.search(r'#{2,}\s*Prompt\s*\n(.*?)(?=\n#{2,}|\Z)', content, re.DOTALL)
    explanation_match = re.search(r'#{2,}\s*中文解释\s*\n(.*)', content, re.DOTALL)
    expl_text = explanation_match.group(1) if explanation_match else None
    if expl_text is None:
        headings = list(re.finditer(r'(?m)^#{2,}[^\n]*\n', content))
        if len(headings) >= 2:
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
        xml_out, text_out = utils.split_by_language(content)
        xml_out = utils.strip_code_fences(xml_out)
        if not xml_out:
            _log_warn("Anima 模式未检测到英文内容，返回完整响应")
            xml_out = content
    return xml_out, text_out


def parse_newbie_output(content, config):
    _log("NewBie 模式: 提取 XML 代码块")
    xml_content, text_content = utils.parse_newbie_content(content)
    if not re.search(r"", content, re.DOTALL):
        if "<img>" in content and "</img>" in content:
            pass
        elif "<img>" in content:
            _log_warn("回复可能被截断")
        else:
            _log_warn("未检测到 <img> 标签")

    gemma_prompt = config.get(
        "gemma_prompt",
        "You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>\n",
    )
    xml_content = utils.clean_prompt(xml_content, gemma_prompt)
    return xml_content, text_content
