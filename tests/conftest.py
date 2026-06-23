import json
import os

import pytest

EXPECTED_TOOLS = {
    "cancel_pipeline_run",
    "download_task_run_artifact",
    "download_task_run_log",
    "get_pipeline_run_status",
    "get_pipeline",
    "import_pipeline",
    "list_assets",
    "list_operations",
    "list_pipeline_runs",
    "list_pipelines",
    "list_task_run_artifacts",
    "list_task_run_logs",
    "list_task_runs",
    "migrate_pipeline",
    "start_pipeline",
    "update_pipeline",
}

MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


@pytest.fixture(autouse=True)
def orchestra_env():
    os.environ["ORCHESTRA_ENV"] = "app"
    yield
    os.environ.pop("ORCHESTRA_ENV", None)
    os.environ.pop("ORCHESTRA_API_KEY", None)


def api_gateway_event(
    method: str = "POST",
    path: str = "/orchestra",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict:
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": headers or {},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
            },
            "stage": "$default",
        },
        "body": body,
        "isBase64Encoded": False,
    }


def mcp_post_event(method: str, params: dict | None = None, api_key: str = "test-api-key") -> dict:
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {api_key}"}
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }
    )
    return api_gateway_event(method="POST", headers=headers, body=body)
