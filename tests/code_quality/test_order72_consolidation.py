"""Resolved source identity, shared mode authority and component cost guards."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


def test_order72_source_resolution_is_reproducible() -> None:
    subprocess.run(
        [sys.executable, "tools/build_core_fight_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_order72_live_and_historical_response_share_resolved_mode_authority() -> None:
    engine = ROOT / "src/warhammer40k_core/engine"
    for name in ("consolidation_fight_queue.py", "consolidation_fight_history.py"):
        text = (engine / name).read_text(encoding="utf-8")
        tree = ast.parse(text)
        calls = [
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        assert calls.count("consolidation_response_source_id") == 1
        assert "ConsolidationModeKind" not in text
        assert "ONGOING_SOURCE_ID" not in text
        assert "source_text" not in text
    for path in engine.rglob("*.py"):
        assert "ongoing-consolidation-erratum" not in path.read_text(encoding="utf-8")


def test_order72_matched_engaging_fight_restore_replay_cost() -> None:
    folder = ROOT / "docs/performance/order72"
    base = json.loads((folder / "base.json").read_bytes())
    head = json.loads((folder / "head.json").read_bytes())
    budget = json.loads((folder / "budgets.json").read_bytes())
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for key in (
        "workload",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "hashes",
        "timing_boundary",
        "scenario",
    ):
        assert base[key] == head[key], key
    assert head["workload"] == budget["workload"]
    for name, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )
    assert len(base["samples_seconds"]) == len(head["samples_seconds"]) == budget["samples"]
    assert base["completion_rate"] == head["completion_rate"] == 1
    for metric in ("mean_seconds", "maximum_seconds"):
        assert head[metric] <= base[metric] * budget["ratio"] + budget["additive_seconds"]
