import os
from unittest.mock import AsyncMock

import pytest

from orchestramcp.client import OrchestraAPIError
from orchestramcp.server import get_client, mcp, parse_iso_datetime


@pytest.fixture
def set_api_key():
    get_client.cache_clear()
    os.environ["ORCHESTRA_API_KEY"] = "test-api-key"
    yield
    os.environ.pop("ORCHESTRA_API_KEY", None)
    get_client.cache_clear()


def test_get_client_missing_api_key():
    get_client.cache_clear()
    if "ORCHESTRA_API_KEY" in os.environ:
        del os.environ["ORCHESTRA_API_KEY"]
    try:
        with pytest.raises(ValueError, match="ORCHESTRA_API_KEY"):
            get_client()
    finally:
        get_client.cache_clear()


def test_get_client_with_api_key(set_api_key):
    assert get_client().api_key == "test-api-key"


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
        "build_pipeline",
        "cancel_pipeline_run",
        "create_pipeline",
        "download_task_run_artifact",
        "download_task_run_log",
        "get_pipeline",
        "get_pipeline_run_lineage_url",
        "get_pipeline_run_status",
        "import_pipeline",
        "list_assets",
        "list_operations",
        "list_pipeline_runs",
        "list_pipelines",
        "list_task_run_artifacts",
        "list_task_run_logs",
        "list_task_runs",
        "migrate_pipeline",
        "start_pipeline",
        "update_pipeline",
        "validate_pipeline",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_delete_pipeline_disabled_by_default():
    tool_names = {tool.name for tool in await mcp.list_tools()}
    assert "delete_pipeline" not in tool_names


def test_delete_enabled_flag(monkeypatch):
    from orchestramcp.server import _delete_enabled

    monkeypatch.delenv("ORCHESTRA_ENABLE_DELETE", raising=False)
    assert _delete_enabled() is False

    for truthy in ("1", "true", "TRUE", "yes", "on"):
        monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", truthy)
        assert _delete_enabled() is True

    monkeypatch.setenv("ORCHESTRA_ENABLE_DELETE", "false")
    assert _delete_enabled() is False


@pytest.mark.asyncio
async def test_build_pipeline_creates_and_starts(set_api_key, monkeypatch):
    from unittest.mock import Mock

    mock_validate = AsyncMock(return_value={"message": "valid"})
    mock_get = AsyncMock(side_effect=OrchestraAPIError(404, "not found"))
    mock_create = AsyncMock(return_value={"id": "p1", "latestVersionNumber": 2})
    mock_update = AsyncMock()
    mock_start = AsyncMock(return_value=Mock(model_dump=Mock(return_value={"pipelineRunId": "r1"})))

    monkeypatch.setattr("orchestramcp.client.OrchestraClient.validate_pipeline_schema", mock_validate)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.get_pipeline", mock_get)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.create_pipeline", mock_create)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.update_pipeline", mock_update)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.start_pipeline", mock_start)

    tool = await mcp.get_tool("build_pipeline")
    result = await tool.fn(alias="my_pipeline", data={"version": "v1", "name": "n"})

    mock_validate.assert_awaited_once()
    mock_create.assert_awaited_once()
    mock_update.assert_not_awaited()
    assert mock_start.await_args.kwargs["version_number"] == 2
    assert result["run"] == {"pipelineRunId": "r1"}


@pytest.mark.asyncio
async def test_build_pipeline_updates_existing(set_api_key, monkeypatch):
    from unittest.mock import Mock

    mock_validate = AsyncMock(return_value={"message": "valid"})
    mock_get = AsyncMock(return_value={"id": "p1", "alias": "my_pipeline"})
    mock_create = AsyncMock()
    mock_update = AsyncMock(return_value={"id": "p1", "latestVersionNumber": 5})
    mock_start = AsyncMock(return_value=Mock(model_dump=Mock(return_value={"pipelineRunId": "r2"})))

    monkeypatch.setattr("orchestramcp.client.OrchestraClient.validate_pipeline_schema", mock_validate)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.get_pipeline", mock_get)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.create_pipeline", mock_create)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.update_pipeline", mock_update)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.start_pipeline", mock_start)

    tool = await mcp.get_tool("build_pipeline")
    await tool.fn(alias="my_pipeline", data={"version": "v1", "name": "n"})

    mock_update.assert_awaited_once()
    mock_create.assert_not_awaited()
    assert mock_start.await_args.kwargs["version_number"] == 5


@pytest.mark.asyncio
async def test_migrate_pipeline_tool(set_api_key, monkeypatch):
    mock_migrate = AsyncMock(return_value={"status": "ok"})
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.migrate_pipeline_storage", mock_migrate)

    tool = await mcp.get_tool("migrate_pipeline")
    result = await tool.fn(
        path="pipelines/my.yaml",
        repository="owner/repo",
        storage_provider="GITHUB",
        default_branch="main",
        alias="my_pipeline",
    )

    assert result == {"status": "ok"}
    mock_migrate.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pipeline_tool_exposes_selectors():
    tool = await mcp.get_tool("get_pipeline")
    props = tool.parameters["properties"]

    assert "pipeline_id" in props
    assert "alias" in props
    assert "repository" in props
    assert "yaml_path" in props
    assert "version" in props
    assert "branch" in props
    assert "commit" in props


@pytest.mark.asyncio
async def test_list_operations_tool_exposes_integration_filter():
    tool = await mcp.get_tool("list_operations")
    integration_schema = tool.parameters["properties"]["integration"]

    assert "integration" in tool.parameters["properties"]
    assert integration_schema["anyOf"][0]["type"] == "string"


@pytest.mark.asyncio
async def test_list_pipeline_runs_tool_uses_string_filters():
    tool = await mcp.get_tool("list_pipeline_runs")
    status_schema = tool.parameters["properties"]["status"]
    pipeline_run_ids_schema = tool.parameters["properties"]["pipeline_run_ids"]

    assert status_schema["anyOf"][0]["$ref"] == "#/$defs/PipelineRunStatus"
    assert pipeline_run_ids_schema["anyOf"][0]["type"] == "string"


@pytest.mark.asyncio
async def test_validate_pipeline_does_not_require_api_key(monkeypatch):
    get_client.cache_clear()
    monkeypatch.delenv("ORCHESTRA_API_KEY", raising=False)
    mock_validate = AsyncMock(return_value={"message": "Pipeline schema is valid"})
    mock_close = AsyncMock()
    monkeypatch.setattr(
        "orchestramcp.client.OrchestraClient.validate_pipeline_schema", mock_validate
    )
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.close", mock_close)
    tool = await mcp.get_tool("validate_pipeline")

    result = await tool.fn({"version": "v1", "name": "test"})

    assert result["message"] == "Pipeline schema is valid"
    mock_validate.assert_awaited_once_with(pipeline_definition={"version": "v1", "name": "test"})
    mock_close.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_pipeline_uses_api_key_when_present(monkeypatch):
    get_client.cache_clear()
    monkeypatch.setenv("ORCHESTRA_API_KEY", "test-api-key")
    mock_validate = AsyncMock(return_value={"message": "Pipeline schema is valid"})
    mock_close = AsyncMock()
    monkeypatch.setattr(
        "orchestramcp.client.OrchestraClient.validate_pipeline_schema", mock_validate
    )
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.close", mock_close)
    tool = await mcp.get_tool("validate_pipeline")

    result = await tool.fn({"version": "v1", "name": "test"})

    assert result["message"] == "Pipeline schema is valid"
    mock_validate.assert_awaited_once_with(pipeline_definition={"version": "v1", "name": "test"})
    mock_close.assert_awaited_once()
