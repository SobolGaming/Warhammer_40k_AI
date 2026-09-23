"""Matched turn-end facade costs; initialized scene preparation excluded."""

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
    helper = importlib.import_module("tests.order79_helpers")
    rows = []
    for owner in ("player-b", "player-a"):
        samples = []
        controllers = []
        for _ in range(5):
            session = helper.control_session(turn_owner=owner)
            start = time.perf_counter()
            session.advance_until_decision_or_terminal()
            samples.append(time.perf_counter() - start)
            record = next(
                r
                for r in session.lifecycle.state.objective_control_records
                if r.battle_round == 1
                and r.active_player_id == owner
                and r.timing.value == "turn_end"
            )
            controllers.append(record.results[0].controlled_by_player_id)
        rows.append(
            {
                "case": owner,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "maximum_seconds": max(samples),
                "complete": True,
                "controllers": controllers,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order79-turn-end-control-v2",
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
            "One facade advance from initialized unengaged Fight boundary to next decision; "
            "five serial samples, no coverage; fixture/restore preparation excluded"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_order79.py",
                "tests/order79_helpers.py",
                "tests/aircraft_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
