"""Matched whole-unit quarter witness diagnostic (no game-performance claim)."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", required=True, type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from tests.phase11c_command_phase_helpers import battle_state

    from warhammer40k_core.build_identity import current_engine_build_id
    from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
        _table_quarter_witness_or_none,
    )
    from warhammer40k_core.engine.rules_units import rules_unit_views_from_armies
    from warhammer40k_core.geometry.pose import Pose

    state = battle_state()
    battlefield = state.battlefield_state
    assert battlefield is not None
    view = rules_unit_views_from_armies(armies=tuple(state.army_definitions))[0]
    original = battlefield.unit_placement_by_id(view.unit_instance_id).model_placements
    radius = view.own_models[0].geometry.base_shape().max_radius()
    rows = []
    for gap in (0.01, 0.5 / 25.4, 0.02, 4.0):
        placements = tuple(
            replace(
                p, pose=Pose.at(battlefield.battlefield_width_inches / 2 - radius - gap, 4 + i * 2)
            )
            for i, p in enumerate(original)
        )
        samples, counts = [], []
        for _ in range(10):
            start = perf_counter()
            count = sum(
                _table_quarter_witness_or_none(
                    view=view, placements=placements, battlefield_state=battlefield
                )
                is not None
                for _ in range(100)
            )
            samples.append((perf_counter() - start) / 100)
            counts.append(count)
        rows.append(
            {
                "gap": gap,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "qualifying_counts": counts,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order86-five-model-quarter-witness-v1",
        "revision": args.revision,
        "runtime_build_id": current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "full_game_certified": False,
        "timing_boundary": (
            "one five-model primary quarter witness; fixture setup excluded; 10 batches of 100"
        ),
        "hashes": {
            p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (
                "uv.lock",
                "scripts/measure_order86.py",
                "tests/phase11c_command_phase_helpers.py",
            )
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
