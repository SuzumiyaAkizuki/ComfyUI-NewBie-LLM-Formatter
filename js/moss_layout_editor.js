import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { createAgentPanel } from "./moss_layout_agent.js";
import { migrateLayoutGraph } from "./moss_layout_ports.js";
import { TYPES, emptyState, readState, validDimension, validBox, errorsFor, resizeCanvas, arrange, History, newId, applyLayoutResult, contentKey } from "./moss_layout_model.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const COLORS = { object: "#ecc078", character: "#91c6fa", text: "#a7d5ac" };
const css = `
.moss-editor { color:var(--fg-color,#e4e4e7); background:var(--comfy-menu-bg,#242428); font:13px/1.45 system-ui,sans-serif; padding:12px; box-sizing:border-box; width:100%; height:100%; min-width:0; min-height:0; overflow:hidden; color-scheme:dark; container-type:inline-size; }
.moss-editor * { box-sizing:border-box; }
.moss-body { display:flex; flex-direction:column; height:100%; min-height:0; }
.moss-workspace { display:grid; grid-template-columns:minmax(0,1fr) 16px clamp(230px,30%,360px); flex:1; min-height:0; min-width:0; }
.moss-canvas-pane { display:flex; flex-direction:column; min-height:0; min-width:0; }
.moss-stage-wrap { display:flex; flex:1; min-height:0; min-width:0; overflow:hidden; position:relative; }
.moss-runtime-log { position:absolute; inset:0; z-index:1; padding:16px; display:flex; flex-direction:column; background:var(--comfy-menu-bg,#242428); border:1px solid var(--border-color,#626269); }
.moss-runtime-log h3 { margin:0 0 12px; font:600 14px/1.5 system-ui,sans-serif; }
.moss-runtime-log pre { margin:0; flex:1; min-height:0; overflow:auto; white-space:pre-wrap; overflow-wrap:anywhere; font:13px/1.65 system-ui,sans-serif; color:var(--fg-color,#e4e4e7); user-select:text; scrollbar-width:thin; }
.moss-inspector { min-height:0; min-width:0; overflow:auto; overscroll-behavior:contain; padding-left:8px; padding-right:4px; scrollbar-width:thin; scrollbar-color:var(--border-color,#626269) transparent; }
.moss-splitter { cursor:col-resize; position:relative; touch-action:none; user-select:none; border-radius:3px; }
.moss-splitter::before { content:""; position:absolute; top:0; bottom:0; width:1px; left:50%; background:var(--border-color,#626269); }
.moss-splitter::after { content:""; position:absolute; top:calc(50% - 14px); left:calc(50% - 2px); width:5px; height:28px; border-left:1px solid #b9bac1; border-right:1px solid #b9bac1; }
.moss-splitter:hover::before,.moss-splitter[data-dragging=true]::before { background:#91c6fa; width:2px; }
.moss-splitter:focus-visible { outline:2px solid #91c6fa; outline-offset:-2px; }
.moss-section-title { font-weight:600; margin:0 0 8px; }
.moss-selection-hint { margin:12px 0; color:var(--descrip-text,#b9bac1); }
.moss-editor button,.moss-editor input,.moss-editor select,.moss-editor textarea { font:inherit; color:var(--input-text,#eee); background:var(--comfy-input-bg,#34343a); border:1px solid var(--border-color,#626269); border-radius:4px; padding:6px 8px; min-height:32px; }
.moss-editor button { cursor:pointer; white-space:nowrap; }
.moss-editor button:hover:not(:disabled) { border-color:#91c6fa; }
.moss-editor button:disabled { opacity:.45; cursor:default; }
.moss-editor :is(button,input,select,textarea):focus-visible { outline:2px solid #91c6fa; outline-offset:2px; }
.moss-editor ::selection { background:#355d83; color:#fff; }
.moss-editor textarea { display:block; width:100%; height:auto; min-height:64px; resize:vertical; caret-color:#91c6fa; }
.moss-editor input[type=number] { width:100%; font-variant-numeric:tabular-nums; }
.moss-editor input[type=checkbox] { min-height:0; width:16px; height:16px; accent-color:#91c6fa; margin:0; }
.moss-editor label { display:flex; flex-direction:column; gap:4px; }
.moss-row { display:flex; align-items:center; flex-wrap:wrap; gap:6px; }
.moss-top { justify-content:space-between; margin-bottom:12px; flex-shrink:0; }
.moss-title { font-size:15px; font-weight:650; }
.moss-dimensions { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.moss-note { color:var(--descrip-text,#b9bac1); font-size:12px; margin:6px 0 10px; }
.moss-summary { margin-bottom:12px; }
.moss-toolbar { margin:0 0 8px; flex-shrink:0; }
.moss-editor button[aria-pressed=true] { background:#355471; border-color:#91c6fa; color:#fff; }
.moss-stage { background:#18181b; border:1px solid var(--border-color,#626269); height:100%; width:100%; min-height:0; min-width:0; display:block; touch-action:none; user-select:none; }
.moss-stage[data-mode=draw] { cursor:crosshair; }
.moss-stage rect[data-id] { cursor:move; }
.moss-stage rect[data-handle] { cursor:nwse-resize; }
.moss-stage rect[data-handle=ne],.moss-stage rect[data-handle=sw] { cursor:nesw-resize; }
.moss-arrange { margin:0; flex-shrink:0; }
.moss-arrange button { font-size:12px; padding:5px 7px; }
.moss-list { display:flex; flex-direction:column; gap:4px; max-height:180px; overflow:auto; margin-bottom:12px; scrollbar-width:thin; }
.moss-list-row { display:flex; gap:8px; align-items:center; padding:4px 6px; border:1px solid transparent; border-radius:4px; }
.moss-list-row[data-selected=true] { border-color:#91c6fa; background:rgba(80,135,186,.15); }
.moss-list-row button { flex:1; text-align:left; overflow:hidden; text-overflow:ellipsis; border:0; background:none; min-width:0; }
.moss-properties { border-top:1px solid var(--border-color,#626269); padding-top:12px; display:flex; flex-direction:column; gap:10px; }
.moss-coords { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:8px; }
.moss-property-title { font-weight:600; }
.moss-properties textarea[aria-label="区域描述"] { min-height:140px; }
.moss-footer { margin-top:12px; border-top:1px solid var(--border-color,#626269); padding-top:10px; }
.moss-editor .moss-check { display:flex; flex-direction:row; align-items:center; gap:8px; }
.moss-status { margin-top:8px; font-size:12px; color:var(--descrip-text,#b9bac1); white-space:pre-line; }
.moss-status[data-error=true],.moss-restore { color:#ffb4ab; }
.moss-coordinate-add { margin:10px 0; padding:10px 0; border-bottom:1px solid var(--border-color,#626269); }
@container (max-width:760px) { .moss-editor button { padding:5px 6px; } }
.moss-editor [hidden] { display:none !important; }
.moss-agent { border-bottom:1px solid var(--border-color,#626269); margin-bottom:16px; padding-bottom:12px; display:flex; flex-direction:column; gap:8px; }
.moss-agent details { border:1px solid var(--border-color,#626269); border-radius:4px; padding:8px; }
.moss-agent details > label { margin-top:8px; }
.moss-agent summary { cursor:pointer; }
.moss-editor .moss-agent-toggle { display:flex; align-items:center; justify-content:center; width:32px; height:32px; padding:5px; }
.moss-agent-toggle[data-busy=true] { border-color:#91c6fa; color:#cbe5ff; }
.moss-agent-settings { position:relative; z-index:5; }
.moss-agent-settings > summary { display:flex; align-items:center; justify-content:center; width:32px; height:32px; padding:5px; border:1px solid var(--border-color,#626269); border-radius:4px; background:var(--comfy-input-bg,#34343a); cursor:pointer; list-style:none; }
.moss-agent-settings > summary::-webkit-details-marker { display:none; }
.moss-agent-settings > summary:hover,.moss-agent-settings[open] > summary { border-color:#91c6fa; }
.moss-agent-settings > summary:focus-visible { outline:2px solid #91c6fa; outline-offset:2px; }
.moss-settings-content { position:absolute; right:0; top:calc(100% + 8px); width:300px; max-width:calc(100cqw - 32px); max-height:340px; overflow:auto; display:flex; flex-direction:column; gap:10px; padding:14px; border-radius:4px; background:var(--comfy-menu-bg,#242428); box-shadow:0 8px 24px rgba(0,0,0,.4); transform-origin:top right; }
.moss-settings-content select { width:100%; }
.moss-agent-run { display:inline-flex; gap:8px; align-items:center; justify-content:center; }
.moss-editor .moss-agent-run[aria-busy=true] { opacity:1; color:#cbe5ff; border-color:#91c6fa; cursor:wait; }
.moss-agent-spinner { width:14px; height:14px; border:2px solid currentColor; border-right-color:transparent; border-radius:50%; animation:moss-agent-spin .8s linear infinite; flex-shrink:0; }
@keyframes moss-agent-spin { to { transform:rotate(360deg); } }
@media (prefers-reduced-motion:reduce) { .moss-agent-spinner { animation:none; } }
.moss-editor[data-busy=true] .moss-stage { pointer-events:none; opacity:.75; }
`;

