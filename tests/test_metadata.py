import httpx
import pytest
from fastmcp import FastMCP

from orchestramcp.auth import build_auth, get_mcp_path

OAUTH_ENV = {
    "MCP_OAUTH_ISSUER": "https://auth.example.com",
    "MCP_OAUTH_JWKS_URI": "https://auth.example.com/.well-known/jwks.json",
    "MCP_PUBLIC_BASE_URL": "https://mcp.getorchestra.io/orchestra",
}

_AUTH_ENV_KEYS = (
    "MCP_OAUTH_ISSUER",
    "MCP_OAUTH_JWKS_URI",
    "MCP_PUBLIC_BASE_URL",
    "MCP_OAUTH_AUDIENCE",
    "MCP_PATH",
)

MCP_REQUEST = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


def _build_app():
    mcp = FastMCP("Orchestra MCP Server", auth=build_auth())
    return mcp.http_app(path=get_mcp_path(), transport="http", stateless_http=True)


async def _request(app, method, path, **kwargs):
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="https://mcp.getorchestra.io"
        ) as client:
            return await client.request(method, path, **kwargs)


@pytest.fixture
def oauth_env(monkeypatch):
    for key in _AUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in OAUTH_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def api_key_only_env(monkeypatch):
    for key in _AUTH_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.asyncio
async def test_protected_resource_metadata_served_unauthenticated(oauth_env):
    app = _build_app()
    response = await _request(app, "GET", "/.well-known/oauth-protected-resource/orchestra")
    assert response.status_code == 200
    body = response.json()
    assert body["resource"] == "https://mcp.getorchestra.io/orchestra"
    assert body["authorization_servers"] == ["https://auth.example.com/"]


@pytest.mark.asyncio
async def test_post_without_token_returns_401_with_challenge(oauth_env):
    app = _build_app()
    response = await _request(app, "POST", "/orchestra", json=MCP_REQUEST, headers=MCP_HEADERS)
    assert response.status_code == 401
    www_authenticate = response.headers.get("www-authenticate", "")
    assert "Bearer" in www_authenticate
    assert (
        "https://mcp.getorchestra.io/.well-known/oauth-protected-resource/orchestra"
        in www_authenticate
    )


@pytest.mark.asyncio
async def test_api_key_only_mode_still_requires_auth(api_key_only_env):
    """With OAuth disabled the server still rejects unauthenticated requests."""
    app = _build_app()
    response = await _request(app, "POST", "/orchestra", json=MCP_REQUEST, headers=MCP_HEADERS)
    assert response.status_code == 401
