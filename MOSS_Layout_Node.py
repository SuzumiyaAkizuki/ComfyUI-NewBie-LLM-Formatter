"""Visual editor node: serializable workflow state -> validated MOSS layout."""

import json
from prompt_agent.moss_layout import validate_draft


class MOSS_Layout_Editor:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "layout_state": ("STRING", {"default": json.dumps({
                "version": 1, "width": 1024, "height": 1024,
                "summary": "", "items": [], "strict_validation": True,
            }), "multiline": False, "dynamicPrompts": False}),
        }}

    RETURN_TYPES = ("MOSS_LAYOUT", "INT", "INT")
    RETURN_NAMES = ("layout", "width", "height")
    FUNCTION = "build_layout"
    CATEGORY = "NewBie LLM Formatter"
    DESCRIPTION = "绘制 MOSS Layout，连接 Formatter 的 layout 输入，并将 mode 设为 MOSS。"

    def build_layout(self, layout_state):
        try:
            state = json.loads(layout_state)
        except (TypeError, ValueError) as error:
            raise ValueError("布局状态无法读取，请检查工作流或重新编辑布局") from error
        if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
            raise ValueError("不支持的布局状态版本，请检查工作流")
        strict = state.get("strict_validation", True)
        if type(strict) is not bool:
            raise ValueError("严格校验开关必须为布尔值")
        draft = validate_draft({
            "width": state.get("width"), "height": state.get("height"),
            "bbox_coord_space": "abs", "bbox_format": "xyxy",
            "summary": {"caption": state.get("summary")}, "items": state.get("items"),
        })
        return ({"draft": draft, "strict_validation": strict}, draft["width"], draft["height"])
