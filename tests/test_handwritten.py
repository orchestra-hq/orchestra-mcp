import base64

import httpx
from fastmcp import Client, FastMCP

from orchestramcp.handwritten import register_handwritten


def _server(handler=None, ui_base_url="https://stage.getorchestra.io"):
    handler = handler or (lambda request: httpx.Response(200, content=b""))
    client = httpx.AsyncClient(
        base_url="https://example.com/api/engine", transport=httpx.MockTransport(handler)
    )
    server = FastMCP("test")
    register_handwritten(server, client, ui_base_url)
    return server


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

    assert result.data["content"] == base64.b64encode(b"hello logs").decode()
    assert result.data["encoding"] == "base64"
    url, range_header = calls[0]
    assert url.endswith(
        "/api/engine/public/pipeline_runs/pr/task_runs/tr/logs/download?filename=run.log"
    )
    assert range_header == "bytes=-10"


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

    assert result.data["content"] == base64.b64encode(b"data").decode()
    assert calls[0].endswith("/task_runs/tr/artifacts/download?filename=manifest.json")
