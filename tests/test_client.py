import uuid
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from orchestramcp.client import OrchestraAPIError, OrchestraClient


@pytest.fixture
def mock_httpx_client():
    with patch("orchestramcp.client.httpx.AsyncClient") as mock_client:
        yield mock_client


@pytest.fixture
def client():
    return OrchestraClient(api_key="test-api-key")


@pytest.mark.asyncio
async def test_list_pipeline_runs(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "page": 1,
        "pageSize": 50,
        "total": 1,
        "results": [
            {
                "id": "test-id",
                "pipelineId": "pipeline-id",
                "pipelineName": "Test Pipeline",
                "accountId": "account-id",
                "envId": "env-id",
                "envName": "Production",
                "runStatus": "SUCCEEDED",
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-01T00:00:00Z",
            }
        ],
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.list_pipeline_runs()
    assert result.page == 1
    assert result.total == 1
    assert len(result.results) == 1


@pytest.mark.asyncio
async def test_list_pipeline_runs_with_filters(client):
    time_from = datetime(2025, 1, 1)
    time_to = datetime(2025, 1, 2)

    mock_response = Mock()
    mock_response.json.return_value = {
        "page": 1,
        "pageSize": 50,
        "total": 0,
        "results": [],
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    await client.list_pipeline_runs(time_from=time_from, time_to=time_to, status="SUCCEEDED")

    call_args = client._client.get.call_args
    assert "time_from" in call_args.kwargs["params"]
    assert "time_to" in call_args.kwargs["params"]
    assert call_args.kwargs["params"]["status"] == "SUCCEEDED"


@pytest.mark.asyncio
async def test_list_pipeline_runs_with_pagination(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "page": 2,
        "pageSize": 25,
        "total": 100,
        "results": [],
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    await client.list_pipeline_runs(page=2, page_size=25)

    params = client._client.get.call_args.kwargs["params"]
    assert params["page"] == 2
    assert params["page_size"] == 25


@pytest.mark.asyncio
async def test_list_pipeline_runs_omits_pagination_when_unset(client):
    mock_response = Mock()
    mock_response.json.return_value = {"page": 1, "pageSize": 50, "total": 0, "results": []}
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    await client.list_pipeline_runs()

    params = client._client.get.call_args.kwargs["params"]
    assert "page" not in params
    assert "page_size" not in params


@pytest.mark.asyncio
async def test_list_assets_with_pagination(client):
    mock_response = Mock()
    mock_response.json.return_value = {"page": 3, "pageSize": 10, "total": 100, "results": []}
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    await client.list_assets(asset_type="TABLE", page=3, page_size=10)

    client._client.get.assert_called_once_with(
        "/assets",
        params={"asset_type": "TABLE", "page": 3, "page_size": 10},
    )


@pytest.mark.asyncio
async def test_start_pipeline(client):
    mock_response = Mock()
    mock_pipeline_run_id = uuid.uuid4()
    mock_response.json.return_value = {
        "id": uuid.uuid4(),
        "pipelineRunId": mock_pipeline_run_id,
        "message": "Pipeline run created successfully",
    }
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    result = await client.start_pipeline(alias_or_pipeline_id="test-pipeline", branch="main")
    assert result.pipeline_run_id == mock_pipeline_run_id
    assert result.message == "Pipeline run created successfully"


@pytest.mark.asyncio
async def test_get_pipeline_run_status(client):
    mock_response = Mock()
    mock_pipeline_run_id = uuid.uuid4()
    mock_response.json.return_value = {
        "id": mock_pipeline_run_id,
        "pipelineId": uuid.uuid4(),
        "pipelineName": "Test Pipeline",
        "runStatus": "RUNNING",
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.get_pipeline_run_status(str(mock_pipeline_run_id))
    assert result.run_status == "RUNNING"
    assert result.id == mock_pipeline_run_id


@pytest.mark.asyncio
async def test_cancel_pipeline_run(client):
    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    await client.cancel_pipeline_run("run-id")
    client._client.post.assert_called_once()


@pytest.mark.asyncio
async def test_create_pipeline(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Daily ETL",
        "yamlPath": "pipelines/daily_etl.yaml",
        "createdAt": "2025-03-01T12:00:00Z",
        "updatedAt": "2025-03-20T15:30:00Z",
        "paused": False,
        "alias": "daily_etl",
        "numTasks": 4,
    }
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    pipeline_definition = {"version": "v1", "name": "Daily ETL"}
    await client.create_pipeline(
        pipeline_definition=pipeline_definition,
        alias="daily_etl",
        published=False,
    )

    client._client.post.assert_called_once()
    _, kwargs = client._client.post.call_args
    assert kwargs["json"]["alias"] == "daily_etl"
    assert kwargs["json"]["published"] is False
    assert kwargs["json"]["data"] == pipeline_definition


@pytest.mark.asyncio
async def test_create_pipeline_full_config(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Full Pipeline",
        "yamlPath": "pipelines/full_pipeline.yaml",
        "createdAt": "2025-03-01T12:00:00Z",
        "updatedAt": "2025-03-20T15:30:00Z",
        "paused": False,
        "alias": "full_pipeline",
        "numTasks": 3,
    }
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    pipeline_definition = {
        "version": "v1",
        "name": "Full Pipeline",
        "tasks": {
            "extract": {"type": "python", "command": "python -c 'print(1)'"},
            "transform": {"type": "dbt", "command": "dbt run --select model+transform"},
            "load": {"type": "http", "command": "curl -X POST https://example.com/ingest"},
        },
    }

    await client.create_pipeline(
        pipeline_definition=pipeline_definition,
        alias="full_pipeline",
        published=True,
        storage_provider="AZURE_DEVOPS",
        default_branch="main",
        repository="my-org/my-repo",
        working_branch="feature/pipeline-create",
        yaml_path="pipelines/full_pipeline.yaml",
        message="Initial pipeline import",
        message_is_custom=False,
    )

    _, kwargs = client._client.post.call_args
    body = kwargs["json"]
    assert body["alias"] == "full_pipeline"
    assert body["published"] is True
    assert body["storageProvider"] == "AZURE_DEVOPS"
    assert body["defaultBranch"] == "main"
    assert body["repository"] == "my-org/my-repo"
    assert body["workingBranch"] == "feature/pipeline-create"
    assert body["yamlPath"] == "pipelines/full_pipeline.yaml"
    assert body["message"] == "Initial pipeline import"
    assert body["messageIsCustom"] is False
    assert body["data"] == pipeline_definition


@pytest.mark.asyncio
async def test_update_pipeline_full_config(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Updated Pipeline",
        "yamlPath": "pipelines/updated_pipeline.yaml",
        "createdAt": "2025-03-01T12:00:00Z",
        "updatedAt": "2025-03-20T15:30:00Z",
        "paused": False,
        "alias": "updated_pipeline",
        "numTasks": 3,
    }
    mock_response.raise_for_status = Mock()

    client._client.put = AsyncMock(return_value=mock_response)

    pipeline_definition = {
        "version": "v1",
        "name": "Updated Pipeline",
        "tasks": {
            "extract": {"type": "python", "command": "python -c 'print(1)'"},
            "load": {"type": "http", "command": "curl -X POST https://example.com/ingest"},
        },
    }

    await client.update_pipeline(
        alias="updated_pipeline",
        pipeline_definition=pipeline_definition,
        published=True,
        storage_provider="AZURE_DEVOPS",
        default_branch="main",
        repository="my-org/my-repo",
        working_branch="feature/pipeline-update",
        yaml_path="pipelines/updated_pipeline.yaml",
        message="Update pipeline import",
        message_is_custom=False,
    )

    client._client.put.assert_called_once()
    _, kwargs = client._client.put.call_args
    body = kwargs["json"]
    assert "alias" not in body  # alias is a path parameter only
    assert body["published"] is True
    assert body["storageProvider"] == "AZURE_DEVOPS"
    assert body["defaultBranch"] == "main"
    assert body["repository"] == "my-org/my-repo"
    assert body["workingBranch"] == "feature/pipeline-update"
    assert body["yamlPath"] == "pipelines/updated_pipeline.yaml"
    assert body["message"] == "Update pipeline import"
    assert body["messageIsCustom"] is False
    assert body["data"] == pipeline_definition


@pytest.mark.asyncio
async def test_update_pipeline_parses_json_error(client):
    """When the API returns an error with JSON body, error message is parsed."""
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 422
    mock_response.json.return_value = {
        "detail": "Invalid pipeline definition: missing tasks",
    }
    mock_response.text = ""

    client._client.put = AsyncMock(return_value=mock_response)

    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.update_pipeline(
            alias="bad_pipeline",
            pipeline_definition={"version": "v1", "name": "Bad Pipeline"},
            published=False,
            storage_provider="ORCHESTRA",
        )

    assert exc_info.value.status_code == 422
    assert "Invalid pipeline definition: missing tasks" in str(exc_info.value)
    assert exc_info.value.message == "Invalid pipeline definition: missing tasks"


@pytest.mark.asyncio
async def test_create_pipeline_parses_json_error(client):
    """When the API returns an error with JSON body, error message is parsed."""
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 422
    mock_response.json.return_value = {
        "detail": "Invalid pipeline definition: missing tasks"
    }
    mock_response.text = ""

    client._client.post = AsyncMock(return_value=mock_response)

    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.create_pipeline(
            pipeline_definition={"version": "v1", "name": "Bad Pipeline"},
            alias="bad_pipeline",
            published=False,
            storage_provider="ORCHESTRA",
        )

    assert exc_info.value.status_code == 422
    assert "Invalid pipeline definition: missing tasks" in str(exc_info.value)
    assert exc_info.value.message == "Invalid pipeline definition: missing tasks"


@pytest.mark.asyncio
async def test_delete_pipeline(client):
    mock_response = Mock()
    mock_response.is_success = True
    mock_response.status_code = 204
    mock_response.content = b""

    client._client.delete = AsyncMock(return_value=mock_response)

    result = await client.delete_pipeline(alias="my_pipeline")
    assert result.is_deleted is True
    client._client.delete.assert_called_once_with(
        "/pipelines", params={"alias": "my_pipeline"}
    )


@pytest.mark.asyncio
async def test_delete_pipeline_requires_selector(client):
    with pytest.raises(ValueError, match="pipeline_id, alias, or repository \\+ yaml_path"):
        await client.delete_pipeline()


@pytest.mark.asyncio
async def test_delete_pipeline_requires_repository_and_yaml_path_together(client):
    with pytest.raises(ValueError, match="repository and yaml_path must be provided together"):
        await client.delete_pipeline(repository="owner/repo")


@pytest.mark.asyncio
async def test_list_assets(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "page": 1,
        "pageSize": 50,
        "total": 1,
        "results": [
            {
                "assetId": "asset-id",
                "integration": "SNOWFLAKE",
                "accountId": "account-id",
                "assetName": "test_table",
                "assetType": "TABLE",
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-01T00:00:00Z",
            }
        ],
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.list_assets(asset_type="TABLE")
    assert result.total == 1
    assert len(result.results) == 1


@pytest.mark.asyncio
async def test_list_pipelines(client):
    mock_response = Mock()
    mock_response.json.return_value = [
        {
            "id": str(uuid.uuid4()),
            "name": "Daily ETL",
            "yamlPath": "pipelines/daily_etl.yaml",
            "createdAt": "2025-03-01T12:00:00Z",
            "updatedAt": "2025-03-20T15:30:00Z",
            "paused": False,
            "alias": "daily_etl",
            "numTasks": 4,
            "latestRunId": str(uuid.uuid4()),
            "latestRunStatus": "SUCCEEDED",
        },
        {
            "id": str(uuid.uuid4()),
            "name": "Hourly Data Push",
            "yamlPath": "pipelines/hourly_data_push.yaml",
            "createdAt": "2025-04-01T12:00:00Z",
            "updatedAt": "2025-04-19T15:30:00Z",
            "paused": False,
            "alias": "hourly_data",
            "numTasks": 2,
            "latestRunId": str(uuid.uuid4()),
            "latestRunStatus": "SUCCEEDED",
        },
    ]
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.list_pipelines()
    assert len(result) == 2
    assert result[0].name == "Daily ETL"
    assert result[0].paused is False
    assert result[1].name == "Hourly Data Push"
    assert result[1].paused is False

    client._client.get.assert_called_once_with("/pipelines", params={})


@pytest.mark.asyncio
async def test_get_pipeline_by_alias(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Daily ETL",
        "yamlPath": "pipelines/daily_etl.yaml",
        "createdAt": "2025-03-01T12:00:00Z",
        "updatedAt": "2025-03-20T15:30:00Z",
        "paused": False,
        "alias": "daily_etl",
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.get_pipeline(alias="daily_etl")
    assert result.name == "Daily ETL"
    assert result.paused is False
    client._client.get.assert_called_once_with(
        "/pipeline", params={"alias": "daily_etl"}
    )


@pytest.mark.asyncio
async def test_get_pipeline_passes_optional_selectors(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Daily ETL",
        "yamlPath": "pipelines/daily_etl.yaml",
        "createdAt": "2025-03-01T12:00:00Z",
        "updatedAt": "2025-03-20T15:30:00Z",
        "paused": False,
        "alias": "daily_etl",
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    await client.get_pipeline(
        alias="daily_etl",
        version=2,
        branch="main",
        commit="deadbeef",
    )

    client._client.get.assert_called_once_with(
        "/pipeline",
        params={
            "alias": "daily_etl",
            "version": 2,
            "branch": "main",
            "commit": "deadbeef",
        },
    )


@pytest.mark.asyncio
async def test_get_pipeline_repository_yaml_requires_both(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": str(uuid.uuid4()),
        "name": "Daily ETL",
        "yamlPath": "pipelines/daily_etl.yaml",
        "createdAt": "2025-03-01T12:00:00Z",
        "updatedAt": "2025-03-20T15:30:00Z",
        "paused": False,
        "alias": "daily_etl",
    }
    mock_response.raise_for_status = Mock()
    client._client.get = AsyncMock(return_value=mock_response)

    with pytest.raises(ValueError, match="repository and yaml_path must be provided together"):
        await client.get_pipeline(repository="repo", yaml_path=None)


@pytest.mark.asyncio
async def test_get_pipeline_rejects_multiple_selectors(client):
    with pytest.raises(ValueError, match="Provide exactly one selector"):
        await client.get_pipeline(pipeline_id="pipeline-id", alias="daily_etl")


@pytest.mark.asyncio
async def test_list_operations_with_integration_filter(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "page": 1,
        "pageSize": 50,
        "total": 0,
        "results": [],
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.list_operations(integration="SNOWFLAKE")

    assert result.total == 0
    client._client.get.assert_called_once_with(
        "/operations",
        params={"integration": "SNOWFLAKE"},
    )


@pytest.mark.asyncio
async def test_client_context_manager():
    async with OrchestraClient(api_key="test-key") as client:
        assert client.api_key == "test-key"
    # __aexit__ is a no-op so cached client (e.g. from lru_cache get_client) is not closed
    assert client._client.is_closed is False


@pytest.mark.asyncio
async def test_start_pipeline_parses_json_error(client):
    """When the API returns 400 with JSON body, error message is parsed and raised."""
    mock_response = Mock()
    mock_response.is_success = False
    mock_response.status_code = 400
    mock_response.json.return_value = {"detail": "Missing required pipeline input: command"}
    mock_response.text = ""

    client._client.post = AsyncMock(return_value=mock_response)

    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.start_pipeline(alias_or_pipeline_id="test-pipeline")

    assert exc_info.value.status_code == 400
    assert "Missing required pipeline input: command" in str(exc_info.value)
    assert exc_info.value.message == "Missing required pipeline input: command"


@pytest.mark.asyncio
async def test_validate_pipeline_schema(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "message": "Pipeline schema is valid",
    }
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    result = await client.validate_pipeline_schema({"version": "v1", "name": "x"})
    assert result.message == "Pipeline schema is valid"
    client._client.post.assert_called_once_with(
        "/pipelines/schema", json={"version": "v1", "name": "x"}
    )
