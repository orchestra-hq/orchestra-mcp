"""Front the real, unmodified orchestramcp.lambda_handler.handler() with a real
bound HTTP socket, so an actual MCP client (e.g. Claude Desktop) can connect to
it over http://localhost instead of API Gateway.

This script sets no OAuth env vars itself — export the ones printed by
scripts/local_authorization_server.py (or, later, point them at a real remote
authorization server) before starting this.

Claude Desktop requires an HTTPS connector URL, and a free tunnel account
(e.g. ngrok) typically only gets one public hostname. Since this server's own
routes (/orchestra, /.well-known/oauth-protected-resource/orchestra) never
collide with the mock auth server's (/authorize, /token, /jwks.json, /register,
/.well-known/oauth-authorization-server, /exchange), set
ORCHESTRA_LOCAL_AUTH_SERVER_PROXY_TARGET to transparently proxy every
non-resource-server path to the local auth server, so both can share a single
tunnel/hostname.

Run with:

    ORCHESTRA_ENV=stage ORCHESTRA_OAUTH_RESOURCE_URL=http://127.0.0.1:8788/orchestra \\
        uv run python scripts/local_resource_server.py
"""

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlparse

import httpx

from scripts._lambda_event_shim import build_api_gateway_event_v2, lambda_response_to_http

DEFAULT_PORT = 8788
_HOP_BY_HOP_HEADERS = {"host", "content-length", "connection", "transfer-encoding"}


def _proxy_target() -> str | None:
    return os.getenv("ORCHESTRA_LOCAL_AUTH_SERVER_PROXY_TARGET", "").strip() or None


def _is_own_path(path: str) -> bool:
    return path == "/orchestra" or path.startswith("/.well-known/oauth-protected-resource")


def _proxy(method: str, target_base: str, path: str, query: str, headers: dict, body: bytes | None):
    url = f"{target_base.rstrip('/')}{path}"
    if query:
        url += f"?{query}"
    forward_headers = {k: v for k, v in headers.items() if k.lower() not in _HOP_BY_HOP_HEADERS}
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        response = client.request(method, url, headers=forward_headers, content=body)
    return response.status_code, dict(response.headers), response.content


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None

        proxy_target = _proxy_target()
        if proxy_target and not _is_own_path(parsed.path):
            status_code, headers, response_body = _proxy(
                method, proxy_target, parsed.path, parsed.query, dict(self.headers), body
            )
        else:
            from orchestramcp.lambda_handler import handler

            event = build_api_gateway_event_v2(
                method, parsed.path, parsed.query, dict(self.headers), body
            )
            context = SimpleNamespace(aws_request_id="local-dev")
            response = handler(event, context)
            status_code, headers, response_body = lambda_response_to_http(response)

        self.send_response(status_code)
        for key, value in headers.items():
            if key.lower() in _HOP_BY_HOP_HEADERS:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_OPTIONS(self):
        self._handle("OPTIONS")


def main() -> None:
    if not os.getenv("ORCHESTRA_ENV", "").strip():
        print("ORCHESTRA_ENV must be set (e.g. stage).", file=sys.stderr)
        raise SystemExit(1)

    port = int(os.getenv("ORCHESTRA_LOCAL_RESOURCE_SERVER_PORT", DEFAULT_PORT))
    server = ThreadingHTTPServer(("127.0.0.1", port), _Handler)

    resource_url = os.getenv("ORCHESTRA_OAUTH_RESOURCE_URL", "").strip()
    print(f"Resource server: http://127.0.0.1:{port}/orchestra")
    if resource_url:
        print(f"  advertising resource: {resource_url}")
    else:
        print(
            "  ORCHESTRA_OAUTH_RESOURCE_URL is not set — OAuth discovery is disabled; "
            "raw Orchestra API keys will be accepted as bearer tokens."
        )
    proxy_target = _proxy_target()
    if proxy_target:
        print(f"  proxying all non-resource-server paths to: {proxy_target}")
    print("Add this URL as a custom connector in Claude Desktop. Ctrl-C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
