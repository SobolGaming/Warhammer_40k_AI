"""Order 49 keeps reroll and targeting authority shared and bounded."""

import ast
import json
from pathlib import Path

from warhammer40k_core.engine.stratagem_catalog import (
    eleventh_edition_core_stratagem_catalog_records,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def _calls(filename: str) -> set[str]:
    return {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(ast.parse((ENGINE / filename).read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }


def test_charge_rerolls_use_shared_dice_and_stratagem_owners() -> None:
    assert "request_command_reroll_if_available" in _calls("charge_roll_flow.py")
    assert "stratagem_use_options_for_handler_from_index" in _calls("command_reroll_windows.py")
    assert "_selected_command_point_cost" in _calls("command_reroll_windows.py")
    assert "charge_reroll_permission_for_unit" in _calls("heroic_intervention_rolls.py")
    assert "validate_stratagem_use_history" in _calls("heroic_intervention_rolls.py")
    assert "validate_mutation_decision_closure" in _calls("charge_roll_flow.py")
    for name in ("charge_declaration.py", "heroic_intervention_rolls.py"):
        tree = ast.parse((ENGINE / name).read_text())
        assert not any(
            isinstance(node, ast.keyword) and node.arg == "reroll_forbidden_rule_ids"
            for node in ast.walk(tree)
        )
    assert (
        "phase15a:charge-roll-command-reroll-forbidden"
        not in (ENGINE / "charge_roll_reroll_requests.py").read_text()
    )


def test_command_reroll_targets_the_rolling_rules_unit() -> None:
    definition = next(
        r.definition
        for r in eleventh_edition_core_stratagem_catalog_records()
        if r.definition.stratagem_id == "command-reroll"
    )
    assert definition.target_spec.target_kind.value == "friendly_unit"
    assert definition.target_spec.target_policy_id == "command_reroll_unit"
    assert "charge_roll" in definition.eligible_roll_types


def test_replay_and_persistence_share_recorded_automatic_progress() -> None:
    assert "advance_recorded_automatic_progress" in _calls("replay.py")
    assert "advance_recorded_automatic_progress" in _calls("../adapters/local_session.py")


def test_order49_matched_charge_workload_meets_declared_budget() -> None:
    directory = ROOT / "docs/performance/order49"
    base, head, budget = (
        json.loads((directory / name).read_text())
        for name in ("base.json", "head.json", "budgets.json")
    )
    assert base["revision"] == budget["base_revision"]
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
        assert len(report["samples"]) == budget["samples"]
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * budget["maximum_mean_ratio"] + budget["mean_allowance_seconds"]
    )
    assert head["maximum_seconds"] <= budget["maximum_slice_seconds"]
    assert all(row["decision_count"] <= budget["maximum_decisions"] for row in head["samples"])
    assert all(row["event_count"] <= budget["maximum_events"] for row in head["samples"])
