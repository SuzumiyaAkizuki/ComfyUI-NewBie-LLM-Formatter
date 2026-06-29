import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const TRACE_EVENT = "newbie_llm_agent_trace";
const NODE_CLASS = "LLM_Prompt_Formatter";
const panels = new Map();
const traces = new Map();
const panelTraceIds = new Map();
let currentExecutingNodeId = null;
let carouselTimer = null;

function injectStyles() {
  if (document.getElementById("newbie-agent-trace-style")) return;
  const style = document.createElement("style");
  style.id = "newbie-agent-trace-style";
  style.textContent = `
    .nb-agent-panel {
      box-sizing: border-box;
      width: 100%;
      min-width: 300px;
      max-height: 240px;
      overflow: auto;
      padding: 10px;
      border: 1px solid rgba(120, 148, 196, 0.28);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(24, 29, 39, 0.96), rgba(16, 19, 27, 0.96));
      color: #d8dfec;
      font: 12px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
    }
    .nb-agent-panel * { box-sizing: border-box; }
    .nb-agent-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 8px;
    }
    .nb-agent-title {
      display: flex;
      align-items: center;
      gap: 7px;
      min-width: 0;
      font-weight: 650;
      color: #f1f5fb;
    }
    .nb-agent-dot {
      width: 8px;
      height: 8px;
      flex: 0 0 8px;
      border-radius: 50%;
      background: #8792a8;
      box-shadow: 0 0 0 3px rgba(135, 146, 168, 0.14);
    }
    .nb-agent-panel[data-state="running"] .nb-agent-dot {
      background: #62a8ff;
      box-shadow: 0 0 0 3px rgba(98, 168, 255, 0.18);
    }
    .nb-agent-panel[data-state="success"] .nb-agent-dot {
      background: #6dd6a4;
      box-shadow: 0 0 0 3px rgba(109, 214, 164, 0.16);
    }
    .nb-agent-panel[data-state="warning"] .nb-agent-dot {
      background: #e7c160;
      box-shadow: 0 0 0 3px rgba(231, 193, 96, 0.16);
    }
    .nb-agent-panel[data-state="error"] .nb-agent-dot {
      background: #ff7f8d;
      box-shadow: 0 0 0 3px rgba(255, 127, 141, 0.16);
    }
    .nb-agent-name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .nb-agent-badge {
      flex: 0 0 auto;
      padding: 2px 7px;
      border-radius: 999px;
      background: rgba(98, 168, 255, 0.14);
      color: #9dccff;
      font-size: 11px;
      line-height: 18px;
    }
    .nb-agent-summary {
      min-height: 18px;
      margin-bottom: 6px;
      color: #aeb9ca;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .nb-agent-current {
      margin-bottom: 7px;
      overflow: hidden;
    }
    .nb-agent-current-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 5px;
      color: #93a1b6;
      font-size: 11px;
    }
    .nb-agent-current-label {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .nb-agent-carousel-count {
      flex: 0 0 auto;
      color: #9dccff;
      font-variant-numeric: tabular-nums;
    }
    .nb-agent-log-toggle {
      margin-top: 4px;
      color: #93a1b6;
    }
    .nb-agent-log-button {
      display: block;
      width: 100%;
      border: 0;
      background: transparent;
      padding: 0;
      text-align: left;
      cursor: pointer;
      color: #9dccff;
      user-select: none;
      font-size: 11px;
      font: inherit;
    }
    .nb-agent-log-button::before {
      content: "▶";
      display: inline-block;
      width: 14px;
    }
    .nb-agent-log-toggle.is-open > .nb-agent-log-button::before {
      content: "▼";
    }
    .nb-agent-log-content {
      display: none;
    }
    .nb-agent-log-toggle.is-open > .nb-agent-log-content {
      display: block;
    }
    .nb-agent-events {
      display: flex;
      flex-direction: column;
      gap: 7px;
      max-height: 155px;
      overflow: auto;
      margin-top: 6px;
      padding-right: 3px;
    }
    .nb-agent-row {
      display: grid;
      grid-template-columns: 16px minmax(0, 1fr);
      gap: 7px;
      align-items: start;
      padding: 6px 8px;
      border: 1px solid rgba(135, 146, 168, 0.16);
      border-radius: 7px;
      background: rgba(255, 255, 255, 0.035);
    }
    .nb-agent-row[data-kind="tool"] {
      background: rgba(98, 168, 255, 0.055);
      border-color: rgba(98, 168, 255, 0.18);
    }
    .nb-agent-icon {
      width: 13px;
      height: 13px;
      margin-top: 2px;
      border-radius: 50%;
      border: 1px solid rgba(174, 185, 202, 0.55);
    }
    .nb-agent-row[data-status="running"] .nb-agent-icon {
      border: 2px solid rgba(98, 168, 255, 0.25);
      border-top-color: #62a8ff;
      animation: nb-agent-spin 0.9s linear infinite;
    }
    .nb-agent-row[data-status="success"] .nb-agent-icon {
      border: 0;
      background: #6dd6a4;
      box-shadow: inset 0 0 0 3px rgba(0, 0, 0, 0.18);
    }
    .nb-agent-row[data-status="warning"] .nb-agent-icon {
      border: 0;
      background: #e7c160;
      clip-path: polygon(50% 0, 100% 92%, 0 92%);
      border-radius: 0;
    }
    .nb-agent-row[data-status="error"] .nb-agent-icon {
      border: 0;
      background: #ff7f8d;
      box-shadow: inset 0 0 0 3px rgba(0, 0, 0, 0.16);
    }
    .nb-agent-row-title {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      color: #eef3fa;
      font-weight: 590;
    }
    .nb-agent-row-title span:first-child {
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .nb-agent-time {
      flex: 0 0 auto;
      color: #7f8da2;
      font-size: 10px;
      font-variant-numeric: tabular-nums;
    }
    .nb-agent-row-summary {
      margin-top: 2px;
      color: #aeb9ca;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .nb-agent-details {
      margin-top: 6px;
      color: #93a1b6;
    }
    .nb-agent-details summary {
      cursor: pointer;
      color: #9dccff;
      user-select: none;
    }
    .nb-agent-details pre {
      max-height: 110px;
      overflow: auto;
      margin: 6px 0 0;
      padding: 7px;
      border-radius: 6px;
      background: rgba(5, 8, 13, 0.5);
      color: #cdd6e4;
      font: 11px/1.4 ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .nb-agent-round {
      flex: 0 0 auto;
      border: 1px solid rgba(135, 146, 168, 0.16);
      border-radius: 7px;
      background: rgba(255, 255, 255, 0.03);
      overflow: hidden;
      min-height: 30px;
    }
    .nb-agent-disclosure-button {
      display: block;
      width: 100%;
      border: 0;
      background: transparent;
      cursor: pointer;
      user-select: none;
      text-align: left;
      color: #dce5f2;
      padding: 7px 8px;
      font: inherit;
    }
    .nb-agent-disclosure-button::before {
      content: "▶";
      display: inline-block;
      width: 14px;
      color: #cbd6e6;
    }
    .nb-agent-round.is-open > .nb-agent-disclosure-button::before,
    .nb-agent-tool.is-open > .nb-agent-disclosure-button::before {
      content: "▼";
    }
    .nb-agent-round > .nb-agent-disclosure-button {
      font-weight: 650;
    }
    .nb-agent-round-content,
    .nb-agent-tool-content {
      display: none;
    }
    .nb-agent-round.is-open > .nb-agent-round-content,
    .nb-agent-tool.is-open > .nb-agent-tool-content {
      display: block;
    }
    .nb-agent-tool {
      margin: 0 7px 7px;
      border: 1px solid rgba(98, 168, 255, 0.18);
      border-radius: 7px;
      background: rgba(98, 168, 255, 0.055);
    }
    .nb-agent-tool > .nb-agent-disclosure-button {
      color: #eef3fa;
      font-weight: 590;
    }
    .nb-agent-tool-meta {
      display: block;
      margin-top: 2px;
      color: #aeb9ca;
      font-weight: 400;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .nb-agent-detail-block {
      padding: 0 8px 8px;
    }
    .nb-agent-detail-title {
      margin: 6px 0 4px;
      color: #9dccff;
      font-size: 11px;
    }
    .nb-agent-detail-block pre {
      display: block;
      max-height: 130px;
      overflow: auto;
      margin: 4px 0 8px;
      padding: 7px;
      border-radius: 6px;
      background: rgba(5, 8, 13, 0.58);
      color: #cdd6e4;
      font: 11px/1.4 ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .nb-agent-empty {
      padding: 7px 8px;
      color: #7f8da2;
    }
    .nb-agent-tool-list {
      padding-top: 2px;
    }
    @keyframes nb-agent-spin {
      to { transform: rotate(360deg); }
    }
    .nb-agent-current .nb-agent-row.nb-agent-anim-in {
      animation: nb-agent-carousel-in 0.32s cubic-bezier(0.22, 0.61, 0.36, 1);
    }
    @keyframes nb-agent-carousel-in {
      from { opacity: 0; transform: translateX(14px); }
      to { opacity: 1; transform: translateX(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .nb-agent-current .nb-agent-row.nb-agent-anim-in { animation: none; }
    }

    /* Light theme: ComfyUI removes the "dark-theme" class from <body> when a
       light palette is active. These overrides have higher specificity than the
       base (dark) rules above and switch automatically with the palette. */
    body:not(.dark-theme) .nb-agent-panel {
      border-color: rgba(120, 148, 196, 0.45);
      background: linear-gradient(180deg, #f7f9fd, #eef1f7);
      color: #2a3340;
      box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6);
    }
    body:not(.dark-theme) .nb-agent-title { color: #1c2733; }
    body:not(.dark-theme) .nb-agent-dot {
      background: #8793a8;
      box-shadow: 0 0 0 3px rgba(135, 146, 168, 0.18);
    }
    body:not(.dark-theme) .nb-agent-badge {
      background: rgba(45, 120, 220, 0.12);
      color: #2f6fd0;
    }
    body:not(.dark-theme) .nb-agent-summary,
    body:not(.dark-theme) .nb-agent-row-summary,
    body:not(.dark-theme) .nb-agent-tool-meta { color: #5a6678; }
    body:not(.dark-theme) .nb-agent-current-head,
    body:not(.dark-theme) .nb-agent-log-toggle,
    body:not(.dark-theme) .nb-agent-details { color: #6b7686; }
    body:not(.dark-theme) .nb-agent-carousel-count,
    body:not(.dark-theme) .nb-agent-log-button,
    body:not(.dark-theme) .nb-agent-details summary,
    body:not(.dark-theme) .nb-agent-detail-title { color: #2f6fd0; }
    body:not(.dark-theme) .nb-agent-row {
      border-color: rgba(60, 72, 92, 0.18);
      background: rgba(20, 30, 50, 0.035);
    }
    body:not(.dark-theme) .nb-agent-row[data-kind="tool"] {
      background: rgba(45, 120, 220, 0.07);
      border-color: rgba(45, 120, 220, 0.28);
    }
    body:not(.dark-theme) .nb-agent-row-title { color: #1c2733; }
    body:not(.dark-theme) .nb-agent-time { color: #8a93a5; }
    body:not(.dark-theme) .nb-agent-icon { border-color: rgba(60, 72, 92, 0.45); }
    body:not(.dark-theme) .nb-agent-details pre,
    body:not(.dark-theme) .nb-agent-detail-block pre {
      background: rgba(15, 23, 42, 0.06);
      color: #2a3340;
    }
    body:not(.dark-theme) .nb-agent-round {
      border-color: rgba(60, 72, 92, 0.18);
      background: rgba(20, 30, 50, 0.025);
    }
    body:not(.dark-theme) .nb-agent-disclosure-button { color: #2a3340; }
    body:not(.dark-theme) .nb-agent-disclosure-button::before { color: #5a6678; }
    body:not(.dark-theme) .nb-agent-tool {
      border-color: rgba(45, 120, 220, 0.28);
      background: rgba(45, 120, 220, 0.06);
    }
    body:not(.dark-theme) .nb-agent-tool > .nb-agent-disclosure-button { color: #1c2733; }
    body:not(.dark-theme) .nb-agent-empty { color: #8a93a5; }
  `;
  document.head.appendChild(style);
}

