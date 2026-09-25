"""Matched reachability diagnostic for circular support bases with asymmetric bodies."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import math
import platform
from pathlib import Path
from time import perf_counter

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.geometry.base import CircularBase, RectangularBase
    from warhammer40k_core.geometry.model_body import ModelBodyPart
    from warhammer40k_core.geometry.movement_reachability import (
        MovementGoal,
        MovementReachabilityQuery,
        movement_reachability,
    )
    from warhammer40k_core.geometry.pathing import (
        PathValidationContext,
        PathWitness,
        TerrainPathLegalityContext,
    )
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    rows = []
    for bearing in (0.0, 7.0):

        def pose(x: float, facing: float = 0.0, bearing: float = bearing) -> Pose:
            angle = math.radians(bearing)
            return Pose.at(
                5 + (x - 5) * math.cos(angle),
                5 + (x - 5) * math.sin(angle),
                facing_degrees=facing + bearing,
            )

        source = Model(
            "source",
            pose(1.5),
            CircularBase(0.5),
            ModelVolume(2),
            body_parts=(ModelBodyPart("body", RectangularBase(4, 0.99), 0, 0, 0, 2, "fixture"),),
        )
        target = Model("target", pose(6), CircularBase(0.5), ModelVolume(2))
        witness = PathWitness.for_paths((("source", (pose(1.5), pose(1.5, 90), pose(3.5, 90))),))
        path = PathValidationContext(
            moving_model=source,
            witness=witness,
            battlefield_width_inches=10,
            battlefield_depth_inches=10,
            enemy_engagement_horizontal_inches=1.0,
            enemy_engagement_vertical_inches=5.0,
            enemy_models=(target,),
            may_end_in_enemy_engagement=True,
            may_transit_enemy_engagement=True,
            movement_distance_budget_inches=3.5,
        )
        terrain = TerrainPathLegalityContext(
            moving_model=source,
            witness=witness,
            terrain=(),
            terrain_movement_policy=RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy,
        )
        query = MovementReachabilityQuery(
            path_context=path,
            terrain_context=terrain,
            goal=MovementGoal(models=(target,), range_inches=1e-9),
        )
        samples = []
        statuses = []
        for _ in range(3):
            start = perf_counter()
            result = movement_reachability(query)
            samples.append(perf_counter() - start)
            statuses.append(result.status.value)
        rows.append({"bearing": bearing, "samples_seconds": samples, "statuses": statuses})
    cpu, memory = _host_inventory()
    report = {
        "workload": "order85-asymmetric-body-contact-search-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "competing_test_build_workers": False,
        "full_game_certified": False,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "rows": rows,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
