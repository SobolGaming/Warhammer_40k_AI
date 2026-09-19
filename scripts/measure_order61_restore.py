"""Measure complete lifecycle restoration of a fixed return-on-death checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import time
from pathlib import Path

from measure_order61 import ROOT, _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.engine.lifecycle import GameLifecycle

    checkpoint_bytes = args.checkpoint.read_bytes()
    checkpoint = json.loads(checkpoint_bytes)
    samples = []
    for _ in range(7):
        start = time.perf_counter()
        restored = GameLifecycle.from_payload(checkpoint)
        elapsed = time.perf_counter() - start
        assert restored.to_payload() == checkpoint
        samples.append(elapsed)
    cpu, memory = _host_inventory()
    report = {
        "workload_id": "order61-r61-001-return-checkpoint-restore-v1",
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "GameLifecycle.from_payload; parsing and round-trip comparison excluded; "
            "first sample cold"
        ),
        "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        "samples_seconds": samples,
        "mean_seconds": statistics.mean(samples),
        "median_seconds": statistics.median(samples),
        "p95_seconds": max(samples),
        "maximum_seconds": max(samples),
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {
            "id": "order61-return-restore-regression-v2",
            "mean_ratio": 1.2,
            "mean_additive_seconds": 0.02,
            "maximum_ratio": 1.2,
            "maximum_additive_seconds": 0.02,
        },
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
