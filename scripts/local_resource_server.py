"""Front the real, unmodified lambda_handler.handler() with a bound HTTP socket.

The Lambda is only ever called with API Gateway v2 events, so there is nothing an
MCP client can connect to locally. This translates real requests into that event
shape and back, which is enough for Claude Code to run the whole OAuth flow —
discovery, consent, then tool calls — against the production code path.

Point it at a deployed authorization server and run it with:

    ORCHESTRA_ENV=dev \\
    ORCHESTRA_OAUTH_ISSUER=https://dev.getorchestra.io \\
    ORCHESTRA_OAUTH_JWKS_URI=https://dev.getorchestra.io/oauth/jwks.json \\
    ORCHESTRA_OAUTH_RESOURCE_URL=https://mcp-dev.getorchestra.io/orchestra \\
        uv run python scripts/local_resource_server.py

The resource URL has to be one auth-srv is configured to serve and one the Orchestra
API accepts as an audience, which is why it names the deployed environment rather than
this socket — see the README for what that costs.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from urllib.parse import urlparse

from orchestramcp.lambda_handler import handler

DEFAULT_PORT = 8788


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"  {self.command} {self.path} -> {args[1]}")

    def _handle(self, method: str) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else None

        response = handler(
            {
                "version": "2.0",
                "routeKey": f"{method} {parsed.path}",
                "rawPath": parsed.path,
                "rawQueryString": parsed.query,
                "headers": dict(self.headers),
                "requestContext": {"http": {"method": method, "path": parsed.path}},
                "body": body.decode() if body else None,
            },
            SimpleNamespace(aws_request_id="local-dev"),
        )
        payload = (response.get("body") or "").encode()

        self.send_response(response.get("statusCode", 200))
        for key, value in (response.get("headers") or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_OPTIONS(self):
        self._handle("OPTIONS")

    def do_DELETE(self):
        self._handle("DELETE")


def main() -> None:
    if not os.getenv("ORCHESTRA_ENV", "").strip():
        print("ORCHESTRA_ENV must be set (e.g. dev).", file=sys.stderr)
        raise SystemExit(1)

    port = int(os.getenv("ORCHESTRA_LOCAL_RESOURCE_SERVER_PORT", DEFAULT_PORT))
    resource_url = os.getenv("ORCHESTRA_OAUTH_RESOURCE_URL", "").strip()

    print(f"Serving http://127.0.0.1:{port}/orchestra against {os.environ['ORCHESTRA_ENV']}")
    if resource_url:
        print(f"  advertising resource: {resource_url}")
    else:
        print("  no OAuth config — bearer tokens are treated as raw Orchestra API keys")
    print("Ctrl-C to stop.\n")

    try:
        # Single-threaded on purpose: the handler passes credentials through the process
        # environment, which is only safe because a Lambda container serves one request
        # at a time. Overlapping requests here would swap one caller's token for another's.
        HTTPServer(("127.0.0.1", port), _Handler).serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
