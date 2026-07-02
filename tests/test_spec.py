from pathlib import Path

from orchestramcp.spec import load_spec, mcp_operations, prune_spec, select_mcp_spec

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


def test_prune_removes_schema_noise_and_truncates_descriptions():
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "keep-me"},
        "components": {
            "schemas": {
                "Thing": {
                    "type": "object",
                    "title": "drop",
                    "example": {"a": 1},
                    "properties": {
                        "name": {"type": "string", "title": "drop", "description": "x" * 500}
                    },
                }
            }
        },
        "paths": {},
    }

    pruned = prune_spec(spec)
    thing = pruned["components"]["schemas"]["Thing"]

    assert "title" not in thing and "example" not in thing
    assert "title" not in thing["properties"]["name"]
    assert len(thing["properties"]["name"]["description"]) < 500
    assert pruned["info"]["title"] == "keep-me"
    assert "title" in spec["components"]["schemas"]["Thing"]
