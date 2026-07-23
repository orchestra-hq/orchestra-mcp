import os

import pytest
from mcp.server.auth.provider import AccessToken

from orchestramcp import oauth

ISSUER = "https://issuer.example.com"


@pytest.fixture(autouse=True)
def _clear_oauth_env():
    yield
    for key in (
        "ORCHESTRA_OAUTH_JWKS_URI",
        "ORCHESTRA_OAUTH_ISSUER",
        "ORCHESTRA_OAUTH_AUDIENCE",
        "ORCHESTRA_MCP_EXCHANGE_URL",
        "ORCHESTRA_MCP_SERVICE_CREDENTIAL",
    ):
        os.environ.pop(key, None)
    oauth._verifier.cache_clear()


def _enable_oauth():
    os.environ["ORCHESTRA_OAUTH_JWKS_URI"] = f"{ISSUER}/.well-known/jwks.json"
    os.environ["ORCHESTRA_OAUTH_ISSUER"] = ISSUER
    os.environ["ORCHESTRA_OAUTH_AUDIENCE"] = "orchestra-mcp"


def _jwt_shaped_token() -> str:
    return "header.payload.signature"


async def test_raw_api_key_passes_through_when_oauth_not_configured():
    assert await oauth.resolve_api_key("plain-orchestra-api-key") == "plain-orchestra-api-key"


async def test_jwt_shaped_token_passes_through_when_oauth_not_configured():
    token = _jwt_shaped_token()
    assert await oauth.resolve_api_key(token) == token


async def test_non_jwt_token_passes_through_even_when_oauth_configured():
    _enable_oauth()
    assert await oauth.resolve_api_key("plain-orchestra-api-key") == "plain-orchestra-api-key"


async def test_valid_oauth_token_is_exchanged_for_api_key(monkeypatch):
    _enable_oauth()
    os.environ["ORCHESTRA_MCP_EXCHANGE_URL"] = "https://api.getorchestra.io/mcp/exchange"
    os.environ["ORCHESTRA_MCP_SERVICE_CREDENTIAL"] = "service-credential"

    class _StubVerifier:
        async def verify_token(self, token):
            assert token == _jwt_shaped_token()
            return AccessToken(
                token=token,
                client_id="client-a",
                scopes=[],
                subject="user-123",
                claims={"iss": ISSUER},
            )

    monkeypatch.setattr(oauth, "_verifier", lambda: _StubVerifier())

    async def _fake_exchange(subject, claims):
        assert subject == "user-123"
        assert claims == {"iss": ISSUER}
        return "real-orchestra-api-key"

    monkeypatch.setattr(oauth, "_exchange_for_api_key", _fake_exchange)

    resolved = await oauth.resolve_api_key(_jwt_shaped_token())

    assert resolved == "real-orchestra-api-key"


async def test_invalid_oauth_token_raises_token_error(monkeypatch):
    _enable_oauth()

    class _StubVerifier:
        async def verify_token(self, token):
            return None

    monkeypatch.setattr(oauth, "_verifier", lambda: _StubVerifier())

    with pytest.raises(oauth.OAuthTokenError):
        await oauth.resolve_api_key(_jwt_shaped_token())


async def test_exchange_without_config_raises_config_error():
    with pytest.raises(oauth.OAuthConfigError):
        await oauth._exchange_for_api_key("user-123", {})


@pytest.mark.parametrize(
    "token",
    ["not-a-jwt", "only.two", "header..signature", ""],
)
def test_looks_like_jwt_rejects_malformed_tokens(token):
    assert oauth._looks_like_jwt(token) is False


def test_looks_like_jwt_accepts_three_nonempty_segments():
    assert oauth._looks_like_jwt(_jwt_shaped_token()) is True
