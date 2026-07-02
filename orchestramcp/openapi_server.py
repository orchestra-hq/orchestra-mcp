import httpx
from fastmcp import FastMCP

from orchestramcp.adaptations import adapt_component
from orchestramcp.spec import prune_spec, select_mcp_spec

SERVER_NAME = "Orchestra MCP Server"


def build_server(spec: dict, client: httpx.AsyncClient, name: str = SERVER_NAME) -> FastMCP:
    """Build an MCP server from the flagged operations of an OpenAPI spec.

    Selection comes from the spec (upstream), presentation from the adaptation
    registry (this repo). ``client`` is the httpx transport tools call through.
    """
    return FastMCP.from_openapi(
        openapi_spec=prune_spec(select_mcp_spec(spec)),
        client=client,
        name=name,
        mcp_component_fn=adapt_component,
    )
