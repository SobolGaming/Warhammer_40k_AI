"""Order 94 retains complete evidence without rewriting the negative audit."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from tools.core_rules_order84_capture import fingerprint
from tools.core_rules_order94_audit import (
    AUDIT,
    REPORT,
    ROOT,
    load_audit,
    markdown,
    source_observation_fingerprint,
    validate_audit,
)


def test_order94_complete_source_and_generated_review() -> None:
    audit = load_audit()
    assert audit.selected_observation.app_data_version is None
    assert audit.selected_observation.app_build is None
    assert audit.selected_observation.provider_name == "40k.app"
    assert audit.finding_id == "C15-10"
    assert not audit.runtime_input
    assert not audit.caudit_01_closed
    assert len(audit.clause_reviews) == 10
    assert REPORT.read_text(encoding="utf-8") == markdown(audit)
    validate_audit(audit)


def test_order94_observation_identity_excludes_implementation_status() -> None:
    observation = load_audit().selected_observation
    metadata = observation.model_dump()
    metadata.update(load_support_status="loaded", semantic_execution_status="executable")
    assert observation.source_observation_sha256 == source_observation_fingerprint(metadata)
    metadata["observed_at"] = "2026-09-29T00:00:00Z"
    assert observation.source_observation_sha256 != source_observation_fingerprint(metadata)


def test_order94_rehashing_truncated_evidence_cannot_rewrite_the_review() -> None:
    payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    observation = payload["selected_observation"]
    observation["transcription"] = "truncated"
    import hashlib

    observation["transcription_sha256"] = hashlib.sha256(b"truncated").hexdigest()
    observation["source_observation_sha256"] = fingerprint(
        {
            key: value
            for key, value in observation.items()
            if key
            not in {"source_observation_sha256", "load_support_status", "semantic_execution_status"}
        }
    )
    with pytest.raises(ValueError, match="Order 94 immutable review identity"):
        load_audit(payload=payload)


@pytest.mark.parametrize(
    "field",
    [
        "provider_name",
        "source_url",
        "observed_at",
        "app_data_version",
        "app_build",
        "policy_id",
        "provider_non_affiliation_recorded",
        "rule_source_id",
        "transcription",
        "transcription_sha256",
        "source_observation_sha256",
    ],
)
def test_order94_rejects_changed_or_missing_observation_tuple(field: str) -> None:
    original = json.loads(AUDIT.read_text(encoding="utf-8"))
    for remove in (True, False):
        payload = deepcopy(original)
        if remove:
            del payload["selected_observation"][field]
        else:
            payload["selected_observation"][field] = "946"
        with pytest.raises(ValueError, match="Order 94"):
            load_audit(payload=payload)


@pytest.mark.parametrize("index", range(10))
def test_order94_rejects_missing_reconciliation_clause(index: int) -> None:
    payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    payload["clause_reviews"].pop(index)
    with pytest.raises(ValueError, match="Order 94"):
        load_audit(payload=payload)


@pytest.mark.parametrize(
    "mutation",
    [
        "truncated_selection",
        "gdm_selected",
        "false_version_match",
        "false_certificate",
        "missing_history",
        "changed_official_hash",
        "changed_gdm_block",
        "changed_owner",
        "unknown_field",
        "wrong_shape",
    ],
)
def test_order94_rejects_incomplete_or_false_closure(mutation: str) -> None:
    payload = json.loads(AUDIT.read_text(encoding="utf-8"))
    if mutation == "truncated_selection":
        payload["selected_observation"]["transcription"] = "Heroic Intervention"
    elif mutation == "gdm_selected":
        payload["selected_observation"]["provider_name"] = "Game Datamissions"
    elif mutation == "false_version_match":
        payload["comparison_status"] = "same_version_equivalent"
    elif mutation == "false_certificate":
        payload["caudit_01_closed"] = True
    elif mutation == "missing_history":
        del payload["historical_gdm"]
    elif mutation == "changed_official_hash":
        payload["official_evidence"]["sha256"] = "0" * 64
    elif mutation == "changed_gdm_block":
        payload["historical_gdm"]["blocks"].pop()
    elif mutation == "changed_owner":
        payload["clause_reviews"][0]["engine_owner"] = "missing.py"
    elif mutation == "unknown_field":
        payload["source_version"] = "946"
    else:
        payload = list[object]()
    with pytest.raises(ValueError, match="Order 94"):
        load_audit(payload=payload)


def test_order94_rejects_changed_retained_capture(tmp_path: Path) -> None:
    audit = load_audit()
    capture = audit.selected_observation.capture
    destination = tmp_path / capture.path
    destination.parent.mkdir(parents=True)
    destination.write_text("truncated capture", encoding="utf-8")
    with pytest.raises(ValueError, match=r"Order 94.*capture"):
        validate_audit(audit, root=tmp_path)


def test_order94_review_does_not_relabel_historical_negative_audit() -> None:
    audit = load_audit()
    historical = json.loads((ROOT / audit.historical_gdm.audit_path).read_text())
    assert historical["outcome"] == "gaps_found_not_certified"
    assert historical["observation"]["app_data_version"] is None
    assert not historical["caudit_01_closed"]
    assert next(f for f in historical["findings"] if f["finding_id"] == "C15-10")
