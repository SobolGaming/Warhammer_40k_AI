"""Order 50 guards against reintroducing a parallel Heroic Charge engine."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_heroic_provider_only_authorizes_the_shared_charge_owner() -> None:
    provider = (ENGINE / "heroic_intervention_rolls.py").read_text()
    calls = {
        node.func.id if isinstance(node.func, ast.Name) else node.func.attr
        for node in ast.walk(ast.parse(provider))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))
    }
    assert {
        "ChargeInterruption",
        "ChargeRollLimit",
        "ChargePhaseState",
        "charge_target_candidates",
    } <= calls
    assert (
        not {"DiceRollManager", "roll_fixed", "request_roll", "resolve_charge_move", "PathWitness"}
        & calls
    )
    assert "declared_target_unit_instance_ids_by_unit" in provider
    assert "charge_grants_fights_first" not in provider
    assert not (ENGINE / "lifecycle_heroic_intervention.py").exists()
    for path in ENGINE.rglob("*.py"):
        source = path.read_text()
        assert "heroic_intervention_charge_move_completed" not in source, path
        assert "heroic_intervention_reroll_context" not in source, path


@pytest.mark.parametrize("prefix", ["ordinary", "heroic"])
def test_order50_matched_slices_meet_declared_budgets(prefix: str) -> None:
    directory = ROOT / "docs/performance/order50"
    base, head, budget = (
        json.loads((directory / name).read_text())
        for name in (f"{prefix}-base.json", f"{prefix}-head.json", "budgets.json")
    )
    assert base["revision"] == budget["base_revision"]
    assert base["workload_id"] == head["workload_id"]
    assert head["workload_id"] in budget["workloads"]
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
