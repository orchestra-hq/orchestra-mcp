from __future__ import annotations

import importlib
import warnings

from authlib.deprecate import AuthlibDeprecationWarning

warnings.filterwarnings(
    "ignore",
    category=AuthlibDeprecationWarning,
    message=r"authlib\.jose module is deprecated, please use joserfc instead\.",
)

mcp = importlib.import_module("orchestramcp.server").mcp


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="INFO")
