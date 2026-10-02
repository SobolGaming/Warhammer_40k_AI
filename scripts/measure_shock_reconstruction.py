"""Measure real active and expired Shock restore and exact replay independently.

Both runtimes prepare their own legal histories through the unchanged Order 62
facade fixture. Preparation, JSON transport, input copies and assertions are
outside each reconstruction timing. This is component evidence, not full games.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import statistics
import time
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from scripts.measure_order63 import _host_inventory, _select_runtime_src

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecyclePayload

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "v963-shock-reconstruction-v1"
CHECKPOINTS = ("active_shock", "expired_shock")
OPERATIONS: tuple[Literal["restore", "replay"], ...] = ("restore", "replay")


def prepare(checkpoint: str) -> tuple[LocalGameSession, GameLifecyclePayload]:
    from tests.order62_shock_helpers import shock_proposal, shock_session
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

    if checkpoint not in CHECKPOINTS:
        raise ValueError(f"Unknown reconstruction checkpoint: {checkpoint}")
    session = shock_session(enemy_x=18)
    initial = session.lifecycle.to_payload()
    request, proposal = shock_proposal(session)
    outcome = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="shock-reconstruction:setup",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
    state = session.lifecycle.state
    assert state is not None
    assert state.disembarked_unit_states
    if checkpoint == "expired_shock":
        for index in range(40):
            if state.active_player_id != "player-a":
                break
            request = pending_request(session)
            options = tuple(option.option_id for option in request.options)
            result_id = f"shock-reconstruction:turn:{index}"
            if request.decision_type == "submit_stratagem_target_proposal":
                outcome = session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id=result_id,
                    payload=stratagem_decline_payload(),
                )
            else:
                if request.decision_type == "select_movement_unit":
                    selected = options[:1]
                elif request.decision_type == "select_movement_action":
                    selected = tuple(option for option in options if option == "remain_stationary")
                else:
                    selected = tuple(
                        option
                        for option in options
                        if any(
                            token in option
                            for token in ("complete", "end", "done", "decline", "skip")
                        )
                        or option == "pass"
                    )
                assert len(selected) == 1, (request.decision_type, options)
                outcome = session.submit_option(
                    request_id=request.request_id, result_id=result_id, option_id=selected[0]
                )
            assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
        assert state.active_player_id == "player-b"
        assert not state.disembarked_unit_states
    return session, initial


def sample(
    session: LocalGameSession,
    initial: GameLifecyclePayload,
    operation: Literal["restore", "replay"],
) -> dict[str, object]:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    saved = session.to_persistence_payload()
    isolated = json.loads(json.dumps(saved))
    artifact = ReplayArtifact.capture(
        artifact_id="shock-reconstruction",
        initial_lifecycle_payload=copy.deepcopy(initial),
        final_lifecycle=session.lifecycle,
    )
    runner = ReplayRunner(artifact)
    if operation == "restore":
        started = time.perf_counter()
        restored = LocalGameSession.from_persistence_payload(isolated)
        elapsed = time.perf_counter() - started
        assert restored.to_persistence_payload() == saved
        assert restored.lifecycle.state is not session.lifecycle.state
    elif operation == "replay":
        started = time.perf_counter()
        replay = runner.run()
        elapsed = time.perf_counter() - started
        assert replay.reproduced_exactly, replay
    else:
        raise ValueError(f"Unknown reconstruction operation: {operation}")
    assert session.to_persistence_payload() == saved
    return {"seconds": elapsed, "complete": True, "exact_result": True, "input_unchanged": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if args.samples < 3:
        parser.error("At least three samples are required.")
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.build_identity import verified_engine_build_identity

    runtime_identity = verified_engine_build_identity().build_id
    rows = []
    for checkpoint in CHECKPOINTS:
        started = time.perf_counter()
        session, initial = prepare(checkpoint)
        preparation_seconds = time.perf_counter() - started
        state = session.lifecycle.state
        assert state is not None
        assert state.battlefield_state is not None
        payload = session.lifecycle.to_payload()
        for operation in OPERATIONS:
            samples = [sample(session, initial, operation) for _ in range(args.samples)]
            times = [float(str(row["seconds"])) for row in samples]
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "operation": operation,
                    "preparation_seconds": preparation_seconds,
                    "unit_count": sum(len(army.units) for army in state.army_definitions),
                    "model_count": sum(
                        len(unit.own_models)
                        for army in state.army_definitions
                        for unit in army.units
                    ),
                    "terrain_features": len(state.battlefield_state.terrain_features),
                    "active_player_id": state.active_player_id,
                    "active_disembark_records": len(state.disembarked_unit_states),
                    "event_records": len(payload["decisions"]["event_log"]),
                    "decision_records": len(payload["decisions"]["records"]),
                    "samples": samples,
                    "mean_seconds": statistics.mean(times),
                    "median_seconds": statistics.median(times),
                    "p95_seconds": sorted(times)[math.ceil(0.95 * len(times)) - 1],
                    "maximum_seconds": max(times),
                    "operations_per_second": 1 / statistics.mean(times),
                    "completion_rate": 1,
                }
            )
            print(
                json.dumps(
                    {
                        "checkpoint": checkpoint,
                        "operation": operation,
                        "mean_seconds": statistics.mean(times),
                        "maximum_seconds": max(times),
                    }
                ),
                flush=True,
            )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": runtime_identity,
        "runtime_src": str(args.runtime_src.resolve()),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": memory,
        "host_role": "provisional",
        "concurrency": 1,
        "coverage": False,
        "profiler": False,
        "sample_protocol": (
            "Repeated independent reconstructions in one process from each fixed prepared "
            "checkpoint; warm fixture/runtime imports, no discarded samples or cold-start claim"
        ),
        "scenario": (
            "Unchanged Order 62 fixture, enemy_x=18, four units, sixteen models, empty terrain; "
            "each runtime creates its own legal Shock and normal turn-completion history"
        ),
        "decision_policy": (
            "Canonical passenger and fixed unengaged Shock poses; remaining units remain "
            "stationary; decline optional actions and complete phases until player-b"
        ),
        "seeds": {key: value for key, value in initial["config"].items() if "seed" in key},
        "timing_boundary": (
            "restore: LocalGameSession.from_persistence_payload only; replay: ReplayRunner.run "
            "only; fixture, facade setup, turn completion, JSON roundtrip, artifact capture, "
            "input copies and correctness assertions excluded"
        ),
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_shock_reconstruction.py",
                "scripts/measure_order63.py",
                "tests/order62_shock_helpers.py",
                "tests/disembark_eligibility_helpers.py",
                "tests/psychic_modifier_helpers.py",
            )
        },
        "rows": rows,
        "full_game_certified": False,
        "qualification": (
            "Matched component costs; source-correctness differences are not judged against "
            "the historical runtime; no full-game or historical-failure certification"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
