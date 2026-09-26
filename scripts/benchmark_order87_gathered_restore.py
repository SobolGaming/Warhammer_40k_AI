"""Matched random-profile restore diagnostic; run with each revision's src first."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from tests.order87_gathered_profile_helpers import gathered_profile_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.build_identity import current_engine_build_id


def measure() -> dict[str, object]:
    samples: list[float] = []
    session = gathered_profile_session(contribution_count=1)
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    events = session.lifecycle.decision_controller.event_log.records
    for _ in range(5):
        started = perf_counter()
        restored = LocalGameSession.from_persistence_payload(checkpoint)
        samples.append(perf_counter() - started)
        assert restored.to_persistence_payload() == checkpoint
        assert restored.lifecycle.decision_controller.event_log.records == events
    return {
        "workload": "order87-r87-001-single-contribution-random-toughness-restore-v1",
        "runtime_build_id": current_engine_build_id(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "workers": 1,
        "coverage": False,
        "fixture": "one attacker, two defending models, one selected two-attack Torrent weapon",
        "seed": "order87-gathered-profiles",
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_sha256": hashlib.sha256(
            (
                Path(__file__).resolve().parents[1] / "tests/order87_gathered_profile_helpers.py"
            ).read_bytes()
        ).hexdigest(),
        "lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        "restore_seconds": samples,
        "mean": statistics.mean(samples),
        "median": statistics.median(samples),
        "maximum": max(samples),
        "events": len(events),
        "work_gate": (
            "JSON round-trip and restore preserve payload and events, including profile dice"
        ),
        "timing_budget": "diagnostic; component budgets deferred by Order 32 owner exception",
        "limitations": (
            "Five restores of one legal checkpoint, not full games. "
            "The two-contribution regression fails on base and is excluded from timing comparison."
        ),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(measure(), indent=2) + "\n")
