import importlib
import os

import pytest

from orchestramcp.server import get_client, mcp, parse_iso_datetime


@pytest.fixture
def set_api_key():
    os.environ["ORCHESTRA_API_KEY"] = "test-api-key"
    yield
    os.environ.pop("ORCHESTRA_API_KEY", None)


@pytest.mark.asyncio
async def test_get_client_missing_api_key(monkeypatch):
    monkeypatch.delenv("ORCHESTRA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ORCHESTRA_API_KEY"):
        await get_client()


@pytest.mark.asyncio
async def test_get_client_falls_back_to_env(set_api_key):
    """With no authenticated request context (local stdio dev), the upstream
    credential comes from the ORCHESTRA_API_KEY environment variable."""
    client = await get_client()
    try:
        assert client.api_key == "test-api-key"
    finally:
        await client.close()


def test_parse_iso_datetime_accepts_z_suffix():
    dt = parse_iso_datetime("2025-04-01T00:00:00Z")
    assert dt.year == 2025
    assert dt.tzinfo is not None


def test_parse_iso_datetime_invalid_message_is_actionable():
    with pytest.raises(ValueError) as exc_info:
        parse_iso_datetime("yesterday")
    message = str(exc_info.value)
    assert "yesterday" in message
    assert "ISO 8601" in message
    assert "2025-04-01T00:00:00Z" in message


@pytest.mark.asyncio
async def test_tool_registration():
    tool_names = {tool.name for tool in await mcp.list_tools()}
    expected_tools = {
        "cancel_pipeline_run",
        "create_pipeline",
        "update_pipeline",
        "download_task_run_artifact",
        "download_task_run_log",
        "get_pipeline_run_status",
        "get_pipeline",
        "import_pipeline",
        "list_assets",
        "list_integration_connections",
        "list_operations",
        "list_pipeline_runs",
        "list_pipelines",
        "list_task_run_artifacts",
        "list_task_run_logs",
        "list_task_runs",
        "migrate_pipeline",
        "start_pipeline",
        "validate_pipeline",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_list_operations_tool_exposes_integration_filter():
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    tool = tools["list_operations"]

    assert "integration" in tool.parameters["properties"]


@pytest.mark.asyncio
async def test_delete_pipeline_disabled_by_default():
    tool_names = {tool.name for tool in await mcp.list_tools()}
    assert "delete_pipeline" not in tool_names


def test_delete_enabled_flag(monkeypatch):
    from orchestramcp.server import _delete_enabled

    monkeypatch.delenv("ORCHESTRA_ENABLE_DELETE", raising=False)
    assert _delete_enabled() is False

    for truthy in ("1", "true", "TRUE"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", truthy)
        assert _delete_enabled() is True

    monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", "false")
    assert _delete_enabled() is False

    for falsy in ("yes", "on", "0", "", "random"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", falsy)
        assert _delete_enabled() is False


@pytest.mark.asyncio
async def test_delete_pipeline_enabled_when_env_var_set(set_api_key, monkeypatch):
    monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", "true")

    import orchestramcp.server as server_module

    server_module = importlib.reload(server_module)

    tool_names = {tool.name for tool in await server_module.mcp.list_tools()}
    assert "delete_pipeline" in tool_names

@pytest.mark.asyncio
async def test_list_integration_connections_tool_exposes_filters():
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    tool = tools["list_integration_connections"]

    assert "integration" in tool.parameters["properties"]
    assert "auth_status" in tool.parameters["properties"]
