import os
from functools import lru_cache

from fastmcp import FastMCP

from orchestramcp.client import build_http_client
from orchestramcp.openapi_server import ApiSource, build_server
from orchestramcp.spec import load_spec

VALID_ENVS = ("app", "stage", "dev")


def _env() -> str:
    env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
    if env not in VALID_ENVS:
        raise ValueError(f"Invalid environment: {env}. Must be one of: {', '.join(VALID_ENVS)}")
    return env


def _base_url() -> str:
    return f"https://{_env()}.getorchestra.io/api/engine"


def _platform_base_url() -> str:
    return f"https://{_env()}.getorchestra.io/public/v1"


def _ui_base_url() -> str:
    return f"https://{_env()}.getorchestra.io"


def _spec_url() -> str:
    return os.getenv("ORCHESTRA_OPENAPI_URL") or f"{_base_url()}/openapi.json"


def _platform_spec_url() -> str:
    return os.getenv("ORCHESTRA_PLATFORM_OPENAPI_URL") or f"{_platform_base_url()}/openapi.json"


def _delete_enabled() -> bool:
    return os.getenv("ORCHESTRA_ENABLE_DELETE", "").strip().lower() in ("1", "true")


@lru_cache
def get_client(base_url: str):
    return build_http_client(base_url)


@lru_cache
def get_mcp() -> FastMCP:
    """A spec that cannot be fetched raises rather than yielding a server missing that
    API's tools: an outage reads better than a tool surface that quietly shrank."""
    return build_server(
        ApiSource(load_spec(_spec_url()), get_client(_base_url())),
        ApiSource(load_spec(_platform_spec_url()), get_client(_platform_base_url())),
        include_deletes=_delete_enabled(),
        ui_base_url=_ui_base_url(),
    )


if __name__ == "__main__":
    get_mcp().run()
