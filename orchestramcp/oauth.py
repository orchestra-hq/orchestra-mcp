"""OAuth 2.1 resource-server behaviour for the Lambda entrypoint.

FastMCP never runs its own HTTP transport here and mcp_lambda's API Gateway
handler ignores the request path, so neither can serve RFC 9728 discovery or
challenge an unauthenticated caller; lambda_handler.py dispatches here first.
Inert unless all three ORCHESTRA_OAUTH_* variables are set, leaving every bearer
token treated as a raw Orchestra API key.
"""

import json
import os
from functools import lru_cache
from typing import Any

from fastmcp.server.auth.providers.jwt import JWTVerifier
from mcp.shared.auth import ProtectedResourceMetadata
from pydantic import AnyHttpUrl

# RFC 9728 serves this at the origin root, which never reaches a Lambda routed one prefix.
_METADATA_PATH_SUFFIX = "/.well-known/oauth-protected-resource"

_RESOURCE_NAME = "Orchestra MCP Server"


class OAuthTokenError(ValueError):
    """The bearer token failed OAuth verification."""


def _setting(name: str) -> str:
    return os.getenv(name, "").strip()


def _issuer() -> str:
    return _setting("ORCHESTRA_OAUTH_ISSUER")


def _jwks_uri() -> str:
    return _setting("ORCHESTRA_OAUTH_JWKS_URI")


def _resource_url() -> str:
    """The MCP URL exactly as users type it into a client, and the audience tokens carry."""
    return _setting("ORCHESTRA_OAUTH_RESOURCE_URL").rstrip("/")


def _resource_metadata_url() -> str:
    return f"{_resource_url()}{_METADATA_PATH_SUFFIX}"


def enabled() -> bool:
    return bool(_issuer() and _jwks_uri() and _resource_url())


def _looks_like_jwt(token: str) -> bool:
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


@lru_cache
def _verifier(jwks_uri: str, issuer: str, audience: str) -> JWTVerifier:
    return JWTVerifier(jwks_uri=jwks_uri, issuer=issuer, audience=audience)


async def verify_token(token: str) -> None:
    """Raise OAuthTokenError unless the token may be forwarded to the Orchestra API.

    Raw Orchestra API keys are not JWTs and pass through untouched.
    """
    if not enabled() or not _looks_like_jwt(token):
        return

    verifier = _verifier(_jwks_uri(), _issuer(), _resource_url())
    if await verifier.verify_token(token) is None:
        raise OAuthTokenError("OAuth token failed verification")


def www_authenticate_header(error: str, description: str) -> str | None:
    """None when OAuth is unconfigured, rather than advertising a document we do not serve."""
    if not enabled():
        return None
    return (
        f'Bearer error="{error}", error_description="{description}", '
        f'resource_metadata="{_resource_metadata_url()}"'
    )


def _protected_resource_metadata() -> dict[str, Any]:
    metadata = ProtectedResourceMetadata(
        resource=AnyHttpUrl(_resource_url()),
        authorization_servers=[AnyHttpUrl(_issuer())],
        resource_name=_RESOURCE_NAME,
    )
    payload = metadata.model_dump(mode="json", exclude_none=True)
    # Only the first entry is tried, and pydantic would give it a trailing slash to mismatch on.
    payload["authorization_servers"] = [_issuer()]
    return payload


def handle_discovery_request(method: str, raw_path: str) -> dict[str, Any] | None:
    """Serve the discovery document, or return None to fall through to MCP handling."""
    # Matched on the suffix because the routed prefix may or may not reach the Lambda.
    if not enabled() or not raw_path.endswith(_METADATA_PATH_SUFFIX):
        return None

    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "access-control-allow-origin": "*",
                "access-control-allow-methods": "GET, OPTIONS",
                "access-control-allow-headers": "*",
            },
            "body": "",
        }

    if method != "GET":
        return None

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json", "access-control-allow-origin": "*"},
        "body": json.dumps(_protected_resource_metadata()),
    }
