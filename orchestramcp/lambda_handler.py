from __future__ import annotations

import os
import sys
from typing import Any

from mcp.client.stdio import StdioServerParameters
from mcp_lambda import stdio_server_adapter

SERVER_ARGS = ["-m", "orchestramcp.server"]
ORCHESTRA_API_KEY = os.getenv("ORCHESTRA_API_KEY")
SERVER_ENV = {"ORCHESTRA_API_KEY": ORCHESTRA_API_KEY} if ORCHESTRA_API_KEY is not None else {}

SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=SERVER_ARGS,
    env=SERVER_ENV,
)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return stdio_server_adapter(SERVER_PARAMS, event, context)
