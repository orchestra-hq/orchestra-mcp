import base64
import json
import re
import statistics
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from uuid import UUID

import httpx
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.tools.tool import ToolResult
from mcp.types import TextContent, ToolAnnotations
from pydantic import UUID4, Field

from orchestramcp.errors import OrchestraAPIError

# Operations excluded from generation because they are served by the hand-written
# tools below: chunked file downloads, and an endpoint whose
# upstream handler reads the raw request, so the spec declares no body for it.
HANDWRITTEN_OPERATION_IDS = (
    "download_task_run_log",
    "download_task_run_artifact",
    "validate_pipeline",
)

# Claude Code saves a text tool result over 50,000 characters (or 25,000 tokens) to a
# file instead of showing it to the model; agents then shell out to read it back.
# Results are kept under this budget with headroom for the envelope.
MAX_RESULT_CHARS = 40_000

# Default bytes per download call. Text comes back at most this many characters and
# binary chunks are cut to 3/4 of it so their base64 is the same length. That stays
# under MAX_RESULT_CHARS and, at base64's ~1.5 characters per token, under the
# 25,000-token limit too.
CHUNK_BYTES = MAX_RESULT_CHARS * 3 // 4

# Largest chunk a caller may ask for, bounded by the transport rather than the agent:
# base64 makes 3MiB about 4MiB, under the Lambda's ~6MB response payload limit with
# room for the JSON-RPC and API Gateway wrapping. For bulk reads saved to a file.
MAX_CHUNK_BYTES = 3 * 1024 * 1024

_DOWNLOAD_DESCRIPTION = (
    "Read a task run {kind} file in chunks.{note} Pass offset to choose where to start: 0 "
    "reads from the beginning, a negative offset counts back from the end (e.g. -30000 "
    "reads the last 30000 bytes, usually where an error is). The first content block "
    "reports total_bytes and next_offset; call again with offset=next_offset until "
    "next_offset is null to read the whole file. Text comes back as-is (encoding utf-8), "
    "binary content base64-encoded (encoding base64, 3/4 of chunk_bytes per call). Text "
    "with a few invalid bytes comes back as utf-8-escaped: each invalid byte appears as "
    "\\xNN and every literal backslash is doubled. "
    f"chunk_bytes defaults to {CHUNK_BYTES}, which you can read in line; "
    f"raise it up to {MAX_CHUNK_BYTES} only to save a large file to disk and process it "
    "with a script."
)

ChunkBytes = Annotated[
    # At least 4, the longest UTF-8 character, so a chunk always holds a whole one.
    int, Field(ge=4, le=MAX_CHUNK_BYTES, description="Bytes to return in this call.")
]


# Mirrors the header's description in the public spec, which the generated tools inherit.
AccountId = Annotated[
    UUID4 | None,
    Field(
        description=(
            "Act on this account rather than the one the credential resolves to. Omit it to "
            "use the credential's own account. An API key is issued to a single account, so it "
            "may only name that account; an OAuth token may name any account its grant covers."
        )
    ),
]


def _account_headers(account_id: UUID | None) -> dict[str, str]:
    return {"X-Orchestra-Account-Id": str(account_id)} if account_id else {}


# GET /task_runs and GET /pipeline_runs serve at most a 7-day window, so a requested
# triage window is clamped to it rather than rejected by the API.
MAX_WINDOW_HOURS = 7 * 24
DEFAULT_WINDOW_HOURS = 24

# The largest page each paginated endpoint accepts.
RUNS_PAGE_SIZE = 100
RUN_TASK_RUNS_PAGE_SIZE = 50

# Output caps. A digest is re-read by the agent on every triage turn, so it trades
# completeness for tokens and reports the totals it truncated against.
MAX_FAILING_RUNS = 20
MAX_FAILED_TASKS_PER_RUN = 10
MAX_SIBLING_TASK_RUNS = 100
MAX_RECENT_RUNS = 20
MAX_ARTIFACT_NAMES = 50
MAX_PARAMETER_CHARS = 2 * 1024
LOG_TAIL_BYTES = 8 * 1024


