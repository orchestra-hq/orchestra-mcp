from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import UUID4, BaseModel, Field


class PipelineRunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class TaskRunStatus(StrEnum):
    CREATED = "CREATED"
    SKIPPED = "SKIPPED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class OperationType(StrEnum):
    AGGREGATION = "AGGREGATION"
    ANALYSIS = "ANALYSIS"
    DEPLOY = "DEPLOY"
    INGESTION = "INGESTION"
    ITERATOR = "ITERATOR"
    MATERIALISATION = "MATERIALISATION"
    OPERATION = "OPERATION"
    QUERY = "QUERY"
    REFRESH = "REFRESH"
    REVERSE_ETL = "REVERSE_ETL"
    SEED = "SEED"
    SNAPSHOT = "SNAPSHOT"
    SOURCE = "SOURCE"
    TEST = "TEST"
    TEST_GROUP = "TEST_GROUP"
    TRIGGER = "TRIGGER"
    UNKNOWN = "UNKNOWN"


class OperationStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"
    WARNING = "WARNING"
    CANCELLED = "CANCELLED"


class AssetType(StrEnum):
    DASHBOARD = "DASHBOARD"
    DASHBOARD_VIEWS = "DASHBOARD_VIEWS"
    DATASET = "DATASET"
    QUERIES = "QUERIES"
    TABLE = "TABLE"
    UNKNOWN = "UNKNOWN"
    VIEW = "VIEW"
    WORKBOOK = "WORKBOOK"


class PaginatedResponse(BaseModel):
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    results: list[dict[str, Any]]


class PipelineRunProgress(BaseModel):
    id: UUID4
    pipeline_id: UUID4 = Field(alias="pipelineId")
    pipeline_name: str = Field(alias="pipelineName")
    run_status: str = Field(alias="runStatus")


class PipelineImportResponse(BaseModel):
    id: UUID4
    name: str
    num_tasks: int = Field(alias="numTasks")
    yaml_path: str = Field(alias="yamlPath")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    paused: bool
    storage_provider: str = Field(alias="storageProvider")
    repository: str
    default_branch: str = Field(alias="defaultBranch")
    alias: str | None = None
    data: dict[str, Any]


class PipelineStartResponse(BaseModel):
    id: UUID4
    pipeline_run_id: UUID4 = Field(alias="pipelineRunId")
    message: str


class ValidatePipelineSchemaResponse(BaseModel):
    message: str
    status: str | None = None


class DeletePipelineResponse(BaseModel):
    is_deleted: bool


class EnvironmentValueType(BaseModel):
    type: Literal["string", "int", "bool", "integration_credential"]
    value: str | bool | int | float


class ProtectedEnvironmentResponse(BaseModel):
    """An Orchestra environment without its variable values."""

    account_id: UUID4 = Field(alias="accountId")
    environment_id: UUID4 = Field(alias="environmentId")
    name: str
    default_env: bool = Field(alias="defaultEnv")


class EnvironmentResponse(BaseModel):
    """An Orchestra environment including its variable values."""

    account_id: UUID4 = Field(alias="accountId")
    environment_id: UUID4 = Field(alias="environmentId")
    name: str
    default_env: bool = Field(alias="defaultEnv")
    values: dict[str, EnvironmentValueType]
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class DeleteEnvironmentResponse(BaseModel):
    is_deleted: bool


class PipelineInputModel(BaseModel):
    type: Literal["string", "number", "boolean", "dict", "list"]
    default: Any | None = None
    optional: bool | None = None


class PipelineResponse(BaseModel):
    id: UUID4
    name: str
    num_tasks: int | None = Field(alias="numTasks", default=None)
    yaml_path: str = Field(alias="yamlPath")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    paused: bool

    # Optional metadata
    trigger_events: str | None = Field(alias="triggerEvents", default=None)
    webhook: str | None = Field(default=None, alias="webhook")
    schedule: str | None = Field(default=None, alias="schedule")
    sensors: str | None = Field(default=None, alias="sensors")
    inputs: dict[str, PipelineInputModel] | None = Field(default=None, alias="inputs")
    product_id: UUID4 | None = Field(alias="productId", default=None)
    product_name: str | None = Field(alias="productName", default=None)
    storage_provider: str | None = Field(alias="storageProvider", default=None)
    repository: str | None = Field(default=None, alias="repository")
    default_branch: str | None = Field(alias="defaultBranch", default=None)
    alias: str | None = Field(default=None)

    # Latest run metadata
    latest_run_id: UUID4 | None = Field(alias="latestRunId", default=None)
    latest_run_status: PipelineRunStatus | None = Field(alias="latestRunStatus", default=None)
    latest_run_message: str | None = Field(alias="latestRunMessage", default=None)
    latest_run_created_at: datetime | None = Field(alias="latestRunCreatedAt", default=None)
    latest_run_completed_at: datetime | None = Field(alias="latestRunCompletedAt", default=None)
    latest_run_started_at: datetime | None = Field(alias="latestRunStartedAt", default=None)

    latest_version_number: int | None = Field(alias="latestVersionNumber", default=None)
    published_version_number: int | None = Field(alias="publishedVersionNumber", default=None)
