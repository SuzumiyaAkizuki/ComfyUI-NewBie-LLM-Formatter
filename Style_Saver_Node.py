import json
import os
import re


class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


class LLM_Style_Saver:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text_input": ("STRING", {"forceInput": True}),
                "preset_name": ("STRING", {"multiline": False, "default": "", "placeholder": "在这里输入新预设的名称"}),
                "save_trigger": ("BOOLEAN",
                                 {"default": False, "label_on": "Save as Styles", "label_off": "Do Not Save"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("extracted_tags",)
    FUNCTION = "save_preset_logic"
    CATEGORY = "NewBie LLM Formatter"
    OUTPUT_NODE = True

    def save_preset_logic(self, text_input, preset_name, save_trigger):
        # 提取
        artist_pattern = r"<(?:artist|artists)>(.*?)</(?:artist|artists)>"
        style_pattern = r"<(?:style|styles)>(.*?)</(?:style|styles)>"

        all_artists = re.findall(artist_pattern, text_input, re.IGNORECASE | re.DOTALL)
        all_styles = re.findall(style_pattern, text_input, re.IGNORECASE | re.DOTALL)

        # 清洗 Artist
        clean_artists = []
        for a in all_artists:
            tags = [t.strip() for t in a.split(',') if t.strip()]
            clean_artists.extend(tags)
        final_artist_str = ", ".join(list(dict.fromkeys(clean_artists)))

        # 清洗 Style
        clean_styles = []
        for s in all_styles:
            tags = [t.strip() for t in s.split(',') if t.strip()]
            clean_styles.extend(tags)
        final_style_str = ", ".join(list(dict.fromkeys(clean_styles)))

        # 拼装输出字符串
        extracted_output = f"<artist>{final_artist_str}</artist>\n<style>{final_style_str}</style>"

        normalized_name = preset_name.strip()

        # 不保存
        if not save_trigger:
            return (extracted_output,)

        if not normalized_name:
            print(f"{BColors.WARNING}[Style_Saver] 警告：已开启保存但未输入预设名称，未保存。{BColors.ENDC}")
            return (extracted_output,)

        if not final_artist_str and not final_style_str:
            print(f"{BColors.WARNING}[Style_Saver] 警告：文本中未找到有效标签，未保存。{BColors.ENDC}")
            return (extracted_output,)

        if not os.path.exists(CONFIG_PATH):
            print(f"{BColors.FAIL}[Style_Saver] 错误：找不到文件 {CONFIG_PATH}{BColors.ENDC}")
            return (extracted_output,)

        # 写文件
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if "styles" not in data:
                data["styles"] = {}

            # 重名检查
            if normalized_name in data["styles"]:
                print(
                    f"{BColors.WARNING}[Style_Saver] 提示：预设名称 '{normalized_name}' 已经存在。未保存。{BColors.ENDC}")
                return (extracted_output,)

            # 保存
            data["styles"][normalized_name] = {
                "artist": final_artist_str,
                "style": final_style_str
            }

            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[Style_Saver] 成功保存新预设：'{normalized_name}'")

        except json.JSONDecodeError:
            print(f"{BColors.FAIL}[Style_Saver] 严重错误：JSON 格式损坏。{BColors.ENDC}")
        except Exception as e:
            print(f"{BColors.FAIL}[Style_Saver] 未知错误：{e}{BColors.ENDC}")

        # 4. 无论保存结果如何，都返回提取的内容
        return (extracted_output,)

