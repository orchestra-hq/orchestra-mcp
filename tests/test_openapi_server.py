import json
from pathlib import Path

import httpx
import pytest
from fastmcp import Client

from orchestramcp.adaptations import ADAPTATIONS
from orchestramcp.openapi_server import ApiSource, build_server
from orchestramcp.spec import load_spec, mcp_operations

SAMPLE = str(Path(__file__).parent / "fixtures" / "openapi_sample.json")
LIVE = str(Path(__file__).parent / "fixtures" / "openapi_live.json")
PLATFORM = str(Path(__file__).parent / "fixtures" / "openapi_platform.json")

# Ceilings on the surface every model call re-reads, set just above the current
# live numbers (38 tools, ~51 KB) so routine upstream growth trips the test and
# gets looked at. Raising them is a decision, not a formality: check first whether
# the growth is worth its tokens, and whether coarsening in spec.py would pay for it.
MAX_TOOLS = 40
MAX_SCHEMA_BYTES = 56_000

ENGINE_BASE_URL = "https://example.com/api/engine"
PLATFORM_BASE_URL = "https://example.com/public/v1"


def _client(base_url=ENGINE_BASE_URL, handler=None):
    handler = handler or (lambda request: httpx.Response(200, json={}))
    return httpx.AsyncClient(base_url=base_url, transport=httpx.MockTransport(handler))


def _server(engine_spec=LIVE, engine_handler=None, platform_handler=None, **kwargs):
    return build_server(
        ApiSource(load_spec(engine_spec), _client(ENGINE_BASE_URL, engine_handler)),
        ApiSource(load_spec(PLATFORM), _client(PLATFORM_BASE_URL, platform_handler)),
        **kwargs,
    )


async def _tools_by_name(server):
    return {tool.name: tool for tool in await server.list_tools()}


# --- selection + adaptation (small sample) ---


async def test_unflagged_operations_are_excluded():
    tools = await _tools_by_name(_server(SAMPLE))
    assert "health_check" not in tools
    assert {"list_pipeline_runs", "cancel_pipeline_run", "list_assets"} <= set(tools)


async def test_adaptation_overrides_description_and_annotations():
    tools = await _tools_by_name(_server(SAMPLE))
    assert "comma-separated" in tools["list_pipeline_runs"].description
    assert tools["list_pipeline_runs"].annotations.readOnlyHint is True
    assert tools["cancel_pipeline_run"].annotations.destructiveHint is True


async def test_unadapted_tool_uses_spec_summary_and_derived_hints():
    tools = await _tools_by_name(_server(SAMPLE))
    assert "list_assets" not in ADAPTATIONS
    assert tools["list_assets"].description == "List data assets"
    assert tools["list_assets"].annotations.readOnlyHint is True


async def test_generated_tool_calls_through_client():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        return httpx.Response(200, json={"page": 1})

    async with Client(_server(SAMPLE, engine_handler=handler)) as client:
        result = await client.call_tool("list_pipeline_runs", {"status": "SUCCEEDED"})

    method, path, params = calls[0]
    assert method == "GET" and path.endswith("/pipeline_runs") and params == {"status": "SUCCEEDED"}
    assert result.data == {"page": 1}


# --- full surface (live spec) ---


async def test_live_surface_gates_deletes_and_registers_handwritten():
    tools = set(await _tools_by_name(_server()))
    assert "delete_pipeline" not in tools and "delete_environment" not in tools
    assert {
        "get_pipeline_run_lineage_url",
        "download_task_run_log",
        "download_task_run_artifact",
    } <= tools


async def test_live_surface_exposes_deletes_when_enabled():
    tools = set(await _tools_by_name(_server(include_deletes=True)))
    assert {"delete_pipeline", "delete_environment"} <= tools


async def test_coarsening_shrinks_pipeline_body_but_keeps_wrapper_fields():
    tools = await _tools_by_name(_server())
    create = tools["create_pipeline"].parameters
    assert len(json.dumps(create)) < 5_000
    assert "published" in create["properties"]


async def test_validate_pipeline_takes_a_pipeline_and_posts_it_raw():
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"valid": True})

    server = _server(engine_handler=handler)
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
    tools = await _server().list_tools()
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


# --- second source (platform spec) ---


async def test_platform_operations_become_tools_named_in_snake_case():
    tools = await _tools_by_name(_server())
    assert "list_accounts" in tools  # the spec's operationId is listAccounts
    assert tools["list_accounts"].annotations.readOnlyHint is True


async def test_platform_tool_calls_through_the_platform_client():
    calls = []

    def platform_handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json=[{"id": "an-id", "name": "A workspace"}])

    server = _server(platform_handler=platform_handler)
    async with Client(server) as client:
        result = await client.call_tool("list_accounts", {})

    assert calls == [f"{PLATFORM_BASE_URL}/accounts"]
    # A JSON array response is wrapped under "result", as MCP requires of non-objects.
    assert result.structured_content == {"result": [{"id": "an-id", "name": "A workspace"}]}


async def test_engine_tools_keep_the_engine_base_url():
    calls = []

    def engine_handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    async with Client(_server(engine_handler=engine_handler)) as client:
        await client.call_tool("list_pipelines", {})

    assert calls[0].startswith(f"{ENGINE_BASE_URL}/public/pipelines")


async def test_a_tool_name_claimed_by_both_apis_is_refused():
    engine = load_spec(LIVE)
    platform = load_spec(PLATFORM)
    platform["paths"]["/pipelines"] = engine["paths"]["/public/pipelines"]

    with pytest.raises(ValueError, match="list_pipelines"):
        build_server(
            ApiSource(engine, _client(ENGINE_BASE_URL)),
            ApiSource(platform, _client(PLATFORM_BASE_URL)),
        )
