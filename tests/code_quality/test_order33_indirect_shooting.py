from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def _function(path: Path, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.parse(path.read_text()).body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_indirect_visibility_does_not_supply_an_obsolete_hit_modifier() -> None:
    candidate = _function(ENGINE / "shooting_targets.py", "_target_candidate")
    indirect = next(
        node
        for node in ast.walk(candidate)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "indirect_no_visible"
    )
    assert not any(isinstance(node, ast.AugAssign) for node in ast.walk(indirect))
    modifiers = ast.parse((ENGINE / "attack_hit_modifiers.py").read_text())
    assert "INDIRECT_FIRE_NO_VISIBLE_RULE_ID" not in {
        node.id for node in ast.walk(modifiers) if isinstance(node, ast.Name)
    }


def test_indirect_stationary_and_observer_queries_use_durable_presence_authorities() -> None:
    path = ENGINE / "phases/shooting_targeting.py"
    stationary = _function(path, "_rules_unit_remained_stationary")
    attributes = {node.attr for node in ast.walk(stationary) if isinstance(node, ast.Attribute)}
    assert "normal_move_states_for_unit_phase" in attributes
    assert "movement_phase_state" not in attributes
    observer = _function(path, "_target_visible_to_friendly_unit")
    attributes = {node.attr for node in ast.walk(observer) if isinstance(node, ast.Attribute)}
    assert "placed_army_for_player_or_none" in attributes
    assert "placed_army_for_player" not in attributes


def test_completed_indirect_slice_stays_within_versioned_work_budgets() -> None:
    from scripts.measure_indirect_shooting import sample

    budgets = json.loads((ROOT / "docs/performance/order33/budgets.json").read_text())
    for name, visible, observer in (
        ("visible-self-observer", True, False),
        ("unseen-no-observer", False, False),
        ("unseen-friendly-observer", False, True),
    ):
        result = sample(visible=visible, observer=observer, profile=True)
        assert result["hit_count"] == 1
        counts = result["work_counts"]
        assert isinstance(counts, dict)
        for metric, maximum in budgets["work_limits"][name].items():
            assert counts.get(metric, 0) <= maximum, (name, metric, counts)
        assert counts["_target_visible_to_friendly_unit"] == 2
