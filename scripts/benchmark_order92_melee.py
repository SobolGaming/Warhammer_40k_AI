"""Serial matched component diagnostic for the random melee declaration boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from tests.random_melee_helpers import melee_boundary, random_melee_session

from warhammer40k_core.build_identity import verified_engine_build_identity


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for random in (False, True):
        setup, samples, outcomes = [], [], []
        for _ in range(5):
            started = perf_counter()
            session = random_melee_session(random=random)
            ready = perf_counter()
            request = melee_boundary(session)
            selections = 0
            while request.decision_type == "select_melee_weapon":
                status = session.submit_option(
                    request_id=request.request_id,
                    option_id=request.options[0].option_id,
                    result_id=f"benchmark-weapon-{selections}",
                )
                assert status.decision_request is not None
                request = status.decision_request
                selections += 1
            setup.append(ready - started)
            samples.append(perf_counter() - ready)
            outcomes.append({"decision_type": request.decision_type, "weapon_choices": selections})
        rows.append(
            {
                "random": random,
                "setup_seconds": setup,
                "samples_seconds": samples,
                "mean": statistics.mean(samples),
                "median": statistics.median(samples),
                "p95_and_maximum": max(samples),
                "outcomes": outcomes,
            }
        )
    report = {
        "workload": "order92-melee-declaration-v1",
        "rows": rows,
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "hardware": "provisional Apple M5 Pro, 64 GiB",
        "concurrency": 1,
        "coverage": False,
        "full_game_samples": 0,
        "fixture": "three single-model leaders, no terrain, two engaged enemies; seeded game ID",
        "timing_boundary": (
            "Fight phase progression to target declaration, including weapon choices"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order92_melee.py",
                "tests/random_melee_helpers.py",
                "uv.lock",
            )
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
