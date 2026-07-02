import json
from pathlib import Path

import httpx

MCP_EXTENSION = "x-mcp"
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def load_spec(source: str) -> dict:
    """Load an OpenAPI document from an http(s) URL or a local file path."""
    if source.startswith(("http://", "https://")):
        response = httpx.get(source, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    return json.loads(Path(source).read_text(encoding="utf-8"))


def mcp_operations(spec: dict):
    """Yield (path, method, operation) for every operation flagged ``x-mcp``."""
    for path, item in spec.get("paths", {}).items():
        for method, operation in item.items():
            if method not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            if operation.get(MCP_EXTENSION):
                yield path, method, operation


def select_mcp_spec(spec: dict) -> dict:
    """Return a copy of the spec whose paths contain only ``x-mcp`` operations.

    The upstream API owns which endpoints are exposed by flagging them; the MCP
    is whatever the spec says is flagged, so there is no local list to drift.
    """
    paths: dict = {}
    for path, method, operation in mcp_operations(spec):
        paths.setdefault(path, {})[method] = operation
    return {**spec, "paths": paths}
