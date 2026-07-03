import os

import httpx

from orchestramcp.errors import OrchestraAPIError, parse_error_response


class OrchestraClient:
    """Thin async HTTP transport over the Orchestra public API.

    Endpoint-agnostic: each MCP tool builds its own request and parses its own
    response, so the tool is the single definition of the surface it exposes.
    """

    @staticmethod
    def _build_base_url() -> str:
        env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
        if env not in ("app", "stage", "dev"):
            raise ValueError(f"Invalid environment: {env}. Must be one of: app, stage, dev")
        return f"https://{env}.getorchestra.io/api/engine/public"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = self._build_base_url()
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    def _raise_for_status(self, response: httpx.Response) -> None:
        if not response.is_success:
            raise OrchestraAPIError(response.status_code, parse_error_response(response))

    async def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json: object | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        response = await self._client.request(
            method, path, params=params, json=json, headers=headers
        )
        self._raise_for_status(response)
        return response

    async def get(
        self, path: str, params: dict | None = None, headers: dict | None = None
    ) -> httpx.Response:
        return await self.request("GET", path, params=params, headers=headers)

    async def post(
        self, path: str, json: object | None = None, params: dict | None = None
    ) -> httpx.Response:
        return await self.request("POST", path, json=json, params=params)

    async def put(self, path: str, json: object | None = None) -> httpx.Response:
        return await self.request("PUT", path, json=json)

    async def patch(
        self, path: str, json: object | None = None, params: dict | None = None
    ) -> httpx.Response:
        return await self.request("PATCH", path, json=json, params=params)

    async def delete(self, path: str, params: dict | None = None) -> httpx.Response:
        return await self.request("DELETE", path, params=params)
