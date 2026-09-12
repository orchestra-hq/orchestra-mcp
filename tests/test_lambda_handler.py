import json
import os
from unittest.mock import MagicMock

import pytest

from orchestramcp import oauth
from orchestramcp.lambda_handler import handler
from tests.conftest import EXPECTED_TOOLS, api_gateway_event, mcp_post_event


@pytest.fixture
def lambda_context():
    context = MagicMock()
    context.aws_request_id = "test-request-id"
    return context


ISSUER = "https://app.getorchestra.io"
RESOURCE_URL = "https://mcp.getorchestra.io/orchestra"
METADATA_PATH = "/orchestra/.well-known/oauth-protected-resource"


def _enable_oauth(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("ORCHESTRA_OAUTH_JWKS_URI", f"{ISSUER}/.well-known/jwks.json")
    monkeypatch.setenv("ORCHESTRA_OAUTH_RESOURCE_URL", RESOURCE_URL)


def test_post_without_bearer_returns_401(lambda_context):
    response = handler(api_gateway_event(method="POST"), lambda_context)

    assert response["statusCode"] == 401
    assert "www-authenticate" not in response["headers"]


def test_post_without_bearer_challenges_with_the_metadata_pointer(lambda_context, monkeypatch):
    _enable_oauth(monkeypatch)

    response = handler(api_gateway_event(method="POST"), lambda_context)

    assert response["statusCode"] == 401
    assert response["headers"]["www-authenticate"] == (
        'Bearer error="invalid_request", error_description="Missing or invalid Authorization '
        f'header", resource_metadata="{RESOURCE_URL}/.well-known/oauth-protected-resource"'
    )


def test_unverifiable_token_is_challenged_rather_than_forwarded(lambda_context, monkeypatch):
    _enable_oauth(monkeypatch)

    async def _reject(token):
        return False

    monkeypatch.setattr(oauth, "token_accepted", _reject)

    response = handler(
        mcp_post_event("initialize", api_key="header.payload.signature"), lambda_context
    )

    assert response["statusCode"] == 401
    assert 'error="invalid_token"' in response["headers"]["www-authenticate"]


def test_discovery_document_served_under_the_routed_prefix(lambda_context, monkeypatch):
    _enable_oauth(monkeypatch)

    response = handler(api_gateway_event(method="GET", raw_path=METADATA_PATH), lambda_context)

    assert response["statusCode"] == 200
    assert json.loads(response["body"])["resource"] == RESOURCE_URL


def test_preflight_on_the_discovery_path_is_answered_by_mcp_lambda(lambda_context, monkeypatch):
    _enable_oauth(monkeypatch)

    response = handler(api_gateway_event(method="OPTIONS", raw_path=METADATA_PATH), lambda_context)

    assert response["statusCode"] == 200
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_get_on_the_mcp_path_still_405s(lambda_context, monkeypatch):
    _enable_oauth(monkeypatch)

    response = handler(api_gateway_event(method="GET"), lambda_context)

    assert response["statusCode"] == 405


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


def test_api_key_applied_per_request(lambda_context):
    handler(mcp_post_event("initialize", _initialize_params(), api_key="key-a"), lambda_context)
    assert os.environ["ORCHESTRA_API_KEY"] == "key-a"

    handler(mcp_post_event("initialize", _initialize_params(), api_key="key-b"), lambda_context)
    assert os.environ["ORCHESTRA_API_KEY"] == "key-b"


def _initialize_params() -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1.0"},
    }


def test_error_event_logged_for_jsonrpc_error_body(lambda_context, caplog):
    from orchestramcp.lambda_handler import _log_mcp_error_event_if_present

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32603, "message": "Response exceeds the maximum MCP payload size"},
        }
    )

    with caplog.at_level("ERROR"):
        _log_mcp_error_event_if_present({"statusCode": 200, "body": body}, lambda_context)

    assert any("mcp_response_too_large" in record.getMessage() for record in caplog.records)


def test_no_error_event_for_success_body_containing_marker(lambda_context, caplog):
    from orchestramcp.lambda_handler import _log_mcp_error_event_if_present

    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "content": [
                    {"type": "text", "text": "Response exceeds the maximum MCP payload size"}
                ]
            },
        }
    )

    with caplog.at_level("ERROR"):
        _log_mcp_error_event_if_present({"statusCode": 200, "body": body}, lambda_context)

    assert not caplog.records
