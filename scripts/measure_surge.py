"""Matched Surge path validation: maximal and deliberately incomplete approaches."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.surge_helpers import SOURCE, surge_descriptor, surge_lifecycle

from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-layout", choices=("base", "head"), required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    module = (
        "warhammer40k_core.engine.triggered_movement"
        if args.runtime_layout == "base"
        else "warhammer40k_core.engine.triggered_movement_resolution"
    )
    resolve_triggered_movement = importlib.import_module(module).resolve_triggered_movement
    setup_start = time.perf_counter()
    lifecycle = surge_lifecycle()
    state = lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    placement = scenario.battlefield_state.unit_placement_by_id(SOURCE)
    descriptor = surge_descriptor()
    paths = tuple(
        PathWitness.for_paths(
            tuple(
                (
                    model.model_instance_id,
                    (model.pose, Pose.at(model.pose.position.x, model.pose.position.y + distance)),
                )
                for model, distance in zip(placement.model_placements, distances, strict=True)
            )
        )
        for distances in ((3, 3, 3, 3, 3), (3, 3, 3, 3, 1))
    )
    setup_seconds = time.perf_counter() - setup_start
    rows = []
    for _ in range(7):
        start = time.perf_counter()
        results = tuple(
            resolve_triggered_movement(
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                unit_placement=placement,
                descriptor=descriptor,
                path_witness=path,
                battle_round=1,
            )
            for path in paths
        )
        rows.append(
            {
                "seconds": time.perf_counter() - start,
                "accepted": [result.is_valid for result in results],
                "path_result_counts": [len(result.path_validation_results) for result in results],
            }
        )
    durations = [row["seconds"] for row in rows]
    report = {
        "workload_id": "order52-surge-v1",
        "revision": args.revision,
        "engine_build_id": current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "mode": "uninstrumented_timing",
        "setup_seconds": setup_seconds,
        "timing_boundary": "Two resolver calls; fixture and witness setup excluded",
        "scenario": {
            "models": 10,
            "moving_models": 5,
            "terrain_count": 0,
            "maximum_inches": 3,
            "paths_inches": [[3, 3, 3, 3, 3], [3, 3, 3, 3, 1]],
            "decision_policy": "fixed witnessed endpoints",
            "game_id": state.game_id,
        },
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("uv.lock", "tests/surge_helpers.py", "scripts/measure_surge.py")
        },
        "samples": rows,
        "mean_seconds": statistics.mean(durations),
        "maximum_seconds": max(durations),
        "median_seconds": statistics.median(durations),
        "completion_rate": 1,
        "full_game_certified": False,
        "correctness_note": "The base accepts incomplete approach and is only a cost comparison.",
        "budgets": {"maximum_seconds": 0.5, "mean_ratio": 2.0, "mean_additive_seconds": 0.02},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
