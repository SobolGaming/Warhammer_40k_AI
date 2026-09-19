"""Reproduce matched Emergency Disembark placement-proof costs.

Diagnostic only; not a full-game benchmark.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "order60-emergency-disembark-placement-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.order60_emergency_disembark_helpers")
    samples = []
    for _index in range(7):
        preparation_start = time.perf_counter()
        session = helpers.order60_emergency_session()
        placement = helpers.order60_passenger_placement(session)
        preparation_seconds = time.perf_counter() - preparation_start
        start = time.perf_counter()
        result = helpers.order60_resolve_emergency(session, placement)
        matched_seconds = time.perf_counter() - start
        samples.append(
            {
                "preparation_seconds": preparation_seconds,
                "matched_seconds": matched_seconds,
                "valid": result.is_valid,
                "violation_count": len(result.violations),
                "complete": True,
            }
        )
    times = [sample["matched_seconds"] for sample in samples]
    cpu, memory_bytes = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory_bytes,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "timing_boundary": (
            "resolve one five-model Emergency Disembark contact-ring placement on the "
            "canonical Transport fixture; fixture creation excluded; first sample cold"
        ),
        "scenario": {
            "models": "five Intercessors emergency-disembarking a 100mm circular Transport",
            "units": 2,
            "emergency_survivors": 5,
        },
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "uv.lock",
                "scripts/measure_order60.py",
                "tests/order60_emergency_disembark_helpers.py",
            )
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "p95_seconds": sorted(times)[int(0.95 * (len(times) - 1))],
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {"mean_ratio": 3, "mean_additive_seconds": 2.5, "maximum_seconds": 12},
        "certification": (
            "component diagnostic only; gameplay slice and complete games unmeasured"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


def _select_runtime_src(runtime_src: Path) -> None:
    resolved = str(runtime_src.resolve())
    while resolved in sys.path:
        sys.path.remove(resolved)
    sys.path.insert(0, resolved)
    root = str(ROOT)
    if root in sys.path:
        sys.path.remove(root)
    sys.path.insert(1, root)


def _host_inventory() -> tuple[str, int]:
    if sys.platform == "win32":
        cpu = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor).Name",
            ],
            text=True,
        ).strip()
        memory = subprocess.check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ],
            text=True,
        ).strip()
        return cpu, int(memory)
    if sys.platform == "darwin":
        return (
            subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip(),
            int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        )
    cpu = subprocess.check_output(
        ["sh", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"],
        text=True,
    ).strip()
    memory = subprocess.check_output(
        ["sh", "-c", "awk '/MemTotal/ {print $2 * 1024}' /proc/meminfo"],
        text=True,
    ).strip()
    return cpu, int(memory)


if __name__ == "__main__":
    main()
