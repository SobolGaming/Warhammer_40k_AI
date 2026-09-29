"""Optional rerolls cannot invent a player result inside an attack resolver."""

import ast
import hashlib
import json
from pathlib import Path

import pytest

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_every_engine_reroll_consumer_has_an_audited_authorizing_decision() -> None:
    # See ORDER_96_SCOPE_PLAN.md for each accepted-decision authority. The one
    # synthetic component result is Command Re-roll after the submitted CP choice.
    expected = {
        ("attack_sequence_dice_rerolls.py", "apply_source_backed_attack_dice_reroll_decision"),
        ("battle_shock_resolution.py", "apply_battle_shock_reroll_resolution_decision"),
        ("charge_roll_flow.py", "_apply_charge_roll_reroll_decision"),
        ("phases/movement_resolution_flow.py", "_apply_advance_roll_reroll_decision"),
        ("stratagems_core_handlers.py", "_apply_command_reroll_handler"),
        ("stratagems_core_handlers.py", "apply_command_reroll_decision"),
        ("surge_authority.py", "_validate_surge_granted_descriptor"),
        ("triggered_movement_selection.py", "apply_triggered_movement_distance_reroll_decision"),
    }
    observed: set[tuple[str, str]] = set()
    synthetic: set[tuple[str, str]] = set()
    for path in ENGINE.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for owner in ast.walk(tree):
            if not isinstance(owner, ast.FunctionDef):
                continue
            calls = [node for node in ast.walk(owner) if isinstance(node, ast.Call)]
            if not any(
                isinstance(node.func, ast.Attribute) and node.func.attr == "resolve_reroll"
                for node in calls
            ):
                continue
            key = (str(path.relative_to(ENGINE)), owner.name)
            observed.add(key)
            if any(
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "for_request"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "DecisionResult"
                for node in calls
            ):
                synthetic.add(key)
    assert observed == expected
    assert synthetic == {("stratagems_core_handlers.py", "_apply_command_reroll_handler")}


def test_twin_linked_uses_the_shared_optional_wound_permission_owner() -> None:
    intrinsic = (ENGINE / "intrinsic_attack_rerolls.py").read_text()
    assert "RerollPermission(" in intrinsic
    assert "SourceBackedRerollPermissionContext(" in intrinsic
    assert "DecisionResult" not in intrinsic
    assert "successful" not in intrinsic
    for path in ENGINE.glob("attack_sequence*.py"):
        assert "_reroll_wound_for_twin_linked_if_needed" not in path.read_text()
    lifecycle = (ENGINE / "lifecycle.py").read_text()
    assert "attack_reroll_dispatch_handler(self)" in lifecycle
    assert "validate_pending_attack_rerolls(lifecycle)" in lifecycle


@pytest.mark.parametrize("suffix", ["", "-sustained"])
def test_order96_performance_evidence_preserves_submitted_choice_work(suffix: str) -> None:
    directory = ROOT / "docs/performance/order96"
    base = json.loads((directory / f"base{suffix}.json").read_text())
    head = json.loads((directory / f"head{suffix}.json").read_text())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "fixture",
        "seeds",
        "policy",
        "timing_boundary",
        "concurrency",
        "coverage",
        "hashes",
    ):
        assert base[key] == head[key]
    for path, expected in head["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert head["concurrency"] == 1
    assert head["coverage"] is False
    assert head["completion_rate"] == 1.0
    assert head["full_game_samples"] == 0
    assert head["full_game_certified"] is False
    assert {(row["phase"], row["accept"]) for row in head["rows"]} == {
        (phase, accept) for phase in ("shooting", "fight") for accept in (False, True)
    }
    for row in head["rows"]:
        assert len(row["samples_seconds"]) == len(row["restore_seconds"]) == 5
        assert all(value > 0 for value in row["samples_seconds"] + row["restore_seconds"])
        if suffix:
            for work in row["work_counts"]:
                assert work["wounds"] == work["reroll_choices"] > 0
                assert work["rerolls"] == (work["wounds"] if row["accept"] else 0)
                assert work["automatic_weapon_rerolls"] == 0
                assert work["sustained_d3"] == work["critical_hits"] > 0
                assert work["hits"] == work["distinct_hit_contexts"] == 12
            continue
        assert (
            row["work_counts"]
            == [
                {
                    "wounds": 12,
                    "reroll_choices": 12,
                    "rerolls": 12 if row["accept"] else 0,
                    "automatic_weapon_rerolls": 0,
                }
            ]
            * 5
        )