function emptyTrace() {
  return {
    state: "idle",
    title: "Agent Path",
    summary: "等待 Agent 运行",
    badge: "idle",
    active: null,
    carouselIndex: 0,
    replay: null,
    ui: {
      logOpen: false,
      openRounds: new Set(),
      openTools: new Set(),
    },
    events: [],
  };
}

function eventTime(event) {
  if (!event.timestamp) return "";
  return new Date(event.timestamp * 1000).toLocaleTimeString([], {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function prettyDetails(details) {
  try {
    return JSON.stringify(details ?? {}, null, 2);
  } catch {
    return String(details ?? "");
  }
}

function eventKey(event) {
  const details = event.details ?? {};
  if (event.event === "tool" && details.tool_call_id) {
    return `tool:${details.tool_call_id}`;
  }
  if (event.event === "round" && details.round) {
    return `round:${details.round}`;
  }
  if (event.event === "parse") return "parse";
  return null;
}

function eventStatusRank(status) {
  if (status === "error") return 4;
  if (status === "warning") return 3;
  if (status === "success") return 2;
  if (status === "running") return 1;
  return 0;
}

function mergeEvent(previous, next) {
  if (!previous) return next;
  return {
    ...previous,
    ...next,
    status: eventStatusRank(next.status) >= eventStatusRank(previous.status) ? next.status : previous.status,
    details: {
      ...(previous.details ?? {}),
      ...(next.details ?? {}),
    },
  };
}

function finishRunningItems(trace, predicate = () => true) {
  for (const item of trace.events) {
    if (item.status === "running" && predicate(item)) {
      item.status = "success";
    }
  }
}

function traceStateFromEvent(event, trace) {
  if (event.event === "complete") return "success";
  if (event.event === "fallback") return "error";
  if (event.status === "error") return "error";
  if (event.status === "warning") return trace.state === "error" ? "error" : "warning";
  if (event.status === "running") return trace.state === "error" ? "error" : "running";
  return trace.state;
}

function topSummary(trace) {
  const rounds = groupRounds(trace);
  const latest = rounds.at(-1);
  const tools = currentRoundTools(trace);
  if (trace.replay) {
    const replayTools = toolsForRound(trace, trace.replay.round);
    return `Round ${trace.replay.round} · 调用完成回放 ${trace.replay.index + 1}/${replayTools.length}`;
  }
  if (trace.state === "success") {
    const complete = [...trace.events].reverse().find((item) => item.event === "complete");
    return complete?.summary || `完成 · ${rounds.length} 轮`;
  }
  if (latest && tools.length > 1) {
    return `Round ${latest.round} · 本轮 ${tools.length} 个工具调用`;
  }
  if (latest) return `Round ${latest.round}`;
  return trace.summary || "等待 Agent 运行";
}

function topBadge(trace) {
  if (trace.state === "success") return "complete";
  if (trace.state === "error") return "error";
  if (trace.state === "warning") return "warning";
  if (trace.state === "running") return "running";
  return "idle";
}

function upsertEvent(trace, event) {
  if (event.event === "round") {
    finishRunningItems(trace, (item) => item.event === "round");
  }
  if (event.event === "parse" || event.event === "complete") {
    finishRunningItems(trace);
  }

  const key = eventKey(event);
  if (key) {
    const index = trace.events.findIndex((item) => eventKey(item) === key);
    if (index !== -1) {
      trace.events[index] = mergeEvent(trace.events[index], event);
      trace.active = trace.events[index];
      return;
    }
  }

  trace.events.push(event);
  trace.active = event;
}

function maybeStartReplay(trace, event) {
  if (event.event !== "round" || event.details?.phase !== "thinking") return;
  const nextRound = event.details?.round;
  const previous = latestRound(trace);
  if (!previous || previous.round === nextRound || previous.tools.length === 0) return;
  trace.replay = {
    round: previous.round,
    index: 0,
    remaining: previous.tools.length,
  };
}

function renderEventRow(item, compact = false) {
  const row = document.createElement("div");
  row.className = "nb-agent-row";
  row.dataset.status = item.status || "info";
  row.dataset.kind = item.event || "event";

  const icon = document.createElement("span");
  icon.className = "nb-agent-icon";

  const body = document.createElement("div");
  const rowTitle = document.createElement("div");
  rowTitle.className = "nb-agent-row-title";
  const rowName = document.createElement("span");
  rowName.textContent = item.title || item.event || "Step";
  const time = document.createElement("span");
  time.className = "nb-agent-time";
  time.textContent = eventTime(item);
  rowTitle.append(rowName, time);

  const rowSummary = document.createElement("div");
  rowSummary.className = "nb-agent-row-summary";
  rowSummary.textContent = item.summary || "";
  body.append(rowTitle, rowSummary);

  if (!compact && item.details && Object.keys(item.details).length) {
    const details = document.createElement("details");
    details.className = "nb-agent-details";
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "查看细节";
    const pre = document.createElement("pre");
    pre.textContent = prettyDetails(item.details);
    details.append(detailsSummary, pre);
    body.append(details);
  }

  row.append(icon, body);
  return row;
}

function renderToolCard(tool, options = {}) {
  const card = document.createElement("div");
  card.className = "nb-agent-row";
  card.dataset.status = tool.status || "info";
  card.dataset.kind = "tool";

  const icon = document.createElement("span");
  icon.className = "nb-agent-icon";

  const body = document.createElement("div");
  const rowTitle = document.createElement("div");
  rowTitle.className = "nb-agent-row-title";
  const name = document.createElement("span");
  name.textContent = tool.title || "tool";
  const count = document.createElement("span");
  count.className = "nb-agent-time";
  count.textContent = options.countText || eventTime(tool);
  rowTitle.append(name, count);

  const summary = document.createElement("div");
  summary.className = "nb-agent-row-summary";
  summary.textContent = tool.summary || "";

  body.append(rowTitle, summary);
  card.append(icon, body);
  return card;
}

function roundNumberForEvent(event) {
  return event?.details?.round ?? null;
}

function groupRounds(trace) {
  const byRound = new Map();
  for (const item of trace.events) {
    if (item.event === "round") {
      const round = roundNumberForEvent(item);
      if (!round) continue;
      const group = byRound.get(round) ?? { round, event: item, tools: [] };
      group.event = item;
      byRound.set(round, group);
    }
  }
  for (const item of trace.events) {
    if (item.event !== "tool") continue;
    const round = roundNumberForEvent(item);
    if (!round) continue;
    const group = byRound.get(round) ?? { round, event: null, tools: [] };
    if (!byRound.has(round)) {
      byRound.set(round, group);
    }
    group.tools.push(item);
  }
  return [...byRound.values()]
    .filter((group) => group.event || group.tools.length)
    .sort((a, b) => a.round - b.round);
}

function latestRound(trace) {
  const rounds = groupRounds(trace);
  return rounds.at(-1) ?? null;
}

function toolsForRound(trace, roundNumber) {
  return groupRounds(trace).find((round) => round.round === roundNumber)?.tools ?? [];
}

function currentRoundTools(trace) {
  return latestRound(trace)?.tools ?? [];
}

function activeCarouselItem(trace) {
  if (trace.state === "success" || trace.state === "error") {
    return { item: trace.active, index: 0, total: trace.active ? 1 : 0 };
  }
  if (trace.replay) {
    const tools = toolsForRound(trace, trace.replay.round);
    if (tools.length) {
      const index = trace.replay.index % tools.length;
      return { item: tools[index], index, total: tools.length, replay: true };
    }
  }
  const latest = latestRound(trace);
  if (latest && latest.tools.length === 0) {
    return { item: latest.event, index: 0, total: latest.event ? 1 : 0 };
  }
  const tools = currentRoundTools(trace);
  if (tools.length > 1) {
    return {
      item: tools[trace.carouselIndex % tools.length],
      index: trace.carouselIndex % tools.length,
      total: tools.length,
    };
  }
  if (tools.length === 1 && tools[0].status === "running") {
    return { item: tools[0], index: 0, total: 1 };
  }
  return { item: trace.active, index: 0, total: trace.active ? 1 : 0 };
}

function renderActive(panel, trace, animate = false) {
  const active = panel.querySelector(".nb-agent-current");
  if (!active) return;
  active.innerHTML = "";
  const { item, index, total, replay } = activeCarouselItem(trace);
  if (!item) return;

  const head = document.createElement("div");
  head.className = "nb-agent-current-head";
  const label = document.createElement("span");
  label.className = "nb-agent-current-label";
  const note = item.event === "tool" ? (item.details?.message || "").trim() : "";
  let labelText;
  if (replay) labelText = "调用完成回放";
  else if (note) labelText = note;
  else labelText = total > 1 ? "本轮工具调用轮播" : "当前步骤";
  label.textContent = labelText;
  label.title = labelText;
  const count = document.createElement("span");
  count.className = "nb-agent-carousel-count";
  count.textContent = total > 1 ? `${index + 1}/${total}` : "";
  head.append(label, count);
  active.append(head);
  let card;
  if (item.event === "tool") {
    card = renderToolCard(item, { countText: total > 1 ? `${index + 1}/${total}` : eventTime(item) });
  } else if (item.event === "round" && item.details?.phase === "thinking") {
    card = renderEventRow({
      ...item,
      title: "思考中...",
      summary: "等待大模型决定是否调用工具",
    });
  } else {
    card = renderEventRow(item);
  }
  // Only animate on actual carousel rotation, not on every re-render (e.g. expand/collapse clicks).
  if (animate) card.classList.add("nb-agent-anim-in");
  active.append(card);
}

function renderTop(panel, trace) {
  panel.dataset.state = trace.state || "idle";
  const title = panel.querySelector(".nb-agent-name");
  const badge = panel.querySelector(".nb-agent-badge");
  const summary = panel.querySelector(".nb-agent-summary");
  if (title) title.textContent = "Agent Path";
  if (badge) badge.textContent = topBadge(trace);
  if (summary) summary.textContent = topSummary(trace);
}

function renderRoundDetails(trace) {
  const events = document.createElement("div");
  events.className = "nb-agent-events";
  const rounds = groupRounds(trace);
  if (!rounds.length) {
    const empty = document.createElement("div");
    empty.className = "nb-agent-empty";
    empty.textContent = "还没有轮次记录";
    events.append(empty);
    return events;
  }

  for (const group of rounds) {
    const round = document.createElement("div");
    round.className = "nb-agent-round";
    if (trace.ui.openRounds.has(String(group.round))) round.classList.add("is-open");
    round.dataset.disclosure = "round";
    round.dataset.round = String(group.round);
    const summary = document.createElement("button");
    summary.type = "button";
    summary.className = "nb-agent-disclosure-button";
    const status = group.tools.some((tool) => tool.status === "running") ? "running" : "done";
    summary.append(document.createTextNode(`Round ${group.round} · ${group.tools.length} tools · ${status}`));
    round.append(summary);

    const roundContent = document.createElement("div");
    roundContent.className = "nb-agent-round-content";

    if (!group.tools.length) {
      const empty = document.createElement("div");
      empty.className = "nb-agent-empty";
      empty.textContent = "本轮没有工具调用";
      roundContent.append(empty);
    }

    const toolList = document.createElement("div");
    toolList.className = "nb-agent-tool-list";
    for (const tool of group.tools) {
      const toolDetails = document.createElement("div");
      toolDetails.className = "nb-agent-tool";
      const toolId = String(tool.details?.tool_call_id ?? `${group.round}:${tool.title}:${tool.summary}`);
      if (trace.ui.openTools.has(toolId)) toolDetails.classList.add("is-open");
      toolDetails.dataset.disclosure = "tool";
      toolDetails.dataset.toolId = toolId;
      const toolSummary = document.createElement("button");
      toolSummary.type = "button";
      toolSummary.className = "nb-agent-disclosure-button";
      toolSummary.append(document.createTextNode(tool.title || "tool"));
      const meta = document.createElement("span");
      meta.className = "nb-agent-tool-meta";
      meta.textContent = `${tool.status || "info"} · ${tool.summary || ""}`;
      toolSummary.append(meta);
      toolDetails.append(toolSummary);

      const detailBlock = document.createElement("div");
      detailBlock.className = "nb-agent-tool-content nb-agent-detail-block";
      const argsTitle = document.createElement("div");
      argsTitle.className = "nb-agent-detail-title";
      argsTitle.textContent = "请求体";
      const argsPre = document.createElement("pre");
      argsPre.textContent = prettyDetails(tool.details?.arguments ?? {});
      detailBlock.append(argsTitle, argsPre);

      const resultTitle = document.createElement("div");
      resultTitle.className = "nb-agent-detail-title";
      resultTitle.textContent = "响应体";
      const resultPre = document.createElement("pre");
      resultPre.textContent = prettyDetails(tool.details?.result ?? {});
      detailBlock.append(resultTitle, resultPre);

      toolDetails.append(detailBlock);
      toolList.append(toolDetails);
    }
    roundContent.append(toolList);
    round.append(roundContent);
    events.append(round);
  }
  return events;
}

function render(panel, trace) {
  panel.innerHTML = "";

  const top = document.createElement("div");
  top.className = "nb-agent-top";

  const title = document.createElement("div");
  title.className = "nb-agent-title";
  const dot = document.createElement("span");
  dot.className = "nb-agent-dot";
  const name = document.createElement("span");
  name.className = "nb-agent-name";
  title.append(dot, name);

  const badge = document.createElement("div");
  badge.className = "nb-agent-badge";
  top.append(title, badge);

  const summary = document.createElement("div");
  summary.className = "nb-agent-summary";

  const active = document.createElement("div");
  active.className = "nb-agent-current";

  const logToggle = document.createElement("div");
  logToggle.className = "nb-agent-log-toggle";
  if (trace.ui.logOpen) logToggle.classList.add("is-open");
  const logSummary = document.createElement("button");
  logSummary.type = "button";
  logSummary.className = "nb-agent-log-button";
  logSummary.dataset.disclosure = "log";
  logSummary.textContent = `查看轮次和工具调用 (${groupRounds(trace).length})`;
  const logContent = document.createElement("div");
  logContent.className = "nb-agent-log-content";
  const events = renderRoundDetails(trace);
  logContent.append(events);
  logToggle.append(logSummary, logContent);

  panel.append(top, summary, active, logToggle);
  renderTop(panel, trace);
  renderActive(panel, trace);
}

function ensureTrace(nodeId) {
  const key = String(nodeId);
  if (!traces.has(key)) traces.set(key, emptyTrace());
  return traces.get(key);
}

function updateTrace(event) {
  const nodeId = String(event.node_id ?? "");
  if (!nodeId) return;
  const trace = ensureTrace(nodeId);

  if (event.event === "start") {
    traces.set(nodeId, emptyTrace());
  }
  const current = ensureTrace(nodeId);

  maybeStartReplay(current, event);
  current.state = traceStateFromEvent(event, current);
  current.summary = event.summary || current.summary;
  current.badge = event.event || current.badge;
  upsertEvent(current, event);
  if (current.events.length > 40) current.events = current.events.slice(-40);

  let panel = panels.get(nodeId);
  let panelId = nodeId;
  if (!panel && currentExecutingNodeId) {
    panelId = String(currentExecutingNodeId);
    panel = panels.get(panelId);
  }
  if (!panel && panels.size === 1) {
    const entry = [...panels.entries()][0];
    panelId = entry[0];
    panel = entry[1];
  }
  if (panel) panelTraceIds.set(panelId, nodeId);
  if (panel) render(panel, current);
  ensureCarouselTimer();
}

function createPanel(node) {
  injectStyles();
  const panel = document.createElement("div");
  panel.className = "nb-agent-panel";
  panel.addEventListener("click", (event) => {
    const button = event.target.closest(".nb-agent-disclosure-button, .nb-agent-log-button");
    if (!button || !panel.contains(button)) return;
    const panelId = [...panels.entries()].find(([, value]) => value === panel)?.[0];
    const traceId = panelId ? (panelTraceIds.get(panelId) ?? panelId) : null;
    const trace = traceId ? traces.get(traceId) : null;
    const item = button.closest("[data-disclosure]");
    if (!item || !trace) return;
    const kind = item.dataset.disclosure;
    if (kind === "log") {
      trace.ui.logOpen = !trace.ui.logOpen;
    } else if (kind === "round") {
      const round = item.dataset.round;
      if (trace.ui.openRounds.has(round)) trace.ui.openRounds.delete(round);
      else trace.ui.openRounds.add(round);
    } else if (kind === "tool") {
      const toolId = item.dataset.toolId;
      if (trace.ui.openTools.has(toolId)) trace.ui.openTools.delete(toolId);
      else trace.ui.openTools.add(toolId);
    }
    render(panel, trace);
    event.preventDefault();
    event.stopPropagation();
  });
  render(panel, emptyTrace());

  if (node.addDOMWidget) {
    node.addDOMWidget("agent_trace", "div", panel, {
      serialize: false,
      hideOnZoom: false,
    });
  } else {
    node.addWidget("text", "agent_trace", "Agent trace ready", () => {}, {});
  }

  panels.set(String(node.id), panel);
}

api.addEventListener(TRACE_EVENT, (message) => {
  updateTrace(message.detail ?? message);
});

api.addEventListener("executing", (message) => {
  currentExecutingNodeId = message.detail ?? message ?? null;
});

api.addEventListener("execution_start", () => {
  for (const [nodeId, panel] of panels.entries()) {
    const trace = emptyTrace();
    traces.set(nodeId, trace);
    panelTraceIds.set(nodeId, nodeId);
    render(panel, trace);
  }
});

function renderActivePanels() {
  for (const [nodeId, panel] of panels.entries()) {
    const traceId = panelTraceIds.get(nodeId) ?? nodeId;
    const trace = traces.get(traceId);
    if (!trace) continue;
    if (trace.replay) {
      const tools = toolsForRound(trace, trace.replay.round);
      if (!tools.length || trace.replay.remaining <= 1) {
        trace.replay = null;
      } else {
        trace.replay.remaining -= 1;
        trace.replay.index = (trace.replay.index + 1) % tools.length;
      }
      renderTop(panel, trace);
      renderActive(panel, trace, true);
      continue;
    }
    const tools = currentRoundTools(trace);
    if (tools.length > 1) {
      trace.carouselIndex = (trace.carouselIndex + 1) % tools.length;
      renderTop(panel, trace);
      renderActive(panel, trace, true);
    }
  }
}

function ensureCarouselTimer() {
  if (carouselTimer) return;
  carouselTimer = window.setInterval(renderActivePanels, 500);
}

app.registerExtension({
  name: "newbie.llm.agent.trace",
  async nodeCreated(node) {
    if (node?.comfyClass === NODE_CLASS) {
      createPanel(node);
    }
  },
});
