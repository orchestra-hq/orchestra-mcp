import json

from fastmcp import Client, FastMCP

from orchestramcp.paging import MAX_RESULT_CHARS, PageSizeMiddleware, shrink_page

ITEMS = [{"id": i, "blob": "x" * 3_000} for i in range(100)]


def _page(page: int, page_size: int, items=ITEMS) -> dict:
    start = (page - 1) * page_size
    return {
        "page": page,
        "pageSize": page_size,
        "total": len(items),
        "results": items[start : start + page_size],
    }


def test_small_page_is_returned_untouched():
    payload = _page(1, 5)
    assert shrink_page(payload) is payload


def test_following_shrunk_pages_reaches_every_item_once():
    # Start at page 2 of 50, as an agent might, then follow the notes to the end.
    seen = list(range(50))
    page, page_size = 2, 50
    while (page - 1) * page_size < len(ITEMS):
        shrunk = shrink_page(_page(page, page_size))
        assert len(json.dumps(shrunk)) <= MAX_RESULT_CHARS
        seen += [item["id"] for item in shrunk["results"]]
        page, page_size = shrunk["page"] + 1, shrunk["pageSize"]
    assert seen == list(range(100))


def test_shrunk_page_names_the_next_call():
    shrunk = shrink_page(_page(1, 50))
    assert shrunk["pageSize"] == 10
    assert shrunk["page"] == 1
    assert f"page={2}, page_size={10}" in shrunk["note"]


def test_single_record_over_the_budget_has_long_strings_cut():
    items = [{"id": 0, "taskParameters": {"script": "x" * 100_000}}]
    shrunk = shrink_page(_page(1, 1, items), "get_task_run")
    assert len(json.dumps(shrunk)) <= MAX_RESULT_CHARS
    assert shrunk["results"][0]["id"] == 0
    assert "get_task_run" in shrunk["note"]


def test_single_record_with_many_small_fields_still_fits():
    items = [{"id": 0, "runParameters": {f"k{i}": "v" * 50 for i in range(5_000)}}]
    shrunk = shrink_page(_page(1, 1, items))
    assert len(json.dumps(shrunk)) <= MAX_RESULT_CHARS
    assert shrunk["results"] == [{"id": 0}]
    assert "not available through any other tool" in shrunk["note"]


async def test_middleware_shrinks_only_paged_tools():
    server = FastMCP("test", middleware=[PageSizeMiddleware()])

    @server.tool
    def list_assets() -> dict:
        return _page(1, 50)

    @server.tool
    def other() -> dict:
        return _page(1, 50)

    async with Client(server) as client:
        shrunk = await client.call_tool("list_assets", {})
        untouched = await client.call_tool("other", {})

    assert len(shrunk.content[0].text) <= MAX_RESULT_CHARS
    assert shrunk.structured_content["pageSize"] == 10
    assert untouched.structured_content["pageSize"] == 50
