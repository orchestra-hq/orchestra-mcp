from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from mangum import Mangum

from orchestramcp.auth import get_mcp_path
from orchestramcp.server import mcp

logger = logging.getLogger("orchestramcp.lambda_handler")
logger.setLevel(logging.ERROR)

# Public path the MCP endpoint is served on. Must match the route forwarded by
# API Gateway (e.g. the custom-domain mapping for https://mcp.getorchestra.io/orchestra).
_MCP_PATH = get_mcp_path()

# Run FastMCP's streamable-HTTP ASGI app. This serves the MCP endpoint AND, when
# OAuth is configured, the RFC 9728 Protected Resource Metadata at
# /.well-known/oauth-protected-resource plus the WWW-Authenticate 401 challenge.
# Each Lambda invocation is independent, so the transport is stateless.
_app = mcp.http_app(path=_MCP_PATH, transport="http", stateless_http=True)
_mangum = Mangum(_app, lifespan="auto")


def _timestamp_utc() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sanitize_message(value: str) -> str:
    return value.replace("\n", " ").replace('"', "'").strip()


def _log_error_event(event_name: str, context: Any, error: BaseException) -> None:
    request_id = getattr(context, "aws_request_id", "-")
    error_type = type(error).__name__
    message = _sanitize_message(str(error)) or "unknown"
    logger.error(
        '%s flags=Y %s error event=%s request_id=%s error_type=%s message="%s"',
        "orchestra-mcp",
        _timestamp_utc(),
        event_name,
        request_id,
        error_type,
        message,
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        return _mangum(event, context)
    except Exception as exc:
        _log_error_event("lambda_handler_unhandled_exception", context, exc)
        raise
