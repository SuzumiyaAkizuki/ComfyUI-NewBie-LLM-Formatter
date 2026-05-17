import os
import sys

# 确保插件目录在 sys.path 中，使 prompt_agent 包可被绝对导入
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from .LLM_Node import LLM_Prompt_Formatter
from .LLM_Style_Node import LLM_Xml_Style_Injector
from .Style_Saver_Node import LLM_Style_Saver

NODE_CLASS_MAPPINGS = {
    "LLM_Prompt_Formatter": LLM_Prompt_Formatter,
    "LLM_Xml_Style_Injector": LLM_Xml_Style_Injector,
    "LLM_Style_Saver": LLM_Style_Saver
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LLM_Prompt_Formatter": "LLM Xml Prompt Formatter",
    "LLM_Xml_Style_Injector": "XML Style Injector",
    "LLM_Style_Saver": "Style Preset Saver"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
