"""Isolated layout jobs and trusted, draft-keyed compilation results.

Workers never submit a ComfyUI graph or touch its global interrupt flag.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import hmac
import json
import secrets
import threading
import time
import uuid

from prompt_agent.execution_context import AgentCancelled, check_interrupted
from prompt_agent.moss_layout import validate_draft, layout_fingerprint, append_layout_input


def state_draft(state):
    if not isinstance(state, dict) or type(state.get("version")) is not int or state["version"] != 1:
        raise ValueError("不支持的布局状态版本")
    extra = state.get("summary_extra", {})
    if not isinstance(extra, dict):
        raise ValueError("全局附加字段必须为对象")
    return validate_draft({"width": state.get("width"), "height": state.get("height"),
        "bbox_coord_space": "abs", "bbox_format": "xyxy",
        "summary": {**extra, "caption": state.get("summary")}, "items": state.get("items")})


class CompilationStore:
    def __init__(self):
        self.secret = secrets.token_bytes(32)
        self.lock = threading.RLock()
        self.cache = OrderedDict()

    def _sign(self, record):
        content = json.dumps({k: record[k] for k in ("fingerprint", "prompt", "text_out")},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hmac.new(self.secret, content.encode(), hashlib.sha256).hexdigest()

    def remember(self, draft, prompt, text_out):
        if not isinstance(prompt, str) or not prompt.strip() or not isinstance(text_out, str):
            raise ValueError("MOSS 编译结果为空或格式错误")
        record = {"fingerprint": layout_fingerprint(draft), "prompt": prompt, "text_out": text_out}
        record["signature"] = self._sign(record)
        with self.lock:
            self.cache[record["fingerprint"]] = deepcopy(record)
            self.cache.move_to_end(record["fingerprint"])
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
        return record

    def compile(self, draft, saved=None):
        fingerprint = layout_fingerprint(draft)
        with self.lock:
            if isinstance(saved, dict) and saved.get("fingerprint") == fingerprint:
                try:
                    if hmac.compare_digest(str(saved.get("signature", "")), self._sign(saved)):
                        return {k: saved[k] for k in ("fingerprint", "prompt", "text_out", "signature")}
                except (KeyError, TypeError, ValueError):
                    pass
            if fingerprint in self.cache:
                return deepcopy(self.cache[fingerprint])
            from prompt_agent.tools import execute_moss_tool
            prompt = execute_moss_tool("compile_moss_prompt", {"draft": draft})
            return self.remember(draft, prompt,
                f"当前布局已编译（含人工修订）。画布尺寸：{draft['width']} × {draft['height']}；生成工作流请使用相同尺寸。")


compilations = CompilationStore()


def public_config():
    from LLM_Node import load_api_config
    config = load_api_config() or {}
    models = config.get("model_list", [])
    if not isinstance(models, list):
        models = []
    return {"models": [m for m in models if isinstance(m, str)],
            "api_configured": bool(config.get("api_key") and config.get("api_url")),
            "web_search_configured": bool(config.get("tavily_api_key"))}


def validate_request(payload):
    if not isinstance(payload, dict):
        raise ValueError("任务请求必须为对象")
    for key in ("editor_id", "input_version", "request"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ValueError(f"缺少 {key}")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise ValueError("缺少布局状态")
    for axis in ("width", "height"):
        n = state.get(axis)
        if type(n) is not int or n <= 0 or n % 16:
            raise ValueError("画布宽高必须为 16 的正整数倍")
    if type(state.get("strict_validation", True)) is not bool:
        raise ValueError("严格校验开关必须为布尔值")
    if payload.get("mode") not in ("generate", "polish"):
        raise ValueError("不支持的生成模式")
    if payload["mode"] == "polish":
        state_draft(state)
    settings = payload.get("settings", {})
    if not isinstance(settings, dict) or settings.get("effort") not in ("Close", "Low", "Medium", "High"):
        raise ValueError("不支持的努力等级")
    if not isinstance(settings.get("model"), str) or not settings["model"].strip():
        raise ValueError("请选择模型")
    if any(type(settings.get(k, False)) is not bool for k in ("thinking", "web_search", "force_full_run")):
        raise ValueError("思考与网页搜索开关必须为布尔值")
    return deepcopy(payload)


def run_layout_agent(payload, cancel, trace, owner):
    from LLM_Node import load_api_config, LLM_Prompt_Formatter
    from prompt_agent.agent_core import PromptAgent
    from prompt_agent.agent_loop import complete_moss_output
    config = load_api_config() or {}
    key, url = LLM_Prompt_Formatter._resolve_credentials(config, None, None)
    settings, state = payload["settings"], payload["state"]
    agent = PromptAgent(key, url, settings["model"], "MOSS", settings.get("thinking", False),
        config, effort=settings["effort"], unique_id=f"layout:{owner}:{payload['editor_id']}",
        enable_web_search=settings.get("web_search", False))
    agent._standalone = True
    agent._cancel_event = cancel
    agent._trace_sink = trace
    agent._layout_run_context = {**{k: v for k, v in settings.items() if k != "force_full_run"}, "mode": payload["mode"]}
    text = ("必须使用Layout模式，禁止使用caption模式。\n"
            f"当前画布宽度：{state['width']} px；高度：{state['height']} px。\n\n"
            + payload["request"])
    if payload["mode"] == "polish":
        agent._moss_layout = {"draft": state_draft(state), "strict_validation": state.get("strict_validation", True)}
        text = append_layout_input(text, agent._moss_layout)
    else:
        agent._moss_canvas = (state["width"], state["height"])
        text += (f"\n\n必须生成完整 MOSS Layout，画布固定为 {state['width']} × {state['height']}。"
                 "自由规划元素和位置，草稿使用 abs/xyxy 像素坐标；必须调用 compile_moss_prompt，禁止输出 caption。")
    try:
        check_interrupted(agent)
        if settings["effort"] == "Close":
            system, fu, fa, _, _ = LLM_Prompt_Formatter._build_normal_config("MOSS", config, url, settings["model"])
            messages = LLM_Prompt_Formatter._build_normal_messages(system, fu, fa, text, None)
            _, explanation = agent._parse_output(complete_moss_output(agent, messages))
        else:
            _, explanation = agent.run(text, force_full_run=settings.get("force_full_run", False))
        check_interrupted(agent)
        draft = validate_draft(getattr(agent, "_moss_compiled_draft", None))
        if payload["mode"] == "generate":
            explanation += f"\n\n画布尺寸：{draft['width']} × {draft['height']}；生成工作流请使用相同尺寸。"
        if payload["mode"] == "generate":
            explanation += f"\n\n画布尺寸：{draft['width']} × {draft['height']}；生成工作流请使用相同尺寸。"
        result = compilations.remember(draft, agent._moss_compiled_prompt, explanation)
        return {"draft": draft, "output": result, "input_version": payload["input_version"]}
    finally:
        agent.llm.close()


class LayoutJobs:
    ACTIVE = {"queued", "running", "cancelling"}

    def __init__(self, runner=run_layout_agent):
        self.runner = runner
        self.jobs = OrderedDict()
        self.lock = threading.RLock()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="moss-layout")

    def _prune(self):
        now = time.time()
        for key, job in list(self.jobs.items()):
            if job["status"] not in self.ACTIVE and now - job["updated"] > 1800:
                self.jobs.pop(key)
        if len(self.jobs) >= 128:
            for key, job in list(self.jobs.items()):
                if job["status"] not in self.ACTIVE:
                    self.jobs.pop(key)
                    break
        if len(self.jobs) >= 128:
            raise ValueError("布局任务较多，请稍后重试")

    def active(self, owner, editor):
        with self.lock:
            return any(j["owner"] == owner and j["editor_id"] == editor and j["status"] in self.ACTIVE for j in self.jobs.values())

    def start(self, owner, payload):
        payload = validate_request(payload)
        with self.lock:
            self._prune()
            if self.active(owner, payload["editor_id"]):
                raise ValueError("此编辑器已有任务在运行")
            job = {"job_id": str(uuid.uuid4()), "owner": owner, "editor_id": payload["editor_id"],
                "input_version": payload["input_version"], "status": "queued", "events": [],
                "updated": time.time(), "cancel": threading.Event()}
            self.jobs[job["job_id"]] = job
            self.executor.submit(self._work, job, payload)
            return self._public(job)

    def _work(self, job, payload):
        def trace(**event):
            with self.lock:
                events = job["events"]
                if (event.get("event") == "reasoning" and events
                        and events[-1].get("event") == "reasoning" and events[-1].get("title") == event.get("title")):
                    events[-1]["summary"] = (events[-1].get("summary", "") + event.get("summary", ""))[-24000:]
                else:
                    events.append({**event, "summary": str(event.get("summary", ""))[-24000:]})
                while len(events) > 80 or (len(events) > 1 and sum(len(e.get("summary", "")) for e in events) > 48000):
                    events.pop(0)
                job["updated"] = time.time()
        try:
            with self.lock:
                if job["cancel"].is_set():
                    raise AgentCancelled()
                job["status"] = "running"
            result = self.runner(payload, job["cancel"], trace, job["owner"])
            with self.lock:
                if job["cancel"].is_set():
                    raise AgentCancelled()
                job["result"] = result
                job["status"] = "succeeded"
        except AgentCancelled:
            with self.lock:
                job["status"] = "cancelled"
        except Exception as error:
            # Provider exceptions can contain credentials/URLs. Keep them off HTTP responses.
            from prompt_agent.diagnostics import write_agent_error_log, format_agent_error_summary
            path = write_agent_error_log(error, context={"purpose": "MOSS Layout job", "job_id": job["job_id"]})
            print(f"[MOSS Layout] {format_agent_error_summary(error)}; diagnostics: {path}")
            with self.lock:
                job["status"] = "cancelled" if job["cancel"].is_set() else "failed"
                job["error"] = "布局生成失败，请查看 ComfyUI 控制台诊断。原布局已保留。"
        finally:
            with self.lock:
                job["updated"] = time.time()

    @staticmethod
    def _public(job):
        return deepcopy({k: v for k, v in job.items() if k not in ("owner", "cancel", "updated")})

    def get(self, owner, job_id, cancel=False):
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job["owner"] != owner or (job["status"] not in self.ACTIVE and time.time() - job["updated"] > 1800):
                raise KeyError(job_id)
            if cancel and job["status"] in self.ACTIVE:
                job["cancel"].set()
                job["status"] = "cancelling"
            return self._public(job)

    def latest(self, owner, editor):
        with self.lock:
            for job in reversed(list(self.jobs.values())):
                if job["owner"] == owner and job["editor_id"] == editor and (job["status"] in self.ACTIVE or time.time() - job["updated"] <= 1800):
                    return self._public(job)
        raise KeyError(editor)


jobs = LayoutJobs()
