"""Matched ordinary/reactive movement costs for the Order 53 source descriptor."""

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
from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.triggered_movement_resolution import (
    resolve_triggered_movement,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                keywords=replace(
                    sheet.keywords, keywords=("VEHICLE", "WALKER", "SUPER_HEAVY_WALKER")
                ),
            )
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("mover",),
        catalog=catalog,
        game_id="order53-move-abilities",
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
        reactive = tuple(
            resolve_triggered_movement(
                scenario=scenario,
                ruleset_descriptor=lifecycle.state.runtime_ruleset_descriptor(),
                unit_placement=placement,
                descriptor=descriptor,
                path_witness=path,
                battle_round=1,
                turn_player_id="player-a",
                take_to_the_skies=False,
            )
            for path in paths
        )
        ordinary = tuple(
            resolve_normal_move(
                scenario=scenario,
                ruleset_descriptor=lifecycle.state.runtime_ruleset_descriptor(),
                unit_placement=placement,
                state=lifecycle.state,
                path_witness=path,
            )
            for path in paths
        )
        results = (*ordinary, *reactive)
        rows.append(
            {
                "seconds": time.perf_counter() - start,
                "accepted": [result.is_valid for result in results],
                "path_result_counts": [len(result.path_validation_results) for result in results],
                "path_violation_codes": [
                    [
                        violation.violation_code
                        for result in resolution.path_validation_results
                        for violation in result.violations
                    ]
                    for resolution in results
                ],
            }
        )
    durations = [row["seconds"] for row in rows]
    report = {
        "workload_id": "order53-move-abilities-v1",
        "revision": args.revision,
        "engine_build_id": current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "timing_boundary": (
            "Four resolver calls (two ordinary, two reactive); "
            "catalog, fixture and witness construction excluded"
        ),
        "scenario": {
            "game_id": "order53-move-abilities",
            "models": 10,
            "moving_models": 5,
            "terrain_count": 0,
            "paths_inches": [2, 3],
            "descriptor_limit_inches": 4,
            "keywords": ["VEHICLE", "WALKER", "SUPER_HEAVY_WALKER"],
        },
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/phase15a_charge_declaration_helpers.py",
                "scripts/measure_order53.py",
            )
        },
        "samples": rows,
        "mean_seconds": statistics.mean(durations),
        "median_seconds": statistics.median(durations),
        "maximum_seconds": max(durations),
        "completion_rate": 1,
        "full_game_certified": False,
        "correctness_note": (
            "Four open-terrain paths crossing friendly Vehicle models; "
            "base lacks the ability and rejects them, head accepts them."
        ),
        "budgets": {"mean_ratio": 2, "mean_additive_seconds": 0.02, "maximum_seconds": 0.5},
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
