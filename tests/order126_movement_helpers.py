"""Canonical catalog/facade fixtures for submitted sequential physical moves."""

from __future__ import annotations

import json

from tests.phase15a_charge_declaration_helpers import charge_lifecycle, compact_test_unit_poses
from tests.psychic_modifier_helpers import pending_request
from warhammer40k_core.adapters.access_control import (
    ROLE_POLICY_BY_ROLE,
    PrincipalRole,
    ViewerContext,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def sequential_session(*, attached: bool = False) -> LocalGameSession:
    lifecycle, _ = charge_lifecycle(
        alpha_unit_ids=("mover", "leader") if attached else ("mover",),
        alpha_attached_unit_ids=("mover", "leader") if attached else None,
        alpha_origins={"mover": Pose.at(10, 20), "leader": Pose.at(10, 21.8)},
        enemy_model_poses=compact_test_unit_poses(origin=Pose.at(35, 20), model_count=5),
        game_id=f"order126-sequential-{attached}",
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    return LocalGameSession(lifecycle)


def select_move(session: LocalGameSession) -> DecisionRequest:
    request = pending_request(session)
    unit_id = (
        "attached-unit:army-alpha:mover"
        if "attached-unit:army-alpha:mover" in (option.option_id for option in request.options)
        else "army-alpha:mover"
    )
    session.submit_option(
        request_id=request.request_id, option_id=unit_id, result_id="order126-select"
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, option_id="normal_move", result_id="order126-normal"
    )
    return pending_request(session)


def submit_path(
    session: LocalGameSession, request: DecisionRequest, witness: PathWitness, *, result_id: str
) -> LifecycleStatus:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=result_id,
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode="normal",
                witness=witness,
            ).to_payload()
        ),
    )


def assert_session_roundtrips(session: LocalGameSession) -> LocalGameSession:
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    assert restored.to_persistence_payload() == checkpoint
    fork = session.fork()
    assert fork.to_persistence_payload() == checkpoint
    viewers = (
        ViewerContext.for_player("player-a"),
        ViewerContext.for_player("player-b"),
        *(
            ViewerContext(
                principal_id=f"order126-{role.value}",
                role=role,
                viewer_player_id=None,
                policy=ROLE_POLICY_BY_ROLE[role],
            )
            for role in (PrincipalRole.DELAYED_SPECTATOR, PrincipalRole.ADMINISTRATOR)
        ),
    )
    for viewer in viewers:
        assert restored.view_for_context(viewer=viewer) == session.view_for_context(viewer=viewer)
        assert restored.events_since_for_context(
            EventStreamCursor(), viewer=viewer
        ) == session.events_since_for_context(EventStreamCursor(), viewer=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order126")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED, replay
    return restored
