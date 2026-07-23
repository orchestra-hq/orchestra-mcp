"""A local mock authorization server standing in for a real remote Orchestra
auth service, for building/testing the interactive OAuth flow end to end.

Implements discovery, dynamic client registration (RFC 7591), a real
interactive `/authorize` consent screen, `/token` (with PKCE, enforced by the
framework), a JWKS endpoint, and the identity->API-key exchange endpoint that
`orchestramcp/oauth.py` calls. Mints real RS256 JWTs (not the opaque tokens
`InMemoryOAuthProvider` normally issues) so the resource server's unmodified
JWKS/JWTVerifier path in `orchestramcp/oauth.py` is genuinely exercised.

Swapping to a real remote authorization server later is a pure env-var change
on the resource-server side (scripts/local_resource_server.py or the real
Lambda deployment) — nothing here needs to change.

Run with:

    uv run python scripts/local_authorization_server.py

Then export the printed env vars before starting scripts/local_resource_server.py.
"""

import os
import secrets
import sys
import time

import uvicorn
from fastmcp.server.auth.providers.in_memory import (
    DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS,
    InMemoryOAuthProvider,
)
from fastmcp.server.auth.providers.jwt import RSAKeyPair
from joserfc import jwk
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    construct_redirect_uri,
)
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

DEFAULT_PORT = 9700
AUDIENCE = "orchestra-mcp"
SERVICE_CREDENTIAL = "local-dev-service-credential"
DEFAULT_SUBJECT = "local-dev-user@example.com"


class MockOrchestraAuthProvider(InMemoryOAuthProvider):
    """InMemoryOAuthProvider, but mints real signed JWTs instead of opaque tokens."""

    def __init__(self, *, keypair: RSAKeyPair, issuer: str, **kwargs):
        super().__init__(**kwargs)
        self._keypair = keypair
        self._issuer = issuer
        self._pending_subjects: dict[str, str] = {}

    def stage_subject(self, code_challenge: str, subject: str) -> None:
        self._pending_subjects[code_challenge] = subject

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        # Same shape as InMemoryOAuthProvider.authorize, but records which
        # subject the consent screen approved on the resulting AuthorizationCode.
        if client.client_id not in self.clients:
            raise AuthorizeError(
                error="unauthorized_client",
                error_description=f"Client '{client.client_id}' not registered.",
            )

        subject = self._pending_subjects.pop(params.code_challenge, DEFAULT_SUBJECT)

        auth_code_value = f"local_auth_code_{secrets.token_hex(16)}"
        expires_at = time.time() + 5 * 60

        scopes_list = params.scopes if params.scopes is not None else []
        if client.scope:
            allowed = set(client.scope.split())
            scopes_list = [s for s in scopes_list if s in allowed]

        auth_code = AuthorizationCode(
            code=auth_code_value,
            client_id=client.client_id,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            scopes=scopes_list,
            expires_at=expires_at,
            code_challenge=params.code_challenge,
            subject=subject,
        )
        self.auth_codes[auth_code_value] = auth_code

        return construct_redirect_uri(
            str(params.redirect_uri), code=auth_code_value, state=params.state
        )

    async def exchange_authorization_code(self, client, authorization_code):
        oauth_token = await super().exchange_authorization_code(client, authorization_code)

        opaque_access = oauth_token.access_token
        access_obj = self.access_tokens.pop(opaque_access)
        subject = authorization_code.subject or DEFAULT_SUBJECT

        jwt_access = self._keypair.create_token(
            subject=subject,
            issuer=self._issuer,
            audience=AUDIENCE,
            scopes=access_obj.scopes,
            expires_in_seconds=DEFAULT_ACCESS_TOKEN_EXPIRY_SECONDS,
        )
        self.access_tokens[jwt_access] = access_obj.model_copy(
            update={"token": jwt_access, "subject": subject}
        )

        opaque_refresh = oauth_token.refresh_token
        if opaque_refresh:
            self._access_to_refresh_map.pop(opaque_access, None)
            self._access_to_refresh_map[jwt_access] = opaque_refresh
            self._refresh_to_access_map[opaque_refresh] = jwt_access

        return oauth_token.model_copy(update={"access_token": jwt_access})


def _consent_html(params: dict[str, str], client_id: str) -> str:
    hidden_fields = "\n".join(
        f'<input type="hidden" name="{key}" value="{value}">'
        for key, value in params.items()
        if value is not None
    )
    return f"""
    <html>
    <head><title>Approve access</title></head>
    <body style="font-family: sans-serif; max-width: 480px; margin: 4rem auto;">
      <h2>Local mock Orchestra login</h2>
      <p><b>{client_id}</b> is requesting access to your Orchestra data.</p>
      <form method="POST" action="/authorize">
        {hidden_fields}
        <label>
          Subject (simulated logged-in user):<br>
          <input type="text" name="subject" value="{DEFAULT_SUBJECT}" style="width: 100%;">
        </label>
        <div style="margin-top: 1.5rem;">
          <button type="submit" name="action" value="approve">Approve</button>
          <button type="submit" name="action" value="deny">Deny</button>
        </div>
      </form>
    </body>
    </html>
    """


