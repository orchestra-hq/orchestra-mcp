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


def test_client_without_api_key_has_no_auth_header():
    client = OrchestraClient()

    assert client.api_key is None
    assert "Authorization" not in client._client.headers


def test_client_with_api_key_sets_auth_header():
    client = OrchestraClient(api_key="test-api-key")

    assert client.api_key == "test-api-key"
    assert client._client.headers["Authorization"] == "Bearer test-api-key"


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

    await client.list_pipeline_runs(
        time_from=time_from,
        time_to=time_to,
        status="SUCCEEDED",
        pipeline_run_ids="run-1,run-2",
    )

    call_args = client._client.get.call_args
    assert "time_from" in call_args.kwargs["params"]
    assert "time_to" in call_args.kwargs["params"]
    assert call_args.kwargs["params"]["status"] == "SUCCEEDED"
    assert call_args.kwargs["params"]["pipeline_run_ids"] == "run-1,run-2"


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

    result = await client.list_assets(asset_type="TABLE", integration="SNOWFLAKE")
    assert result.total == 1
    assert len(result.results) == 1
    client._client.get.assert_called_once_with(
        "/assets",
        params={"asset_type": "TABLE", "integration": "SNOWFLAKE"},
    )


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

    result = await client.list_operations(
        integration="SNOWFLAKE",
        operation_type="QUERY",
        status="SUCCEEDED",
    )

    assert result.total == 0
    client._client.get.assert_called_once_with(
        "/operations",
        params={
            "integration": "SNOWFLAKE",
            "operation_type": "QUERY",
            "status": "SUCCEEDED",
        },
    )


@pytest.mark.asyncio
async def test_client_context_manager():
    async with OrchestraClient(api_key="test-key") as client:
        assert client.api_key == "test-key"
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
    mock_response.json.return_value = {"message": "Pipeline schema is valid"}
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    result = await client.validate_pipeline_schema({"version": "v1", "name": "x"})
    assert result["message"] == "Pipeline schema is valid"
    client._client.post.assert_called_once_with("/pipelines/schema", json={"version": "v1", "name": "x"})


@pytest.mark.asyncio
async def test_list_pipelines(client):
    mock_response = Mock()
    mock_response.json.return_value = [{"alias": "a", "id": str(uuid.uuid4())}]
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.list_pipelines()
    assert len(result) == 1
    assert result[0]["alias"] == "a"


@pytest.mark.asyncio
async def test_create_pipeline(client):
    mock_response = Mock()
    mock_response.json.return_value = {"alias": "my_pipeline", "id": str(uuid.uuid4())}
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    result = await client.create_pipeline("my_pipeline", {"version": "v1", "name": "n"})
    assert result["alias"] == "my_pipeline"
    call = client._client.post.call_args
    assert call[0][0] == "/pipelines"
    assert call[1]["json"]["published"] is False
    assert call[1]["json"]["storage_provider"] == "ORCHESTRA"


@pytest.mark.asyncio
async def test_update_pipeline(client):
    mock_response = Mock()
    mock_response.json.return_value = {"alias": "my_pipeline"}
    mock_response.raise_for_status = Mock()

    client._client.put = AsyncMock(return_value=mock_response)

    await client.update_pipeline("my_pipeline", {"version": "v1", "name": "n"})
    client._client.put.assert_called_once()
    assert client._client.put.call_args[0][0] == "/pipelines/my_pipeline"


@pytest.mark.asyncio
async def test_delete_pipeline(client):
    mock_response = Mock()
    mock_response.raise_for_status = Mock()

    client._client.delete = AsyncMock(return_value=mock_response)

    await client.delete_pipeline("my_pipeline")
    client._client.delete.assert_called_once_with("/pipelines/my_pipeline")
