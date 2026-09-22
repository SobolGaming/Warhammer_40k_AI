"""Matched cold-cache Surge facade submissions against fixed noncircular targets."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
import time
from pathlib import Path

from measure_order60 import ROOT, _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.surge_fixed_target_helpers")
    geometry = importlib.import_module("warhammer40k_core.geometry.movement_reachability")
    phase = importlib.import_module("warhammer40k_core.engine.phase")
    build = importlib.import_module("warhammer40k_core.build_identity")
    samples = []
    for attached, oval, facing in ((False, False, 0), (True, False, 37), (False, True, 90)):
        for repeat in range(3):
            prepared = time.perf_counter()
            session = helpers.fixed_target_surge_session(
                attached=attached, oval=oval, facing=facing
            )
            request = helpers.fixed_target_surge_request(session)
            payload = helpers.fixed_target_surge_payload(session, request)
            preparation_seconds = time.perf_counter() - prepared
            geometry.clear_movement_reachability_cache()
            start = time.perf_counter()
            result = session.submit_parameterized_payload(
                request_id=request.request_id, result_id="measured-surge", payload=payload
            )
            samples.append(
                {
                    "attached": attached,
                    "oval": oval,
                    "facing": facing,
                    "repeat": repeat,
                    "preparation_seconds": preparation_seconds,
                    "seconds": time.perf_counter() - start,
                    "accepted": result.status_kind
                    is phase.LifecycleStatusKind.WAITING_FOR_DECISION,
                    "status": result.status_kind.value,
                }
            )
    times = [row["seconds"] for row in samples]
    cpu, memory = _host_inventory()
    report = {
        "workload_id": "order75-fixed-target-surge-facade-v1",
        "revision": args.revision,
        "runtime_id": build.current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "library_versions": {
            name: importlib.metadata.version(name)
            for name in (
                "orjson",
                "msgspec",
                "pydantic",
                "shapely",
                "numpy",
                "jsonschema",
                "referencing",
                "z3-solver",
            )
        },
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": "cold-cache facade submission; preparation reported separately",
        "workload": {
            "moving_models": [5, 6, 5],
            "target_models": 1,
            "target_size_inches": [8, 2],
            "terrain_count": 0,
            "movement_budget_inches": 3,
            "decision_policy": "fixed finite target followed by a complete three-pose path",
            "rng": "no dice in measured slice",
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "p95_seconds": sorted(times)[math.ceil(0.95 * len(times)) - 1],
        "percentile_method": "nearest rank",
        "completed_submissions": len(samples),
        "completion_rate": 1,
        "acceptance_rate": sum(row["accepted"] for row in samples) / len(samples),
        "throughput_submissions_per_second": len(samples) / sum(times),
        "full_game_certified": False,
        "budget": {"maximum_head_seconds": 12, "required_head_acceptance_rate": 1},
        "comparison_note": "Base rejects optimal moves; accepted head work is not equivalent.",
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "uv.lock",
                "scripts/measure_order75.py",
                "tests/surge_fixed_target_helpers.py",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
