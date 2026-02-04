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
async def test_start_pipeline(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "pipeline-id",
        "pipelineRunId": "run-id",
        "message": "Pipeline run created successfully",
    }
    mock_response.raise_for_status = Mock()

    client._client.post = AsyncMock(return_value=mock_response)

    result = await client.start_pipeline(alias="test-pipeline", branch="main")
    assert result.pipeline_run_id == "run-id"
    assert result.message == "Pipeline run created successfully"


@pytest.mark.asyncio
async def test_get_pipeline_run_status(client):
    mock_response = Mock()
    mock_response.json.return_value = {
        "id": "run-id",
        "pipelineId": "pipeline-id",
        "pipelineName": "Test Pipeline",
        "runStatus": "RUNNING",
    }
    mock_response.raise_for_status = Mock()

    client._client.get = AsyncMock(return_value=mock_response)

    result = await client.get_pipeline_run_status("run-id")
    assert result.run_status == "RUNNING"
    assert result.id == "run-id"


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

    result = await client.list_assets(asset_type="TABLE")
    assert result.total == 1
    assert len(result.results) == 1


@pytest.mark.asyncio
async def test_time_range_validation(client):
    with pytest.raises(ValueError, match="Both time_from and time_to must be provided"):
        await client.list_pipeline_runs(time_from=datetime(2025, 1, 1))


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
        await client.start_pipeline(alias="test-pipeline")

    assert exc_info.value.status_code == 400
    assert "Missing required pipeline input: command" in str(exc_info.value)
    assert exc_info.value.message == "Missing required pipeline input: command"
