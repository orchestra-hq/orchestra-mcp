from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import UUID4, BaseModel, Field


class PipelineRunStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class TaskRunStatus(str, Enum):
    CREATED = "CREATED"
    SKIPPED = "SKIPPED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    WARNING = "WARNING"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class OperationType(str, Enum):
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


class OperationStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNKNOWN = "UNKNOWN"
    WARNING = "WARNING"
    CANCELLED = "CANCELLED"


class AssetType(str, Enum):
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
    alias: str
    data: dict[str, Any]


class PipelineStartResponse(BaseModel):
    id: UUID4
    pipeline_run_id: UUID4 = Field(alias="pipelineRunId")
    message: str


class ValidatePipelineSchemaResponse(BaseModel):
    """Response from Orchestra pipeline schema validation.

    The tool is intentionally small: callers generally only need a human-readable message
    and a status indicator.
    """

    message: str
    status: str