def _lineage_url(ui_base_url: str, pipeline_run_id: str) -> str:
    return f"{ui_base_url}/pipeline-runs/{pipeline_run_id}/lineage"


def _window(hours: int) -> tuple[str, str, int]:
    """Resolve a window of the last ``hours``, clamped to what the API serves.

    The span asked for is a second short of the requested one, so a window clamped
    to the maximum cannot be rejected by a range check on the boundary itself.
    """
    hours = max(1, min(hours, MAX_WINDOW_HOURS))
    now = datetime.now(tz=UTC)
    time_from = now - timedelta(hours=hours) + timedelta(seconds=1)
    return time_from.isoformat(), now.isoformat(), hours


def _duration_seconds(started_at: str | None, completed_at: str | None) -> int | None:
    """Whole seconds between two API timestamps, or None if either cannot be read."""
    try:
        started = datetime.fromisoformat(started_at)
        completed = datetime.fromisoformat(completed_at)
        return round((completed - started).total_seconds())
    except (TypeError, ValueError):
        return None


def _bound_strings(value, limit: int = MAX_PARAMETER_CHARS):
    """Cut over-long strings anywhere inside a parameter object, keeping its shape.

    Task parameters carry arbitrary payloads — an inline script, a rendered SQL
    statement — and a digest cannot afford one verbatim. Structure survives so the
    agent still sees which parameters were set; only the oversized values are cut.
    A parameter object with a huge *number* of small keys is still passed whole, and
    the response-size guard in the request handler remains the backstop for that.
    """
    if isinstance(value, str):
        return value if len(value) <= limit else f"{value[:limit]}… ({len(value)} chars)"
    if isinstance(value, dict):
        return {key: _bound_strings(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_bound_strings(item, limit) for item in value]
    return value


def _anomalies(record: dict) -> list[dict]:
    """Flatten the uuid-keyed anomaly map on a run or task run into a list."""
    return list((record.get("anomalies") or {}).values())


def _compact(record: dict) -> dict:
    """Drop empty values, which carry no signal and are re-read on every turn."""
    return {key: value for key, value in record.items() if value not in (None, "", [], {})}


def _task_digest(task_run: dict) -> dict:
    """Compact a task run down to what identifies a failure and explains it."""
    return _compact(
        {
            "taskRunId": task_run.get("id"),
            "task": task_run.get("taskName"),
            "taskId": task_run.get("taskId"),
            "integration": task_run.get("integration"),
            "integrationJob": task_run.get("integrationJob"),
            "status": task_run.get("status"),
            "message": task_run.get("message"),
            "externalStatus": task_run.get("externalStatus"),
            "externalMessage": task_run.get("externalMessage"),
            "platformLink": task_run.get("platformLink"),
            "attemptNumber": task_run.get("attemptNumber"),
            "anomalies": _anomalies(task_run),
        }
    )


def _pipeline_selector(pipeline_id_or_alias: str) -> dict:
    """Pick the selector the pipeline endpoints expect, by whether the value is a UUID."""
    try:
        UUID(pipeline_id_or_alias)
    except ValueError:
        return {"alias": pipeline_id_or_alias}
    return {"pipeline_id": pipeline_id_or_alias}


def _definition_integrations(definition: dict) -> list[str]:
    """Collect the integrations named by a pipeline definition's tasks.

    Entries under ``pipeline`` are either a task group, whose ``tasks`` hold the
    integrations, or a standalone task that names one itself.
    """
    integrations = set()
    for node in (definition.get("pipeline") or {}).values():
        if not isinstance(node, dict):
            continue
        tasks = node.get("tasks")
        for task in tasks.values() if isinstance(tasks, dict) else [node]:
            if isinstance(task, dict) and task.get("integration"):
                integrations.add(task["integration"])
    return sorted(integrations)


def register_handwritten(server: FastMCP, client: httpx.AsyncClient, ui_base_url: str) -> None:
    """Register the tools that cannot be generated from the spec.

    ``get_pipeline_run_lineage_url`` has no backing endpoint; the downloads read a
    file in chunks an agent can take in line; ``validate_pipeline``
    posts a body the spec does not declare. The composite triage tools each join
    several endpoints, so no single operation describes them.
    """
    _register_triage(server, client, ui_base_url)

    @server.tool(
        annotations=ToolAnnotations(title="Get Pipeline Run Lineage URL", readOnlyHint=True)
    )
    def get_pipeline_run_lineage_url(pipeline_run_id: str) -> str:
        """Build the URL of a pipeline run's lineage graph in the Orchestra UI."""
        return _lineage_url(ui_base_url, pipeline_run_id)

    @server.tool(
        description=(
            "Validate a full pipeline definition document without creating or updating a "
            "pipeline. Use it to check a definition before create_pipeline or update_pipeline."
        ),
        annotations=ToolAnnotations(title="Validate Pipeline", readOnlyHint=True),
    )
    async def validate_pipeline(
        pipeline_definition: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "Full pipeline definition document as JSON, matching the pipeline YAML "
                    'structure, e.g. {"version": "v1", "name": "...", "pipeline": '
                    "{...task groups...}}. Pass the whole document — version, name and "
                    "pipeline are required top-level keys; the task groups go under the "
                    "nested 'pipeline' key. Same document create_pipeline accepts."
                )
            ),
        ],
        canonicalize: Annotated[
            bool,
            Field(
                description=(
                    "When true, a valid response also includes the pipeline serialised in "
                    "Orchestra's canonical camelCase form under a 'pipeline' key."
                )
            ),
        ] = False,
        account_id: AccountId = None,
    ) -> dict:
        response = await client.post(
            "/public/pipelines/schema",
            json=pipeline_definition,
            params={"canonicalize": canonicalize},
            headers=_account_headers(account_id),
        )
        return response.json()

    async def _download(
        path: str, filename: str, offset: int, chunk_bytes: int, account_id: UUID | None
    ) -> ToolResult:
        headers = _account_headers(account_id)
        if offset >= 0:
            headers["Range"] = f"bytes={offset}-{offset + chunk_bytes - 1}"
        else:
            headers["Range"] = f"bytes={offset}"
        try:
            async with client.stream(
                "GET", path, params={"filename": filename}, headers=headers
            ) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise OrchestraAPIError(response.status_code, f"Download of {filename} failed")
                start, total = _content_range(response)
                if start is None and offset != 0:
                    raise ToolError(
                        f"The server ignored the requested range for {filename}; only "
                        "offset=0 can be read."
                    )
                # Only the first chunk_bytes are read: a server ignoring the range sends
                # the whole file, which can run to hundreds of MB.
                content = b""
                async for content in response.aiter_bytes(chunk_size=chunk_bytes):
                    break
                start = start or 0
        except OrchestraAPIError as exc:
            if exc.status_code != 416:
                raise
            # An empty file satisfies no range, so reading it from the start is not an error.
            if offset <= 0:
                return _chunk_result(filename, b"", 0, 0, chunk_bytes, tail=False)
            raise ToolError(f"Offset {offset} is past the end of {filename}.") from exc
        return _chunk_result(filename, content, start, total, chunk_bytes, tail=offset < 0)

    @server.tool(
        description=_DOWNLOAD_DESCRIPTION.format(kind="log", note=""),
        annotations=ToolAnnotations(title="Download Task Run Log", readOnlyHint=True),
    )
    async def download_task_run_log(
        pipeline_run_id: str,
        task_run_id: str,
        filename: str,
        offset: int = 0,
        chunk_bytes: ChunkBytes = CHUNK_BYTES,
        account_id: AccountId = None,
    ) -> ToolResult:
        path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download"
        return await _download(path, filename, offset, chunk_bytes, account_id=account_id)

    @server.tool(
        description=_DOWNLOAD_DESCRIPTION.format(
            kind="artifact", note=" Artifacts such as a dbt manifest.json are often tens of MB."
        ),
        annotations=ToolAnnotations(title="Download Task Run Artifact", readOnlyHint=True),
    )
    async def download_task_run_artifact(
        pipeline_run_id: str,
        task_run_id: str,
        filename: str,
        offset: int = 0,
        chunk_bytes: ChunkBytes = CHUNK_BYTES,
        account_id: AccountId = None,
    ) -> ToolResult:
        path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download"
        return await _download(path, filename, offset, chunk_bytes, account_id=account_id)


