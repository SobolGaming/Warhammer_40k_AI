"""Reproduce matched empty Dedicated Transport destruction costs.

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
WORKLOAD_ID = "order59-empty-dedicated-transport-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.order59_empty_dedicated_transport_helpers")
    samples = []
    for index in range(7):
        preparation_start = time.perf_counter()
        lifecycle, status = helpers.order59_lifecycle_at_reserve_request(
            game_id=f"order59-performance-{index}"
        )
        preparation_seconds = time.perf_counter() - preparation_start
        start = time.perf_counter()
        helpers.complete_order59_declare_battle_formations(
            lifecycle,
            status,
            result_id_prefix=f"order59-performance-{index}",
        )
        matched_seconds = time.perf_counter() - start
        state = helpers.typed_state(lifecycle)
        transport = helpers.order59_transport_unit(
            state,
            helpers.ORDER59_EMPTY_TRANSPORT_UNIT_ID,
        )
        samples.append(
            {
                "preparation_seconds": preparation_seconds,
                "matched_seconds": matched_seconds,
                "destroyed_model_count": sum(
                    1 for model in transport.own_models if not model.is_alive
                ),
                "destruction_events": len(helpers.order59_destruction_events(lifecycle)),
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
            "complete remaining Declare Battle Formations reserve declarations including "
            "empty Dedicated Transport destruction on head; fixture creation excluded; "
            "first sample cold"
        ),
        "scenario": {
            "models": "one empty Dedicated Transport, reservable infantry, and opposing infantry",
            "units": 4,
            "empty_dedicated_transports": 1,
        },
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "uv.lock",
                "scripts/measure_order59.py",
                "tests/order59_empty_dedicated_transport_helpers.py",
            )
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "p95_seconds": sorted(times)[int(0.95 * (len(times) - 1))],
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {"mean_ratio": 3, "mean_additive_seconds": 0.45, "maximum_seconds": 8},
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
