"""HTTP facade for node-local jobs. All LLM work runs on worker threads."""
from aiohttp import web
from prompt_agent.layout_tasks import jobs, public_config

PREFIX = "/newbie/moss-layout"


def owner(request):
    value = request.headers.get("X-Moss-Client-Id", "")
    if not value or len(value) > 128:
        raise web.HTTPBadRequest(text="缺少编辑器会话")
    return value


async def config(request):
    return web.json_response(public_config())


async def start(request):
    client = owner(request)
    try:
        return web.json_response(jobs.start(client, await request.json()))
    except (ValueError, TypeError) as error:
        raise web.HTTPBadRequest(text=str(error))


async def job(request):
    try:
        return web.json_response(jobs.get(owner(request), request.match_info["job_id"], request.method == "DELETE"))
    except KeyError:
        raise web.HTTPNotFound(text="任务不存在或已过期")


async def latest(request):
    try:
        return web.json_response(jobs.latest(owner(request), request.query.get("editor_id", "")))
    except KeyError:
        raise web.HTTPNotFound(text="任务不存在或服务已重启")


async def accept(request):
    try:
        return web.json_response(jobs.accept(owner(request), request.match_info["job_id"]))
    except KeyError:
        raise web.HTTPNotFound(text="任务不存在或会话已清空")


async def reset(request):
    try:
        return web.json_response(jobs.reset(owner(request), (await request.json()).get("editor_id")))
    except (ValueError, TypeError, AttributeError) as error:
        raise web.HTTPBadRequest(text=str(error))


async def session(request):
    return web.json_response(jobs.history(owner(request), request.query.get("editor_id", "")))


def register_layout_routes():
    from server import PromptServer
    routes = PromptServer.instance.routes
    routes.get(PREFIX + "/config")(config)
    routes.post(PREFIX + "/jobs")(start)
    routes.post(PREFIX + "/jobs/{job_id}/accept")(accept)
    routes.post(PREFIX + "/reset")(reset)
    routes.get(PREFIX + "/session")(session)
    routes.get(PREFIX + "/latest")(latest)
    routes.get(PREFIX + "/jobs/{job_id}")(job)
    routes.delete(PREFIX + "/jobs/{job_id}")(job)
