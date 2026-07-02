from fastmcp import FastMCP

from orchestramcp.adaptations import adapt_component
from orchestramcp.spec import select_mcp_spec

SERVER_NAME = "Orchestra MCP Server"


def build_server(spec: dict, client, name: str = SERVER_NAME) -> FastMCP:
    """Build an MCP server from the x-mcp operations of an OpenAPI spec.

    Selection comes from the spec (upstream), presentation from the adaptation
    registry (this repo). ``client`` is the httpx transport tools call through.
    """
    return FastMCP.from_openapi(
        select_mcp_spec(spec),
        client=client,
        name=name,
        mcp_component_fn=adapt_component,
    )
