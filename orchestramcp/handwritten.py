import base64

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

# Operations excluded from generation because they are served by the hand-written
# tools below (binary downloads that need base64 wrapping).
HANDWRITTEN_OPERATION_IDS = ("download_task_run_log", "download_task_run_artifact")

# Cap on raw file bytes returned per call. Base64 inflates content by ~33% and the
# Lambda response payload is hard-limited to ~6MB, so 3MiB raw (~4MiB encoded)
# leaves headroom for the JSON-RPC and API Gateway wrapping.
MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024

_RANGE_EXAMPLE = f"bytes=0-{MAX_DOWNLOAD_BYTES - 1}"


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

    async def _download(path: str, filename: str, range_header: str | None = None) -> dict:
        headers = {"Range": range_header} if range_header else None
        response = await client.get(path, params={"filename": filename}, headers=headers)
        content = response.content
        if len(content) > MAX_DOWNLOAD_BYTES:
            raise ToolError(
                f"{filename} chunk is {len(content)} bytes; at most {MAX_DOWNLOAD_BYTES} bytes "
                f"of file content can be returned per call. Request the file in chunks with "
                f"range_header, e.g. '{_RANGE_EXAMPLE}', then advance the range."
            )
        result = {
            "filename": filename,
            "content": base64.b64encode(content).decode("utf-8"),
            "encoding": "base64",
            "size_bytes": len(content),
        }
        content_range = response.headers.get("content-range")
        if content_range:
            result["content_range"] = content_range
        return result

    @server.tool(annotations=ToolAnnotations(title="Download Task Run Log", readOnlyHint=True))
    async def download_task_run_log(
        pipeline_run_id: str, task_run_id: str, filename: str, range_header: str | None = None
    ) -> dict:
        """Download a task run log file, returned base64-encoded. At most 3MiB of file
        content is returned per call; fetch larger files in chunks by passing
        range_header (e.g. 'bytes=0-1048575') and advancing the range each call."""
        path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download"
        return await _download(path, filename, range_header)

    @server.tool(annotations=ToolAnnotations(title="Download Task Run Artifact", readOnlyHint=True))
    async def download_task_run_artifact(
        pipeline_run_id: str, task_run_id: str, filename: str, range_header: str | None = None
    ) -> dict:
        """Download a task run artifact file, returned base64-encoded. Artifacts such as
        a dbt manifest.json are often tens of MB; at most 3MiB of file content is returned
        per call, so fetch large files in chunks by passing range_header
        (e.g. 'bytes=0-1048575') and advancing the range each call."""
        path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download"
        return await _download(path, filename, range_header)
