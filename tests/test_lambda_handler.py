import importlib
import json
from unittest.mock import MagicMock

import pytest

import orchestramcp.lambda_handler
import orchestramcp.server
from orchestramcp.auth import OrchestraApiKeyVerifier
from orchestramcp.lambda_handler import ConfigInvalidError, handler
from tests.conftest import EXPECTED_TOOLS, api_gateway_event, mcp_post_event

OAUTH_ENV = {
    "MCP_OAUTH_ISSUER": "https://auth.example.com",
    "MCP_OAUTH_JWKS_URI": "https://auth.example.com/.well-known/jwks.json",
    "MCP_PUBLIC_BASE_URL": "https://mcp.getorchestra.io/orchestra",
}


@pytest.fixture
def lambda_context():
    context = MagicMock()
    context.aws_request_id = "test-request-id"
    return context


@pytest.fixture
def valid_api_key(monkeypatch):
    async def accept(api_key):
        return True

    monkeypatch.setattr(OrchestraApiKeyVerifier, "_probe", staticmethod(accept))


def test_post_without_bearer_returns_401(lambda_context):
    response = handler(api_gateway_event(method="POST"), lambda_context)

    assert response["statusCode"] == 401


def test_missing_orchestra_env_raises(lambda_context, monkeypatch):
    monkeypatch.delenv("ORCHESTRA_ENV", raising=False)

    with pytest.raises(ConfigInvalidError):
        handler(api_gateway_event(method="POST"), lambda_context)


def test_options_preflight_returns_cors_headers(lambda_context):
    response = handler(
        api_gateway_event(
            method="OPTIONS",
            headers={
                "Origin": "https://claude.ai",
                "Access-Control-Request-Method": "POST",
            },
        ),
        lambda_context,
    )

    assert response["statusCode"] == 200
    assert response["headers"]["access-control-allow-origin"] == "*"


def test_initialize_via_lambda_handler(lambda_context, valid_api_key):
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


def test_tools_list_via_lambda_handler(lambda_context, valid_api_key):
    response = handler(mcp_post_event("tools/list"), lambda_context)

    body = json.loads(response["body"])
    tool_names = {tool["name"] for tool in body["result"]["tools"]}
    assert EXPECTED_TOOLS.issubset(tool_names)


def test_warm_lambda_handles_repeated_invocations(lambda_context, valid_api_key):
    """A warm Lambda container reuses the module-level app; the lifespan must
    survive being entered once per invocation."""
    for _ in range(2):
        response = handler(mcp_post_event("tools/list"), lambda_context)
        assert response["statusCode"] == 200


def test_protected_resource_metadata_via_lambda(lambda_context, monkeypatch):
    """With OAuth configured, API Gateway events for the RFC 9728 metadata URL
    must be served unauthenticated through the Lambda handler."""
    for key, value in OAUTH_ENV.items():
        monkeypatch.setenv(key, value)

    server_module = importlib.reload(orchestramcp.server)
    lambda_module = importlib.reload(orchestramcp.lambda_handler)
    try:
        response = lambda_module.handler(
            api_gateway_event(method="GET", path="/.well-known/oauth-protected-resource/orchestra"),
            lambda_context,
        )
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["resource"] == "https://mcp.getorchestra.io/orchestra"
        assert body["authorization_servers"] == ["https://auth.example.com/"]
    finally:
        for key in OAUTH_ENV:
            monkeypatch.delenv(key)
        importlib.reload(server_module)
        importlib.reload(lambda_module)
