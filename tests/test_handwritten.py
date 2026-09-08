import base64
import json
import os
import re
from datetime import datetime, timedelta

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from orchestramcp.client import build_http_client
from orchestramcp.handwritten import (
    LOG_TAIL_BYTES,
    MAX_ARTIFACT_NAMES,
    MAX_DOWNLOAD_BYTES,
    MAX_FAILED_TASKS_PER_RUN,
    MAX_SIBLING_TASK_RUNS,
    MAX_WINDOW_HOURS,
    RUN_TASK_RUNS_PAGE_SIZE,
    _duration_seconds,
    register_handwritten,
)


def _server(handler=None, ui_base_url="https://stage.getorchestra.io"):
    handler = handler or (lambda request: httpx.Response(200, content=b""))
    client = httpx.AsyncClient(
        base_url="https://example.com/api/engine", transport=httpx.MockTransport(handler)
    )
    server = FastMCP("test")
    register_handwritten(server, client, ui_base_url)
    return server


def _download_result(result) -> dict:
    return json.loads(result.content[0].text)


async def test_lineage_url_uses_ui_base():
    async with Client(_server(ui_base_url="https://stage.getorchestra.io")) as client:
        result = await client.call_tool("get_pipeline_run_lineage_url", {"pipeline_run_id": "r1"})
    assert result.data == "https://stage.getorchestra.io/pipeline-runs/r1/lineage"


async def test_download_log_base64_encodes_with_range():
    calls = []

    def handler(request):
        calls.append((str(request.url), request.headers.get("Range")))
        return httpx.Response(200, content=b"hello logs")

    async with Client(_server(handler)) as client:
        result = await client.call_tool(
            "download_task_run_log",
            {
                "pipeline_run_id": "pr",
                "task_run_id": "tr",
                "filename": "run.log",
                "range_header": "bytes=-10",
            },
        )

    data = _download_result(result)
    assert data["content"] == base64.b64encode(b"hello logs").decode()
    assert data["encoding"] == "base64"
    url, range_header = calls[0]
    assert url.endswith(
        "/api/engine/public/pipeline_runs/pr/task_runs/tr/logs/download?filename=run.log"
    )
    assert range_header == "bytes=-10"


async def test_download_result_is_not_duplicated_as_structured_content():
    async with Client(_server(lambda request: httpx.Response(200, content=b"data"))) as client:
        result = await client.call_tool(
            "download_task_run_log",
            {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "run.log"},
        )

    assert result.structured_content is None
    assert len(result.content) == 1


async def test_download_artifact_hits_artifacts_path():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, content=b"data")

    async with Client(_server(handler)) as client:
        result = await client.call_tool(
            "download_task_run_artifact",
            {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "manifest.json"},
        )

    assert _download_result(result)["content"] == base64.b64encode(b"data").decode()
    assert calls[0].endswith("/task_runs/tr/artifacts/download?filename=manifest.json")


async def test_download_over_cap_errors_with_range_guidance():
    def handler(request):
        return httpx.Response(200, content=b"x" * (MAX_DOWNLOAD_BYTES + 1))

    async with Client(_server(handler)) as client:
        with pytest.raises(ToolError, match="range_header"):
            await client.call_tool(
                "download_task_run_artifact",
                {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "manifest.json"},
            )


async def test_download_artifact_forwards_range_and_returns_content_range():
    calls = []

    def handler(request):
        calls.append(request.headers.get("Range"))
        return httpx.Response(206, content=b"2345", headers={"Content-Range": "bytes 2-5/10"})

    async with Client(_server(handler)) as client:
        result = await client.call_tool(
            "download_task_run_artifact",
            {
                "pipeline_run_id": "pr",
                "task_run_id": "tr",
                "filename": "manifest.json",
                "range_header": "bytes=2-5",
            },
        )

    data = _download_result(result)
    assert calls[0] == "bytes=2-5"
    assert base64.b64decode(data["content"]) == b"2345"
    assert data["size_bytes"] == 4
    assert data["content_range"] == "bytes 2-5/10"


