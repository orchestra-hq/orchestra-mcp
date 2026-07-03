from pathlib import Path

from orchestramcp.spec import coarsen_spec, load_spec, mcp_operations, prune_spec, select_mcp_spec

SAMPLE = str(Path(__file__).parent / "fixtures" / "openapi_sample.json")
LIVE = str(Path(__file__).parent / "fixtures" / "openapi_live.json")


def test_select_keeps_only_flagged_operations():
    selected = select_mcp_spec(load_spec(SAMPLE))
    assert set(selected["paths"]) == {
        "/pipeline_runs",
        "/pipeline_runs/{pipeline_run_id}/cancel",
        "/assets",
    }


def test_mcp_operations_yields_flagged_only():
    ops = {op["operationId"] for _, _, op in mcp_operations(load_spec(SAMPLE))}
    assert ops == {"list_pipeline_runs", "cancel_pipeline_run", "list_assets"}


def test_select_gates_deletes():
    with_deletes = {op["operationId"] for _, _, op in _selected_ops(include_deletes=True)}
    without_deletes = {op["operationId"] for _, _, op in _selected_ops(include_deletes=False)}
    assert "delete_pipeline" in with_deletes
    assert "delete_pipeline" not in without_deletes


def test_select_excludes_named_operations():
    selected = select_mcp_spec(load_spec(LIVE), exclude_operation_ids=("download_task_run_log",))
    ops = {op.get("operationId") for item in selected["paths"].values() for op in item.values()}
    assert "download_task_run_log" not in ops


def test_coarsen_replaces_named_schema():
    spec = {
        "components": {"schemas": {"PipelineModel": {"type": "object", "properties": {"a": {}}}}}
    }
    model = coarsen_spec(spec)["components"]["schemas"]["PipelineModel"]
    assert model["additionalProperties"] is True
    assert "properties" not in model
    assert "validate_pipeline" in model["description"]


def test_prune_keeps_property_named_title():
    spec = {
        "components": {
            "schemas": {
                "Thing": {
                    "type": "object",
                    "required": ["title"],
                    "properties": {"title": {"type": "string", "title": "noise"}},
                }
            }
        }
    }
    props = prune_spec(spec)["components"]["schemas"]["Thing"]["properties"]
    assert "title" in props  # the field literally named 'title' survives
    assert "title" not in props["title"]  # its schema-level noise title is stripped


def test_select_preserves_path_item_parameters():
    spec = {
        "paths": {
            "/pipelines/{id}": {
                "parameters": [{"name": "id", "in": "path", "required": True}],
                "get": {"operationId": "get_thing", "x-orchestra-mcp": True},
            }
        }
    }
    item = select_mcp_spec(spec)["paths"]["/pipelines/{id}"]
    assert item["parameters"] == [{"name": "id", "in": "path", "required": True}]
    assert "get" in item


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


def _selected_ops(include_deletes):
    selected = select_mcp_spec(load_spec(LIVE), include_deletes=include_deletes)
    return [(p, m, op) for p, item in selected["paths"].items() for m, op in item.items()]
