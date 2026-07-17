import base64
import json

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import ToolResult
from mcp.types import ToolAnnotations

# Operations excluded from generation because they are served by the hand-written
# tools below (binary downloads that need base64 wrapping).
HANDWRITTEN_OPERATION_IDS = ("download_task_run_log", "download_task_run_artifact")

# Cap on raw file bytes returned per call. Base64 inflates content by ~33% and the
# Lambda response payload is hard-limited to ~6MB, so 3MiB raw (~4MiB encoded)
# leaves headroom for the JSON-RPC and API Gateway wrapping. The result is returned
# as a single text content block (no structuredContent) so the payload is not
# duplicated in the response.
MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024

_RANGE_EXAMPLE = f"bytes=0-{MAX_DOWNLOAD_BYTES - 1}"

_DOWNLOAD_DESCRIPTION = (
    "Download a task run {kind} file, returned base64-encoded.{note} At most "
    f"{MAX_DOWNLOAD_BYTES // (1024 * 1024)}MiB of file content is returned per call; "
    f"fetch larger files in chunks by passing range_header (e.g. '{_RANGE_EXAMPLE}') "
    "and advancing the range each call."
)


def register_handwritten(server: FastMCP, client: httpx.AsyncClient, ui_base_url: str) -> None:
    """Register the tools that cannot be generated from the spec.

    ``get_pipeline_run_lineage_url`` has no backing endpoint; the downloads return
    binary content that is base64-encoded so it survives as JSON.
    """

    @server.tool(
        annotations=ToolAnnotations(title="Get Pipeline Run Lineage URL", readOnlyHint=True)
    )
    def get_pipeline_run_lineage_url(pipeline_run_id: str) -> str:
        """Build the URL of a pipeline run's lineage graph in the Orchestra UI."""
        return f"{ui_base_url}/pipeline-runs/{pipeline_run_id}/lineage"

    async def _download(path: str, filename: str, range_header: str | None = None) -> ToolResult:
        headers = {"Range": range_header} if range_header else None
        async with client.stream(
            "GET", path, params={"filename": filename}, headers=headers
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                hint = (
                    " The requested range is not satisfiable; check it against the file size."
                    if response.status_code == 416
                    else ""
                )
                raise ToolError(
                    f"Download of {filename} failed with HTTP {response.status_code}.{hint}"
                )
            chunks: list[bytes] = []
            received = 0
            async for chunk in response.aiter_bytes():
                received += len(chunk)
                if received > MAX_DOWNLOAD_BYTES:
                    raise ToolError(
                        f"{filename} chunk exceeds the {MAX_DOWNLOAD_BYTES} bytes of file "
                        f"content that can be returned per call. Request the file in chunks "
                        f"with range_header, e.g. '{_RANGE_EXAMPLE}', then advance the range."
                    )
                chunks.append(chunk)
        content = b"".join(chunks)
        result = {
            "filename": filename,
            "content": base64.b64encode(content).decode("utf-8"),
            "encoding": "base64",
            "size_bytes": len(content),
        }
        content_range = response.headers.get("content-range")
        if content_range:
            result["content_range"] = content_range
        return ToolResult(content=json.dumps(result))

    @server.tool(
        description=_DOWNLOAD_DESCRIPTION.format(kind="log", note=""),
        annotations=ToolAnnotations(title="Download Task Run Log", readOnlyHint=True),
    )
    async def download_task_run_log(
        pipeline_run_id: str, task_run_id: str, filename: str, range_header: str | None = None
    ) -> ToolResult:
        path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download"
        return await _download(path, filename, range_header)

    @server.tool(
        description=_DOWNLOAD_DESCRIPTION.format(
            kind="artifact", note=" Artifacts such as a dbt manifest.json are often tens of MB."
        ),
        annotations=ToolAnnotations(title="Download Task Run Artifact", readOnlyHint=True),
    )
    async def download_task_run_artifact(
        pipeline_run_id: str, task_run_id: str, filename: str, range_header: str | None = None
    ) -> ToolResult:
        path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download"
        return await _download(path, filename, range_header)
