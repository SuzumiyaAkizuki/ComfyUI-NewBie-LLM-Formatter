import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_CLASS = "LLM_Style_Saver";
const SAVE_WIDGET = "save_trigger";
const saverNodes = new Map();
let currentExecutingNodeId = null;

function nodeKey(nodeId) {
  if (nodeId === null || nodeId === undefined) return null;
  return String(nodeId);
}

function getWidget(node, name) {
  return node?.widgets?.find((widget) => widget.name === name);
}

function markCanvasDirty(node) {
  node?.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
  app.canvas?.setDirty?.(true, true);
  app.canvas?.draw?.(true, true);
}

function syncWidgetValue(node, widget, value) {
  widget.value = value;

  const widgetIndex = node?.widgets?.indexOf(widget) ?? -1;
  if (widgetIndex >= 0 && Array.isArray(node.widgets_values)) {
    node.widgets_values[widgetIndex] = value;
  }

  const inputEl = widget.inputEl ?? widget.element ?? widget.domElement;
  if (inputEl) {
    if ("checked" in inputEl) inputEl.checked = value;
    if ("value" in inputEl) inputEl.value = value;
    inputEl.dispatchEvent?.(new Event("input", { bubbles: true }));
    inputEl.dispatchEvent?.(new Event("change", { bubbles: true }));
  }
}

function resetSaveTrigger(nodeId, force = false) {
  const key = nodeKey(nodeId);
  if (!key) return;

  const node = saverNodes.get(key);
  const widget = getWidget(node, SAVE_WIDGET);
  if (!widget || (!force && widget.value !== true)) return;

  syncWidgetValue(node, widget, false);
  widget.callback?.call(widget, false, app.canvas, node, app.canvas?.graph_mouse);
  markCanvasDirty(node);
}

function resetSaveTriggerWithUiRefresh(nodeId) {
  resetSaveTrigger(nodeId);
  requestAnimationFrame(() => resetSaveTrigger(nodeId, true));
  window.setTimeout(() => resetSaveTrigger(nodeId, true), 120);
}

function scheduleSaveTriggerReset(nodeId) {
  const runSoon = () => resetSaveTriggerWithUiRefresh(nodeId);
  if (typeof queueMicrotask === "function") {
    queueMicrotask(runSoon);
  } else {
    Promise.resolve().then(runSoon);
  }
}

function installOneShotSerializeReset(node, widget) {
  if (!node || !widget || widget.__newbieStyleSaverSerializeWrapped) return;
  const key = nodeKey(node.id);
  if (key) saverNodes.set(key, node);

  const originalSerializeValue = widget.serializeValue;
  widget.serializeValue = async function (...args) {
    const widgetValue = originalSerializeValue
      ? await originalSerializeValue.apply(this, args)
      : this.value;

    if (widgetValue === true) {
      scheduleSaveTriggerReset(node.id);
    }

    return widgetValue;
  };

  widget.__newbieStyleSaverSerializeWrapped = true;
}

function rememberSaverNode(node) {
  const key = nodeKey(node?.id);
  if (!key) return;
  saverNodes.set(key, node);
  installOneShotSerializeReset(node, getWidget(node, SAVE_WIDGET));
}

function handleExecuting(message) {
  const nextExecutingNodeId = message?.detail ?? message ?? null;
  const previousExecutingNodeId = currentExecutingNodeId;

  if (
    previousExecutingNodeId !== null &&
    nodeKey(previousExecutingNodeId) !== nodeKey(nextExecutingNodeId)
  ) {
    resetSaveTriggerWithUiRefresh(previousExecutingNodeId);
  }

  currentExecutingNodeId = nextExecutingNodeId;
}

api.addEventListener("executing", handleExecuting);

api.addEventListener("executed", (message) => {
  resetSaveTriggerWithUiRefresh(message?.detail?.node ?? message?.detail ?? message);
});

api.addEventListener("execution_error", () => {
  resetSaveTriggerWithUiRefresh(currentExecutingNodeId);
  currentExecutingNodeId = null;
});

api.addEventListener("execution_success", () => {
  resetSaveTriggerWithUiRefresh(currentExecutingNodeId);
  currentExecutingNodeId = null;
});

app.registerExtension({
  name: "newbie.llm.style.saver.auto_reset",
  async nodeCreated(node) {
    if (node?.comfyClass !== NODE_CLASS) return;
    rememberSaverNode(node);
    requestAnimationFrame(() => rememberSaverNode(node));
  },
});

export const __test__ = {
  installOneShotSerializeReset,
  rememberSaverNode,
  resetSaveTrigger,
  resetSaveTriggerWithUiRefresh,
  syncWidgetValue,
};
