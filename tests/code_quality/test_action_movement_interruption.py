"""Core 16.01 keeps completed-move authority separate from endpoint deltas."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_action_interruption_uses_one_completed_move_authority() -> None:
    tree = ast.parse((ENGINE / "primary_mission_action_interruptions.py").read_text())
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "displacements" for node in ast.walk(tree)
    )
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for name in (
        "_first_interruption_evidence",
        "validate_primary_mission_action_interruption_evidence",
    ):
        assert "_transition_evidence" in ast.unparse(functions[name])
    assert "distances_from_completion" in ast.unparse(functions["_transition_evidence"])
    assert (
        "reconcile_primary_mission_action_interruptions"
        in (ENGINE / "move_completion_triggers.py").read_text()
    )
    assert (
        '"mission_action_interrupted"'
        not in (ENGINE / "phases/movement_fall_back_embark.py").read_text()
    )
    assert (
        "validate_mission_action_movement_history"
        in (ENGINE / "primary_mission_restore_integrity.py").read_text()
    )
    history = ast.unparse(functions["validate_mission_action_movement_history"])
    assert "terminals[0]" not in history
    assert history.index("validate_mission_action_terminal_event(") < history.index(
        "_first_interruption_evidence("
    )
    assert (
        "validate_mission_action_terminal_event("
        in (ENGINE / "primary_mission_action_integrity.py").read_text()
    )
    terminal = (ENGINE / "mission_action_terminal_integrity.py").read_text()
    assert "_validate_completion_timing_and_boundary(" in terminal
    assert "mission_action_for_state(" in terminal
    assert "ObjectiveControlTiming.TURN_END" in terminal
    assert "def _validate_completion_boundary_event(" in terminal
    terminal_functions = {
        node.name: node for node in ast.parse(terminal).body if isinstance(node, ast.FunctionDef)
    }
    terminal_validation = ast.unparse(terminal_functions["validate_mission_action_terminal_event"])
    assert terminal_validation.index("_validate_mission_action_start_state(") < (
        terminal_validation.index("if action.status")
    )
    assert terminal_validation.index("_validate_mission_action_start_state(") < (
        terminal_validation.index("_validate_completion_timing_and_boundary(")
    )
    start_validation = ast.unparse(terminal_functions["_validate_mission_action_start_state"])
    assert "expected_started.to_payload()" in start_validation
    assert "validate_mission_action_event_context(" in start_validation
    assert "expected_started" not in (ENGINE / "primary_mission_action_integrity.py").read_text()
    assert (
        "def _validate_completion_boundary_event("
        not in (ENGINE / "primary_mission_action_integrity.py").read_text()
    )


@pytest.mark.parametrize(
    "baseline",
    [
        "base.json",
        "r77_001/base.json",
        "r77_001_boundary/base.json",
        "r77_001_start_binding/base.json",
    ],
)
def test_order77_matched_completed_move_cost_evidence(baseline: str) -> None:
    folder = ROOT / "docs/performance/order77"
    base, head = (json.loads((folder / name).read_text()) for name in (baseline, "head.json"))
    budgets = json.loads((folder / "budgets.json").read_text())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "library_versions",
        "timing_boundary",
        "workload",
    ):
        assert base[key] == head[key], key
    _assert_versioned_fixture_inputs(base["hashes"], head["hashes"])
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert len(base["samples"]) == len(head["samples"]) == budgets["required_completed_submissions"]
    assert head["full_game_certified"] is False
    for old, new in zip(base["samples"], head["samples"], strict=True):
        assert (old["case"], old["repeat"]) == (new["case"], new["repeat"])
        assert new["status"] == "waiting_for_decision"
        assert new["action_status"] == "interrupted"
        assert new["seconds"] <= budgets["maximum_submission_seconds"]
        assert (
            new["seconds"]
            <= old["seconds"] * budgets["maximum_ratio"] + budgets["jitter_allowance_seconds"]
        )

        assert new["restore_seconds"] <= budgets["maximum_restore_seconds"]
        assert (
            new["restore_seconds"]
            <= old["restore_seconds"] * budgets["maximum_ratio"]
            + budgets["jitter_allowance_seconds"]
        )


@pytest.mark.parametrize("baseline", ["r77_001_boundary", "r77_001_start_binding"])
def test_order77_completed_secondary_restore_cost_evidence(baseline: str) -> None:
    folder = ROOT / "docs/performance/order77"
    base = json.loads((folder / baseline / "completion-base.json").read_text())
    head = json.loads((folder / "r77_001_boundary/completion-head.json").read_text())
    budgets = json.loads((folder / "budgets.json").read_text())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "library_versions",
        "timing_boundary",
    ):
        assert base[key] == head[key], key
    _assert_versioned_fixture_inputs(base["hashes"], head["hashes"])
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert head["full_game_certified"] is False
    # Reuse the existing fifteen-sample requirement and unchanged restore budgets.
    assert len(base["samples"]) == len(head["samples"]) == budgets["required_completed_submissions"]
    for old, new in zip(base["samples"], head["samples"], strict=True):
        assert old["repeat"] == new["repeat"]
        assert old["action_status"] == new["action_status"] == "completed"
        assert new["seconds"] <= budgets["maximum_restore_seconds"]
        assert new["seconds"] <= (
            old["seconds"] * budgets["maximum_ratio"] + budgets["jitter_allowance_seconds"]
        )


def _assert_versioned_fixture_inputs(base: dict[str, str], head: dict[str, str]) -> None:
    migration = json.loads(
        (ROOT / "docs/performance/order79/inherited-fixture-migration.json").read_text()
    )
    changes = migration["changed_files"]
    assert set(changes) == {
        "tests/mission_action_history_helpers.py",
        "tests/phase17n_primary_mission_helpers.py",
    }
    assert base.keys() == head.keys()
    for name in base:
        if name in changes:
            assert base[name] == changes[name]["base_sha256"], name
            assert head[name] == changes[name]["head_sha256"], name
        else:
            assert base[name] == head[name], name
    # The movement workload uses these unchanged roster/mission initializers;
    # whole-file changes are confined to separate turn-end fixture functions.
    expected = migration["unchanged_primary_fixture_entrypoints"]
    assert set(expected) == {"phase17n_event_setup", "phase17n_state_with_setup"}
    tree = ast.parse((ROOT / "tests/phase17n_primary_mission_helpers.py").read_text())
    actual = {
        node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in expected
    }
    assert actual == expected
