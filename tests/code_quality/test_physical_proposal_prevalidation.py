"""Prevent physical payload/context rejection from mutating replay authority."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "src/warhammer40k_core/engine"


def test_physical_prevalidation_owners_do_not_write_authoritative_history() -> None:
    owners = {
        "physical_proposal_validation.py": {
            "physical_proposal_invalid_status",
            "parse_movement_proposal_payload",
        },
        "physical_proposal_context.py": {"invalid_physical_proposal_spatial_context_status"},
        "triggered_movement.py": {
            "invalid_triggered_movement_proposal_status",
            "_reject_invalid_triggered_movement_proposal",
        },
        "attack_sequence_destroyed_transport.py": {"_destroyed_transport_proposal_invalid_status"},
    }
    for filename, names in owners.items():
        tree = ast.parse((ENGINE / filename).read_text())
        functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
        for name in names:
            calls = [node for node in ast.walk(functions[name]) if isinstance(node, ast.Call)]
            for call in calls:
                text = ast.unparse(call.func)
                assert text not in {
                    "decisions.event_log.append",
                    "decisions.submit_result",
                    "decisions.request_decision",
                }, (filename, name, text)
    for filename, alias in (
        ("phases/charge.py", "_reject_invalid_charge_proposal"),
        ("phases/movement_resolution_flow.py", "_reject_invalid_proposal"),
    ):
        tree = ast.parse((ENGINE / filename).read_text())
        assert not any(
            isinstance(node, ast.FunctionDef) and node.name == alias for node in tree.body
        )
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "warhammer40k_core.engine.physical_proposal_validation"
            and any(
                row.name == "physical_proposal_invalid_status" and row.asname == alias
                for row in node.names
            )
            for node in tree.body
        )


def test_order76_matched_proposal_cost_and_pure_rejection_evidence() -> None:
    folder = ROOT / "docs/performance/order76"
    base, head = (json.loads((folder / name).read_text()) for name in ("base.json", "head.json"))
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
        "hashes",
    ):
        assert base[key] == head[key], key
    for name, digest in head["hashes"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    assert len(base["samples"]) == len(head["samples"]) == head["completed_submissions"] == 30
    assert head["full_game_certified"] is False
    for old, new in zip(base["samples"], head["samples"], strict=True):
        assert (old["family"], old["malformed"], old["repeat"]) == (
            new["family"],
            new["malformed"],
            new["repeat"],
        )
        assert new["status"] == ("invalid" if new["malformed"] else "waiting_for_decision")
        if new["malformed"]:
            assert new["event_delta"] == 0
        assert new["seconds"] <= budgets["maximum_submission_seconds"]
        assert (
            new["seconds"]
            <= old["seconds"] * budgets["maximum_ratio"] + budgets["jitter_allowance_seconds"]
        )
