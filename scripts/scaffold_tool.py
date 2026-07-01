#!/usr/bin/env python3
"""Scaffold a new MCP tool from an Orchestra OpenAPI operation.

The MCP is a curated surface, so this does NOT auto-register anything — it prints
starting-point stubs (a client method, a ``@mcp.tool`` function, and an ``api_contract``
entry) with ``TODO`` markers for you to paste in and hand-finish. This keeps the "add an
endpoint" workflow fast while leaving the curation (naming, docstrings, response shaping,
auth/annotations) a human decision.

Usage:
    python scripts/scaffold_tool.py --path /assets/{asset_id} --method get
    python scripts/scaffold_tool.py --operation-id get_asset_by_id_api_public_assets__asset_id__get
    python scripts/scaffold_tool.py --path /assets --method post --tool-name create_asset
"""

import argparse
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(_PROJECT_ROOT), str(_SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from check_api_conformance import HTTP_METHODS, load_spec  # noqa: E402

from orchestramcp.api_contract import LIVE_SPEC_URL, PUBLIC_PREFIX  # noqa: E402

OPENAPI_TYPE_TO_PY = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "str",  # Orchestra list filters are comma-separated strings
    "object": "dict[str, Any]",
}


def _py_type(schema: dict | None) -> str:
    if not isinstance(schema, dict):
        return "str"
    if "type" in schema:
        return OPENAPI_TYPE_TO_PY.get(schema["type"], "str")
    # anyOf/allOf (e.g. nullable) — take the first concrete type we recognise.
    for key in ("anyOf", "oneOf", "allOf"):
        for sub in schema.get(key, []):
            if isinstance(sub, dict) and sub.get("type") in OPENAPI_TYPE_TO_PY:
                return OPENAPI_TYPE_TO_PY[sub["type"]]
    return "str"


def _snake(text: str) -> str:
    text = re.sub(r"[^0-9a-zA-Z]+", "_", text).strip("_")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return text.lower()


def _suggest_tool_name(method: str, client_path: str) -> str:
    """Heuristic tool name from method + path (e.g. GET /assets -> list_assets)."""
    segments = [s for s in client_path.split("/") if s and not s.startswith("{")]
    resource = _snake(segments[-1]) if segments else "resource"
    has_path_param = "{" in client_path.split("/")[-1]
    verb = {
        "get": "get" if has_path_param else "list",
        "post": "create",
        "put": "update",
        "patch": "update",
        "delete": "delete",
    }.get(method, method)
    if verb == "list" and not resource.endswith("s"):
        resource += "s"
    return f"{verb}_{resource}"


def _find_operation(spec: dict, path: str | None, method: str | None, operation_id: str | None):
    """Return (full_path, method, operation) for the requested operation."""
    paths = spec.get("paths", {})
    if operation_id:
        for p, item in paths.items():
            if not isinstance(item, dict):
                continue
            for m, op in item.items():
                if (
                    m in HTTP_METHODS
                    and isinstance(op, dict)
                    and op.get("operationId") == operation_id
                ):
                    return p, m, op
        raise SystemExit(f"operationId '{operation_id}' not found in spec")

    if not (path and method):
        raise SystemExit("provide either --operation-id, or both --path and --method")
    method = method.lower()
    full_path = path if path.startswith(PUBLIC_PREFIX) else f"{PUBLIC_PREFIX}{path}"
    item = paths.get(full_path)
    if not isinstance(item, dict) or method not in item:
        raise SystemExit(f"{method.upper()} {full_path} not found in spec")
    return full_path, method, item[method]


