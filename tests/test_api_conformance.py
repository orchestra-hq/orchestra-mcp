"""Tests for the MCP <-> API conformance checker and the contract it reads."""

import importlib

import pytest

from orchestramcp import api_contract
from scripts import check_api_conformance as chk

ERROR, WARN, INFO = chk.ERROR, chk.WARN, chk.INFO


def _levels(findings, tool):
    return [f.level for f in findings if f.tool == tool]


def _summary(findings, tool):
    return " ".join(f.summary for f in findings if f.tool == tool)


# ---------------------------------------------------------------------------
# Spec fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def spec():
    """A minimal spec that matches a small hand-written contract fixture."""
    return {
        "paths": {
            "/public/widgets": {
                "get": {
                    "parameters": [
                        {"name": "status", "in": "query", "required": False},
                        {"name": "page", "in": "query", "required": False},
                    ]
                }
            },
            "/public/widgets/{widget_id}": {
                "get": {"parameters": [{"name": "widget_id", "in": "path", "required": True}]}
            },
        },
        "components": {
            "schemas": {
                "WidgetStatus": {"enum": ["ACTIVE", "ARCHIVED", "DRAFT"]},
            }
        },
    }


C = api_contract.ToolContract
Q = api_contract.QueryParam


# ---------------------------------------------------------------------------
# Path checks
# ---------------------------------------------------------------------------


def test_path_present_no_finding(spec):
    contracts = (C(tool="list_widgets", method="get", path="/widgets"),)
    assert chk.check_paths(spec, contracts) == []


def test_missing_path_is_error(spec):
    contracts = (C(tool="list_gadgets", method="get", path="/gadgets"),)
    findings = chk.check_paths(spec, contracts)
    assert _levels(findings, "list_gadgets") == [ERROR]
    assert "not found" in _summary(findings, "list_gadgets")


def test_missing_method_reports_available_methods(spec):
    contracts = (C(tool="make_widget", method="post", path="/widgets"),)
    findings = chk.check_paths(spec, contracts)
    assert _levels(findings, "make_widget") == [ERROR]
    assert "get" in _summary(findings, "make_widget")


def test_allow_missing_path_suppresses_error(spec):
    contracts = (C(tool="x", method="get", path="/gone", allow_missing_path=True),)
    assert chk.check_paths(spec, contracts) == []


def test_allow_missing_path_flags_stale_override_when_present(spec):
    contracts = (C(tool="list_widgets", method="get", path="/widgets", allow_missing_path=True),)
    findings = chk.check_paths(spec, contracts)
    assert _levels(findings, "list_widgets") == [INFO]
    assert "stale" in _summary(findings, "list_widgets")


def test_templated_path_matches_regardless_of_placeholder_name(spec):
    # Contract uses a different placeholder name than the spec ({id} vs {widget_id}).
    contracts = (C(tool="get_widget", method="get", path="/widgets/{id}"),)
    assert chk.check_paths(spec, contracts) == []


# ---------------------------------------------------------------------------
# Query param checks
# ---------------------------------------------------------------------------


def test_query_param_present(spec):
    contracts = (
        C(tool="list_widgets", method="get", path="/widgets", query_params=(Q("status"),)),
    )
    assert [f for f in chk.check_query_params(spec, contracts) if f.is_actionable] == []


def test_missing_query_param_is_warn(spec):
    contracts = (
        C(tool="list_widgets", method="get", path="/widgets", query_params=(Q("colour"),)),
    )
    findings = chk.check_query_params(spec, contracts)
    assert WARN in _levels(findings, "list_widgets")
    assert "colour" in _summary(findings, "list_widgets")


def test_required_mismatch_is_warn(spec):
    contracts = (
        C(
            tool="list_widgets",
            method="get",
            path="/widgets",
            query_params=(Q("status", required=True),),
        ),
    )
    findings = [f for f in chk.check_query_params(spec, contracts) if f.is_actionable]
    assert [f.level for f in findings] == [WARN]
    assert "required-ness" in findings[0].summary


def test_new_spec_param_is_info(spec):
    contracts = (
        C(tool="list_widgets", method="get", path="/widgets", query_params=(Q("status"),)),
    )
    findings = chk.check_query_params(spec, contracts)
    info = [f for f in findings if f.level == INFO]
    assert len(info) == 1
    assert "page" in info[0].summary


