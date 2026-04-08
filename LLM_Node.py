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
    ENDC = '\033[0m'

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


def split_by_language(text):
    """Split text into English and Chinese parts.
    Handles both real newlines and literal \\n that some models emit.
    """
    # Normalize literal \n sequences into real newlines
    text = text.replace('\\n', '\n')
    lines = text.splitlines()
    en_lines = []
    zh_lines = []
    for line in lines:
        if re.search(r'[\u4e00-\u9fff]', line):
            zh_lines.append(line)
        elif line.strip():
            en_lines.append(line)
    return "\n".join(en_lines).strip(), "\n".join(zh_lines).strip()



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
        default_user_text = "1girl, holding a sword"

        AllReadSuccess = True
        if model_list and isinstance(model_list, list) and (not all("your_model" in model for model in model_list)):
            model_widget = (model_list,)
        else:
            model_widget = ("STRING", {"multiline": False, "default": "读取模型列表失败，请在此填写模型名称"})
            AllReadSuccess = False

        if api_key and isinstance(api_key, str) and (not api_key == default_api_key):
            key_default = "已从配置文件中读取api key，在此填写将不生效"
        else:
            key_default = "读取API失败，请在此填写api key"
            AllReadSuccess = False

        if api_url and isinstance(api_url, str) and (not api_url == default_api_url):
            url_default = "已从配置文件中读取api url，在此填写将不生效"
        else:
            url_default = "读取API失败，请在此填写api url"
            AllReadSuccess = False

        if not AllReadSuccess:
            default_user_text = "1girl, holding a sword\n[警告]：读取API失败，请检查配置文件。你可以在节点输入相关信息。请注意，你的API会在原图中保存，分享原图可能会导致API泄露。强烈建议使用配置文件，完成配置后按F5刷新页面并重新创建此节点。"
            print(
                f"{BColors.WARNING}[LLM_Prompt_Formatter]: 读取API失败，请检查配置文件。你可以在节点输入相关信息。请注意，你的API会在原图中保存，分享原图可能会导致API泄露。强烈建议使用配置文件，完成配置后按F5刷新页面并重新创建此节点。{BColors.ENDC}")

        return {
            "required": {
                "api_key": ("STRING", {"multiline": False, "default": key_default, "dynamicPrompts": False}),
                "api_url": ("STRING", {"multiline": False, "default": url_default, "dynamicPrompts": False}),
                "model_name": model_widget,
                "user_text": ("STRING",
                              {"multiline": True, "default": default_user_text, "dynamicPrompts": False}),
                "thinking": ("BOOLEAN", {"default": False}),
                "mode": (["NewBie", "Anima"],),
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
        i = 255. * image_tensor[0].cpu().numpy()
        img = Image.fromarray(np.clip(i, 0, 255).astype(np.uint8))
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=90)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')

    def get_platform_settings(self, api_url, model_name, thinking):
        extra_body = {}

        # Detect Claude 4.6+ models which support adaptive thinking
        def _is_claude_46_plus(name):
            n = name.lower()
            return ('claude-sonnet-4-6' in n or 'claude-opus-4-6' in n
                    or 'sonnet-4.6' in n or 'opus-4.6' in n)

        if 'openrouter' in api_url:
            if thinking:
                extra_body = {"reasoning": {"enabled": True, "exclude": False}}
            else:
                extra_body = {"reasoning": {"enabled": False, "effort": "minimal"}}

        elif 'deepseek' in api_url:
            if thinking:
                extra_body = {"reasoning": {"type": "enabled"}}

        elif 'googleapis' in api_url:
            if not thinking:
                if '3' in model_name or '2.5-pro' in model_name:
                    print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: googleapis平台的{model_name}模型无法彻底关闭思考功能。已将思考模式设置为low。{BColors.ENDC}")
                    extra_body = {"reasoning_effort": "low"}
                else:
                    extra_body = {"reasoning_effort": "none"}

        elif 'xiaomimimo' in api_url or 'moonshot' in api_url:
            # Xiaomi MIMO and Kimi (api.moonshot.cn) share the same thinking param format.
            if thinking:
                extra_body = {"thinking": {"type": "enabled"}}
            else:
                extra_body = {"thinking": {"type": "disabled"}}

        elif 'anthropic.com' in api_url:
            # Anthropic official API (api.anthropic.com).
            # The OpenAI-compatible endpoint accepts the thinking param via extra_body.
            if thinking:
                if _is_claude_46_plus(model_name):
                    extra_body = {"thinking": {"type": "adaptive"}}
                else:
                    # Older Claude models: manual budget required
                    extra_body = {"thinking": {"type": "enabled", "budget_tokens": 8000}}
            # When thinking=False, omit the param entirely; Anthropic defaults to off.

        elif 'vercel' in api_url:
            # Vercel AI Gateway (ai-gateway.vercel.sh/v1).
            # The gateway exposes a unified reasoning field in extra_body that it
            # translates to each provider's native format server-side.
            # Docs: https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions/advanced
            if thinking:
                extra_body = {"reasoning": {"enabled": True, "max_tokens": 8000}}
            else:
                extra_body = {"reasoning": {"enabled": False}}

        else:
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 思考模式开关暂不支持您使用的API平台。{BColors.ENDC}")

        return extra_body

    def process_text(self, api_key, api_url, model_name, mode, user_text, thinking, image=None):
        config = load_api_config()
        config_key = config.get("api_key")
        config_url = config.get("api_url")
        key_placeholders = ["sk-...", "读取API失败，请在此填写api key", "", "已从配置文件中读取api key，在此填写将不生效", None]
        url_placeholders = ["https://xxx.ai/api/v1", "读取API失败，请在此填写api url", "", "已从配置文件中读取api url，在此填写将不生效", None]

        if config_key and config_key not in key_placeholders:
            final_key = config_key.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从配置文件中读取API KEY.")
        else:
            if api_key and api_key not in key_placeholders:
                final_key = api_key.replace(" ", "")
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 已从UI输入中读取API KEY.{BColors.ENDC}")
            else:
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 配置文件和UI输入中均无有效API KEY.{BColors.ENDC}")
                raise RuntimeError(f"LLM_Prompt_Formatter failed: API KEY 缺失！请在 LPF_config.json 中配置")

        if config_url and config_url not in url_placeholders:
            final_url = config_url.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从配置文件中读取API URL: {final_url}.")
        else:
            if api_url and api_url not in url_placeholders:
                final_url = api_url.replace(" ", "")
                print(f"[LLM_Prompt_Formatter]: 已从UI输入中读取API URL: {final_url}.")
            else:
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 配置文件和UI输入中均无有效API URL.{BColors.ENDC}")
                raise RuntimeError(f"LLM_Prompt_Formatter failed: API URL 缺失！请在 LPF_config.json 中配置")

        is_anima = (mode == "Anima")

        if is_anima:
            system_content = config.get("system_prompt_anima", "You are a helpful assistant that generates image prompts.")
            fewshot_user = config.get("fewshot_user_anima", "")
            fewshot_assistant = config.get("fewshot_assistant_anima", "")
            artists_anima = config.get("artists_anima", "")
            system_content = f"{system_content}{artists_anima}"
            print(f"[LLM_Prompt_Formatter]: 当前模式: Anima")
        else:
            system_content = config.get("system_prompt", "You are a helpful assistant that provides prompt tags.")
            fewshot_user = config.get("fewshot_user", "")
            fewshot_assistant = config.get("fewshot_assistant", "")
            print(f"[LLM_Prompt_Formatter]: 当前模式: NewBie")

        jailbreaker = config.get("gemini_jailbreaker", "")
        gemma_prompt = config.get("gemma_prompt", "You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>\n")

        if (not 'googleapis' in api_url) and ('gemini' in model_name.lower()) and jailbreaker:
            print(f"[LLM_Prompt_Formatter]: 已启用Gemini强力破甲。")
            system_content = f"{jailbreaker}{system_content}"

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

            extra_body = self.get_platform_settings(final_url, model_name, thinking)
            max_retries = 3

            if fewshot_assistant and fewshot_user:
                messages_list = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": fewshot_user},
                    {"role": "assistant", "content": fewshot_assistant},
                    {"role": "user", "content": messages_content}
                ]
                print("[LLM_Prompt_Formatter]: 已成功应用用户few-shot设置。\n")
            else:
                messages_list = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": messages_content}
                ]

            for attempt in range(max_retries + 1):
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=messages_list,
                        temperature=0.7,
                        extra_body=extra_body,
                    )
                    usage = response.usage
                    token_info = f"Tokens: {usage.prompt_tokens} tokens input + {usage.completion_tokens} tokens output = {usage.total_tokens} tokens used."
                    print(f"[LLM_Prompt_Formatter]: {token_info}")
                    full_response = response.choices[0].message.content

                    reasoning_present = False
                    if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                        reasoning_present = True
                    if hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
                        reasoning_present = True

                    if full_response is None:
                        if not reasoning_present:
                            raise ValueError("LLM API 返回了 NoneType (返回内容为空)。")
                        full_response = ""

                    reasoning = ""
                    found_thinking = False
                    if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
                        reasoning = response.choices[0].message.reasoning
                        found_thinking = True
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")
                    if hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
                        reasoning = response.choices[0].message.reasoning_content
                        found_thinking = True
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")

                    match = re.search(r'<think>(.*?)</think>', full_response, re.DOTALL)
                    if match:
                        found_thinking = True
                        reasoning = match.group(1)
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")
                        full_response = re.sub(r'<think>(.*?)</think>', "", full_response, flags=re.DOTALL).strip()

                    if thinking and not found_thinking:
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:虽然您开启了思考开关，但是未解析到思考内容。{BColors.ENDC}")
                    if (not full_response) and reasoning:
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:模型未返回结果但检测到思考内容，以思考内容作为结果。{BColors.ENDC}")
                        full_response = reasoning

                    if is_anima:
                        xml_content, text_content = split_by_language(full_response)
                        if not xml_content:
                            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: Anima模式未检测到英文内容，返回完整响应。{BColors.ENDC}")
                            xml_content = full_response
                        return (xml_content, text_content)

                    # NewBie mode: existing XML parsing logic
                    match = re.search(r"```(?:xml)?\s*(.*?)\s*```", full_response, re.DOTALL)
                    if match:
                        xml_content = match.group(1).strip()
                        text_content = full_response.replace(match.group(0), "").strip()
                    else:
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 解析代码块失败，正在尝试进一步分离{BColors.ENDC}")
                        if "<img>" in full_response and "</img>" in full_response:
                            start = full_response.find("<img>")
                            end = full_response.rfind("</img>") + 6
                            xml_content = full_response[start:end]
                            text_content = full_response[:start] + full_response[end:]
                        elif "<img>" in full_response:
                            start = full_response.find("<img>")
                            xml_content = full_response[start:]
                            text_content = ""
                            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 大模型的回复可能被截断。以下是大模型的回复：\n {full_response} {BColors.ENDC}")
                            raise ValueError("LLM API 的回复可能被截断。")
                        else:
                            xml_content = full_response
                            text_content = ""
                            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 大模型的回复中未检测到<img>标签。以下是大模型的回复：\n {full_response} {BColors.ENDC}")
                            raise ValueError("LLM API 的回复中未检测到<img>标签。")

                    xml_content = clean_prompt(xml_content, gemma_prompt)
                    return (xml_content, text_content)

                except Exception as inner_e:
                    err_msg = str(inner_e).lower()
                    if any(kw in err_msg for kw in ["api key", "authentication", "401", "unauthorized"]):
                        raise inner_e
                    if attempt < max_retries:
                        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 遇到网络抖动或API报错 ({inner_e})，正在进行第 {attempt + 1} 次重试...{BColors.ENDC}")
                        continue
                    else:
                        raise inner_e

        except Exception as e:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: {str(e)}, 请确认 API 配置是否正确。{BColors.ENDC}")
            raise RuntimeError(f"LLM_Prompt_Formatter failed: {str(e)}") from e


