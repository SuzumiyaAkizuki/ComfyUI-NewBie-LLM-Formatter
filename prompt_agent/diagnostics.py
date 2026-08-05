"""Safe Agent error summaries and full redacted diagnostic logs."""

import json
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from prompt_agent.console import _log_error


_ERROR_DIR = Path(__file__).resolve().parent.parent / "error"
_SENSITIVE_HEADERS = {
    "authorization", "proxy-authorization", "x-api-key", "api-key",
    "cookie", "set-cookie",
}
_SENSITIVE_QUERY_KEYS = {"api_key", "apikey", "key", "token", "access_token"}


def _redact_headers(headers):
    """保留诊断所需请求头，但绝不把认证信息写进日志。"""
    if headers is None:
        return None
    try:
        items = headers.items()
    except Exception:
        return str(headers)
    return {
        str(key): "<redacted>" if str(key).lower() in _SENSITIVE_HEADERS else str(value)
        for key, value in items
    }


def _redact_url(url):
    if not url:
        return None
    try:
        parts = urlsplit(str(url))
        query = urlencode([
            (key, "<redacted>" if key.lower() in _SENSITIVE_QUERY_KEYS else value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
        ])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:
        return str(url)


def _body_text(message):
    if message is None:
        return None
    for attr in ("text", "content"):
        try:
            value = getattr(message, attr, None)
        except Exception:
            continue
        if value is None:
            continue
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)
    return None


def format_agent_error_summary(error):
    """生成可安全展示在控制台的短摘要，不包含响应体。"""
    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(getattr(error, "response", None), "status_code", None)
    suffix = f" (HTTP {status})" if status is not None else ""
    return f"{type(error).__name__}{suffix}"


def _http_exchange(error):
    request = getattr(error, "request", None)
    response = getattr(error, "response", None)
    return {
        "request": None if request is None else {
            "method": getattr(request, "method", None),
            "url": _redact_url(getattr(request, "url", None)),
            "headers": _redact_headers(getattr(request, "headers", None)),
            "body": _body_text(request),
        },
        "response": None if response is None else {
            "status_code": getattr(response, "status_code", None),
            "reason_phrase": getattr(response, "reason_phrase", None),
            "headers": _redact_headers(getattr(response, "headers", None)),
            "body": _body_text(response),
        },
    }


def _new_error_log_path(error_dir=None):
    target_dir = Path(error_dir) if error_dir is not None else _ERROR_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S-%f")
    return target_dir / f"{timestamp}.log"


def write_agent_error_log(
        error, *, context=None, completion_args=None, completion_response=None,
        log_path=None, error_dir=None):
    """把完整 Agent 错误诊断写入项目 error 目录；同一重试链追加到同一文件。"""
    try:
        path = Path(log_path) if log_path else _new_error_log_path(error_dir)
        exchange = _http_exchange(error)
        record = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "context": context or {},
            "environment": {
                "python": sys.version,
                "platform": platform.platform(),
            },
            "exception": {
                "type": type(error).__name__,
                "message": str(error),
                "repr": repr(error),
                "traceback": "".join(traceback.format_exception(
                    type(error), error, error.__traceback__,
                )),
            },
            "completion_arguments": completion_args,
            "completion_response": completion_response,
            "sdk_http": exchange,
        }
        with path.open("a", encoding="utf-8") as handle:
            if path.stat().st_size > 0:
                handle.write("\n\n" + "=" * 80 + "\n")
            json.dump(record, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        try:
            setattr(error, "_agent_error_log_path", str(path))
        except Exception:
            pass
        return str(path)
    except Exception as log_error:
        _log_error(f"错误诊断日志写入失败: {format_agent_error_summary(log_error)}")
        return None
