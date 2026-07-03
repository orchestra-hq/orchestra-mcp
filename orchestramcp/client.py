import os

import httpx

from orchestramcp.errors import OrchestraAPIError, parse_error_response


class _BearerAuth(httpx.Auth):
    """Attach the current ORCHESTRA_API_KEY on each request.

    Reading the token per request (rather than baking it in) lets one cached
    client serve requests whose credentials change, as the Lambda handler does.
    """

    def auth_flow(self, request):
        token = os.getenv("ORCHESTRA_API_KEY")
        if not token:
            raise ValueError("ORCHESTRA_API_KEY environment variable is required")
        request.headers["Authorization"] = f"Bearer {token}"
        yield request


async def _raise_on_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    await response.aread()
    raise OrchestraAPIError(response.status_code, parse_error_response(response))


def build_http_client(base_url: str) -> httpx.AsyncClient:
    """Build the httpx client the generated tools call through."""
    return httpx.AsyncClient(
        base_url=base_url,
        auth=_BearerAuth(),
        timeout=30.0,
        event_hooks={"response": [_raise_on_error]},
    )
