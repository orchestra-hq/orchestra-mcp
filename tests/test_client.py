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
async def test_pagination_collects_all_results_across_two_pages(client):
    """An agent paging by `page` retrieves the complete result set.

    The API holds 2 results with page_size=1, so it takes two requests
    (page 1 and page 2) to collect everything. This mirrors how an agent
    loops: keep requesting the next page until it has `total` results.
    """
    page_one = Mock()
    page_one.json.return_value = {
        "page": 1,
        "pageSize": 1,
        "total": 2,
        "results": [{"id": "run-1"}],
    }
    page_one.raise_for_status = Mock()

    page_two = Mock()
    page_two.json.return_value = {
        "page": 2,
        "pageSize": 1,
        "total": 2,
        "results": [{"id": "run-2"}],
    }
    page_two.raise_for_status = Mock()

    client._client.get = AsyncMock(side_effect=[page_one, page_two])

    # Agent-style loop: fetch pages until collected count reaches total.
    collected: list[dict] = []
    page = 1
    while True:
        response = await client.list_pipeline_runs(page=page, page_size=1)
        collected.extend(response.results)
        if len(collected) >= response.total:
            break
        page += 1

    # Both pages were hit, with the expected page numbers...
    assert client._client.get.call_count == 2
    requested_pages = [call.kwargs["params"]["page"] for call in client._client.get.call_args_list]
    assert requested_pages == [1, 2]

    # ...and the complete result set was assembled from both pages.
    assert [r["id"] for r in collected] == ["run-1", "run-2"]
    assert len(collected) == 2


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
