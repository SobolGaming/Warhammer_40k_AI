"""Matched phase-end Fire Overwatch scheduling, declaration and continuation costs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.fire_overwatch_helpers import (
    ENEMIES,
    choose_enemy,
    choose_shooter,
    overwatch_session,
    pending_overwatch,
)

from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--attached", action="store_true")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = []
    for _ in range(args.samples):
        start = time.perf_counter()
        session = overwatch_session(moved=not args.attached, attached=args.attached)
        state = session.lifecycle.state
        assert state is not None
        enemy_id = rules_unit_view_by_id(state=state, unit_instance_id=ENEMIES[0]).unit_instance_id
        ready = time.perf_counter()
        request = pending_overwatch(session)
        scheduled = time.perf_counter()
        status = choose_shooter(session, request)
        request = status.decision_request
        assert request is not None
        declared = time.perf_counter()
        status = choose_enemy(session, request, enemy_id)
        for index in range(50):
            assert status.status_kind is not LifecycleStatusKind.INVALID, status
            state = session.lifecycle.state
            assert state is not None
            if state.current_battle_phase is BattlePhase.SHOOTING:
                break
            if status.decision_request is None:
                status = session.advance_until_decision_or_terminal()
                continue
            request = status.decision_request
            option = next(
                (o for o in request.options if "decline" in o.option_id), request.options[0]
            )
            status = session.submit_option(
                request_id=request.request_id,
                option_id=option.option_id,
                result_id=f"order45:finish-{index}",
            )
        else:
            raise AssertionError("Overwatch did not finish and resume the parent phase.")
        end = time.perf_counter()
        rows.append(
            {
                "setup_seconds": ready - start,
                "scheduling_seconds": scheduled - ready,
                "declaration_seconds": declared - scheduled,
                "continuation_seconds": end - declared,
                "slice_seconds": end - ready,
                "decision_count": len(session.lifecycle.decision_controller.records),
                "event_count": len(session.lifecycle.decision_controller.event_log.records),
            }
        )
    times = sorted(row["slice_seconds"] for row in rows)
    report = {
        "workload_id": "r45-001-attached-overwatch-v1"
        if args.attached
        else "order45-fire-overwatch-slice-v1",
        "revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runtime_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD", "--", "src"])
        ).hexdigest(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_allocation": os.cpu_count(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "model_count": 5 if args.attached else 3,
        "terrain_count": 0,
        "timing_boundary": "phase-end scheduling through next Shooting decision; setup separate",
        "scenario": {
            "game_id": "order45-overwatch",
            "moved_enemy": None if args.attached else ENEMIES[0],
            "chosen_enemy": enemy_id,
            "shooters": 1,
            "enemies": 2,
            "command_points": 1,
            "weapon_range_inches": 24,
            "weapon_attacks": 2,
            "attached": args.attached,
        },
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/fire_overwatch_helpers.py",
                "scripts/measure_fire_overwatch.py",
            )
        },
        "samples": rows,
        "mean_seconds": statistics.mean(times),
        "median_seconds": statistics.median(times),
        "p95_seconds": times[math.ceil(len(times) * 0.95) - 1],
        "maximum_seconds": max(times),
        "completion_rate": 1,
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
