import base64
import os

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

# Operations excluded from generation because they are served by the hand-written
# tools below (binary downloads that need base64 wrapping).
HANDWRITTEN_OPERATION_IDS = ("download_task_run_log", "download_task_run_artifact")


def register_handwritten(server: FastMCP, client: httpx.AsyncClient) -> None:
    """Register the tools that cannot be generated from the spec.

    ``get_pipeline_run_lineage_url`` has no backing endpoint; the downloads return
    binary content that is base64-encoded so it survives as JSON.
    """

    @server.tool(
        annotations=ToolAnnotations(title="Get Pipeline Run Lineage URL", readOnlyHint=True)
    )
    def get_pipeline_run_lineage_url(pipeline_run_id: str) -> str:
        """Build the URL of a pipeline run's lineage graph in the Orchestra UI."""
        env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
        return f"https://{env}.getorchestra.io/pipeline-runs/{pipeline_run_id}/lineage"

    @server.tool(annotations=ToolAnnotations(title="Download Task Run Log", readOnlyHint=True))
    async def download_task_run_log(
        pipeline_run_id: str, task_run_id: str, filename: str, range_header: str | None = None
    ) -> dict:
        """Download a task run log file, returned base64-encoded."""
        headers = {"Range": range_header} if range_header else None
        response = await client.get(
            f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download",
            params={"filename": filename},
            headers=headers,
        )
        return {
            "filename": filename,
            "content": base64.b64encode(response.content).decode("utf-8"),
            "encoding": "base64",
        }

    @server.tool(annotations=ToolAnnotations(title="Download Task Run Artifact", readOnlyHint=True))
    async def download_task_run_artifact(
        pipeline_run_id: str, task_run_id: str, filename: str
    ) -> dict:
        """Download a task run artifact file, e.g. dbt manifest.json, returned base64-encoded."""
        response = await client.get(
            f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download",
            params={"filename": filename},
        )
        return {
            "filename": filename,
            "content": base64.b64encode(response.content).decode("utf-8"),
            "encoding": "base64",
        }
