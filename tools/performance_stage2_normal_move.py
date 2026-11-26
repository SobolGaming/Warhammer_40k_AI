"""Serial exact-checkout comparison of the Stage 2 translation search."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import cast

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyAction
from warhammer40k_core.ai.screen_movement_candidates import (
    generate_retreat_proposals,
    generate_screen_movement_options,
)
from warhammer40k_core.build_identity import verified_engine_build_identity
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import MovementProposalPayload, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement_model import FallBackModeKind
from warhammer40k_core.geometry.pathing import ModelPathEndpoint, PathWitness
from warhammer40k_core.geometry.pose import Pose

_BATCH = 20
_SAMPLES = 5
_VIEWER = ViewerContext.for_player("player-a")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _context(session: LocalGameSession) -> PlayerDecisionContext:
    return PlayerDecisionContext.from_view(session.view_for_context(viewer=_VIEWER), choice_seed=0)


def _choose(session: LocalGameSession, action: PolicyAction) -> None:
    assert action.option_id is not None
    status = session.submit_viewer_option(
        viewer=_VIEWER,
        request_id=action.request_id,
        option_id=action.option_id,
        result_id=action.request_id,
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION


def _before_action(engaged: bool) -> LocalGameSession:
    lifecycle, units = charge_lifecycle(
        game_id=f"stage2-move-performance-{engaged}",
        alpha_unit_ids=("moving", "spare"),
        alpha_origins={"moving": Pose.at(12, 20)},
        enemy_model_poses=compact_test_unit_poses(
            origin=Pose.at(12, 22) if engaged else Pose.at(40, 40), model_count=5
        ),
        battle_round=4,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    record_primary_turn_start_evidence_for_fixture(state, decisions=lifecycle.decision_controller)
    session = LocalGameSession(lifecycle)
    assert (
        session.advance_until_decision_or_terminal().status_kind
        is LifecycleStatusKind.WAITING_FOR_DECISION
    )
    context = _context(session)
    _choose(
        session,
        FiniteCandidateSet.from_context(context).select(context, units["moving"].unit_instance_id),
    )
    return session


def _time(
    call: Callable[[PlayerDecisionContext], tuple[PolicyAction, ...]],
    context: PlayerDecisionContext,
) -> dict[str, object]:
    candidates = call(context)
    assert len(candidates) == 32
    assert len(set(candidates)) == 32
    samples: list[float] = []
    for _ in range(_SAMPLES):
        start = perf_counter()
        for _ in range(_BATCH):
            assert call(context) == candidates
        samples.append((perf_counter() - start) / _BATCH)
    return {
        "count": len(candidates),
        "ordered_actions_sha256": _digest([asdict(action) for action in candidates]),
        "actor_observation_sha256": context.observation_hash,
        "seconds_per_call": samples,
        "median_seconds_per_call": statistics.median(samples),
    }


def _ordinary_control(
    session: LocalGameSession, context: PlayerDecisionContext
) -> dict[str, object]:
    request = context.request["payload"]
    assert isinstance(request, dict)
    proposal_request = request["proposal_request"]
    assert isinstance(proposal_request, dict)
    unit_id = proposal_request["unit_instance_id"]
    assert isinstance(unit_id, str)
    board = context.observation["battlefield_view"]
    assert board is not None
    endpoints: list[ModelPathEndpoint] = []
    for model_id, row in board["authoritative"]["models_by_id"].items():
        if row["rules_unit_instance_id"] != unit_id:
            continue
        p = row["pose"]
        assert p is not None
        at = p["position"]
        src = Pose.at(at["x_inches"], at["y_inches"], at["z_inches"], p["facing_degrees"])
        end = Pose.at(at["x_inches"], at["y_inches"] - 1, at["z_inches"], p["facing_degrees"])
        endpoints.append((model_id, src, end))
    assert len(endpoints) == 5
    proposal = MovementProposalPayload(
        context.request["request_id"],
        ProposalKind.NORMAL_MOVE,
        unit_id,
        "normal_move",
        PathWitness.for_straight_line_endpoints(tuple(endpoints)),
        movement_mode="normal",
    )
    status = session.submit_viewer_parameterized_payload(
        viewer=_VIEWER,
        request_id=context.request["request_id"],
        payload=cast(JsonValue, proposal.to_payload()),
        result_id="ordinary-native-control",
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    checkpoint = session.to_persistence_payload()
    assert isinstance(checkpoint, dict)
    return {
        "status": status.status_kind.value,
        "final_event_log_hash": checkpoint["event_log_hash"],
        "viewer_sha256": _context(session).observation_hash,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("side", choices=("base", "head"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    retreat: dict[str, dict[str, object]] = {}
    for mode in FallBackModeKind:
        session = _before_action(engaged=True)
        options = generate_screen_movement_options(_context(session))
        _choose(session, dict(options.fall_back)[mode])
        retreat[mode.value] = _time(generate_retreat_proposals, _context(session))
    session = _before_action(engaged=False)
    before = _context(session)
    choices = FiniteCandidateSet.from_context(before)
    assert {"remain_stationary", "normal_move"} <= set(choices.candidate_ids)
    _choose(session, choices.select(before, "normal_move"))
    normal = _context(session)
    result: dict[str, object] = {
        "schema": "stage2-normal-move-exact-base-probe-v1",
        "side": args.side,
        "checkout_base": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runtime": verified_engine_build_identity().build_id,
        "python": sys.version,
        "platform": platform.platform(),
        "lock_sha256": hashlib.sha256(Path("uv.lock").read_bytes()).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "batch": _BATCH,
        "sample_count": _SAMPLES,
        "retreat": retreat,
        "finite_options_sha256": choices.content_hash,
        "normal_observation_sha256": normal.observation_hash,
    }
    if args.side == "head":
        from warhammer40k_core.ai.screen_movement_candidates import generate_normal_move_proposals

        result["generated_normal_move"] = _time(generate_normal_move_proposals, normal)
    result["ordinary_native_control"] = _ordinary_control(session, normal)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
