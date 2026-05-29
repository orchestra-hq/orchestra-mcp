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


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    api_key = (event.get("headers") or {}).get("x-api-key")
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

    event_handler = APIGatewayProxyEventHandler(
        StdioServerAdapterRequestHandler(server_params)
    )
    return event_handler.handle(event, context)
