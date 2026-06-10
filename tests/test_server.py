import os
from unittest.mock import AsyncMock

import pytest

from orchestramcp.models import ValidatePipelineSchemaResponse
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
        "cancel_pipeline_run",
        "download_task_run_artifact",
        "download_task_run_log",
        "get_pipeline_run_status",
        "import_pipeline",
        "list_assets",
        "list_operations",
        "list_pipeline_runs",
        "list_task_run_artifacts",
        "list_task_run_logs",
        "list_task_runs",
        "start_pipeline",
        "validate_pipeline",
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_list_operations_tool_exposes_integration_filter():
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    tool = tools["list_operations"]

    assert "integration" in tool.parameters["properties"]
