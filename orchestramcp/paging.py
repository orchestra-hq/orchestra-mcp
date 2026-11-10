import json

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from orchestramcp.handwritten import MAX_RESULT_CHARS, _bound_strings

# The tool that returns one record of a paged list in full, named in the note when
# a single record has to be cut to fit.
FULL_RECORD_TOOLS = {
    "list_task_runs": "get_task_run",
    "list_task_runs_for_pipeline_run": "get_task_run",
    "list_assets": "get_asset_by_id",
    "list_pipeline_runs": "get_pipeline_run",
    "list_incidents": "get_incident",
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
        last = new_page * size >= (payload.get("total") or 0) and len(results) <= size
        shrunk = {
            **payload,
            "page": new_page,
            "pageSize": size,
            "results": results[:size],
            "note": f"Page size reduced from {page_size} to {size} to fit the result size limit. "
            + (
                "This is the last page."
                if last
                else f"Continue with page={new_page + 1}, page_size={size}."
            ),
        }
        if size == 1 or _size(shrunk) <= budget:
            break
    if _size(shrunk) > budget:
        # One record alone over the budget keeps only its top-level scalar fields,
        # strings cut short. Only a full-record tool recovers what was cut.
        cut = _bound_strings(results[0], _SHORT_FIELD_CHARS)
        shrunk["results"] = [
            {key: value for key, value in cut.items() if not isinstance(value, (dict, list))}
        ]
        recover = (
            f"fetch it in full with {getter}"
            if getter
            else "fetch it in full with this record's get_* tool, if there is one"
        )
        shrunk["note"] += f" This record alone exceeds the limit, so it was cut; {recover}."
    return shrunk


class PageSizeMiddleware(Middleware):
    """Keep any tool returning the API's {page, pageSize, total, results} envelope under
    the size an agent can read in line."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        payload = result.structured_content
        paged = (
            isinstance(payload, dict)
            and isinstance(payload.get("results"), list)
            and isinstance(payload.get("pageSize"), int)
        )
        if not paged:
            return result
        shrunk = shrink_page(payload, FULL_RECORD_TOOLS.get(context.message.name))
        if shrunk is payload:
            return result
        # Meta makes the result bypass outputSchema validation, which the added note fails.
        return ToolResult(structured_content=shrunk, meta=result.meta or {})
