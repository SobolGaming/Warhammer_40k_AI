"""Reproduce matched destroyed-referent measurement costs; diagnostic, not a full-game benchmark."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUERY_COUNT = 50
WORKLOAD_ID = "order57-destroyed-referent-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.order57_destroyed_referent_helpers")
    deadly_demise = importlib.import_module("warhammer40k_core.engine.deadly_demise")
    destroyed_query = _destroyed_query()
    samples = []
    for _ in range(7):
        preparation_start = time.perf_counter()
        state, event_log = helpers.order57_battle_state()
        source = helpers.order57_alpha_models(state)[0]
        target = helpers.order57_beta_models(state)[0]
        ordinary = helpers.ordinary_order57_distance(state=state, source=source, target=target)
        preparation_seconds = time.perf_counter() - preparation_start
        start = time.perf_counter()
        distances = tuple(
            helpers.ordinary_order57_distance(state=state, source=source, target=target)
            for _query in range(QUERY_COUNT)
        )
        target_counts = tuple(
            len(
                _deadly_demise_targets(
                    deadly_demise_target_unit_ids=deadly_demise.deadly_demise_target_unit_ids,
                    state=state,
                    source_model_instance_id=source.model_instance_id,
                    event_records=(),
                )
            )
            for _query in range(QUERY_COUNT)
        )
        matched_seconds = time.perf_counter() - start
        destroyed_seconds = None
        destroyed_distance = None
        if destroyed_query is not None:
            helpers.destroy_and_remove_order57_model(
                state=state,
                event_log=event_log,
                model=target,
                cause_id="cause-order57-performance",
            )
            start = time.perf_counter()
            destroyed_distances = tuple(
                destroyed_query(
                    state=state,
                    event_records=event_log.records,
                    source_model_instance_id=source.model_instance_id,
                    destroyed_model_instance_id=target.model_instance_id,
                )
                for _query in range(QUERY_COUNT)
            )
            destroyed_seconds = time.perf_counter() - start
            destroyed_distance = destroyed_distances[0]
            if any(value != destroyed_distance for value in destroyed_distances):
                raise SystemExit("Destroyed-referent distances drifted across the sample.")
        if any(value != ordinary for value in distances):
            raise SystemExit("Ordinary distances drifted across the sample.")
        if any(count != target_counts[0] for count in target_counts):
            raise SystemExit("Deadly Demise target counts drifted across the sample.")
        samples.append(
            {
                "preparation_seconds": preparation_seconds,
                "matched_seconds": matched_seconds,
                "ordinary_distance": ordinary,
                "deadly_demise_target_count": target_counts[0],
                "destroyed_seconds": destroyed_seconds,
                "destroyed_distance": destroyed_distance,
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
            f"{QUERY_COUNT} ordinary closest-distance queries and "
            f"{QUERY_COUNT} still-placed Deadly Demise target enumerations; "
            "fixture creation excluded; first sample cold"
        ),
        "scenario": {
            "models": 10,
            "units": 2,
            "query_count": QUERY_COUNT,
            "destroyed_query_available": destroyed_query is not None,
        },
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "uv.lock",
                "scripts/measure_order57.py",
                "tests/order57_destroyed_referent_helpers.py",
            )
        },
        "samples": samples,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "maximum_seconds": max(times),
        "p95_seconds": sorted(times)[int(0.95 * (len(times) - 1))],
        "completion_rate": 1,
        "full_game_certified": False,
        "budgets": {"mean_ratio": 3, "mean_additive_seconds": 0.05, "maximum_seconds": 1},
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


def _deadly_demise_targets(
    *,
    deadly_demise_target_unit_ids: Callable[..., tuple[str, ...]],
    state: object,
    source_model_instance_id: str,
    event_records: tuple[object, ...],
) -> tuple[str, ...]:
    kwargs: dict[str, Any] = {
        "state": state,
        "source_model_instance_id": source_model_instance_id,
        "range_inches": 6.0,
    }
    if "event_records" in inspect.signature(deadly_demise_target_unit_ids).parameters:
        kwargs["event_records"] = event_records
    return deadly_demise_target_unit_ids(**kwargs)


def _destroyed_query() -> Callable[..., float] | None:
    engine_package = importlib.import_module("warhammer40k_core.engine")
    module_path = Path(engine_package.__file__).resolve().parent / (
        "destroyed_referent_measurement.py"
    )
    if not module_path.is_file():
        return None
    module = importlib.import_module("warhammer40k_core.engine.destroyed_referent_measurement")
    return module.distance_to_destroyed_model


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
