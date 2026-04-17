import os
from unittest.mock import AsyncMock

import pytest

from orchestramcp.server import get_client, mcp


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


@pytest.mark.asyncio
async def test_tool_registration():
    tool_names = {tool.name for tool in await mcp.list_tools()}
    expected_tools = {
        "cancel_pipeline_run",
        "create_pipeline",
        "delete_pipeline",
        "download_task_run_artifact",
        "download_task_run_log",
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
        "start_pipeline",
        "update_pipeline",
        "validate_pipeline",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_list_operations_tool_exposes_integration_filter():
    tool = (await mcp.get_tools())["list_operations"]
    integration_schema = tool.parameters["properties"]["integration"]

    assert "integration" in tool.parameters["properties"]
    assert integration_schema["anyOf"][0]["type"] == "array"


@pytest.mark.asyncio
async def test_list_pipeline_runs_tool_uses_array_filters():
    tool = (await mcp.get_tools())["list_pipeline_runs"]
    status_schema = tool.parameters["properties"]["status"]
    pipeline_run_ids_schema = tool.parameters["properties"]["pipeline_run_ids"]

    assert status_schema["anyOf"][0]["type"] == "array"
    assert pipeline_run_ids_schema["anyOf"][0]["type"] == "array"


@pytest.mark.asyncio
async def test_validate_pipeline_does_not_require_api_key(monkeypatch):
    get_client.cache_clear()
    monkeypatch.delenv("ORCHESTRA_API_KEY", raising=False)
    mock_validate = AsyncMock(return_value={"message": "Pipeline schema is valid"})
    mock_close = AsyncMock()
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.validate_pipeline_schema", mock_validate)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.close", mock_close)
    tool = (await mcp.get_tools())["validate_pipeline"]

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
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.validate_pipeline_schema", mock_validate)
    monkeypatch.setattr("orchestramcp.client.OrchestraClient.close", mock_close)
    tool = (await mcp.get_tools())["validate_pipeline"]

    result = await tool.fn({"version": "v1", "name": "test"})

    assert result["message"] == "Pipeline schema is valid"
    mock_validate.assert_awaited_once_with(pipeline_definition={"version": "v1", "name": "test"})
    mock_close.assert_awaited_once()
