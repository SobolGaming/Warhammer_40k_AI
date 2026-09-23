"""Matched completed-move Action interruption facade timings."""

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
    helpers = importlib.import_module("tests.action_movement_interruption_helpers")
    build = importlib.import_module("warhammer40k_core.build_identity")
    samples = []
    for case in ("translation", "return", "zero", "rotation", "rotation_return"):
        for repeat in range(3):
            prepared = time.perf_counter()
            session, unit_id = helpers.action_movement_session(pause_after_move=True)
            request = helpers.request_action_move(session, unit_id, case)
            preparation_seconds = time.perf_counter() - prepared
            option = next(o for o in request.options if o.option_id != "decline_triggered_movement")
            events_before = len(session.lifecycle.decision_controller.event_log.records)
            started = time.perf_counter()
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id="order77-measured-move",
            )
            seconds = time.perf_counter() - started
            saved = session.lifecycle.to_payload()
            restore_start = time.perf_counter()
            restored = type(session.lifecycle).from_payload(saved)
            restore_seconds = time.perf_counter() - restore_start
            assert restored.to_payload() == saved
            assert session.lifecycle.state is not None
            samples.append(
                {
                    "case": case,
                    "repeat": repeat,
                    "preparation_seconds": preparation_seconds,
                    "seconds": seconds,
                    "restore_seconds": restore_seconds,
                    "status": status.status_kind.value,
                    "action_status": session.lifecycle.state.mission_action_states[-1].status.value,
                    "event_delta": len(session.lifecycle.decision_controller.event_log.records)
                    - events_before,
                }
            )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": "order77-action-completed-move-v2",
        "revision": args.revision,
        "runtime_build_id": build.current_engine_build_id(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "host_role": "provisional",
        "library_versions": {
            name: importlib.metadata.version(name) for name in ("shapely", "z3-solver", "orjson")
        },
        "timing_boundary": (
            "one facade submission, preparation separate; first sample cold, "
            "subsequent process caches retained; authenticated restore timed separately, "
            "input serialization and equality check excluded from restore timer"
        ),
        "workload": (
            "Two five-model friendly and one five-model enemy unit, canonical "
            "purge-the-foe-vs-priority-assets-layout-1 terrain, fixed source seed; "
            "Maintain Control then reactive Normal Move of .25 inches, return to origin, "
            "zero distance, 45-degree rotation, or rotate-and-return. One facade submission "
            "with both versions stopping at the same spare friendly unit Shooting choice; "
            "no scoring/turn advancement in the timer. Base is cost evidence only."
        ),
        "samples": samples,
        "summary": {
            label: {
                "count": len(times),
                "mean_seconds": statistics.mean(times),
                "median_seconds": statistics.median(times),
                "p95_seconds": sorted(times)[math.ceil(0.95 * len(times)) - 1],
                "maximum_seconds": max(times),
                "submissions_per_second": 1 / statistics.mean(times),
                "completion_rate": 1,
            }
            for label, times in (
                (case, [row["seconds"] for row in samples if row["case"] == case])
                for case in ("translation", "return", "zero", "rotation", "rotation_return")
            )
        },
        "completed_submissions": len(samples),
        "full_game_certified": False,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_order77.py",
                "tests/action_movement_interruption_helpers.py",
                "tests/phase17n_primary_mission_helpers.py",
                "tests/phase17n_step5g_pairing_certification_helpers.py",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
