import os

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
    tool_names = {tool for tool in await mcp.get_tools()}
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
    }
    assert expected_tools.issubset(tool_names)


@pytest.mark.asyncio
async def test_list_operations_tool_exposes_integration_filter():
    tool = (await mcp.get_tools())["list_operations"]

    assert "integration" in tool.parameters["properties"]
