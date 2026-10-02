"""Current Shock uses shared setup; retain historical Order 62 measurement evidence."""

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_shock_candidates_do_not_snapshot_transport_engagements() -> None:
    source = (ENGINE / "phases/movement_transports.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    candidate_builder = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_disembark_candidates_for_movement_unit"
    )
    snapshots = [
        keyword.value
        for node in ast.walk(candidate_builder)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "start_engaged_enemy_unit_instance_ids"
    ]
    assert snapshots
    assert all(isinstance(value, ast.Tuple) and not value.elts for value in snapshots)


def test_shock_has_no_queue_producer_or_mandatory_restore_disposition() -> None:
    source = (ENGINE / "phases/movement_placement_proposals.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {node for node in tree.body if isinstance(node, ast.FunctionDef)}
    assert not any(node.name == "_start_shock_disembark_forced_fight_activations" for node in names)
    assert "install_forced_fight_queue" not in source
    assert "current_physically_engaged_enemy_rules_unit_ids(" in source
    history = (ENGINE / "shock_disembark_history.py").read_text(encoding="utf-8")
    assert "historical_engaged_enemy_rules_unit_ids(" in history
    assert "event_index=index + 1" in history
    assert "Shock Disembark setup must be unengaged" in history
    lifecycle = (ENGINE / "lifecycle_state_validation.py").read_text(encoding="utf-8")
    assert "validate_shock_disembark_engagement_history(" in lifecycle
    assert "_validate_shock_disembark_fight_history" not in lifecycle
    shared = (ENGINE / "consolidation_fight_queue.py").read_text(encoding="utf-8")
    assert "install_forced_fight_queue(" in shared


def test_order62_matched_measurement_gate() -> None:
    folder = ROOT / "docs/performance/order62"
    base = json.loads((folder / "base.json").read_text(encoding="utf-8"))
    head = json.loads((folder / "head.json").read_text(encoding="utf-8"))
    for key in ("workload_id", "hashes", "platform", "python", "cpu", "memory_bytes", "budgets"):
        assert head[key] == base[key]
    for report in (base, head):
        assert len(report["samples"]) == 7
        assert all(sample["complete"] for sample in report["samples"])
        assert report["completion_rate"] == 1
        assert report["full_game_certified"] is False
    budget = base["budgets"]
    assert (
        head["mean_seconds"]
        <= base["mean_seconds"] * budget["mean_ratio"] + budget["mean_additive_seconds"]
    )
    assert (
        head["maximum_seconds"]
        <= base["maximum_seconds"] * budget["maximum_ratio"] + budget["maximum_additive_seconds"]
    )
