"""Keep random melee generation in the recorded pre-target commitment owner."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_random_melee_retry_and_replacement_do_not_generate_dice() -> None:
    for name in (
        "melee_commitment_dispatch.py",
        "melee_target_replacement.py",
        "melee_attack_counts.py",
    ):
        tree = ast.parse((ENGINE / name).read_text())
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name | ast.Attribute)
        }
        assert not calls.intersection({"roll_random_characteristic", "attacks_for_profile"})
    for path in ENGINE.rglob("*.py"):
        assert '"random_melee_split_unsupported"' not in path.read_text()


def test_all_fight_hosts_share_the_committed_declaration_boundary() -> None:
    phase = (ENGINE / "phases/fight.py").read_text()
    assert "from warhammer40k_core.engine.phases.fight_melee import" in phase
    lifecycle = (ENGINE / "lifecycle.py").read_text()
    assert (
        "validate_melee_commitment_history(self)" in lifecycle
        or "validate_melee_commitment_history(lifecycle)" in lifecycle
    )
    assert "_melee_commitment_dispatch.decision_dispatch_handlers(self)" in lifecycle


def test_extra_attacks_commitment_never_offers_a_skip() -> None:
    tree = ast.parse((ENGINE / "melee_weapon_commitment.py").read_text())
    assert not any(
        isinstance(node, ast.Constant) and node.value == "skip_extra" for node in ast.walk(tree)
    )
    validator = (ENGINE / "fight_weapon_selection.py").read_text()
    assert 'violation_code="melee_extra_attacks_weapon_required"' in validator


def test_deferred_allocation_uses_current_sequence_without_global_presence_grant() -> None:
    tree = ast.parse((ENGINE / "attack_sequence_group_selection.py").read_text())
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "damage_allocation_target_state"
    ]
    assert len(calls) == 1
    assert any(
        keyword.arg == "attack_sequence"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "attack_sequence"
        for keyword in calls[0].keywords
    )
    presence = (ENGINE / "retained_model_presence.py").read_text()
    assert "pending_attack_destructions" not in presence
