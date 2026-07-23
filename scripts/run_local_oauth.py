"""Exercise the OAuth bearer-token path end to end against a local mock IdP.

Stands up two throwaway local HTTP servers — one serving a JWKS document,
one acting as the identity->API-key exchange endpoint — mints a JWT signed
against the JWKS, then drives orchestramcp.lambda_handler.handler() exactly
as API Gateway would, with that JWT as the bearer token. This proves the
real JWTVerifier fetch-and-verify path and the real exchange HTTP call both
work; it does not exercise a real authorization server or login flow.

Requires a real Orchestra API key for ORCHESTRA_ENV (stage by default) so
the resulting tool calls hit real data — the mock exchange endpoint hands
this back in place of a real identity exchange.

Run with:

    ORCHESTRA_TEST_API_KEY=<a real stage api key> uv run python scripts/run_local_oauth.py
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from fastmcp.server.auth.providers.jwt import RSAKeyPair
from joserfc import jwk

from scripts._lambda_event_shim import build_api_gateway_event_v2

ISSUER = "https://local-mock-idp.test"
AUDIENCE = "orchestra-mcp"
SERVICE_CREDENTIAL = "local-dev-service-credential"


def _serve_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _start_server(handler_cls: type[BaseHTTPRequestHandler]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _start_jwks_server(public_jwk: dict) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            _serve_json(self, 200, {"keys": [public_jwk]})

    return _start_server(Handler)


def _start_exchange_server(api_key: str) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.headers.get("Authorization") != f"Bearer {SERVICE_CREDENTIAL}":
                _serve_json(self, 401, {"message": "bad service credential"})
                return
            length = int(self.headers.get("Content-Length", 0))
            request = json.loads(self.rfile.read(length) or b"{}")
            print(f"  [exchange] resolving subject={request.get('subject')!r} -> api_key")
            _serve_json(self, 200, {"api_key": api_key})

    return _start_server(Handler)


def _call(handler, method: str, params: dict | None, bearer_token: str) -> dict:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer_token}",
    }
    event = build_api_gateway_event_v2("POST", "/orchestra", "", headers, body.encode())
    context = SimpleNamespace(aws_request_id="local-dev")
    response = handler(event, context)
    return json.loads(response["body"])


def main() -> None:
    api_key = os.getenv("ORCHESTRA_TEST_API_KEY", "").strip()
    if not api_key:
        print("ORCHESTRA_TEST_API_KEY must be set to a real Orchestra API key.", file=sys.stderr)
        raise SystemExit(1)

    keypair = RSAKeyPair.generate()
    public_jwk = jwk.import_key(keypair.public_key, "RSA").as_dict()

    jwks_server = _start_jwks_server(public_jwk)
    exchange_server = _start_exchange_server(api_key)
    print(f"JWKS server:     http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json")
    print(f"Exchange server: http://127.0.0.1:{exchange_server.server_address[1]}/exchange")

    os.environ["ORCHESTRA_ENV"] = os.getenv("ORCHESTRA_ENV", "stage")
    os.environ["ORCHESTRA_OAUTH_JWKS_URI"] = (
        f"http://127.0.0.1:{jwks_server.server_address[1]}/jwks.json"
    )
    os.environ["ORCHESTRA_OAUTH_ISSUER"] = ISSUER
    os.environ["ORCHESTRA_OAUTH_AUDIENCE"] = AUDIENCE
    os.environ["ORCHESTRA_MCP_EXCHANGE_URL"] = (
        f"http://127.0.0.1:{exchange_server.server_address[1]}/exchange"
    )
    os.environ["ORCHESTRA_MCP_SERVICE_CREDENTIAL"] = SERVICE_CREDENTIAL

    token = keypair.create_token(subject="local-dev-user", issuer=ISSUER, audience=AUDIENCE)

    from orchestramcp.lambda_handler import handler

    print("\n> initialize")
    print(json.dumps(_call(handler, "initialize", _initialize_params(), token), indent=2))

    print("\n> tools/list")
    tools_result = _call(handler, "tools/list", None, token)
    tool_names = [tool["name"] for tool in tools_result.get("result", {}).get("tools", [])]
    print(f"resolved {len(tool_names)} tools: {tool_names}")

    jwks_server.shutdown()
    exchange_server.shutdown()


def _initialize_params() -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "local-oauth-smoke-test", "version": "1.0"},
    }


if __name__ == "__main__":
    main()