def clean_prompt(xml_content, gemma_prompt):
    header = gemma_prompt
    match = re.search(r'(<img>.*?</img>)', xml_content, re.DOTALL | re.IGNORECASE)
    if not match:
        print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: LLM返回结果匹配失败，请检查输出结果，必要时停止工作流。{BColors.ENDC}")
        xml_content = repair_xml_custom(xml_content)
        return xml_content
    xml_part = match.group(1)
    xml_part = repair_xml_custom(xml_part)
    return f"{header}\n{xml_part}"


def repair_xml_custom(xml_string):
    if not xml_string.strip():
        return xml_string

    strict_parser = etree.XMLParser(remove_blank_text=True)
    recover_parser = etree.XMLParser(recover=True, remove_blank_text=True)

    try:
        etree.fromstring(xml_string.encode('utf-8'), parser=strict_parser)
        print("[LLM_Prompt_Formatter]:已完成xml格式检查，无错误。")
        return xml_string
    except etree.XMLSyntaxError:
        try:
            root = etree.fromstring(xml_string.encode('utf-8'), parser=recover_parser)
            if root is None:
                raise ValueError("无法解析出任何有效结构")

            repaired_xml = etree.tostring(
                root,
                encoding='unicode',
                pretty_print=True,
                xml_declaration=False
            ).strip()

            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:检测到xml格式错误，已自动修复。差异如下：{BColors.ENDC}")
            orig_lines = [line.strip() for line in xml_string.splitlines() if line.strip()]
            new_lines = [line.strip() for line in repaired_xml.splitlines() if line.strip()]
            diff = difflib.unified_diff(orig_lines, new_lines, fromfile='Original', tofile='Repaired', lineterm='', n=0)

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
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]:XML 损坏严重，无法修复！必要时请停止工作流。\n错误详情: {e}{BColors.ENDC}")
            print("-" * 30)
            return xml_string