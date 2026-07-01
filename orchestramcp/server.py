import os
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

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
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        raise ValueError(
            f"Invalid datetime '{dt_str}'. Expected ISO 8601 format, e.g. 2025-04-01T00:00:00Z"
        )


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
    page: int | None = None,
    page_size: int | None = None,
) -> dict:
    """List pipeline runs with optional filters (GET /pipeline_runs).

    Args:
        time_from: Start time in ISO 8601 format (e.g., 2025-04-01T00:00:00Z)
        time_to: End time in ISO 8601 format (e.g., 2025-04-05T00:00:00Z)
        status: Comma-separated statuses (CREATED, RUNNING, SUCCEEDED, WARNING, FAILED, SKIPPED, CANCELLING, CANCELLED)
        pipeline_run_ids: Comma-separated pipeline run IDs
        page: 1-based page number to retrieve (default 1)
        page_size: Number of results per page (default 50, max 100)

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
            page=page,
            page_size=page_size,
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
    page: int | None = None,
    page_size: int | None = None,
) -> dict:
    """List task runs with optional filters (GET /task_runs).

    Args:
        time_from: Start time in ISO 8601 format
        time_to: End time in ISO 8601 format
        status: Comma-separated statuses (CREATED, SKIPPED, QUEUED, RUNNING, SUCCEEDED, WARNING, FAILED, etc.)
        pipeline_ids: Comma-separated pipeline IDs
        integration: Comma-separated integrations (e.g., HTTP, SNOWFLAKE)
        task_run_ids: Comma-separated task run IDs
        page: 1-based page number to retrieve (default 1)
        page_size: Number of results per page (default 50, max 100)

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
            page=page,
            page_size=page_size,
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
    page: int | None = None,
    page_size: int | None = None,
) -> dict:
    """List operations with optional filters (GET /operations).

    Args:
        time_from: Start time in ISO 8601 format
        time_to: End time in ISO 8601 format
        operation_type: Comma-separated operation types (AGGREGATION, ANALYSIS, DEPLOY, INGESTION, etc.)
        integration: Integration filter
        external_id: External ID to filter on
        task_run_id: Task run ID to filter on
        status: Operation status (SUCCEEDED, FAILED, REUSED, SKIPPED, UNKNOWN, WARNING, CANCELLED)
        page: 1-based page number to retrieve (default 1)
        page_size: Number of results per page (default 50, max 100)

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
            page=page,
            page_size=page_size,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="List Assets", readOnlyHint=True))
async def list_assets(
    asset_type: AssetType | None = None,
    integration: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> dict:
    """List data assets (GET /assets).

    Args:
        asset_type: Asset type filter (CHART, DASHBOARD, DASHBOARD_VIEWS, DATASET, QUERIES, TABLE, VIEW, WORKBOOK, UNKNOWN)
        integration: Integration filter
        page: 1-based page number to retrieve (default 1)
        page_size: Number of results per page (default 50, max 100)

    Returns:
        Paginated list of assets

    Reference:
        https://docs.getorchestra.io/api/assets/list-assets
    """
    async with get_client() as client:
        response = await client.list_assets(
            asset_type=asset_type,
            integration=integration,
            page=page,
            page_size=page_size,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="List Pipelines", readOnlyHint=True))
async def list_pipelines() -> list[dict[str, Any]]:
    """List pipelines available to the current workspace API key (GET /pipelines).

    Returns:
        List of pipelines available to the workspace

    Reference:
        https://docs.getorchestra.io/api/pipelines/list-pipelines
    """

    async with get_client() as client:
        response = await client.list_pipelines()
        return [pipeline.model_dump() for pipeline in response]


@mcp.tool(annotations=ToolAnnotations(title="Get Pipeline", readOnlyHint=True))
async def get_pipeline(
    pipeline_id: str | None = None,
    alias: str | None = None,
    repository: str | None = None,
    yaml_path: str | None = None,
    version: int | None = None,
    branch: str | None = None,
    commit: str | None = None,
) -> dict:
    """Fetch a single pipeline by selector (GET /pipeline).

    Provide exactly one selector: pipeline_id, alias, or repository + yaml_path.

    Args:
        pipeline_id: Pipeline ID selector (UUID)
        alias: Pipeline alias selector
        repository: Repository slug or URL selector (used with yaml_path)
        yaml_path: Path to pipeline YAML file within repository (used with repository)
        version: Optional pipeline version number
        branch: Optional branch name
        commit: Optional commit SHA

    Returns:
        The matching pipeline with metadata

    Reference:
        https://docs.getorchestra.io/api/pipelines/get-a-pipeline-by-selector
    """
    async with get_client() as client:
        response = await client.get_pipeline(
            pipeline_id=pipeline_id,
            alias=alias,
            repository=repository,
            yaml_path=yaml_path,
            version=version,
            branch=branch,
            commit=commit,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Create Pipeline", destructiveHint=False))
async def create_pipeline(
    pipeline_definition: dict[str, Any],
    alias: str,
    published: bool,
    storage_provider: Literal[
        "ORCHESTRA", "AZURE_DEVOPS", "GITHUB", "GITLAB", "BITBUCKET"
    ] = "ORCHESTRA",
    default_branch: str | None = None,
    repository: str | None = None,
    working_branch: str | None = None,
    yaml_path: str | None = None,
    message: str | None = None,
    message_is_custom: bool | None = None,
) -> dict:
    """Create a new pipeline (POST /pipelines).

    Args:
        pipeline_definition: Pipeline definition object (e.g. from YAML converted to JSON)
        alias: Pipeline alias identifier
        published: Whether to publish the pipeline on creation
        storage_provider: Where the pipeline definition is stored (default ORCHESTRA)
        default_branch: Default branch name (Git-backed pipelines)
        repository: Repository slug or URL (Git-backed pipelines)
        working_branch: Working branch to commit to (Git-backed pipelines)
        yaml_path: Path to pipeline YAML file within repository (Git-backed pipelines)
        message: Commit message (Git-backed pipelines)
        message_is_custom: Whether the commit message is custom (Git-backed pipelines)

    Returns:
        Created pipeline with metadata

    Reference:
        https://docs.getorchestra.io/api/pipelines/create-a-pipeline
    """
    async with get_client() as client:
        response = await client.create_pipeline(
            pipeline_definition=pipeline_definition,
            alias=alias,
            published=published,
            storage_provider=storage_provider,
            default_branch=default_branch,
            repository=repository,
            working_branch=working_branch,
            yaml_path=yaml_path,
            message=message,
            message_is_custom=message_is_custom,
        )
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Update Pipeline", destructiveHint=False))
async def update_pipeline(
    alias: str,
    pipeline_definition: dict[str, Any],
    published: bool,
) -> dict:
    """Update an existing Orchestra-backed pipeline by alias (PUT /pipelines/{alias}).
    To move an Orchestra-backed pipeline to git-backed storage, use ``migrate_pipeline``.

    Args:
        alias: Pipeline alias identifier (must be an Orchestra-backed pipeline)
        pipeline_definition: Pipeline definition object (e.g. from YAML converted to JSON)
        published: Whether to publish the pipeline on update

    Returns:
        Updated pipeline with metadata

    Reference:
        https://docs.getorchestra.io/api/pipelines/update-a-pipeline
    """
    async with get_client() as client:
        response = await client.update_pipeline(
            alias=alias,
            pipeline_definition=pipeline_definition,
            published=published,
        )
        return response.model_dump()


def _delete_enabled() -> bool:
    """Whether the destructive delete_pipeline tool should be registered.

    Disabled by default; set ORCHESTRA_ENABLE_DELETE to "TRUE", "true" or "1" to expose it.
    """

    return os.getenv("ORCHESTRA_ENABLE_DELETE", "").strip().lower() in ("1", "true")


async def delete_pipeline(
    pipeline_id: str | None = None,
    alias: str | None = None,
    repository: str | None = None,
    yaml_path: str | None = None,
) -> dict:
    """Delete a pipeline by selector (DELETE /pipelines).

    Disabled by default; set the `ORCHESTRA_ENABLE_DELETE` environment variable to
    either `1` or `true` to expose this tool.

    Args:
        pipeline_id: Pipeline ID selector (UUID)
        alias: Pipeline alias selector
        repository: Repository slug or URL selector (used with `yaml_path`)
        yaml_path: Path to the pipeline YAML file within the repository (used with `repository`)

    Returns:
        Confirmation message indicating the selected pipeline that was deleted

    Reference:
        https://docs.getorchestra.io/api/pipelines/delete-a-pipeline
    """

    async with get_client() as client:
        response = await client.delete_pipeline(
            pipeline_id=pipeline_id,
            alias=alias,
            repository=repository,
            yaml_path=yaml_path,
        )

    return response.model_dump()


if _delete_enabled():
    delete_pipeline = mcp.tool(
        annotations=ToolAnnotations(title="Delete Pipeline", destructiveHint=True)
    )(delete_pipeline)


@mcp.tool()
async def list_integration_connections(
    integration: str | None = None,
    auth_status: str | None = None,
) -> list[dict[str, Any]]:
    """List integration connections for the workspace linked to the API key."""
    async with get_client() as client:
        return await client.list_integration_connections(
            integration=integration,
            auth_status=auth_status,
        )


@mcp.tool(annotations=ToolAnnotations(title="List Environments", readOnlyHint=True))
async def list_environments() -> list[dict[str, Any]]:
    """List environments for the workspace linked to the API key (GET /environments).

    Returns environment metadata only (id, name, default flag). Use `get_environment`
    to retrieve a single environment's variable values.

    Returns:
        List of environments without their variable values

    Reference:
        https://docs.getorchestra.io/api/environments/list-environments
    """
    async with get_client() as client:
        response = await client.list_environments()
        return [environment.model_dump() for environment in response]


@mcp.tool(annotations=ToolAnnotations(title="Get Environment", readOnlyHint=True))
async def get_environment(environment_id: str) -> dict:
    """Fetch a single environment by its ID, including its variable values (GET /environments/{environment_id}).

    Args:
        environment_id: Environment ID (UUID)

    Returns:
        The environment with its variable values

    Reference:
        https://docs.getorchestra.io/api/environments/get-an-environment
    """
    async with get_client() as client:
        response = await client.get_environment(environment_id=environment_id)
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Create Environment", destructiveHint=False))
async def create_environment(
    name: str,
    values: dict[str, dict[str, Any]],
) -> dict:
    """Create a new environment with an initial set of variable values (POST /environments).

    The first environment created for a workspace is automatically marked as the default.

    Args:
        name: Environment name
        values: Mapping of variable name to a typed value object of the form
            `{"type": <"string"|"int"|"bool"|"integration_credential">, "value": <value>}`.
            For example: `{"WAREHOUSE": {"type": "string", "value": "COMPUTE_WH"},
            "RETRIES": {"type": "int", "value": 3}}`

    Returns:
        The created environment with its variable values

    Reference:
        https://docs.getorchestra.io/api/environments/create-an-environment
    """
    async with get_client() as client:
        response = await client.create_environment(name=name, values=values)
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Update Environment", destructiveHint=False))
async def update_environment(
    environment_id: str,
    name: str,
    values: dict[str, dict[str, Any]],
    default_env: bool,
) -> dict:
    """Update an environment's name, default flag, and variable values (PATCH /environments/{environment_id}).

    The supplied `values` replace the existing values in full — they are not merged, so
    fetch the environment first with `get_environment` if you only mean to change some of
    them. Marking an environment as the default automatically unsets the previous default.

    Args:
        environment_id: Environment ID (UUID)
        name: Environment name
        values: Mapping of variable name to a typed value object of the form
            `{"type": <"string"|"int"|"bool"|"integration_credential">, "value": <value>}`.
            Replaces the existing values in full.
        default_env: Whether this environment should be the workspace default

    Returns:
        The updated environment with its variable values

    Reference:
        https://docs.getorchestra.io/api/environments/update-an-environment
    """
    async with get_client() as client:
        response = await client.update_environment(
            environment_id=environment_id,
            name=name,
            values=values,
            default_env=default_env,
        )
        return response.model_dump()


async def delete_environment(environment_id: str) -> dict:
    """Delete an environment entirely (DELETE /environments/{environment_id}).

    Disabled by default; set the `ORCHESTRA_ENABLE_DELETE` environment variable to
    either `1` or `true` to expose this tool. The default environment cannot be deleted
    while other environments still exist.

    Args:
        environment_id: Environment ID (UUID)

    Returns:
        Deletion result, e.g. `{"is_deleted": true}`

    Reference:
        https://docs.getorchestra.io/api/environments/delete-an-environment
    """
    async with get_client() as client:
        response = await client.delete_environment(environment_id=environment_id)
        return response.model_dump()


if _delete_enabled():
    delete_environment = mcp.tool(
        annotations=ToolAnnotations(title="Delete Environment", destructiveHint=True)
    )(delete_environment)


@mcp.tool()
async def import_pipeline(
    storage_provider: str,
    repository: str,
    default_branch: str,
    yaml_path: str,
    alias: str | None = None,
    working_branch: str | None = None,
) -> dict:
    """Import a pipeline from a Git repository (POST /pipelines/import).

    Args:
        storage_provider: Storage provider (e.g., GITHUB)
        repository: Repository slug or URL
        default_branch: Default branch name
        yaml_path: Path to pipeline YAML file within repository
        alias: Pipeline alias identifier
        working_branch: Optional working branch to import from

    Returns:
        Pipeline import response with metadata

    Reference:
        https://docs.getorchestra.io/api/pipelines/import-a-pipeline
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


