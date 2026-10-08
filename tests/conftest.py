import json
import os
from pathlib import Path

import pytest

from orchestramcp.server import get_client, get_mcp

LIVE_SPEC = str(Path(__file__).parent / "fixtures" / "openapi_live.json")
PLATFORM_SPEC = str(Path(__file__).parent / "fixtures" / "openapi_platform.json")
AGENTS_SPEC = str(Path(__file__).parent / "fixtures" / "openapi_agents.json")

EXPECTED_TOOLS = {
    "cancel_agent_session_prompt",
    "cancel_pipeline_run",
    "create_agent",
    "create_agent_session",
    "create_environment",
    "create_incident_comment",
    "create_pipeline",
    "create_skill",
    "diagnose",
    "download_task_run_artifact",
    "download_task_run_log",
    "get_agent",
    "get_agent_session",
    "get_agent_session_history_messages",
    "get_agent_usage",
    "get_asset_by_id",
    "get_environment",
    "get_incident",
    "get_integration_state_for_state_aware",
    "get_pipeline",
    "get_pipeline_data",
    "get_pipeline_run_lineage_url",
    "get_pipeline_run_status",
    "get_skill",
    "import_pipeline",
    "import_skill",
    "list_accounts",
    "list_agent_avatars",
    "list_agent_integrations",
    "list_agent_sessions",
    "list_agent_skills",
    "list_agents",
    "list_assets",
    "list_environments",
    "list_incident_events",
    "list_incidents",
    "list_integration_connections",
    "list_operations",
    "list_pipeline_runs",
    "list_pipelines",
    "list_skills",
    "list_task_run_artifacts",
    "list_task_run_logs",
    "list_task_runs",
    "list_task_runs_for_pipeline_run",
    "merge_incidents",
    "migrate_pipeline",
    "pipeline_context",
    "send_agent_session_message",
    "set_agent_integrations",
    "set_agent_skills",
    "start_pipeline",
    "unmerge_incidents",
    "update_agent",
    "update_environment",
    "update_incident",
    "update_pipeline",
    "update_skill",
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
    os.environ["ORCHESTRA_AGENTS_OPENAPI_URL"] = AGENTS_SPEC
    yield
    for key in (
        "ORCHESTRA_ENV",
        "ORCHESTRA_OPENAPI_URL",
        "ORCHESTRA_PLATFORM_OPENAPI_URL",
        "ORCHESTRA_AGENTS_OPENAPI_URL",
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
