"""Keep eligibility ahead of geometry and reserve enumeration bounded per window."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

import pytest
from scripts.measure_rapid_ingress import CASES, sample

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case", CASES)
def test_rapid_ingress_work_budget(case: str) -> None:
    budget = json.loads((ROOT / "docs/performance/order35/budgets.json").read_text())
    row = sample(case=case, profile=True)
    counts = cast(dict[str, int], row["work_counts"])
    limits = cast(dict[str, int], budget["work_limits"][case])
    for metric, maximum in limits.items():
        assert counts.get(metric, 0) <= maximum, (case, metric, counts)
    if case in {"first_round", "aircraft"}:
        assert row["eligible_targets"] == 0
        assert row["target_unavailable_reason"] == (
            "rapid_ingress_first_battle_round"
            if case == "first_round"
            else "rapid_ingress_aircraft_target"
        )
        assert counts.get("resolve_reserve_arrival", 0) == 0
        assert counts.get("resolve_visibility_pair", 0) == 0
    else:
        assert row["submitted"] is True
        assert row["eligible_targets"] == (8 if case == "mixed" else 1)


def test_rapid_ingress_target_preflight_does_not_reenumerate_all_reserves() -> None:
    tree = ast.parse((ROOT / "src/warhammer40k_core/engine/stratagems_targeting.py").read_text())
    binding = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_target_binding_error"
    )
    calls = {
        n.func.id
        for n in ast.walk(binding)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "rapid_ingress_target_error" in calls
    assert "_rapid_ingress_unit_ids" not in calls


def test_pending_rapid_ingress_uses_target_aware_affordability_with_runtime_modifiers() -> None:
    tree = ast.parse((ROOT / "src/warhammer40k_core/engine/rapid_ingress_authority.py").read_text())
    calls = [
        (node.func.id, node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert not any(name == "_stratagem_unavailable_reason" for name, _ in calls)
    checks = [node for name, node in calls if name == "_parameterized_stratagem_unavailable_reason"]
    assert len(checks) == 1
    assert any(
        keyword.arg == "stratagem_cost_modifier_registry"
        and isinstance(keyword.value, ast.Name)
        and keyword.value.id == "stratagem_cost_modifier_registry"
        for keyword in checks[0].keywords
    )
