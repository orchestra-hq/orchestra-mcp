from __future__ import annotations

import os
import sys
from typing import Any

from mcp.client.stdio import StdioServerParameters
from mcp_lambda import APIGatewayProxyEventHandler, StdioServerAdapterRequestHandler

ORCHESTRA_ENV = os.getenv("ORCHESTRA_ENV")
if not ORCHESTRA_ENV:
    raise ValueError("Missing ORCHESTRA_ENV environment variable")

SERVER_ARGS = ["-m", "orchestramcp.server"]


def _get_api_key_from_event(event: dict[str, Any]) -> str | None:
    header_name = "x-api-key"

    headers = event.get("headers") or {}
    for key, value in headers.items():
        if isinstance(key, str) and key.lower() == header_name:
            return value

    multi_value_headers = event.get("multiValueHeaders") or {}
    for key, values in multi_value_headers.items():
        if isinstance(key, str) and key.lower() == header_name and values:
            return values[0]

    return None


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    api_key = _get_api_key_from_event(event)
    if not api_key:
        return {
            "statusCode": 401,
            "headers": {"content-type": "application/json"},
            "body": '{"message":"Missing x-api-key header"}',
        }

    server_params = StdioServerParameters(
        command=sys.executable,
        args=SERVER_ARGS,
        env={
            "ORCHESTRA_API_KEY": api_key,
            "ORCHESTRA_ENV": ORCHESTRA_ENV,
        },
    )

    event_handler = APIGatewayProxyEventHandler(StdioServerAdapterRequestHandler(server_params))
    return event_handler.handle(event, context)
