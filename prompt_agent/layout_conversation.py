"""Canvas conversations are explicit turns, separate from Formatter diff caching.

Only accepted turns live in the job manager's memory. Tool traces are transient;
the current canvas is attached afresh on every turn, never reconstructed from history.
"""
from copy import deepcopy
import json
import re

from prompt_agent.agent_core import PromptAgent
from prompt_agent.moss_layout import validate_draft


CANVAS_RULES = """\n[CANVAS_CONVERSATION_RULES]
这是同一作品的连续对话。本轮要求是新消息，不是上一轮输入的替换文本。
本轮 CURRENT_CANVAS_DATA 是当前作品的事实基准，优先于历史中的旧布局。
保留用户手动修订；默认只修改本轮要求涉及的部分，不无故恢复或重做其他内容。
空画板按要求创建，有内容时按要求修改；只有用户明确要求时才重新构图。
必须使用 Layout，保持当前画布宽高；用原始 abs/xyxy 草稿调用 compile_moss_prompt。
"""


def polish_only(request, explicit=False):
    # Deliberately bounded: explicit UI lock is the reliable alternative to wording.
    return explicit or bool(re.search(
        r"(?:仅|只)(?:润色|扩写|修改描述)|保留构图|不(?:改|调整|改变)(?:画框|布局|构图)|only\s+(?:polish|rephrase)",
        request, re.I))


def canvas_input(state, request, locked=False):
    if locked:
        from prompt_agent.layout_tasks import state_draft
        draft = state_draft(state)
    else:
        draft = {"width": state["width"], "height": state["height"],
                 "bbox_coord_space": "abs", "bbox_format": "xyxy",
                 "summary": {**state.get("summary_extra", {}), "caption": state.get("summary", "")},
                 "items": deepcopy(state.get("items", []))}
        # Unfinished descriptions are legitimate editor input. Validate geometry
        # and schema with temporary nonempty text, but send the actual blanks.
        check = deepcopy(draft)
        if not isinstance(check["summary"]["caption"], str):
            raise ValueError("全局描述必须为字符串")
        check["summary"]["caption"] = check["summary"]["caption"] or "pending"
        for item in check["items"]:
            if not isinstance(item.get("caption"), str):
                raise ValueError("元素描述必须为字符串")
            item["caption"] = item["caption"].strip() or "pending"
            if item.get("label") == "text" and not item.get("text"):
                item["text"] = "pending"
        if not check["items"]:
            check["items"] = [{"label": "object", "caption": "pending", "bbox": [0, 0, 1, 1]}]
        validate_draft(check)
        for item in draft["items"]:
            item.pop("id", None)
            if item["label"] != "text":
                item.pop("text", None)
    text = ("必须使用Layout模式，禁止使用caption模式。\n"
            f"当前画布宽度：{state['width']} px；高度：{state['height']} px。\n\n"
            + request + CANVAS_RULES)
    if locked:
        text += "\n本轮仅润色描述：禁止修改宽高、元素数量/顺序、label、bbox 和可见 text。\n"
    text += "\n[CURRENT_CANVAS_DATA]\n" + json.dumps(draft, ensure_ascii=False)
    return text, draft


class LayoutConversationAgent(PromptAgent):
    def _store_baseline(self, *args, **kwargs):
        # Layout sessions never read/write the ordinary Formatter's diff baseline.
        pass

    def _build_cold_run(self, user_text, image):
        messages, rounds, provided = super()._build_cold_run(user_text, image)
        messages[-1:-1] = deepcopy(self._layout_history)
        return messages, rounds, provided

    def _conversation_text(self, text):
        if not self._layout_history:
            return text
        return (text + "\n[PREVIOUS_CREATIVE_TURNS]\n"
                + json.dumps(self._layout_history, ensure_ascii=False)
                + "\n以上仅为创作历史，当前作品以本轮 CURRENT_CANVAS_DATA 为准。")

    def _assemble_low_output(self, tags, translations, user_text, user_tags, image):
        return super()._assemble_low_output(tags, translations,
            self._conversation_text(user_text), user_tags, image)

    def _fallback_normal(self, user_text, image):
        return super()._fallback_normal(self._conversation_text(user_text), image)