def _content_range(response: httpx.Response) -> tuple[int | None, int | None]:
    """Read (start, total) from a partial response, or (None, total) for a whole one."""
    match = re.fullmatch(r"bytes (\d+)-\d+/(\d+|\*)", response.headers.get("content-range", ""))
    if match and response.status_code == 206:
        total = match.group(2)
        return int(match.group(1)), None if total == "*" else int(total)
    # A compressed body's length is not the length of the bytes read from it.
    length = response.headers.get("content-length")
    encoded = response.headers.get("content-encoding", "identity") != "identity"
    return None, int(length) if length and length.isdigit() and not encoded else None


def _decode(body: bytes, more_follows: bool) -> tuple[bytes, str, str] | None:
    """Decode a chunk to (bytes covered, text, encoding), or None if it is binary.

    A last character cut by the chunk's end is left for the next chunk, which exists
    only if more of the file follows. Text with a few invalid bytes, such as one
    Latin-1 character in a log, stays readable: those bytes are escaped as \\xNN and
    literal backslashes doubled, so the original bytes can still be recovered.
    """
    try:
        return body, body.decode("utf-8"), "utf-8"
    except UnicodeDecodeError as exc:
        split = exc.reason == "unexpected end of data" and exc.start >= len(body) - 3
        if split and more_follows:
            return _decode(body[: exc.start], False)
    invalid = body.decode("utf-8", "replace").count("\ufffd")
    if invalid * 100 > len(body):
        return None
    escaped = body.replace(b"\\", b"\\\\").decode("utf-8", "backslashreplace")
    return body, escaped, "utf-8-escaped"


