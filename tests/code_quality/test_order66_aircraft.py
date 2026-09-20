"""Category 23 authority, source artifacts and bounded component evidence."""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from warhammer40k_core.build_identity import verified_engine_build_identity

ROOT = Path(__file__).resolve().parents[2]


def test_aircraft_source_is_reproducible_and_hover_state_is_retired() -> None:
    subprocess.run(
        [sys.executable, "tools/build_core_aircraft_source.py", "--check"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    aircraft = (ROOT / "src/warhammer40k_core/engine/aircraft.py").read_text(encoding="utf-8")
    definitions = {
        node.name
        for node in ast.parse(aircraft).body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
    }
    assert "HoverModeState" not in definitions
    assert "resolve_aircraft_reserve_transition" not in definitions
    state = (ROOT / "src/warhammer40k_core/engine/game_state_payloads.py").read_text(
        encoding="utf-8"
    )
    assert "hover_mode_states" not in state
    boundary = (ROOT / "src/warhammer40k_core/engine/boundary_rule_flow.py").read_text(
        encoding="utf-8"
    )
    assert "aircraft_turn_end_binding()" in boundary


def test_aircraft_matched_component_evidence() -> None:
    folder = ROOT / "docs/performance/order66"
    base = json.loads((folder / "base.json").read_text(encoding="utf-8"))
    head = json.loads((folder / "head.json").read_text(encoding="utf-8"))
    budgets = json.loads((folder / "budgets.json").read_text(encoding="utf-8"))
    for key in (
        "workload_id",
        "platform",
        "python",
        "cpu",
        "memory_bytes",
        "cpu_allocation",
        "concurrency",
        "scenario",
        "timing_boundary",
        "hashes",
    ):
        assert base[key] == head[key], key
    assert head["workload_id"] == budgets["workload_id"]
    assert head["runtime_build_id"] == verified_engine_build_identity().build_id
    for name, digest in head["hashes"].items():
        assert (
            hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() == digest
        )
    for old, current in zip(base["rows"], head["rows"], strict=True):
        assert old["fleet_size"] == current["fleet_size"]
        assert len(old["samples"]) == len(current["samples"]) == 7
        assert all(row["complete"] for row in (*old["samples"], *current["samples"]))
        assert all(row["returned_aircraft"] == current["fleet_size"] for row in current["samples"])
        for metric, additive in (
            ("guard_seconds", "guard_additive_seconds"),
            ("boundary_seconds", "boundary_additive_seconds"),
        ):
            before, after = old["summary"][metric], current["summary"][metric]
            assert after["mean"] <= before["mean"] * budgets["mean_ratio"] + budgets[additive]
            assert (
                after["maximum"]
                <= before["maximum"] * budgets["maximum_ratio"]
                + budgets["maximum_additive_seconds"]
            )
