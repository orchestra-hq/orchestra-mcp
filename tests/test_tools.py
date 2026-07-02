import uuid
from unittest.mock import AsyncMock, Mock

import pytest

from orchestramcp import server
from orchestramcp.client import OrchestraAPIError
from orchestramcp.models import AssetType, PipelineRunStatus, TaskRunStatus


class _FakeClient:
    """Stand-in for the HTTP transport: every verb is an ``AsyncMock``."""

    def __init__(self):
        self.get = AsyncMock()
        self.post = AsyncMock()
        self.put = AsyncMock()
        self.patch = AsyncMock()
        self.delete = AsyncMock()


def _response(json=None, status_code=200, content=b""):
    response = Mock()
    response.json.return_value = json
    response.status_code = status_code
    response.content = content
    return response


@pytest.fixture
def http(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(server, "get_client", lambda: fake)
    return fake


def _paginated(results=None, total=0):
    return {"page": 1, "pageSize": 50, "total": total, "results": results or []}


# --- Observability reads ---------------------------------------------------


async def test_list_pipeline_runs_parses_and_omits_unset_params(http):
    http.get.return_value = _response(_paginated(total=1, results=[{"id": "x"}]))

    result = await server.list_pipeline_runs()

    assert result["total"] == 1 and result["page_size"] == 50
    http.get.assert_called_once_with("/pipeline_runs", params={})


async def test_list_pipeline_runs_serializes_filters(http):
    http.get.return_value = _response(_paginated())

    await server.list_pipeline_runs(
        time_from="2025-01-01T00:00:00Z",
        time_to="2025-01-02T00:00:00Z",
        status=PipelineRunStatus.SUCCEEDED,
        page=2,
        page_size=25,
    )

    params = http.get.call_args.kwargs["params"]
    assert params["time_from"] == "2025-01-01T00:00:00+00:00"
    assert params["status"] == "SUCCEEDED"
    assert params["page"] == 2 and params["page_size"] == 25


async def test_list_task_runs_serializes_enum_status(http):
    http.get.return_value = _response(_paginated())

    await server.list_task_runs(status=TaskRunStatus.RUNNING, integration="SNOWFLAKE")

    params = http.get.call_args.kwargs["params"]
    assert params == {"status": "RUNNING", "integration": "SNOWFLAKE"}


async def test_list_operations_integration_filter(http):
    http.get.return_value = _response(_paginated())

    await server.list_operations(integration="SNOWFLAKE")

    http.get.assert_called_once_with("/operations", params={"integration": "SNOWFLAKE"})


async def test_list_assets_builds_params(http):
    http.get.return_value = _response(_paginated())

    await server.list_assets(asset_type=AssetType.TABLE, page=3, page_size=10)

    http.get.assert_called_once_with(
        "/assets", params={"asset_type": "TABLE", "page": 3, "page_size": 10}
    )


async def test_list_pipelines_parses_each_item(http):
    http.get.return_value = _response(
        [
            {
                "id": str(uuid.uuid4()),
                "name": "Daily ETL",
                "yamlPath": "pipelines/daily_etl.yaml",
                "createdAt": "2025-03-01T12:00:00Z",
                "updatedAt": "2025-03-20T15:30:00Z",
                "paused": False,
                "alias": "daily_etl",
            }
        ]
    )

    result = await server.list_pipelines()

    assert result[0]["name"] == "Daily ETL"
    assert result[0]["yaml_path"] == "pipelines/daily_etl.yaml"
    http.get.assert_called_once_with("/pipelines", params={})


# --- Pipeline selectors ----------------------------------------------------


async def test_get_pipeline_by_alias_with_optional_selectors(http):
    http.get.return_value = _response(
        {
            "id": str(uuid.uuid4()),
            "name": "Daily ETL",
            "yamlPath": "pipelines/daily_etl.yaml",
            "createdAt": "2025-03-01T12:00:00Z",
            "updatedAt": "2025-03-20T15:30:00Z",
            "paused": False,
            "alias": "daily_etl",
        }
    )

    await server.get_pipeline(alias="daily_etl", version=2, branch="main", commit="deadbeef")

    http.get.assert_called_once_with(
        "/pipeline",
        params={"alias": "daily_etl", "version": 2, "branch": "main", "commit": "deadbeef"},
    )


async def test_get_pipeline_rejects_multiple_selectors(http):
    with pytest.raises(ValueError, match="Provide exactly one selector"):
        await server.get_pipeline(pipeline_id="id", alias="daily_etl")


async def test_get_pipeline_requires_repository_and_yaml_together(http):
    with pytest.raises(ValueError, match="repository and yaml_path must be provided together"):
        await server.get_pipeline(repository="repo")


# --- Pipeline writes -------------------------------------------------------


async def test_create_pipeline_minimal_body(http):
    http.post.return_value = _response(
        {
            "id": str(uuid.uuid4()),
            "name": "Daily ETL",
            "yamlPath": "pipelines/daily_etl.yaml",
            "createdAt": "2025-03-01T12:00:00Z",
            "updatedAt": "2025-03-20T15:30:00Z",
            "paused": False,
            "alias": "daily_etl",
        }
    )
    definition = {"version": "v1", "name": "Daily ETL"}

    await server.create_pipeline(pipeline_definition=definition, alias="daily_etl", published=False)

    body = http.post.call_args.kwargs["json"]
    assert body == {
        "data": definition,
        "published": False,
        "storageProvider": "ORCHESTRA",
        "alias": "daily_etl",
    }


async def test_create_pipeline_maps_git_fields_to_camel_case(http):
    http.post.return_value = _response(
        {
            "id": str(uuid.uuid4()),
            "name": "Full",
            "yamlPath": "pipelines/full.yaml",
            "createdAt": "2025-03-01T12:00:00Z",
            "updatedAt": "2025-03-20T15:30:00Z",
            "paused": False,
            "alias": "full",
        }
    )

    await server.create_pipeline(
        pipeline_definition={"version": "v1"},
        alias="full",
        published=True,
        storage_provider="GITHUB",
        default_branch="main",
        repository="org/repo",
        working_branch="feature",
        yaml_path="pipelines/full.yaml",
        message="msg",
        message_is_custom=False,
    )

    body = http.post.call_args.kwargs["json"]
    assert body["storageProvider"] == "GITHUB"
    assert body["defaultBranch"] == "main"
    assert body["workingBranch"] == "feature"
    assert body["yamlPath"] == "pipelines/full.yaml"
    assert body["messageIsCustom"] is False


async def test_update_pipeline_sends_only_data_and_published(http):
    http.put.return_value = _response(
        {
            "id": str(uuid.uuid4()),
            "name": "Updated",
            "yamlPath": "pipelines/updated.yaml",
            "createdAt": "2025-03-01T12:00:00Z",
            "updatedAt": "2025-03-20T15:30:00Z",
            "paused": False,
            "alias": "updated",
        }
    )
    definition = {"version": "v1", "name": "Updated"}

    await server.update_pipeline(alias="updated", pipeline_definition=definition, published=True)

    args, kwargs = http.put.call_args
    assert args[0] == "/pipelines/updated"
    assert kwargs["json"] == {"data": definition, "published": True}


async def test_delete_pipeline_reports_deleted_on_204(http):
    http.delete.return_value = _response(status_code=204)

    result = await server.delete_pipeline(alias="my_pipeline")

    assert result == {"is_deleted": True}
    http.delete.assert_called_once_with("/pipelines", params={"alias": "my_pipeline"})


async def test_delete_pipeline_requires_selector(http):
    with pytest.raises(ValueError, match="pipeline_id, alias, or repository"):
        await server.delete_pipeline()


# --- Integrations & environments -------------------------------------------


async def test_list_integration_connections_maps_auth_status(http):
    http.get.return_value = _response([{"integration": "SNOWFLAKE"}])

    result = await server.list_integration_connections(
        integration="SNOWFLAKE", auth_status="AUTHENTICATED"
    )

    assert result == [{"integration": "SNOWFLAKE"}]
    http.get.assert_called_once_with(
        "/integrations/connections",
        params={"integration": "SNOWFLAKE", "authStatus": "AUTHENTICATED"},
    )


def _environment(name="Production", default_env=True):
    return {
        "accountId": str(uuid.uuid4()),
        "environmentId": str(uuid.uuid4()),
        "name": name,
        "defaultEnv": default_env,
        "values": {"WAREHOUSE": {"type": "string", "value": "COMPUTE_WH"}},
        "createdAt": "2025-01-01T00:00:00Z",
        "updatedAt": "2025-01-02T00:00:00Z",
    }


async def test_list_environments_strips_values(http):
    http.get.return_value = _response(
        [
            {
                "accountId": str(uuid.uuid4()),
                "environmentId": str(uuid.uuid4()),
                "name": "Production",
                "defaultEnv": True,
            }
        ]
    )

    result = await server.list_environments()

    assert result[0]["name"] == "Production" and result[0]["default_env"] is True
    assert "values" not in result[0]
    http.get.assert_called_once_with("/environments", params={})


async def test_get_environment_includes_values(http):
    payload = _environment()
    http.get.return_value = _response(payload)

    result = await server.get_environment(payload["environmentId"])

    assert result["values"]["WAREHOUSE"]["value"] == "COMPUTE_WH"
    http.get.assert_called_once_with(f"/environments/{payload['environmentId']}")


async def test_create_environment_sends_name_and_values(http):
    http.post.return_value = _response(_environment(name="Dev", default_env=False))
    values = {"WAREHOUSE": {"type": "string", "value": "COMPUTE_WH"}}

    await server.create_environment(name="Dev", values=values)

    http.post.assert_called_once_with("/environments", json={"name": "Dev", "values": values})


async def test_update_environment_maps_default_env(http):
    payload = _environment()
    http.patch.return_value = _response(payload)
    values = {"RETRIES": {"type": "int", "value": 5}}

    await server.update_environment(
        environment_id=payload["environmentId"], name="Production", values=values, default_env=True
    )

    http.patch.assert_called_once_with(
        f"/environments/{payload['environmentId']}",
        json={"name": "Production", "values": values, "defaultEnv": True},
    )


async def test_delete_environment_reports_deleted_on_204(http):
    environment_id = str(uuid.uuid4())
    http.delete.return_value = _response(status_code=204)

    result = await server.delete_environment(environment_id)

    assert result == {"is_deleted": True}
    http.delete.assert_called_once_with(f"/environments/{environment_id}")


# --- Import / migrate / validate / run -------------------------------------


async def test_import_pipeline_without_alias(http):
    http.post.return_value = _response(
        {
            "id": str(uuid.uuid4()),
            "name": "Imported",
            "numTasks": 1,
            "yamlPath": "orchestra/claude_dbt.yml",
            "createdAt": "2026-06-12T11:30:08Z",
            "updatedAt": "2026-06-12T11:30:08Z",
            "paused": False,
            "storageProvider": "GITHUB",
            "repository": "org/repo",
            "defaultBranch": "main",
            "data": {"version": "v1"},
        }
    )

    result = await server.import_pipeline(
        storage_provider="GITHUB",
        repository="org/repo",
        default_branch="main",
        yaml_path="orchestra/claude_dbt.yml",
    )

    assert result["alias"] is None and result["num_tasks"] == 1
    assert "alias" not in http.post.call_args.kwargs["json"]


async def test_migrate_pipeline_omits_working_branch_when_default(http):
    http.patch.return_value = _response(content=b"")

    result = await server.migrate_pipeline(
        path="pipelines/my.yaml",
        repository="org/repo",
        storage_provider="GITHUB",
        default_branch="main",
        working_branch="main",
        pipeline_id="abc",
    )

    assert result == {}
    body = http.patch.call_args.kwargs["json"]
    assert "working_branch" not in body
    assert http.patch.call_args.kwargs["params"] == {"pipeline_id": "abc"}


async def test_migrate_pipeline_requires_selector(http):
    with pytest.raises(ValueError, match="pipeline_id or alias"):
        await server.migrate_pipeline(
            path="p.yaml", repository="org/repo", storage_provider="GITHUB", default_branch="main"
        )


async def test_validate_pipeline_posts_definition(http):
    http.post.return_value = _response({"message": "Pipeline schema is valid"})

    result = await server.validate_pipeline({"version": "v1", "name": "x"})

    assert result["message"] == "Pipeline schema is valid"
    http.post.assert_called_once_with("/pipelines/schema", json={"version": "v1", "name": "x"})


async def test_start_pipeline_parses_run_id(http):
    run_id = uuid.uuid4()
    http.post.return_value = _response(
        {"id": str(uuid.uuid4()), "pipelineRunId": str(run_id), "message": "created"}
    )

    result = await server.start_pipeline(alias_or_pipeline_id="p", branch="main")

    assert result["pipeline_run_id"] == run_id
    http.post.assert_called_once_with("/pipelines/p/start", json={"branch": "main"})


async def test_get_pipeline_run_status(http):
    run_id = uuid.uuid4()
    http.get.return_value = _response(
        {
            "id": str(run_id),
            "pipelineId": str(uuid.uuid4()),
            "pipelineName": "Test",
            "runStatus": "RUNNING",
        }
    )

    result = await server.get_pipeline_run_status(str(run_id))

    assert result["run_status"] == "RUNNING"
    http.get.assert_called_once_with(f"/pipeline_runs/{run_id}/status")


async def test_cancel_pipeline_run_returns_message(http):
    http.post.return_value = _response()

    result = await server.cancel_pipeline_run("run-id")

    assert "run-id" in result["message"]
    http.post.assert_called_once_with("/pipeline_runs/run-id/cancel")


# --- Logs & artifacts (binary) ---------------------------------------------


async def test_download_task_run_log_base64_encodes_with_range(http):
    http.get.return_value = _response(content=b"hello logs")

    result = await server.download_task_run_log(
        pipeline_run_id="pr", task_run_id="tr", filename="run.log", range_header="bytes=-10"
    )

    assert result == {"filename": "run.log", "content": "aGVsbG8gbG9ncw==", "encoding": "base64"}
    http.get.assert_called_once_with(
        "/pipeline_runs/pr/task_runs/tr/logs/download",
        params={"filename": "run.log"},
        headers={"Range": "bytes=-10"},
    )


async def test_download_task_run_artifact_omits_range_header(http):
    http.get.return_value = _response(content=b"data")

    await server.download_task_run_artifact(
        pipeline_run_id="pr", task_run_id="tr", filename="manifest.json"
    )

    http.get.assert_called_once_with(
        "/pipeline_runs/pr/task_runs/tr/artifacts/download", params={"filename": "manifest.json"}
    )


async def test_list_task_run_logs_returns_raw_json(http):
    http.get.return_value = _response({"filenames": ["a.log"]})

    result = await server.list_task_run_logs(pipeline_run_id="pr", task_run_id="tr")

    assert result == {"filenames": ["a.log"]}
    http.get.assert_called_once_with("/pipeline_runs/pr/task_runs/tr/logs")


# --- Error propagation & pure helpers --------------------------------------


async def test_transport_error_propagates_through_tool(http):
    http.post.side_effect = OrchestraAPIError(400, "Missing required input: command")

    with pytest.raises(OrchestraAPIError, match="Missing required input"):
        await server.start_pipeline(alias_or_pipeline_id="p")


def test_lineage_url_uses_orchestra_env(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_ENV", "stage")
    url = server.get_pipeline_run_lineage_url("run-123")
    assert url == "https://stage.getorchestra.io/pipeline-runs/run-123/lineage"
