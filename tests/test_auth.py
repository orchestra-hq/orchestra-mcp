import pytest
from fastmcp.server.auth import AccessToken

from orchestramcp import auth
from orchestramcp.auth import (
    MultiAuth,
    OrchestraApiKeyVerifier,
    build_auth,
    build_oauth_provider,
    get_mcp_path,
    resolve_orchestra_credential,
)
from orchestramcp.errors import OrchestraAPIError

OAUTH_ENV = {
    "MCP_OAUTH_ISSUER": "https://auth.example.com",
    "MCP_OAUTH_JWKS_URI": "https://auth.example.com/.well-known/jwks.json",
    "MCP_PUBLIC_BASE_URL": "https://mcp.getorchestra.io/orchestra",
}


@pytest.fixture
def clear_auth_env(monkeypatch):
    for key in (
        "MCP_OAUTH_ISSUER",
        "MCP_OAUTH_JWKS_URI",
        "MCP_PUBLIC_BASE_URL",
        "MCP_OAUTH_AUDIENCE",
        "ORCHESTRA_API_KEY",
        "ORCHESTRA_MCP_EXCHANGE_URL",
        "ORCHESTRA_MCP_SERVICE_CREDENTIAL",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def oauth_env(clear_auth_env, monkeypatch):
    for key, value in OAUTH_ENV.items():
        monkeypatch.setenv(key, value)


# --- OrchestraApiKeyVerifier ------------------------------------------------


async def test_api_key_verifier_rejects_jwt_without_probing(monkeypatch):
    verifier = OrchestraApiKeyVerifier()
    probed = False

    async def fake_probe(api_key):
        nonlocal probed
        probed = True
        return True

    monkeypatch.setattr(OrchestraApiKeyVerifier, "_probe", staticmethod(fake_probe))

    result = await verifier.verify_token("header.payload.signature")
    assert result is None
    assert probed is False


async def test_api_key_verifier_accepts_valid_key(monkeypatch):
    verifier = OrchestraApiKeyVerifier()
    monkeypatch.setattr(
        OrchestraApiKeyVerifier, "_probe", staticmethod(lambda api_key: _async_true())
    )

    token = await verifier.verify_token("orchestra-key-123")
    assert token is not None
    assert token.claims["auth_method"] == "api_key"
    assert token.claims["orchestra_api_key"] == "orchestra-key-123"


async def test_api_key_verifier_rejects_bad_key(monkeypatch):
    verifier = OrchestraApiKeyVerifier()
    monkeypatch.setattr(
        OrchestraApiKeyVerifier, "_probe", staticmethod(lambda api_key: _async_false())
    )
    assert await verifier.verify_token("bad-key") is None


async def test_api_key_verifier_caches_validation(monkeypatch):
    verifier = OrchestraApiKeyVerifier()
    calls = 0

    async def counting_probe(api_key):
        nonlocal calls
        calls += 1
        return True

    monkeypatch.setattr(OrchestraApiKeyVerifier, "_probe", staticmethod(counting_probe))

    await verifier.verify_token("orchestra-key-123")
    await verifier.verify_token("orchestra-key-123")
    assert calls == 1


async def test_probe_fails_closed_only_on_auth_errors(monkeypatch):
    """401/403 from upstream mean the key is invalid; any other failure must
    not be treated as an auth failure."""

    class FakeClient:
        def __init__(self, api_key):
            pass

        async def list_pipeline_runs(self, page=None, page_size=None):
            raise error

        async def close(self):
            pass

    monkeypatch.setattr(auth, "OrchestraClient", FakeClient)

    error = OrchestraAPIError(401, "bad key")
    assert await OrchestraApiKeyVerifier._probe("key") is False

    error = OrchestraAPIError(500, "upstream down")
    assert await OrchestraApiKeyVerifier._probe("key") is True


# --- provider composition ---------------------------------------------------


def test_build_auth_api_key_only_without_oauth_env(clear_auth_env):
    assert isinstance(build_auth(), OrchestraApiKeyVerifier)
    assert build_oauth_provider() is None


def test_build_auth_multiauth_with_oauth_env(oauth_env):
    auth_provider = build_auth()
    assert isinstance(auth_provider, MultiAuth)
    # OAuth provider owns routes/metadata; api-key verifier is the fallback.
    assert auth_provider.server is not None
    assert any(isinstance(v, OrchestraApiKeyVerifier) for v in auth_provider.verifiers)


def test_partial_oauth_env_disables_oauth(clear_auth_env, monkeypatch):
    monkeypatch.setenv("MCP_OAUTH_ISSUER", "https://auth.example.com")
    assert build_oauth_provider() is None
    assert isinstance(build_auth(), OrchestraApiKeyVerifier)


def test_path_and_origin_derivation(oauth_env):
    assert get_mcp_path() == "/orchestra"
    assert auth._public_base() == ("https://mcp.getorchestra.io", "/orchestra")


def test_path_defaults_without_public_base_url(clear_auth_env):
    assert get_mcp_path() == "/orchestra"


# --- resolve_orchestra_credential -------------------------------------------


async def test_resolve_credential_api_key_path():
    token = AccessToken(
        token="raw-key",
        client_id="orchestra-api-key",
        scopes=[],
        claims={"auth_method": "api_key", "orchestra_api_key": "raw-key"},
    )
    assert await resolve_orchestra_credential(token) == "raw-key"


async def test_resolve_credential_env_fallback(clear_auth_env, monkeypatch):
    monkeypatch.setenv("ORCHESTRA_API_KEY", "env-key")
    assert await resolve_orchestra_credential(None) == "env-key"


async def test_resolve_credential_no_token_no_env_raises(clear_auth_env):
    with pytest.raises(ValueError, match="ORCHESTRA_API_KEY"):
        await resolve_orchestra_credential(None)


async def test_resolve_credential_oauth_without_exchange_config_raises(clear_auth_env):
    token = AccessToken(
        token="jwt-token",
        client_id="some-client",
        scopes=[],
        claims={"auth_method": "oauth", "sub": "user-1"},
    )
    with pytest.raises(RuntimeError, match="credential exchange is not configured"):
        await resolve_orchestra_credential(token)


# --- helpers ----------------------------------------------------------------


async def _async_true():
    return True


async def _async_false():
    return False
