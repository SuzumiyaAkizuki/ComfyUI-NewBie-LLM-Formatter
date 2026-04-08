import os
import json
import re
from lxml import etree


class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


DEFAULT_STYLES = {
    "空样式，请在下方文本框中自行书写": {
        "artist": "",
        "style": ""
    }
}

CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def load_styles_from_config():
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


def format_anima_artists(artist_str):
    """
    Clean and convert a comma-separated artist string to @artist1, @artist2 format.
    Cleaning steps per artist name:
      1. Remove brackets: [], {}, ()
      2. Remove colon-prefixed weights (e.g. :1.2, :0.93) and standalone
         numbers/decimals surrounded by spaces or string boundaries.
         Numbers part of a tag token (e.g. year_2024) are preserved.
      3. Replace internal spaces with underscores (spaces near commas are
         already stripped by the split/strip step).
    """
    if not artist_str.strip():
        return ""

    # Remove bracket characters before splitting
    artist_str = re.sub(r'[\[\]{}()]', '', artist_str)

    tags = [t.strip() for t in artist_str.split(',') if t.strip()]

    cleaned = []
    for tag in tags:
        if tag.startswith('@'):
            tag = tag[1:]
        # Remove "artist:" prefix (case-insensitive)
        tag = re.sub(r'(?i)^artist:', '', tag.strip())
        # Remove colon-prefixed numbers/weights (e.g. :1.2, :0.93) before stripping colons
        tag = re.sub(r':\d+(\.\d+)?', '', tag)
        # Remove all remaining colons
        tag = tag.replace(':', '')
        # Remove standalone numbers/decimals not adjacent to letters or underscores
        tag = re.sub(r'(?<![a-zA-Z_\d])\d+(\.\d+)?(?![a-zA-Z_\d])', '', tag)
        # Replace internal whitespace with underscores
        tag = re.sub(r'\s+', '_', tag.strip()).strip('_')
        if tag:
            cleaned.append(f'@{tag}')

    return ', '.join(cleaned)


def inject_anima_style(prompt_text, artist_str, style_str):
    """
    Inject artist and style into an Anima-mode plain text prompt.
    Mirrors NewBie upsert behaviour: if a field is empty, leave the original untouched.
    """
    lines = prompt_text.splitlines()

    def is_artist_line(line):
        stripped = line.strip()
        if not stripped:
            return False
        return bool(re.match(r'(@[\w\-.]+[,\s]*)+$', stripped))

    def strip_artists_from_line(line):
        line = re.sub(r'@[\w\-.]+', '', line)
        line = re.sub(r'\s*,\s*,\s*', ', ', line)
        return line.strip(' ,')

    result_lines = list(lines)
    non_empty = [(i, l) for i, l in enumerate(result_lines) if l.strip()]

    if not non_empty:
        parts = [p for p in [format_anima_artists(artist_str), prompt_text, style_str] if p]
        return "\n".join(parts)

    # --- Artist injection (only when artist_str is non-empty) ---
    if artist_str.strip():
        formatted_artists = format_anima_artists(artist_str)

        artist_line_idx = None
        if len(non_empty) >= 2:
            second_idx, second_line = non_empty[1]
            if is_artist_line(second_line):
                artist_line_idx = second_idx

        if artist_line_idx is not None:
            result_lines[artist_line_idx] = formatted_artists
        else:
            first_idx = non_empty[0][0]
            result_lines[first_idx] = strip_artists_from_line(result_lines[first_idx])
            if formatted_artists:
                result_lines.insert(first_idx + 1, formatted_artists)
    else:
        print(f"{BColors.WARNING}[XML_Style_Injector]: 用户未输入 Artist，保持原有 Artist 不变{BColors.ENDC}")

    # --- Style injection (only when style_str is non-empty) ---
    if style_str.strip():
        result_lines.append(style_str)

    return "\n".join(result_lines)


class LLM_Xml_Style_Injector:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        current_styles = load_styles_from_config()
        style_keys = list(current_styles.keys())

        return {
            "required": {
                "xml_input": ("STRING", {"forceInput": True}),
                "mode": (["NewBie", "Anima"],),
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
    CATEGORY = "NewBie LLM Formatter"

    def inject_style(self, xml_input, mode, preset, artist_add, style_add):
        current_styles = load_styles_from_config()
        selected_data = current_styles.get(preset, {"artist": "", "style": ""})

        preset_artist = selected_data.get("artist", "").strip()
        preset_style = selected_data.get("style", "").strip()

        def combine_tags(input_val, preset_val):
            input_val = input_val.strip()
            if input_val and preset_val:
                return f"{input_val}, {preset_val}"
            return input_val if input_val else preset_val

        target_artist = combine_tags(artist_add, preset_artist)
        target_style = combine_tags(style_add, preset_style)

        if mode == "Anima":
            result = inject_anima_style(xml_input, target_artist, target_style)
            return (result,)

        # NewBie mode: existing XML injection logic
        match = re.search(r'(<img>.*?</img>)', xml_input, re.DOTALL | re.IGNORECASE)

        if not match:
            print(f"{BColors.WARNING}[XML_Style_Injector]: 未发现 <img> 标签，跳过注入。{BColors.ENDC}")
            return (xml_input,)

        header_text = xml_input[:match.start()].strip()
        xml_content = match.group(1)

        try:
            parser = etree.XMLParser(recover=True, encoding='utf-8')
            root = etree.fromstring(xml_content.encode('utf-8'), parser=parser)

            def upsert(parent, tag_name, text_value):
                if text_value and text_value.strip():
                    elements = parent.xpath(f"//{tag_name}")
                    if elements:
                        for el in elements:
                            el.text = text_value
                    else:
                        print(f"{BColors.WARNING}[XML_Style_Injector]: 未找到<{tag_name}>标签，正在尝试注入<general_tags>{BColors.ENDC}")
                        gen_containers = parent.xpath("//general_tags")
                        if gen_containers:
                            new_node = etree.SubElement(gen_containers[0], tag_name)
                            new_node.text = text_value
                        else:
                            print(f"{BColors.WARNING}[XML_Style_Injector]: 未找到<general_tags>标签{BColors.ENDC}")
                            new_node = etree.SubElement(parent, tag_name)
                            new_node.text = text_value
                else:
                    print(f"{BColors.WARNING}[XML_Style_Injector]: 用户未输入<{tag_name}>，不改变标签{BColors.ENDC}")

            upsert(root, "artist", target_artist)
            upsert(root, "style", target_style)

            modified_xml = etree.tostring(root, encoding='unicode', method='xml', pretty_print=True)
            final_output = f"{header_text}\n{modified_xml}" if header_text else modified_xml
            return (final_output,)

        except Exception as e:
            print(f"{BColors.FAIL}[XML_Style_Injector]: XML 解析失败: {e}{BColors.ENDC}")
            return (xml_input,)