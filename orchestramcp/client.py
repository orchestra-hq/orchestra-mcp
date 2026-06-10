import os
from datetime import datetime
from typing import Any

import httpx

from orchestramcp.errors import OrchestraAPIError, parse_error_response
from orchestramcp.models import (
    AssetType,
    OperationStatus,
    OperationType,
    PaginatedResponse,
    PipelineImportResponse,
    PipelineRunProgress,
    PipelineRunStatus,
    PipelineStartResponse,
    TaskRunStatus,
)


class OrchestraClient:
    @staticmethod
    def _build_base_url() -> str:
        env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
        if env not in ("app", "stage", "dev"):
            raise ValueError(f"Invalid environment: {env}. Must be one of: app, stage, dev")
        return f"https://{env}.getorchestra.io/api/engine/public"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = self._build_base_url()
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def _build_query_params(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if time_from:
            params["time_from"] = time_from.isoformat()
        if time_to:
            params["time_to"] = time_to.isoformat()

        for key, value in kwargs.items():
            if value is not None:
                params[key] = value

        return params

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        raise OrchestraAPIError(response.status_code, parse_error_response(response))

    async def list_pipeline_runs(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        status: PipelineRunStatus | None = None,
        pipeline_run_ids: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PaginatedResponse:
        """List pipeline runs.

        Args:
            time_from: Start time for filtering (ISO 8601)
            time_to: End time for filtering (ISO 8601)
            status: Comma-separated statuses (CREATED, RUNNING, SUCCEEDED, etc.)
            pipeline_run_ids: Comma-separated pipeline run UUIDs
            page: 1-based page number (default 1)
            page_size: Results per page (default 50, max 100)

        Returns:
            Paginated response with pipeline runs
        """
        params = self._build_query_params(
            time_from=time_from,
            time_to=time_to,
            status=status,
            pipeline_run_ids=pipeline_run_ids,
            page=page,
            page_size=page_size,
        )
        response = await self._client.get("/pipeline_runs", params=params)
        self._raise_for_status(response)
        return PaginatedResponse(**response.json())

    async def list_task_runs(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        status: TaskRunStatus | None = None,
        pipeline_ids: str | None = None,
        integration: str | None = None,
        task_run_ids: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PaginatedResponse:
        """List task runs.

        Args:
            time_from: Start time for filtering (ISO 8601)
            time_to: End time for filtering (ISO 8601)
            status: Comma-separated statuses
            pipeline_ids: Comma-separated pipeline UUIDs
            integration: Comma-separated integrations
            task_run_ids: Comma-separated task run UUIDs
            page: 1-based page number (default 1)
            page_size: Results per page (default 50, max 100)

        Returns:
            Paginated response with task runs
        """
        params = self._build_query_params(
            time_from=time_from,
            time_to=time_to,
            status=status,
            pipeline_ids=pipeline_ids,
            integration=integration,
            task_run_ids=task_run_ids,
            page=page,
            page_size=page_size,
        )
        response = await self._client.get("/task_runs", params=params)
        self._raise_for_status(response)
        return PaginatedResponse(**response.json())

    async def list_operations(
        self,
        time_from: datetime | None = None,
        time_to: datetime | None = None,
        operation_type: OperationType | None = None,
        integration: str | None = None,
        external_id: str | None = None,
        task_run_id: str | None = None,
        status: OperationStatus | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PaginatedResponse:
        """List operations.

        Args:
            time_from: Start time for filtering (ISO 8601)
            time_to: End time for filtering (ISO 8601)
            operation_type: Comma-separated operation types
            integration: Integration filter
            external_id: External ID to filter on
            task_run_id: Task run UUID to filter on
            status: Operation status
            page: 1-based page number (default 1)
            page_size: Results per page (default 50, max 100)

        Returns:
            Paginated response with operations
        """
        params = self._build_query_params(
            time_from=time_from,
            time_to=time_to,
            operation_type=operation_type,
            integration=integration,
            external_id=external_id,
            task_run_id=task_run_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        response = await self._client.get("/operations", params=params)
        self._raise_for_status(response)
        return PaginatedResponse(**response.json())

    async def list_assets(
        self,
        asset_type: AssetType | None = None,
        integration: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> PaginatedResponse:
        """List assets.

        Args:
            asset_type: Asset type filter
            integration: Integration filter
            page: 1-based page number (default 1)
            page_size: Results per page (default 50, max 100)

        Returns:
            Paginated response with assets
        """
        params: dict[str, Any] = {}
        if asset_type:
            params["asset_type"] = asset_type
        if integration:
            params["integration"] = integration
        if page is not None:
            params["page"] = page
        if page_size is not None:
            params["page_size"] = page_size

        response = await self._client.get("/assets", params=params)
        self._raise_for_status(response)
        return PaginatedResponse(**response.json())

    async def import_pipeline(
        self,
        storage_provider: str,
        repository: str,
        default_branch: str,
        yaml_path: str,
        alias: str | None = None,
        working_branch: str | None = None,
    ) -> PipelineImportResponse:
        """Import a pipeline from Git.

        Args:
            storage_provider: Storage provider (e.g., GITHUB)
            repository: Repository slug or URL
            default_branch: Default branch name
            yaml_path: Path to pipeline YAML file
            alias: Optional pipeline alias
            working_branch: Optional working branch

        Returns:
            Pipeline import response
        """
        payload: dict[str, Any] = {
            "storage_provider": storage_provider,
            "repository": repository,
            "default_branch": default_branch,
            "yaml_path": yaml_path,
        }
        if alias:
            payload["alias"] = alias
        if working_branch:
            payload["working_branch"] = working_branch

        response = await self._client.post("/pipelines/import", json=payload)
        self._raise_for_status(response)
        return PipelineImportResponse(**response.json())

    async def validate_pipeline_schema(
        self, pipeline_definition: dict[str, Any]
    ) -> dict[str, Any]:
        """Validate a pipeline definition (JSON) against the Orchestra schema (POST /pipelines/schema).

        Does not create or update a pipeline. This endpoint can be called without authentication.
        """
        response = await self._client.post(
            "/pipelines/schema", json=pipeline_definition
        )
        self._raise_for_status(response)
        return response.json()

    async def start_pipeline(
        self,
        alias_or_pipeline_id: str,
        branch: str | None = None,
        commit: str | None = None,
        environment: str | None = None,
        run_inputs: dict[str, Any] | None = None,
    ) -> PipelineStartResponse:
        """Start a pipeline run.

        Args:
            alias_or_pipeline_id: Pipeline alias or pipeline ID (UUID)
            branch: Optional branch name
            commit: Optional commit SHA
            environment: Optional environment name
            run_inputs: Optional run inputs

        Returns:
            Pipeline start response with run ID
        """
        payload: dict[str, Any] = {}
        if branch:
            payload["branch"] = branch
        if commit:
            payload["commit"] = commit
        if environment:
            payload["environment"] = environment
        if run_inputs:
            payload["runInputs"] = run_inputs

        response = await self._client.post(f"/pipelines/{alias_or_pipeline_id}/start", json=payload)
        self._raise_for_status(response)
        return PipelineStartResponse(**response.json())

    async def get_pipeline_run_status(self, pipeline_run_id: str) -> PipelineRunProgress:
        """Get pipeline run status.

        Args:
            pipeline_run_id: Pipeline run UUID

        Returns:
            Pipeline run status
        """
        response = await self._client.get(f"/pipeline_runs/{pipeline_run_id}/status")
        self._raise_for_status(response)
        return PipelineRunProgress(**response.json())

    async def cancel_pipeline_run(self, pipeline_run_id: str) -> None:
        """Cancel a pipeline run.

        Args:
            pipeline_run_id: Pipeline run UUID
        """
        response = await self._client.post(f"/pipeline_runs/{pipeline_run_id}/cancel")
        self._raise_for_status(response)

    async def list_task_run_logs(
        self,
        pipeline_run_id: str,
        task_run_id: str,
    ) -> dict[str, list[str]]:
        """List log filenames for a task run.

        Args:
            pipeline_run_id: Pipeline run ID
            task_run_id: Task run ID

        Returns:
            Dictionary with filenames list
        """
        response = await self._client.get(
            f"/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs"
        )
        self._raise_for_status(response)
        return response.json()

    async def download_task_run_log(
        self,
        pipeline_run_id: str,
        task_run_id: str,
        filename: str,
        range_header: str | None = None,
    ) -> bytes:
        """Download a task run log file.

        Args:
            pipeline_run_id: Pipeline run ID
            task_run_id: Task run ID
            filename: Log filename
            range_header: Optional Range header for selectively downloading parts of the file
                          (e.g., "bytes=-262144" for last 256kB)

        Returns:
            Log file contents as bytes
        """
        headers = {}
        if range_header:
            headers["Range"] = range_header
        response = await self._client.get(
            f"/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download",
            headers=headers,
            params={"filename": filename},
        )
        self._raise_for_status(response)
        return response.content

    async def list_task_run_artifacts(
        self,
        pipeline_run_id: str,
        task_run_id: str,
    ) -> dict[str, list[str]]:
        """List artifact filenames for a task run.

        Args:
            pipeline_run_id: Pipeline run ID
            task_run_id: Task run ID

        Returns:
            Dictionary with filenames list
        """
        response = await self._client.get(
            f"/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts"
        )
        self._raise_for_status(response)
        return response.json()

    async def download_task_run_artifact(
        self,
        pipeline_run_id: str,
        task_run_id: str,
        filename: str,
    ) -> bytes:
        """Download a task run artifact file.

        Args:
            pipeline_run_id: Pipeline run ID
            task_run_id: Task run ID
            filename: Artifact filename

        Returns:
            Artifact file contents as bytes
        """
        response = await self._client.get(
            f"/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download",
            params={"filename": filename},
        )
        self._raise_for_status(response)
        return response.content
