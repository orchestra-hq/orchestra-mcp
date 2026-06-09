import os
from unittest.mock import MagicMock

import pytest
from mcp.types import JSONRPCError, JSONRPCRequest, JSONRPCResponse

from orchestramcp.in_process_request_handler import FastMCPInProcessRequestHandler
from orchestramcp.server import get_client

EXPECTED_TOOLS = {
    "cancel_pipeline_run",
    "download_task_run_artifact",
    "download_task_run_log",
    "get_pipeline_run_status",
    "import_pipeline",
    "list_assets",
    "list_operations",
    "list_pipeline_runs",
    "list_task_run_artifacts",
    "list_task_run_logs",
    "list_task_runs",
    "start_pipeline",
}


@pytest.fixture
def handler():
    return FastMCPInProcessRequestHandler()


@pytest.fixture
def lambda_context():
    context = MagicMock()
    context.aws_request_id = "test-request-id"
    return context


@pytest.fixture
def set_api_key():
    get_client.cache_clear()
    os.environ["ORCHESTRA_API_KEY"] = "test-api-key"
    os.environ["ORCHESTRA_ENV"] = "app"
    yield
    os.environ.pop("ORCHESTRA_API_KEY", None)
    os.environ.pop("ORCHESTRA_ENV", None)
    get_client.cache_clear()


def _make_request(method: str, params: dict | None = None, req_id: int = 1) -> JSONRPCRequest:
    return JSONRPCRequest(
        jsonrpc="2.0",
        id=req_id,
        method=method,
        params=params,
    )


def test_initialize_returns_server_info(handler, lambda_context, set_api_key):
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
    assert response.id == 1
    assert "serverInfo" in response.result
    assert response.result["serverInfo"]["name"] == "Orchestra MCP Server"


def test_tools_list_returns_registered_tools(handler, lambda_context, set_api_key):
    response = handler.handle_request(_make_request("tools/list"), lambda_context)

    assert isinstance(response, JSONRPCResponse)
    tool_names = {tool["name"] for tool in response.result["tools"]}
    assert EXPECTED_TOOLS.issubset(tool_names)


def test_api_key_isolation_with_cache_clear(set_api_key):
    os.environ["ORCHESTRA_API_KEY"] = "key-a"
    get_client.cache_clear()
    assert get_client().api_key == "key-a"

    os.environ["ORCHESTRA_API_KEY"] = "key-b"
    get_client.cache_clear()
    assert get_client().api_key == "key-b"


def test_unknown_method_returns_jsonrpc_error(handler, lambda_context, set_api_key):
    response = handler.handle_request(_make_request("nonexistent/method"), lambda_context)

    assert isinstance(response, JSONRPCError)
    assert response.id == 1
