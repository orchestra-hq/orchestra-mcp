"""OAuth protected-resource discovery for the Lambda entrypoint.

`mcp_lambda`'s API Gateway handler ignores the request path entirely (it always
405s a GET before any path-aware logic runs), so it can never serve
`/.well-known/oauth-protected-resource`. This module builds that discovery
document and the matching `WWW-Authenticate` header directly, and
`lambda_handler.py` dispatches to it before falling through to the normal
MCP request handling.

Deliberately inert unless `ORCHESTRA_OAUTH_JWKS_URI`, `ORCHESTRA_OAUTH_ISSUER`,
and `ORCHESTRA_OAUTH_RESOURCE_URL` are all set — matching `oauth.py`'s
"no OAuth configured, no behaviour change" invariant.
"""

import json
import os
from typing import Any
from urllib.parse import urlparse

from mcp.server.auth.routes import build_resource_metadata_url
from mcp.shared.auth import ProtectedResourceMetadata
from pydantic import AnyHttpUrl

from orchestramcp.oauth import oauth_enabled

_RESOURCE_NAME = "Orchestra MCP Server"


def _resource_url() -> str | None:
    return os.getenv("ORCHESTRA_OAUTH_RESOURCE_URL", "").strip() or None


def _issuer() -> str | None:
    return os.getenv("ORCHESTRA_OAUTH_ISSUER", "").strip() or None


def discovery_enabled() -> bool:
    return bool(oauth_enabled() and _resource_url() and _issuer())


def resource_metadata_url() -> str | None:
    if not discovery_enabled():
        return None
    return str(build_resource_metadata_url(AnyHttpUrl(_resource_url())))


def build_protected_resource_metadata() -> dict[str, Any]:
    metadata = ProtectedResourceMetadata(
        resource=AnyHttpUrl(_resource_url()),
        authorization_servers=[AnyHttpUrl(_issuer())],
        resource_name=_RESOURCE_NAME,
    )
    return metadata.model_dump(mode="json", exclude_none=True)


def www_authenticate_header(error: str, description: str) -> str | None:
    if not discovery_enabled():
        return None
    return (
        f'Bearer error="{error}", error_description="{description}", '
        f'resource_metadata="{resource_metadata_url()}"'
    )


def _discovery_path() -> str | None:
    url = resource_metadata_url()
    if url is None:
        return None
    return urlparse(url).path


def handle_discovery_request(method: str, raw_path: str) -> dict[str, Any] | None:
    if not discovery_enabled() or raw_path != _discovery_path():
        return None

    if method == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "content-type": "application/json",
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
        "body": json.dumps(build_protected_resource_metadata()),
    }
