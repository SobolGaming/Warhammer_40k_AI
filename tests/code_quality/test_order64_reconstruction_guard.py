"""Keep authenticated restore/fork work bounded as the replay suffix grows."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Literal, cast

import pytest
from scripts.measure_ingress_reconstruction import CHECKPOINTS

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/performance/order64"


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
@pytest.mark.parametrize("operation", ["restore", "fork"])
def test_post_ingress_reconstruction_work_budget(
    checkpoint: str, operation: Literal["restore", "fork"]
) -> None:
    budgets = json.loads((EVIDENCE / "budgets.json").read_text(encoding="utf-8"))
    # Keep cProfile state independent of earlier audits in the xdist worker,
    # matching the standalone evidence process. Profile exactly one real
    # reconstruction; retain every authentication and work-budget assertion.
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; "
            "from scripts.measure_ingress_reconstruction import prepare, sample; "
            "print(json.dumps(sample(prepare(sys.argv[1]), sys.argv[2], profile=True)))",
            checkpoint,
            operation,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    row = json.loads(completed.stdout)
    counts = cast(dict[str, int], row["work_counts"])
    limits = budgets["work_limits"][checkpoint]
    assert row["complete"] is True
    assert counts.keys() == limits.keys() | {"total_profiled_calls"}
    # A lower count in these authentication primitives would be a correctness
    # regression too. The equality/evidence checks in sample still apply.
    assert counts["replay.py:run"] == 1
    assert counts["lifecycle.py:from_payload"] == 4
    assert counts["lifecycle.py:submit_decision"] == limits["lifecycle.py:submit_decision"]
    assert counts["reserve_arrival_resolution.py:resolve_reserve_arrival"] == 1
    for metric, limit in limits.items():
        assert counts[metric] <= limit, (checkpoint, operation, metric, counts)
    base = json.loads((EVIDENCE / "base-reconstruction.json").read_text(encoding="utf-8"))
    reference = next(
        row
        for row in base["rows"]
        if (row["checkpoint"], row["operation"]) == (checkpoint, operation)
    )
    assert counts["total_profiled_calls"] <= (
        reference["profile"]["work_counts"]["total_profiled_calls"]
        * budgets["total_profiled_call_ratio"]
    )


def test_matched_reconstruction_timing_evidence() -> None:
    base = json.loads((EVIDENCE / "base-reconstruction.json").read_text(encoding="utf-8"))
    head = json.loads((EVIDENCE / "head-reconstruction.json").read_text(encoding="utf-8"))
    budgets = json.loads((EVIDENCE / "budgets.json").read_text(encoding="utf-8"))
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id, (
        "Order 64 head timing evidence is stale for the current engine build. "
        "Refresh qualified measurements as required by docs/performance/order64/README.md."
    )
    for field in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "cpu_allocation",
        "memory_bytes",
        "concurrency",
        "timing_boundary",
        "scenario",
        "input_hash_algorithm",
        "hashes",
    ):
        assert base[field] == head[field], field
    assert base["workload_id"] == budgets["workload_id"]
    assert head["input_hash_algorithm"] == "sha256-normalized-text-lf"
    for name, digest in head["hashes"].items():
        content = (ROOT / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        assert hashlib.sha256(content).hexdigest() == digest, name
    expected = {
        (checkpoint, operation) for checkpoint in CHECKPOINTS for operation in ("restore", "fork")
    }
    for report in (base, head):
        assert report["full_game_certified"] is False
        assert len(report["rows"]) == len(expected)
        assert {(r["checkpoint"], r["operation"]) for r in report["rows"]} == expected
        for row in report["rows"]:
            assert len(row["samples"]) == 7
            assert all(sample["complete"] for sample in row["samples"])
            assert row["completion_rate"] == 1
            assert row["mean_seconds"] > 0
    limits = budgets["timing_limits"]
    for before, after in zip(base["rows"], head["rows"], strict=True):
        for field in ("game_id", "unit_count", "model_count", "decision_records", "event_records"):
            assert before[field] == after[field], field
        assert (before["checkpoint"], before["operation"]) == (
            after["checkpoint"],
            after["operation"],
        )
        assert (
            after["mean_seconds"]
            <= before["mean_seconds"] * limits["mean_ratio"] + limits["mean_additive_seconds"]
        )
        assert (
            after["maximum_seconds"]
            <= before["maximum_seconds"] * limits["maximum_ratio"]
            + limits["maximum_additive_seconds"]
        )


def test_order64_source_generator_is_reproducible() -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "tools/build_core_reserve_lifetimes_source.py"), "--check"],
        cwd=ROOT,
        check=True,
    )


def test_every_shared_movement_consumer_uses_the_shared_lock() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in (
        "charge_eligibility.py",
        "fight_rules_unit_movement.py",
        "phases/fight.py",
        "physical_proposal_context.py",
        "triggered_movement_selection.py",
        "triggered_movement_handler_impl.py",
        "phases/movement_validation.py",
    ):
        assert "movement_lock_reason" in (engine / name).read_text(encoding="utf-8"), name
    assert "validate_ingress_movement_mutation(" in (
        engine / "phase_movement_history.py"
    ).read_text(encoding="utf-8")


def test_reposition_and_ingress_cannot_reset_turn_history_or_effect_duration() -> None:
    """20.02 applies equally to every history kind, including Disembark/Battle-shock."""
    engine = ROOT / "src/warhammer40k_core/engine"
    protected = {
        "advanced_unit_states",
        "fell_back_unit_states",
        "disembarked_unit_states",
        "battle_shocked_unit_ids",
        "battle_shocked_unit_states",
        "persisting_effects",
    }
    reset_calls = {
        "clear_turn_action_states",
        "replace_battle_shock_state",
        "expire_persisting_effects_at_boundary",
    }
    owners = {
        "game_state.py": {"reposition_unit_to_strategic_reserves", "replace_reserve_state"},
        "phases/movement_reinforcements.py": {"_apply_valid_reinforcement_placement"},
        "stratagems_ingress.py": {"_apply_rapid_ingress_placement"},
    }
    for filename, names in owners.items():
        tree = ast.parse((engine / filename).read_text(encoding="utf-8"))
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name in names
        ]
        assert {node.name for node in functions} == names, filename
        for function in functions:
            for node in ast.walk(function):
                if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Store):
                    assert node.attr not in protected, (filename, node.attr)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    assert node.func.attr not in reset_calls, (filename, node.func.attr)
