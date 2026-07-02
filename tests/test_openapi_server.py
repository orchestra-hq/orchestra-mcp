import json
from pathlib import Path

import httpx
from fastmcp import Client

from orchestramcp.adaptations import ADAPTATIONS
from orchestramcp.openapi_server import build_server
from orchestramcp.spec import load_spec, mcp_operations

FIXTURE = str(Path(__file__).parent / "fixtures" / "openapi_sample.json")

MAX_TOOLS = 40
MAX_SCHEMA_BYTES = 20_000


def _client(handler=None):
    handler = handler or (lambda request: httpx.Response(200, json={}))
    return httpx.AsyncClient(base_url="https://example.com", transport=httpx.MockTransport(handler))


async def _tools_by_name(server):
    return {tool.name: tool for tool in await server.list_tools()}


async def test_only_flagged_operations_become_tools():
    server = build_server(load_spec(FIXTURE), _client())
    tools = await _tools_by_name(server)
    assert set(tools) == {"list_pipeline_runs", "cancel_pipeline_run", "list_assets"}
    assert "health_check" not in tools


async def test_adaptation_overrides_description_and_annotations():
    server = build_server(load_spec(FIXTURE), _client())
    tools = await _tools_by_name(server)

    assert "comma-separated" in tools["list_pipeline_runs"].description
    assert tools["list_pipeline_runs"].annotations.readOnlyHint is True
    assert tools["cancel_pipeline_run"].annotations.destructiveHint is True


async def test_unadapted_tool_falls_back_to_spec_summary_and_derived_hints():
    server = build_server(load_spec(FIXTURE), _client())
    tools = await _tools_by_name(server)

    assert "list_assets" not in ADAPTATIONS
    assert tools["list_assets"].description == "List data assets"
    assert tools["list_assets"].annotations.readOnlyHint is True


async def test_tool_surface_stays_within_budget():
    server = build_server(load_spec(FIXTURE), _client())
    tools = await server.list_tools()

    assert len(tools) <= MAX_TOOLS
    size = sum(
        len(json.dumps({"name": t.name, "description": t.description, "parameters": t.parameters}))
        for t in tools
    )
    assert size <= MAX_SCHEMA_BYTES


async def test_generated_tool_calls_through_client():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"page": 1})

    server = build_server(load_spec(FIXTURE), _client(handler))
    async with Client(server) as client:
        result = await client.call_tool("list_pipeline_runs", {"status": "SUCCEEDED"})

    assert calls == [("GET", "/pipeline_runs", {"status": "SUCCEEDED"})]
    assert result.data == {"page": 1}


def test_every_adaptation_targets_a_flagged_operation():
    flagged = {op["operationId"] for _, _, op in mcp_operations(load_spec(FIXTURE))}
    stale = set(ADAPTATIONS) - flagged
    assert not stale, f"adaptations reference operations not flagged x-mcp: {stale}"
