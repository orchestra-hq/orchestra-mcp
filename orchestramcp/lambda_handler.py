import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import anyio
from mcp_lambda import APIGatewayProxyEventV2Handler

from orchestramcp.in_process_request_handler import (
    INTERNAL_FAILURE_MESSAGE,
    RESPONSE_TOO_LARGE_MESSAGE,
    FastMCPInProcessRequestHandler,
)
from orchestramcp.oauth import OAuthTokenError, resolve_api_key
from orchestramcp.server import get_client

logger = logging.getLogger("orchestramcp.lambda_handler")
logger.setLevel(logging.ERROR)

_event_handler = APIGatewayProxyEventV2Handler(FastMCPInProcessRequestHandler())


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


def _apply_request_credentials(api_key: str | None) -> None:
    if api_key:
        os.environ["ORCHESTRA_API_KEY"] = api_key
    else:
        os.environ.pop("ORCHESTRA_API_KEY", None)
    get_client.cache_clear()


# The JSON-RPC error bodies produced by the in-process handler are small; anything
# larger is a successful result and cannot be one of the alerted errors.
_MAX_ERROR_BODY_BYTES = 4096


def _extract_jsonrpc_error_message(body: Any) -> str:
    if not isinstance(body, str) or len(body) > _MAX_ERROR_BODY_BYTES:
        return ""
    try:
        parsed = json.loads(body)
    except ValueError:
        return ""
    if not isinstance(parsed, dict):
        return ""
    error = parsed.get("error")
    if not isinstance(error, dict):
        return ""
    message = error.get("message")
    return message if isinstance(message, str) else ""


def _log_mcp_error_event_if_present(response: dict[str, Any], context: Any) -> None:
    message = _extract_jsonrpc_error_message(response.get("body"))
    if not message:
        return
    if INTERNAL_FAILURE_MESSAGE in message:
        _log_error_event(
            "mcp_in_process_internal_failure",
            context,
            RuntimeError("MCP in-process handler returned internal failure"),
        )
    if RESPONSE_TOO_LARGE_MESSAGE in message:
        _log_error_event(
            "mcp_response_too_large",
            context,
            RuntimeError("MCP response exceeded the maximum payload size"),
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
        method = _get_http_method(event)
        bearer_token = _extract_bearer_token(event)
        if method == "POST" and not bearer_token:
            return {
                "statusCode": 401,
                "headers": {"content-type": "application/json"},
                "body": '{"message":"Missing or invalid Authorization header"}',
            }

        _resolve_orchestra_env()
        try:
            api_key = anyio.run(resolve_api_key, bearer_token) if bearer_token else None
        except OAuthTokenError as exc:
            _log_error_event("oauth_token_invalid", context, exc)
            return {
                "statusCode": 401,
                "headers": {"content-type": "application/json"},
                "body": '{"message":"Invalid or expired OAuth token"}',
            }
        _apply_request_credentials(api_key)
        response = _event_handler.handle(event, context)
        _log_mcp_error_event_if_present(response, context)
        return response
    except Exception as exc:
        if isinstance(exc, ConfigInvalidError):
            event_name = "config_invalid"
        else:
            event_name = "lambda_handler_unhandled_exception"
        _log_error_event(event_name, context, exc)
        raise
