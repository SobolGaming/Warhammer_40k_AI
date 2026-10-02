"""Two bounded, real engine workloads for the required current-runtime smoke."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

CASES = ("associated-woods-queries", "ingress-facade-restore-view-fork-replay")
CASE_LIMIT_SECONDS = 60.0
PROCESS_LIMIT_SECONDS = 180.0
WORKLOAD = "current-runtime-smoke-v1"


def run_case(case: str) -> dict[str, object]:
    started = time.perf_counter()
    if case == CASES[0]:
        from tests.order78_associated_terrain_helpers import associated_woods_scene
        from tests.order78_helpers import candidate_for_scene, shared_los

        lifecycle, units, _ = associated_woods_scene()
        for _ in range(10):
            assert not candidate_for_scene(lifecycle, units).is_legal
            assert not shared_los(lifecycle, units)
        work: dict[str, object] = {"candidate_queries": 10, "visibility_queries": 10}
    elif case == CASES[1]:
        from scripts.measure_ingress_reconstruction import prepare

        from warhammer40k_core.adapters.event_stream import EventStreamCursor
        from warhammer40k_core.adapters.local_session import LocalGameSession
        from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

        session = prepare("rapid_disembark")
        original = session.lifecycle.to_payload()
        restored = LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(session.to_persistence_payload(), allow_nan=False))
        )
        assert restored.lifecycle.to_payload() == original
        for player_id in ("player-a", "player-b"):
            assert restored.view(viewer_player_id=player_id) == session.view(
                viewer_player_id=player_id
            )
            assert restored.events_since(
                EventStreamCursor(), viewer_player_id=player_id
            ) == session.events_since(EventStreamCursor(), viewer_player_id=player_id)
        fork = session.fork()
        assert fork.lifecycle.to_payload() == original
        assert fork.lifecycle.state is not session.lifecycle.state
        artifact = session.replay_artifact(artifact_id="performance-smoke:ingress")
        replay = ReplayRunner.from_payload(json.loads(json.dumps(artifact))).run()
        assert replay.status is ReplayRunStatus.REPRODUCED
        assert session.lifecycle.to_payload() == original
        work = {
            "facade_ingress": 1,
            "facade_disembark": 1,
            "json_restores": 1,
            "viewers": 2,
            "event_consumers": 2,
            "forks": 1,
            "exact_replays": 1,
        }
    else:
        raise ValueError(f"Unknown required smoke case: {case}")
    return {"case": case, "complete": True, "seconds": time.perf_counter() - started, "work": work}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=CASES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_case(args.case)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
