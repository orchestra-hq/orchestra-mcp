from __future__ import annotations

import importlib

mcp = importlib.import_module("orchestramcp.server").mcp


if __name__ == "__main__":
    mcp.run(show_banner=False, log_level="INFO")
