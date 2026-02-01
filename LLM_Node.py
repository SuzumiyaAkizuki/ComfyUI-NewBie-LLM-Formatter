import io
import os
import re
import json
import base64
import difflib
from openai import OpenAI
from lxml import etree
import numpy as np
from PIL import Image


class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m' # Reset all attributes

CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def load_api_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: Error loading {CONFIG_FILENAME}: {e} {BColors.ENDC}")
    return {}


class LLM_Prompt_Formatter:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        config = load_api_config()
        model_list = config.get("model_list", [])
        api_key = config.get("api_key")
        api_url = config.get("api_url")
        default_api_key = "sk-..."
        default_api_url = "https://xxx.ai/api/v1"
        default_user_text="1girl, holding a sword"
        if model_list and isinstance(model_list, list) \
                and api_key and isinstance(api_key, str) and (not api_key == default_api_key)\
                and api_url and isinstance(api_url, str) and (not api_url == default_api_url):
            model_widget = (model_list,)
            key_default = "已从配置文件中读取api key，在此填写将不生效"
            url_default = "已从配置文件中读取api url，在此填写将不生效"
        else:
            model_widget = ("STRING", {"multiline": False, "default": "deepseek-chat"})
            key_default = "读取API失败，请在此填写api key"
            url_default = "读取API失败，请在此填写api url"
            default_user_text = "1girl, holding a sword\n[警告]：读取API失败，请检查配置文件。你可以在节点输入相关信息。请注意，你的API会在原图中保存，分享原图会导致API泄露。强烈建议使用配置文件，完成配置后按F5刷新页面并重新创建此节点。"
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 读取API失败，请检查配置文件。你可以在节点输入相关信息。请注意，你的API会在原图中保存，分享原图会导致API泄露。强烈建议使用配置文件，完成配置后按F5刷新页面并重新创建此节点。{BColors.ENDC}")


        return {
            "required": {
                "api_key": ("STRING", {"multiline": False, "default": key_default, "dynamicPrompts": False}),
                "api_url": ("STRING", {"multiline": False, "default": url_default, "dynamicPrompts": False}),
                "model_name": model_widget,
                "user_text": ("STRING",
                              {"multiline": True, "default": default_user_text, "dynamicPrompts": False}),
                "thinking": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "image": ("IMAGE",),
            }
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("xml_out", "text_out")
    OUTPUT_NODE = True
    FUNCTION = "process_text"
    CATEGORY = "NewBie LLM Formatter"

    def tensor_to_base64(self, image_tensor):
        """将 ComfyUI 的张量图片转换为 Base64 编码"""
        # image_tensor shape is [B, H, W, C]
        i = 255. * image_tensor[0].cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))

        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=90)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def get_platform_settings(self, api_url, model_name, thinking):
        """统一处理不同平台的参数构造"""
        extra_body = {}

        if 'openrouter' in api_url:
            if thinking:
                extra_body = {"reasoning": {"enabled": True, "exclude": False}}
            else:
                extra_body = {"reasoning": {"enabled": False,"effort": "minimal"}}
        elif 'deepseek' in api_url:
            if thinking:
                extra_body = {"reasoning": {"type": "enabled"}}
        elif 'googleapis' in api_url:
            if thinking:
                extra_body = {}
            else:
                if '3' in model_name or '2.5-pro' in model_name:
                    print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: googleapis平台的{model_name}模型无法彻底关闭思考功能。已将思考模式设置为low。{BColors.ENDC}")
                    extra_body = {"reasoning_effort": "low"}
                else:
                    extra_body = {"reasoning_effort":"none"}
        elif "xiaomimimo" in api_url:
            if thinking:
                extra_body = {"thinking": {"type": "enabled"}}
            else:
                extra_body = {"thinking": {"type": "disabled"}}
        else:
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 思考模式开关暂不支持您使用的API平台。{BColors.ENDC}")
        return extra_body

    def process_text(self, api_key, api_url, model_name, user_text,thinking,image=None):
        # 加载配置（优先从 JSON 取，UI 次之）

        config = load_api_config()
        config_key = config.get("api_key")
        config_url = config.get("api_url")
        key_placeholders = ["sk-...", "读取API失败，请在此填写api key", "","已从配置文件中读取api key，在此填写将不生效",None]
        url_placeholders = ["https://xxx.ai/api/v1","读取API失败，请在此填写api url","","已从配置文件中读取api url，在此填写将不生效",None]

        if config_key and config_key not in key_placeholders:
            final_key = config_key
            final_key = final_key.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从配置文件中读取API KEY.")
        else:
            if api_key and api_key not in key_placeholders:
                final_key = api_key
                final_key = final_key.replace(" ", "")
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 已从UI输入中读取API KEY.{BColors.ENDC}")
            else:
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 配置文件和UI输入中均无有效API KEY.{BColors.ENDC}")
                raise RuntimeError(f"LLM_Prompt_Formatter failed: API KEY 缺失！请在 LPF_config.json 中配置")

        if config_url and config_url not in url_placeholders:
            final_url = config_url
            final_url = final_url.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从配置文件中读取API URL: {final_url}.")
        else:
            if api_url and api_url not in url_placeholders:
                final_url = api_url
                final_url = final_url.replace(" ", "")
                print(f"[LLM_Prompt_Formatter]: 已从UI输入中读取API URL: {final_url}.")
            else:
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 配置文件和UI输入中均无有效API URL.{BColors.ENDC}")
                raise RuntimeError(f"LLM_Prompt_Formatter failed: API URL 缺失！请在 LPF_config.json 中配置")

        system_content = config.get("system_prompt", "You are a helpful assistant that provides prompt tags.")
        jailbreaker = config.get("gemini_jailbreaker","")
        gemma_prompt = config.get("gemma_prompt", "You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>\n")

        if (not 'googleapis' in api_url) and ('gemini' in model_name.lower()):
            print(f"[LLM_Prompt_Formatter]: 已启用Gemini强力破甲。")
            system_content = f"{jailbreaker}{system_content}"


        # 调用 OpenAI
        try:
            if not final_key or final_key == "sk-...":
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: API KEY 缺失！请在 LPF_config.json 中配置。{BColors.ENDC}")
                raise RuntimeError(f"LLM_Prompt_Formatter failed: API KEY 缺失！请在 LPF_config.json 中配置")

            client = OpenAI(api_key=final_key, base_url=final_url)

            messages_content = [{"type": "text", "text": user_text}]

            if image is not None:
                print(f"[LLM_Prompt_Formatter]: 检测到图片输入，正在转换...")
                base64_image = self.tensor_to_base64(image)
                messages_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                })

            extra_body = self.get_platform_settings(final_url,model_name,thinking)

            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": messages_content}
                ],
                temperature=0.7,
                extra_body=extra_body,
            )

            usage = response.usage
            prompt_tokens = usage.prompt_tokens
            completion_tokens = usage.completion_tokens
            total_tokens = usage.total_tokens
            token_info = f"Tokens: {prompt_tokens} tokens input + {completion_tokens} tokens output = {total_tokens} tokens used."
            print(f"[LLM_Prompt_Formatter]: {token_info}")

            full_response = response.choices[0].message.content
            #print(
               # f"{BColors.WARNING}[LLM_Prompt_Formatter调试输出]:LLM输出：\n {full_response} {BColors.ENDC}")

            found_thinking=False
            if  hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                reasoning=response.choices[0].message.reasoning
                found_thinking=True
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")

            if  hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
                reasoning=response.choices[0].message.reasoning_content
                found_thinking=True
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")

            match = re.search(r'<think>(.*?)</think>', full_response, re.DOTALL)
            if match:
                found_thinking=True
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {match.group(1)} {BColors.ENDC}")
                full_response = re.sub(r'<think>(.*?)</think>', "", full_response, flags=re.DOTALL)
                full_response = full_response.strip()

            if thinking and not found_thinking:
                print(
                    f"{BColors.WARNING}[LLM_Prompt_Formatter]:虽然您开启了思考开关，但是未解析到思考内容。{BColors.ENDC}")

            # # XML 匹配
            # xml_pattern = r"```xml\s*(.*?)\s*```"
            # match = re.search(xml_pattern, full_response, re.DOTALL)
            # if not match: # XML 匹配失败，试图匹配纯代码块
            #     code_pattern = r"```\s*(.*?)\s*```"
            #     match = re.search(code_pattern, full_response, re.DOTALL)
            match = re.search(r"```(?:xml)?\s*(.*?)\s*```", full_response, re.DOTALL)

            if match:
                xml_content = match.group(1).strip()
                # 剩下的部分作为 text_out
                text_content = full_response.replace(match.group(0), "").strip()
            else:
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 解析代码块失败，正在尝试进一步分离{BColors.ENDC}")

                # 如果没有代码块，检查是否有明显的 XML 标签结构
                if "<img>" in full_response and "</img>" in full_response:
                    start = full_response.find("<img>")
                    end = full_response.rfind("</img>") + 6
                    xml_content = full_response[start:end]
                    text_content = full_response[:start] + full_response[end:]
                else:
                    xml_content = full_response
                    text_content = ""
                    print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 大模型的回复中未检测到<img>标签。以下是大模型的回复：{full_response} {BColors.ENDC}")

            xml_content=clean_prompt(xml_content,gemma_prompt)
            return (xml_content, text_content)

        except Exception as e:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: {str(e)}, 请确认 API 配置是否正确。{BColors.ENDC}")
            raise RuntimeError(f"LLM_Prompt_Formatter failed: {str(e)}") from e



