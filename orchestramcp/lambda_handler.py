import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

from mangum import Mangum
from starlette.middleware.cors import CORSMiddleware

from orchestramcp.auth import get_mcp_path
from orchestramcp.server import mcp

logger = logging.getLogger("orchestramcp.lambda_handler")
logger.setLevel(logging.ERROR)


class ConfigInvalidError(ValueError):
    pass


# FastMCP's streamable-HTTP ASGI app serves the MCP endpoint and, when OAuth is
# configured, the RFC 9728 Protected Resource Metadata at /.well-known/* plus
# the WWW-Authenticate 401 challenge. Lambda invocations are independent, so
# the transport is stateless, and responses are buffered, so plain JSON beats
# SSE framing.
_app = mcp.http_app(path=get_mcp_path(), transport="http", stateless_http=True, json_response=True)
_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["mcp-session-id", "mcp-protocol-version"],
)
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


def _ensure_event_loop() -> None:
    # Mangum resolves its loop via asyncio.get_event_loop(), which on Python
    # 3.12+ no longer creates one. The Lambda runtime is single-threaded, so a
    # persistent loop per process is safe (and lets warm invocations reuse it).
    try:
        if asyncio.get_event_loop().is_closed():
            raise RuntimeError
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _require_orchestra_env() -> None:
    # Without this the client would default to the production API, so a
    # misconfigured stage Lambda would silently serve production data.
    if not os.getenv("ORCHESTRA_ENV", "").strip():
        raise ConfigInvalidError("Missing ORCHESTRA_ENV environment variable")


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        _require_orchestra_env()
        _ensure_event_loop()
        return _mangum(event, context)
    except Exception as exc:
        if isinstance(exc, ConfigInvalidError):
            event_name = "config_invalid"
        else:
            event_name = "lambda_handler_unhandled_exception"
        _log_error_event(event_name, context, exc)
        raise
