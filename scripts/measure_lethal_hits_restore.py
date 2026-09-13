"""R44-001 declined Lethal Hits restore and wound Command Re-roll continuation cost."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.lethal_hits_helpers import lethal_wound_checkpoint

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    results = {}
    for phase in (BattlePhase.SHOOTING, BattlePhase.FIGHT):
        start = time.perf_counter()
        session = lethal_wound_checkpoint(phase=phase)
        payload = session.to_persistence_payload()
        setup_seconds = time.perf_counter() - start
        samples = []
        for _ in range(args.samples):
            start = time.perf_counter()
            restored = LocalGameSession.from_persistence_payload(payload)
            restored_at = time.perf_counter()
            request = restored.lifecycle.decision_controller.queue.pending_requests[0]
            status = restored.submit_option(
                request_id=request.request_id,
                result_id="r44:benchmark-continue-wound",
                option_id="decline_stratagem_window",
            )
            completed = time.perf_counter()
            assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
            samples.append(
                {
                    "restore_seconds": restored_at - start,
                    "continuation_seconds": completed - restored_at,
                    "decision_count": len(restored.lifecycle.decision_controller.records),
                    "event_count": len(restored.lifecycle.decision_controller.event_log.records),
                }
            )
        results[phase.value] = {
            "setup_seconds": setup_seconds,
            "samples": samples,
            "completion_rate": 1,
            **{
                metric: {
                    "mean_seconds": statistics.mean(row[metric] for row in samples),
                    "median_seconds": statistics.median(row[metric] for row in samples),
                    "maximum_seconds": max(row[metric] for row in samples),
                }
                for metric in ("restore_seconds", "continuation_seconds")
            },
        }
    report = {
        "workload_id": "r44-lethal-choice-wound-checkpoint-v1",
        "build_id": current_engine_build_id(),
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "mode": "uninstrumented_timing",
        "full_game_certified": False,
        "hashes": {
            path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            for path in (
                "scripts/measure_lethal_hits_restore.py",
                "tests/lethal_hits_helpers.py",
                "uv.lock",
            )
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
