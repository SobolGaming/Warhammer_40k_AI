"""Matched shared Gone to Ground query component costs; fixture preparation excluded."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import time
from pathlib import Path

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.order78_helpers")
    areas = importlib.import_module("warhammer40k_core.core.terrain_areas")
    rows = []
    for name, settings in (
        ("dense-outside", {}),
        ("dense-inside", {"dense_occupancy": True}),
        ("attached-outside", {"attached_target": True}),
        ("light-outside", {"classification": areas.TerrainAreaClassification.LIGHT}),
        ("not-hidden", {"hidden": False}),
        ("fully-visible", {"wall_y": 40.0}),
    ):
        lifecycle, units = helpers.scene(**settings)
        samples = []
        for _ in range(7):
            start = time.perf_counter()
            for _ in range(10):
                candidate = helpers.candidate_for_scene(lifecycle, units)
                los = helpers.shared_los(lifecycle, units)
            samples.append(time.perf_counter() - start)
        rows.append(
            {
                "case": name,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "complete": True,
                "legal": candidate.is_legal,
                "shared_los": los,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order78-gone-to-ground-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "Ten pairs of model-target candidate and shared LOS queries per sample; "
            "seven serial samples without coverage, normal immutable geometry caches enabled; "
            "no cached candidate wrapper; canonical scene preparation excluded"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in ("scripts/measure_order78.py", "tests/order78_helpers.py", "uv.lock")
        },
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
