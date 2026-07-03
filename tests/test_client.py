from unittest.mock import AsyncMock, Mock

import pytest

from orchestramcp.client import OrchestraAPIError, OrchestraClient


@pytest.fixture
def client():
    return OrchestraClient(api_key="test-api-key")


def _response(is_success=True, status_code=200, json=None, text=""):
    response = Mock()
    response.is_success = is_success
    response.status_code = status_code
    response.text = text
    response.json.return_value = json
    return response


def test_build_base_url_defaults_to_app(monkeypatch):
    monkeypatch.delenv("ORCHESTRA_ENV", raising=False)
    assert OrchestraClient(api_key="k").base_url.startswith("https://app.getorchestra.io")


@pytest.mark.parametrize("env", ["app", "stage", "dev"])
def test_build_base_url_accepts_known_environments(monkeypatch, env):
    monkeypatch.setenv("ORCHESTRA_ENV", env)
    expected = f"https://{env}.getorchestra.io/api/engine/public"
    assert OrchestraClient(api_key="k").base_url == expected


def test_build_base_url_rejects_unknown_environment(monkeypatch):
    monkeypatch.setenv("ORCHESTRA_ENV", "prod")
    with pytest.raises(ValueError, match="Invalid environment"):
        OrchestraClient(api_key="k")


async def test_verbs_delegate_to_httpx_and_return_response(client):
    ok = _response(json={"ok": True})
    client._client.request = AsyncMock(return_value=ok)

    assert await client.get("/x", params={"a": 1}) is ok
    client._client.request.assert_called_with("GET", "/x", params={"a": 1}, json=None, headers=None)

    await client.post("/x", json={"b": 2})
    client._client.request.assert_called_with(
        "POST", "/x", params=None, json={"b": 2}, headers=None
    )

    await client.delete("/x", params={"id": "1"})
    client._client.request.assert_called_with(
        "DELETE", "/x", params={"id": "1"}, json=None, headers=None
    )


async def test_request_raises_orchestra_error_with_parsed_message(client):
    client._client.request = AsyncMock(
        return_value=_response(is_success=False, status_code=422, json={"detail": "bad input"})
    )

    with pytest.raises(OrchestraAPIError) as exc_info:
        await client.post("/pipelines", json={})

    assert exc_info.value.status_code == 422
    assert exc_info.value.message == "bad input"