def clean_prompt(xml_content,gemma_prompt):
    """
    清洗大模型生成的 XML 提示词
    添加gemma_prompt
    """

    header = gemma_prompt

    match = re.search(r'(<img>.*?</img>)', xml_content, re.DOTALL | re.IGNORECASE)

    if not match:
        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: LLM返回结果匹配失败，请检查输出结果，必要时停止工作流。{BColors.ENDC}")
        xml_content=repair_xml_custom(xml_content) #尝试修复一次
        return xml_content

    # xml内部的内容
    xml_part = match.group(1)
    xml_part=repair_xml_custom(xml_part)

    cleaned_content = f"{header}\n{xml_part}"

    return cleaned_content


def repair_xml_custom(xml_string):
    """
    修复 XML 格式错误，不包含 XML 声明。
    成功修复时打印差异，修复失败时发出警告并返回原串。
    """
    if not xml_string.strip():
        return xml_string

    # 解析器
    strict_parser = etree.XMLParser(remove_blank_text=True)
    recover_parser = etree.XMLParser(recover=True, remove_blank_text=True)

    try:
        # 严格解析
        etree.fromstring(xml_string.encode('utf-8'), parser=strict_parser)
        print("[LLM_Prompt_Formatter]:已完成xml格式检查，无错误。")
        return xml_string
    except etree.XMLSyntaxError:
        try:
            # 修复
            root = etree.fromstring(xml_string.encode('utf-8'), parser=recover_parser)
            if root is None:
                raise ValueError("无法解析出任何有效结构")

            repaired_xml = etree.tostring(
                root,
                encoding='unicode',
                pretty_print=True,
                xml_declaration=False
            ).strip()

            # 修复对比
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:检测到xml格式错误，已自动修复。差异如下：{BColors.ENDC}")
            orig_lines = [line.strip() for line in xml_string.splitlines() if line.strip()]
            new_lines = [line.strip() for line in repaired_xml.splitlines() if line.strip()]
            diff = difflib.unified_diff(
                orig_lines,
                new_lines,
                fromfile='Original',
                tofile='Repaired',
                lineterm='',
                n=0
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
            # 修复失败
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:XML 损坏严重，无法修复！必要时请停止工作流。\n错误详情: {e}{BColors.ENDC}")
            print("-" * 30)
            return xml_string