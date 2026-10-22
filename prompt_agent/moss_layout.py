"""Editor transport and layout guards; coordinate compilation stays in MCP."""

from copy import deepcopy
import hashlib
import json
import math


LAYOUT_INSTRUCTION = """[MOSS_LAYOUT_INPUT]
以下 JSON 是用户在画布编辑器中确定的 Layout 草稿，必须输出 Layout，禁止改成 caption。
保留画布宽高、元素数量、顺序、类型、每个 bbox 和文字元素的 text（含标点和换行）。
只扩写 summary.caption 和各 items[].caption，保留原有主体与关键属性，统一整体画风。
补充要求与布局、数量、文字冲突时以布局 JSON 为准，并在 text_out 说明实际处理。
不要将编辑框、序号、坐标或内部说明画进图片；不要添加独立的布局元素。
保持原始像素 abs/xyxy 坐标，调用 compile_moss_prompt 编译完整草稿，不要自行转换坐标。
在 text_out 中注明实际画布尺寸，提醒生成工作流使用相同尺寸。
"""


def validate_draft(draft):
    """Validate user input before any remote request; return an independent copy."""
    if not isinstance(draft, dict):
        raise ValueError("Layout 必须是 JSON 对象")
    _check_fields(draft, {"width", "height", "bbox_coord_space", "bbox_format", "summary", "items"}, "Layout")
    for axis in ("width", "height"):
        n = draft.get(axis)
        if type(n) is not int or n <= 0 or n % 16:
            raise ValueError(f"画布 {axis} 必须是 16 的正整数倍")
    if draft.get("bbox_coord_space") != "abs" or draft.get("bbox_format") != "xyxy":
        raise ValueError("Layout 草稿必须使用原始像素 abs/xyxy 坐标")
    summary = draft.get("summary")
    if not isinstance(summary, dict) or not _nonempty(summary.get("caption")):
        raise ValueError("请填写全局描述")
    _check_fields(summary, {"caption", "meta", "canvas", "palette"}, "全局描述")
    if "canvas" in summary and summary["canvas"] not in ("single", "multi_panel", "collage"):
        raise ValueError("summary.canvas 必须为 single、multi_panel 或 collage")
    _check_arrays(summary, ("meta", "palette"), "全局描述")
    items = draft.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("请至少添加一个布局元素")
    for i, item in enumerate(items, 1):
        prefix = f"元素 {i}"
        if not isinstance(item, dict) or item.get("label") not in ("character", "object", "text"):
            raise ValueError(f"{prefix} 的类型必须为人物、物体或文字")
        _check_fields(item, {"id", "label", "caption", "bbox", "text", "tags", "palette"}, prefix)
        _check_arrays(item, ("tags", "palette"), prefix)
        if not _nonempty(item.get("caption")):
            raise ValueError(f"{prefix} 请填写描述")
        if item["label"] == "text" and not _nonempty(item.get("text")):
            raise ValueError(f"{prefix} 请填写实际可见文字")
        box = item.get("bbox")
        if (not isinstance(box, list) or len(box) != 4 or any(
                type(v) not in (int, float) or not math.isfinite(v) for v in box)):
            raise ValueError(f"{prefix} 的 bbox 必须包含四个有限数值")
        x1, y1, x2, y2 = box
        if not (0 <= x1 < x2 <= draft["width"] and 0 <= y1 < y2 <= draft["height"]):
            raise ValueError(f"{prefix} 的 bbox 越界或面积非正，请检查坐标")
    # Editor metadata must never enter a model-facing draft.
    clean = {key: deepcopy(draft[key]) for key in (
        "width", "height", "bbox_coord_space", "bbox_format", "summary", "items")}
    for item in clean["items"]:
        item.pop("id", None)
        if item["label"] != "text":
            item.pop("text", None)
    return clean


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _check_fields(value, allowed, prefix):
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{prefix} 含不支持的字段：" + ", ".join(sorted(map(str, unknown))))


def _check_arrays(value, fields, prefix):
    for field in fields:
        if field in value and (not isinstance(value[field], list) or any(not isinstance(v, str) for v in value[field])):
            raise ValueError(f"{prefix} 的 {field} 必须为字符串数组")


def prepare_layout(layout, mode):
    if mode != "MOSS":
        raise ValueError("连接 layout 时，请将 Formatter 的 mode 设置为 MOSS")
    if not isinstance(layout, dict) or type(layout.get("strict_validation", True)) is not bool:
        raise ValueError("无效的 MOSS_LAYOUT 输入")
    return {"draft": validate_draft(layout.get("draft")),
            "strict_validation": layout.get("strict_validation", True)}


def layout_fingerprint(layout):
    if layout is None:
        return None
    raw = json.dumps(layout, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def append_layout_input(user_text, layout):
    # Validation policy deliberately does not appear in LLM messages.
    return (user_text + "\n\n" + LAYOUT_INSTRUCTION +
            json.dumps(layout["draft"], ensure_ascii=False, allow_nan=False))


def layout_search_text(user_text, layout):
    """Search visual descriptions, not JSON field names or numeric coordinates."""
    marker = "\n\n[MOSS_LAYOUT_INPUT]\n"
    if layout is None or marker not in user_text:
        return user_text
    original = user_text.rsplit(marker, 1)[0]
    draft = layout["draft"]
    return "\n".join([original, draft["summary"]["caption"],
                      *(item["caption"] for item in draft["items"])])


def guard_compilation(layout, candidate):
    """Strict policy checks consistency; loose policy still requires valid Layout."""
    clean = validate_draft(candidate)
    if not layout["strict_validation"]:
        return clean
    original = layout["draft"]
    for key in ("width", "height"):
        if clean[key] != original[key]:
            raise ValueError(f"布局锁定：不得修改 {key}；请使用用户原始布局，仅扩写描述")
    if len(clean["items"]) != len(original["items"]):
        raise ValueError("布局锁定：不得增加或减少元素，请恢复原始元素数量和顺序")
    for i, (before, after) in enumerate(zip(original["items"], clean["items"]), 1):
        for key in ("label", "bbox", "text"):
            if before.get(key) != after.get(key):
                raise ValueError(f"布局锁定：元素 {i} 的 {key} 已改变，请恢复原值，仅扩写 caption")
    return clean
