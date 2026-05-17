"""
prompt_agent/utils.py
--------------------
Shared utility functions used by both agent_core and LLM_Node.

消除以下代码重复：
- DUP-1: 图片 Tensor → Base64 转换（原 3 处重复）
- DUP-2: XML 修复逻辑（原 agent_core._repair_xml / LLM_Node.repair_xml_custom）
- DUP-3: NewBie 模式输出解析（原 agent_core._parse_newbie_output / LLM_Node.process_text 内联）
- DUP-4: clean_prompt（原 agent_core._clean_prompt / LLM_Node.clean_prompt）
- DUP-5: split_by_language（原 agent_core._split_by_language / LLM_Node.split_by_language）
"""

import io
import re
import base64
import difflib

import numpy as np
from PIL import Image
from lxml import etree


# ═══════════════════════════════════════════════════════════════════
# DUP-1: 图片 Tensor → Base64 转换
# ═══════════════════════════════════════════════════════════════════

def tensor_to_base64(image_tensor):
    """将 ComfyUI 图片 Tensor 转换为 base64 编码的 JPEG 字符串。

    原出现在三处：agent_core._run_low_effort、agent_core.run()、LLM_Node.tensor_to_base64。
    """
    i = 255.0 * image_tensor[0].cpu().numpy()
    img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG", quality=90)
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


# ═══════════════════════════════════════════════════════════════════
# DUP-2: XML 修复
# ═══════════════════════════════════════════════════════════════════

def repair_xml(xml_string, verbose=False):
    """验证并修复 XML 格式。

    合并了 agent_core._repair_xml 和 LLM_Node.repair_xml_custom。
    verbose=True 时输出 diff 展示修复变化（LLM_Node 原行为）。
    """
    if not xml_string.strip():
        return xml_string

    strict_parser = etree.XMLParser(remove_blank_text=True)
    recover_parser = etree.XMLParser(recover=True, remove_blank_text=True)

    try:
        etree.fromstring(xml_string.encode('utf-8'), parser=strict_parser)
        print("[XML] 格式检查通过")
        return xml_string
    except etree.XMLSyntaxError:
        try:
            root = etree.fromstring(xml_string.encode('utf-8'), parser=recover_parser)
            if root is None:
                raise ValueError("无法解析出任何有效结构")

            repaired_xml = etree.tostring(
                root, encoding='unicode', pretty_print=True, xml_declaration=False
            ).strip()

            print("[XML] 检测到格式错误，已自动修复")
            if verbose:
                orig_lines = [line.strip() for line in xml_string.splitlines() if line.strip()]
                new_lines = [line.strip() for line in repaired_xml.splitlines() if line.strip()]
                diff = difflib.unified_diff(
                    orig_lines, new_lines,
                    fromfile='Original', tofile='Repaired', lineterm='', n=0
                )
                has_diff = False
                for line in diff:
                    if line.startswith(('+', '-')) and not line.startswith(('+++', '---')):
                        print(line)
                        has_diff = True
                if not has_diff:
                    print("(仅修复了微小的空白符或内部编码格式)")
                print("-" * 30)
            return repaired_xml
        except Exception as e:
            print(f"[XML] 损坏严重，无法修复: {e}")
            return xml_string


# ═══════════════════════════════════════════════════════════════════
# DUP-4: clean_prompt
# ═══════════════════════════════════════════════════════════════════

def clean_prompt(xml_content, gemma_prompt):
    """从内容中提取 <img>...</img> 块并修复 XML。

    合并了 agent_core._clean_prompt 和 LLM_Node.clean_prompt。
    """
    header = gemma_prompt
    match = re.search(r'(<img>.*?</img>)', xml_content, re.DOTALL | re.IGNORECASE)
    if not match:
        print("[XML] 未匹配到 <img> 标签，尝试全文修复")
        xml_content = repair_xml(xml_content)
        return xml_content
    xml_part = match.group(1)
    xml_part = repair_xml(xml_part)
    return f"{header}\n{xml_part}"


# ═══════════════════════════════════════════════════════════════════
# DUP-5: 中英文分离
# ═══════════════════════════════════════════════════════════════════

def split_by_language(text):
    """将文本分离为英文和中文两部分。

    合并了 agent_core._split_by_language 和 LLM_Node.split_by_language。
    统一使用标准 Unicode 中文字符范围 [\\u4e00-\\u9fff]。
    """
    text = text.replace('\\n', '\n')
    lines = text.splitlines()
    en_lines = []
    zh_lines = []
    for line in lines:
        if re.search(r'[一-鿿]', line):
            zh_lines.append(line)
        elif line.strip():
            en_lines.append(line)
    return "\n".join(en_lines).strip(), "\n".join(zh_lines).strip()


# ═══════════════════════════════════════════════════════════════════
# DUP-3: NewBie 模式输出解析（三级提取策略）
# ═══════════════════════════════════════════════════════════════════

def parse_newbie_content(content):
    """从 NewBie 模式 LLM 输出中提取 XML 和文本内容。

    三级提取策略：
    1. Markdown 代码块 (```xml ... ```)
    2. <img>...</img> 标签块
    3. 裸 <img> 标签（回复被截断的情况）

    返回 (xml_content, text_content)。
    原出现在 agent_core._parse_newbie_output 和 LLM_Node.process_text 内联代码。
    """
    match = re.search(r"```(?:xml)?\s*(.*?)\s*```", content, re.DOTALL)
    if match:
        xml_content = match.group(1).strip()
        text_content = content.replace(match.group(0), "").strip()
    elif "<img>" in content and "</img>" in content:
        start = content.find("<img>")
        end = content.rfind("</img>") + 6
        xml_content = content[start:end]
        text_content = content[:start] + content[end:]
    elif "<img>" in content:
        start = content.find("<img>")
        xml_content = content[start:]
        text_content = ""
    else:
        xml_content = content
        text_content = ""
    return xml_content, text_content
