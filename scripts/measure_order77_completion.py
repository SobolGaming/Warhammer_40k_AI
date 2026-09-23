"""Matched restore cost of source-backed, turn-end completed Cleanse history."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
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
    helpers = importlib.import_module("tests.phase17n_step6g_secondary_certification_helpers")
    build = importlib.import_module("warhammer40k_core.build_identity")
    started = time.perf_counter()
    session, payload, _expectation = helpers.secondary_certification_session(
        helpers.lifecycle_row("cleanse", mode="tactical", scoring_player_id="player-a")
    )
    preparation_seconds = time.perf_counter() - started
    samples = []
    for repeat in range(15):
        started = time.perf_counter()
        restored = type(session.lifecycle).from_payload(payload)
        seconds = time.perf_counter() - started
        assert restored.to_payload() == payload
        assert restored.state is not None
        action = restored.state.mission_action_states[-1]
        assert action.mission_action_id == "cleanse-objective"
        assert action.status.value == "completed"
        assert action.completed_phase == "fight"
        samples.append({"repeat": repeat, "seconds": seconds, "action_status": action.status.value})
    cpu, memory = _host_inventory()
    report = {
        "workload_id": "order77-completed-secondary-restore-v1",
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
            "Authenticated restore of a completed Cleanse at its engine turn-end boundary. "
            "Preparation and equality checking excluded; fixture preparation warms process caches. "
            "Fifteen repeated restores of the same serialized save in each fresh runtime process."
        ),
        "preparation_seconds": preparation_seconds,
        "samples": samples,
        "full_game_certified": False,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_order77_completion.py",
                "tests/mission_action_history_helpers.py",
                "tests/phase17n_secondary_certification_fixtures.py",
                "tests/phase17n_step6g_secondary_certification_helpers.py",
                "tests/phase17n_primary_mission_helpers.py",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
