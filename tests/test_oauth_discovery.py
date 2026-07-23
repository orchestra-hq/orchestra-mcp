import json
import os

import pytest

from orchestramcp import oauth, oauth_discovery

ISSUER = "https://issuer.example.com"
RESOURCE_URL = "https://mcp.example.com/orchestra"
JWKS_URI = f"{ISSUER}/.well-known/jwks.json"
DISCOVERY_PATH = "/.well-known/oauth-protected-resource/orchestra"


@pytest.fixture(autouse=True)
def _clear_oauth_env():
    yield
    for key in (
        "ORCHESTRA_OAUTH_JWKS_URI",
        "ORCHESTRA_OAUTH_ISSUER",
        "ORCHESTRA_OAUTH_AUDIENCE",
        "ORCHESTRA_OAUTH_RESOURCE_URL",
        "ORCHESTRA_MCP_EXCHANGE_URL",
        "ORCHESTRA_MCP_SERVICE_CREDENTIAL",
    ):
        os.environ.pop(key, None)
    oauth._verifier.cache_clear()


def _enable_discovery():
    os.environ["ORCHESTRA_OAUTH_JWKS_URI"] = JWKS_URI
    os.environ["ORCHESTRA_OAUTH_ISSUER"] = ISSUER
    os.environ["ORCHESTRA_OAUTH_RESOURCE_URL"] = RESOURCE_URL


def test_discovery_disabled_when_nothing_configured():
    assert oauth_discovery.discovery_enabled() is False


def test_discovery_disabled_when_jwks_uri_missing():
    os.environ["ORCHESTRA_OAUTH_ISSUER"] = ISSUER
    os.environ["ORCHESTRA_OAUTH_RESOURCE_URL"] = RESOURCE_URL
    assert oauth_discovery.discovery_enabled() is False


def test_discovery_disabled_when_issuer_missing():
    os.environ["ORCHESTRA_OAUTH_JWKS_URI"] = JWKS_URI
    os.environ["ORCHESTRA_OAUTH_RESOURCE_URL"] = RESOURCE_URL
    assert oauth_discovery.discovery_enabled() is False


def test_discovery_disabled_when_resource_url_missing():
    os.environ["ORCHESTRA_OAUTH_JWKS_URI"] = JWKS_URI
    os.environ["ORCHESTRA_OAUTH_ISSUER"] = ISSUER
    assert oauth_discovery.discovery_enabled() is False


def test_discovery_enabled_when_fully_configured():
    _enable_discovery()
    assert oauth_discovery.discovery_enabled() is True


def test_resource_metadata_url():
    _enable_discovery()
    assert oauth_discovery.resource_metadata_url() == f"https://mcp.example.com{DISCOVERY_PATH}"


def test_resource_metadata_url_none_when_disabled():
    assert oauth_discovery.resource_metadata_url() is None


def test_build_protected_resource_metadata_shape():
    _enable_discovery()
    metadata = oauth_discovery.build_protected_resource_metadata()

    assert metadata["resource"] == RESOURCE_URL
    assert metadata["authorization_servers"] == [f"{ISSUER}/"]
    assert metadata["resource_name"] == "Orchestra MCP Server"
    assert metadata["bearer_methods_supported"] == ["header"]


def test_www_authenticate_header_none_when_disabled():
    assert oauth_discovery.www_authenticate_header("invalid_token", "bad token") is None


def test_www_authenticate_header_when_enabled():
    _enable_discovery()
    header = oauth_discovery.www_authenticate_header("invalid_token", "bad token")

    assert header == (
        'Bearer error="invalid_token", error_description="bad token", '
        f'resource_metadata="https://mcp.example.com{DISCOVERY_PATH}"'
    )


def test_handle_discovery_request_none_for_non_matching_path():
    _enable_discovery()
    assert oauth_discovery.handle_discovery_request("GET", "/orchestra") is None


def test_handle_discovery_request_none_when_disabled():
    assert oauth_discovery.handle_discovery_request("GET", DISCOVERY_PATH) is None


def test_handle_discovery_request_get_returns_metadata():
    _enable_discovery()
    response = oauth_discovery.handle_discovery_request("GET", DISCOVERY_PATH)

    assert response["statusCode"] == 200
    assert response["headers"]["content-type"] == "application/json"
    body = json.loads(response["body"])
    assert body["resource"] == RESOURCE_URL


def test_handle_discovery_request_options_returns_cors():
    _enable_discovery()
    response = oauth_discovery.handle_discovery_request("OPTIONS", DISCOVERY_PATH)

    assert response["statusCode"] == 200
    assert response["body"] == ""


def test_handle_discovery_request_rejects_other_methods():
    _enable_discovery()
    assert oauth_discovery.handle_discovery_request("POST", DISCOVERY_PATH) is None
