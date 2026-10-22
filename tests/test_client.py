import os
import re

import httpx
import pytest

from orchestramcp.client import build_http_client
from orchestramcp.errors import OrchestraAPIError


def _client(handler, api_key="test-key"):
    if api_key is None:
        os.environ.pop("ORCHESTRA_API_KEY", None)
    else:
        os.environ["ORCHESTRA_API_KEY"] = api_key
    client = build_http_client("https://example.com/api/engine")
    client._transport = httpx.MockTransport(handler)
    return client


async def test_request_carries_current_bearer_token():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, api_key="key-a")
    await client.get("/public/pipelines")
    assert seen["auth"] == "Bearer key-a"

    # A later request picks up a rotated token without rebuilding the client.
    os.environ["ORCHESTRA_API_KEY"] = "key-b"
    await client.get("/public/pipelines")
    assert seen["auth"] == "Bearer key-b"


async def test_missing_token_raises():
    client = _client(lambda r: httpx.Response(200, json={}), api_key=None)
    with pytest.raises(ValueError, match="ORCHESTRA_API_KEY"):
        await client.get("/public/pipelines")


async def test_error_response_becomes_orchestra_error():
    client = _client(lambda r: httpx.Response(422, json={"detail": "bad input"}))
    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.post("/public/pipelines", json={})
    assert exc_info.value.status_code == 422
    assert exc_info.value.message == "bad input"


async def test_requests_carry_a_fresh_support_id():
    seen = []

    def handler(request):
        seen.append(request.headers.get("X-Orchestra-Support-Id"))
        return httpx.Response(200, json={})

    client = _client(handler)
    await client.get("/public/pipelines")
    await client.get("/public/pipelines")
    assert all(re.fullmatch(r"[0-9a-f]{12}", support_id) for support_id in seen)
    assert seen[0] != seen[1]


async def test_waf_block_names_the_support_id():
    seen = {}

    def handler(request):
        seen["support_id"] = request.headers["X-Orchestra-Support-Id"]
        return httpx.Response(
            403,
            headers={"content-type": "text/html"},
            text="<html><head><title>403 Forbidden</title></head></html>",
        )

    client = _client(handler)
    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.get("/public/pipelines")
    message = f"Your request was blocked. Contact Orchestra support with ID: {seen['support_id']}"
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == message
    assert str(exc_info.value) == f"403: {message}"


async def test_json_403_keeps_the_api_message_and_hint():
    client = _client(lambda r: httpx.Response(403, json={"detail": "Forbidden"}))
    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.get("/public/pipelines")
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Forbidden"
    assert "Metadata API" in str(exc_info.value)
