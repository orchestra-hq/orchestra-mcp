from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from mcp.client.stdio import StdioServerParameters
from mcp_lambda import (
    APIGatewayProxyEventV2Handler,
    StdioServerAdapterRequestHandler,
)

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


def _get_http_method(event: dict[str, Any]) -> str:
    return event["requestContext"]["http"]["method"].upper()


def _extract_bearer_token(event: dict[str, Any]) -> str | None:
    headers = {key.lower(): value for key, value in event.get("headers", {}).items()}
    authorization = headers.get("authorization")
    if not authorization:
        return None

    parts = authorization.strip().split(maxsplit=1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1].strip()
    return token or None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    try:
        orchestra_env = _resolve_orchestra_env()

        method = _get_http_method(event)
        api_key = _extract_bearer_token(event)
        if method == "POST" and not api_key:
            return {
                "statusCode": 401,
                "headers": {"content-type": "application/json"},
                "body": '{"message":"Missing or invalid Authorization header"}',
            }

        mcp_env = {"ORCHESTRA_ENV": orchestra_env}
        if api_key:
            mcp_env["ORCHESTRA_API_KEY"] = api_key

        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "orchestramcp.server_lambda"],
            env=mcp_env,
        )

        event_handler = APIGatewayProxyEventV2Handler(
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
