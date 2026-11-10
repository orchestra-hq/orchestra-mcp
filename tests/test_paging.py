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


def test_single_record_over_the_budget_keeps_its_top_level_fields():
    items = [
        {
            "id": 0,
            "message": "m" * 100_000,
            "runParameters": {f"k{i}": "v" * 50 for i in range(5_000)},
        }
    ]
    shrunk = shrink_page(_page(1, 1, items))
    assert len(json.dumps(shrunk)) <= MAX_RESULT_CHARS
    assert shrunk["results"][0]["id"] == 0
    assert "runParameters" not in shrunk["results"][0]
    assert "too large" in shrunk["note"]


async def test_middleware_shrinks_any_paged_envelope_only():
    server = FastMCP("test", middleware=[PageSizeMiddleware()])

    @server.tool
    def list_assets() -> dict:
        return _page(1, 50)

    @server.tool
    def list_audit_events() -> dict:
        return _page(1, 50)

    @server.tool
    def get_big() -> dict:
        return {"results": ITEMS}

    async with Client(server) as client:
        listed = await client.call_tool("list_assets", {})
        other_list = await client.call_tool("list_audit_events", {})
        untouched = await client.call_tool("get_big", {})

    assert len(listed.content[0].text) <= MAX_RESULT_CHARS
    assert listed.structured_content["pageSize"] == 10
    assert other_list.structured_content["pageSize"] == 10
    assert len(untouched.structured_content["results"]) == 100