async def test_download_http_error_raises_tool_error():
    def handler(request):
        return httpx.Response(404, content=b"not found")

    async with Client(_server(handler)) as client:
        with pytest.raises(ToolError, match="HTTP 404"):
            await client.call_tool(
                "download_task_run_log",
                {"pipeline_run_id": "pr", "task_run_id": "tr", "filename": "missing.log"},
            )


async def test_download_unsatisfiable_range_raises_tool_error_with_hint():
    def handler(request):
        return httpx.Response(416, content=b"")

    async with Client(_server(handler)) as client:
        with pytest.raises(ToolError, match="not satisfiable"):
            await client.call_tool(
                "download_task_run_log",
                {
                    "pipeline_run_id": "pr",
                    "task_run_id": "tr",
                    "filename": "run.log",
                    "range_header": "bytes=99999999-",
                },
            )


# --- composite triage tools ---
#
# These go through build_http_client so the error-raising response hook is in place,
# which is what makes an HTTP failure inside a digest an OrchestraAPIError.

TASK_ANOMALY = {
    "a-1": {
        "type": "task_duration_above_baseline",
        "data": {
            "percentageAboveBaseline": 340,
            "medianSeconds": 60,
            "observedSeconds": 264,
            "thresholdSeconds": 120,
            "comparedRuns": 14,
        },
    }
}


def _page(results, total=None, page=1):
    return {
        "page": page,
        "pageSize": len(results),
        "total": len(results) if total is None else total,
        "results": results,
    }


def _triage_server(routes, ui_base_url="https://app.getorchestra.io"):
    """Serve each request from the first route whose pattern matches its path.

    Routes are regexes against the request path — order them specific-first, since
    e.g. ``/task_runs$`` also matches a pipeline run's task runs. A route value is a
    payload to serialize as JSON, or a callable taking the request and returning
    either a payload or an ``httpx.Response``.
    """
    requests: list[httpx.Request] = []

    def handler(request):
        requests.append(request)
        for pattern, route in routes.items():
            if re.search(pattern, request.url.path):
                payload = route(request) if callable(route) else route
                if isinstance(payload, httpx.Response):
                    return payload
                return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"detail": f"unrouted path {request.url.path}"})

    os.environ["ORCHESTRA_API_KEY"] = "test-api-key"
    client = build_http_client("https://example.com/api/engine")
    client._transport = httpx.MockTransport(handler)
    server = FastMCP("test")
    register_handwritten(server, client, ui_base_url)
    return server, requests


def _params(requests, pattern):
    return [dict(r.url.params) for r in requests if re.search(pattern, r.url.path)]


