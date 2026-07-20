import base64
import json

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from orchestramcp.handwritten import MAX_DOWNLOAD_BYTES, register_handwritten


def _server(handler=None, ui_base_url="https://stage.getorchestra.io"):
    handler = handler or (lambda request: httpx.Response(200, content=b""))
    client = httpx.AsyncClient(
        base_url="https://example.com/api/engine", transport=httpx.MockTransport(handler)
    )
    server = FastMCP("test")
    register_handwritten(server, client, ui_base_url)
    return server


def _download_result(result) -> dict:
    return json.loads(result.content[0].text)


async def test_lineage_url_uses_ui_base():
    async with Client(_server(ui_base_url="https://stage.getorchestra.io")) as client:
        result = await client.call_tool("get_pipeline_run_lineage_url", {"pipeline_run_id": "r1"})
    assert result.data == "https://stage.getorchestra.io/pipeline-runs/r1/lineage"


async def test_download_log_base64_encodes_with_range():
    calls = []

    def handler(request):
        calls.append((str(request.url), request.headers.get("Range")))
        return httpx.Response(200, content=b"hello logs")

    async with Client(_server(handler)) as client:
        result = await client.call_tool(
            "download_task_run_log",
            {
                "pipeline_run_id": "pr",
                "task_run_id": "tr",
                "filename": "run.log",
                "range_header": "bytes=-10",
            },
        )

    data = _download_result(result)
    assert data["content"] == base64.b64encode(b"hello logs").decode()
    assert data["encoding"] == "base64"
    url, range_header = calls[0]
    assert url.endswith(
        "/api/engine/public/pipeline_runs/pr/task_runs/tr/logs/download?filename=run.log"
    )
    assert range_header == "bytes=-10"


async def test_download_result_is_not_duplicated_as_structured_content():
    async with Client(_server(lambda request: httpx.Response(200, content=b"data"))) as client:
        result = await client.call_tool(
            "download_task_run_log",
            {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "run.log"},
        )

    assert result.structured_content is None
    assert len(result.content) == 1


async def test_download_artifact_hits_artifacts_path():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"data")

    async with Client(_server(handler)) as client:
        result = await client.call_tool(
            "download_task_run_artifact",
            {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "manifest.json"},
        )

    assert _download_result(result)["content"] == base64.b64encode(b"data").decode()
    assert calls[0].endswith("/task_runs/tr/artifacts/download?filename=manifest.json")


async def test_download_over_cap_errors_with_range_guidance():
    def handler(request):
        return httpx.Response(200, content=b"x" * (MAX_DOWNLOAD_BYTES + 1))

    async with Client(_server(handler)) as client:
        with pytest.raises(ToolError, match="range_header"):
            await client.call_tool(
                "download_task_run_artifact",
                {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "manifest.json"},
            )


async def test_download_artifact_forwards_range_and_returns_content_range():
    calls = []

    def handler(request):
        calls.append(request.headers.get("Range"))
        return httpx.Response(206, content=b"2345", headers={"Content-Range": "bytes 2-5/10"})

    async with Client(_server(handler)) as client:
        result = await client.call_tool(
            "download_task_run_artifact",
            {
                "pipeline_run_id": "pr",
                "task_run_id": "tr",
                "filename": "manifest.json",
                "range_header": "bytes=2-5",
            },
        )

    data = _download_result(result)
    assert calls[0] == "bytes=2-5"
    assert base64.b64decode(data["content"]) == b"2345"
    assert data["size_bytes"] == 4
    assert data["content_range"] == "bytes 2-5/10"


async def test_download_http_error_raises_tool_error():
    def handler(request):
        return httpx.Response(404, content=b"not found")

    async with Client(_server(handler)) as client:
        with pytest.raises(ToolError, match="HTTP 404"):
            await client.call_tool(
                "download_task_run_log",
                {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "missing.log"},
            )


async def test_download_unsatisfiable_range_raises_tool_error_with_hint():
    def handler(request):
        return httpx.Response(416, content=b"")

    async with Client(_server(handler)) as client:
        with pytest.raises(ToolError, match="not satisfiable"):
            await client.call_tool(
                "download_task_run_log",
                {
                    "pipeline_run_id": "pr",
                    "task_run_id": "tr",
                    "filename": "run.log",
                    "range_header": "bytes=99999999-",
                },
            )
