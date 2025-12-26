import os
import json
import re
import difflib
from lxml import etree


class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


# === 配置与默认值 ===
# 预定义默认样式，确保加载失败时也有得选
DEFAULT_STYLES = {
    "空样式，请在下方文本框中自行书写": {
        "artist": "",
        "style": ""
    }
}

CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def load_styles_from_config():
    """读取配置文件并与默认样式合并"""
    styles = DEFAULT_STYLES.copy()

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                user_styles = data.get("styles", {})
                if isinstance(user_styles, dict) and user_styles:
                    styles.update(user_styles)
        except Exception as e:
            print(f"{BColors.FAIL}[XML_Style_Injector]: 加载配置文件出错: {e}{BColors.ENDC}")

    return styles


class LLM_Xml_Style_Injector:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        # 实时获取最新的 style 列表
        current_styles = load_styles_from_config()
        style_keys = list(current_styles.keys())

        return {
            "required": {
                "xml_input": ("STRING", {"forceInput": True}),
                "preset": (style_keys,),
            },
            "optional": {
                "artist_add": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "在此输入要添加的 Artist，将拼接到预设前面"
                }),
                "style_add": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "在此输入要添加的 Style，将拼接到预设前面"
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("xml_output",)
    FUNCTION = "inject_style"
    CATEGORY = "LLM XML Helpers"

    def inject_style(self, xml_input, preset, artist_add, style_add):
        # 1. 获取选中的预设内容
        current_styles = load_styles_from_config()
        selected_data = current_styles.get(preset, {"artist": "", "style": ""})

        preset_artist = selected_data.get("artist", "").strip()
        preset_style = selected_data.get("style", "").strip()

        # 2. 定义拼接逻辑：[输入] + [预设]
        def combine_tags(input_val, preset_val):
            input_val = input_val.strip()
            # 如果两边都有内容，用逗号隔开；否则返回不为空的那一边
            if input_val and preset_val:
                return f"{input_val}, {preset_val}"
            return input_val if input_val else preset_val

        target_artist = combine_tags(artist_add, preset_artist)
        target_style = combine_tags(style_add, preset_style)

        # 3. 提取 XML 块和 Header
        # 使用非贪婪匹配获取 <img> 之后的内容
        match = re.search(r'(<img>.*?</img>)', xml_input, re.DOTALL | re.IGNORECASE)

        if not match:
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 未发现 <img> 标签，跳过注入。{BColors.ENDC}")
            return (xml_input,)

        header_text = xml_input[:match.start()].strip()
        xml_content = match.group(1)

        try:
            # 4. 使用 lxml 解析
            parser = etree.XMLParser(recover=True, encoding='utf-8')
            root = etree.fromstring(xml_content.encode('utf-8'), parser=parser)

            # 5. 更新或创建标签的辅助函数
            def upsert(parent, tag_name, text_value):
                if text_value and text_value.strip():
                    elements = parent.xpath(f"//{tag_name}")
                    if elements:
                        for el in elements:
                            el.text = text_value
                    else:
                        # 尝试找 general_tags 容器插入
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 未找到<{tag_name}>标签，正在尝试注入<general_tags>{BColors.ENDC}")
                        gen_containers = parent.xpath("//general_tags")
                        if gen_containers:
                            new_node = etree.SubElement(gen_containers[0], tag_name)
                            new_node.text = text_value
                        else:
                            # 实在没地方插了就插在根节点最后
                            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 未找到<general_tags>标签{BColors.ENDC}")
                            new_node = etree.SubElement(parent, tag_name)
                            new_node.text = text_value
                else:
                    print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 用户未输入<{tag_name}>，不改变标签{BColors.ENDC}")
                    pass


            upsert(root, "artist", target_artist)
            upsert(root, "style", target_style)

            # 6. 生成最终字符串
            modified_xml = etree.tostring(root, encoding='unicode', method='xml', pretty_print=True)
            modified_xml = repair_xml_custom(modified_xml)
            # 如果 Header 为空，只返回 XML；否则拼接
            final_output = f"{header_text}\n{modified_xml}" if header_text else modified_xml
            return (final_output,)

        except Exception as e:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: XML 解析失败: {e}{BColors.ENDC}")
            return (xml_input,)


def repair_xml_custom(xml_string):
    """
    修复 XML 格式错误，不包含 XML 声明。
    成功修复时打印差异，修复失败时发出警告并返回原串。
    """
    if not xml_string.strip():
        return xml_string

    # 1. 准备解析器
    # remove_blank_text 帮助我们在对比时减少空白符干扰
    strict_parser = etree.XMLParser(remove_blank_text=True)
    recover_parser = etree.XMLParser(recover=True, remove_blank_text=True)

    try:
        # 尝试严格解析
        etree.fromstring(xml_string.encode('utf-8'), parser=strict_parser)
        print("[LLM_Prompt_Formatter]:已完成xml格式检查，无错误。")
        return xml_string
    except etree.XMLSyntaxError:
        try:
            # 2. 触发修复逻辑
            root = etree.fromstring(xml_string.encode('utf-8'), parser=recover_parser)
            if root is None:
                raise ValueError("无法解析出任何有效结构")

            # 3. 生成修复后的字符串
            # xml_declaration=False 剔除 <?xml ... ?>
            # encoding='unicode' 返回 str 类型而非 bytes
            repaired_xml = etree.tostring(
                root,
                encoding='unicode',
                pretty_print=True,
                xml_declaration=False
            ).strip()

            # 4. 打印修复对比
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:检测到xml格式错误，已自动修复。差异如下：{BColors.ENDC}")
            diff = difflib.unified_diff(
                xml_string.splitlines(),
                repaired_xml.splitlines(),
                fromfile='Original',
                tofile='Repaired',
                lineterm=''
            )

            # 过滤掉 diff 头部信息，只看改动
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
            # 修复失败
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:XML 损坏严重，无法修复！必要时请停止工作流。\n错误详情: {e}{BColors.ENDC}")
            print("-" * 30)
            return xml_string