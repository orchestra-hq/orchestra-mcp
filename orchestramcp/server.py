import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

# Allow running server.py directly (e.g. via fastmcp run); project root must be on path
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastmcp import FastMCP  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from orchestramcp.client import OrchestraClient  # noqa: E402
from orchestramcp.models import (  # noqa: E402
    AssetType,
    OperationStatus,
    OperationType,
    PipelineRunStatus,
    TaskRunStatus,
)


def parse_iso_datetime(dt_str: str) -> datetime:
    dt_str = dt_str.strip()
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)


mcp = FastMCP("Orchestra MCP Server")


@lru_cache
def get_client() -> OrchestraClient:
    api_key = os.getenv("ORCHESTRA_API_KEY")
    if not api_key:
        raise ValueError("ORCHESTRA_API_KEY environment variable is required")
    return OrchestraClient(api_key=api_key)


@mcp.tool(annotations=ToolAnnotations(title="List Pipeline Runs", readOnlyHint=True))
async def list_pipeline_runs(
    time_from: str | None = None,
    time_to: str | None = None,
    status: PipelineRunStatus | None = None,
    pipeline_run_ids: str | None = None,
) -> dict:
    """List pipeline runs with optional filters.

    Args:
        time_from: Start time in ISO 8601 format (e.g., 2025-04-01T00:00:00Z)
        time_to: End time in ISO 8601 format (e.g., 2025-04-05T00:00:00Z)
        status: Comma-separated statuses (CREATED, RUNNING, SUCCEEDED, WARNING, FAILED, CANCELLING, CANCELLED)
        pipeline_run_ids: Comma-separated pipeline run IDs

    Returns:
        Paginated list of pipeline runs

    Reference:
        https://docs.getorchestra.io/api/pipeline-runs/list-pipeline-runs
    """
    async with get_client() as client:
        response = await client.list_pipeline_runs(
            time_from=parse_iso_datetime(time_from) if time_from else None,
            time_to=parse_iso_datetime(time_to) if time_to else None,
            status=status,
            pipeline_run_ids=pipeline_run_ids,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="List Task Runs", readOnlyHint=True))
async def list_task_runs(
    time_from: str | None = None,
    time_to: str | None = None,
    status: TaskRunStatus | None = None,
    pipeline_ids: str | None = None,
    integration: str | None = None,
    task_run_ids: str | None = None,
) -> dict:
    """List task runs with optional filters.

    Args:
        time_from: Start time in ISO 8601 format
        time_to: End time in ISO 8601 format
        status: Comma-separated statuses (CREATED, SKIPPED, QUEUED, RUNNING, SUCCEEDED, WARNING, FAILED, etc.)
        pipeline_ids: Comma-separated pipeline IDs
        integration: Comma-separated integrations (e.g., HTTP, SNOWFLAKE)
        task_run_ids: Comma-separated task run IDs

    Returns:
        Paginated list of task runs

    Reference:
        https://docs.getorchestra.io/api/task-runs/list-task-runs
    """
    async with get_client() as client:
        response = await client.list_task_runs(
            time_from=parse_iso_datetime(time_from) if time_from else None,
            time_to=parse_iso_datetime(time_to) if time_to else None,
            status=status,
            pipeline_ids=pipeline_ids,
            integration=integration,
            task_run_ids=task_run_ids,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="List Operations", readOnlyHint=True))
async def list_operations(
    time_from: str | None = None,
    time_to: str | None = None,
    operation_type: OperationType | None = None,
    integration: str | None = None,
    external_id: str | None = None,
    task_run_id: str | None = None,
    status: OperationStatus | None = None,
) -> dict:
    """List operations with optional filters.

    Args:
        time_from: Start time in ISO 8601 format
        time_to: End time in ISO 8601 format
        operation_type: Comma-separated operation types (AGGREGATION, ANALYSIS, DEPLOY, INGESTION, etc.)
        integration: Integration filter
        external_id: External ID to filter on
        task_run_id: Task run ID to filter on
        status: Operation status (SUCCEEDED, FAILED, SKIPPED, UNKNOWN, WARNING, CANCELLED)

    Returns:
        Paginated list of operations

    Reference:
        https://docs.getorchestra.io/api/operations/list-operations
    """
    async with get_client() as client:
        response = await client.list_operations(
            time_from=parse_iso_datetime(time_from) if time_from else None,
            time_to=parse_iso_datetime(time_to) if time_to else None,
            operation_type=operation_type,
            integration=integration,
            external_id=external_id,
            task_run_id=task_run_id,
            status=status,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="List Assets", readOnlyHint=True))
