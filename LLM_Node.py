import os
import re
import json
from openai import OpenAI
from prompt_agent.agent_core import PromptAgent
from prompt_agent import utils


class BColors:
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

CONFIG_FILENAME = "LPF_config.json"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CONFIG_FILENAME)


def get_platform_settings(api_url: str, model_name: str, thinking: bool) -> dict:
    """
    根据 API 平台和思考模式设置，返回 extra_body 参数。
    从 LLM_Prompt_Formatter.get_platform_settings 提取为模块级函数，
    供 Agent 模式和普通模式共用。
    """
    extra_body = {}

    def _is_claude_46_plus(name):
        n = name.lower()
        return ('claude-sonnet-4-6' in n or 'claude-opus-4-6' in n
                or 'sonnet-4.6' in n or 'opus-4.6' in n)

    if 'openrouter' in api_url:
        if thinking:
            extra_body = {"reasoning": {"enabled": True, "exclude": False}}
        else:
            extra_body = {"reasoning": {"enabled": False, "effort": "minimal"}}

    elif 'googleapis' in api_url:
        if not thinking:
            if '3' in model_name or '2.5-pro' in model_name:
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: googleapis平台的{model_name}模型无法彻底关闭思考功能。已将思考模式设置为low。{BColors.ENDC}")
                extra_body = {"reasoning_effort": "low"}
            else:
                extra_body = {"reasoning_effort": "none"}

    elif 'xiaomimimo' in api_url or 'moonshot' in api_url or 'deepseek' in api_url:
        if thinking:
            extra_body = {"thinking": {"type": "enabled"}}
        else:
            extra_body = {"thinking": {"type": "disabled"}}

    elif 'anthropic.com' in api_url:
        if thinking:
            if _is_claude_46_plus(model_name):
                extra_body = {"thinking": {"type": "adaptive"}}
            else:
                extra_body = {"thinking": {"type": "enabled", "budget_tokens": 8000}}

    elif 'vercel' in api_url:
        if thinking:
            extra_body = {"reasoning": {"enabled": True, "max_tokens": 8000}}
        else:
            extra_body = {"reasoning": {"enabled": False}}

    else:
        print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 思考模式开关暂不支持您使用的API平台。{BColors.ENDC}")

    return extra_body


def load_api_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: Error loading {CONFIG_FILENAME}: {e} {BColors.ENDC}")
    return {}


