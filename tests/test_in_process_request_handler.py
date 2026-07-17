from unittest.mock import MagicMock

import pytest
from mcp.types import JSONRPCError, JSONRPCRequest, JSONRPCResponse

import orchestramcp.in_process_request_handler as iprh
from orchestramcp.in_process_request_handler import (
    MAX_RESPONSE_BYTES,
    FastMCPInProcessRequestHandler,
)


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


def test_oversized_response_returns_error_and_logs_tool(
    handler, lambda_context, monkeypatch, caplog
):
    async def oversized(request_dict):
        return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "x" * (MAX_RESPONSE_BYTES + 1)}]},
        }

    monkeypatch.setattr(iprh, "_forward_request", oversized)

    with caplog.at_level("ERROR"):
        response = handler.handle_request(
            _make_request("tools/call", {"name": "download_task_run_artifact", "arguments": {}}),
            lambda_context,
        )

    assert isinstance(response, JSONRPCError)
    assert "range_header" in response.error.message
    assert "tool 'download_task_run_artifact'" in response.error.message
    assert any(
        "MCP response too large" in record.message
        and "download_task_run_artifact" in record.message
        for record in caplog.records
    )


def test_guard_accounts_for_proxy_envelope_escaping():
    # 1.5MiB of quotes serializes to ~3MiB of body (under the 5MiB limit), but the
    # proxy envelope escapes it again to ~6MiB — the guard must measure that form.
    text = '"' * int(1.5 * 1024 * 1024)
    response_dict = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"type": "text", "text": text}]},
    }

    error = iprh._guard_response_size(_make_request("tools/call", {"name": "t"}), response_dict)

    assert error is not None
    assert "Response exceeds the maximum MCP payload size" in error.error.message
