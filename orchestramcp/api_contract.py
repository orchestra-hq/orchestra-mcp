"""Declarative contract linking each MCP tool to the Orchestra API operation it wraps.

This module is the single source of truth for "which endpoints the MCP depends on
and how". It is intentionally hand-maintained: the MCP is a curated surface over the
API, not a generated copy of it, so a human decides what each tool exposes.

``scripts/check_api_conformance.py`` reads this contract and asserts it still matches
the live OpenAPI spec, so that renamed paths/params or new enum values surface as a PR
instead of silently breaking a tool. When you add or change a tool in ``server.py`` /
``client.py``, add or update its entry here.

Paths are written **client-relative** — i.e. as passed to ``OrchestraClient._client``
(base URL ``.../api/engine/public``). The checker prepends ``PUBLIC_PREFIX`` to match
the spec, where every operation lives under ``/public/...``.
"""

from dataclasses import dataclass

# Every MCP-backed operation lives under this prefix in the OpenAPI spec, but the
# client's base URL already includes it, so contract paths omit it.
PUBLIC_PREFIX = "/public"

# Public URL of the live engine OpenAPI document (same source the docs repo uses).
LIVE_SPEC_URL = "https://app.getorchestra.io/api/engine/openapi.json"


@dataclass(frozen=True)
class QueryParam:
    """A query parameter the client sends for an operation."""

    name: str  # name as sent on the wire (may be camelCase, e.g. "authStatus")
    required: bool = False


@dataclass(frozen=True)
class ToolContract:
    """Links one MCP tool to the API operation it calls.

    The checker verifies ``method`` + ``path`` still exist in the spec and that each
    ``query_params`` name is still accepted (with matching required-ness). Request-body
    field conformance is intentionally out of scope for now (bodies reference deeply
    nested schemas); see ``check_api_conformance.py`` for the rationale.
    """

    tool: str  # MCP tool name as registered in server.py
    method: str  # lowercase HTTP method, e.g. "get"
    path: str  # client-relative path, may contain {templated} segments
    query_params: tuple[QueryParam, ...] = ()
    sends_body: bool = False
    # Set when the tool intentionally diverges from the public spec (e.g. an endpoint
    # that exists on the API but is not published in the public OpenAPI document).
    # ``note`` documents why; ``allow_missing_path`` keeps the check green.
    note: str | None = None
    allow_missing_path: bool = False


# ---------------------------------------------------------------------------
# Tool -> operation contracts
# ---------------------------------------------------------------------------

