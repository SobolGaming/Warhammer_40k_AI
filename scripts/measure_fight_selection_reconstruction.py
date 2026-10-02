"""Measure bounded Fight completion histories through real restore and replay.

Each selected runtime creates its own history with identical current fixtures.
The baseline's known incorrect empty-fought/early-removal behavior is recorded,
not a correctness oracle. Armed pending restore has no successful base and is
reported separately for the current runtime, without a relative-budget claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.measure_order63 import _host_inventory, _select_runtime_src

if TYPE_CHECKING:
    from warhammer40k_core.adapters.local_session import LocalGameSession

ROOT = Path(__file__).resolve().parents[1]
WORKLOAD_ID = "order102-fight-selection-reconstruction-v1"
CASES = {
    "ordinary_empty": ("restore", "replay"),
    "retained_empty_completed": ("restore", "replay"),
    "engaging_resumed": ("restore", "replay"),
    "retained_armed_pending": ("replay",),
    "retained_armed_completed": ("restore",),
}


def prepare(checkpoint: str) -> LocalGameSession:
    from tests.fight_completion_helpers import (
        completion_session,
        drive_to_completion,
        engaging_completion_session,
        submit_completion_request,
    )
    from tests.psychic_modifier_helpers import pending_request

    if checkpoint == "engaging_resumed":
        return engaging_completion_session(fight_type="normal")
    if checkpoint not in CASES:
        raise ValueError(f"Unknown checkpoint: {checkpoint}")
    retained = checkpoint.startswith("retained_")
    armed = checkpoint.startswith("retained_armed_")
    session = completion_session(armed=armed, retained=retained)
    if checkpoint == "retained_armed_pending":
        for _ in range(100):
            request = pending_request(session)
            if request.decision_type == "select_feel_no_pain":
                assert isinstance(request.payload, dict)
                wound = request.payload["lost_wound_context"]
                assert isinstance(wound, dict)
                assert wound["source_rule_id"] == "order102-demise"
                assert wound["target_unit_instance_id"] == "army-alpha:observer"
                return session
            submit_completion_request(session)
        raise AssertionError("Armed retained completion did not reach real pending cleanup.")
    drive_to_completion(session, unit_id="army-beta:enemy" if retained else "army-alpha:subject")
    return session


def inventory(session: LocalGameSession, checkpoint: str, *, semantics: str) -> dict[str, object]:
    from warhammer40k_core.engine.retained_destruction_state import (
        RetainedDestructionStage,
        retained_destructions,
    )

    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    events = session.lifecycle.decision_controller.event_log.records
    counts = Counter(event.event_type for event in events)
    artifact = session.replay_artifact(artifact_id="order102-measurement")
    initial = artifact["initial_lifecycle"]
    assert not any(
        event["event_type"] in {"fight_activation_selected", "fight_selection_completed"}
        for event in initial["decisions"]["event_log"]
    )
    assert not initial["decisions"]["records"]
    if checkpoint == "engaging_resumed":
        assert counts["forced_fight_activation_queue_completed"] == 1
        assert counts["melee_declaration_accepted"] >= 1
        assert counts["attack_sequence_completed"] >= 1
        assert state.fight_phase_state is not None
        assert state.fight_phase_state.forced_activation_context is None
        resumed = next(
            event
            for event in events
            if event.event_type == "forced_fight_activation_queue_completed"
        )
        assert isinstance(resumed.payload, dict)
        assert resumed.payload["resumed_state"] is not None
    if checkpoint.startswith("retained_"):
        assert counts["melee_declaration_accepted"] >= 1
        assert counts["attack_sequence_completed"] >= 1
    if checkpoint == "retained_armed_completed":
        assert counts["fight_on_death_destruction_completed"] == 1
    if semantics == "current":
        expected = 1 if checkpoint == "ordinary_empty" else 2
        assert counts["fight_selection_completed"] == expected
        if checkpoint in {"ordinary_empty", "retained_empty_completed", "engaging_resumed"}:
            assert counts["unit_has_fought"] == expected - 1
        else:
            assert counts["unit_has_fought"] == expected
        if checkpoint == "retained_empty_completed":
            retained = retained_destructions(state=state)
            assert len(retained) == 1
            assert retained[0].stage is RetainedDestructionStage.WAITING
            assert counts["fight_on_death_destruction_ready"] == 0
    elif semantics == "base":
        assert counts["fight_selection_completed"] == 0
        if checkpoint == "retained_empty_completed":
            assert counts["fight_on_death_destruction_completed"] == 1
    else:
        raise ValueError(f"Unknown semantic qualification: {semantics}")
    return {
        "unit_count": sum(len(army.units) for army in state.army_definitions),
        "model_count": sum(
            len(unit.own_models) for army in state.army_definitions for unit in army.units
        ),
        "terrain_features": len(state.battlefield_state.terrain_features),
        "event_records": len(events),
        "decision_records": len(session.lifecycle.decision_controller.records),
        "initial_event_records": len(initial["decisions"]["event_log"]),
        "initial_decision_records": len(initial["decisions"]["records"]),
        "event_type_counts": dict(sorted(counts.items())),
        "retained_stages": [record.stage.value for record in retained_destructions(state=state)],
        "current_step": None
        if state.fight_phase_state is None
        else state.fight_phase_state.current_step.value,
        "forced_context": None
        if state.fight_phase_state is None
        or state.fight_phase_state.forced_activation_context is None
        else state.fight_phase_state.forced_activation_context.to_payload(),
        "semantics": semantics,
    }


def reconstruct(session: LocalGameSession, operation: str, *, timed: bool) -> dict[str, object]:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.replay import ReplayRunner

    saved = session.to_persistence_payload()
    isolated = json.loads(json.dumps(saved))
    runner = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order102-measurement"))
    if operation == "restore":
        started = time.perf_counter() if timed else 0
        restored = LocalGameSession.from_persistence_payload(isolated)
        elapsed = time.perf_counter() - started if timed else None
        assert restored.to_persistence_payload() == saved
        assert restored.lifecycle.state is not session.lifecycle.state
    elif operation == "replay":
        started = time.perf_counter() if timed else 0
        replay = runner.run()
        elapsed = time.perf_counter() - started if timed else None
        assert replay.reproduced_exactly, replay
    else:
        raise ValueError(f"Unknown operation: {operation}")
    assert session.to_persistence_payload() == saved
    return {"seconds": elapsed, "complete": True, "exact_result": True, "input_unchanged": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--semantics", choices=("base", "current"), required=True)
    parser.add_argument(
        "--preflight", action="store_true", help="Check outcomes once without timing"
    )
    parser.add_argument("--include-unmatched", action="store_true")
    args = parser.parse_args()
    if args.include_unmatched and args.semantics != "current":
        parser.error(
            "Unmatched armed pending restore is current-only; retain the separate base failure."
        )
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core import build_identity
    from warhammer40k_core.engine import active_player_scope_history, fight_activation_completion

    rows = []
    unmatched = []
    for checkpoint, operations in CASES.items():
        session = prepare(checkpoint)
        context = inventory(session, checkpoint, semantics=args.semantics)
        work = [(operation, "matched") for operation in operations]
        if checkpoint == "retained_armed_pending" and args.include_unmatched:
            work.append(("restore", "unmatched_current_only"))
        for operation, kind in work:
            samples = [
                reconstruct(session, operation, timed=not args.preflight)
                for _ in range(1 if args.preflight else 3)
            ]
            row = {
                "checkpoint": checkpoint,
                "operation": operation,
                "kind": kind,
                **context,
                "samples": samples,
                "completion_rate": 1,
            }
            if not args.preflight:
                times = [float(str(sample["seconds"])) for sample in samples]
                row.update(
                    mean_seconds=statistics.mean(times),
                    median_seconds=statistics.median(times),
                    p95_seconds=sorted(times)[math.ceil(0.95 * len(times)) - 1],
                    maximum_seconds=max(times),
                    operations_per_second=1 / statistics.mean(times),
                )
            (rows if kind == "matched" else unmatched).append(row)
            print(
                json.dumps(
                    {
                        "checkpoint": checkpoint,
                        "operation": operation,
                        "kind": kind,
                        "complete": True,
                        "preflight": args.preflight,
                    }
                ),
                flush=True,
            )
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": build_identity.verified_engine_build_identity().build_id,
        "runtime_src": str(args.runtime_src.resolve()),
        "runtime_imports": {
            module.__name__: module.__file__
            for module in (build_identity, active_player_scope_history, fight_activation_completion)
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": cpu,
        "cpu_allocation": os.cpu_count(),
        "memory_bytes": memory,
        "host_role": "provisional",
        "concurrency": 1,
        "coverage": False,
        "mode": "untimed_preflight" if args.preflight else "measurement",
        "sample_protocol": (
            "Three repeated independent reconstructions in one process per fixed prepared "
            "checkpoint; warm fixtures/imports; no discarded samples or cold-start claim"
        ),
        "scenario": (
            "Two or three one-model canonical units; empty terrain; deterministic facade choices; "
            "full ordinary/retained/Engaging histories; no trimming or amplification"
        ),
        "decision_policy": (
            "Canonical first finite option, fixed no-move proposals and first melee target; "
            "accept retention, decline optional Stratagems; real demise/FNP cleanup"
        ),
        "timing_boundary": (
            "LocalGameSession.from_persistence_payload or ReplayRunner.run only; preparation, "
            "JSON transport, artifact capture, input copies and correctness assertions excluded"
        ),
        "hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in (
                "uv.lock",
                "scripts/measure_fight_selection_reconstruction.py",
                "scripts/measure_order63.py",
                "tests/fight_completion_helpers.py",
                "tests/phase15c_fight_order_helpers.py",
                "tests/psychic_modifier_helpers.py",
                "tests/retained_attack_helpers.py",
                "tests/setup_completion_helpers.py",
            )
        },
        "rows": rows,
        "unmatched_current_only": unmatched,
        "full_game_certified": False,
        "qualification": (
            "Bounded component costs, not refreshed Order72 end-to-end pytest timing or long-game "
            "scalability; actual base wrongly marks empty selections fought and removes retained "
            "models early. Base armed pending restore rejects its own valid checkpoint; rejection "
            "is never a successful matched sample. Current-only armed pending restore has no "
            "relative-budget claim."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
