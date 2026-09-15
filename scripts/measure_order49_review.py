"""Matched cost-window construction and checkpoint replay timings for PR 469 review."""

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

from tests.command_reroll_cost_helpers import discounted_attack_session
from tests.fire_overwatch_helpers import (
    ENEMIES,
    choose_enemy,
    choose_shooter,
    finish_overwatch,
    overwatch_session,
    pending_overwatch,
)

from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayProjectionCheckpoint,
    ReplayProjectionSnapshot,
    ReplayRunner,
)

ROOT = Path(__file__).resolve().parents[1]


def projection_provider(
    lifecycle: GameLifecycle, checkpoint: ReplayProjectionCheckpoint
) -> ReplayProjectionSnapshot:
    view = project_game_view(lifecycle=lifecycle, viewer_player_id=checkpoint.viewer_player_id)
    return ReplayProjectionSnapshot(
        viewer_player_id=checkpoint.viewer_player_id,
        projection_schema=view["projection_schema"],
        projection_state_hash=view["projection_state_hash"],
    )


def checkpoint_artifact() -> ReplayArtifact:
    session = overwatch_session(cp=2, attacks=18)
    request = pending_overwatch(session)
    initial = session.lifecycle.to_payload()
    initial_records = len(session.lifecycle.decision_controller.records)
    status = choose_shooter(session, request)
    request = status.decision_request
    assert request is not None
    status = choose_enemy(session, request, ENEMIES[0])
    finish_overwatch(session, status)
    view = session.view(viewer_player_id="player-a")
    checkpoint = ReplayProjectionCheckpoint.from_lifecycle(
        lifecycle=session.lifecycle,
        checkpoint_id="overwatch-completed",
        decision_record_index=len(session.lifecycle.decision_controller.records) - initial_records,
        viewer_player_id="player-a",
        projection_schema=view["projection_schema"],
        projection_state_hash=view["projection_state_hash"],
    )
    session.advance_until_decision_or_terminal()
    return ReplayArtifact.capture(
        artifact_id="review-checkpoint-with-tail",
        initial_lifecycle_payload=initial,
        final_lifecycle=session.lifecycle,
        projection_checkpoints=(checkpoint,),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    rows = []
    for _ in range(args.samples):
        start = time.perf_counter()
        session, status = discounted_attack_session(cp=1)
        attack_seconds = time.perf_counter() - start
        assert status.decision_request is not None
        assert isinstance(status.payload, dict)
        assert status.payload["phase_body_status"] == "attack_hit_command_reroll_pending"
        artifact = checkpoint_artifact()
        start = time.perf_counter()
        result = ReplayRunner(artifact=artifact, projection_provider=projection_provider).run()
        replay_seconds = time.perf_counter() - start
        rows.append(
            {
                "attack_seconds": attack_seconds,
                "attack_events": len(session.lifecycle.decision_controller.event_log.records),
                "attack_decisions": len(session.lifecycle.decision_controller.records),
                "replay_seconds": replay_seconds,
                "replay_events": result.reproduced_event_count,
                "replay_decisions": result.reproduced_decision_count,
                "replay_status": result.status.value,
            }
        )
    summary = {}
    for metric in ("attack_seconds", "replay_seconds"):
        times = sorted(float(row[metric]) for row in rows)
        summary[metric] = {
            "mean": statistics.mean(times),
            "median": statistics.median(times),
            "p95": times[math.ceil(len(times) * 0.95) - 1],
            "maximum": max(times),
        }
    report = {
        "workload_id": "order49-review-cost-and-replay-v1",
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
        "mode": "uninstrumented_timing",
        "concurrency": 1,
        "timing_boundary": {
            "attack": (
                "fixture/catalog setup through first Hit reroll window, 1 CP, automatic discount"
            ),
            "replay": (
                "ReplayRunner.run only; Overwatch checkpoint at 84 events and phase tail to 92"
            ),
        },
        "scenario": {
            "attack_models": 6,
            "attack_dice": 24,
            "overwatch_models": 3,
            "overwatch_dice": 18,
            "terrain_count": 0,
            "seeds": ["order49-discounted-attacks", "order45-overwatch"],
        },
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "tests/command_reroll_cost_helpers.py",
                "tests/fire_overwatch_helpers.py",
                "scripts/measure_order49_review.py",
            )
        },
        "samples": rows,
        "summary": summary,
        "completion_rate": 1,
        "full_game_certified": False,
        "correctness_note": "The reviewed base is a timing comparison, not a correctness oracle.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
