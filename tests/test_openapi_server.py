import json
from pathlib import Path

import httpx
from fastmcp import Client

from orchestramcp.adaptations import ADAPTATIONS
from orchestramcp.openapi_server import build_server
from orchestramcp.spec import load_spec, mcp_operations

SAMPLE = str(Path(__file__).parent / "fixtures" / "openapi_sample.json")
LIVE = str(Path(__file__).parent / "fixtures" / "openapi_live.json")

MAX_TOOLS = 30
MAX_SCHEMA_BYTES = 40_000


def _client(handler=None):
    handler = handler or (lambda request: httpx.Response(200, json={}))
    return httpx.AsyncClient(
        base_url="https://example.com/api/engine", transport=httpx.MockTransport(handler)
    )


async def _tools_by_name(server):
    return {tool.name: tool for tool in await server.list_tools()}


# --- selection + adaptation (small sample) ---


async def test_unflagged_operations_are_excluded():
    tools = await _tools_by_name(build_server(load_spec(SAMPLE), _client()))
    assert "health_check" not in tools
    assert {"list_pipeline_runs", "cancel_pipeline_run", "list_assets"} <= set(tools)


async def test_adaptation_overrides_description_and_annotations():
    tools = await _tools_by_name(build_server(load_spec(SAMPLE), _client()))
    assert "comma-separated" in tools["list_pipeline_runs"].description
    assert tools["list_pipeline_runs"].annotations.readOnlyHint is True
    assert tools["cancel_pipeline_run"].annotations.destructiveHint is True


async def test_unadapted_tool_uses_spec_summary_and_derived_hints():
    tools = await _tools_by_name(build_server(load_spec(SAMPLE), _client()))
    assert "list_assets" not in ADAPTATIONS
    assert tools["list_assets"].description == "List data assets"
    assert tools["list_assets"].annotations.readOnlyHint is True


async def test_generated_tool_calls_through_client():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"page": 1})

    async with Client(build_server(load_spec(SAMPLE), _client(handler))) as client:
        result = await client.call_tool("list_pipeline_runs", {"status": "SUCCEEDED"})

    method, path, params = calls[0]
    assert method == "GET" and path.endswith("/pipeline_runs") and params == {"status": "SUCCEEDED"}
    assert result.data == {"page": 1}


# --- full surface (live spec) ---


async def test_live_surface_gates_deletes_and_registers_handwritten():
    tools = set(await _tools_by_name(build_server(load_spec(LIVE), _client())))
    assert "delete_pipeline" not in tools and "delete_environment" not in tools
    assert {
        "get_pipeline_run_lineage_url",
        "download_task_run_log",
        "download_task_run_artifact",
    } <= tools


async def test_live_surface_exposes_deletes_when_enabled():
    tools = set(
        await _tools_by_name(build_server(load_spec(LIVE), _client(), include_deletes=True))
    )
    assert {"delete_pipeline", "delete_environment"} <= tools


async def test_coarsening_shrinks_pipeline_body_but_keeps_wrapper_fields():
    tools = await _tools_by_name(build_server(load_spec(LIVE), _client()))
    create = tools["create_pipeline"].parameters
    assert len(json.dumps(create)) < 5_000
    assert "published" in create["properties"]


async def test_validate_pipeline_takes_a_pipeline_and_posts_it_raw():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"valid": True})

    server = build_server(load_spec(LIVE), _client(handler))
    parameters = (await _tools_by_name(server))["validate_pipeline"].parameters
    assert "pipeline_definition" in parameters["properties"]
    assert "pipeline_definition" in parameters["required"]

    definition = {"version": "v1", "name": "demo", "pipeline": {}}
    async with Client(server) as client:
        await client.call_tool("validate_pipeline", {"pipeline_definition": definition})

    method, path, body = calls[0]
    assert method == "POST" and path.endswith("/pipelines/schema")
    assert body == definition  # posted raw, not wrapped under a key


async def test_live_surface_within_budget():
    tools = await build_server(load_spec(LIVE), _client()).list_tools()
    assert len(tools) <= MAX_TOOLS
    size = sum(
        len(json.dumps({"name": t.name, "description": t.description, "parameters": t.parameters}))
        for t in tools
    )
    assert size <= MAX_SCHEMA_BYTES


def test_every_adaptation_targets_a_flagged_operation():
    flagged = {op["operationId"] for _, _, op in mcp_operations(load_spec(LIVE))}
    stale = set(ADAPTATIONS) - flagged
    assert not stale, f"adaptations reference operations not flagged for the MCP: {stale}"