function element(tag, attrs = {}, text = null) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") el.className = value;
    else el.setAttribute(key, value);
  }
  if (text !== null) el.textContent = text;
  return el;
}
function svgElement(tag, attrs, text = null) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
  if (text !== null) el.textContent = text;
  return el;
}
function field(parent, title, control) {
  control.setAttribute("aria-label", title);
  const label = element("label", {}, title); label.append(control); parent.append(label); return control;
}
function button(parent, text, callback, attrs = {}) {
  const control = element("button", { type: "button", ...attrs }, text);
  control.addEventListener("click", callback); parent.append(control); return control;
}

export function createLayoutEditor(raw, onChange, options = {}) {
  let state = emptyState();
  let selected = new Set();
  let primary = null;
  let mode = "draw";
  let gesture = null;
  let restoreError = "";
  let notice = "";
  let dims = [1024, 1024];
  let agentPanel = null;
  const history = new History();
  const root = element("div", { class: "moss-editor" });
  const style = element("style"); style.textContent = css; root.append(style);
  const recovery = element("div", { class: "moss-restore", hidden: "" }); root.append(recovery);
  const body = element("div", { class: "moss-body" }); root.append(body);
  const top = element("div", { class: "moss-row moss-top" }); body.append(top);
  top.append(element("span", { class: "moss-title" }, "MOSS 布局画布"));
  const historyBar = element("div", { class: "moss-row" }); top.append(historyBar);
  const undoButton = button(historyBar, "撤销", () => travel(false), { title: "撤销上一次编辑" });
  const redoButton = button(historyBar, "重做", () => travel(true), { title: "重做上一次撤销" });
  const dimensions = element("div", { class: "moss-dimensions" }); body.append(dimensions);
  const width = field(dimensions, "画布宽度 / px", element("input", { type: "number", min: 16, step: 16 }));
  const height = field(dimensions, "画布高度 / px", element("input", { type: "number", min: 16, step: 16 }));
  const dimensionNote = element("p", { class: "moss-note" }, "宽高为 16 的倍数。修改尺寸时，已有框按比例缩放。"); body.append(dimensionNote);
  const summary = field(body, "全局描述", element("textarea", { class: "moss-summary", placeholder: "整体场景、画风、背景、光照与主体关系…", rows: 3 }));
  const toolbar = element("div", { class: "moss-row moss-toolbar" }); body.append(toolbar);
  const selectButton = button(toolbar, "选择 / 移动", () => { mode = "select"; render(); });
  const drawButton = button(toolbar, "画框", () => { mode = "draw"; render(); });
  button(toolbar, "坐标新增", () => { addPanel.hidden = !addPanel.hidden; });
  const addPanel = element("div", { class: "moss-coordinate-add", hidden: "" }); body.append(addPanel);
  const addCoords = element("div", { class: "moss-coords" }); addPanel.append(addCoords);
  const newCoordinates = ["x_min", "y_min", "x_max", "y_max"].map((label, i) => {
    const input = field(addCoords, label, element("input", { type: "number", step: "any" }));
    input.value = [0, 0, 256, 256][i]; return input;
  });
  button(addPanel, "添加矩形", () => {
    const bbox = newCoordinates.map(numeric);
    if (!validBox(bbox, state.width, state.height)) { notice = "新元素坐标越界或面积非正，请修改后添加。"; renderStatus(); return; }
    change(() => addItem(bbox)); addPanel.hidden = true;
  });
  const svg = svgElement("svg", { class: "moss-stage", role: "img", "aria-label": "MOSS 布局画布；可拖拽画框，使用下方列表和坐标输入精确编辑", tabindex: 0 }); body.append(svg);
  const canvasNote = element("p", { class: "moss-note" }, "Shift + 点击可多选；也可勾选右侧列表。边框仅用于编辑。"); body.append(canvasNote);
  const arrangeBar = element("div", { class: "moss-row moss-arrange" }); body.append(arrangeBar);
  const arrangementButtons = [];
  for (const [action, title] of [["left", "左对齐"], ["center", "水平居中"], ["right", "右对齐"], ["horizontal", "水平均布"], ["vertical", "竖直均布"]]) {
    arrangementButtons.push([button(arrangeBar, title, () => change(() => {
      if (!arrange(state, selected, action)) notice = "所选框的均布空间不足，请调整框尺寸或位置后重试。";
    }), { title: ["horizontal", "vertical"].includes(action) ? "选中至少三个元素，按外沿范围均分间距；需要足够空间" : "选中至少两个元素，按所选框的整体范围对齐" }), action]);
  }
  const list = element("div", { class: "moss-list", "aria-label": "布局元素" }); body.append(list);
  const properties = element("div", { class: "moss-properties" }); body.append(properties);
  const propertyTitle = element("div", { class: "moss-property-title" }); properties.append(propertyTitle);
  const type = field(properties, "元素类型", element("select"));
  for (const [value, title] of Object.entries(TYPES)) type.append(element("option", { value }, title));
  const caption = field(properties, "区域描述", element("textarea", { placeholder: "描述此框内的主体、外观、动作或文字样式…", rows: 3 }));
  const text = field(properties, "实际可见文字（原样保留）", element("textarea", { placeholder: "需要实际画出的文字，支持换行", rows: 2 }));
  const coords = element("div", { class: "moss-coords" }); properties.append(coords);
  const coordinateInputs = ["x_min", "y_min", "x_max", "y_max"].map((name) => field(coords, name, element("input", { type: "number", step: "any" })));
  const remove = button(properties, "删除当前元素", () => change(() => {
    state.items = state.items.filter((item) => item.id !== primary); selected.delete(primary); primary = [...selected].at(-1) ?? null;
  }));
  const footer = element("div", { class: "moss-footer" }); body.append(footer);
  const strict = field(footer, "严格校验布局", element("input", { type: "checkbox" })); strict.parentElement.className = "moss-check";
  footer.append(element("p", { class: "moss-note" }, "关闭后跳过 LLM 返回布局的一致性检查；输入合法性与 MOSS 编译仍会校验。"));
  const status = element("div", { class: "moss-status", role: "status", "aria-live": "polite" }); footer.append(status);

  const workspace = element("div", { class: "moss-workspace" });
  const canvasPane = element("section", { class: "moss-canvas-pane", "aria-label": "画布与布局工具" });
  const stageWrap = element("div", { class: "moss-stage-wrap" }); stageWrap.append(svg);
  const runtimeLog = element("section", { class:"moss-runtime-log", hidden:"", "aria-label":"Agent 运行日志" });
  runtimeLog.append(element("h3", {}, "Agent 运行过程"));
  const runtimeText = element("pre", { tabindex:0, "aria-label":"模型思考与工具调用记录" }); runtimeLog.append(runtimeText); stageWrap.append(runtimeLog);
  canvasPane.append(toolbar, stageWrap, canvasNote, arrangeBar);
  const inspector = element("section", { class: "moss-inspector", "aria-label": "布局与元素编辑" });
  const selectionHint = element("p", { class: "moss-selection-hint" }, "选择画布中的框或下方元素，编辑区域描述与坐标。");
  inspector.append(dimensions, dimensionNote, summary.parentElement, addPanel,
    element("div", { class: "moss-section-title" }, "元素列表"), list, selectionHint, properties, footer);
  const splitter = element("div", { class:"moss-splitter", role:"separator", tabindex:0, "aria-label":"调整右侧编辑栏宽度", "aria-orientation":"vertical", title:"左右拖动调整栏宽；方向键微调" });
  workspace.append(canvasPane, splitter, inspector); body.append(workspace);
  let splitDrag = null;
  function splitBounds() {
    const available = workspace.clientWidth - 16;
    return { available, min:Math.min(230, available * .45), max:Math.max(Math.min(230, available * .45), available - 260) };
  }
  function layoutSplit(requested = null) {
    const { available, min, max } = splitBounds(); if (available <= 0) return;
    const ratio = Number.isFinite(state.ui?.inspector_ratio) ? state.ui.inspector_ratio : .3;
    const size = Math.max(min, Math.min(max, requested ?? available * ratio));
    workspace.style.gridTemplateColumns = `minmax(0,1fr) 16px ${size}px`;
    splitter.setAttribute("aria-valuemin", Math.round(100 * min / available));
    splitter.setAttribute("aria-valuemax", Math.round(100 * max / available));
    splitter.setAttribute("aria-valuenow", Math.round(100 * size / available));
    splitter.setAttribute("aria-valuetext", `右栏宽度 ${Math.round(size)} 像素`);
    return size;
  }
  function resizeSplit(size) {
    const actual = layoutSplit(size); if (actual === undefined) return;
    state.ui = { ...state.ui, inspector_ratio:actual / splitBounds().available };
  }
  splitter.addEventListener("pointerdown", event => {
    if (event.button !== 0 || restoreError) return;
    event.preventDefault(); event.stopPropagation(); splitter.focus();
    const rect = workspace.getBoundingClientRect();
    splitDrag = { x:event.clientX, size:inspector.getBoundingClientRect().width * workspace.clientWidth / rect.width,
      scale:workspace.clientWidth / rect.width, before:state.ui ? JSON.parse(JSON.stringify(state.ui)) : undefined };
    splitter.dataset.dragging = "true"; splitter.setPointerCapture(event.pointerId);
  });
  splitter.addEventListener("pointermove", event => {
    if (!splitDrag) return;
    event.preventDefault(); resizeSplit(splitDrag.size + (splitDrag.x - event.clientX) * splitDrag.scale);
  });
  function finishSplit(event, cancel = false) {
    if (!splitDrag) return;
    if (cancel) { if (splitDrag.before === undefined) delete state.ui; else state.ui = splitDrag.before; layoutSplit(); }
    splitDrag = null; delete splitter.dataset.dragging; notify();
    if (splitter.hasPointerCapture(event.pointerId)) splitter.releasePointerCapture(event.pointerId);
  }
  splitter.addEventListener("pointerup", event => finishSplit(event));
  splitter.addEventListener("pointercancel", event => finishSplit(event, true));
  splitter.addEventListener("lostpointercapture", event => finishSplit(event, true));
  splitter.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    const { min, max } = splitBounds(); const step = event.shiftKey ? 32 : 16;
    const currentSize = layoutSplit();
    resizeSplit(event.key === "Home" ? min : event.key === "End" ? max : currentSize + (event.key === "ArrowLeft" ? step : -step));
    notify();
  });

  function numeric(input) { return input.value.trim() === "" || !Number.isFinite(Number(input.value)) ? null : Number(input.value); }
  function serialize() { return JSON.stringify(state); }
  function notify() { if (!restoreError) onChange(serialize()); }
  function change(update, key = null) {
    if (agentPanel?.busy() && key !== "task") return;
    const before = serialize(); notice = ""; update();
    if (key !== "task") history.push(before, serialize(), key);
    if (key === "task" || before !== serialize()) notify(); render();
  }
  function addItem(bbox) {
    const item = { id: newId(), label: "object", caption: "", text: "", bbox };
    state.items.push(item); selected = new Set([item.id]); primary = item.id; mode = "select";
  }
  function pick(id, multiple = false) {
    if (!multiple) selected = new Set([id]);
    else if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    primary = selected.has(id) ? id : [...selected].at(-1) ?? null;
    render();
  }
  function current() { return state.items.find((item) => item.id === primary); }
  function setValue(control, value) {
    const next = value ?? "";
    if (String(control.value) !== String(next)) control.value = next;
  }
  function setCoordinate(control, value) {
    if (document.activeElement !== control) setValue(control, Number.isFinite(value) ? Number(value.toFixed(3)) : value);
  }
  function travel(redo) {
    if (gesture || agentPanel?.busy()) return;
    const rawState = redo ? history.redo(serialize()) : history.undo(serialize());
    if (rawState === null) return;
    state = readState(rawState); dims = validDimension(state.width) && validDimension(state.height) ? [state.width, state.height] : state.canvas_size ?? dims;
    selected = new Set([...selected].filter((id) => state.items.some((item) => item.id === id)));
    primary = selected.has(primary) ? primary : [...selected].at(-1) ?? null;
    notice = ""; notify(); render();
  }
  function dimensionChanged() {
    change(() => {
      state.width = numeric(width); state.height = numeric(height);
      if (resizeCanvas(state, ...dims)) dims = [state.width, state.height];
      state.canvas_size = [...dims];
    }, "dimensions");
  }
  width.addEventListener("input", dimensionChanged); height.addEventListener("input", dimensionChanged);
  summary.addEventListener("input", () => change(() => { state.summary = summary.value; }, "summary"));
  strict.addEventListener("change", () => change(() => { state.strict_validation = strict.checked; }));
  type.addEventListener("change", () => change(() => { if (current()) current().label = type.value; }));
  caption.addEventListener("input", () => change(() => { if (current()) current().caption = caption.value; }, `caption-${primary}`));
  text.addEventListener("input", () => change(() => { if (current()) current().text = text.value; }, `text-${primary}`));
  coordinateInputs.forEach((input, index) => input.addEventListener("input", () => change(() => {
    if (current()) current().bbox[index] = numeric(input);
  }, `bbox-${primary}-${index}`)));

  function renderStatus() {
    const errors = errorsFor(state);
    status.textContent = notice || (errors.length ? errors.slice(0, 4).join("\n") + (errors.length > 4 ? `\n另有 ${errors.length - 4} 项待完善。` : "") : `${state.items.length} 个元素 · ${state.width} × ${state.height} · layout_prompr 可连接 Formatter 的 layout 或直接用于 MOSS`);
    status.dataset.error = String(Boolean(notice || errors.length));
  }
  function draw() {
    svg.setAttribute("viewBox", `0 0 ${dims[0]} ${dims[1]}`); svg.dataset.mode = mode;
    svg.replaceChildren(svgElement("rect", { x: 0, y: 0, width: dims[0], height: dims[1], fill: "#25262b" }));
    const unit = Math.max(dims[0] / Math.max(svg.clientWidth, 1), dims[1] / Math.max(svg.clientHeight, 1));
    state.items.forEach((item, index) => {
      if (!validBox(item.bbox, ...dims)) return;
      const [x1, y1, x2, y2] = item.bbox;
      const color = COLORS[item.label]; const active = selected.has(item.id);
      svg.append(svgElement("rect", { x: x1, y: y1, width: x2 - x1, height: y2 - y1,
        fill: color, "fill-opacity": active ? .16 : .06, stroke: color, "stroke-width": active ? 2 : 1,
        "vector-effect": "non-scaling-stroke", "data-id": item.id }));
      svg.append(svgElement("text", { x: x1 + 4 * unit, y: Math.min(y2, y1 + 17 * unit),
        fill: color, "font-size": 12 * unit, "font-family": "system-ui,sans-serif", "pointer-events": "none" }, `${index + 1} ${TYPES[item.label]}`));
      if (active && selected.size === 1 && mode === "select") {
        for (const [corner, x, y] of [["nw", x1, y1], ["ne", x2, y1], ["sw", x1, y2], ["se", x2, y2]]) {
          svg.append(svgElement("rect", { x: x - 4 * unit, y: y - 4 * unit, width: 8 * unit, height: 8 * unit,
            fill: color, stroke: "#18181b", "stroke-width": 1, "vector-effect": "non-scaling-stroke", "data-id": item.id, "data-handle": corner }));
        }
      }
    });
    if (gesture?.kind === "draw") {
      const [x1, y1] = gesture.start; const [x2, y2] = gesture.end;
      svg.append(svgElement("rect", { x: Math.min(x1, x2), y: Math.min(y1, y2), width: Math.abs(x2 - x1), height: Math.abs(y2 - y1),
        fill: "#91c6fa", "fill-opacity": .12, stroke: "#91c6fa", "stroke-dasharray": "5 3", "vector-effect": "non-scaling-stroke", "pointer-events": "none" }));
    }
  }
  function render() {
    layoutSplit();
    setValue(width, state.width); setValue(height, state.height); setValue(summary, state.summary); strict.checked = state.strict_validation;
    selectButton.setAttribute("aria-pressed", String(mode === "select")); drawButton.setAttribute("aria-pressed", String(mode === "draw"));
    undoButton.disabled = !history.undoStack.length; redoButton.disabled = !history.redoStack.length;
    for (const [control, action] of arrangementButtons) control.disabled = selected.size < (["horizontal", "vertical"].includes(action) ? 3 : 2) || state.items.some(item => selected.has(item.id) && !validBox(item.bbox, ...dims));
    const activeListId = list.contains(document.activeElement) ? document.activeElement?.dataset?.focusId : null;
    list.replaceChildren();
    state.items.forEach((item, index) => {
      const row = element("div", { class: "moss-list-row", "data-selected": String(selected.has(item.id)) });
      const check = element("input", { type: "checkbox", "aria-label": `选择元素 ${index + 1}`, "data-focus-id": item.id }); check.checked = selected.has(item.id);
      check.addEventListener("change", () => pick(item.id, true)); row.append(check);
      button(row, `${index + 1} · ${TYPES[item.label]} · ${item.caption || "待填写描述"}`, (event) => pick(item.id, event.shiftKey), { title: item.caption || "待填写描述", "aria-pressed": String(selected.has(item.id)) });
      list.append(row);
    });
    if (activeListId) list.querySelector(`[data-focus-id="${CSS.escape(activeListId)}"]`)?.focus({ preventScroll: true });
    const item = current(); properties.hidden = !item; selectionHint.hidden = Boolean(item);
    if (item) {
      propertyTitle.textContent = `元素 ${state.items.indexOf(item) + 1}${selected.size > 1 ? ` · 已选 ${selected.size} 个，属性仅修改当前元素` : ""}`;
      setValue(type, item.label); setValue(caption, item.caption); setValue(text, item.text || ""); text.parentElement.hidden = item.label !== "text";
      coordinateInputs.forEach((control, index) => setCoordinate(control, item.bbox[index])); remove.disabled = false;
    }
    draw(); renderStatus(); agentPanel?.refresh();
  }

  function point(event) {
    const p = svg.createSVGPoint(); p.x = event.clientX; p.y = event.clientY;
    const transform = svg.getScreenCTM();
    if (!transform) return [0, 0];
    const q = p.matrixTransform(transform.inverse());
    return [Math.max(0, Math.min(dims[0], q.x)), Math.max(0, Math.min(dims[1], q.y))];
  }
  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || restoreError || agentPanel?.busy()) return;
    event.preventDefault(); event.stopPropagation();
    if (!validDimension(state.width) || !validDimension(state.height)) { notice = "请先修正画布宽高。"; renderStatus(); return; }
    const start = point(event); const id = event.target.dataset.id; const handle = event.target.dataset.handle;
    if (mode === "draw") gesture = { kind: "draw", start, end: start, before: serialize() };
    else if (id) {
      if (event.shiftKey) { pick(id, true); return; }
      if (!selected.has(id)) pick(id);
      else { primary = id; render(); }
      if (state.items.some(item => selected.has(item.id) && !validBox(item.bbox, ...dims))) return;
      gesture = { kind: handle ? "resize" : "move", handle,
        start, before: serialize(), boxes: state.items.filter(item => selected.has(item.id)).map(item => ({ id: item.id, bbox: [...item.bbox] })) };
    } else { selected.clear(); primary = null; render(); return; }
    svg.setPointerCapture(event.pointerId);
  });
  svg.addEventListener("pointermove", (event) => {
    if (!gesture) return;
    event.preventDefault(); const end = point(event);
    if (gesture.kind === "draw") { gesture.end = end; draw(); return; }
    const [sx, sy] = gesture.start;
    if (gesture.kind === "move") {
      const minX = Math.min(...gesture.boxes.map(item => item.bbox[0])); const maxX = Math.max(...gesture.boxes.map(item => item.bbox[2]));
      const minY = Math.min(...gesture.boxes.map(item => item.bbox[1])); const maxY = Math.max(...gesture.boxes.map(item => item.bbox[3]));
      const dx = Math.max(-minX, Math.min(dims[0] - maxX, end[0] - sx)); const dy = Math.max(-minY, Math.min(dims[1] - maxY, end[1] - sy));
      for (const original of gesture.boxes) state.items.find(item => item.id === original.id).bbox = original.bbox.map((n, i) => n + (i % 2 ? dy : dx));
    } else {
      const original = gesture.boxes[0].bbox; const box = [...original];
      const minWidth = Math.min(1, original[2] - original[0]);
      const minHeight = Math.min(1, original[3] - original[1]);
      if (gesture.handle.includes("w")) box[0] = Math.min(end[0], original[2] - minWidth);
      if (gesture.handle.includes("e")) box[2] = Math.max(end[0], original[0] + minWidth);
      if (gesture.handle.includes("n")) box[1] = Math.min(end[1], original[3] - minHeight);
      if (gesture.handle.includes("s")) box[3] = Math.max(end[1], original[1] + minHeight);
      current().bbox = box;
    }
    notify(); draw(); coordinateInputs.forEach((control, index) => setCoordinate(control, current()?.bbox[index])); renderStatus();
  });
  function finish(event, cancel = false) {
    if (!gesture) return;
    const active = gesture; gesture = null;
    if (cancel) { state = readState(active.before); notify(); render(); return; }
    if (active.kind === "draw") {
      const end = point(event); const bbox = [Math.min(active.start[0], end[0]), Math.min(active.start[1], end[1]), Math.max(active.start[0], end[0]), Math.max(active.start[1], end[1])];
      if (bbox[2] - bbox[0] >= 1 && bbox[3] - bbox[1] >= 1) addItem(bbox);
      else { selected.clear(); primary = null; }
    }
    history.push(active.before, serialize()); notify(); render();
    if (svg.hasPointerCapture(event.pointerId)) svg.releasePointerCapture(event.pointerId);
  }
  svg.addEventListener("pointerup", event => finish(event));
  svg.addEventListener("pointercancel", event => finish(event, true));
  svg.addEventListener("lostpointercapture", event => { if (gesture) finish(event, true); });
  for (const eventName of ["pointerdown", "mousedown", "dblclick", "wheel", "keyup"]) root.addEventListener(eventName, event => event.stopPropagation());
  root.addEventListener("keydown", (event) => {
    event.stopPropagation();
    const editing = event.target.matches("input,textarea,select");
    if (!editing && (event.ctrlKey || event.metaKey) && ["z", "y"].includes(event.key.toLowerCase())) {
      event.preventDefault(); travel(event.key.toLowerCase() === "y" || event.shiftKey);
    }
  });

  function load(value) {
    raw = value; gesture = null; selected.clear(); primary = null; notice = "";
    try {
      state = readState(value); restoreError = "";
      if (validDimension(state.width) && validDimension(state.height)) dims = [state.width, state.height];
      else if (Array.isArray(state.canvas_size) && state.canvas_size.length === 2 && state.canvas_size.every(validDimension)) dims = [...state.canvas_size];
      body.hidden = false; recovery.hidden = true;
      history.undoStack = []; history.redoStack = []; history.lastKey = null; render();
      agentPanel?.load();
    } catch (error) {
      restoreError = error.message; body.hidden = true; recovery.hidden = false;
      recovery.replaceChildren(element("p", {}, `布局恢复失败：${restoreError} 原始状态仍保留。`));
      button(recovery, "重置为空白布局", () => { load(JSON.stringify(emptyState())); notify(); });
    }
  }
  const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => { layoutSplit(); draw(); }); observer?.observe(svg); observer?.observe(workspace);
  load(raw);
  agentPanel = createAgentPanel({ root, inspector, settingsHost:historyBar, getState: () => state,
    update: (fn, key) => change(() => fn(state), key), render,
    fetchApi: options.fetchApi ?? ((path, opts) => api.fetchApi(path, opts)),
    apply(result, jobId) {
      const before = serialize();
      const previous = JSON.parse(before); previous.task = null;
      state = applyLayoutResult(state, result); state.last_applied_job = jobId;
      dims = [state.width, state.height]; selected.clear(); primary = null;
      history.push(JSON.stringify(previous), serialize()); notify(); render();
    },
  });
  historyBar.prepend(historyBar.querySelector(".moss-agent-toggle"), historyBar.querySelector(".moss-agent-settings"));
  if (!restoreError) agentPanel.load();
  return { element: root, load, serialize: () => restoreError ? raw : serialize(),
    acceptCompilation(result) {
      if (restoreError || agentPanel.busy()) return;
      const candidate = applyLayoutResult(state, result);
      if (contentKey(candidate) !== contentKey(state)) return;
      if (JSON.stringify(state.output) !== JSON.stringify(candidate.output)) {
        state.output = candidate.output; notify(); render();
      }
    },
    destroy: () => { observer?.disconnect(); agentPanel.destroy(); } };
}

