"""Order 46 source, shared Charge arithmetic and retained performance evidence."""

import ast
import json
from pathlib import Path

import pytest
from tools.build_core_charge_source import ARTIFACT_PATH, AUDIT_PATH, build_payloads

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_charge_source_artifact_and_observation_are_reproducible() -> None:
    package, audit = build_payloads()
    assert json.loads(ARTIFACT_PATH.read_text()) == package
    assert json.loads(AUDIT_PATH.read_text()) == audit


def test_charge_consumers_share_current_budget_and_target_authority() -> None:
    for filename in (
        "phases/charge.py",
        "catalog_setup_reactive_shoot_charge.py",
        "catalog_setup_reactive_charge_move.py",
        "charge_target_continuation.py",
    ):
        tree = ast.parse((ENGINE / filename).read_text())
        calls = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "current_charge_movement_budget" in calls, filename
    resolver = (ENGINE / "charge_movement_budget.py").read_text()
    assert "charge_roll_modifiers_for_unit(" in resolver
    assert "move_distance_modifiers(" in resolver
    assert "resolve_distance_deltas(" in resolver
    continuation = (ENGINE / "charge_target_continuation.py").read_text()
    assert "replacement_request(" in continuation
    assert "charge_target_candidates(" in continuation
    assert "charge_target_constraints_satisfied(" in continuation
    replacement_owner = next(
        node
        for node in ast.parse(continuation).body
        if isinstance(node, ast.FunctionDef) and node.name == "is_charge_target_replacement_request"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "target_selection"
        for node in ast.walk(replacement_owner)
    ), "Replacement ownership must survive an erased target commitment."
    lifecycle = (ENGINE / "lifecycle.py").read_text()
    assert "validate_restored_charge_targets(" in lifecycle
    assert "refresh_pending_charge_move(" in lifecycle
    authority = (ENGINE / "charge_move_event_authority.py").read_text()
    assert "validate_charge_selection_reference(" in authority
    for filename in (
        "target_replacement_dispatch.py",
        "shooting_target_replacement_authority.py",
        "charge_target_authority.py",
    ):
        assert "is_charge_target_replacement_request(" in (ENGINE / filename).read_text()
    dispatch = (ENGINE / "target_replacement_dispatch.py").read_text()
    assert "current_battle_phase is BattlePhase.CHARGE" not in dispatch


@pytest.mark.parametrize("prefix", ["", "review-"])
def test_charge_slice_evidence_is_comparable_and_within_versioned_budgets(prefix: str) -> None:
    directory = ROOT / "docs/performance/order46"
    base = json.loads((directory / f"{prefix}base.json").read_text())
    head = json.loads((directory / f"{prefix}head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
    assert base["workload_id"] == head["workload_id"] == budget["workload_id"]
    for field in (
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "mode",
        "concurrency",
        "model_count",
        "terrain_count",
        "timing_boundary",
        "scenario",
        "hashes",
    ):
        assert base[field] == head[field], field
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert report["engine_build_id"].startswith("warhammer40k-core-v2:")
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * budget["mean_regression_factor"]
        + budget["mean_regression_allowance_seconds"]
    )
    assert head["maximum_seconds"] <= budget["maximum_seconds"]
    assert all(row["decision_count"] <= budget["maximum_decisions"] for row in head["samples"])
    assert all(row["event_count"] <= budget["maximum_events"] for row in head["samples"])
