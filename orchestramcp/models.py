from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class PipelineRun(BaseModel):
    id: str
    pipeline_id: str = Field(alias="pipelineId")
    pipeline_name: str = Field(alias="pipelineName")
    account_id: str = Field(alias="accountId")
    env_id: str = Field(alias="envId")
    env_name: str = Field(alias="envName")
    run_status: str = Field(alias="runStatus")
    triggered_by: list[dict[str, Any]] = Field(alias="triggeredBy", default_factory=list)
    child_pipeline_runs: list[dict[str, Any]] = Field(
        alias="childPipelineRuns", default_factory=list
    )
    message: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    completed_at: datetime | None = Field(alias="completedAt", default=None)
    started_at: datetime | None = Field(alias="startedAt", default=None)
    branch: str | None = None
    commit: str | None = None
    pipeline_version_number: int | None = Field(alias="pipelineVersionNumber", default=None)


class TaskRun(BaseModel):
    id: str
    pipeline_run_id: str = Field(alias="pipelineRunId")
    task_name: str = Field(alias="taskName")
    task_id: str = Field(alias="taskId")
    account_id: str = Field(alias="accountId")
    pipeline_id: str = Field(alias="pipelineId")
    integration: str
    integration_job: str = Field(alias="integrationJob")
    status: str
    message: str | None = None
    external_status: str | None = Field(alias="externalStatus", default=None)
    external_message: str | None = Field(alias="externalMessage", default=None)
    platform_link: str | None = Field(alias="platformLink", default=None)
    task_parameters: dict[str, Any] = Field(alias="taskParameters", default_factory=dict)
    run_parameters: dict[str, Any] = Field(alias="runParameters", default_factory=dict)
    connection_id: str | None = Field(alias="connectionId", default=None)
    number_of_attempts: int = Field(alias="numberOfAttempts", default=1)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    completed_at: datetime | None = Field(alias="completedAt", default=None)
    started_at: datetime | None = Field(alias="startedAt", default=None)


class Operation(BaseModel):
    id: str
    account_id: str = Field(alias="accountId")
    pipeline_run_id: str = Field(alias="pipelineRunId")
    task_run_id: str = Field(alias="taskRunId")
    inserted_at: datetime = Field(alias="insertedAt")
    message: str | None = None
    operation_name: str = Field(alias="operationName")
    operation_status: str = Field(alias="operationStatus")
    operation_type: str = Field(alias="operationType")
    external_status: str | None = Field(alias="externalStatus", default=None)
    external_detail: str | None = Field(alias="externalDetail", default=None)
    external_id: str | None = Field(alias="externalId", default=None)
    integration: str | None = None
    integration_job: str | None = Field(alias="integrationJob", default=None)
    started_at: datetime | None = Field(alias="startedAt", default=None)
    completed_at: datetime | None = Field(alias="completedAt", default=None)
    dependencies: list[str] = Field(default_factory=list)
    operation_duration: float | None = Field(alias="operationDuration", default=None)
    rows_affected: int | None = Field(alias="rowsAffected", default=None)


class Asset(BaseModel):
    asset_id: str = Field(alias="assetId")
    integration: str
    account_id: str = Field(alias="accountId")
    asset_name: str = Field(alias="assetName")
    asset_type: str = Field(alias="assetType")
    integration_account_id: str | None = Field(alias="integrationAccountId", default=None)
    external_id: str | None = Field(alias="externalId", default=None)
    connection: str | None = None
    status: str | None = None
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    connection_integration: str | None = Field(alias="connectionIntegration", default=None)
    upstream_dependencies: list[str] = Field(alias="upstreamDependencies", default_factory=list)
    downstream_dependencies: list[str] = Field(alias="downstreamDependencies", default_factory=list)


class PaginatedResponse(BaseModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    results: list[dict[str, Any]]


class PipelineRunStatus(BaseModel):
    id: str
    pipeline_id: str = Field(alias="pipelineId")
    pipeline_name: str = Field(alias="pipelineName")
    run_status: str = Field(alias="runStatus")


class PipelineImportResponse(BaseModel):
    id: str
    name: str
    num_tasks: int = Field(alias="numTasks")
    yaml_path: str = Field(alias="yamlPath")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    paused: bool
    storage_provider: str = Field(alias="storageProvider")
    repository: str
    default_branch: str = Field(alias="defaultBranch")
    alias: str
    data: dict[str, Any]


class PipelineStartResponse(BaseModel):
    id: str
    pipeline_run_id: str = Field(alias="pipelineRunId")
    message: str
