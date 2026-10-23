import { contentKey, requestKey, newId, validDimension, errorsFor } from "./moss_layout_model.js";

const editors = new Map();
function clientId() {
  try {
    const key = "newbie.moss.client";
    if (!sessionStorage.getItem(key)) sessionStorage.setItem(key, newId());
    return sessionStorage.getItem(key);
  } catch { return fallbackClient; }
}
const fallbackClient = newId();

// The panel has no API-key input. Config is resolved exclusively by the server.
export function createAgentPanel({ root, inspector, settingsHost, getState, update, apply, render, fetchApi = fetch }) {
  const token = {};
  const motions = new Map();
  function reveal(el, open, kind, complete = () => {}) {
    const visible = !el.hidden;
    const before = visible ? getComputedStyle(el) : null;
    const snapshot = before ? Object.fromEntries(["height", "opacity", "marginBottom", "paddingBottom", "borderBottomWidth", "transform"].map(k => [k, before[k]])) : null;
    motions.get(el)?.cancel(); motions.delete(el);
    el.inert = !open;
    if (!el.animate || matchMedia("(prefers-reduced-motion: reduce)").matches) {
      el.hidden = !open; el.style.overflow = ""; complete(); return;
    }
    el.hidden = false;
    const natural = getComputedStyle(el);
    let from, to;
    if (kind === "panel") {
      const full = { height:`${el.offsetHeight}px`, opacity:1, marginBottom:natural.marginBottom, paddingBottom:natural.paddingBottom, borderBottomWidth:natural.borderBottomWidth };
      const zero = { height:"0px", opacity:0, marginBottom:"0px", paddingBottom:"0px", borderBottomWidth:"0px" };
      from = snapshot ? Object.fromEntries(Object.keys(full).map(k => [k, snapshot[k]])) : zero;
      to = open ? full : zero; el.style.overflow = "hidden";
    } else {
      from = snapshot ? { opacity:snapshot.opacity, transform:snapshot.transform } : { opacity:0, transform:"translateY(-6px) scale(.98)" };
      to = open ? { opacity:1, transform:"translateY(0) scale(1)" } : { opacity:0, transform:"translateY(-4px) scale(.98)" };
    }
    const animation = el.animate([from, to], { duration:open ? 180 : 130, easing:"cubic-bezier(.16,1,.3,1)" });
    motions.set(el, animation);
    animation.finished.then(() => {
      if (motions.get(el) !== animation) return;
      motions.delete(el); el.hidden = !open; el.style.overflow = ""; complete();
    }).catch(() => {});
  }
  let disposed = false, timer = null, polling = false, config = null, message = "", modelError = "";
  function el(tag, text, parent = panel) { const n = document.createElement(tag); if (text) n.textContent = text; parent.append(n); return n; }
  function field(label, tag, parent = panel) {
    const wrap = el("label", label, parent); const n = el(tag, "", wrap); n.setAttribute("aria-label", label); return n;
  }
  const panel = document.createElement("section"); panel.className = "moss-agent"; panel.id = `moss-agent-${newId()}`; panel.hidden = true; inspector.prepend(panel);
  const agentToggle = el("button", "", settingsHost); agentToggle.type = "button"; agentToggle.className = "moss-agent-toggle";
  agentToggle.setAttribute("aria-label", "Agent 布局助手"); agentToggle.setAttribute("aria-controls", panel.id);
  agentToggle.setAttribute("aria-expanded", "false"); agentToggle.setAttribute("aria-pressed", "false"); agentToggle.title = "展开 Agent 布局助手";
  const spark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ viewBox:"0 0 24 24", width:"18", height:"18", fill:"none", stroke:"currentColor", "stroke-width":"1.7", "stroke-linejoin":"round", "aria-hidden":"true" })) spark.setAttribute(key, value);
  const sparkPath = document.createElementNS(spark.namespaceURI, "path"); sparkPath.setAttribute("d", "M12 2 14.7 9.3 22 12 14.7 14.7 12 22 9.3 14.7 2 12 9.3 9.3Z"); spark.append(sparkPath); agentToggle.append(spark);
  let agentOpen = false;
  panel.inert = true;
  agentToggle.onclick = () => {
    agentOpen = !agentOpen;
    agentToggle.setAttribute("aria-expanded", String(agentOpen)); agentToggle.setAttribute("aria-pressed", String(agentOpen));
    agentToggle.title = busy() ? "Agent 布局助手（运行中）" : agentOpen ? "收起 Agent 布局助手" : "展开 Agent 布局助手";
    if (agentOpen) inspector.scrollTop = 0;
    reveal(panel, agentOpen, "panel");
  };
  const heading = el("div", "Agent 布局助手"); heading.className = "moss-section-title";
  const request = field("创作 / 修订要求", "textarea"); request.rows = 3; request.placeholder = "描述你希望生成或修订的画面…";
  const mode = field("Agent 模式", "select");
  for (const [value, text] of [["generate", "生成新布局"], ["polish", "保留布局润色"]]) { const o = el("option", text, mode); o.value = value; }
  const settings = el("details", "", settingsHost); settings.className = "moss-agent-settings";
  const settingsToggle = el("summary", "", settings); settingsToggle.setAttribute("aria-label", "Agent 设置"); settingsToggle.setAttribute("role", "button"); settingsToggle.title = "Agent 设置";
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 24 24"); icon.setAttribute("width", "18"); icon.setAttribute("height", "18"); icon.setAttribute("fill", "none"); icon.setAttribute("stroke", "currentColor"); icon.setAttribute("stroke-width", "1.7"); icon.setAttribute("aria-hidden", "true");
  const gear = document.createElementNS(icon.namespaceURI, "path"); gear.setAttribute("d", "m9.5 2-.5 3-2 1-3-.5-2 3 2 2v3l-2 2 2 3 3-.5 2 1 .5 3h5l.5-3 2-1 3 .5 2-3-2-2v-3l2-2-2-3-3 .5-2-1-.5-3Z");
  gear.setAttribute("stroke-linejoin", "round");
  const hub = document.createElementNS(icon.namespaceURI, "circle"); hub.setAttribute("cx", "12"); hub.setAttribute("cy", "12"); hub.setAttribute("r", "3"); icon.append(gear, hub); settingsToggle.append(icon);
  const settingsContent = el("div", "", settings); settingsContent.className = "moss-settings-content";
  settingsContent.hidden = true; settingsContent.inert = true;
  let settingsOpen = false;
  function setSettingsOpen(open) {
    if (settingsOpen === open) return;
    settingsOpen = open;
    if (open) settings.open = true;
    settingsToggle.setAttribute("aria-expanded", String(open));
    reveal(settingsContent, open, "popover", () => { settings.open = open; });
  }
  settingsToggle.setAttribute("aria-expanded", "false");
  settingsToggle.addEventListener("click", event => { event.preventDefault(); setSettingsOpen(!settingsOpen); });
  el("div", "Agent 设置", settingsContent).className = "moss-section-title";
  const model = field("模型", "select", settingsContent);
  const apiStatus = el("p", "正在读取 API 配置…", settingsContent); apiStatus.className = "moss-note";
  const effort = field("努力等级", "select", settingsContent);
  for (const value of ["Close", "Low", "Medium", "High"]) { const o = el("option", value, effort); o.value = value; }
  const thinking = field("启用思考", "input", settingsContent); thinking.type = "checkbox"; thinking.parentElement.className = "moss-check";
  const web = field("网页搜索（Medium / High）", "input", settingsContent); web.type = "checkbox"; web.parentElement.className = "moss-check";
  const forceFull = field("强制冷启动", "input", settingsContent); forceFull.type = "checkbox"; forceFull.parentElement.className = "moss-check";
  el("p", "忽略 Agent 增量基线，重新完整生成；Close 本身即为普通生成。", settingsContent).className = "moss-note";
  const actions = el("div"); actions.className = "moss-row";
  const run = el("button", "", actions); run.type = "button";
  run.className = "moss-agent-run";
  const spinner = el("span", "", run); spinner.className = "moss-agent-spinner"; spinner.setAttribute("aria-hidden", "true"); spinner.hidden = true;
  const runLabel = el("span", "运行 Agent", run);
  const cancel = el("button", "取消任务", actions); cancel.type = "button";
  const progress = el("p"); progress.className = "moss-note"; progress.setAttribute("role", "status"); progress.setAttribute("aria-live", "polite");
  const outputDetails = el("details"); el("summary", "当前提示词", outputDetails);
  const preview = field("提示词预览", "textarea", outputDetails); preview.readOnly = true; preview.rows = 5;
  const explanation = el("p", "", outputDetails); explanation.className = "moss-note";
  const copy = el("button", "复制提示词", outputDetails); copy.type = "button";
  copy.onclick = async () => { try { await navigator.clipboard.writeText(getState().output.prompt); message = "提示词已复制"; } catch { message = "复制失败，可从预览框手动复制"; } refresh(); };

  function ensureIdentity() {
    const state = getState();
    if (!state.editor_id || (editors.has(state.editor_id) && editors.get(state.editor_id) !== token)) {
      state.editor_id = newId(); state.task = null;
    }
    editors.set(state.editor_id, token);
    if (state.client_id && state.client_id !== clientId()) state.task = null;
    state.client_id = clientId();
    state.agent = { request: "", mode: "generate", model: "", effort: "Medium", thinking: false, web_search: false, force_full_run:false, ...state.agent };
  }
  function busy() { return Boolean(getState().task); }
  function changed() {
    if (busy()) return;
    update(state => { state.agent = { request: request.value, mode: mode.value, model: model.value,
      effort: effort.value, thinking: thinking.checked, web_search: web.checked, force_full_run:forceFull.checked }; }, "agent-settings");
  }
  request.addEventListener("input", changed);
  for (const n of [mode, model, effort, thinking, web, forceFull]) n.addEventListener("change", changed);
  async function api(path, options = {}) {
    const response = await fetchApi(`/newbie/moss-layout${path}`, { ...options,
      headers: { "Content-Type": "application/json", "X-Moss-Client-Id": clientId() } });
    if (!response.ok) { const e = new Error((await response.text()).slice(0, 400)); e.status = response.status; throw e; }
    return response.json();
  }
  function refresh() {
    ensureIdentity();
    const state = getState(), a = state.agent, running = busy();
    agentToggle.title = running ? "Agent 布局助手（运行中）" : agentOpen ? "收起 Agent 布局助手" : "展开 Agent 布局助手";
    agentToggle.dataset.busy = String(running);
    root.dataset.busy = String(running);
    request.value = a.request; mode.value = a.mode; effort.value = a.effort; thinking.checked = a.thinking; web.checked = a.web_search;
    forceFull.checked = a.force_full_run;
    const models = [...new Set([...(config?.models ?? []), ...(a.model ? [a.model] : [])])];
    if (JSON.stringify([...model.options].map(o => o.value)) !== JSON.stringify(models)) {
      model.replaceChildren(); for (const value of models) { const o = el("option", value, model); o.value = value; }
    }
    model.value = a.model;
    for (const n of [request, mode, model, effort, thinking, forceFull]) n.disabled = running;
    web.disabled = running || !["Medium", "High"].includes(a.effort) || !config?.web_search_configured;
    run.disabled = running || !config?.api_configured || !a.model || !a.request.trim() ||
      !validDimension(state.width) || !validDimension(state.height) || (a.mode === "polish" && errorsFor(state).length > 0);
    runLabel.textContent = running ? "Agent 运行中…" : "运行 Agent"; spinner.hidden = !running;
    run.setAttribute("aria-busy", String(running)); cancel.hidden = !running;
    cancel.disabled = state.task?.cancelling === true;
    apiStatus.textContent = modelError || (!config ? "正在读取 API 配置…" : config.api_configured ? "API 已配置（来自 LPF_config.json）" : "请先在 LPF_config.json 配置 API 和模型");
    progress.textContent = message || (running ? "任务运行期间锁定编辑；完成后整体回填。" :
      !config?.api_configured ? "请展开 Agent 设置，检查 API 和模型配置。" : "Agent 独立运行；开启工作流只输出当前布局。");
    const valid = state.output?.source_key === contentKey(state);
    preview.value = valid ? state.output.prompt : ""; copy.disabled = !valid;
    explanation.textContent = valid ? state.output.text_out : "布局尚未编译或已经修订；开启工作流后会编译当前布局。";
    // Lock editor controls while keeping the isolated cancel button available.
    for (const n of root.querySelectorAll("button,input,textarea,select")) {
      if (panel.contains(n) || settings.contains(n) || n === agentToggle) continue;
      if (running) { if (!n.hasAttribute("data-moss-disabled")) n.dataset.mossDisabled = String(n.disabled); n.disabled = true; }
      else if (n.hasAttribute("data-moss-disabled")) { n.disabled = n.dataset.mossDisabled === "true"; delete n.dataset.mossDisabled; }
    }
  }
  const runtimeLog = root.querySelector(".moss-runtime-log"), runtimeText = root.querySelector(".moss-runtime-log pre");
  let logJob = null;
  function showLog(job = null) {
    runtimeLog.hidden = !busy();
    if (!busy()) return;
    const nextJob = getState().task.input_version;
    const follow = logJob !== nextJob || runtimeText.scrollHeight - runtimeText.clientHeight - runtimeText.scrollTop < 40;
    logJob = nextJob;
    const text = job?.events?.map(e => `[${e.title || e.event || "运行状态"}]\n${e.summary || ""}`).join("\n\n") || "正在启动 Agent…\n模型返回的思考内容和工具调用会在这里实时更新。";
    if (runtimeText.textContent !== text) { runtimeText.textContent = text; if (follow) runtimeText.scrollTop = runtimeText.scrollHeight; }
  }
  function schedule() { clearTimeout(timer); if (!disposed && busy()) timer = setTimeout(poll, 350); }
  async function accept(job) {
    const state = getState(), task = state.task;
    if (!task || job.editor_id !== state.editor_id || job.input_version !== task.input_version) return;
    let notify = true;
    if (job.status === "succeeded") {
      if (task.cancelling || task.source_key !== requestKey(state) || state.last_applied_job === job.job_id) {
        state.task = null; message = "任务已完成，当前内容已变化，保留现有编辑。";
      } else {
        try {
          apply(job.result, job.job_id); notify = false; message = "Agent 结果已回填，可继续修订；开启工作流输出当前布局。";
        } catch (error) {
          state.task = null; message = `结果无法回填：${error.message}。原布局已保留。`;
        }
      }
    } else if (["failed", "cancelled"].includes(job.status)) {
      state.task = null; message = job.error || "任务已取消，原布局已保留。";
    } else {
      notify = state.task.job_id !== job.job_id;
      state.task.job_id = job.job_id;
      const event = job.events?.filter(e => e.event !== "reasoning").at(-1);
      message = state.task.cancelling ? "正在取消，等待当前请求结束…" : [event?.title, event?.summary?.slice(0, 160)].filter(Boolean).join(" · ") || "Agent 正在运行…";
    }
    if (notify) update(() => {}, "task"); render(); showLog(job); schedule();
  }
  async function poll() {
    if (polling || disposed || !busy()) return;
    polling = true;
    try {
      const task = getState().task;
      const job = await api(task.job_id ? `/jobs/${encodeURIComponent(task.job_id)}` : `/latest?editor_id=${encodeURIComponent(getState().editor_id)}`);
      if (!disposed && busy()) await accept(job);
    } catch (error) {
      if (disposed) return;
      if (error.status === 404) { getState().task = null; message = "任务已过期或服务已重启，原布局已保留；可重新运行。"; update(() => {}, "task"); render(); showLog(); }
      else { message = "任务连接暂时中断，正在重连…"; refresh(); }
    } finally { polling = false; schedule(); }
  }
  run.onclick = async () => {
    if (run.disabled) return;
    const state = getState(), inputVersion = newId();
    state.task = { job_id: null, input_version: inputVersion, source_key: requestKey(state) };
    update(() => {}, "task"); message = "正在提交布局任务…"; render();
    showLog();
    const payload = { editor_id: state.editor_id, input_version: inputVersion, state: JSON.parse(JSON.stringify(state)),
      mode: state.agent.mode, request: state.agent.request,
      settings: { model: state.agent.model, effort: state.agent.effort, thinking: state.agent.thinking, web_search: state.agent.web_search, force_full_run:state.agent.force_full_run } };
    try { const job = await api("/jobs", { method: "POST", body: JSON.stringify(payload) }); if (!disposed) await accept(job); }
    catch (error) {
      if (disposed) return;
      if (error.status === 400) { state.task = null; message = error.message; update(() => {}, "task"); render(); showLog(); }
      else { message = "提交状态待确认，正在恢复任务…"; refresh(); schedule(); }
    }
  };
  cancel.onclick = async () => {
    const task = getState().task; if (!task) return;
    task.cancelling = true; update(() => {}, "task"); refresh();
    try {
      const job = task.job_id ? { job_id: task.job_id } : await api(`/latest?editor_id=${encodeURIComponent(getState().editor_id)}`);
      await accept(await api(`/jobs/${encodeURIComponent(job.job_id)}`, { method: "DELETE" }));
    } catch { message = "取消请求未确认，正在重连…"; refresh(); schedule(); }
  };
  async function load() {
    ensureIdentity(); update(() => {}, "task"); refresh(); showLog();
    try {
      config = await api("/config"); if (disposed) return;
      const state = getState();
      if (!state.agent.model && config.models.length && !busy()) { state.agent.model = config.models[0]; update(() => {}, "task"); }
      modelError = ""; refresh(); schedule();
    } catch (error) { modelError = `API 配置读取失败：${error.message}。请确认 ComfyUI 已重启加载新版本`; refresh(); schedule(); }
  }
  function dismissSettings(event) { if (!settings.contains(event.target)) setSettingsOpen(false); }
  function escapeSettings(event) { if (event.key === "Escape" && settingsOpen) { setSettingsOpen(false); settingsToggle.focus(); event.stopPropagation(); } }
  document.addEventListener("pointerdown", dismissSettings, true); settings.addEventListener("keydown", escapeSettings);
  return { refresh, busy, load, destroy() {
    disposed = true; clearTimeout(timer); document.removeEventListener("pointerdown", dismissSettings, true); settings.removeEventListener("keydown", escapeSettings);
    for (const animation of motions.values()) animation.cancel(); motions.clear();
    for (const [id, value] of editors) if (value === token) editors.delete(id);
  } };
}