function attach(node) {
  if (node.comfyClass !== "MOSS_Layout_Editor" || node._mossEditor) return;
  const stateWidget = node.widgets?.find(widget => widget.name === "layout_state");
  if (!stateWidget || !node.addDOMWidget) return;
  stateWidget.type = "converted-widget";
  stateWidget.hidden = true;
  stateWidget.computeSize = () => [0, -4];
  const editor = createLayoutEditor(stateWidget.value, (value) => {
    stateWidget.value = value;
    const index = node.widgets.indexOf(stateWidget);
    if (Array.isArray(node.widgets_values) && index >= 0) node.widgets_values[index] = value;
    node.setDirtyCanvas?.(true, true);
    app.graph?.change?.();
  });
  node._mossEditor = editor;
  const panel = node.addDOMWidget("moss_layout_canvas", "div", editor.element, {
    serialize: false, hideOnZoom: false,
    getMinHeight: () => 400, getMaxHeight: () => Number.POSITIVE_INFINITY,
  });
  // Modern ComfyUI distributes remaining node height through this flexible range.
  panel.computeLayoutSize = () => ({ minWidth: 700, minHeight: 400, maxHeight: Number.POSITIVE_INFINITY });
  node.size = [Math.max(node.size?.[0] || 0, 1040), Math.max(node.size?.[1] || 0, 780)];
  const originalConfigure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = originalConfigure?.apply(this, args);
    // The graph migration already merges the legacy layout/prompt connections.
    this.outputs = this.outputs?.slice(0, 3) ?? [];
    for (const [index, [name, type]] of [["layout_prompr", "STRING"], ["width", "INT"], ["height", "INT"]].entries()) {
      if (this.outputs[index]) Object.assign(this.outputs[index], { name, localized_name:name, type });
      else this.addOutput?.(name, type);
    }
    this.size = [Math.max(this.size[0], 720), Math.max(this.size[1], 480)];
    editor.load(stateWidget.value);
    return result;
  };
  const originalRemoved = node.onRemoved;
  node.onRemoved = function (...args) { editor.destroy(); return originalRemoved?.apply(this, args); };
  const originalExecuted = node.onExecuted;
  node.onExecuted = function (message, ...args) {
    const result = originalExecuted?.call(this, message, ...args);
    if (message?.moss_layout_result?.[0]) editor.acceptCompilation(message.moss_layout_result[0]);
    return result;
  };
}

app.registerExtension({
  name: "NewBie.MossLayoutEditor",
  beforeConfigureGraph: migrateLayoutGraph,
  nodeCreated: attach,
  loadedGraphNode(node) { attach(node); node._mossEditor?.load(node.widgets.find(widget => widget.name === "layout_state").value); },
});
