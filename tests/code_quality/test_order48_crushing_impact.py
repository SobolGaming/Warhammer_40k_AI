"""Keep Charge-end Stratagems, casualty routing and performance on shared owners."""

import ast
import json
from pathlib import Path

from warhammer40k_core.engine.core_stratagem_mortal_wound_continuation import (
    core_stratagem_mortal_wound_bindings,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_stratagems_2026_08 import (
    source_rule_by_id,
)

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def _calls(filename: str) -> list[str]:
    return [
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(ast.parse((ENGINE / filename).read_text()))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    ]


def test_charge_move_discovery_and_stratagem_damage_share_authorities() -> None:
    for filename in (
        "phases/charge_move_completed_hooks.py",
        "phases/movement_completion_candidates.py",
    ):
        assert "charge_move_stratagem_candidates" in _calls(filename)
    assert "stratagem_timing_candidates" in _calls("move_completed_stratagem_candidates.py")
    calls = _calls("stratagems_effect_handlers.py")
    assert calls.count("crushing_impact_mortal_wounds") == 2
    assert calls.count("continue_rule_mortal_wound_application") == 2
    assert calls.count("resolve_rule_mortal_wound_decision") == 2
    assert "continue_mortal_wound_application" not in calls
    assert "resolve_mortal_wound_decision" not in calls
    assert "continue_applied_mortal_wound_destruction_with_rule_reactions" in _calls(
        "mortal_wound_destruction_routing.py"
    )
    for filename in (
        "move_completed_stratagem_candidates.py",
        "mortal_wound_destruction_routing.py",
    ):
        strings = [
            node.value
            for node in ast.walk(ast.parse((ENGINE / filename).read_text()))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        assert not any("crushing-impact" in value or "explosives" in value for value in strings)


def test_crushing_impact_support_and_completion_hooks_are_source_linked() -> None:
    row = source_rule_by_id("crushing-impact")
    assert row.load_support_status == "loaded"
    assert row.semantic_execution_status == "executable_engine_runtime"
    bindings = core_stratagem_mortal_wound_bindings()
    assert len({binding.hook_id for binding in bindings}) == 3
    assert {binding.source_id for binding in bindings} == {
        row.source_id,
        source_rule_by_id("explosives").source_id,
    }
    assert all(binding.completion_handler is not None for binding in bindings)


def test_order48_matched_charge_and_new_capability_meet_versioned_budgets() -> None:
    directory = ROOT / "docs/performance/order48"
    base = json.loads((directory / "base.json").read_text())
    head = json.loads((directory / "head.json").read_text())
    budget = json.loads((directory / "budgets.json").read_text())
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
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * budget["maximum_mean_ratio"] + budget["mean_allowance_seconds"]
    )
    assert head["maximum_seconds"] <= budget["maximum_slice_seconds"]
    assert all(row["decision_count"] <= budget["maximum_decisions"] for row in head["samples"])
    assert all(row["event_count"] <= budget["maximum_events"] for row in head["samples"])
    capability = json.loads((directory / "crushing-impact.json").read_text())
    limits = budget["new_capability"]
    assert capability["workload_id"] == limits["workload_id"]
    assert capability["engine_build_id"] == head["engine_build_id"]
    assert capability["full_game_certified"] is False
    assert {row["scenario_id"] for row in capability["scenarios"]} == {
        "ordinary",
        "both_caps_and_feel_no_pain",
        "both_attached_units_destroyed",
    }
    for scenario in capability["scenarios"]:
        assert scenario["completion_rate"] == 1
        assert len(scenario["samples"]) == limits["samples"]
        assert scenario["maximum_seconds"] <= limits["maximum_slice_seconds"]
        for sample in scenario["samples"]:
            assert sample["decision_count"] <= limits["maximum_decisions"]
            assert sample["event_count"] <= limits["maximum_events"]
            for side in ("source", "enemy"):
                assert sample[f"{side}_mortal_wounds"] <= limits["maximum_mortal_wounds_per_side"]
