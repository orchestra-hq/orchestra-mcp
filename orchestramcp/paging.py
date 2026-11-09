import json

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from orchestramcp.handwritten import MAX_PARAMETER_CHARS, _bound_strings

# Claude Code saves a text tool result over 50,000 characters (or 25,000 tokens) to a
# file instead of showing it to the model; agents then shell out to read it back.
# Results are kept under this budget with headroom for the envelope and the note.
MAX_RESULT_CHARS = 40_000

# Generated list tools whose pages routinely exceed the budget. Each returns the
# API's {page, pageSize, total, results} envelope.
PAGED_TOOLS = frozenset(
    {
        "list_task_runs",
        "list_task_runs_for_pipeline_run",
        "list_assets",
        "list_incident_events",
        "list_operations",
    }
)


def _size(value) -> int:
    return len(json.dumps(value))


def shrink_page(payload: dict, budget: int = MAX_RESULT_CHARS) -> dict:
    """Shrink an oversized page to a smaller page size that fits ``budget``.

    The new size divides the old one, so the items kept are exactly page
    ``(page - 1) * (old // new) + 1`` at the new size, and the agent continues with
    the next page at that size without skipping or repeating an item.
    """
    if _size(payload) <= budget:
        return payload
    results = payload.get("results")
    if not results:
        return payload
    page, page_size = payload.get("page") or 1, payload.get("pageSize") or len(results)
    for size in sorted((d for d in range(1, page_size + 1) if page_size % d == 0), reverse=True):
        new_page = (page - 1) * (page_size // size) + 1
        shrunk = {
            **payload,
            "page": new_page,
            "pageSize": size,
            "results": results[:size],
            "note": (
                f"Page size reduced from {page_size} to {size} to fit the result size limit. "
                f"Continue with page={new_page + 1}, page_size={size}."
            ),
        }
        if size == 1 or _size(shrunk) <= budget:
            break
    if _size(shrunk) > budget:
        # ponytail: one record alone over the budget has its long strings cut; the
        # full record stays reachable through the matching get_* tool.
        shrunk["results"] = _bound_strings(shrunk["results"])
        shrunk["note"] += (
            f" This record alone exceeds the limit, so strings over {MAX_PARAMETER_CHARS} "
            "characters are cut; get_task_run and get_asset_by_id return a record in full."
        )
    return shrunk


class PageSizeMiddleware(Middleware):
    """Keep the paged list tools' results under the size an agent can read in line."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        payload = result.structured_content
        if context.message.name not in PAGED_TOOLS or not isinstance(payload, dict):
            return result
        shrunk = shrink_page(payload)
        if shrunk is payload:
            return result
        # Meta makes the result bypass outputSchema validation, which the added note fails.
        return ToolResult(structured_content=shrunk, meta=result.meta or {})
