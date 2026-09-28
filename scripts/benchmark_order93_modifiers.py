"""Matched no-permission attack slice cost for generic modifier evaluation.

Run serially with PYTHONPATH=.:src against the archived base and current source,
using the same interpreter, script, fixtures, workload and dependency lock.
"""

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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-choices", action="store_true")
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        setup: list[float] = []
        samples: list[float] = []
        counts: list[dict[str, int]] = []
        for iteration in range(6):
            started = perf_counter()
            session = strength_session(phase, strength=1)
            pending_request(session)
            ready = perf_counter()
            complete_attack(session)
            finished = perf_counter()
            if iteration == 0:
                continue
            setup.append(ready - started)
            samples.append(finished - ready)
            counts.append(
                {
                    "wounds": len(attack_steps(session, "wound")),
                    "decisions": len(session.lifecycle.decision_controller.records),
                    "modifier_decisions": sum(
                        record.request.decision_type == "select_modifier_ignores"
                        for record in session.lifecycle.decision_controller.records
                    ),
                }
            )
        rows.append(
            {
                "phase": phase.value,
                "setup_seconds": setup,
                "samples_seconds": samples,
                "mean": statistics.mean(samples),
                "median": statistics.median(samples),
                "p95_and_maximum": max(samples),
                "completed": len(samples),
                "counts": counts,
            }
        )
    report = {
        "workload": "order93-no-permission-attack-slices-v1",
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
        "full_game_samples": 0,
        "fixture": "Two one-model units, no terrain, twelve Torrent/Twin-linked S1 vs T1 attacks",
        "seeds": ["order88-shooting", "order88-fight"],
        "policy": "First legal fixture option/proposal through LocalGameSession",
        "timing_boundary": (
            "First pending phase choice through attack-sequence completion; setup separate"
        ),
        "warmup_runs_per_phase": 1,
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/benchmark_order93_modifiers.py",
                "tests/absent_strength_helpers.py",
                "tests/lethal_hits_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
    }
    if args.include_choices:
        report["choice_diagnostic"] = measure_choices()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


def measure_choices() -> dict[str, object]:
    from tests.order93_movement_helpers import (
        finish_modifier_choices,
        movement_modifier_session,
        start_modifier_action,
    )

    samples: list[float] = []
    counts: list[int] = []
    widths: list[int] = []
    for iteration in range(4):
        session = movement_modifier_session(BattlePhase.CHARGE, extra_charge_modifiers=11)
        start_modifier_action(session)
        ignored = tuple(
            f"test:modifier-ignore:charge-extra-{index:02d}" for index in range(0, 11, 2)
        )
        started = perf_counter()
        finish_modifier_choices(session, ignored)
        elapsed = perf_counter() - started
        if iteration == 0:
            continue
        requests = tuple(
            record.request
            for record in session.lifecycle.decision_controller.records
            if record.request.decision_type == "select_modifier_ignores"
        )
        samples.append(elapsed)
        counts.append(len(requests))
        widths.append(max(len(request.options) for request in requests))
    return {
        "workload": "order93-thirteen-operation-charge-v1",
        "status": "head-only diagnostic; base lacks the supported choice path",
        "samples_seconds": samples,
        "mean": statistics.mean(samples),
        "maximum": max(samples),
        "decision_counts": counts,
        "maximum_option_widths": widths,
        "fixture_sha256": hashlib.sha256(
            Path("tests/order93_movement_helpers.py").read_bytes()
        ).hexdigest(),
        "timing_boundary": (
            "First modifier choice through accepted arbitrary subset; no export/replay"
        ),
    }


if __name__ == "__main__":
    main()
