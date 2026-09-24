from __future__ import annotations

from copy import deepcopy

import pytest
from tools.core_rules_order84_audit import REPORT, ROOT, load_audit, markdown, validate_audit
from tools.core_rules_order84_capture import capture_literals


def test_order84_inventory_and_generated_report_are_complete_and_negative() -> None:
    audit = load_audit()
    validate_audit(audit, roadmap=(ROOT / "docs/CORE_RULES_REMEDIATION_ROADMAP.md").read_text())
    assert REPORT.read_text() == markdown(audit)
    duplicated_number = [r for r in audit["source_inventory"] if r["locator"] == "09.07.01"]
    assert len(duplicated_number) == 2
    assert len({r["row_id"] for r in duplicated_number}) == 2
    assert len({r["title"] for r in duplicated_number}) == 2
    assert sum(r["category"] == "FAQ" for r in audit["source_inventory"]) == 59


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_category",
        "missing_faq",
        "missing_block",
        "missing_disposition",
        "missing_owner",
        "orphan_finding",
        "missing_obligation",
        "claim_clause_certificate",
        "claim_source_version",
        "claim_game_timing",
        "claim_closure",
    ],
)
def test_order84_rejects_omissions_and_false_certification(mutation: str) -> None:
    audit = deepcopy(load_audit())
    if mutation == "missing_category":
        audit["category_reviews"].pop()
    elif mutation == "missing_faq":
        audit["source_inventory"].pop()
    elif mutation == "missing_block":
        audit["source_inventory"][0]["blocks"].pop()
    elif mutation == "missing_disposition":
        audit["row_reviews"].pop()
    elif mutation == "missing_owner":
        audit["findings"].pop()
    elif mutation == "orphan_finding":
        audit["findings"][0]["source_rows"] = ["unknown-source-row"]
    elif mutation == "missing_obligation":
        audit["obligation_reviews"].pop()
    elif mutation == "claim_clause_certificate":
        audit["row_reviews"][0]["clause_certification"] = "certified"
    elif mutation == "claim_source_version":
        audit["observation"]["app_data_version"] = "946"
    elif mutation == "claim_game_timing":
        audit["complete_game_performance"]["mean_seconds"] = 0
    else:
        audit["caudit_01_closed"] = True
    with pytest.raises(ValueError, match="Order 84"):
        validate_audit(audit)


def test_order84_rejects_missing_canonical_followup() -> None:
    roadmap = (ROOT / "docs/CORE_RULES_REMEDIATION_ROADMAP.md").read_text()
    roadmap = roadmap.replace("| C01-07 |", "| C01-99 |", 1)
    with pytest.raises(ValueError, match="canonical roadmap owners"):
        validate_audit(load_audit(), roadmap=roadmap)


@pytest.mark.parametrize("literal", ["{x:1,x:2}", "{x:run()}", "[1,run()]"])
def test_order84_capture_does_not_execute_or_silently_accept_ambiguous_data(literal: str) -> None:
    script = f"let x={literal},m=[{{id:'faq'}}],c={{}},u={{}},f={{}}"
    with pytest.raises(ValueError, match="Audit capture"):
        capture_literals(script)


def test_order84_capture_retains_exact_strings_without_evaluating_them() -> None:
    script = r"""let x=[{text:['run()', 'two\nlines']}],m=[{id:'faq'}],c={},u={},f={}"""
    captured = capture_literals(script)
    assert captured["categories"] == [{"text": ["run()", "two\nlines"]}]
