import json

import mcp.types as mt
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.tool import ToolResult

from orchestramcp.handwritten import MAX_RESULT_CHARS, _bound_strings


def _size(value) -> int:
    return len(json.dumps(value))


def shrink_page(payload: dict, budget: int = MAX_RESULT_CHARS) -> dict:
    """Cut an oversized page to the largest page size that divides it and fits.

    Because the new size divides the old one, the records kept are exactly a page at
    the new size, so the agent continues from the next page without a gap or repeat.
    """
    if _size(payload) <= budget:
        return payload
    page, size, results = payload.get("page") or 1, payload["pageSize"], payload["results"]
    for new_size in (d for d in range(size, 0, -1) if size % d == 0):
        new_page = (page - 1) * size // new_size + 1
        shrunk = {
            **payload,
            "page": new_page,
            "pageSize": new_size,
            "results": results[:new_size],
            "note": f"Page too large, so cut to page_size={new_size}. "
            f"Continue with page={new_page + 1}, page_size={new_size}.",
        }
        if _size(shrunk) <= budget:
            return shrunk
    # A single record over the budget keeps only its top-level fields, strings cut short.
    record = _bound_strings(results[0], 200)
    shrunk["results"] = [{k: v for k, v in record.items() if not isinstance(v, (dict, list))}]
    shrunk["note"] += " This record alone is too large, so only its top-level fields are shown."
    return shrunk


class PageSizeMiddleware(Middleware):
    """Keep any result in the API's {page, pageSize, total, results} envelope small
    enough for an agent to read in line."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[mt.CallToolRequestParams],
        call_next: CallNext[mt.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        payload = result.structured_content
        if not (
            isinstance(payload, dict)
            and isinstance(payload.get("results"), list)
            and isinstance(payload.get("pageSize"), int)
            and payload["results"]
        ):
            return result
        shrunk = shrink_page(payload)
        if shrunk is payload:
            return result
        # Meta makes the result bypass outputSchema validation, which the added note fails.
        return ToolResult(structured_content=shrunk, meta=result.meta or {})