# split_by_language, clean_prompt, repair_xml_custom \u5df2\u8fc1\u79fb\u81f3 prompt_agent.utils



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
                "agent_effort": (["Close", "Low", "Medium", "High"],),
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

    def get_platform_settings(self, api_url, model_name, thinking):
        return get_platform_settings(api_url, model_name, thinking)

    # ── 辅助方法（从 process_text 拆分）─────────────────────────────────

    @staticmethod
    def _resolve_credentials(config, api_key, api_url):
        """解析 API 凭据：配置文件优先，UI 输入作为回退。
        Returns (final_key, final_url). 缺失时抛出 RuntimeError。
        """
        key_placeholders = ["sk-...", "读取API失败，请在此填写api key", "", "已从配置文件中读取api key，在此填写将不生效", None]
        url_placeholders = ["https://xxx.ai/api/v1", "读取API失败，请在此填写api url", "", "已从配置文件中读取api url，在此填写将不生效", None]

        config_key = config.get("api_key")
        config_url = config.get("api_url")

        if config_key and config_key not in key_placeholders:
            final_key = config_key.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从配置文件中读取API KEY.")
        elif api_key and api_key not in key_placeholders:
            final_key = api_key.replace(" ", "")
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 已从UI输入中读取API KEY.{BColors.ENDC}")
        else:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 配置文件和UI输入中均无有效API KEY.{BColors.ENDC}")
            raise RuntimeError(f"LLM_Prompt_Formatter failed: API KEY 缺失！请在 LPF_config.json 中配置")

        if config_url and config_url not in url_placeholders:
            final_url = config_url.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从配置文件中读取API URL: {final_url}.")
        elif api_url and api_url not in url_placeholders:
            final_url = api_url.replace(" ", "")
            print(f"[LLM_Prompt_Formatter]: 已从UI输入中读取API URL: {final_url}.")
        else:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 配置文件和UI输入中均无有效API URL.{BColors.ENDC}")
            raise RuntimeError(f"LLM_Prompt_Formatter failed: API URL 缺失！请在 LPF_config.json 中配置")

        return final_key, final_url

    @staticmethod
    def _build_normal_config(mode, config, api_url, model_name):
        """构建普通模式（非 Agent）的提示词配置。
        Returns (system_content, fewshot_user, fewshot_assistant, gemma_prompt, is_anima).
        """
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

        gemma_prompt = config.get("gemma_prompt", "You are an assistant designed to generate high-quality anime images with the highest degree of image-text alignment based on xml format textual prompts. <Prompt Start>\n")

        # Gemini 强力破甲
        jailbreaker = config.get("gemini_jailbreaker", "")
        if (not 'googleapis' in api_url) and ('gemini' in model_name.lower()) and jailbreaker:
            print(f"[LLM_Prompt_Formatter]: 已启用Gemini强力破甲。")
            system_content = f"{jailbreaker}{system_content}"

        return system_content, fewshot_user, fewshot_assistant, gemma_prompt, is_anima

    @staticmethod
    def _build_normal_messages(system_content, fewshot_user, fewshot_assistant, user_text, image):
        """构建普通模式的完整消息列表（含图片）。"""
        messages_content = [{"type": "text", "text": user_text}]
        if image is not None:
            print(f"[LLM_Prompt_Formatter]: 检测到图片输入，正在转换...")
            base64_image = utils.tensor_to_base64(image)
            messages_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
            })
        if fewshot_assistant and fewshot_user:
            print("[LLM_Prompt_Formatter]: 已成功应用用户few-shot设置。\n")
            return [
                {"role": "system", "content": system_content},
                {"role": "user", "content": fewshot_user},
                {"role": "assistant", "content": fewshot_assistant},
                {"role": "user", "content": messages_content},
            ]
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": messages_content},
        ]

    @staticmethod
    def _extract_reasoning(response, full_response, thinking):
        """从 LLM 响应中提取思考/推理内容。
        Returns (full_response, reasoning).
        注：会从 full_response 中移除 <think> 标签内容。
        """
        reasoning = ""
        found_thinking = False

        # 方式 1：reasoning 属性（部分平台）
        if hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning:
            reasoning = response.choices[0].message.reasoning
            found_thinking = True
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")
        if hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content:
            reasoning = response.choices[0].message.reasoning_content
            found_thinking = True
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]:大模型已进行深度思考，以下是思考内容：\n {reasoning} {BColors.ENDC}")

        # 方式 2：<think> 标签（DeepSeek R1 等）
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

        return full_response, reasoning

    @staticmethod
    def _parse_normal_output(full_response, is_anima, gemma_prompt):
        """解析普通模式的 LLM 输出。
        Anima: 中英文分离。NewBie: 三级 XML 提取策略。
        """
        if is_anima:
            xml_content, text_content = utils.split_by_language(full_response)
            if not xml_content:
                print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: Anima模式未检测到英文内容，返回完整响应。{BColors.ENDC}")
                xml_content = full_response
            return xml_content, text_content

        # NewBie mode: 严格错误处理
        if "```" not in full_response and "<img>" not in full_response:
            print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: 大模型的回复中未检测到<img>标签。以下是大模型的回复：\n {full_response} {BColors.ENDC}")
            raise ValueError("LLM API 的回复中未检测到<img>标签。")
        if "```" not in full_response and "<img>" in full_response and "</img>" not in full_response:
            print(f"{BColors.WARNING}[LLM_Prompt_Formatter]: 大模型的回复可能被截断。以下是大模型的回复：\n {full_response} {BColors.ENDC}")
            raise ValueError("LLM API 的回复可能被截断。")

        xml_content, text_content = utils.parse_newbie_content(full_response)
        xml_content = utils.clean_prompt(xml_content, gemma_prompt)
        return xml_content, text_content

    # ── 主方法 ─────────────────────────────────────────────────────────

    def process_text(self, api_key, api_url, model_name, mode, user_text, thinking, agent_effort, image=None):
        config = load_api_config()
        final_key, final_url = self._resolve_credentials(config, api_key, api_url)

        # ── Agent 模式分支 ───────────────────────────────────────────
        if agent_effort != "Close":
            print(f"[LLM_Prompt_Formatter]: Agent 模式已启用 (effort={agent_effort})")
            try:
                agent = PromptAgent(
                    api_key=final_key, api_url=final_url, model_name=model_name,
                    mode=mode, thinking=thinking, config=config, effort=agent_effort,
                )
                return agent.run(user_text, image=image)
            except Exception as e:
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: Agent 模式失败: {e}，回退为普通模式{BColors.ENDC}")

        # ── 普通模式 ─────────────────────────────────────────────────
        system_content, fewshot_user, fewshot_assistant, gemma_prompt, is_anima = \
            self._build_normal_config(mode, config, final_url, model_name)

        try:
            if not final_key or final_key == "sk-...":
                print(f"{BColors.FAIL}[LLM_Prompt_Formatter]: API KEY 缺失！请在 LPF_config.json 中配置。{BColors.ENDC}")
                raise RuntimeError(f"LLM_Prompt_Formatter failed: API KEY 缺失！请在 LPF_config.json 中配置")

            client = OpenAI(api_key=final_key, base_url=final_url)
            messages_list = self._build_normal_messages(
                system_content, fewshot_user, fewshot_assistant, user_text, image
            )

            extra_body = self.get_platform_settings(final_url, model_name, thinking)
            max_retries = 3

            for attempt in range(max_retries + 1):
                try:
                    response = client.chat.completions.create(
                        model=model_name, messages=messages_list,
                        temperature=0.7, extra_body=extra_body,
                    )
                    usage = response.usage
                    print(f"[LLM_Prompt_Formatter]: Tokens: {usage.prompt_tokens} input + {usage.completion_tokens} output = {usage.total_tokens} used.")
                    full_response = response.choices[0].message.content

                    # 检查响应是否为空
                    reasoning_present = (
                        hasattr(response.choices[0].message, 'reasoning') and response.choices[0].message.reasoning
                    ) or (
                        hasattr(response.choices[0].message, 'reasoning_content') and response.choices[0].message.reasoning_content
                    )
                    if full_response is None:
                        if not reasoning_present:
                            raise ValueError("LLM API 返回了 NoneType (返回内容为空)。")
                        full_response = ""

                    # 提取思考/推理内容
                    full_response, _reasoning = self._extract_reasoning(response, full_response, thinking)

                    # 解析输出
                    return self._parse_normal_output(full_response, is_anima, gemma_prompt)

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


# 以下函数已迁移至 prompt_agent.utils:
#   - split_by_language
#   - clean_prompt
#   - repair_xml_custom
