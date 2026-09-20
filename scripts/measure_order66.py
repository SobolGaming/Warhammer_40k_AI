"""Matched Aircraft end-turn and shared mutation-guard component timings."""

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

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "order66-aircraft-v1"
INPUTS = ("uv.lock", "scripts/measure_order66.py", "tests/aircraft_helpers.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helpers = importlib.import_module("tests.aircraft_helpers")
    rows = []
    for fleet_size in (1, 2):
        samples = []
        for _ in range(7):
            prepared = time.perf_counter()
            session = helpers.aircraft_session(fleet_size=fleet_size)
            state = session.lifecycle.state
            assert state is not None
            assert state.battlefield_state is not None
            preparation_seconds = time.perf_counter() - prepared
            battlefield = state.battlefield_state
            started = time.perf_counter()
            for _query in range(100):
                state.replace_battlefield_state(battlefield)
            guard_seconds = time.perf_counter() - started
            started = time.perf_counter()
            status = session.advance_until_decision_or_terminal()
            boundary_seconds = time.perf_counter() - started
            assert status.status_kind.value == "waiting_for_decision"
            returned = sum(row.is_unarrived for row in state.reserve_states)
            samples.append(
                {
                    "preparation_seconds": preparation_seconds,
                    "guard_seconds": guard_seconds,
                    "boundary_seconds": boundary_seconds,
                    "returned_aircraft": returned,
                    "complete": True,
                }
            )
        rows.append(
            {
                "fleet_size": fleet_size,
                "samples": samples,
                "summary": {
                    metric: {
                        "mean": statistics.mean(values),
                        "median": statistics.median(values),
                        "p95": max(values),
                        "maximum": max(values),
                        "operations_per_second": 1 / statistics.mean(values),
                    }
                    for metric in ("guard_seconds", "boundary_seconds")
                    for values in ([row[metric] for row in samples],)
                },
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
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
        "scenario": (
            "one/two Aircraft and five enemy infantry; empty terrain; canonical seed; "
            "opponent Fight-phase end"
        ),
        "timing_boundary": (
            "100 unchanged battlefield submissions; then advance through opponent turn "
            "boundary to next pending decision; preparation excluded"
        ),
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            for name in INPUTS
        },
        "rows": rows,
        "completion_rate": 1,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
