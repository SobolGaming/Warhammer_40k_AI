"""Matched reactive-flight path validation at and beyond the adjusted limit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from dataclasses import replace
from pathlib import Path

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses

from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
    resolve_triggered_movement,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet, keywords=replace(sheet.keywords, keywords=(*sheet.keywords.keywords, "FLY"))
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=catalog,
        game_id="order51-review-reactive",
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
    )
    assert lifecycle.state is not None
    scenario = battlefield_scenario_for_state(state=lifecycle.state)
    placement = scenario.battlefield_state.unit_placement_by_id(units["mover"].unit_instance_id)
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id="benchmark:reactive-normal",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=None,
            source_event_id=None,
        ),
        max_distance_inches=4,
    )
    paths = tuple(
        PathWitness.for_straight_line_endpoints(
            tuple(
                (
                    model.model_instance_id,
                    model.pose,
                    Pose.at(model.pose.position.x + distance, model.pose.position.y),
                )
                for model in placement.model_placements
            )
        )
        for distance in (2, 3)
    )
    rows = []
    for _ in range(7):
        start = time.perf_counter()
        results = tuple(
            resolve_triggered_movement(
                scenario=scenario,
                ruleset_descriptor=lifecycle.state.runtime_ruleset_descriptor(),
                unit_placement=placement,
                descriptor=descriptor,
                path_witness=path,
                battle_round=1,
                take_to_the_skies=True,
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
        "workload_id": "order51-review-reactive-flight-v1",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "engine_build_id": current_engine_build_id(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"])
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "timing_boundary": "Two resolver calls; catalog, fixture and witness construction excluded",
        "scenario": {
            "game_id": "order51-review-reactive",
            "models": 10,
            "moving_models": 5,
            "terrain_count": 0,
            "paths_inches": [2, 3],
            "descriptor_limit_inches": 4,
            "flight_limit_inches": 2,
            "take_to_the_skies": True,
            "hover": False,
        },
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/phase15a_charge_declaration_helpers.py",
                "scripts/measure_reactive_flight.py",
            )
        },
        "samples": rows,
        "mean_seconds": statistics.mean(durations),
        "median_seconds": statistics.median(durations),
        "maximum_seconds": max(durations),
        "completion_rate": 1,
        "full_game_certified": False,
        "correctness_note": "Base wrongly accepts three inches; compare cost only.",
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