TOOL_CONTRACTS: tuple[ToolContract, ...] = (
    # --- Observability (reads) ---
    ToolContract(
        tool="list_pipeline_runs",
        method="get",
        path="/pipeline_runs",
        query_params=(
            QueryParam("time_from"),
            QueryParam("time_to"),
            QueryParam("status"),
            QueryParam("pipeline_run_ids"),
            QueryParam("page"),
            QueryParam("page_size"),
            QueryParam("pipeline_ids"),
            QueryParam("environments"),
        ),
    ),
    ToolContract(
        tool="list_task_runs",
        method="get",
        path="/task_runs",
        query_params=(
            QueryParam("time_from"),
            QueryParam("time_to"),
            QueryParam("status"),
            QueryParam("pipeline_ids"),
            QueryParam("integration"),
            QueryParam("task_run_ids"),
            QueryParam("page"),
            QueryParam("page_size"),
        ),
    ),
    ToolContract(
        tool="list_operations",
        method="get",
        path="/operations",
        query_params=(
            QueryParam("time_from"),
            QueryParam("time_to"),
            QueryParam("operation_type"),
            QueryParam("integration"),
            QueryParam("external_id"),
            QueryParam("task_run_id"),
            QueryParam("status"),
            QueryParam("page"),
            QueryParam("page_size"),
        ),
    ),
    ToolContract(
        tool="list_assets",
        method="get",
        path="/assets",
        query_params=(
            QueryParam("asset_type"),
            QueryParam("integration"),
            QueryParam("page"),
            QueryParam("page_size"),
        ),
    ),
    # --- Integrations ---
    ToolContract(
        tool="list_integration_connections",
        method="get",
        path="/integrations/connections",
        query_params=(
            QueryParam("integration"),
            QueryParam("authStatus"),
        ),
    ),
    # --- Pipeline lifecycle ---
    ToolContract(tool="list_pipelines", method="get", path="/pipelines"),
    ToolContract(
        tool="get_pipeline",
        method="get",
        path="/pipeline",
        query_params=(
            QueryParam("pipeline_id"),
            QueryParam("alias"),
            QueryParam("repository"),
            QueryParam("yaml_path"),
            QueryParam("version"),
            QueryParam("branch"),
            QueryParam("commit"),
        ),
    ),
    ToolContract(tool="create_pipeline", method="post", path="/pipelines", sends_body=True),
    ToolContract(
        tool="update_pipeline",
        method="put",
        path="/pipelines/{alias}",
        sends_body=True,
        allow_missing_path=True,
        note=(
            "Intentional divergence: the client PUTs /pipelines/{alias} (alias in path), "
            "which the API supports, whereas the public OpenAPI document only publishes "
            "PUT /pipelines with alias as a query param. allow_missing_path keeps the "
            "conformance check green; do not 'fix' this to match the spec."
        ),
    ),
    ToolContract(
        tool="migrate_pipeline",
        method="patch",
        path="/pipelines/storage-settings",
        query_params=(QueryParam("pipeline_id"), QueryParam("alias")),
        sends_body=True,
    ),
    ToolContract(
        tool="delete_pipeline",
        method="delete",
        path="/pipelines",
        query_params=(
            QueryParam("pipeline_id"),
            QueryParam("alias"),
            QueryParam("repository"),
            QueryParam("yaml_path"),
        ),
    ),
    ToolContract(tool="import_pipeline", method="post", path="/pipelines/import", sends_body=True),
    ToolContract(tool="validate_pipeline", method="post", path="/pipelines/schema"),
    # --- Pipeline running ---
    ToolContract(
        tool="start_pipeline",
        method="post",
        path="/pipelines/{alias_or_pipeline_id}/start",
        sends_body=True,
    ),
    ToolContract(
        tool="get_pipeline_run_status",
        method="get",
        path="/pipeline_runs/{pipeline_run_id}/status",
    ),
    ToolContract(
        tool="cancel_pipeline_run",
        method="post",
        path="/pipeline_runs/{pipeline_run_id}/cancel",
    ),
    # --- Logs and artifacts ---
    ToolContract(
        tool="list_task_run_logs",
        method="get",
        path="/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs",
    ),
    ToolContract(
        tool="download_task_run_log",
        method="get",
        path="/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/logs/download",
        query_params=(QueryParam("filename", required=True),),
    ),
    ToolContract(
        tool="list_task_run_artifacts",
        method="get",
        path="/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts",
    ),
    ToolContract(
        tool="download_task_run_artifact",
        method="get",
        path="/pipeline_runs/{pipeline_run_id}/task_runs/{task_run_id}/artifacts/download",
        query_params=(QueryParam("filename", required=True),),
    ),
    # --- Environments ---
    ToolContract(tool="list_environments", method="get", path="/environments"),
    ToolContract(
        tool="get_environment",
        method="get",
        path="/environments/{environment_id}",
    ),
    ToolContract(tool="create_environment", method="post", path="/environments", sends_body=True),
    ToolContract(
        tool="update_environment",
        method="patch",
        path="/environments/{environment_id}",
        sends_body=True,
    ),
    ToolContract(
        tool="delete_environment",
        method="delete",
        path="/environments/{environment_id}",
    ),
    ToolContract(
        tool="get_pipeline_data",
        method="get",
        path="/pipelines/data",
        query_params=(
            QueryParam("pipeline_id"),
            QueryParam("alias"),
            QueryParam("repository"),
            QueryParam("yaml_path"),
            QueryParam("version"),
            QueryParam("branch"),
            QueryParam("commit"),
        ),
    ),
)


@dataclass(frozen=True)
class EnumContract:
    """Links a ``models.py`` enum class to the OpenAPI component schema that defines it.

    The checker compares the enum's member values against the spec schema's ``enum``
    list, so newly added API values (e.g. a new pipeline-run status) surface as a PR.
    """

    model_class: str  # class name in orchestramcp.models
    spec_schema: str  # component schema name in the OpenAPI document
    # ``server.py`` docstrings enumerate the accepted values; flagged for the reviewer
    # so the PR reminds them to update the prose too.
    docstring_hint: str | None = None


ENUM_CONTRACTS: tuple[EnumContract, ...] = (
    EnumContract("PipelineRunStatus", "PipelineRunStatus"),
    EnumContract("TaskRunStatus", "TaskRunStatus"),
    EnumContract("OperationType", "OperationType"),
    EnumContract("OperationStatus", "OperationStatus"),
    EnumContract("AssetType", "AssetTypeEnum"),
)


def spec_path(client_relative_path: str) -> str:
    """Return the OpenAPI path for a client-relative contract path."""
    return f"{PUBLIC_PREFIX}{client_relative_path}"


# Names of the enum classes covered by the contract, for quick membership checks.
CONTRACTED_ENUM_CLASSES: frozenset[str] = frozenset(e.model_class for e in ENUM_CONTRACTS)
