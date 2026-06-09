import json
import os
from unittest.mock import MagicMock, patch

import pytest

from orchestramcp.lambda_handler import handler
from orchestramcp.server import get_client


@pytest.fixture(autouse=True)
def orchestra_env():
    os.environ["ORCHESTRA_ENV"] = "app"
    yield
    os.environ.pop("ORCHESTRA_ENV", None)
    get_client.cache_clear()


@pytest.fixture
def lambda_context():
    context = MagicMock()
    context.aws_request_id = "test-request-id"
    return context


def _api_gateway_event(
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
        "requestContext": {
            "http": {
                "method": method,
                "path": "/orchestra",
            }
        },
        "body": body,
    }


def test_post_without_bearer_returns_401(lambda_context):
    response = handler(_api_gateway_event(method="POST"), lambda_context)

    assert response["statusCode"] == 401
    assert "Missing or invalid Authorization header" in response["body"]


def test_options_returns_cors_response(lambda_context):
    response = handler(_api_gateway_event(method="OPTIONS"), lambda_context)

    assert response["statusCode"] == 200
    assert response["headers"]["Access-Control-Allow-Origin"] == "*"


def test_post_calls_get_client_cache_clear(lambda_context):
    initialize_body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
    )
    event = _api_gateway_event(
        method="POST",
        headers={
            "Authorization": "Bearer test-api-key",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        body=initialize_body,
    )

    with patch.object(get_client, "cache_clear") as cache_clear:
        response = handler(event, lambda_context)

    cache_clear.assert_called_once()
    assert response["statusCode"] == 200


def test_post_sets_orchestra_api_key_env(lambda_context):
    initialize_body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        }
    )
    event = _api_gateway_event(
        method="POST",
        headers={
            "Authorization": "Bearer workspace-key-123",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        body=initialize_body,
    )

    handler(event, lambda_context)

    assert os.environ.get("ORCHESTRA_API_KEY") == "workspace-key-123"
    assert os.environ.get("ORCHESTRA_ENV") == "app"
