"""Matched completed-checkpoint cost and direct/collateral retention diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from tests.stratagem_retention_helpers import (
    finish_stratagem_reactions,
    offered_stratagem_reaction,
)

from warhammer40k_core.adapters.local_session import (
    LocalGameSession,
    LocalGameSessionPersistenceError,
)
from warhammer40k_core.build_identity import current_engine_build_id
from warhammer40k_core.engine.damage_allocation import DECLINE_DESTRUCTION_REACTION_OPTION_ID

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=7)
    parser.add_argument("--collateral-depth", type=int, choices=(0, 1, 2), default=0)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    scenarios = []
    for stratagem in ("crushing-impact", "explosives"):
        boundaries = ("offered", "accepted", "completed") + ("accepted_completed",) * bool(
            args.collateral_depth
        )
        for boundary in boundaries:
            setup = time.perf_counter()
            session, request = offered_stratagem_reaction(
                stratagem, collateral_depth=args.collateral_depth
            )
            if boundary in ("accepted", "accepted_completed"):
                option = next(
                    option
                    for option in request.options
                    if option.option_id != DECLINE_DESTRUCTION_REACTION_OPTION_ID
                )
                session.submit_option(
                    request_id=request.request_id,
                    option_id=option.option_id,
                    result_id="r48-001:reaction",
                )
            if boundary in ("completed", "accepted_completed"):
                finish_stratagem_reactions(session)
            payload = session.to_persistence_payload()
            setup_seconds = time.perf_counter() - setup
            state = session.lifecycle.state
            assert state is not None
            assert state.battlefield_state is not None
            samples = []
            for _ in range(args.samples):
                start = time.perf_counter()
                try:
                    restored = LocalGameSession.from_persistence_payload(payload)
                except LocalGameSessionPersistenceError as exc:
                    # The reviewed base rejects valid retained checkpoints. Retain
                    # the typed failure as failed evidence, never a timing pass.
                    samples.append(
                        {
                            "seconds": time.perf_counter() - start,
                            "status": "rejected",
                            "diagnostic": str(exc.__cause__),
                        }
                    )
                else:
                    elapsed = time.perf_counter() - start
                    assert restored.to_persistence_payload() == payload
                    samples.append({"seconds": elapsed, "status": "restored"})
            durations = [sample["seconds"] for sample in samples]
            scenarios.append(
                {
                    "stratagem": stratagem,
                    "boundary": boundary,
                    "game_id": state.game_id,
                    "setup_seconds": setup_seconds,
                    "model_count": sum(
                        len(unit.own_models)
                        for army in state.army_definitions
                        for unit in army.units
                    ),
                    "terrain_count": len(state.battlefield_state.terrain_features),
                    "decision_count": len(session.lifecycle.decision_controller.records),
                    "event_count": len(session.lifecycle.decision_controller.event_log.records),
                    "samples": samples,
                    "mean_seconds": statistics.mean(durations),
                    "median_seconds": statistics.median(durations),
                    "maximum_seconds": max(durations),
                    "completion_rate": sum(sample["status"] == "restored" for sample in samples)
                    / len(samples),
                }
            )
    report = {
        "workload_id": (
            f"r48-002-collateral-depth-{args.collateral_depth}-checkpoint-v1"
            if args.collateral_depth
            else "r48-001-retained-checkpoint-v1"
        ),
        "engine_build_id": current_engine_build_id(),
        "revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip(),
        "memory_bytes": int(subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)),
        "cpu_allocation": os.cpu_count(),
        "concurrency": 1,
        "mode": "uninstrumented_timing",
        "timing_boundary": (
            "LocalGameSession.from_persistence_payload; "
            "preparation and roundtrip comparison excluded"
        ),
        "policy": (
            "Shared deterministic facade fixture; accept first source or decline all reactions "
            "to completion"
        ),
        "scenarios": scenarios,
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_stratagem_retention_restore.py",
                "tests/stratagem_retention_helpers.py",
                "tests/crushing_impact_helpers.py",
                "tests/explosives_helpers.py",
                "tests/retained_attack_helpers.py",
            )
        },
        "full_game_certified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
