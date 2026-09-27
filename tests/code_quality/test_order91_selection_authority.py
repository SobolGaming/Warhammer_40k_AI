"""Unit/type eligibility cannot depend on the existence of a legal attack target."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src/warhammer40k_core/engine"


def test_shooting_selection_has_no_target_candidate_gate() -> None:
    tree = ast.parse((ROOT / "phases/shooting_eligibility.py").read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in {
            "_legal_shooting_unit_ids",
            "_legal_shooting_types_for_rules_unit",
            "shooting_rules_unit_is_eligible_to_shoot",
        }:
            calls = {
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
            }
            assert not calls & {
                "_rules_unit_has_legal_shooting_declaration",
                "_cached_shooting_target_candidate_for_model",
            }


def test_empty_completion_cannot_fabricate_attack_participation() -> None:
    text = (ROOT / "shooting_without_attacks.py").read_text()
    for forbidden in (
        "AttackSequence(",
        "record_ranged_attack_history(",
        "record_one_shot_weapon_selected(",
        "apply_hidden_status_loss_after_ranged_attacks(",
    ):
        assert forbidden not in text
    assert (
        "complete_shooting_without_attacks(" in (ROOT / "phases/shooting_requests.py").read_text()
    )
    assert (
        "validate_no_attack_completions(" in (ROOT / "activity_restriction_restore.py").read_text()
    )