async def authorize_get(request: Request) -> Response:
    query = request.query_params
    client_id = query.get("client_id")
    client = await request.app.state.provider.get_client(client_id) if client_id else None
    if client is None:
        return JSONResponse(
            {"error": "invalid_request", "error_description": "Unknown client_id"}, status_code=400
        )

    params = {
        "client_id": query.get("client_id"),
        "redirect_uri": query.get("redirect_uri"),
        "response_type": query.get("response_type"),
        "code_challenge": query.get("code_challenge"),
        "code_challenge_method": query.get("code_challenge_method"),
        "state": query.get("state"),
        "scope": query.get("scope"),
        "resource": query.get("resource"),
    }
    return HTMLResponse(_consent_html(params, client_id))


async def authorize_post(request: Request) -> Response:
    from mcp.server.auth.handlers.authorize import AuthorizationHandler

    provider: MockOrchestraAuthProvider = request.app.state.provider
    form = await request.form()

    if form.get("action") != "approve":
        redirect_uri = form.get("redirect_uri")
        state = form.get("state")
        url = construct_redirect_uri(
            str(redirect_uri),
            error="access_denied",
            error_description="User denied the request",
            **({"state": state} if state else {}),
        )
        return RedirectResponse(url, status_code=302)

    provider.stage_subject(form.get("code_challenge"), form.get("subject") or DEFAULT_SUBJECT)
    return await AuthorizationHandler(provider).handle(request)


async def jwks(request: Request) -> Response:
    return JSONResponse({"keys": [request.app.state.public_jwk]})


async def exchange(request: Request) -> Response:
    if request.headers.get("Authorization") != f"Bearer {SERVICE_CREDENTIAL}":
        return JSONResponse({"message": "bad service credential"}, status_code=401)

    payload = await request.json()
    api_key = os.getenv("ORCHESTRA_TEST_API_KEY", "").strip()
    print(f"  [exchange] resolving subject={payload.get('subject')!r} -> api_key")
    return JSONResponse({"api_key": api_key})


def _build_app(provider: MockOrchestraAuthProvider, issuer: str, public_jwk: dict) -> Starlette:
    routes = create_auth_routes(
        provider,
        issuer_url=AnyHttpUrl(issuer),
        client_registration_options=ClientRegistrationOptions(enabled=True),
    )
    routes = [route for route in routes if route.path != "/authorize"]
    routes += [
        Route("/authorize", authorize_get, methods=["GET"]),
        Route("/authorize", authorize_post, methods=["POST"]),
        Route("/jwks.json", jwks, methods=["GET"]),
        Route("/exchange", exchange, methods=["POST"]),
    ]

    app = Starlette(routes=routes)
    app.state.provider = provider
    app.state.public_jwk = public_jwk
    return app


def main() -> None:
    if not os.getenv("ORCHESTRA_TEST_API_KEY", "").strip():
        print("ORCHESTRA_TEST_API_KEY must be set to a real Orchestra API key.", file=sys.stderr)
        raise SystemExit(1)

    port = int(os.getenv("ORCHESTRA_LOCAL_AUTH_SERVER_PORT", DEFAULT_PORT))
    public_url = os.getenv("ORCHESTRA_LOCAL_AUTH_SERVER_PUBLIC_URL", "").strip()
    # Normalize through AnyHttpUrl so this matches exactly what the AS metadata
    # document (built internally by create_auth_routes) declares as `issuer`
    # (it adds a trailing slash) — the JWT `iss` claim and ORCHESTRA_OAUTH_ISSUER
    # must agree with that value byte-for-byte. When fronted by a tunnel (e.g.
    # ngrok, required for Claude Desktop's HTTPS-only connector requirement),
    # ORCHESTRA_LOCAL_AUTH_SERVER_PUBLIC_URL lets this advertise the tunnel's
    # HTTPS URL while still binding the socket to localhost below.
    issuer = str(AnyHttpUrl(public_url or f"http://127.0.0.1:{port}"))

    keypair = RSAKeyPair.generate()
    public_jwk = jwk.import_key(keypair.public_key, "RSA").as_dict()
    provider = MockOrchestraAuthProvider(keypair=keypair, issuer=issuer, base_url=issuer)

    app = _build_app(provider, issuer, public_jwk)

    base = issuer.rstrip("/")
    print(f"Mock authorization server: {issuer}")
    print()
    print("Export these before starting scripts/local_resource_server.py:")
    print()
    print(f'  export ORCHESTRA_OAUTH_JWKS_URI="{base}/jwks.json"')
    print(f'  export ORCHESTRA_OAUTH_ISSUER="{issuer}"')
    print(f'  export ORCHESTRA_OAUTH_AUDIENCE="{AUDIENCE}"')
    print(f'  export ORCHESTRA_MCP_EXCHANGE_URL="{base}/exchange"')
    print(f'  export ORCHESTRA_MCP_SERVICE_CREDENTIAL="{SERVICE_CREDENTIAL}"')
    print()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
