"""Order 95 records a complete negative survey without manufacturing certification."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from tools.core_rules_order95_audit import AUDIT, REPORT, load_audit, markdown, validate_audit


def test_order95_inventory_and_report_are_complete() -> None:
    audit = load_audit()
    assert audit["outcome"] == "gaps_found_not_certified"
    assert not audit["caudit_01_closed"]
    assert not audit["operative_clause_certification_complete"]
    assert len(audit["category_reviews"]) == 25
    assert len(audit["row_reviews"]) == 345
    assert len(audit["changelog_reviews"]) == 91
    assert (
        audit["source_selection"]["heroic_intervention_override"]["audit_id"]
        == "order94-2026-09-28"
    )
    assert REPORT.read_text() == markdown(audit)
    assert "| 931:change:15 | FAQ 55 |" in markdown(audit)
    validate_audit(audit)


@pytest.mark.parametrize(
    "field",
    [
        "row_reviews",
        "category_reviews",
        "changelog_reviews",
        "version_inventory",
        "retained_core_packages",
        "september10_reviews",
        "cross_category_reviews",
        "prior_finding_reviews",
        "findings",
        "evidence_files",
    ],
)
def test_order95_rejects_missing_duplicate_or_rewritten_evidence(field: str) -> None:
    original = json.loads(AUDIT.read_text())
    for mutation in ("missing", "duplicate", "rewrite"):
        payload = deepcopy(original)
        if mutation == "missing":
            payload[field].pop()
        elif mutation == "duplicate":
            payload[field].append(payload[field][0])
        else:
            payload[field][0]["status"] = "certified"
        with pytest.raises(ValueError, match="Order 95"):
            load_audit(payload=payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("caudit_01_closed", True),
        ("operative_clause_certification_complete", True),
        ("outcome", "certified"),
        ("reviewed_commit", "main"),
        ("runtime_input", True),
    ],
)
def test_order95_rejects_false_closure(field: str, value: object) -> None:
    payload = json.loads(AUDIT.read_text())
    payload[field] = value
    with pytest.raises(ValueError, match="Order 95"):
        load_audit(payload=payload)


def test_order95_keeps_older_changes_and_resolved_exceptions_distinct() -> None:
    audit = load_audit()
    entries = {row["entry_id"]: row for row in audit["changelog_reviews"]}
    assert entries["931:change:7"]["disposition"] == "superseded_by_owner_app_v946"
    assert entries["909:change:28"]["evidence_id"] == "heavy-flight"
    assert entries["895:change:1"]["evidence_id"] == "normal-move"
    assert entries["909:change:12"]["evidence_id"] == "control-first"
    assert entries["946:change:1"]["source_rows"] == ["rule:18:18.04.01:1"]
    assert all(row["clause_certification"] == "open" for row in audit["row_reviews"])
    assert {row["finding_id"] for row in audit["findings"]} == {"C04-06", "C24-11", "CAUDIT-02"}


def test_order95_requires_every_new_repair_before_pfinal() -> None:
    from tools.core_rules_order95_audit import ROOT

    roadmap = (ROOT / "docs/CORE_RULES_REMEDIATION_ROADMAP.md").read_text()
    for owner in ("P04E", "P24K", "PEVIDENCE"):
        line = next(line for line in roadmap.splitlines() if f"| {owner} |" in line)
        with pytest.raises(ValueError, match="Order 95"):
            validate_audit(load_audit(), roadmap=roadmap.replace(line, ""))


def test_order95_changelog_parser_accepts_only_one_literal_version_inventory() -> None:
    from tools.core_rules_order95_audit import changelog_versions

    versions: list[dict[str, object]] = [{"version": "946", "changes": []}]
    chunk = json.dumps([1, '"versions":' + json.dumps(versions)], separators=(",", ":"))
    html = f"<script>self.__next_f.push({chunk})</script>"
    assert changelog_versions(html) == versions
    for malformed in ("", html + html, html.replace('[{\\"version', '[0,{\\"version')):
        with pytest.raises(ValueError, match="Order 95"):
            changelog_versions(malformed)


def test_order95_capture_verification_rejects_drift_before_parsing(tmp_path: Path) -> None:
    from tools.core_rules_order95_audit import verify_captures

    path = tmp_path / "capture"
    path.write_text("changed observation")
    with pytest.raises(ValueError, match="Order 95 Core capture hash"):
        verify_captures(load_audit(), core=path)
    with pytest.raises(ValueError, match="Order 95 changelog capture hash"):
        verify_captures(load_audit(), changelog=path)
