from .LLM_Node import LLM_Prompt_Formatter
from .LLM_Style_Node import LLM_Xml_Style_Injector

NODE_CLASS_MAPPINGS = {
    "LLM_Prompt_Formatter": LLM_Prompt_Formatter,
    "LLM_Xml_Style_Injector": LLM_Xml_Style_Injector,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LLM_Prompt_Formatter": "LLM Xml Prompt Formatter",
    "LLM_Xml_Style_Injector": "XML Style Injector",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
