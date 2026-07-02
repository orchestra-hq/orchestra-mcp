#!/usr/bin/env python3
"""Check the curated MCP surface against the live Orchestra OpenAPI spec.

The MCP is a hand-curated wrapper over the Orchestra API, so we deliberately do NOT
regenerate it from OpenAPI. Instead this script guards against *silent drift*: it reads
``orchestramcp/api_contract.py`` (what the MCP depends on) and asserts it still matches
the live spec. Renamed paths/params or new enum values surface as findings — and, on a
schedule, as a pull request — instead of quietly breaking a tool at runtime.

Usage:
    python scripts/check_api_conformance.py                # check the live spec
    python scripts/check_api_conformance.py --spec spec.json
    python scripts/check_api_conformance.py --apply-enums   # auto-add new enum values
    python scripts/check_api_conformance.py --report-md report.md

Exit code is non-zero when there is actionable drift (any ERROR or WARN finding), so it
doubles as a CI gate.
"""

import argparse
import ast
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from orchestramcp.api_contract import (  # noqa: E402
    ENUM_CONTRACTS,
    LIVE_SPEC_URL,
    TOOL_CONTRACTS,
    EnumContract,
    ToolContract,
    spec_path,
)

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "head", "options", "trace"})

ERROR = "ERROR"
WARN = "WARN"
INFO = "INFO"
_LEVEL_ORDER = {ERROR: 0, WARN: 1, INFO: 2}

MODELS_PATH = _PROJECT_ROOT / "orchestramcp" / "models.py"


@dataclass
class Finding:
    """A single conformance discrepancy between the contract and the live spec."""

    level: str  # ERROR | WARN | INFO
    tool: str  # tool / enum the finding is about
    summary: str  # one-line description
    detail: str = ""  # optional extra context / suggested fix
    # Structured payload used by --apply-enums (e.g. {"model_class": ..., "add": [...]}).
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.level in (ERROR, WARN)


# ---------------------------------------------------------------------------
# Spec loading
# ---------------------------------------------------------------------------