async def list_assets(
    asset_type: AssetType | None = None,
    integration: str | None = None,
) -> dict:
    """List data assets.

    Args:
        asset_type: Asset type filter (DASHBOARD, DASHBOARD_VIEWS, DATASET, QUERIES, TABLE, VIEW, WORKBOOK, UNKNOWN)
        integration: Integration filter

    Returns:
        Paginated list of assets

    Reference:
        https://docs.getorchestra.io/api/assets/list-assets
    """
    async with get_client() as client:
        response = await client.list_assets(asset_type=asset_type, integration=integration)
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Import Pipeline", destructiveHint=False))
async def import_pipeline(
    storage_provider: str,
    repository: str,
    default_branch: str,
    yaml_path: str,
    alias: str | None = None,
    working_branch: str | None = None,
) -> dict:
    """Import a pipeline from a Git repository.

    Args:
        storage_provider: Storage provider (e.g., GITHUB)
        repository: Repository slug or URL
        default_branch: Default branch name
        yaml_path: Path to pipeline YAML file within repository
        alias: Pipeline alias identifier
        working_branch: Optional working branch to import from

    Returns:
        Pipeline import response with metadata
    """
    async with get_client() as client:
        response = await client.import_pipeline(
            storage_provider=storage_provider,
            repository=repository,
            default_branch=default_branch,
            yaml_path=yaml_path,
            alias=alias,
            working_branch=working_branch,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Start Pipeline", destructiveHint=False))
async def start_pipeline(
    alias_or_pipeline_id: str,
    branch: str | None = None,
    commit: str | None = None,
    environment: str | None = None,
    run_inputs: dict[str, Any] | None = None,
) -> dict:
    """Start a pipeline run.

    Args:
        alias_or_pipeline_id: Pipeline alias or pipeline ID (UUID)
        branch: Optional branch name to run from
        commit: Optional commit SHA to run from
        environment: Optional environment name
        run_inputs: Optional run inputs

    Returns:
        Pipeline start response with pipeline run ID
    """
    async with get_client() as client:
        response = await client.start_pipeline(
            alias_or_pipeline_id=alias_or_pipeline_id,
            branch=branch,
            commit=commit,
            environment=environment,
            run_inputs=run_inputs,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Get Pipeline Run Status", readOnlyHint=True))
async def get_pipeline_run_status(pipeline_run_id: str) -> dict:
    """Get the status of a pipeline run.

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        Pipeline run status information
    """
    async with get_client() as client:
        response = await client.get_pipeline_run_status(pipeline_run_id=pipeline_run_id)
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Cancel Pipeline Run", destructiveHint=True))
async def cancel_pipeline_run(pipeline_run_id: str) -> dict:
    """Cancel a pipeline run.

    Args:
        pipeline_run_id: Pipeline run ID to cancel

    Returns:
        Confirmation message
    """
    async with get_client() as client:
        await client.cancel_pipeline_run(pipeline_run_id=pipeline_run_id)
        return {"message": f"Pipeline run {pipeline_run_id} cancellation requested"}


@mcp.tool(annotations=ToolAnnotations(title="List Task Run Logs", readOnlyHint=True))
async def list_task_run_logs(
    pipeline_run_id: str,
    task_run_id: str,
) -> dict:
    """List available log files for a task run.

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID

    Returns:
        Dictionary with list of log filenames
    """
    async with get_client() as client:
        response = await client.list_task_run_logs(
            pipeline_run_id=pipeline_run_id,
            task_run_id=task_run_id,
        )
        return response


@mcp.tool(annotations=ToolAnnotations(title="Download Task Run Log", readOnlyHint=True))
async def download_task_run_log(
    pipeline_run_id: str,
    task_run_id: str,
    filename: str,
    range_header: str | None = None,
) -> dict:
    """Download a task run log file.

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID
        filename: Log filename to download
        range_header: Optional range header for selectively downloading parts of the file.

    Returns:
        Dictionary with log content (base64 encoded for binary safety)
    """
    import base64

    async with get_client() as client:
        content = await client.download_task_run_log(
            pipeline_run_id=pipeline_run_id,
            task_run_id=task_run_id,
            filename=filename,
            range_header=range_header,
        )
        return {
            "filename": filename,
            "content": base64.b64encode(content).decode("utf-8"),
            "encoding": "base64",
        }


@mcp.tool(annotations=ToolAnnotations(title="List Task Run Artifacts", readOnlyHint=True))
async def list_task_run_artifacts(
    pipeline_run_id: str,
    task_run_id: str,
) -> dict:
    """List available artifact files for a task run.

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID

    Returns:
        Dictionary with list of artifact filenames
    """
    async with get_client() as client:
        response = await client.list_task_run_artifacts(
            pipeline_run_id=pipeline_run_id,
            task_run_id=task_run_id,
        )
        return response


@mcp.tool(annotations=ToolAnnotations(title="Download Task Run Artifact", readOnlyHint=True))
async def download_task_run_artifact(
    pipeline_run_id: str,
    task_run_id: str,
    filename: str,
) -> dict:
    """Download a task run artifact file (e.g., dbt manifest.json).

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID
        filename: Artifact filename to download

    Returns:
        Dictionary with artifact content (base64 encoded for binary safety)
    """
    import base64

    async with get_client() as client:
        content = await client.download_task_run_artifact(
            pipeline_run_id=pipeline_run_id,
            task_run_id=task_run_id,
            filename=filename,
        )
        return {
            "filename": filename,
            "content": base64.b64encode(content).decode("utf-8"),
            "encoding": "base64",
        }


@mcp.tool(annotations=ToolAnnotations(title="Get Pipeline Run Lineage URL", readOnlyHint=True))
def get_pipeline_run_lineage_url(pipeline_run_id: str) -> str:
    """Get the URL of a pipeline run lineage graph."""
    env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
    return f"https://{env}.getorchestra.io/pipeline-runs/{pipeline_run_id}/lineage"


if __name__ == "__main__":
    mcp.run()
