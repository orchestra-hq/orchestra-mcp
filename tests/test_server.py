import os

import httpx
import pytest

from orchestramcp import server
from tests.conftest import EXPECTED_TOOLS


async def test_get_mcp_builds_expected_surface():
    tool_names = {tool.name for tool in await server.get_mcp().list_tools()}
    assert tool_names == EXPECTED_TOOLS


async def test_deletes_gated_off_by_default():
    tool_names = {tool.name for tool in await server.get_mcp().list_tools()}
    assert "delete_pipeline" not in tool_names
    assert "delete_environment" not in tool_names


async def test_deletes_exposed_when_enabled(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", "true")
    server.get_mcp.cache_clear()

    tool_names = {tool.name for tool in await server.get_mcp().list_tools()}
    assert {"delete_pipeline", "delete_environment"} <= tool_names


def test_invalid_environment_rejected(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_ENV", "prod")
    with pytest.raises(ValueError, match="Invalid environment"):
        server._base_url()


def test_spec_urls_prefer_overrides():
    assert server._spec_url() == os.environ["ORCHESTRA_OPENAPI_URL"]
    assert server._platform_spec_url() == os.environ["ORCHESTRA_PLATFORM_OPENAPI_URL"]


def test_spec_urls_default_to_each_api_origin(monkeypatch):
    monkeypatch.delenv("ORCHESTRA_OPENAPI_URL")
    monkeypatch.delenv("ORCHESTRA_PLATFORM_OPENAPI_URL")
    assert server._spec_url() == "https://app.getorchestra.io/api/engine/openapi.json"
    assert server._platform_spec_url() == "https://app.getorchestra.io/public/v1/openapi.json"


@pytest.mark.parametrize("failing", ["ORCHESTRA_OPENAPI_URL", "ORCHESTRA_PLATFORM_OPENAPI_URL"])
def test_a_spec_that_cannot_be_fetched_fails_the_build(monkeypatch, failing):
    unreachable = os.environ[failing]
    load_spec = server.load_spec

    def fail_to_fetch(source):
        if source == unreachable:
            raise httpx.ConnectError("unreachable")
        return load_spec(source)

    monkeypatch.setattr(server, "load_spec", fail_to_fetch)
    server.get_mcp.cache_clear()

    with pytest.raises(httpx.ConnectError):
        server.get_mcp()


async def test_both_apis_receive_the_caller_credential(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_API_KEY", "key-a")
    seen = []

    def handler(request):
        seen.append((str(request.url), request.headers.get("Authorization")))
        return httpx.Response(200, json={})

    for base_url in (server._base_url(), server._platform_base_url()):
        client = server.get_client(base_url)
        client._transport = httpx.MockTransport(handler)
        await client.get("/probe")

    assert seen == [
        (f"{server._base_url()}/probe", "Bearer key-a"),
        (f"{server._platform_base_url()}/probe", "Bearer key-a"),
    ]


def test_delete_enabled_flag(monkeypatch):
    monkeypatch.delenv("ORCHESTRA_ENABLE_DELETE", raising=False)
    assert server._delete_enabled() is False
    for truthy in ("1", "true", "TRUE"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", truthy)
        assert server._delete_enabled() is True
    for falsy in ("yes", "on", "0", "", "random"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", falsy)
        assert server._delete_enabled() is False
