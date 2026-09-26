"""Matched numeric Strength attack slice; run serially with PYTHONPATH=.:src."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
from pathlib import Path
from time import perf_counter

from tests.absent_strength_helpers import strength_session
from tests.lethal_hits_helpers import attack_steps, complete_attack
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.phase import BattlePhase


def measure() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        setup: list[float] = []
        samples: list[float] = []
        counts: list[int] = []
        for _ in range(5):
            start = perf_counter()
            session = strength_session(phase, strength=1)
            pending_request(session)
            prepared = perf_counter()
            complete_attack(session)
            samples.append(perf_counter() - prepared)
            setup.append(prepared - start)
            counts.append(len(attack_steps(session, "wound")))
        rows.append(
            {
                "phase": phase.value,
                "setup_seconds": setup,
                "samples_seconds": samples,
                "wound_count": counts,
                "mean": statistics.mean(samples),
                "median": statistics.median(samples),
                "p95_and_maximum": max(samples),
                "slices_per_second": 1 / statistics.mean(samples),
            }
        )
    return {
        "workload": "order88-numeric-strength-attacks-v1",
        "runtime_build_id": verified_engine_build_identity().build_id,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "hardware_status": "provisional",
        "concurrency": 1,
        "coverage": False,
        "fixture": (
            "Two units, Shooting 1+1 models; Fight 1+1; no terrain; "
            "twelve Torrent/Twin-linked attacks, S1 versus T1"
        ),
        "seeds": ["order88-shooting", "order88-fight"],
        "policy": "First legal fixture option/proposal through LocalGameSession",
        "timing_boundary": (
            "pending phase choice through first attack sequence completion; setup separate"
        ),
        "hashes": {
            path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
            for path in (
                "scripts/benchmark_order88_strength.py",
                "tests/absent_strength_helpers.py",
                "tests/lethal_hits_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "completion_rate": 1.0,
        "full_game_samples": 0,
        "full_game_certified": False,
        "timing_budget": "Diagnostic; component timing budgets remain deferred by Order 32",
        "work_gate": "Twelve wound interactions; no random-profile evaluation for fixed/dash S",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(measure(), indent=2) + "\n")
