"""Matched fixed-profile Charge and viewer diagnostic; PYTHONPATH=.:src, no coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from tests.crushing_impact_helpers import complete_charge, crushing_session


def measure() -> dict[str, object]:
    samples: list[dict[str, float | int]] = []
    for _ in range(5):
        started = perf_counter()
        session = crushing_session(game_id="order87-fixed-profile-benchmark")
        prepared = perf_counter()
        status = complete_charge(session)
        assert status.decision_request is not None
        assert status.decision_request.decision_type == "use_stratagem"
        moved = perf_counter()
        events = session.lifecycle.decision_controller.event_log.records
        for _ in range(10):
            session.view(viewer_player_id="player-a")
            session.view(viewer_player_id="player-b")
        viewed = perf_counter()
        assert session.lifecycle.decision_controller.event_log.records == events
        assert not any(e.event_type == "random_profile_values_evaluated" for e in events)
        samples.append(
            {
                "setup_seconds": prepared - started,
                "charge_seconds": moved - prepared,
                "twenty_views_seconds": viewed - moved,
                "events": len(events),
            }
        )
    return {
        "workload": "order87-fixed-profile-charge-and-view-v1",
        "scope": "Fixed-profile gameplay slice; no full-game or random-profile timing claim.",
        "hardware_status": "provisional",
        "cpu": "Apple M5 Pro",
        "logical_cpus": 18,
        "memory_bytes": 68719476736,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "workers": 1,
        "coverage": False,
        "fixture": "crushing_session default: fixed profiles, 4 five-model units, no terrain",
        "seed": "order87-fixed-profile-benchmark",
        "policy": "legal witnessed Charge then no Stratagem selection",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        "samples": samples,
        "summary": {
            key: {
                "mean": statistics.mean(row[key] for row in samples),
                "median": statistics.median(row[key] for row in samples),
                "maximum": max(row[key] for row in samples),
            }
            for key in ("setup_seconds", "charge_seconds", "twenty_views_seconds")
        },
        "completion_rate": 1.0,
        "timing_budget": "diagnostic; component budgets deferred by Order 32 owner exception",
        "work_gate": "20 viewer queries add no events/dice; fixed profiles add no profile rolls",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.write_text(json.dumps(measure(), indent=2) + "\n")