@mcp.tool(annotations=ToolAnnotations(title="Migrate Pipeline", destructiveHint=False))
async def migrate_pipeline(
    path: str,
    repository: str,
    storage_provider: str,
    default_branch: str,
    working_branch: str | None = None,
    alias: str | None = None,
    pipeline_id: str | None = None,
) -> dict:
    """Migrate an Orchestra-backed pipeline to git-backed storage (PATCH /pipelines/storage-settings).

    Identify the pipeline with `alias` or `pipeline_id`. The pipeline YAML must already
    exist in the target Git repository at `path`. This tool only repoints Orchestra at
    the Git-backed definition; it does not commit or push files.

    Args:
        path: Path to the pipeline YAML within the repository
        repository: Repository slug (e.g. owner/repo)
        storage_provider: Git storage provider (e.g. GITHUB, GITLAB, BITBUCKET)
        default_branch: Default branch to store in Orchestra
        working_branch: Optional working branch (omitted when equal to default_branch)
        alias: Pipeline alias selector
        pipeline_id: Pipeline ID selector

    Returns:
        The API response payload

    Reference:
        https://docs.getorchestra.io/api/pipelines/update-pipeline-storage-settings
    """
    async with get_client() as client:
        return await client.migrate_pipeline_storage(
            path=path,
            repository=repository,
            storage_provider=storage_provider,
            default_branch=default_branch,
            working_branch=working_branch,
            alias=alias,
            pipeline_id=pipeline_id,
        )


