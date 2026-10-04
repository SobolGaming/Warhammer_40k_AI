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
