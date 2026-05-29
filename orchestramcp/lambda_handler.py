from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from mcp.client.stdio import StdioServerParameters
from mcp_lambda import APIGatewayProxyEventHandler, StdioServerAdapterRequestHandler

logger = logging.getLogger("orchestramcp.lambda_handler")
logger.setLevel(logging.ERROR)


class ConfigInvalidError(ValueError):
    pass


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


def _resolve_orchestra_env() -> str:
    env = os.getenv("ORCHESTRA_ENV", "").strip()
    if env:
        return env
    raise ConfigInvalidError("Missing ORCHESTRA_ENV environment variable")


def _log_mcp_internal_failure_if_present(response: dict[str, Any], context: Any) -> None:
    body = response.get("body")
    if not isinstance(body, str) or "Internal failure, please check Lambda function logs" not in body:
        return
    _log_error_event(
        "mcp_subprocess_nonzero_exit",
        context,
        RuntimeError("MCP subprocess returned internal failure"),
    )


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        orchestra_env = _resolve_orchestra_env()

        api_key = (event.get("headers") or {}).get("x-api-key")
        if not api_key:
            return {
                "statusCode": 401,
                "headers": {"content-type": "application/json"},
                "body": '{"message":"Missing x-api-key header"}',
            }

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "orchestramcp.server"],
            env={
                "ORCHESTRA_API_KEY": api_key,
                "ORCHESTRA_ENV": orchestra_env,
            },
        )

        event_handler = APIGatewayProxyEventHandler(
            StdioServerAdapterRequestHandler(server_params)
        )
        response = event_handler.handle(event, context)
        _log_mcp_internal_failure_if_present(response, context)
        return response
    except Exception as exc:
        if isinstance(exc, ConfigInvalidError):
            event_name = "config_invalid"
        elif isinstance(exc, OSError):
            event_name = "mcp_subprocess_start_failed"
        else:
            event_name = "lambda_handler_unhandled_exception"
        _log_error_event(event_name, context, exc)
        raise
