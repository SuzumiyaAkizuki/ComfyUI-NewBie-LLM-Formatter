"""Visual editor node: serializable workflow state -> validated MOSS layout."""

import json
from prompt_agent.layout_tasks import state_draft, jobs, compilations


class MOSS_Layout_Editor:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "layout_state": ("STRING", {"default": json.dumps({
                "version": 1, "width": 1024, "height": 1024,
                "summary": "", "items": [], "strict_validation": True,
            }), "multiline": False, "dynamicPrompts": False}),
        }, "hidden": {"prompt": "PROMPT", "unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("STRING", "INT", "INT")
    RETURN_NAMES = ("layout_prompr", "width", "height")
    FUNCTION = "build_layout"
    CATEGORY = "NewBie LLM Formatter"
    DESCRIPTION = "编辑 MOSS Layout；layout_prompr 可连接 Formatter 的 layout 或直接用于 MOSS。工作流执行不调用 LLM，说明保留在节点内。"

    @classmethod
    def IS_CHANGED(cls, layout_state, **kwargs):
        try:
            state = json.loads(layout_state)
            if jobs.active(state.get("client_id"), state.get("editor_id")):
                return float("nan")
        except (ValueError, TypeError, AttributeError):
            pass
        return layout_state

    def build_layout(self, layout_state, prompt=None, unique_id=None):
        try:
            state = json.loads(layout_state)
        except (TypeError, ValueError) as error:
            raise ValueError("布局状态无法读取，请检查工作流或重新编辑布局") from error
        if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
            raise ValueError("不支持的布局状态版本，请检查工作流")
        strict = state.get("strict_validation", True)
        if type(strict) is not bool:
            raise ValueError("严格校验开关必须为布尔值")
        if jobs.active(state.get("client_id"), state.get("editor_id")):
            raise ValueError("布局 Agent 正在运行，请完成或取消后再开启工作流")
        draft = state_draft(state)
        output = compilations.compile(draft, state.get("output"))
        return {"ui": {"moss_layout_result": [{"draft": draft, "output": output}]},
                "result": (output["prompt"], draft["width"], draft["height"])}
