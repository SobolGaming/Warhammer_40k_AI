"""Matched R86-001 rotated-boundary query diagnostic; no full-game claim."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
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

    from warhammer40k_core.build_identity import current_engine_build_id
    from warhammer40k_core.geometry.base import OvalBase, RectangularBase
    from warhammer40k_core.geometry.pose import Pose
    from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    sw = "table-quarter:south-west"
    angle = math.radians(17)
    support = math.hypot(2 * math.cos(angle), math.sin(angle))
    sine = 2**-28
    cases = (
        ("reported-outer-contained", 1.7694605058044857, 10, 101, RectangularBase(6.2, 2.4), sw),
        ("reported-divider-overlap", 27.775333743981115, 10, 17, RectangularBase(4, 2), None),
        ("ellipse-outer-contained", math.nextafter(support, math.inf), 10, 17, OvalBase(4, 2), sw),
        ("ellipse-outer-overlap", math.nextafter(support, -math.inf), 10, 17, OvalBase(4, 2), None),
        ("ellipse-exact-contact", 10, 5 * sine, math.degrees(sine), OvalBase(6, 8 * sine), sw),
    )
    rows = []
    for case, x, y, facing, base, expected in cases:
        model = Model(case, Pose.at(x, y, facing_degrees=facing), base, ModelVolume(1))
        samples, counts = [], []
        for _ in range(9):
            start = perf_counter()
            count = sum(
                wholly_within_table_quarter(
                    models=(model,), center_x=30, center_y=30, divider_width_inches=1 / 25.4
                )
                is not None
                for _ in range(100)
            )
            samples.append((perf_counter() - start) / 100)
            counts.append(count)
        rows.append(
            {
                "case": case,
                "model": model.to_payload(),
                "expected_quarter": expected,
                "iterations": 100,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "qualifying_counts": counts,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "r86-001-rotated-boundary-queries-v1",
        "revision": args.revision,
        "runtime_build_id": current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "full_game_certified": False,
        "timing_boundary": "one rotated geometry query; setup excluded; 9 batches of 100",
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in ("uv.lock", "scripts/measure_order86_boundaries.py")
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
