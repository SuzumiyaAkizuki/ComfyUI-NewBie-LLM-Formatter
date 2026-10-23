"""Cancellation shared by workflow runs and isolated editor jobs."""


class AgentCancelled(Exception):
    pass


def check_interrupted(agent):
    event = getattr(agent, "_cancel_event", None)
    if event is not None:
        if event.is_set():
            raise AgentCancelled("布局 Agent 已取消")
        return
    try:
        import comfy.model_management
    except ImportError:
        return
    comfy.model_management.throw_exception_if_processing_interrupted()
