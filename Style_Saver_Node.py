import json
import os
import re

class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m' # Reset all attributes
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

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "save_preset_logic"
    CATEGORY = "NewBie LLM Formatter"
    OUTPUT_NODE = True

    def save_preset_logic(self, text_input, preset_name, save_trigger):

        pass_through_output = text_input

        if not save_trigger:
            return ()

        normalized_name = preset_name.strip()
        if not normalized_name:
            print(f"{BColors.WARNING}[Style_Saver] 警告：没有输入预设名称，保存已跳过。{BColors.ENDC}")
            return ()

        # 匹配
        artist_pattern = r"<artist>(.*?)</artist>"
        style_pattern = r"<style>(.*?)</style>"
        all_artists = re.findall(artist_pattern, text_input, re.IGNORECASE | re.DOTALL)
        all_styles = re.findall(style_pattern, text_input, re.IGNORECASE | re.DOTALL)
        clean_artists = []
        for a in all_artists:
            tags = [t.strip() for t in a.split(',') if t.strip()]
            clean_artists.extend(tags)
        final_artist_str = ", ".join(list(dict.fromkeys(clean_artists)))
        clean_styles = []
        for s in all_styles:
            tags = [t.strip() for t in s.split(',') if t.strip()]
            clean_styles.extend(tags)
        final_style_str = ", ".join(list(dict.fromkeys(clean_styles)))

        if not final_artist_str and not final_style_str:
            print(f"{BColors.WARNING}[LLM_Style_Saver] 文本中没有找到任何有效的 artist 或 style 内容。{BColors.ENDC}")
            return ()

        if not os.path.exists(CONFIG_PATH):
            print(f"{BColors.FAIL}[Style_Saver] 错误：找不到文件 {CONFIG_PATH} {BColors.ENDC}")
            return ()

        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if "styles" not in data:
                data["styles"] = {}

            # --- 关键修改：重名处理 ---
            if normalized_name in data["styles"]:

                print(f"{BColors.WARNING}[Style_Saver] 提示：预设名称 '{normalized_name}' 已存在。本次保存已忽略，但工作流继续执行。{BColors.ENDC}")
                return ()

            # 写入新数据
            new_entry = {
                "artist": final_artist_str,
                "style": final_style_str
            }

            data["styles"][normalized_name] = new_entry

            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            print(f"[Style_Saver] 成功保存新预设：'{normalized_name}'")

        except json.JSONDecodeError:
            print(f"{BColors.FAIL} [Style_Saver] 严重错误：配置文件 JSON 格式损坏，无法写入。{BColors.ENDC}")
        except Exception as e:
            print(f"{BColors.FAIL} [Style_Saver] 未知错误：{e} {BColors.ENDC}")

        return ()

