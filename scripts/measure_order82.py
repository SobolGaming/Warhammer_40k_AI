"""Matched revival submission, two viewers, checkpoint and replay diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import platform
import statistics
from pathlib import Path
from time import perf_counter

from scripts.measure_order65 import _host_inventory, _select_runtime_src


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=Path("src"))
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    helper = importlib.import_module("tests.order82_revival_helpers")
    session_type = importlib.import_module(
        "warhammer40k_core.adapters.local_session"
    ).LocalGameSession
    replay = importlib.import_module("warhammer40k_core.engine.replay")
    pose = importlib.import_module("warhammer40k_core.geometry.pose").Pose
    cases = (
        ("unengaged-control", {"revival_pose": pose.at(8.5, 15)}),
        ("same-enemy-unit", {}),
        ("attached", {"attached_target": True, "attached_enemy": True}),
        ("retained-enemy", {"retained_enemy": True}),
        ("new-enemy-unit", {"second_enemy": True}),
    )
    rows = []
    for case, kwargs in cases:
        samples, outcomes = [], []
        for sample in range(3):
            session, proposal = helper.revival_session(**kwargs)
            request = session.lifecycle.pending_decision_request()
            assert request is not None
            started = perf_counter()
            for viewer in ("player-a", "player-b"):
                session.view(viewer_player_id=viewer)
            result = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"sample-{sample}",
                payload=proposal,
            )
            payload = session.to_persistence_payload()
            restored = session_type.from_persistence_payload(payload)
            assert restored.to_persistence_payload() == payload
            artifact = restored.replay_artifact(artifact_id=f"sample-{sample}")
            assert replay.ReplayRunner.from_payload(artifact).run().status.value == "reproduced"
            samples.append(perf_counter() - started)
            outcomes.append(result.status_kind.value)
        rows.append(
            {
                "case": case,
                "samples_seconds": samples,
                "outcomes": outcomes,
                "complete": True,
                "mean_seconds": statistics.mean(samples),
                "median_seconds": statistics.median(samples),
                "maximum_seconds": max(samples),
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order82-revival-engagement-v1",
        "revision": args.revision,
        "runtime_build_id": importlib.import_module(
            "warhammer40k_core.build_identity"
        ).current_engine_build_id(),
        "cpu": cpu,
        "memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "host_role": "provisional",
        "concurrency": 1,
        "timing_boundary": (
            "Two viewer projections, one facade submission, exact checkpoint recovery "
            "and replay; fixture setup excluded."
        ),
        "fixture": (
            "Two canonical five-model units, optional attached Leaders or second enemy; "
            "flat empty terrain; no random draws."
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_order82.py",
                "tests/order82_revival_helpers.py",
                "tests/healing_phase_start_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
                "tests/fight_on_death_helpers.py",
                "tests/destruction_occurrence_fixture_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "coverage": False,
        "full_game_certified": False,
    }
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
