"""The attack-mortal Core seam keeps source authority and shared mutation owners."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_additional_attack_mortal_source_rows_preserve_selected_authority() -> None:
    audit = json.loads((ROOT / "data/source_audits/order116/source.audit.json").read_bytes())
    raw = (ROOT / audit["source"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == audit["source_sha256"]
    exemplar = audit["official_exemplar"]
    assert hashlib.sha256((ROOT / exemplar["path"]).read_bytes()).hexdigest() == exemplar["sha256"]
    rows = {row["row_id"]: row for row in json.loads(raw)}
    assert audit["requirement"] == "06.02.01-obligation-02"
    for row in audit["selected_rows"]:
        assert row == rows[row["row_id"]]


def test_additional_attack_mortal_producer_and_mutation_have_shared_owners() -> None:
    calls: list[str] = []
    for path in ENGINE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "defer_additional_attack_mortals"
            ):
                calls.append(path.name)
    assert calls == ["attack_sequence_post_roll.py"]
    producer = (ENGINE / "additional_attack_mortals.py").read_text(encoding="utf-8")
    consumer = (ENGINE / "attack_sequence_deferred_mortals.py").read_text(encoding="utf-8")
    assert "additional_attack_mortal_permissions(" in producer
    assert "continue_mortal_wound_application(" in consumer
    assert "MortalWoundDestructionEvidence.for_attack_state(" in consumer
    for text in (producer, consumer):
        assert "Radiant Champion" not in text
        assert "Hallowed Ground" not in text
        assert ".lose_wounds(" not in text


def test_attack_mortal_identity_and_fnp_share_source_aware_owners() -> None:
    producer = (ENGINE / "additional_attack_mortals.py").read_text(encoding="utf-8")
    native = (ENGINE / "attack_sequence_post_roll.py").read_text(encoding="utf-8")
    normal = (ENGINE / "attack_sequence_validation.py").read_text(encoding="utf-8")
    mortal = (ENGINE / "mortal_wound_model_allocation.py").read_text(encoding="utf-8")
    deferred = (ENGINE / "deferred_mortal_wounds.py").read_text(encoding="utf-8")
    consumer = (ENGINE / "attack_sequence_deferred_mortals.py").read_text(encoding="utf-8")
    assert "attack_mortal_origin(" in producer
    assert "attack_mortal_origin(" in native
    assert "has_deferred_mortal_occurrence(" in producer
    assert "has_deferred_mortal_occurrence(" in native
    assert "feel_no_pain_source_applies_to_attack(" in normal
    assert "feel_no_pain_source_applies_to_mortal_wounds(" in mortal
    assert mortal.count("destruction_evidence=progress.destruction_evidence") == 2
    assert 'f"{self.source_kind}:{self.source_permission.effect_id}"' in deferred
    assert "deferred.application_suffix" in consumer
