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

from orchestramcp.openapi_server import SERVER_NAME

# RFC 9728 serves this at the origin root, which a Lambda routed one path prefix never sees.
_METADATA_PATH_SUFFIX = "/.well-known/oauth-protected-resource"


def _setting(name: str) -> str:
    return os.getenv(name, "").strip()


def _issuer() -> str:
    return _setting("ORCHESTRA_OAUTH_ISSUER")


def _jwks_uri() -> str:
    return _setting("ORCHESTRA_OAUTH_JWKS_URI")


def _resource_url() -> str:
    """The MCP URL exactly as users type it into a client, and the audience tokens carry."""
    return _setting("ORCHESTRA_OAUTH_RESOURCE_URL")


def _resource_metadata_url() -> str:
    return f"{_resource_url().rstrip('/')}{_METADATA_PATH_SUFFIX}"


def enabled() -> bool:
    return bool(_issuer() and _jwks_uri() and _resource_url())


def _looks_like_jwt(token: str) -> bool:
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


@lru_cache
def _verifier(jwks_uri: str, issuer: str, audience: str) -> JWTVerifier:
    return JWTVerifier(jwks_uri=jwks_uri, issuer=issuer, audience=audience)


async def token_accepted(token: str) -> bool:
    """Whether the token may be forwarded to the Orchestra API.

    Raw Orchestra API keys are not JWTs and pass through untouched.
    """
    if not enabled() or not _looks_like_jwt(token):
        return True

    verifier = _verifier(_jwks_uri(), _issuer(), _resource_url())
    return await verifier.verify_token(token) is not None


def www_authenticate_header(error: str, description: str) -> str | None:
    """None when OAuth is unconfigured, rather than advertising a document we do not serve."""
    if not enabled():
        return None
    return (
        f'Bearer error="{error}", error_description="{description}", '
        f'resource_metadata="{_resource_metadata_url()}"'
    )


def _protected_resource_metadata() -> dict[str, Any]:
    # Hand-built: a URL model would normalise these two, and clients compare them literally.
    return {
        "resource": _resource_url(),
        "authorization_servers": [_issuer()],
        "bearer_methods_supported": ["header"],
        "resource_name": SERVER_NAME,
    }


def handle_discovery_request(method: str, raw_path: str) -> dict[str, Any] | None:
    """Serve the discovery document, or return None to fall through to MCP handling."""
    # Matched on the suffix because the routed prefix may or may not reach the Lambda.
    if not enabled() or not raw_path.endswith(_METADATA_PATH_SUFFIX):
        return None

    # OPTIONS falls through too: mcp_lambda answers every preflight with permissive CORS.
    if method != "GET":
        return None

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json", "access-control-allow-origin": "*"},
        "body": json.dumps(_protected_resource_metadata()),
    }
