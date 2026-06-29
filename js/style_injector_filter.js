import { app } from "../../scripts/app.js";

const NODE_CLASS = "LLM_Xml_Style_Injector";
const MODE_WIDGET = "mode";
const PRESET_WIDGET = "preset";
const PREFIX_RE = /^\[(NewBie|Anima|Both)\]\s*/;

function getWidget(node, name) {
  return node?.widgets?.find((widget) => widget.name === name);
}

function getValues(widget) {
  const values = widget?.options?.values;
  return Array.isArray(values) ? values : [];
}

function setValues(widget, values) {
  if (!widget.options) widget.options = {};
  widget.options.values = values;
}

function splitPreset(value) {
  const text = String(value ?? "");
  const match = text.match(PREFIX_RE);
  if (!match) {
    return { value: text, mode: null, raw: text.trim() };
  }
  return {
    value: text,
    mode: match[1],
    raw: text.replace(PREFIX_RE, "").trim(),
  };
}

function isAllowedMode(presetMode, selectedMode) {
  return presetMode === selectedMode || presetMode === "Both";
}

function buildPresetIndex(values) {
  const prefixed = [];
  const byRawAndMode = new Map();

  for (const value of values) {
    const preset = splitPreset(value);
    if (preset.mode) {
      prefixed.push(preset);
      byRawAndMode.set(`${preset.raw}\u0000${preset.mode}`, preset.value);
      if (preset.mode === "Both") {
        byRawAndMode.set(`${preset.raw}\u0000NewBie`, preset.value);
        byRawAndMode.set(`${preset.raw}\u0000Anima`, preset.value);
      }
    }
  }

  return { prefixed, byRawAndMode };
}

function resolveCurrentValue(currentValue, selectedMode, index) {
  const current = splitPreset(currentValue);
  if (current.mode && isAllowedMode(current.mode, selectedMode)) {
    return current.value;
  }
  return index.byRawAndMode.get(`${current.raw}\u0000${selectedMode}`) ?? null;
}

function filterPresetWidget(node) {
  const modeWidget = getWidget(node, MODE_WIDGET);
  const presetWidget = getWidget(node, PRESET_WIDGET);
  if (!modeWidget || !presetWidget) return;

  const originalValues = node.__newbieStylePresetValues ?? getValues(presetWidget).slice();
  node.__newbieStylePresetValues = originalValues;

  const selectedMode = modeWidget.value === "Anima" ? "Anima" : "NewBie";
  const index = buildPresetIndex(originalValues);
  const filteredValues = index.prefixed
    .filter((preset) => isAllowedMode(preset.mode, selectedMode))
    .map((preset) => preset.value);

  let nextValue = resolveCurrentValue(presetWidget.value, selectedMode, index);
  if (!nextValue && filteredValues.includes(presetWidget.value)) {
    nextValue = presetWidget.value;
  }
  if (!nextValue && presetWidget.value && !splitPreset(presetWidget.value).mode) {
    nextValue = presetWidget.value;
    filteredValues.push(presetWidget.value);
  }
  if (!nextValue) {
    nextValue = filteredValues[0] ?? "";
  }

  setValues(presetWidget, filteredValues);
  presetWidget.value = nextValue;

  node.setDirtyCanvas?.(true, true);
}

function wrapModeCallback(node) {
  const modeWidget = getWidget(node, MODE_WIDGET);
  if (!modeWidget || modeWidget.__newbieStyleFilterWrapped) return;

  const originalCallback = modeWidget.callback;
  modeWidget.callback = function (...args) {
    const result = originalCallback?.apply(this, args);
    filterPresetWidget(node);
    return result;
  };
  modeWidget.__newbieStyleFilterWrapped = true;
}

function wrapConfigure(node) {
  if (node.__newbieStyleFilterConfigureWrapped) return;

  const originalOnConfigure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = originalOnConfigure?.apply(this, args);
    requestAnimationFrame(() => filterPresetWidget(node));
    return result;
  };
  node.__newbieStyleFilterConfigureWrapped = true;
}

app.registerExtension({
  name: "newbie.llm.style.injector.filter",
  async nodeCreated(node) {
    if (node?.comfyClass !== NODE_CLASS) return;
    wrapModeCallback(node);
    wrapConfigure(node);
    requestAnimationFrame(() => filterPresetWidget(node));
  },
});
