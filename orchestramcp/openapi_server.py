import httpx
from fastmcp import FastMCP

from orchestramcp.adaptations import adapt_component
from orchestramcp.handwritten import HANDWRITTEN_OPERATION_IDS, register_handwritten
from orchestramcp.spec import coarsen_spec, prune_spec, select_mcp_spec

SERVER_NAME = "Orchestra MCP Server"


def build_server(
    spec: dict, client: httpx.AsyncClient, include_deletes: bool = False, name: str = SERVER_NAME
) -> FastMCP:
    """Build an MCP server from the flagged operations of an OpenAPI spec.

    Selection comes from the spec (upstream); presentation from the adaptation
    registry (this repo). Oversized bodies are coarsened and schema noise pruned to
    keep the surface small, then the hand-written tools are registered alongside.
    """
    selected = select_mcp_spec(
        spec, include_deletes=include_deletes, exclude_operation_ids=HANDWRITTEN_OPERATION_IDS
    )
    prepared = prune_spec(coarsen_spec(selected))
    server = FastMCP.from_openapi(
        openapi_spec=prepared,
        client=client,
        name=name,
        mcp_component_fn=adapt_component,
        validate_output=False,
    )
    register_handwritten(server, client)
    return server