def load_spec(source: str) -> dict:
    """Load an OpenAPI document from a local path or an http(s) URL."""
    if source.startswith(("http://", "https://")):
        import httpx

        response = httpx.get(source, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.json()
    return json.loads(Path(source).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Enum value discovery (from orchestramcp.models)
# ---------------------------------------------------------------------------


def model_enum_values(class_name: str) -> list[str]:
    """Return the values of an Enum subclass defined in orchestramcp.models."""
    from orchestramcp import models

    enum_cls = getattr(models, class_name, None)
    if enum_cls is None or not (isinstance(enum_cls, type) and issubclass(enum_cls, Enum)):
        raise LookupError(f"{class_name} is not an Enum in orchestramcp.models")
    return [member.value for member in enum_cls]


def spec_enum_values(spec: dict, schema_name: str) -> list[str] | None:
    """Return the ``enum`` values of a component schema, or None if absent."""
    schema = (spec.get("components", {}).get("schemas", {}) or {}).get(schema_name)
    if not isinstance(schema, dict):
        return None
    values = schema.get("enum")
    return list(values) if isinstance(values, list) else None


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _normalize_path(path: str) -> str:
    """Collapse templated segments so ``/x/{a}`` and ``/x/{b}`` compare equal.

    The URL shape is what matters for conformance; the placeholder name is cosmetic
    and differs freely between the client's paths and the spec's.
    """
    segments = path.split("/")
    return "/".join("{}" if s.startswith("{") and s.endswith("}") else s for s in segments)


def _path_item(spec: dict, full_path: str) -> dict | None:
    """Return the spec path-item for a path, matching on normalized template shape."""
    paths = spec.get("paths", {})
    exact = paths.get(full_path)
    if isinstance(exact, dict):
        return exact
    target = _normalize_path(full_path)
    for p, item in paths.items():
        if isinstance(item, dict) and _normalize_path(p) == target:
            return item
    return None


def _operation(spec: dict, path: str, method: str) -> dict | None:
    path_item = _path_item(spec, path)
    if not isinstance(path_item, dict):
        return None
    op = path_item.get(method)
    return op if isinstance(op, dict) else None


def check_paths(spec: dict, contracts: tuple[ToolContract, ...] = TOOL_CONTRACTS) -> list[Finding]:
    findings: list[Finding] = []
    for c in contracts:
        full_path = spec_path(c.path)
        path_item = _path_item(spec, full_path)
        method_present = isinstance(path_item, dict) and c.method in path_item

        if method_present:
            if c.allow_missing_path:
                findings.append(
                    Finding(
                        INFO,
                        c.tool,
                        f"{c.method.upper()} {full_path} now exists in the spec — "
                        "the allow_missing_path override is stale and can be removed.",
                    )
                )
            continue

        # Method/path not found.
        if c.allow_missing_path:
            continue  # intentional, documented divergence
        detail = c.note or ""
        # Distinguish "path gone" from "method gone" to point the reviewer at the fix.
        if isinstance(path_item, dict):
            summary = (
                f"{c.method.upper()} {full_path} missing — path exists but not that "
                f"method (available: {', '.join(sorted(m for m in path_item if m in HTTP_METHODS))})."
            )
        else:
            summary = (
                f"{c.method.upper()} {full_path} not found in the spec (path removed or renamed)."
            )
        findings.append(Finding(ERROR, c.tool, summary, detail))
    return findings


def check_query_params(
    spec: dict, contracts: tuple[ToolContract, ...] = TOOL_CONTRACTS
) -> list[Finding]:
    findings: list[Finding] = []
    for c in contracts:
        op = _operation(spec, spec_path(c.path), c.method)
        if op is None:
            continue  # path-level finding already raised in check_paths

        spec_params = {
            p["name"]: p
            for p in op.get("parameters", [])
            if isinstance(p, dict) and p.get("in") == "query"
        }

        for qp in c.query_params:
            spec_param = spec_params.get(qp.name)
            if spec_param is None:
                findings.append(
                    Finding(
                        WARN,
                        c.tool,
                        f"query param '{qp.name}' no longer accepted by "
                        f"{c.method.upper()} {spec_path(c.path)} (renamed or removed).",
                    )
                )
                continue
            spec_required = bool(spec_param.get("required", False))
            if spec_required != qp.required:
                findings.append(
                    Finding(
                        WARN,
                        c.tool,
                        f"query param '{qp.name}' required-ness changed: contract="
                        f"{qp.required}, spec={spec_required}.",
                    )
                )

        # Additive: params the API now accepts that the MCP does not expose. Informational.
        declared = {qp.name for qp in c.query_params}
        new_params = [
            name
            for name, p in spec_params.items()
            if name not in declared and not p.get("deprecated", False)
        ]
        if new_params:
            findings.append(
                Finding(
                    INFO,
                    c.tool,
                    f"spec accepts query params the MCP does not expose: {', '.join(sorted(new_params))}.",
                    "Consider surfacing them if useful; no action required.",
                )
            )
    return findings


def check_enums(
    spec: dict,
    contracts: tuple[EnumContract, ...] = ENUM_CONTRACTS,
    values_provider: Callable[[str], list[str]] = model_enum_values,
) -> list[Finding]:
    findings: list[Finding] = []
    for ec in contracts:
        spec_values = spec_enum_values(spec, ec.spec_schema)
        if spec_values is None:
            findings.append(
                Finding(
                    ERROR,
                    ec.model_class,
                    f"spec schema '{ec.spec_schema}' not found or has no enum "
                    f"(models.{ec.model_class} can no longer be validated).",
                )
            )
            continue

        model_values = values_provider(ec.model_class)
        spec_set, model_set = set(spec_values), set(model_values)

        removed = [v for v in model_values if v not in spec_set]
        if removed:
            findings.append(
                Finding(
                    ERROR,
                    ec.model_class,
                    f"models.{ec.model_class} has values the API dropped: {', '.join(removed)}.",
                    "The API no longer returns/accepts these — confirm and remove them.",
                )
            )

        added = [v for v in spec_values if v not in model_set]
        if added:
            applicable = [v for v in added if v.isidentifier()]
            non_ident = [v for v in added if not v.isidentifier()]
            if applicable:
                findings.append(
                    Finding(
                        WARN,
                        ec.model_class,
                        f"API added values missing from models.{ec.model_class}: {', '.join(applicable)}.",
                        "Auto-fixable with --apply-enums. Remember to update the tool "
                        "docstring in server.py that enumerates these values.",
                        data={"model_class": ec.model_class, "add": applicable},
                    )
                )
            if non_ident:
                findings.append(
                    Finding(
                        WARN,
                        ec.model_class,
                        f"API added non-identifier values to {ec.spec_schema}: {', '.join(non_ident)}.",
                        "Add manually to models.py (value differs from a valid member name).",
                    )
                )
    return findings


def run_checks(spec: dict) -> list[Finding]:
    findings = check_paths(spec) + check_query_params(spec) + check_enums(spec)
    findings.sort(key=lambda f: (_LEVEL_ORDER[f.level], f.tool))
    return findings


# ---------------------------------------------------------------------------
# --apply-enums: patch orchestramcp/models.py in place
# ---------------------------------------------------------------------------


def _append_enum_members(source: str, class_name: str, new_values: list[str]) -> str:
    """Append string-enum members to a class in `source`, returning the new source.

    Assumes ``value == name`` (true for every enum in models.py). Members are appended
    after the class's last statement, preserving its indentation.
    """
    tree = ast.parse(source)
    class_node = next(
        (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name), None
    )
    if class_node is None or not class_node.body:
        raise LookupError(f"class {class_name} not found in models source")

    last_stmt = class_node.body[-1]
    indent = " " * last_stmt.col_offset
    lines = source.splitlines(keepends=True)
    insert_at = last_stmt.end_lineno  # 1-based line of last member; insert after it
    new_lines = [f'{indent}{v} = "{v}"\n' for v in new_values]
    # Guard: end the file with a newline so insertion is clean.
    if lines and not lines[insert_at - 1].endswith("\n"):
        lines[insert_at - 1] += "\n"
    lines[insert_at:insert_at] = new_lines
    return "".join(lines)


def apply_enum_additions(findings: list[Finding], models_path: Path = MODELS_PATH) -> list[str]:
    """Apply auto-fixable enum additions to models.py. Returns human-readable messages."""
    applied: list[str] = []
    for f in findings:
        add = f.data.get("add")
        model_class = f.data.get("model_class")
        if not add or not model_class:
            continue
        source = models_path.read_text(encoding="utf-8")
        source = _append_enum_members(source, model_class, add)
        models_path.write_text(source, encoding="utf-8")
        applied.append(f"{model_class}: added {', '.join(add)}")
    return applied


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

_EMOJI = {ERROR: "❌", WARN: "⚠️", INFO: "ℹ️"}


def render_markdown(findings: list[Finding], applied: list[str]) -> str:
    lines = [
        "## MCP ↔ API conformance report",
        "",
        "_Auto-generated by `scripts/check_api_conformance.py`. Do not edit by hand; "
        "it is refreshed by the `api_conformance` workflow._",
        "",
    ]
    if applied:
        lines.append("### Auto-applied enum additions")
        lines += [f"- {msg}" for msg in applied]
        lines.append("")
        lines.append(
            "> ⚠️ Update the corresponding tool docstrings in `server.py` that "
            "enumerate these values, then verify tests pass."
        )
        lines.append("")

    actionable = [f for f in findings if f.is_actionable]
    if actionable:
        lines.append("### Actionable drift")
        lines.append("")
        lines.append("| Level | Tool / model | Finding |")
        lines.append("|-------|--------------|---------|")
        for f in actionable:
            detail = f" _{f.detail}_" if f.detail else ""
            lines.append(f"| {_EMOJI[f.level]} {f.level} | `{f.tool}` | {f.summary}{detail} |")
        lines.append("")
    elif not applied:
        lines.append("No outstanding drift. ✅")
        lines.append("")

    informational = [f for f in findings if f.level == INFO]
    if informational:
        lines.append("### Informational (no action required)")
        lines.append("")
        for f in informational:
            lines.append(f"- `{f.tool}`: {f.summary}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_text(findings: list[Finding], applied: list[str]) -> str:
    out: list[str] = []
    for msg in applied:
        out.append(f"applied  {msg}")
    for f in findings:
        line = f"{f.level:5}  {f.tool}: {f.summary}"
        if f.detail:
            line += f"\n         → {f.detail}"
        out.append(line)
    if not out:
        out.append("No drift detected.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spec",
        default=LIVE_SPEC_URL,
        help="OpenAPI source: http(s) URL or local file path (default: live spec).",
    )
    parser.add_argument(
        "--apply-enums",
        action="store_true",
        help="Auto-add newly discovered enum values to orchestramcp/models.py.",
    )
    parser.add_argument("--report-md", help="Write a Markdown report to this path (for PR bodies).")
    parser.add_argument("--json", action="store_true", help="Emit findings as JSON to stdout.")
    args = parser.parse_args(argv)

    spec = load_spec(args.spec)
    findings = run_checks(spec)

    applied: list[str] = []
    if args.apply_enums:
        applied = apply_enum_additions(findings)
        # Applied additions are no longer outstanding drift.
        findings = [f for f in findings if not f.data.get("add")]

    if args.report_md:
        Path(args.report_md).write_text(render_markdown(findings, applied), encoding="utf-8")

    if args.json:
        print(
            json.dumps(
                {
                    "applied": applied,
                    "findings": [
                        {"level": f.level, "tool": f.tool, "summary": f.summary, "detail": f.detail}
                        for f in findings
                    ],
                },
                indent=2,
            )
        )
    else:
        print(render_text(findings, applied))

    return 1 if any(f.is_actionable for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
