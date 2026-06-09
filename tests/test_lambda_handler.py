import json
import os
from unittest.mock import MagicMock

import pytest

from orchestramcp.lambda_handler import handler
from orchestramcp.server import get_client
from tests.conftest import EXPECTED_TOOLS, api_gateway_event, mcp_post_event


@pytest.fixture
def lambda_context():
    context = MagicMock()
    context.aws_request_id = "test-request-id"
    return context


def test_post_without_bearer_returns_401(lambda_context):
    response = handler(api_gateway_event(method="POST"), lambda_context)

    assert response["statusCode"] == 401


def test_options_returns_cors_and_clears_stale_api_key(lambda_context):
    os.environ["ORCHESTRA_API_KEY"] = "stale-key"

    response = handler(api_gateway_event(method="OPTIONS"), lambda_context)

    assert response["statusCode"] == 200
    assert "ORCHESTRA_API_KEY" not in os.environ


def test_initialize_via_lambda_handler(lambda_context):
    response = handler(
        mcp_post_event(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        ),
        lambda_context,
    )

    body = json.loads(response["body"])
    assert response["statusCode"] == 200
    assert body["result"]["serverInfo"]["name"] == "Orchestra MCP Server"


def test_tools_list_via_lambda_handler(lambda_context):
    response = handler(mcp_post_event("tools/list"), lambda_context)

    body = json.loads(response["body"])
    tool_names = {tool["name"] for tool in body["result"]["tools"]}
    assert EXPECTED_TOOLS.issubset(tool_names)


def test_api_key_isolated_between_requests(lambda_context):
    handler(mcp_post_event("initialize", _initialize_params(), api_key="key-a"), lambda_context)
    assert get_client().api_key == "key-a"

    handler(mcp_post_event("initialize", _initialize_params(), api_key="key-b"), lambda_context)
    assert get_client().api_key == "key-b"


def _initialize_params() -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    }
