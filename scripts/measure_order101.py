"""Matched failed setup, restore, viewer and exact replay component workload."""

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
    local = importlib.import_module("warhammer40k_core.adapters.local_session")
    lifecycle_module = importlib.import_module("warhammer40k_core.engine.lifecycle")
    replay_module = importlib.import_module("warhammer40k_core.engine.replay")
    stream = importlib.import_module("warhammer40k_core.adapters.event_stream")
    battlefield = importlib.import_module("warhammer40k_core.engine.battlefield_state")
    proposals = importlib.import_module("warhammer40k_core.engine.movement_proposals")
    transports = importlib.import_module("warhammer40k_core.engine.transports")
    large = importlib.import_module("tests.large_model_disembark_helpers")
    ingress = importlib.import_module("tests.order63_reserve_transport_helpers")
    pending = importlib.import_module("tests.psychic_modifier_helpers").pending_request
    rows = []
    for case in ("cargo-5", "cargo-100", "loaded-deep-strike"):
        samples = []
        selected = []
        for sample in range(7):
            reserve = case == "loaded-deep-strike"
            session = (
                ingress.reserve_transport_session(deep_strike=True)
                if reserve
                else large.large_disembark_session(diameter=100 if case == "cargo-100" else 5)
            )
            request = pending(session)
            initial = session.lifecycle.to_payload()
            unit_id = "army-alpha:transport" if reserve else "army-alpha:intercessor-unit-1"
            started = perf_counter()
            session.submit_option(
                request_id=request.request_id, result_id=f"measure:{sample}:unit", option_id=unit_id
            )
            request = pending(session)
            session.submit_option(
                request_id=request.request_id,
                result_id=f"measure:{sample}:action",
                option_id="ingress" if reserve else "disembark",
            )
            request = pending(session)
            proposal = proposals.MovementProposalRequest.from_decision_request_payload(
                request.payload
            )
            submission = proposals.PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=unit_id,
                placement_kind=battlefield.BattlefieldPlacementKind.DEEP_STRIKE
                if reserve
                else battlefield.BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=ingress.placement(session, unit_id, x=100, y=100)
                if reserve
                else large.large_disembark_placement(session, gap=1.01),
                **(
                    {}
                    if reserve
                    else {
                        "transport_unit_instance_id": "army-alpha:transport",
                        "disembark_mode": transports.DisembarkModeKind.TACTICAL_DISEMBARK,
                        "transport_movement_status": transports.TransportMovementStatus.NOT_MOVED,
                    }
                ),
            )
            result = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"measure:{sample}:failed",
                payload=submission.to_payload(),
            )
            assert result.status_kind.value == "invalid"
            restored = local.LocalGameSession(
                lifecycle_module.GameLifecycle.from_payload(session.lifecycle.to_payload())
            )
            for viewer in ("player-a", "player-b"):
                assert restored.view(viewer_player_id=viewer) == session.view(
                    viewer_player_id=viewer
                )
                assert restored.events_since(
                    stream.EventStreamCursor(), viewer_player_id=viewer
                ) == session.events_since(stream.EventStreamCursor(), viewer_player_id=viewer)
            replay = replay_module.ReplayRunner(
                replay_module.ReplayArtifact.capture(
                    artifact_id="measure-order101",
                    initial_lifecycle_payload=initial,
                    final_lifecycle=session.lifecycle,
                )
            ).run()
            assert replay.reproduced_exactly
            samples.append(perf_counter() - started)
            state = session.lifecycle.state
            assert state is not None
            assert state.movement_phase_state is not None
            selected.append(unit_id in state.movement_phase_state.selected_unit_ids)
        rows.append(
            {
                "case": case,
                "samples_seconds": samples,
                "mean_seconds": statistics.mean(samples),
                "median_seconds": statistics.median(samples),
                "p95_seconds": max(samples),
                "maximum_seconds": max(samples),
                "selected_after_failure": selected,
                "completion_rate": 1,
            }
        )
    cpu, memory = _host_inventory()
    report = {
        "workload": "order101-failed-setup-restore-view-replay-v1",
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
            "Finite unit/action submission, rejected complete placement, serialization/restore, "
            "both viewer/event consumers and exact replay; canonical fixture preparation excluded"
        ),
        "scenario": (
            "Seven serial samples each: five-inch cargo, globally impossible 100-inch cargo, "
            "loaded Deep Strike carrier; no policy search or full game"
        ),
        "hashes": {
            name: hashlib.sha256(Path(name).read_bytes()).hexdigest()
            for name in (
                "scripts/measure_order101.py",
                "tests/large_model_disembark_helpers.py",
                "tests/disembark_eligibility_helpers.py",
                "tests/order63_reserve_transport_helpers.py",
                "uv.lock",
            )
        },
        "rows": rows,
        "coverage": False,
        "full_game_certified": False,
        "base_correctness": (
            "The uncorrected main retains selection. Its timings are a cost comparison, "
            "not a correctness oracle."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
