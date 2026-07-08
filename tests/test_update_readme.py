import json
from pathlib import Path

import pytest

from scripts.update_readme import END_MARKER, START_MARKER, render_table, replace_table
from tests.conftest import EXPECTED_TOOLS

FIXTURE = Path(__file__).parent / "fixtures" / "openapi_live.json"


def test_render_table_lists_every_tool():
    table = render_table(json.loads(FIXTURE.read_text(encoding="utf-8")))
    documented = {line.split("`")[1] for line in table.splitlines() if line.startswith("| `")}
    assert documented == EXPECTED_TOOLS | {"delete_pipeline", "delete_environment"}


def test_replace_table_swaps_marked_block():
    readme = f"intro\n{START_MARKER}\nold table\n{END_MARKER}\noutro\n"
    assert replace_table(readme, "new table") == (
        f"intro\n{START_MARKER}\nnew table\n{END_MARKER}\noutro\n"
    )


def test_replace_table_requires_markers():
    with pytest.raises(ValueError):
        replace_table("no markers here", "table")