def _chunk_result(
    filename: str, content: bytes, start: int, total: int | None, chunk_bytes: int, tail: bool
) -> ToolResult:
    """Return the chunk as plain text when it is UTF-8, else base64.

    Plain text avoids base64 and JSON escaping, so a chunk's characters track its
    bytes. A multi-byte character split by either chunk boundary is left to the
    neighbouring chunk, so following next_offset still reads every byte once.
    """
    more_follows = len(content) >= chunk_bytes and (total is None or start + len(content) < total)
    lead = 0
    # Only a tail read lands at an arbitrary byte; a start reached by following
    # next_offset is on a character boundary, so stripping there could drop the
    # bytes of a binary chunk returned before it.
    while tail and lead < min(3, len(content)) and 0x80 <= content[lead] < 0xC0:
        lead += 1
    decoded = _decode(content[lead:], more_follows)
    if decoded is None:
        lead = 0
        body = content[: chunk_bytes * 3 // 4]
        text, encoding = base64.b64encode(body).decode("ascii"), "base64"
    else:
        body, text, encoding = decoded
    start += lead
    end = start + len(body)
    more = (
        end < total
        if total is not None
        else len(body) < len(content) or len(content) >= chunk_bytes
    )
    meta = {
        "filename": filename,
        "offset": start,
        "size_bytes": len(body),
        "total_bytes": total,
        "next_offset": end if more else None,
        "encoding": encoding,
    }
    return ToolResult(
        content=[
            TextContent(type="text", text=json.dumps(meta)),
            TextContent(type="text", text=text),
        ]
    )


def _register_triage(server: FastMCP, client: httpx.AsyncClient, ui_base_url: str) -> None:
    """Register the composite read tools, each answering one triage question in a call.

    They join several endpoints and page internally, so the agent spends no round
    trips on plumbing and never sees a cursor.
    """

    # Every helper below takes account_id with no default, so a call that forgets to
    # forward it fails outright instead of silently querying the default account.
    async def _get(path: str, account_id: UUID | None, params: dict | None = None) -> Any:
        response = await client.get(path, params=params, headers=_account_headers(account_id))
        return response.json()

    async def _paged(
        path: str, params: dict, page_size: int, limit: int, account_id: UUID | None
    ) -> tuple[list[dict], int]:
        """Follow pages until ``limit`` results are collected or the endpoint runs out.

        Returns the results alongside the endpoint's reported total, so a caller can
        say what it truncated against.
        """
        results: list[dict] = []
        total = 0
        page = 1
        while True:
            payload = await _get(path, account_id, {**params, "page": page, "page_size": page_size})
            batch = payload.get("results") or []
            total = payload.get("total") or len(results) + len(batch)
            results.extend(batch)
            if not batch or len(results) >= min(limit, total):
                break
            page += 1
        return results[:limit], total

    async def _resolve_environment(environment: str, account_id: UUID | None) -> dict:
        """Look up an environment by ID or name, so a caller can pass either."""
        environments = await _get("/public/environments", account_id=account_id)
        for candidate in environments:
            if environment == candidate.get("environmentId") or (
                environment.casefold() == (candidate.get("name") or "").casefold()
            ):
                return candidate
        available = ", ".join(sorted(c.get("name", "") for c in environments)) or "none"
        raise ToolError(f"No environment matches '{environment}'. Available: {available}.")

    async def _log_tail(base_path: str, account_id: UUID | None) -> dict | None:
        """Fetch the tail of the newest log on a task run, or None if it has no logs."""
        listing = await _get(f"{base_path}/logs", account_id=account_id)
        filenames = listing.get("filenames") or []
        if not filenames:
            return None
        files = listing.get("files") or {}
        newest = max(filenames, key=lambda name: (files.get(name) or {}).get("attemptNumber", 0))
        # Streamed into a bounded buffer rather than read whole: the suffix range
        # should make the body small, but a log ignoring it can run to hundreds of MB
        # and the Lambda has no memory to buffer one.
        try:
            received = 0
            tail = b""
            async with client.stream(
                "GET",
                f"{base_path}/logs/download",
                params={"filename": newest},
                headers={**_account_headers(account_id), "Range": f"bytes=-{LOG_TAIL_BYTES}"},
            ) as response:
                async for chunk in response.aiter_bytes():
                    received += len(chunk)
                    tail = (tail + chunk)[-LOG_TAIL_BYTES:]
        except OrchestraAPIError as exc:
            return {"filename": newest, "unavailable": str(exc)}
        return {
            "filename": newest,
            "tail": tail.decode("utf-8", errors="replace"),
            # A honoured range returns exactly the cap for any longer log, so treat a
            # full buffer as truncated: over-reporting costs a download the agent did
            # not need, under-reporting has it believe a cut log is the whole one.
            "truncated": received >= LOG_TAIL_BYTES,
        }

    @server.tool(
        description=(
            "Start here for 'what is broken' or 'why did last night's run fail'. Returns every "
            "failing and warning pipeline run in the window, already joined to the task runs "
            "that failed inside it, with each task's message, externalMessage, platformLink and "
            "duration-vs-baseline anomalies. Retried attempts are excluded. Windows wider than "
            f"{MAX_WINDOW_HOURS} hours are clamped to that, the widest the API serves. Follow up "
            "on a single task run with diagnose."
        ),
        annotations=ToolAnnotations(title="What's Broken", readOnlyHint=True),
    )
    async def whats_broken(
        window_hours: int = DEFAULT_WINDOW_HOURS,
        environment: str | None = None,
        account_id: AccountId = None,
    ) -> dict:
        time_from, time_to, hours = _window(window_hours)
        environment_record = (
            await _resolve_environment(environment, account_id=account_id) if environment else None
        )

        run_params = {"status": "FAILED,WARNING", "time_from": time_from, "time_to": time_to}
        if environment_record:
            run_params["environments"] = environment_record["environmentId"]
        runs, run_total = await _paged(
            "/public/pipeline_runs",
            run_params,
            RUNS_PAGE_SIZE,
            MAX_FAILING_RUNS,
            account_id=account_id,
        )

        # One status-filtered sweep over the pipelines that failed, then group by run.
        # /task_runs cannot filter by pipeline run, but fetching per run would cost a
        # request per run and return every passing task alongside the failures.
        failed_tasks: list[dict] = []
        failed_task_total = 0
        pipeline_ids = sorted({run["pipelineId"] for run in runs})
        if pipeline_ids:
            failed_tasks, failed_task_total = await _paged(
                "/public/task_runs",
                {
                    "status": "FAILED,WARNING",
                    "time_from": time_from,
                    "time_to": time_to,
                    "pipeline_ids": ",".join(pipeline_ids),
                    "include_superseded": "false",
                },
                RUNS_PAGE_SIZE,
                MAX_FAILING_RUNS * MAX_FAILED_TASKS_PER_RUN,
                account_id=account_id,
            )
        tasks_by_run: dict[str, list[dict]] = {}
        for task_run in failed_tasks:
            tasks_by_run.setdefault(task_run.get("pipelineRunId"), []).append(task_run)

        failures = []
        dropped_tasks = False
        for run in runs:
            tasks = tasks_by_run.get(run["id"], [])
            dropped_tasks = dropped_tasks or len(tasks) > MAX_FAILED_TASKS_PER_RUN
            failure = _compact(
                {
                    "pipeline": run.get("pipelineName"),
                    "pipelineId": run.get("pipelineId"),
                    "pipelineRunId": run.get("id"),
                    "runStatus": run.get("runStatus"),
                    "environment": run.get("envName"),
                    "branch": run.get("branch"),
                    "startedAt": run.get("startedAt"),
                    "completedAt": run.get("completedAt"),
                    "message": run.get("message"),
                    "anomalies": _anomalies(run),
                    "lineageUrl": _lineage_url(ui_base_url, run["id"]),
                }
            )
            failure["failedTaskCount"] = len(tasks)
            failure["failedTasks"] = [
                _task_digest(task) for task in tasks[:MAX_FAILED_TASKS_PER_RUN]
            ]
            failures.append(failure)

        return {
            "window": {"from": time_from, "to": time_to, "hours": hours},
            "environment": environment_record["name"] if environment_record else None,
            "failingRunCount": run_total,
            "failures": failures,
            # Partial for any of three reasons: more failing runs than are listed,
            # a task sweep that hit its own cap (it is ordered by task run, not by
            # pipeline run, so a noisy window can starve a listed run), or a single
            # run with more failed tasks than the per-run cap shows.
            "truncated": (
                run_total > len(failures) or failed_task_total > len(failed_tasks) or dropped_tasks
            ),
        }

    @server.tool(
        description=(
            "Deep dive on one failed task run: its status and messages, taskParameters and "
            "runParameters, the statuses of the upstream tasks it depends on, the tail of its "
            "newest log, and its artifact filenames. "
            "Over-long parameter values, the log tail and the artifact list are capped, and the "
            "response says which parts were cut. Use download_task_run_log or "
            "download_task_run_artifact when the tail is not enough."
        ),
        annotations=ToolAnnotations(title="Diagnose Task Run", readOnlyHint=True),
    )
    async def diagnose(task_run_id: str, account_id: AccountId = None) -> dict:
        try:
            task_run = await _get(f"/public/task_runs/{task_run_id}", account_id=account_id)
        except OrchestraAPIError as exc:
            if exc.status_code == 404:
                raise ToolError(f"No task run found with ID {task_run_id}.") from exc
            raise
        pipeline_run_id = task_run["pipelineRunId"]

        siblings, sibling_total = await _paged(
            f"/public/pipeline_runs/{pipeline_run_id}/task_runs",
            {"include_superseded": "false"},
            RUN_TASK_RUNS_PAGE_SIZE,
            MAX_SIBLING_TASK_RUNS,
            account_id=account_id,
        )
        siblings_by_task_id = {sibling.get("taskId"): sibling for sibling in siblings}
        upstream = [
            _compact(
                {
                    "taskId": task_id,
                    "task": siblings_by_task_id.get(task_id, {}).get("taskName"),
                    "status": siblings_by_task_id.get(task_id, {}).get("status"),
                }
            )
            for task_id in task_run.get("dependsOn") or []
        ]

        base_path = f"/public/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}"
        artifacts = await _get(f"{base_path}/artifacts", account_id=account_id)

        detail = _task_digest(task_run)
        detail.update(
            _compact(
                {
                    "pipelineRunId": pipeline_run_id,
                    "pipelineId": task_run.get("pipelineId"),
                    "startedAt": task_run.get("startedAt"),
                    "completedAt": task_run.get("completedAt"),
                    "durationSeconds": _duration_seconds(
                        task_run.get("startedAt"), task_run.get("completedAt")
                    ),
                }
            )
        )
        filenames = artifacts.get("filenames") or []
        return {
            "taskRun": detail,
            "taskParameters": _bound_strings(task_run.get("taskParameters") or {}),
            "runParameters": _bound_strings(task_run.get("runParameters") or {}),
            "upstream": upstream,
            # A run with more task runs than the cap can leave a dependency's status
            # unresolved, which would otherwise be indistinguishable from a dependency
            # that has no task run at all.
            "upstreamTruncated": sibling_total > len(siblings),
            "logTail": await _log_tail(base_path, account_id=account_id),
            "artifactCount": len(filenames),
            "artifacts": filenames[:MAX_ARTIFACT_NAMES],
            "lineageUrl": _lineage_url(ui_base_url, pipeline_run_id),
        }

    @server.tool(
        description=(
            "What an agent needs before editing or reasoning about a pipeline: its metadata, "
            "its full definition (the pipeline YAML structure as JSON), the integrations its "
            "tasks use, its recent run outcomes, and the median duration of its succeeded runs. "
            "Takes a pipeline ID or an alias. Run history covers the last 7 days, the widest "
            "window the API serves."
        ),
        annotations=ToolAnnotations(title="Pipeline Context", readOnlyHint=True),
    )
    async def pipeline_context(pipeline_id_or_alias: str, account_id: AccountId = None) -> dict:
        selector = _pipeline_selector(pipeline_id_or_alias)
        pipeline = await _get("/public/pipeline", account_id, selector)
        definition = await _get("/public/pipelines/data", account_id, selector)
        # Without an explicit window the API returns only the last 24 hours of runs.
        time_from, time_to, _ = _window(MAX_WINDOW_HOURS)
        runs, run_total = await _paged(
            "/public/pipeline_runs",
            {"pipeline_ids": pipeline["id"], "time_from": time_from, "time_to": time_to},
            RUNS_PAGE_SIZE,
            MAX_RECENT_RUNS,
            account_id=account_id,
        )

        recent_runs = []
        succeeded_durations = []
        for run in runs:
            duration = _duration_seconds(run.get("startedAt"), run.get("completedAt"))
            if duration is not None and run.get("runStatus") == "SUCCEEDED":
                succeeded_durations.append(duration)
            recent_runs.append(
                _compact(
                    {
                        "pipelineRunId": run.get("id"),
                        "runStatus": run.get("runStatus"),
                        "startedAt": run.get("startedAt"),
                        "durationSeconds": duration,
                        "message": run.get("message"),
                        "anomalies": _anomalies(run),
                    }
                )
            )

        return {
            "pipeline": _compact(
                {
                    "id": pipeline.get("id"),
                    "name": pipeline.get("name"),
                    "alias": pipeline.get("alias"),
                    "paused": pipeline.get("paused"),
                    "schedule": pipeline.get("schedule"),
                    "numTasks": pipeline.get("numTasks"),
                    "yamlPath": pipeline.get("yamlPath"),
                    "repository": pipeline.get("repository"),
                    "defaultBranch": pipeline.get("defaultBranch"),
                    "storageProvider": pipeline.get("storageProvider"),
                    "publishedVersionNumber": pipeline.get("publishedVersionNumber"),
                    "latestVersionNumber": pipeline.get("latestVersionNumber"),
                }
            ),
            "integrations": _definition_integrations(definition),
            "definition": definition,
            "recentRunCount": run_total,
            "recentRuns": recent_runs,
            "medianSucceededDurationSeconds": (
                round(statistics.median(succeeded_durations)) if succeeded_durations else None
            ),
        }
