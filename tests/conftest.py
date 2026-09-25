import json
import os
from pathlib import Path

import pytest

from orchestramcp.server import get_client, get_mcp

LIVE_SPEC = str(Path(__file__).parent / "fixtures" / "openapi_live.json")
PLATFORM_SPEC = str(Path(__file__).parent / "fixtures" / "openapi_platform.json")

EXPECTED_TOOLS = {
    "cancel_pipeline_run",
    "create_environment",
    "create_incident_comment",
    "create_pipeline",
    "diagnose",
    "download_task_run_artifact",
    "download_task_run_log",
    "get_asset_by_id",
    "get_environment",
    "get_incident",
    "get_integration_state_for_state_aware",
    "get_pipeline",
    "get_pipeline_data",
    "get_pipeline_run_lineage_url",
    "get_pipeline_run_status",
    "import_pipeline",
    "list_accounts",
    "list_assets",
    "list_environments",
    "list_incident_events",
    "list_incidents",
    "list_integration_connections",
    "list_operations",
    "list_pipeline_runs",
    "list_pipelines",
    "list_task_run_artifacts",
    "list_task_run_logs",
    "list_task_runs",
    "list_task_runs_for_pipeline_run",
    "merge_incidents",
    "migrate_pipeline",
    "pipeline_context",
    "start_pipeline",
    "unmerge_incidents",
    "update_environment",
    "update_incident",
    "update_pipeline",
    "validate_pipeline",
    "whats_broken",
}

MCP_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


@pytest.fixture(autouse=True)
def orchestra_env():
    os.environ["ORCHESTRA_ENV"] = "app"
    os.environ["ORCHESTRA_OPENAPI_URL"] = LIVE_SPEC
    os.environ["ORCHESTRA_PLATFORM_OPENAPI_URL"] = PLATFORM_SPEC
    yield
    for key in (
        "ORCHESTRA_ENV",
        "ORCHESTRA_OPENAPI_URL",
        "ORCHESTRA_PLATFORM_OPENAPI_URL",
        "ORCHESTRA_API_KEY",
        "ORCHESTRA_ENABLE_DELETE",
    ):
        os.environ.pop(key, None)
    get_client.cache_clear()
    get_mcp.cache_clear()


def api_gateway_event(
    method: str = "POST",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    raw_path: str = "/orchestra",
) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} {raw_path}",
        "rawPath": raw_path,
        "rawQueryString": "",
        "headers": headers or {},
        "requestContext": {"http": {"method": method, "path": raw_path}},
        "body": body,
    }


def mcp_post_event(method: str, params: dict | None = None, api_key: str = "test-api-key") -> dict:
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {api_key}"}
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return api_gateway_event(method="POST", headers=headers, body=body)
