"""Lightweight UI trace events for the ComfyUI Agent node."""

from __future__ import annotations

import time
from typing import Any

EVENT_NAME = "newbie_llm_agent_trace"


def _get_prompt_server():
    try:
        from server import PromptServer
    except Exception:
        return None
    return getattr(PromptServer, "instance", None)


def emit_agent_trace(
    node_id: str | None,
    event: str,
    *,
    status: str = "info",
    title: str = "",
    summary: str = "",
    details: dict[str, Any] | None = None,
) -> bool:
    """Send one node-scoped Agent trace event to the ComfyUI browser."""
    if not node_id:
        return False
    server = _get_prompt_server()
    if server is None or not hasattr(server, "send_sync"):
        return False

    payload = {
        "node_id": str(node_id),
        "event": event,
        "status": status,
        "title": title,
        "summary": summary,
        "details": details or {},
        "timestamp": time.time(),
    }
    server.send_sync(EVENT_NAME, payload, getattr(server, "client_id", None))
    return True
