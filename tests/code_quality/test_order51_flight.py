"""Flight source, turn-history ownership and inherited Charge slice budgets."""

import ast
import json
from pathlib import Path

import pytest

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_flying_2026_09

ROOT = Path(__file__).resolve().parents[2]


def test_heavy_does_not_depend_on_temporary_movement_phase_state() -> None:
    source = ROOT / "src/warhammer40k_core/engine/phases/shooting_targeting.py"
    tree = ast.parse(source.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_rules_unit_within_heavy_movement_allowance"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "movement_phase_state"
        for node in ast.walk(function)
    )


def test_reactive_path_validation_cannot_use_the_raw_descriptor_budget() -> None:
    source = ROOT / "src/warhammer40k_core/engine/triggered_movement.py"
    tree = ast.parse(source.read_text())
    budgets = [
        keyword.value
        for call in ast.walk(tree)
        if isinstance(call, ast.Call)
        for keyword in call.keywords
        if keyword.arg == "movement_distance_budget_inches"
    ]
    assert budgets
    assert not any(
        isinstance(budget, ast.Attribute)
        and budget.attr == "max_distance_inches"
        and isinstance(budget.value, ast.Name)
        and budget.value.id == "descriptor"
        for budget in budgets
    )


def test_flying_source_pin_rejects_altered_artifact() -> None:
    artifact = Path(core_flying_2026_09.__file__).parent / "artifacts/package.json"
    data = artifact.read_bytes()
    assert core_flying_2026_09.validate_source_artifact_bytes(data).rules
    with pytest.raises(core_flying_2026_09.FlyingSourceError, match="reviewed pin"):
        core_flying_2026_09.validate_source_artifact_bytes(data + b"\n")


@pytest.mark.parametrize("prefix", ["ordinary", "heroic"])
def test_flight_retains_inherited_charge_slice_budgets(prefix: str) -> None:
    directory = ROOT / "docs/performance/order51"
    base, head, budget = (
        json.loads((directory / name).read_text())
        for name in (f"{prefix}-base.json", f"{prefix}-head.json", "budgets.json")
    )
    assert base["revision"] == budget["base_revision"]
    for field in (
        "workload_id",
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


def test_reactive_review_preserves_workload_and_inherited_budgets() -> None:
    directory = ROOT / "docs/performance/order51"
    base, head, budget = (
        json.loads((directory / name).read_text())
        for name in ("reactive-review-base.json", "reactive-review-head.json", "budgets.json")
    )
    assert base["revision"] == "09aaa696e19a86f9b610f12b3ae34426af738175"
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "mode",
        "concurrency",
        "timing_boundary",
        "scenario",
        "hashes",
    ):
        assert base[key] == head[key], key
    for report, acceptance in ((base, [True, True]), (head, [True, False])):
        assert len(report["samples"]) == budget["samples"]
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
        assert all(row["accepted"] == acceptance for row in report["samples"])
        assert all(row["path_result_counts"] == [5, 5] for row in report["samples"])
    assert head["mean_seconds"] <= (
        base["mean_seconds"] * budget["maximum_mean_ratio"] + budget["mean_allowance_seconds"]
    )
    assert head["maximum_seconds"] <= budget["maximum_slice_seconds"]
