import copy
import json
from pathlib import Path

import httpx

MCP_EXTENSION = "x-orchestra-mcp"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")

_NOISE_KEYS = ("title", "example", "examples")
_MAX_DESCRIPTION = 300

# Component schemas replaced with a generic object to keep tool schemas small. The
# structure is described instead of enumerated; the validate_pipeline tool checks it.
COARSEN_SCHEMAS = {
    "PipelineModel": (
        "Pipeline definition as JSON, matching the pipeline YAML structure. "
        "Validate it with the validate_pipeline tool before submitting."
    ),
}


def load_spec(source: str) -> dict:
    """Load an OpenAPI document from an http(s) URL or a local file path."""
    if source.startswith(("http://", "https://")):
        response = httpx.get(source, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    return json.loads(Path(source).read_text(encoding="utf-8"))


def mcp_operations(spec: dict):
    """Yield (path, method, operation) for every operation flagged for the MCP."""
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            if operation.get(MCP_EXTENSION):
                yield path, method, operation


def select_mcp_spec(
    spec: dict, include_deletes: bool = True, exclude_operation_ids: tuple[str, ...] = ()
) -> dict:
    """Return a copy of the spec whose paths contain only flagged operations.

    The upstream API owns which endpoints are exposed via the extension flag, so
    there is no local list of tools to drift. DELETE operations are gated off by
    default, and operations handled by hand-written tools can be excluded.
    """
    excluded = set(exclude_operation_ids)
    paths: dict = {}
    for path, method, operation in mcp_operations(spec):
        if method == "delete" and not include_deletes:
            continue
        if operation.get("operationId") in excluded:
            continue
        paths.setdefault(path, {})[method] = operation
    return {**spec, "paths": paths}


def coarsen_spec(spec: dict) -> dict:
    """Replace the oversized component schemas in COARSEN_SCHEMAS with a described object."""
    coarsened = copy.deepcopy(spec)
    schemas = coarsened.get("components", {}).get("schemas", {})
    for name, description in COARSEN_SCHEMAS.items():
        if name in schemas:
            schemas[name] = {
                "type": "object",
                "additionalProperties": True,
                "description": description,
            }
    return coarsened


def _prune_schema(node) -> None:
    if isinstance(node, dict):
        for key in _NOISE_KEYS:
            node.pop(key, None)
        description = node.get("description")
        if isinstance(description, str) and len(description) > _MAX_DESCRIPTION:
            node["description"] = description[:_MAX_DESCRIPTION].rstrip() + "..."
        for value in node.values():
            _prune_schema(value)
    elif isinstance(node, list):
        for item in node:
            _prune_schema(item)


def prune_spec(spec: dict) -> dict:
    """Strip schema noise from a copy of the spec to keep tool schemas small.

    Removes auto-generated titles and examples and truncates long descriptions in
    request schemas — every one of these is tokens the model re-reads each call.
    """
    pruned = copy.deepcopy(spec)
    for schema in pruned.get("components", {}).get("schemas", {}).values():
        _prune_schema(schema)
    for item in pruned.get("paths", {}).values():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            for parameter in operation.get("parameters", []):
                _prune_schema(parameter.get("schema"))
            for content in operation.get("requestBody", {}).get("content", {}).values():
                _prune_schema(content.get("schema"))
    return pruned
