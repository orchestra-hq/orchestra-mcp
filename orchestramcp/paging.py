import json

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from orchestramcp.handwritten import MAX_RESULT_CHARS, _bound_strings

# Generated list tools whose pages routinely exceed the budget, each returning the
# API's {page, pageSize, total, results} envelope, mapped to the tool that returns
# one of its records in full (None where the API has no such endpoint).
PAGED_TOOLS = {
    "list_task_runs": "get_task_run",
    "list_task_runs_for_pipeline_run": "get_task_run",
    "list_assets": "get_asset_by_id",
    "list_incident_events": None,
    "list_operations": None,
}

_SHORT_FIELD_CHARS = 200


def _size(value) -> int:
    return len(json.dumps(value))


def shrink_page(payload: dict, getter: str | None = None, budget: int = MAX_RESULT_CHARS) -> dict:
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
        # ponytail: one record alone over the budget keeps only its top-level scalar
        # fields, strings cut short. Only a getter recovers what was cut.
        cut = _bound_strings(results[0], _SHORT_FIELD_CHARS)
        shrunk["results"] = [
            {key: value for key, value in cut.items() if not isinstance(value, (dict, list))}
        ]
        recover = (
            f"fetch it in full with {getter}"
            if getter
            else "the cut values are not available through any other tool"
        )
        shrunk["note"] += f" This record alone exceeds the limit, so it was cut; {recover}."
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
        shrunk = shrink_page(payload, PAGED_TOOLS[context.message.name])
        if shrunk is payload:
            return result
        # Meta makes the result bypass outputSchema validation, which the added note fails.
        return ToolResult(structured_content=shrunk, meta=result.meta or {})
