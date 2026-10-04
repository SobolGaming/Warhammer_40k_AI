"""Psychic ability classification stays source-bound and shared by mortal routes."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_direct_and_pending_mortal_owners_forward_both_damage_contexts() -> None:
    for filename in ("direct_mortal_wound_application.py", "mortal_wound_model_allocation.py"):
        calls = [
            node
            for node in ast.walk(ast.parse((ENGINE / filename).read_text(encoding="utf-8")))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id
            in {"record_mortal_wound_allocation_occurrence", "mortal_wound_feel_no_pain_sources"}
        ]
        assert calls
        for call in calls:
            assert {"destruction_evidence", "source_context"} <= {
                keyword.arg for keyword in call.keywords
            }, (filename, call.lineno)


def test_psychic_ability_damage_runtime_uses_structured_source_evidence() -> None:
    for filename in ("ability_damage_context.py", "feel_no_pain_conditions.py"):
        text = (ENGINE / filename).read_text(encoding="utf-8")
        assert "normalized_text" not in text
        assert "RuleSourceText" not in text
        assert "Blue Scribes" not in text
        assert "Xirat" not in text
    deferred = (ENGINE / "attack_sequence_deferred_mortals.py").read_text(encoding="utf-8")
    assert "source_permission_damage_context(" in deferred