async def test_whats_broken_joins_failed_tasks_onto_their_pipeline_runs():
    server, requests = _triage_server(
        {
            r"/pipeline_runs$": _page(
                [
                    {
                        "id": "run-1",
                        "pipelineId": "pipe-1",
                        "pipelineName": "nightly",
                        "runStatus": "FAILED",
                        "envName": "Production",
                        "message": "1 task failed",
                    }
                ]
            ),
            r"/task_runs$": _page(
                [
                    {
                        "id": "tr-1",
                        "pipelineRunId": "run-1",
                        "taskName": "load_orders",
                        "taskId": "load_orders",
                        "integration": "SNOWFLAKE",
                        "status": "FAILED",
                        "message": "table not found",
                        "externalMessage": "SQL compilation error",
                        "platformLink": "https://snowflake.example/q/1",
                        "anomalies": TASK_ANOMALY,
                    },
                    {
                        "id": "tr-2",
                        "pipelineRunId": "other-run",
                        "taskName": "unrelated",
                        "taskId": "unrelated",
                        "status": "FAILED",
                    },
                ]
            ),
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("whats_broken", {})

    assert result.data["failingRunCount"] == 1
    assert result.data["truncated"] is False
    failure = result.data["failures"][0]
    assert failure["pipeline"] == "nightly"
    assert failure["environment"] == "Production"
    assert failure["lineageUrl"] == "https://app.getorchestra.io/pipeline-runs/run-1/lineage"
    assert failure["failedTaskCount"] == 1  # tr-2 belongs to a different pipeline run
    task = failure["failedTasks"][0]
    assert task["taskRunId"] == "tr-1"
    assert task["externalMessage"] == "SQL compilation error"
    assert task["anomalies"][0]["data"]["percentageAboveBaseline"] == 340


async def test_whats_broken_asks_for_a_bounded_window_without_superseded_attempts():
    server, requests = _triage_server(
        {
            r"/pipeline_runs$": _page([{"id": "run-1", "pipelineId": "pipe-1"}]),
            r"/task_runs$": _page([]),
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("whats_broken", {"window_hours": 24 * 30})

    assert result.data["window"]["hours"] == MAX_WINDOW_HOURS  # a month is clamped to 7 days
    run_params = _params(requests, r"/pipeline_runs$")[0]
    span = datetime.fromisoformat(run_params["time_to"]) - datetime.fromisoformat(
        run_params["time_from"]
    )
    assert span < timedelta(hours=MAX_WINDOW_HOURS)  # never lands on the API's own boundary
    assert run_params["status"] == "FAILED,WARNING"

    task_params = _params(requests, r"/public/task_runs$")[0]
    assert task_params["include_superseded"] == "false"
    assert task_params["pipeline_ids"] == "pipe-1"


async def test_whats_broken_pages_pipeline_runs_internally():
    def pipeline_runs(request):
        page = int(request.url.params["page"])
        return _page([{"id": f"run-{page}", "pipelineId": "pipe-1"}], total=2, page=page)

    server, requests = _triage_server(
        {r"/pipeline_runs$": pipeline_runs, r"/task_runs$": _page([])}
    )

    async with Client(server) as client:
        result = await client.call_tool("whats_broken", {})

    assert [f["pipelineRunId"] for f in result.data["failures"]] == ["run-1", "run-2"]
    assert [p["page"] for p in _params(requests, r"/pipeline_runs$")] == ["1", "2"]


async def test_whats_broken_reports_nothing_broken_without_a_task_run_lookup():
    server, requests = _triage_server({r"/pipeline_runs$": _page([])})

    async with Client(server) as client:
        result = await client.call_tool("whats_broken", {})

    assert result.data["failures"] == []
    assert result.data["failingRunCount"] == 0
    assert _params(requests, r"/public/task_runs$") == []


async def test_whats_broken_accepts_an_environment_name():
    server, requests = _triage_server(
        {
            r"/environments$": [{"environmentId": "env-1", "name": "Production"}],
            r"/pipeline_runs$": _page([]),
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("whats_broken", {"environment": "production"})

    assert result.data["environment"] == "Production"
    assert _params(requests, r"/pipeline_runs$")[0]["environments"] == "env-1"


async def test_whats_broken_lists_environments_when_the_name_is_unknown():
    server, _ = _triage_server({r"/environments$": [{"environmentId": "env-1", "name": "Prod"}]})

    async with Client(server) as client:
        with pytest.raises(ToolError, match="Available: Prod"):
            await client.call_tool("whats_broken", {"environment": "Staging"})


async def test_whats_broken_explains_a_403_from_the_metadata_api():
    server, _ = _triage_server(
        {r"/pipeline_runs$": lambda request: httpx.Response(403, json={"detail": "Forbidden"})}
    )

    async with Client(server) as client:
        with pytest.raises(ToolError, match="Metadata API may not be enabled"):
            await client.call_tool("whats_broken", {})


async def test_diagnose_gathers_upstream_statuses_log_tail_and_artifacts():
    server, requests = _triage_server(
        {
            r"/pipeline_runs/[^/]+/task_runs$": _page(
                [
                    {
                        "id": "tr-0",
                        "taskId": "extract",
                        "taskName": "extract",
                        "status": "SUCCEEDED",
                    },
                    {"id": "tr-1", "taskId": "load", "taskName": "load", "status": "FAILED"},
                ]
            ),
            r"/task_runs$": _page(
                [
                    {
                        "id": "tr-1",
                        "pipelineRunId": "run-1",
                        "pipelineId": "pipe-1",
                        "taskName": "load",
                        "taskId": "load",
                        "integration": "SNOWFLAKE",
                        "status": "FAILED",
                        "message": "table not found",
                        "taskParameters": {"warehouse": "WH"},
                        "runParameters": {"date": "2026-09-07"},
                        "dependsOn": ["extract", "vanished"],
                        "startedAt": "2026-09-07T01:00:00+00:00",
                        "completedAt": "2026-09-07T01:02:30+00:00",
                    }
                ]
            ),
            r"/logs/download$": lambda request: httpx.Response(200, content=b"line one\nboom"),
            r"/logs$": {
                "filenames": ["attempt-1.log", "attempt-2.log"],
                "files": {
                    "attempt-1.log": {"attemptNumber": 1},
                    "attempt-2.log": {"attemptNumber": 2},
                },
            },
            r"/artifacts$": {"filenames": ["run_results.json"]},
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("diagnose", {"task_run_id": "tr-1"})

    assert result.data["taskRun"]["durationSeconds"] == 150
    assert result.data["taskParameters"] == {"warehouse": "WH"}
    assert result.data["upstream"] == [
        {"taskId": "extract", "task": "extract", "status": "SUCCEEDED"},
        {"taskId": "vanished"},
    ]
    assert result.data["logTail"]["filename"] == "attempt-2.log"  # newest attempt
    assert result.data["logTail"]["tail"] == "line one\nboom"
    assert result.data["logTail"]["truncated"] is False
    assert result.data["artifacts"] == ["run_results.json"]
    assert result.data["lineageUrl"].endswith("/pipeline-runs/run-1/lineage")

    download = next(r for r in requests if r.url.path.endswith("/logs/download"))
    assert download.headers["Range"] == f"bytes=-{LOG_TAIL_BYTES}"
    assert dict(download.url.params)["filename"] == "attempt-2.log"


async def test_diagnose_reports_the_seven_day_limit_when_the_task_run_is_not_found():
    server, _ = _triage_server({r"/task_runs$": _page([])})

    async with Client(server) as client:
        with pytest.raises(ToolError, match="last 7 days"):
            await client.call_tool("diagnose", {"task_run_id": "tr-1"})


async def test_diagnose_survives_a_log_download_failure():
    server, _ = _triage_server(
        {
            r"/pipeline_runs/[^/]+/task_runs$": _page([]),
            r"/task_runs$": _page([{"id": "tr-1", "pipelineRunId": "run-1", "taskName": "load"}]),
            r"/logs/download$": lambda request: httpx.Response(416, content=b""),
            r"/logs$": {"filenames": ["attempt-1.log"], "files": {}},
            r"/artifacts$": {"filenames": []},
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("diagnose", {"task_run_id": "tr-1"})

    assert "416" in result.data["logTail"]["unavailable"]
    assert result.data["taskRun"]["taskRunId"] == "tr-1"


async def test_pipeline_context_summarises_runs_and_integrations_for_an_alias():
    definition = {
        "version": "v1",
        "name": "nightly",
        "pipeline": {
            "group_a": {
                "tasks": {"t1": {"integration": "DBT_CORE"}, "t2": {"integration": "SNOWFLAKE"}}
            },
            "standalone": {"integration": "PYTHON"},
        },
    }
    server, requests = _triage_server(
        {
            r"/pipelines/data$": definition,
            r"/public/pipeline$": {
                "id": "pipe-1",
                "name": "nightly",
                "alias": "nightly",
                "paused": False,
            },
            r"/pipeline_runs$": _page(
                [
                    {
                        "id": "run-1",
                        "runStatus": "SUCCEEDED",
                        "startedAt": "2026-09-07T01:00:00+00:00",
                        "completedAt": "2026-09-07T01:01:00+00:00",
                    },
                    {
                        "id": "run-2",
                        "runStatus": "SUCCEEDED",
                        "startedAt": "2026-09-06T01:00:00+00:00",
                        "completedAt": "2026-09-06T01:05:00+00:00",
                    },
                    {
                        "id": "run-3",
                        "runStatus": "FAILED",
                        "startedAt": "2026-09-05T01:00:00+00:00",
                        "completedAt": "2026-09-05T02:00:00+00:00",
                    },
                ]
            ),
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("pipeline_context", {"pipeline_id_or_alias": "nightly"})

    assert result.data["integrations"] == ["DBT_CORE", "PYTHON", "SNOWFLAKE"]
    assert result.data["definition"] == definition
    assert result.data["pipeline"]["paused"] is False
    # median over the succeeded runs only, so the hour-long failure does not skew it
    assert result.data["medianSucceededDurationSeconds"] == 180
    assert _params(requests, r"/public/pipeline$")[0] == {"alias": "nightly"}
    assert _params(requests, r"/pipeline_runs$")[0]["pipeline_ids"] == "pipe-1"


async def test_pipeline_context_selects_by_id_when_given_a_uuid():
    pipeline_id = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    server, requests = _triage_server(
        {
            r"/pipelines/data$": {"pipeline": {}},
            r"/public/pipeline$": {"id": pipeline_id, "name": "nightly"},
            r"/pipeline_runs$": _page([]),
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("pipeline_context", {"pipeline_id_or_alias": pipeline_id})

    assert result.data["medianSucceededDurationSeconds"] is None
    assert result.data["integrations"] == []
    assert _params(requests, r"/public/pipeline$")[0] == {"pipeline_id": pipeline_id}


@pytest.mark.parametrize(
    "started_at,completed_at",
    [
        (None, "2026-09-07T01:02:30+00:00"),
        ("2026-09-07T01:00:00+00:00", None),
        ("not a timestamp", "2026-09-07T01:02:30+00:00"),
        # One naive, one offset-aware: subtracting these raises rather than failing to parse.
        ("2026-09-07T01:00:00", "2026-09-07T01:02:30Z"),
    ],
)
def test_duration_is_none_when_timestamps_cannot_be_subtracted(started_at, completed_at):
    assert _duration_seconds(started_at, completed_at) is None


async def test_diagnose_bounds_the_log_tail_when_the_range_header_is_ignored():
    whole_log = b"".join(f"line {index}\n".encode() for index in range(20_000))
    assert len(whole_log) > LOG_TAIL_BYTES
    server, _ = _triage_server(
        {
            r"/pipeline_runs/[^/]+/task_runs$": _page([]),
            r"/task_runs$": _page([{"id": "tr-1", "pipelineRunId": "run-1", "taskName": "load"}]),
            # A server that ignores the suffix range and returns the entire log.
            r"/logs/download$": lambda request: httpx.Response(200, content=whole_log),
            r"/logs$": {"filenames": ["run.log"], "files": {}},
            r"/artifacts$": {"filenames": []},
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("diagnose", {"task_run_id": "tr-1"})

    tail = result.data["logTail"]["tail"]
    assert result.data["logTail"]["truncated"] is True
    assert len(tail.encode()) <= LOG_TAIL_BYTES
    assert tail.endswith("line 19999\n")


async def test_diagnose_flags_a_truncated_tail_when_the_range_header_is_honoured():
    server, _ = _triage_server(
        {
            r"/pipeline_runs/[^/]+/task_runs$": _page([]),
            r"/task_runs$": _page([{"id": "tr-1", "pipelineRunId": "run-1", "taskName": "load"}]),
            # A server honouring the suffix range returns exactly the cap, whatever the
            # log's real size, so the tail is the only evidence that it was cut.
            r"/logs/download$": lambda request: httpx.Response(
                206,
                content=b"x" * LOG_TAIL_BYTES,
                headers={"Content-Range": f"bytes 100-{100 + LOG_TAIL_BYTES - 1}/900000"},
            ),
            r"/logs$": {"filenames": ["run.log"], "files": {}},
            r"/artifacts$": {"filenames": []},
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("diagnose", {"task_run_id": "tr-1"})

    assert result.data["logTail"]["truncated"] is True


async def test_whats_broken_flags_truncation_when_a_run_exceeds_the_per_task_cap():
    failed_tasks = [
        {
            "id": f"tr-{index}",
            "pipelineRunId": "run-1",
            "taskName": f"task-{index}",
            "status": "FAILED",
        }
        for index in range(MAX_FAILED_TASKS_PER_RUN + 3)
    ]
    server, _ = _triage_server(
        {
            r"/pipeline_runs$": _page([{"id": "run-1", "pipelineId": "pipe-1"}]),
            r"/task_runs$": _page(failed_tasks),
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("whats_broken", {})

    failure = result.data["failures"][0]
    assert failure["failedTaskCount"] == MAX_FAILED_TASKS_PER_RUN + 3
    assert len(failure["failedTasks"]) == MAX_FAILED_TASKS_PER_RUN
    assert result.data["truncated"] is True  # the dropped tasks are declared


async def test_diagnose_flags_an_unresolved_dependency_from_a_capped_sibling_listing():
    siblings = [
        {"id": f"tr-{index}", "taskId": f"task-{index}", "status": "SUCCEEDED"}
        for index in range(RUN_TASK_RUNS_PAGE_SIZE)
    ]
    server, _ = _triage_server(
        {
            # More task runs in the run than the listing returns, so "extract" is
            # unresolved because of the cap rather than because it does not exist.
            r"/pipeline_runs/[^/]+/task_runs$": _page(siblings, total=MAX_SIBLING_TASK_RUNS + 50),
            r"/task_runs$": _page(
                [
                    {
                        "id": "tr-x",
                        "pipelineRunId": "run-1",
                        "taskName": "load",
                        "dependsOn": ["extract"],
                    }
                ]
            ),
            r"/logs$": {"filenames": []},
            r"/artifacts$": {"filenames": []},
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("diagnose", {"task_run_id": "tr-x"})

    assert result.data["upstream"] == [{"taskId": "extract"}]
    assert result.data["upstreamTruncated"] is True


async def test_diagnose_bounds_a_huge_parameter_value_and_caps_the_artifact_list():
    script = "print('x')\n" * 5_000
    server, _ = _triage_server(
        {
            r"/pipeline_runs/[^/]+/task_runs$": _page([]),
            r"/task_runs$": _page(
                [
                    {
                        "id": "tr-1",
                        "pipelineRunId": "run-1",
                        "taskName": "load",
                        "taskParameters": {"command": script, "warehouse": "WH"},
                    }
                ]
            ),
            r"/logs$": {"filenames": []},
            r"/artifacts$": {
                "filenames": [f"artifact-{index}.json" for index in range(MAX_ARTIFACT_NAMES + 20)]
            },
        }
    )

    async with Client(server) as client:
        result = await client.call_tool("diagnose", {"task_run_id": "tr-1"})

    command = result.data["taskParameters"]["command"]
    assert len(command) < len(script)
    assert command.endswith(f"({len(script)} chars)")
    assert result.data["taskParameters"]["warehouse"] == "WH"  # structure survives
    assert len(result.data["artifacts"]) == MAX_ARTIFACT_NAMES
    assert result.data["artifactCount"] == MAX_ARTIFACT_NAMES + 20
