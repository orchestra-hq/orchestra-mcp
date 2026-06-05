import pytest

from orchestramcp.server import get_client, mcp


@pytest.mark.asyncio
async def test_get_client_falls_back_to_env(monkeypatch):
    """With no authenticated request context (local stdio dev), the upstream
    credential comes from the ORCHESTRA_API_KEY environment variable."""
    monkeypatch.setenv("ORCHESTRA_API_KEY", "test-api-key")
    client = await get_client()
    try:
        assert client.api_key == "test-api-key"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_get_client_missing_api_key(monkeypatch):
    monkeypatch.delenv("ORCHESTRA_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ORCHESTRA_API_KEY"):
        await get_client()


@pytest.mark.asyncio
async def test_tool_registration():
    tool_names = {tool.name for tool in await mcp.list_tools()}
    expected_tools = {
        "cancel_pipeline_run",
        "download_task_run_artifact",
        "download_task_run_log",
        "get_pipeline_run_status",
        "get_pipeline_run_lineage_url",
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
async def test_all_tools_have_directory_annotations():
    """Claude Directory review requires every tool to declare a title and the
    applicable readOnlyHint / destructiveHint."""
    destructive = {"cancel_pipeline_run"}
    writes = {"import_pipeline", "start_pipeline"}
    for tool in await mcp.list_tools():
        ann = tool.annotations
        assert ann is not None, f"{tool.name} missing annotations"
        assert ann.title, f"{tool.name} missing title"
        assert ann.readOnlyHint is not None, f"{tool.name} missing readOnlyHint"
        assert ann.destructiveHint is not None, f"{tool.name} missing destructiveHint"
        expected_read_only = tool.name not in destructive and tool.name not in writes
        assert ann.readOnlyHint is expected_read_only, tool.name
        assert ann.destructiveHint is (tool.name in destructive), tool.name


@pytest.mark.asyncio
async def test_list_operations_tool_exposes_integration_filter():
    tools = {tool.name: tool for tool in await mcp.list_tools()}
    tool = tools["list_operations"]

    assert "integration" in tool.parameters["properties"]
