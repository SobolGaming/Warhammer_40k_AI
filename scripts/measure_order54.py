"""Reproduce matched, uninstrumented oversized deployment resolver costs."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.large_model_setup_helpers import composite_deployment_case, oversized_deployment_case

from warhammer40k_core.engine.deployment import resolve_deployment_placement


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--composite", action="store_true")
    args = parser.parse_args()
    cases = tuple(
        oversized_deployment_case(zone_width=width, x=x)
        for width, x in ((3, None), (3, 5), (10, None), (10, 9))
    )
    if args.composite:
        cases += tuple(composite_deployment_case(redundant=value) for value in (False, True))
    first_state = cases[0][0]
    assert first_state.battlefield_state is not None
    assert first_state.mission_setup is not None
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        results = tuple(
            resolve_deployment_placement(
                state=state,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                request=request,
                proposal=proposal,
            )
            for state, request, proposal in cases
        )
        samples.append(
            {"seconds": time.perf_counter() - start, "accepted": [r.is_valid for r in results]}
        )
    times = [r["seconds"] for r in samples]
    root = Path(__file__).resolve().parents[1]
    report = {
        "workload_id": (
            "order54-composite-deployment-v2"
            if args.composite
            else "order54-oversized-deployment-v1"
        ),
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "timing_boundary": (
            f"{len(cases)} deployment resolutions; fixture creation excluded; first sample cold"
        ),
        "scenario": {
            "models": sum(
                len(unit.own_models) for army in first_state.army_definitions for unit in army.units
            ),
            "placed_models": len(first_state.battlefield_state.placed_model_ids()),
            "terrain_count": len(first_state.mission_setup.terrain_features),
            "zone_widths": [3, 3, 10, 10],
            "base_diameter_mm": 200,
            "composite_cases": args.composite,
        },
        "hashes": {
            p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            for p in ("uv.lock", "scripts/measure_order54.py", "tests/large_model_setup_helpers.py")
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {"mean_ratio": 3, "mean_additive_seconds": 0.05, "maximum_seconds": 1},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
