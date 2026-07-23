"""Translate real HTTP requests/responses to and from API Gateway v2 event shape.

Shared by scripts/run_local_oauth.py (drives lambda_handler.handler() in-process
with a hand-built event) and scripts/local_resource_server.py (fronts the same
handler with a real bound HTTP socket) so both exercise the exact same
production Lambda code, just via different entrypoints.
"""

from typing import Any


def build_api_gateway_event_v2(
    method: str,
    path: str,
    query_string: str,
    headers: dict[str, str],
    body: bytes | None,
) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": query_string,
        "headers": headers,
        "requestContext": {"http": {"method": method, "path": path}},
        "body": body.decode() if body else None,
    }


def lambda_response_to_http(response: dict[str, Any]) -> tuple[int, dict[str, str], bytes]:
    status_code = response.get("statusCode", 200)
    headers = dict(response.get("headers") or {})
    body = response.get("body") or ""
    return status_code, headers, body.encode()
