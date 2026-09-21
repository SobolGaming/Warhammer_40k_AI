"""Matched full-Fight consolidation/restore/replay regression workload."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from scripts.measure_order65 import _host_inventory, _select_runtime_src

ROOT = Path(__file__).resolve().parents[1]
CASE = (
    "tests/unit/test_phase15c_fight_order.py::"
    "test_p12_full_fight_phase_reconstructs_ordinary_continuation_and_forced_overrun"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    samples = []
    with tempfile.TemporaryDirectory(prefix="order72-") as temporary:
        for index in range(3):
            start = time.perf_counter()
            result = subprocess.run(
                [sys.executable, "-m", "pytest", CASE, "-q", "--no-cov"],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PYTHONPATH": str(args.runtime_src.resolve()) + os.pathsep + str(ROOT),
                },
            )
            samples.append(time.perf_counter() - start)
            Path(temporary, f"sample-{index}.txt").write_text(result.stdout, encoding="utf-8")
    cpu, memory = _host_inventory()
    from warhammer40k_core.build_identity import current_engine_build_id

    report = {
        "workload": "order72-engaging-full-fight-restore-replay-v1",
        "revision": args.revision,
        "runtime_build_id": current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "Fresh pytest process, real facade fixture, full Fight, restore and replay"
        ),
        "scenario": CASE,
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in ("scripts/measure_order72.py", "uv.lock")
        },
        "samples_seconds": samples,
        "mean_seconds": statistics.mean(samples),
        "median_seconds": statistics.median(samples),
        "maximum_seconds": max(samples),
        "completion_rate": 1,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
