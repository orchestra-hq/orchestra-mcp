import json

import pytest
from fastmcp.server.auth.providers.jwt import JWTVerifier, RSAKeyPair

from orchestramcp import oauth

ISSUER = "https://app.getorchestra.io"
RESOURCE_URL = "https://mcp.getorchestra.io/orchestra"
JWKS_URI = f"{ISSUER}/.well-known/jwks.json"
METADATA_URL = f"{RESOURCE_URL}/.well-known/oauth-protected-resource"


def _enable(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_OAUTH_ISSUER", ISSUER)
    monkeypatch.setenv("ORCHESTRA_OAUTH_JWKS_URI", JWKS_URI)
    monkeypatch.setenv("ORCHESTRA_OAUTH_RESOURCE_URL", RESOURCE_URL)


@pytest.fixture
def key_pair(monkeypatch):
    """Verify signatures against a local key pair instead of auth-srv's JWKS."""
    pair = RSAKeyPair.generate()
    monkeypatch.setattr(
        oauth,
        "_verifier",
        lambda jwks_uri, issuer, audience: JWTVerifier(
            public_key=pair.public_key, issuer=issuer, audience=audience
        ),
    )
    return pair


def test_disabled_when_nothing_configured():
    assert oauth.enabled() is False


@pytest.mark.parametrize(
    "missing",
    ["ORCHESTRA_OAUTH_ISSUER", "ORCHESTRA_OAUTH_JWKS_URI", "ORCHESTRA_OAUTH_RESOURCE_URL"],
)
def test_disabled_when_any_setting_missing(monkeypatch, missing):
    _enable(monkeypatch)
    monkeypatch.delenv(missing)

    assert oauth.enabled() is False


def test_enabled_when_fully_configured(monkeypatch):
    _enable(monkeypatch)

    assert oauth.enabled() is True


async def test_api_key_passes_through_when_oauth_configured(monkeypatch, key_pair):
    _enable(monkeypatch)

    await oauth.verify_token("plain-orchestra-api-key")


async def test_jwt_passes_through_when_oauth_not_configured():
    await oauth.verify_token("header.payload.signature")


async def test_token_for_this_resource_is_accepted(monkeypatch, key_pair):
    _enable(monkeypatch)
    token = key_pair.create_token(issuer=ISSUER, audience=RESOURCE_URL)

    await oauth.verify_token(token)


async def test_token_for_another_audience_is_rejected(monkeypatch, key_pair):
    _enable(monkeypatch)
    token = key_pair.create_token(issuer=ISSUER, audience="https://app.getorchestra.io/api")

    with pytest.raises(oauth.OAuthTokenError):
        await oauth.verify_token(token)


async def test_token_from_another_issuer_is_rejected(monkeypatch, key_pair):
    _enable(monkeypatch)
    token = key_pair.create_token(issuer="https://evil.example.com", audience=RESOURCE_URL)

    with pytest.raises(oauth.OAuthTokenError):
        await oauth.verify_token(token)


async def test_expired_token_is_rejected(monkeypatch, key_pair):
    _enable(monkeypatch)
    token = key_pair.create_token(issuer=ISSUER, audience=RESOURCE_URL, expires_in_seconds=-60)

    with pytest.raises(oauth.OAuthTokenError):
        await oauth.verify_token(token)


def test_www_authenticate_header_omitted_when_disabled():
    assert oauth.www_authenticate_header("invalid_token", "bad token") is None


def test_www_authenticate_header_points_at_the_metadata_document(monkeypatch):
    _enable(monkeypatch)

    assert oauth.www_authenticate_header("invalid_token", "bad token") == (
        'Bearer error="invalid_token", error_description="bad token", '
        f'resource_metadata="{METADATA_URL}"'
    )


def test_metadata_matches_the_url_users_type_and_the_configured_issuer(monkeypatch):
    _enable(monkeypatch)

    response = oauth.handle_discovery_request(
        "GET", "/orchestra/.well-known/oauth-protected-resource"
    )
    metadata = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert metadata["resource"] == RESOURCE_URL
    assert metadata["authorization_servers"] == [ISSUER]


def test_metadata_served_when_the_route_prefix_is_stripped(monkeypatch):
    _enable(monkeypatch)

    response = oauth.handle_discovery_request("GET", "/.well-known/oauth-protected-resource")

    assert response["statusCode"] == 200


def test_discovery_falls_through_on_the_mcp_path(monkeypatch):
    _enable(monkeypatch)

    assert oauth.handle_discovery_request("GET", "/orchestra") is None


def test_discovery_falls_through_when_disabled():
    assert oauth.handle_discovery_request("GET", METADATA_URL) is None


def test_discovery_answers_cors_preflight(monkeypatch):
    _enable(monkeypatch)

    response = oauth.handle_discovery_request(
        "OPTIONS", "/orchestra/.well-known/oauth-protected-resource"
    )

    assert response["statusCode"] == 200
    assert response["headers"]["access-control-allow-origin"] == "*"


def test_discovery_falls_through_on_other_methods(monkeypatch):
    _enable(monkeypatch)

    assert (
        oauth.handle_discovery_request("POST", "/orchestra/.well-known/oauth-protected-resource")
        is None
    )
