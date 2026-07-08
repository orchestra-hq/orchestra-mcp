"""Regenerate the Available Tools table in README.md from the Orchestra OpenAPI spec.

Run daily by .github/workflows/update_readme.yml, or locally with:

    uv run python scripts/update_readme.py
"""

import os
import re
from pathlib import Path

from orchestramcp.adaptations import ADAPTATIONS
from orchestramcp.spec import load_spec, mcp_operations

DEFAULT_SPEC_URL = "https://app.getorchestra.io/api/engine/openapi.json"
README = Path(__file__).resolve().parent.parent / "README.md"

START_MARKER = "<!-- available-tools:start -->"
END_MARKER = "<!-- available-tools:end -->"

TABLE_HEADER = (
    "| Tool | Auth required | Purpose | Category |\n|------|---------------|---------|------|"
)

# Tools callable without an Orchestra API key.
NO_AUTH_TOOLS = {"validate_pipeline", "get_pipeline_run_lineage_url"}

# Display order for categories (spec tags). Unlisted tags sort last; within a
# category, rows keep their spec order.
CATEGORY_ORDER = (
    "Pipelines",
    "Pipeline Runs",
    "Task Runs",
    "Operations",
    "Assets",
    "Logs",
    "Artifacts",
    "Integrations",
    "Environments",
)

# Hand-written tool with no backing endpoint (see orchestramcp/handwritten.py),
# so its row cannot be derived from the spec.
LINEAGE_URL_ROW = (
    "get_pipeline_run_lineage_url",
    "Build the URL of a pipeline run's lineage graph in the Orchestra UI (derived from `ORCHESTRA_ENV`).",
    "Pipeline Runs",
)


def _purpose(operation: dict, method: str, path: str) -> str:
    """Describe a tool the way the MCP server presents it, with its endpoint."""
    adaptation = ADAPTATIONS.get(operation.get("operationId"))
    text = (
        adaptation.description
        if adaptation and adaptation.description
        else operation.get("summary", "")
    )
    text = " ".join(text.split()).rstrip(".")
    endpoint = f"`{method.upper()} {path.removeprefix('/public')}`"
    if method == "delete":
        return f"**Disabled by default.** {text} ({endpoint}). Set `ORCHESTRA_ENABLE_DELETE` to expose it."
    return f"{text} ({endpoint})."


def render_table(spec: dict) -> str:
    rows = [
        (
            operation["operationId"],
            _purpose(operation, method, path),
            (operation.get("tags") or ["Other"])[0],
        )
        for path, method, operation in mcp_operations(spec)
    ]
    rows.append(LINEAGE_URL_ROW)

    def category_rank(row: tuple[str, str, str]) -> int:
        category = row[2]
        return CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else len(CATEGORY_ORDER)

    rows.sort(key=category_rank)
    lines = [TABLE_HEADER]
    for tool, purpose, category in rows:
        auth = "No" if tool in NO_AUTH_TOOLS else "Yes"
        lines.append(f"| `{tool}` | {auth} | {purpose} | {category} |")
    return "\n".join(lines)


def replace_table(readme: str, table: str) -> str:
    pattern = re.compile(re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER), re.DOTALL)
    if not pattern.search(readme):
        raise ValueError(f"README is missing the {START_MARKER} / {END_MARKER} markers")
    return pattern.sub(lambda _: f"{START_MARKER}\n{table}\n{END_MARKER}", readme)


def main() -> None:
    spec = load_spec(os.getenv("ORCHESTRA_OPENAPI_URL") or DEFAULT_SPEC_URL)
    readme = README.read_text(encoding="utf-8")
    README.write_text(replace_table(readme, render_table(spec)), encoding="utf-8")


if __name__ == "__main__":
    main()
