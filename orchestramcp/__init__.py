from importlib.metadata import PackageNotFoundError, version

from orchestramcp.errors import OrchestraAPIError

__all__ = ["OrchestraAPIError", "__version__"]

try:
    # Derived from server.json via [tool.hatch.version] in pyproject.toml.
    __version__ = version("orchestramcp")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0.dev0"