# ---------------------------------------------------------------------------
# Enum checks
# ---------------------------------------------------------------------------


def _enum_provider(mapping):
    def provider(name):
        return mapping[name]

    return provider


def test_enum_in_sync(spec):
    contracts = (api_contract.EnumContract("WidgetStatus", "WidgetStatus"),)
    provider = _enum_provider({"WidgetStatus": ["ACTIVE", "ARCHIVED", "DRAFT"]})
    assert chk.check_enums(spec, contracts, provider) == []


def test_enum_added_value_is_warn_and_autofixable(spec):
    contracts = (api_contract.EnumContract("WidgetStatus", "WidgetStatus"),)
    provider = _enum_provider({"WidgetStatus": ["ACTIVE", "ARCHIVED"]})  # missing DRAFT
    findings = chk.check_enums(spec, contracts, provider)
    assert [f.level for f in findings] == [WARN]
    assert findings[0].data == {"model_class": "WidgetStatus", "add": ["DRAFT"]}


def test_enum_removed_value_is_error(spec):
    contracts = (api_contract.EnumContract("WidgetStatus", "WidgetStatus"),)
    provider = _enum_provider({"WidgetStatus": ["ACTIVE", "ARCHIVED", "DRAFT", "LEGACY"]})
    findings = chk.check_enums(spec, contracts, provider)
    assert ERROR in [f.level for f in findings]
    assert "LEGACY" in _summary(findings, "WidgetStatus")


def test_missing_enum_schema_is_error(spec):
    contracts = (api_contract.EnumContract("WidgetStatus", "NoSuchSchema"),)
    provider = _enum_provider({"WidgetStatus": ["ACTIVE"]})
    findings = chk.check_enums(spec, contracts, provider)
    assert [f.level for f in findings] == [ERROR]


def test_non_identifier_added_value_not_autofixable():
    spec = {"components": {"schemas": {"Kind": {"enum": ["A", "Two Words"]}}}}
    contracts = (api_contract.EnumContract("Kind", "Kind"),)
    provider = _enum_provider({"Kind": ["A"]})
    findings = chk.check_enums(spec, contracts, provider)
    assert [f.level for f in findings] == [WARN]
    assert not findings[0].data  # no auto-apply payload


# ---------------------------------------------------------------------------
# Enum auto-apply (source patching)
# ---------------------------------------------------------------------------


def test_append_enum_members_inserts_at_end_of_class():
    source = (
        "from enum import Enum\n\n\n"
        "class Colour(str, Enum):\n"
        '    RED = "RED"\n'
        '    BLUE = "BLUE"\n\n\n'
        "class Other(str, Enum):\n"
        '    X = "X"\n'
    )
    out = chk._append_enum_members(source, "Colour", ["GREEN"])
    # Re-import safety: the value lands inside Colour, before Other.
    assert '    BLUE = "BLUE"\n    GREEN = "GREEN"\n' in out
    assert out.index("GREEN") < out.index("class Other")


def test_apply_enum_additions_writes_file(tmp_path):
    models = tmp_path / "models.py"
    models.write_text(
        'from enum import Enum\n\n\nclass Colour(str, Enum):\n    RED = "RED"\n',
        encoding="utf-8",
    )
    finding = chk.Finding(WARN, "Colour", "added", data={"model_class": "Colour", "add": ["BLUE"]})
    applied = chk.apply_enum_additions([finding], models_path=models)
    assert applied == ["Colour: added BLUE"]
    assert 'BLUE = "BLUE"' in models.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The real, committed contract must stay valid
# ---------------------------------------------------------------------------


def test_every_contract_tool_exists_in_server():
    server = importlib.import_module("orchestramcp.server")
    for c in api_contract.TOOL_CONTRACTS:
        assert hasattr(server, c.tool), f"contract references unknown tool {c.tool!r}"


def test_every_enum_contract_maps_to_a_real_model_enum():
    for ec in api_contract.ENUM_CONTRACTS:
        # Raises LookupError if the class is missing or not an Enum.
        values = chk.model_enum_values(ec.model_class)
        assert values, f"{ec.model_class} has no members"


def test_contract_methods_are_valid_http_verbs():
    for c in api_contract.TOOL_CONTRACTS:
        assert c.method in chk.HTTP_METHODS
