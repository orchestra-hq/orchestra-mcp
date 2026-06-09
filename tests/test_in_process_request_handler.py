from unittest.mock import MagicMock

import pytest
from mcp.types import JSONRPCError, JSONRPCRequest, JSONRPCResponse

from orchestramcp.in_process_request_handler import FastMCPInProcessRequestHandler


@pytest.fixture
def handler():
    return FastMCPInProcessRequestHandler()


@pytest.fixture
def lambda_context():
    context = MagicMock()
    context.aws_request_id = "test-request-id"
    return context


def _make_request(method: str, params: dict | None = None) -> JSONRPCRequest:
    return JSONRPCRequest(jsonrpc="2.0", id=1, method=method, params=params)


def test_initialize_returns_server_info(handler, lambda_context):
    response = handler.handle_request(
        _make_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        ),
        lambda_context,
    )

    assert isinstance(response, JSONRPCResponse)
    assert response.result["serverInfo"]["name"] == "Orchestra MCP Server"


def test_unknown_method_returns_jsonrpc_error(handler, lambda_context):
    response = handler.handle_request(_make_request("nonexistent/method"), lambda_context)

    assert isinstance(response, JSONRPCError)
