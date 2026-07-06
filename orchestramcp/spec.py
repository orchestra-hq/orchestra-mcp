import json
from pathlib import Path

import httpx

MCP_EXTENSION = "x-orchestra-mcp"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")

_NOISE_KEYS = ("title", "example", "examples")
_MAX_DESCRIPTION = 300

# JSON Schema keywords whose values are subschemas, so pruning recurses into them
# rather than treating name-keyed maps (e.g. properties) as schemas themselves.
_SUBSCHEMA_KEYS = ("items", "additionalProperties", "not", "if", "then", "else")
_SUBSCHEMA_LISTS = ("allOf", "anyOf", "oneOf", "prefixItems")
_SUBSCHEMA_MAPS = ("properties", "patternProperties", "$defs", "definitions")

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
        if not isinstance(item, dict):
            continue
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
    default, and operations handled by hand-written tools can be excluded. Path-item
    level fields (e.g. shared parameters) are preserved alongside the kept operations.
    """
    excluded = set(exclude_operation_ids)
    paths: dict = {}
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        kept = {}
        for method, operation in item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            if not operation.get(MCP_EXTENSION):
                continue
            if method == "delete" and not include_deletes:
                continue
            if operation.get("operationId") in excluded:
                continue
            kept[method] = operation
        if kept:
            shared = {k: v for k, v in item.items() if k not in _HTTP_METHODS}
            paths[path] = {**shared, **kept}
    return {**spec, "paths": paths}


def coarsen_spec(spec: dict) -> dict:
    """Replace the oversized component schemas in COARSEN_SCHEMAS with a described
    object. Mutates ``spec`` in place and returns it."""
    schemas = spec.get("components", {}).get("schemas", {})
    for name, description in COARSEN_SCHEMAS.items():
        if name in schemas:
            schemas[name] = {
                "type": "object",
                "additionalProperties": True,
                "description": description,
            }
    return spec


def _prune_schema(schema) -> None:
    if not isinstance(schema, dict):
        return
    for key in _NOISE_KEYS:
        schema.pop(key, None)
    description = schema.get("description")
    if isinstance(description, str) and len(description) > _MAX_DESCRIPTION:
        schema["description"] = description[:_MAX_DESCRIPTION].rstrip() + "..."
    for key in _SUBSCHEMA_KEYS:
        _prune_schema(schema.get(key))
    for key in _SUBSCHEMA_LISTS:
        for item in schema.get(key) or []:
            _prune_schema(item)
    for key in _SUBSCHEMA_MAPS:
        for value in (schema.get(key) or {}).values():
            _prune_schema(value)


def _prune_parameters(parameters) -> None:
    for parameter in parameters or []:
        if isinstance(parameter, dict):
            _prune_schema(parameter.get("schema"))


def prune_spec(spec: dict) -> dict:
    """Strip schema noise (auto titles, examples, long descriptions) from request
    schemas to keep tool schemas small — every one is tokens the model re-reads each
    call. Mutates ``spec`` in place and returns it."""
    for schema in spec.get("components", {}).get("schemas", {}).values():
        _prune_schema(schema)
    for item in spec.get("paths", {}).values():
        if not isinstance(item, dict):
            continue
        _prune_parameters(item.get("parameters"))
        for method, operation in item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            _prune_parameters(operation.get("parameters"))
            for content in operation.get("requestBody", {}).get("content", {}).values():
                if isinstance(content, dict):
                    _prune_schema(content.get("schema"))
    return spec
