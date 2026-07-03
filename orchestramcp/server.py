import os
from functools import lru_cache

from fastmcp import FastMCP

from orchestramcp.client import build_http_client
from orchestramcp.openapi_server import build_server
from orchestramcp.spec import load_spec

VALID_ENVS = ("app", "stage", "dev")


def _env() -> str:
    env = os.getenv("ORCHESTRA_ENV", "app").lower().strip()
    if env not in VALID_ENVS:
        raise ValueError(f"Invalid environment: {env}. Must be one of: {', '.join(VALID_ENVS)}")
    return env


def _base_url() -> str:
    return f"https://{_env()}.getorchestra.io/api/engine"


def _ui_base_url() -> str:
    return f"https://{_env()}.getorchestra.io"


def _spec_url() -> str:
    return os.getenv("ORCHESTRA_OPENAPI_URL") or f"{_base_url()}/openapi.json"


def _delete_enabled() -> bool:
    return os.getenv("ORCHESTRA_ENABLE_DELETE", "").strip().lower() in ("1", "true")


@lru_cache
def get_client():
    return build_http_client(_base_url())


@lru_cache
def get_mcp() -> FastMCP:
    return build_server(
        load_spec(_spec_url()),
        get_client(),
        include_deletes=_delete_enabled(),
        ui_base_url=_ui_base_url(),
    )


if __name__ == "__main__":
    get_mcp().run()
