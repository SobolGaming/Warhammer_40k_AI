"""Matched healing query/dispatch diagnostic; run serially without coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from tests.order89_healing_helpers import healing_scene

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.healing import resolve_healing_until_blocked


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for attached in (False, True):
        for revive in (False, True):
            setup, samples, steps = [], [], []
            for _ in range(5):
                start = perf_counter()
                lifecycle, effect, _, _ = healing_scene(
                    wounded=() if revive else (0,),
                    destroyed=(0,) if revive else (),
                    attached=attached,
                )
                state = lifecycle.state
                assert state is not None
                prepared = perf_counter()
                resolved, request = resolve_healing_until_blocked(
                    state=state,
                    decisions=lifecycle.decision_controller,
                    ruleset_descriptor=state.runtime_ruleset_descriptor(),
                    effect=effect,
                )
                setup.append(prepared - start)
                samples.append(perf_counter() - prepared)
                steps.append(len(resolved.resolved_steps))
                assert (request is not None) == revive
            rows.append(
                {
                    "attached": attached,
                    "revival": revive,
                    "setup_seconds": setup,
                    "samples_seconds": samples,
                    "mean": statistics.mean(samples),
                    "median": statistics.median(samples),
                    "p95_and_maximum": max(samples),
                    "steps": steps,
                }
            )
    report = {
        "workload": "order89-healing-v1",
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "full_game_samples": 0,
        "hardware": "provisional Apple M5 Pro, 64 GiB",
        "timing_boundary": (
            "shared healing resolution through completion or placement request; setup separate"
        ),
        "fixture": (
            "5 infantry, optional attached Character, 5 enemy infantry, no terrain; "
            "seed order89-healing"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order89_healing.py",
                "tests/order89_healing_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
