from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import UUID4, BaseModel, ConfigDict, Field


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
    CHART = "CHART"
    DASHBOARD = "DASHBOARD"
    DASHBOARD_VIEWS = "DASHBOARD_VIEWS"
    DATASET = "DATASET"
    QUERIES = "QUERIES"
    TABLE = "TABLE"
    UNKNOWN = "UNKNOWN"
    VIEW = "VIEW"
    WORKBOOK = "WORKBOOK"


class AssetStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"
    WARNING = "WARNING"


class AssetResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    asset_id: UUID4 = Field(alias="assetId")
    integration: str
    account_id: UUID4 = Field(alias="accountId")
    asset_name: str = Field(alias="assetName")
    asset_type: AssetType = Field(alias="assetType")
    integration_account_id: str = Field(alias="integrationAccountId")
    external_id: str = Field(alias="externalId")
    status: AssetStatus
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    # Optional fields (asset can represent table, view, dashboard, etc.)
    database_name: str | None = Field(alias="databaseName", default=None)
    schema_name: str | None = Field(alias="schemaName", default=None)
    workspace_name: str | None = Field(alias="workspaceName", default=None)
    workspace_id: str | None = Field(alias="workspaceId", default=None)
    connection: str | None = Field(alias="connection", default=None)
    connection_integration: str | None = Field(alias="connectionIntegration", default=None)
    last_successful_run: str | None = Field(alias="lastSuccessfulRun", default=None)
    upstream_dependencies: list[str] | None = Field(alias="upstreamDependencies", default=None)
    downstream_dependencies: list[str] | None = Field(alias="downstreamDependencies", default=None)
    integration_asset_type: str | None = Field(alias="integrationAssetType", default=None)
    owner: str | None = Field(alias="owner", default=None)
    owners: list[str] | None = Field(alias="owners", default=None)
    created_in_integration: str | None = Field(alias="createdInIntegration", default=None)
    last_updated_in_integration: str | None = Field(alias="lastUpdatedInIntegration", default=None)
    usage_percentage: float | None = Field(alias="usagePercentage", default=None)
    freshness_config: dict[str, Any] | None = Field(alias="freshnessConfig", default=None)
    table_name: str | None = Field(alias="tableName", default=None)
    row_count: int | None = Field(alias="rowCount", default=None)
    bytes: int | None = Field(alias="bytes", default=None)
    description: str | None = Field(alias="description", default=None)
    url: str | None = Field(alias="url", default=None)
    last_viewed: str | None = Field(alias="lastViewed", default=None)
    unique_viewers: int | None = Field(alias="uniqueViewers", default=None)
    view_count: int | None = Field(alias="viewCount", default=None)
    view_count_from_timestamp: str | None = Field(alias="viewCountFromTimestamp", default=None)


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
