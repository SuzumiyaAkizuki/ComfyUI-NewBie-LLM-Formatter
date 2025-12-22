import re
import os
import json

class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m' # Reset all attributes



# === 配置 ===
# 这里定义默认样式，防止配置文件读取失败时报错
DEFAULT_STYLES = {
    "Empty style": {
        "artist": " ",
        "style": " "
    }
}

CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def load_styles_from_config():
    """
    辅助函数：读取 LPF_config.json 中的 'styles' 字段并将其与默认样式合并。
    """
    styles = DEFAULT_STYLES.copy()

    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)


                user_styles = data.get("styles", {})

                if isinstance(user_styles, dict) and user_styles:
                    styles.update(user_styles)

        except Exception as e:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: Error loading {CONFIG_FILENAME}: {e} {BColors.ENDC}")

    return styles


class LLM_Xml_Style_Injector:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        # 重新加载
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
                    "placeholder": "Add extra artists here (comma separated). Will be added BEFORE the preset."
                }),
                "style_add": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "Add extra styles here (comma separated). Will be added BEFORE the preset."
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("xml_output",)
    FUNCTION = "inject_style"
    CATEGORY = "LLM XML Helpers"

    def inject_style(self, xml_input, preset, artist_add, style_add):
        current_styles = load_styles_from_config()

        selected_data = current_styles.get(preset, {"artist": "", "style": ""})

        preset_artist = selected_data.get("artist", "")
        preset_style = selected_data.get("style", "")


        # 处理 Artist
        parts_artist = [artist_add.strip(), preset_artist]
        target_artist = ", ".join([p for p in parts_artist if p])  # 过滤空值并合并

        # 处理 Style
        parts_style = [style_add.strip(), preset_style]
        target_style = ", ".join([p for p in parts_style if p])

        output_text = xml_input

        def upsert_tag(text, tag_name, content, insert_after_tag=None):
            """
            text: 完整的 XML 文本
            tag_name: 比如 "artist" 或 "style"
            content: 要填入的内容
            insert_after_tag: 锚点标签
            """
            if not content:
                return text

            tag_pattern = f"(<{tag_name}>)(.*?)(</{tag_name}>)"

            # 签已经存在 -> 替换内容
            if re.search(tag_pattern, text, re.DOTALL | re.IGNORECASE):
                # \1 是 <tag>, \3 是 </tag>，这里直接替换中间内容
                return re.sub(tag_pattern, f"\\1{content}\\3", text, flags=re.DOTALL | re.IGNORECASE)

            # 标签不存在 -> 插入
            else:
                new_block = f"<{tag_name}>{content}</{tag_name}>"

                if insert_after_tag:
                    target_pattern = f"(</{insert_after_tag}>)"
                    if re.search(target_pattern, text, re.IGNORECASE):
                        print(f"[LLM_Prompt_Formatter]: Auto-inserting <{tag_name}> after <{insert_after_tag}>")
                        return re.sub(target_pattern, f"\\1\n{new_block}", text, flags=re.IGNORECASE, count=1)

                # 没找到锚点 -> 追加到末尾
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: Missing tag <{tag_name}>, appending to end.{BColors.ENDC}")
                return text + "\n" + new_block

        # 执行注入
        output_text = upsert_tag(output_text, "style", target_style)

        output_text = upsert_tag(output_text, "artist", target_artist, insert_after_tag="style")


        return (output_text,)
