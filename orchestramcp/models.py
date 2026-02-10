from datetime import datetime
from typing import Any

from pydantic import UUID4, BaseModel, Field


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