def scaffold(
    spec: dict, full_path: str, method: str, operation: dict, tool_name: str | None
) -> str:
    client_path = full_path[len(PUBLIC_PREFIX) :] or "/"
    tool_name = tool_name or _suggest_tool_name(method, client_path)
    summary = operation.get("summary") or tool_name.replace("_", " ").title()
    description = operation.get("description") or summary
    read_only = method == "get"

    params = operation.get("parameters", [])
    path_params = [p for p in params if isinstance(p, dict) and p.get("in") == "path"]
    query_params = [p for p in params if isinstance(p, dict) and p.get("in") == "query"]
    has_body = "requestBody" in operation

    # --- signature pieces (path params first, then required query, then optional) ---
    sig: list[str] = []
    for p in path_params:
        sig.append(f"{p['name']}: {_py_type(p.get('schema'))}")
    if has_body:
        sig.append("payload: dict[str, Any]")
    for p in query_params:
        py = _py_type(p.get("schema"))
        if p.get("required"):
            sig.append(f"{p['name']}: {py}")
        else:
            sig.append(f"{p['name']}: {py} | None = None")
    sig_str = ", ".join(sig)
    client_sig = f"self, {sig_str}" if sig_str else "self"

    # Path params already appear as {name} in client_path, so an f-string literal
    # interpolates them directly.
    path_literal = f'f"{client_path}"' if path_params else f'"{client_path}"'

    qp_kwargs = ", ".join(f"{p['name']}={p['name']}" for p in query_params)
    call_args = ", ".join(
        [p["name"] for p in path_params]
        + (["payload=payload"] if has_body else [])
        + [f"{p['name']}={p['name']}" for p in query_params]
    )
    request_call = f"await self._client.{method}({path_literal}"
    if qp_kwargs:
        request_call += f", params=self._build_query_params({qp_kwargs})"
    if has_body:
        request_call += ", json=payload"
    request_call += ")"

    # --- contract entry ---
    contract_qps = ", ".join(
        f'QueryParam("{p["name"]}"' + (", required=True)" if p.get("required") else ")")
        for p in query_params
    )
    contract_lines = [
        "    ToolContract(",
        f'        tool="{tool_name}",',
        f'        method="{method}",',
        f'        path="{client_path}",',
    ]
    if query_params:
        contract_lines.append(f"        query_params=({contract_qps},),")
    if has_body:
        contract_lines.append("        sends_body=True,")
    contract_lines.append("    ),")
    contract_block = "\n".join(contract_lines)

    args_doc = (
        "\n".join(
            f"            {p['name']}: {p.get('description', 'TODO')}"
            for p in (path_params + query_params)
        )
        or "            (none)"
    )

    return f"""\
# ============================================================================
# Scaffold for {method.upper()} {full_path}  ->  tool `{tool_name}`
# Review names/types, replace TODOs, wire a response model, then delete this banner.
# ============================================================================

# ---- 1. orchestramcp/client.py : add to class OrchestraClient -------------

    async def {tool_name}({client_sig}) -> dict:
        \"\"\"{summary} ({method.upper()} {client_path}).

        TODO: replace the dict return with a pydantic model in models.py.
        \"\"\"
        response = {request_call}
        self._raise_for_status(response)
        return response.json()


# ---- 2. orchestramcp/server.py : add near related tools -------------------

@mcp.tool(annotations=ToolAnnotations(title="{summary}", readOnlyHint={read_only}))
async def {tool_name}({sig_str}) -> dict:
    \"\"\"{description}

    Args:
{args_doc}

    Reference:
        https://docs.getorchestra.io/api/  # TODO: exact doc URL
    \"\"\"
    async with get_client() as client:
        result = await client.{tool_name}({call_args})
        return result  # TODO: `.model_dump()` once a response model exists


# ---- 3. orchestramcp/api_contract.py : add to TOOL_CONTRACTS --------------

{contract_block}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", default=LIVE_SPEC_URL, help="OpenAPI URL or file path.")
    parser.add_argument("--path", help="Client-relative or public path, e.g. /assets/{asset_id}.")
    parser.add_argument("--method", help="HTTP method (get/post/put/patch/delete).")
    parser.add_argument(
        "--operation-id", help="Match by OpenAPI operationId instead of path+method."
    )
    parser.add_argument("--tool-name", help="Override the suggested tool name.")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    full_path, method, operation = _find_operation(spec, args.path, args.method, args.operation_id)
    print(scaffold(spec, full_path, method, operation, args.tool_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
