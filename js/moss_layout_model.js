// Pure editor operations. Pixel coordinates are never converted to model space here.
export const TYPES = { object: "物体", character: "人物", text: "文字" };
export const clone = (value) => JSON.parse(JSON.stringify(value));
export const validDimension = (n) => Number.isSafeInteger(n) && n > 0 && n % 16 === 0;
export const newId = () => globalThis.crypto?.randomUUID?.() ?? `box-${Date.now()}-${Math.random().toString(36).slice(2)}`;
export const emptyState = () => ({ version: 1, width: 1024, height: 1024, summary: "", items: [], strict_validation: true });

export function stateToDraft(state) {
  return { width: state.width, height: state.height, bbox_coord_space: "abs", bbox_format: "xyxy",
    summary: { ...(state.summary_extra ?? {}), caption: state.summary },
    items: state.items.map(({ id, text, ...item }) => item.label === "text" ? { ...item, text } : item) };
}
const canonical = (value) => Array.isArray(value) ? value.map(canonical) : value && typeof value === "object" ?
  Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
export const contentKey = (state) => JSON.stringify(canonical(stateToDraft(state)));
export const requestKey = (state) => JSON.stringify([contentKey(state), state.strict_validation, state.agent]);

export function applyLayoutResult(state, result) {
  const { draft, output } = result;
  if (!output || typeof output.prompt !== "string" || !output.prompt.trim() || typeof output.text_out !== "string") {
    throw new Error("Agent 编译结果为空或格式无法读取");
  }
  if (!draft || draft.bbox_coord_space !== "abs" || draft.bbox_format !== "xyxy" ||
      !validDimension(draft.width) || !validDimension(draft.height) || !draft.summary ||
      typeof draft.summary.caption !== "string" || !Array.isArray(draft.items)) throw new Error("Agent 布局格式无法读取");
  const { caption, ...extra } = draft.summary;
  const next = readState(JSON.stringify({ ...state, width: draft.width, height: draft.height,
    canvas_size: [draft.width, draft.height], summary: caption, summary_extra: extra,
    items: draft.items.map(item => ({ ...item, id: newId() })), task: null }));
  if (errorsFor(next).length) throw new Error("Agent 布局存在无效元素");
  next.output = { ...output, source_key: contentKey(next) };
  return next;
}

export function readState(raw) {
  const state = JSON.parse(raw);
  if (!state || state.version !== 1 || !Array.isArray(state.items) || typeof state.summary !== "string" ||
      typeof state.strict_validation !== "boolean" || !("width" in state) || !("height" in state)) {
    throw new Error("布局状态版本或字段无法读取，请恢复正确的工作流，或手动重置编辑器。");
  }
  const ids = new Set();
  if (state.canvas_size !== undefined && (!Array.isArray(state.canvas_size) || state.canvas_size.length !== 2 || !state.canvas_size.every(validDimension))) {
    throw new Error("布局保存的画布尺寸无法读取。");
  }
  for (const item of state.items) {
    if (!item || !TYPES[item.label] || typeof item.caption !== "string" ||
        !Array.isArray(item.bbox) || item.bbox.length !== 4 ||
        item.bbox.some((n) => n !== null && (typeof n !== "number" || !Number.isFinite(n))) ||
        (item.text !== undefined && typeof item.text !== "string")) throw new Error("布局元素状态无法读取。");
    if (typeof item.id !== "string" || ids.has(item.id)) item.id = newId();
    ids.add(item.id);
  }
  return state;
}

export function validBox(box, width, height) {
  return Array.isArray(box) && box.length === 4 && box.every(Number.isFinite) &&
    box[0] >= 0 && box[1] >= 0 && box[0] < box[2] && box[1] < box[3] && box[2] <= width && box[3] <= height;
}

export function errorsFor(state) {
  const errors = [];
  if (!validDimension(state.width) || !validDimension(state.height)) errors.push("宽高必须是 16 的正整数倍。");
  if (!state.summary.trim()) errors.push("请填写全局描述。");
  if (!state.items.length) errors.push("在画布拖拽画框，或点击“坐标新增”。");
  state.items.forEach((item, i) => {
    if (!validBox(item.bbox, state.width, state.height)) errors.push(`元素 ${i + 1} 的坐标越界或面积非正。`);
    if (!item.caption.trim()) errors.push(`元素 ${i + 1} 请填写描述。`);
    if (item.label === "text" && !item.text?.trim()) errors.push(`元素 ${i + 1} 请填写实际可见文字。`);
  });
  return errors;
}

export function resizeCanvas(state, previousWidth, previousHeight) {
  if (!validDimension(state.width) || !validDimension(state.height)) return false;
  for (const item of state.items) {
    item.bbox = item.bbox.map((n, i) => n === null ? null : n * (i % 2 ? state.height / previousHeight : state.width / previousWidth));
  }
  return true;
}

export function arrange(state, selected, action) {
  const items = state.items.filter((item) => selected.has(item.id));
  if (items.length < 2 || items.some((item) => !validBox(item.bbox, state.width, state.height))) return false;
  if (["left", "center", "right"].includes(action)) {
    const left = Math.min(...items.map((item) => item.bbox[0]));
    const right = Math.max(...items.map((item) => item.bbox[2]));
    for (const item of items) {
      const width = item.bbox[2] - item.bbox[0];
      const x = action === "left" ? left : action === "right" ? right - width : (left + right - width) / 2;
      item.bbox[0] = x; item.bbox[2] = x + width;
    }
  } else {
    if (items.length < 3 || !["horizontal", "vertical"].includes(action)) return false;
    const axis = action === "horizontal" ? 0 : 1;
    items.sort((a, b) => a.bbox[axis] - b.bbox[axis]);
    const start = Math.min(...items.map((item) => item.bbox[axis]));
    const end = Math.max(...items.map((item) => item.bbox[axis + 2]));
    const total = items.reduce((sum, item) => sum + item.bbox[axis + 2] - item.bbox[axis], 0);
    if (total > end - start) return false;
    const gap = (end - start - total) / (items.length - 1);
    let cursor = start;
    for (const item of items) {
      const size = item.bbox[axis + 2] - item.bbox[axis];
      item.bbox[axis] = cursor; item.bbox[axis + 2] = cursor + size;
      cursor += size + gap;
    }
  }
  return true;
}

export class History {
  constructor(limit = 50) { this.limit = limit; this.undoStack = []; this.redoStack = []; this.lastKey = null; this.lastTime = 0; }
  push(before, after, key = null) {
    if (before === after) return;
    const now = Date.now();
    if (!key || key !== this.lastKey || now - this.lastTime > 650) {
      this.undoStack.push(before);
      if (this.undoStack.length > this.limit) this.undoStack.shift();
    }
    this.redoStack = []; this.lastKey = key; this.lastTime = now;
  }
  undo(current) {
    if (!this.undoStack.length) return null;
    this.redoStack.push(current); this.lastKey = null;
    return this.undoStack.pop();
  }
  redo(current) {
    if (!this.redoStack.length) return null;
    this.undoStack.push(current); this.lastKey = null;
    return this.redoStack.pop();
  }
}
