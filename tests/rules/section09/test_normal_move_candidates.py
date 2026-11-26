"""Ordinary Normal Move alternatives and their native actor boundary."""

import json
from math import hypot, isclose
from typing import cast

import pytest

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import movement_case, select
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.ai.finite_candidates import FiniteCandidateSet
from warhammer40k_core.ai.player_policy import PlayerDecisionContext, PolicyError
from warhammer40k_core.ai.screen_movement_candidates import (
    MAX_NORMAL_MOVE_PROPOSALS,
    ScreenMovementGap,
    ScreenMovementGapReason,
    generate_normal_move_proposals,
)
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalPayloadPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifactPayload, ReplayRunner
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def test_normal_paths_use_native_offer_alongside_unchanged_hold(
    section09_definitions: Section02Definitions,
) -> None:
    for choice in ("remain_stationary", "normal_move"):
        session, state, unit = movement_case(section09_definitions)
        actor = select(session, unit).actor_id
        assert actor is not None
        viewer = ViewerContext.for_player(actor)
        view = session.view_for_context(viewer=viewer)
        context = PlayerDecisionContext.from_view(view, choice_seed=0)
        model_ids = {model.model_instance_id for model in unit.own_models}
        board = view["battlefield_view"]
        assert board is not None
        starts = {
            model_id: board["authoritative"]["models_by_id"][model_id]["pose"]
            for model_id in model_ids
        }
        finite = FiniteCandidateSet.from_context(context)
        assert {"normal_move", "remain_stationary"} <= set(finite.candidate_ids)
        with pytest.raises(ScreenMovementGap) as wrong_route:
            generate_normal_move_proposals(context)
        assert wrong_route.value.reason is ScreenMovementGapReason.NO_ORDINARY_NORMAL_MOVE_REQUEST
        action = finite.select(context, choice)
        assert action.option_id is not None
        status = session.submit_viewer_option(
            viewer=viewer,
            request_id=action.request_id,
            option_id=action.option_id,
            result_id=f"normal-test:{choice}",
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        if choice == "remain_stationary":
            after = session.view_for_context(viewer=viewer)["battlefield_view"]
            assert after is not None
            assert all(
                after["authoritative"]["models_by_id"][model_id]["pose"] == start
                for model_id, start in starts.items()
            )
            continue

        view = session.view_for_context(viewer=viewer)
        context = PlayerDecisionContext.from_view(view, choice_seed=0)
        enemy = next(player for player in state.player_ids if player != actor)
        with pytest.raises(PolicyError, match="own pending actor request"):
            PlayerDecisionContext.from_view(session.view(viewer_player_id=enemy), choice_seed=0)
        generated = generate_normal_move_proposals(context)
        assert 1 <= len(generated) <= MAX_NORMAL_MOVE_PROPOSALS == 32
        assert len(generated) == len(set(generated))
        assert (
            generate_normal_move_proposals(PlayerDecisionContext.from_view(view, choice_seed=42))
            == generated
        )
        shortest_move = min(
            value
            for model_id in starts
            if (
                value := view["model_display_by_id"][model_id]["current_characteristics"]["M"][
                    "final"
                ]
            )
            is not None
        )
        southbound: list[tuple[str, JsonValue, PathWitness]] = []
        for candidate in generated:
            assert candidate.option_id is None
            assert candidate.actor_id == actor
            assert candidate.request_id == context.request["request_id"]
            assert candidate.observation_hash == context.observation_hash
            assert candidate.proposal_json is not None
            payload: JsonValue = json.loads(candidate.proposal_json)
            proposal = MovementProposalPayload.from_payload(
                cast(MovementProposalPayloadPayload, payload)
            )
            assert proposal.proposal_request_id == candidate.request_id
            assert proposal.proposal_kind is ProposalKind.NORMAL_MOVE
            assert proposal.movement_mode == MovementMode.NORMAL
            assert proposal.fall_back_mode is None
            assert proposal.unit_instance_id == unit.unit_instance_id
            assert set(proposal.witness.model_ids()) == model_ids

            deltas: list[tuple[float, float]] = []
            for model_id, (start, end) in proposal.witness.model_paths:
                origin = starts[model_id]
                assert origin is not None
                assert start.position.x == origin["position"]["x_inches"]
                assert start.position.y == origin["position"]["y_inches"]
                assert start.position.z == end.position.z == origin["position"]["z_inches"]
                assert start.facing == end.facing
                deltas.append(
                    (end.position.x - start.position.x, end.position.y - start.position.y)
                )
            dx, dy = deltas[0]
            assert all(
                isclose(x, dx, abs_tol=1e-9) and isclose(y, dy, abs_tol=1e-9) for x, y in deltas
            )
            assert 0 < hypot(dx, dy) <= shortest_move
            if dx == 0 and dy < 0:
                southbound.append((candidate.request_id, payload, proposal.witness))
        assert context.observation == session.view_for_context(viewer=viewer)

        assert len(southbound) == 2
        request_id, payload, witness = southbound[0]
        with pytest.raises(GameLifecycleError, match="stale or unissued"):
            session.submit_viewer_parameterized_payload(
                viewer=viewer,
                request_id=action.request_id,
                result_id="normal-test:stale",
                payload=payload,
            )
        assert context.observation == session.view_for_context(viewer=viewer)
        status = session.submit_viewer_parameterized_payload(
            viewer=viewer, request_id=request_id, result_id="normal-test:path", payload=payload
        )
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        after = session.view_for_context(viewer=viewer)["battlefield_view"]
        assert after is not None
        for model_id, (_, end) in witness.model_paths:
            pose = after["authoritative"]["models_by_id"][model_id]["pose"]
            assert pose is not None
            assert pose["position"]["x_inches"] == end.position.x
            assert pose["position"]["y_inches"] == end.position.y


def test_generated_normal_move_replays_with_exact_viewer_history() -> None:
    lifecycle, units = charge_lifecycle(
        game_id="generated-normal-move-replay",
        alpha_unit_ids=("moving", "spare"),
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(40, 40), model_count=5),
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
    viewer = ViewerContext.for_player("player-a")
    for option_id in (units["moving"].unit_instance_id, "normal_move"):
        context = PlayerDecisionContext.from_view(
            session.view_for_context(viewer=viewer), choice_seed=0
        )
        action = FiniteCandidateSet.from_context(context).select(context, option_id)
        assert action.option_id is not None
        assert (
            session.submit_viewer_option(
                viewer=viewer,
                request_id=action.request_id,
                option_id=action.option_id,
                result_id=f"normal-replay:{option_id}",
            ).status_kind
            is LifecycleStatusKind.WAITING_FOR_DECISION
        )

    context = PlayerDecisionContext.from_view(
        session.view_for_context(viewer=viewer), choice_seed=0
    )
    # On this open fixture the new branch has a full five-model formation and
    # exactly one candidate per point in the bounded stencil.
    generated = generate_normal_move_proposals(context)
    assert len(generated) == 32
    for action in generated:
        assert action.proposal_json is not None
        payload: JsonValue = json.loads(action.proposal_json)
        witness = MovementProposalPayload.from_payload(
            cast(MovementProposalPayloadPayload, payload)
        ).witness
        assert len(witness.model_ids()) == 5
        start, end = witness.model_paths[0][1]
        if end.position.x == start.position.x and end.position.y < start.position.y:
            break
    else:
        pytest.fail("The open fixture did not generate a southbound translation.")
    assert (
        session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=action.request_id,
            payload=payload,
            result_id="normal-replay:path",
        ).status_kind
        is LifecycleStatusKind.WAITING_FOR_DECISION
    )
    checkpoint = session.to_persistence_payload()
    assert isinstance(checkpoint, dict)
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    for player in state.player_ids:
        assert restored.view(viewer_player_id=player) == session.view(viewer_player_id=player)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=player
        ) == session.events_since(EventStreamCursor(), viewer_player_id=player)
    replay = ReplayRunner.from_payload(
        cast(ReplayArtifactPayload, checkpoint["replay_artifact"])
    ).run()
    assert replay.reproduced_exactly
    assert replay.final_event_log_hash == checkpoint["event_log_hash"]
