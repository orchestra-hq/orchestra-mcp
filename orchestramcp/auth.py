"""Authentication for the Orchestra MCP server.

The server accepts two kinds of bearer credentials:

1. A raw Orchestra API key (the header-auth flow used by existing Cursor /
   Claude Code clients), validated by ``OrchestraApiKeyVerifier``.
2. An OAuth 2.1 access token (JWT) issued by an external authorization server,
   validated by FastMCP's ``JWTVerifier`` and surfaced through a
   ``RemoteAuthProvider`` so the server advertises the RFC 9728 Protected
   Resource Metadata required for the Claude Directory.

Both are composed with ``MultiAuth``: the OAuth provider owns the
``/.well-known`` routes and the ``WWW-Authenticate`` challenge, while the
API-key verifier runs as a fallback verifier. OAuth is only wired in when
``MCP_OAUTH_ISSUER``, ``MCP_OAUTH_JWKS_URI`` and ``MCP_PUBLIC_BASE_URL`` are
all set, so the server runs in API-key-only mode until the authorization
server is ready.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from urllib.parse import urlsplit, urlunsplit

import httpx
from fastmcp.server.auth import (
    AccessToken,
    AuthProvider,
    MultiAuth,
    RemoteAuthProvider,
    TokenVerifier,
)
from fastmcp.server.auth.providers.jwt import JWTVerifier

from orchestramcp.client import OrchestraClient
from orchestramcp.errors import OrchestraAPIError

logger = logging.getLogger("orchestramcp.auth")

# How long a successful API-key validation is trusted before re-probing the
# Orchestra API. Short enough that revoked keys stop working quickly.
_API_KEY_CACHE_TTL_SECONDS = 60.0

_AUTH_METHOD_CLAIM = "auth_method"
_API_KEY_CLAIM = "orchestra_api_key"

_DEFAULT_MCP_PATH = "/orchestra"


def _looks_like_jwt(token: str) -> bool:
    """A JWT is three base64url segments separated by dots."""
    return token.count(".") == 2


def _public_base() -> tuple[str, str]:
    """(origin, mount path) of the public MCP endpoint.

    ``MCP_PUBLIC_BASE_URL`` is the full URL clients connect to, e.g.
    ``https://mcp.getorchestra.io/orchestra``. The origin feeds
    ``RemoteAuthProvider.base_url`` (which must not carry a path — FastMCP
    appends the mount path itself) and the path is where the ASGI app mounts
    the MCP endpoint. Unset (local dev) yields no origin and the default path.
    """
    base = os.getenv("MCP_PUBLIC_BASE_URL", "").strip()
    if not base:
        return "", _DEFAULT_MCP_PATH
    parts = urlsplit(base)
    if not (parts.scheme and parts.netloc):
        logger.warning("MCP_PUBLIC_BASE_URL %r is not an absolute URL; ignoring it", base)
        return "", _DEFAULT_MCP_PATH
    origin = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    path = parts.path.rstrip("/") or _DEFAULT_MCP_PATH
    return origin, path


def get_mcp_path() -> str:
    """Path the MCP endpoint is mounted on (what API Gateway forwards)."""
    return _public_base()[1]


class OrchestraApiKeyVerifier(TokenVerifier):
    """Validates a raw Orchestra API key by probing the Orchestra API.

    On success the raw key is stashed in the returned token's ``claims`` so the
    tool layer can recover it to call the upstream API.
    """

    def __init__(self, base_url: str | None = None):
        super().__init__(base_url=base_url)
        # token-hash -> (expires_at_monotonic, AccessToken)
        self._cache: dict[str, tuple[float, AccessToken]] = {}

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def verify_token(self, token: str) -> AccessToken | None:
        # Defer JWT-shaped strings to the OAuth verifier and never send them
        # upstream as if they were API keys.
        if _looks_like_jwt(token):
            return None

        key = self._hash(token)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached is not None and cached[0] > now:
            return cached[1]

        if not await self._probe(token):
            self._cache.pop(key, None)
            return None

        access_token = AccessToken(
            token=token,
            client_id="orchestra-api-key",
            scopes=[],
            claims={_AUTH_METHOD_CLAIM: "api_key", _API_KEY_CLAIM: token},
        )
        self._cache[key] = (now + _API_KEY_CACHE_TTL_SECONDS, access_token)
        return access_token

    @staticmethod
    async def _probe(api_key: str) -> bool:
        """Whether the key authenticates against the Orchestra API.

        Only a definitive rejection (401/403) marks the key invalid. Any other
        upstream failure fails open: the tool call will hit the same API and
        surface the real error, whereas failing closed would turn an upstream
        outage into an auth outage.
        """
        client = OrchestraClient(api_key=api_key)
        try:
            await client.list_pipeline_runs(page=1, page_size=1)
        except OrchestraAPIError as error:
            return error.status_code not in (401, 403)
        except httpx.HTTPError:
            return True
        finally:
            await client.close()
        return True


def build_oauth_provider() -> RemoteAuthProvider | None:
    """Build the OAuth Resource Server provider from environment.

    Returns ``None`` when the OAuth environment variables are not configured,
    so the server can run in API-key-only mode.
    """
    issuer = os.getenv("MCP_OAUTH_ISSUER", "").strip()
    jwks_uri = os.getenv("MCP_OAUTH_JWKS_URI", "").strip()
    origin, path = _public_base()

    if not (issuer and jwks_uri and origin):
        if issuer or jwks_uri:
            logger.warning(
                "Partial OAuth config detected; OAuth disabled. "
                "Set MCP_OAUTH_ISSUER, MCP_OAUTH_JWKS_URI and MCP_PUBLIC_BASE_URL together."
            )
        return None

    # Tokens are minted for the full resource URL (origin + path), which is
    # also what FastMCP advertises in the protected-resource metadata.
    audience = os.getenv("MCP_OAUTH_AUDIENCE", "").strip() or origin + path

    jwt_verifier = JWTVerifier(
        jwks_uri=jwks_uri,
        issuer=issuer,
        audience=audience,
    )
    return RemoteAuthProvider(
        token_verifier=jwt_verifier,
        authorization_servers=[issuer],
        base_url=origin,
        resource_name="Orchestra MCP Server",
    )


def build_auth() -> AuthProvider:
    """Compose the server's auth provider.

    With OAuth configured: ``MultiAuth`` with the OAuth provider as the route /
    metadata owner and the API-key verifier as a fallback. Otherwise: the
    API-key verifier alone.
    """
    origin, _ = _public_base()
    api_key_verifier = OrchestraApiKeyVerifier(base_url=origin or None)

    oauth = build_oauth_provider()
    if oauth is None:
        return api_key_verifier

    return MultiAuth(server=oauth, verifiers=[api_key_verifier])


async def resolve_orchestra_credential(token: AccessToken | None) -> str:
    """Resolve the Orchestra API key to use for an upstream request.

    - No token (local stdio dev with no auth context): fall back to the
      ``ORCHESTRA_API_KEY`` environment variable.
    - API-key auth: return the raw key carried in the token claims.
    - OAuth auth: exchange the validated identity for an Orchestra credential.
    """
    if token is None:
        api_key = os.getenv("ORCHESTRA_API_KEY")
        if not api_key:
            raise ValueError("ORCHESTRA_API_KEY environment variable is required")
        return api_key

    claims = token.claims or {}
    if claims.get(_AUTH_METHOD_CLAIM) == "api_key":
        return claims[_API_KEY_CLAIM]

    return await _exchange_oauth_identity(token)


async def _exchange_oauth_identity(token: AccessToken) -> str:
    """Exchange a validated OAuth token for a scoped Orchestra API key.

    The MCP server never forwards the user's OAuth token upstream (its audience
    is this server, not the Orchestra API). Instead it calls an Orchestra
    server-to-server exchange endpoint, authenticating with its own confidential
    service credential, and receives a short-lived Orchestra API key.
    """
    exchange_url = os.getenv("ORCHESTRA_MCP_EXCHANGE_URL", "").strip()
    service_credential = os.getenv("ORCHESTRA_MCP_SERVICE_CREDENTIAL", "").strip()
    if not exchange_url or not service_credential:
        raise RuntimeError(
            "OAuth token presented but credential exchange is not configured. "
            "Set ORCHESTRA_MCP_EXCHANGE_URL and ORCHESTRA_MCP_SERVICE_CREDENTIAL."
        )

    payload = {
        "subject_token": token.token,
        "issuer": os.getenv("MCP_OAUTH_ISSUER", "").strip(),
        "audience": os.getenv("MCP_OAUTH_AUDIENCE", "").strip(),
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            exchange_url,
            headers={"Authorization": f"Bearer {service_credential}"},
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    api_key = data.get("orchestra_api_key")
    if not api_key:
        raise RuntimeError("Credential exchange did not return an orchestra_api_key")
    return api_key
