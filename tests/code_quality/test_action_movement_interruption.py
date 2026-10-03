"""Core 16.01 keeps completed-move authority separate from endpoint deltas."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from tests.performance_evidence_helpers import (
    assert_historical_report,
    historical_input_bytes,
    historical_input_text,
)

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
    assert_historical_report(head)
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
        assert hashlib.sha256(historical_input_bytes(name)).hexdigest() == digest, name
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
    assert_historical_report(head)
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
        assert hashlib.sha256(historical_input_bytes(name)).hexdigest() == digest, name
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
        historical_input_text("docs/performance/order79/inherited-fixture-migration.json")
    )
    changes = migration["changed_files"]
    occurrence_migration = json.loads(
        historical_input_text("docs/performance/order80/inherited-fixture-migration.json")
    )["changed_files"]
    assert set(occurrence_migration) == {"tests/phase17n_primary_mission_helpers.py"}
    assert set(changes) == {
        "tests/mission_action_history_helpers.py",
        "tests/phase17n_primary_mission_helpers.py",
    }
    quarter_migration = json.loads(
        historical_input_text("docs/performance/order86/inherited-fixture-migration.json")
    )["changed_files"]
    assert set(quarter_migration) == {
        "tests/phase17n_secondary_certification_fixtures.py",
        "tests/phase17n_step6g_secondary_certification_helpers.py",
    }
    movement_proof = json.loads(
        historical_input_text("docs/performance/order93/inherited-fixture-migration.json")
    )
    movement_migration = movement_proof["changed_files"]
    movement_helper = "tests/action_movement_interruption_helpers.py"
    assert movement_proof["schema_version"] == 1
    assert set(movement_migration) == {movement_helper}
    assert movement_proof["base_revision"] == "d7bcb10bd9e34b1eabb060465be7f9517d8417eb"
    assert (
        movement_proof["runtime_build_id"]
        == json.loads(historical_input_text("docs/performance/order93/base.json"))[
            "runtime_build_id"
        ]
    )
    assert movement_proof["entrypoint"] == "action_movement_session"
    assert movement_proof["entrypoint_kwargs"] == {"pause_after_move": True}
    assert (
        movement_migration[movement_helper]["head_sha256"]
        == hashlib.sha256(historical_input_bytes(movement_helper)).hexdigest()
    )
    assert [row["case"] for row in movement_proof["cases"]] == [
        "translation",
        "return",
        "zero",
        "rotation",
        "rotation_return",
    ]
    for row in movement_proof["cases"]:
        assert row["base_payload_sha256"] == row["head_payload_sha256"]
        assert row["base_component_sha256"] == row["head_component_sha256"]
        assert set(row["base_component_sha256"]) == {
            "initial_lifecycle",
            "request",
            "pending_lifecycle",
            "submission",
            "status",
            "final_lifecycle",
            "restored_lifecycle",
        }
        assert row["submission_status"] == "waiting_for_decision"
        assert row["action_status"] == "interrupted"
        assert row["restored_payload_identical"] is True
        for digest in (row["base_payload_sha256"], *row["base_component_sha256"].values()):
            assert len(digest) == 64
            assert all(character in "0123456789abcdef" for character in digest)
    assert base.keys() == head.keys()
    for name in base:
        if name in changes:
            assert base[name] == changes[name]["base_sha256"], name
            expected_head = changes[name]["head_sha256"]
            if name in occurrence_migration:
                assert occurrence_migration[name]["base_sha256"] == expected_head
                expected_head = occurrence_migration[name]["head_sha256"]
            assert head[name] == expected_head, name
        elif name in quarter_migration:
            assert base[name] == quarter_migration[name]["base_sha256"], name
            assert head[name] == quarter_migration[name]["head_sha256"], name
        elif name in movement_migration:
            assert base[name] == movement_migration[name]["base_sha256"], name
            assert head[name] == movement_migration[name]["head_sha256"], name
        else:
            assert base[name] == head[name], name
    # The movement workload uses these unchanged roster/mission initializers;
    # whole-file changes are confined to separate turn-end fixture functions.
    expected = migration["unchanged_primary_fixture_entrypoints"]
    assert set(expected) == {"phase17n_event_setup", "phase17n_state_with_setup"}
    tree = ast.parse(historical_input_text("tests/phase17n_primary_mission_helpers.py"))
    actual = {
        node.name: hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in expected
    }
    assert actual == expected


def test_action_battle_shock_interruption_has_one_status_mutation_owner() -> None:
    for name, call in (
        ("battle_shock_resolution.py", "apply_battle_shock_result_state"),
        ("move_keyword_completion.py", "apply_direct_battle_shock_state"),
    ):
        tree = ast.parse((ENGINE / name).read_text())
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == call
        ]
        assert calls
        assert all(any(kw.arg == "decisions" for kw in node.keywords) for node in calls)
    owner = (ENGINE / "battle_shock_state.py").read_text()
    assert "interrupt_mission_actions_for_battle_shock(" in owner
    for path in ENGINE.rglob("*.py"):
        if path.name in {"actions.py", "primary_mission_action_interruptions.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "interrupt"
            and any(
                kw.arg == "reason"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value == "unit_battle_shocked"
                for kw in node.keywords
            )
            for node in ast.walk(tree)
        ), path
