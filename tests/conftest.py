import json
import os

import pytest

from orchestramcp.api_contract import TOOL_CONTRACTS
from orchestramcp.server import get_client

# Tools gated behind ORCHESTRA_ENABLE_DELETE, so not registered by default.
CONDITIONAL_TOOLS = {"delete_pipeline", "delete_environment"}
# Tools that make no API call and so have no api_contract entry.
NON_API_TOOLS = {"get_pipeline_run_lineage_url"}

# The tools registered by default. Derived from the contract so that adding a tool
# there (the required step for any new API-backed tool) keeps the tests in sync
# automatically, instead of maintaining a hand-written list in two places.
EXPECTED_TOOLS = ({c.tool for c in TOOL_CONTRACTS} - CONDITIONAL_TOOLS) | NON_API_TOOLS

MCP_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


@pytest.fixture(autouse=True)
def orchestra_env():
    os.environ["ORCHESTRA_ENV"] = "app"
    yield
    os.environ.pop("ORCHESTRA_ENV", None)
    os.environ.pop("ORCHESTRA_API_KEY", None)
    get_client.cache_clear()


def api_gateway_event(
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} /orchestra",
        "rawPath": "/orchestra",
        "rawQueryString": "",
        "headers": headers or {},
        "requestContext": {"http": {"method": method, "path": "/orchestra"}},
        "body": body,
    }


def mcp_post_event(method: str, params: dict | None = None, api_key: str = "test-api-key") -> dict:
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {api_key}"}
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
    )
    return api_gateway_event(method="POST", headers=headers, body=body)
