from copy import deepcopy
from dataclasses import dataclass

import httpx
from fastmcp import FastMCP
from fastmcp.server.providers import OpenAPIProvider

from orchestramcp.adaptations import adapt_component
from orchestramcp.handwritten import HANDWRITTEN_OPERATION_IDS, register_handwritten
from orchestramcp.spec import (
    coarsen_spec,
    patch_request_bodies,
    prune_spec,
    select_mcp_spec,
    tool_names,
)

SERVER_NAME = "Orchestra MCP Server"
DEFAULT_UI_BASE_URL = "https://app.getorchestra.io"


@dataclass(frozen=True)
class ApiSource:
    """An API to generate tools from. It carries its own client because FastMCP binds
    one per provider and ignores the document's own ``servers`` once a client is passed."""

    spec: dict
    client: httpx.AsyncClient


def _prepare(spec: dict, include_deletes: bool) -> dict:
    """Narrow a spec to the operations tools are generated from, shrinking the schemas
    the model re-reads on every call and patching in the request bodies it lacks."""
    selected = select_mcp_spec(
        spec,
        include_deletes=include_deletes,
        exclude_operation_ids=HANDWRITTEN_OPERATION_IDS,
    )
    return patch_request_bodies(prune_spec(coarsen_spec(deepcopy(selected))))


def build_server(
    engine: ApiSource,
    platform: ApiSource,
    include_deletes: bool = False,
    name: str = SERVER_NAME,
    ui_base_url: str = DEFAULT_UI_BASE_URL,
) -> FastMCP:
    """Build an MCP server from the flagged operations of both Orchestra APIs.

    Tools are not namespaced by source, so a name both APIs claim is refused here
    rather than letting the provider registered first silently shadow the other.
    """
    server = FastMCP(name=name)
    taken: set[str] = set()
    for source in (engine, platform):
        prepared = _prepare(source.spec, include_deletes)
        names = tool_names(prepared)
        generated = set(names.values())
        if clashes := taken & generated:
            raise ValueError(f"Both Orchestra APIs generate the tool(s) {sorted(clashes)}")
        taken |= generated
        server.add_provider(
            OpenAPIProvider(
                openapi_spec=prepared,
                client=source.client,
                mcp_component_fn=adapt_component,
                mcp_names=names,
                validate_output=False,
            )
        )
    register_handwritten(server, engine.client, ui_base_url)
    return server
