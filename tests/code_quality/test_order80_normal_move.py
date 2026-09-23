"""The once-per-phase limit has one occurrence-aware history owner."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


def test_normal_move_recording_is_owned_by_shared_completion() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    callers: list[str] = []
    for path in engine.rglob("*.py"):
        tree = ast.parse(path.read_text())
        if any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record_normal_move_state"
            for node in ast.walk(tree)
        ):
            callers.append(path.relative_to(engine).as_posix())
    assert callers == ["move_completion_triggers.py"]
    query = (engine / "normal_move_history.py").read_text()
    assert "row.turn_player_id == state.active_player_id" in query
    for name in (
        "phases/movement_validation.py",
        "phases/shooting_targeting.py",
        "phases/movement_transports.py",
        "triggered_movement_selection.py",
    ):
        assert "normal_move_states_for_unit_phase(" in (engine / name).read_text()
    handler = ast.parse((engine / "triggered_movement_handler_impl.py").read_text())
    calls = [
        node
        for node in ast.walk(handler)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_triggered_movement"
    ]
    assert len(calls) == 3
    assert all(any(keyword.arg == "turn_player_id" for keyword in node.keywords) for node in calls)


def test_order80_matched_occurrence_performance() -> None:
    folder = ROOT / "docs/performance/order80"
    base, head = (json.loads((folder / name).read_bytes()) for name in ("base.json", "head.json"))
    budget = json.loads((folder / "budgets.json").read_bytes())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "concurrency",
        "hashes",
        "timing_boundary",
    ):
        assert base[key] == head[key], key
    assert head["workload"] == budget["workload"]
    for path, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    assert [row["case"] for row in head["rows"]] == ["finite", "parameterized"]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        assert before["complete"]
        assert after["complete"]
        assert len(before["samples_seconds"]) == len(after["samples_seconds"]) == 3
        assert before["normal_move_available"] == [False] * 3
        assert after["normal_move_available"] == [True] * 3
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * budget["mean_ratio"] + budget["mean_additive_seconds"]
        )
        assert after["maximum_seconds"] <= budget["maximum_seconds"]
    assert not head["full_game_certified"]
