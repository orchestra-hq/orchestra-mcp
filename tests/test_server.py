import os

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


def test_spec_url_prefers_override():
    assert server._spec_url() == os.environ["ORCHESTRA_OPENAPI_URL"]


def test_delete_enabled_flag(monkeypatch):
    monkeypatch.delenv("ORCHESTRA_ENABLE_DELETE", raising=False)
    assert server._delete_enabled() is False
    for truthy in ("1", "true", "TRUE"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", truthy)
        assert server._delete_enabled() is True
    for falsy in ("yes", "on", "0", "", "random"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", falsy)
        assert server._delete_enabled() is False
