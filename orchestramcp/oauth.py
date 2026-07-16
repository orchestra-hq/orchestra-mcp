"""OAuth 2.1 bearer-token resolution for the Lambda entrypoint.

FastMCP never runs its own ASGI/HTTP transport here (see lambda_handler.py /
in_process_request_handler.py), so FastMCP's `auth=` construct has nowhere to
attach. Instead this module verifies the bearer token directly and, if it's an
OAuth access token rather than a raw Orchestra API key, exchanges it for one.
`lambda_handler.py` calls `resolve_api_key()` in place of using the bearer
token as the API key verbatim.

Deliberately inert by default: without ORCHESTRA_OAUTH_JWKS_URI configured,
every token is treated as a raw Orchestra API key, matching today's behaviour.
"""

import os
from functools import lru_cache

import httpx
from fastmcp.server.auth.providers.jwt import JWTVerifier

_EXCHANGE_TIMEOUT_SECONDS = 10.0


class OAuthConfigError(ValueError):
    """The OAuth environment variables are missing or inconsistent."""


class OAuthTokenError(ValueError):
    """The bearer token failed OAuth verification or exchange."""


def _looks_like_jwt(token: str) -> bool:
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


def oauth_enabled() -> bool:
    return bool(os.getenv("ORCHESTRA_OAUTH_JWKS_URI", "").strip())


@lru_cache
def _verifier() -> JWTVerifier:
    jwks_uri = os.getenv("ORCHESTRA_OAUTH_JWKS_URI", "").strip()
    if not jwks_uri:
        raise OAuthConfigError("Missing ORCHESTRA_OAUTH_JWKS_URI environment variable")

    issuer = os.getenv("ORCHESTRA_OAUTH_ISSUER", "").strip() or None
    audience = os.getenv("ORCHESTRA_OAUTH_AUDIENCE", "").strip() or None
    return JWTVerifier(jwks_uri=jwks_uri, issuer=issuer, audience=audience)


def _exchange_url() -> str:
    url = os.getenv("ORCHESTRA_MCP_EXCHANGE_URL", "").strip()
    if not url:
        raise OAuthConfigError("Missing ORCHESTRA_MCP_EXCHANGE_URL environment variable")
    return url


def _service_credential() -> str:
    credential = os.getenv("ORCHESTRA_MCP_SERVICE_CREDENTIAL", "").strip()
    if not credential:
        raise OAuthConfigError("Missing ORCHESTRA_MCP_SERVICE_CREDENTIAL environment variable")
    return credential


async def _exchange_for_api_key(subject: str, claims: dict) -> str:
    """Exchange a verified OAuth identity for a real Orchestra API key.

    Talks to the identity->API-key exchange endpoint that is still a backend
    TODO (see PR #17 notes) — this is the shape the client side expects once
    that endpoint exists, not yet a working integration end-to-end.
    """
    async with httpx.AsyncClient(timeout=_EXCHANGE_TIMEOUT_SECONDS) as client:
        response = await client.post(
            _exchange_url(),
            headers={"Authorization": f"Bearer {_service_credential()}"},
            json={"subject": subject, "claims": claims},
        )
        if response.is_error:
            raise OAuthTokenError(f"Identity exchange failed: HTTP {response.status_code}")
        api_key = response.json().get("api_key")
        if not api_key:
            raise OAuthTokenError("Identity exchange response missing api_key")
        return api_key


async def resolve_api_key(bearer_token: str) -> str:
    """Resolve an incoming bearer token to the Orchestra API key to use.

    Raw Orchestra API keys pass through unchanged (today's behaviour, and the
    permanent path for direct/stdio clients). A JWT-shaped token is only
    treated as OAuth if ORCHESTRA_OAUTH_JWKS_URI is configured; otherwise it
    falls through to passthrough too, so leaving OAuth unconfigured is a no-op
    change from the current deployment.
    """
    if not oauth_enabled() or not _looks_like_jwt(bearer_token):
        return bearer_token

    access_token = await _verifier().verify_token(bearer_token)
    if access_token is None:
        raise OAuthTokenError("OAuth token failed verification")

    subject = access_token.subject or access_token.client_id
    return await _exchange_for_api_key(subject, access_token.claims or {})
