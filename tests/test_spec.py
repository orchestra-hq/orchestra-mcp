from pathlib import Path

from orchestramcp.spec import load_spec, mcp_operations, select_mcp_spec

FIXTURE = str(Path(__file__).parent / "fixtures" / "openapi_sample.json")


def test_select_keeps_only_flagged_operations():
    selected = select_mcp_spec(load_spec(FIXTURE))
    assert set(selected["paths"]) == {
        "/pipeline_runs",
        "/pipeline_runs/{pipeline_run_id}/cancel",
        "/assets",
    }


def test_mcp_operations_yields_flagged_only():
    ops = {op["operationId"] for _, _, op in mcp_operations(load_spec(FIXTURE))}
    assert ops == {"list_pipeline_runs", "cancel_pipeline_run", "list_assets"}


def test_select_preserves_spec_metadata():
    spec = load_spec(FIXTURE)
    selected = select_mcp_spec(spec)
    assert selected["info"] == spec["info"]
    assert selected["servers"] == spec["servers"]