@mcp.tool(annotations=ToolAnnotations(title="Validate Pipeline", readOnlyHint=True))
async def validate_pipeline(pipeline_definition: dict[str, Any]) -> dict:
    """Validate a pipeline definition against the Orchestra schema without persisting it (POST /pipelines/schema).

    Supply the same structure as the pipeline YAML (version, name, tasks, etc.) as parsed JSON.

    Args:
        pipeline_definition: Pipeline definition object (e.g. from YAML converted to JSON)

    Returns:
        Validation result payload; API errors are surfaced as tool errors

    Reference:
        https://docs.getorchestra.io/api/pipelines/validate-pipeline-schema
    """
    async with get_client() as client:
        response = await client.validate_pipeline_schema(pipeline_definition=pipeline_definition)
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Start Pipeline", destructiveHint=False))
async def start_pipeline(
    alias_or_pipeline_id: str,
    branch: str | None = None,
    commit: str | None = None,
    environment: str | None = None,
    run_inputs: dict[str, Any] | None = None,
) -> dict:
    """Start a pipeline run (POST /pipelines/{alias_or_pipeline_id}/start).

    Args:
        alias_or_pipeline_id: Pipeline alias or pipeline ID (UUID)
        branch: Optional branch name to run from
        commit: Optional commit SHA to run from
        environment: Optional environment name
        run_inputs: Optional run inputs

    Returns:
        Pipeline start response with pipeline run ID

    Reference:
        https://docs.getorchestra.io/api/pipelines/start-a-pipeline-run
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
    """Get the status of a pipeline run (GET /pipeline_runs/{pipeline_run_id}/status).

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        Pipeline run status information

    Reference:
        https://docs.getorchestra.io/api/pipeline-runs/get-pipeline-run-status
    """
    async with get_client() as client:
        response = await client.get_pipeline_run_status(pipeline_run_id=pipeline_run_id)
        return response.model_dump()


@mcp.tool(annotations=ToolAnnotations(title="Cancel Pipeline Run", destructiveHint=True))
async def cancel_pipeline_run(pipeline_run_id: str) -> dict:
    """Cancel a pipeline run (POST /pipeline_runs/{pipeline_run_id}/cancel).

    Args:
        pipeline_run_id: Pipeline run ID to cancel

    Returns:
        Confirmation message

    Reference:
        https://docs.getorchestra.io/api/pipeline-runs/cancel-a-pipeline-run
    """
    async with get_client() as client:
        await client.cancel_pipeline_run(pipeline_run_id=pipeline_run_id)
        return {"message": f"Pipeline run {pipeline_run_id} cancellation requested"}


@mcp.tool(annotations=ToolAnnotations(title="List Task Run Logs", readOnlyHint=True))
async def list_task_run_logs(
    pipeline_run_id: str,
    task_run_id: str,
) -> dict:
    """List available log files for a task run (GET /pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs).

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID

    Returns:
        Dictionary with list of log filenames

    Reference:
        https://docs.getorchestra.io/api/logs/list-task-run-logs
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
    """Download a task run log file (GET /pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download).

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID
        filename: Log filename to download
        range_header: Optional range header for selectively downloading parts of the file.

    Returns:
        Dictionary with log content (base64 encoded for binary safety)

    Reference:
        https://docs.getorchestra.io/api/logs/download-a-task-run-log
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
    """List available artifact files for a task run (GET /pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts).

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID

    Returns:
        Dictionary with list of artifact filenames

    Reference:
        https://docs.getorchestra.io/api/artifacts/list-task-run-artifacts
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
    """Download a task run artifact file, e.g. dbt manifest.json (GET /pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download).

    Args:
        pipeline_run_id: Pipeline run ID
        task_run_id: Task run ID
        filename: Artifact filename to download

    Returns:
        Dictionary with artifact content (base64 encoded for binary safety)

    Reference:
        https://docs.getorchestra.io/api/artifacts/download-a-task-run-artifact
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
    """Build the URL of a pipeline run's lineage graph in the Orchestra UI.

    Args:
        pipeline_run_id: Pipeline run ID

    Returns:
        URL of the pipeline run lineage graph in the Orchestra UI
    """
    env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
    return f"https://{env}.getorchestra.io/pipeline-runs/{pipeline_run_id}/lineage"


if __name__ == "__main__":
    mcp.run()
