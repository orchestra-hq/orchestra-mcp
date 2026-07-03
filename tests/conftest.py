import json
import os
from pathlib import Path

import pytest

from orchestramcp.server import get_client, get_mcp

LIVE_SPEC = str(Path(__file__).parent / "fixtures" / "openapi_live.json")

EXPECTED_TOOLS = {
    "cancel_pipeline_run",
    "create_environment",
    "create_pipeline",
    "download_task_run_artifact",
    "download_task_run_log",
    "get_environment",
    "get_pipeline",
    "get_pipeline_run_lineage_url",
    "get_pipeline_run_status",
    "import_pipeline",
    "list_assets",
    "list_environments",
    "list_integration_connections",
    "list_operations",
    "list_pipeline_runs",
    "list_pipelines",
    "list_task_run_artifacts",
    "list_task_run_logs",
    "list_task_runs",
    "migrate_pipeline",
    "start_pipeline",
    "update_environment",
    "update_pipeline",
    "validate_pipeline",
}

MCP_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}


@pytest.fixture(autouse=True)
def orchestra_env():
    os.environ["ORCHESTRA_ENV"] = "app"
    os.environ["ORCHESTRA_OPENAPI_URL"] = LIVE_SPEC
    yield
    for key in (
        "ORCHESTRA_ENV",
        "ORCHESTRA_OPENAPI_URL",
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
) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} /orchestra",
        "rawPath": "/orchestra",
        "rawQueryString": "",
        "headers": headers or {},
        "requestContext": {"http": {"method": method, "path": "/orchestra"}},
        "body": body,
    }


def mcp_post_event(method: str, params: dict | None = None, api_key: str = "test-api-key") -> dict:
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {api_key}"}
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return api_gateway_event(method="POST", headers=headers, body=body)
