from __future__ import annotations

import json

import pytest
from msgspec.structs import replace
from tests.order61_embark_helpers import (
    TRANSPORT_ID,
    UNIT_ID,
    embark_option_ids,
    embark_session,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phase_movement_history import PhaseMovementRecord
from warhammer40k_core.engine.transport_embark_context import NoMovementEmbarkContext
from warhammer40k_core.engine.transports import (
    EmbarkSelection,
    TransportMovementStatus,
    TransportRestrictionOverride,
    TransportRestrictionOverrideKind,
    resolve_embark,
)


@pytest.mark.parametrize(
    "kind",
    [
        BattlefieldPlacementKind.DISEMBARK,
        BattlefieldPlacementKind.STRATEGIC_RESERVES,
        BattlefieldPlacementKind.DEEP_STRIKE,
        BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,
    ],
)
@pytest.mark.parametrize("turn_player", ["player-a", "player-b"])
def test_setup_blocks_every_transport_throughout_actual_turn(
    kind: BattlefieldPlacementKind, turn_player: str
) -> None:
    session = embark_session()
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.active_player_id = turn_player
    placement = state.battlefield_state.unit_placement_by_id(UNIT_ID)
    record = PhaseMovementRecord(
        event_id="order61:setup",
        battle_round=1,
        turn_player_id=turn_player,
        phase=BattlePhase.COMMAND,
        unit_instance_id=UNIT_ID,
        model_instance_ids=tuple(
            sorted(row.model_instance_id for row in placement.model_placements)
        ),
        is_surge=False,
        is_ingress=kind
        in {BattlefieldPlacementKind.STRATEGIC_RESERVES, BattlefieldPlacementKind.DEEP_STRIKE},
        setup_kind=kind,
    )
    state.phase_movement_history.append(record)
    assert embark_option_ids(session) == ()
    # A source permitting embark after disembark does not exempt Ingress/repositioning.
    resolution = resolve_embark(
        scenario=battlefield_scenario_for_state(state=state),
        cargo_state=state.transport_cargo_states[0],
        selection=EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=UNIT_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            movement_phase_action=TransportMovementStatus.NORMAL_MOVE,
            restriction_overrides=(
                TransportRestrictionOverride(
                    override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                    source_rule_id="test:explicit-disembark-exemption",
                ),
            ),
        ),
        unit_placement=placement,
        transport_placement=state.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
        movement_history=tuple(state.phase_movement_history),
        turn_player_id=turn_player,
    )
    assert resolution.is_valid is (kind is BattlefieldPlacementKind.DISEMBARK)
    # Same battle round, other player's turn: restriction expired.
    state.active_player_id = "player-b" if turn_player == "player-a" else "player-a"
    assert embark_option_ids(session) == (TRANSPORT_ID,)

    state.active_player_id = turn_player
    state.battle_round = 2
    assert embark_option_ids(session) == (TRANSPORT_ID,)
    state.battle_round = 1
    state.phase_movement_history[0] = replace(record, setup_kind=None, is_ingress=False)
    assert embark_option_ids(session) == (TRANSPORT_ID,)


def test_tactical_setup_followup_move_suppresses_embark_restores_and_replays() -> None:
    import copy

    from tests.disembark_eligibility_helpers import PASSENGER_ID, disembark_session
    from tests.movement_submission_helpers import straight_line_witness_for_state
    from tests.order60_emergency_disembark_helpers import emergency_disembark_unit_placement
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
        PlacementProposalPayload,
        ProposalKind,
    )
    from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
    from warhammer40k_core.engine.transports import DisembarkModeKind

    session = disembark_session()
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    initial = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="order61:select", option_id=PASSENGER_ID
    )
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="order61:disembark",
        option_id="disembark",
    )
    assert status.decision_request is not None
    request = status.decision_request
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    placement = emergency_disembark_unit_placement(
        passenger, army_id="army-alpha", player_id="player-a", center_x=10, center_y=10
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order61:place",
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=PASSENGER_ID,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=placement,
                transport_unit_instance_id=TRANSPORT_ID,
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    (setup,) = state.phase_movement_history
    assert setup.setup_kind is BattlefieldPlacementKind.DISEMBARK
    assert setup.turn_player_id == "player-a"
    checkpoint = session.lifecycle.to_payload()
    restored = LocalGameSession(GameLifecycle.from_payload(checkpoint))
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    tampered = copy.deepcopy(checkpoint)
    tampered["state"]["phase_movement_history"][0]["setup_kind"] = None
    with pytest.raises(GameLifecycleError, match="Phase movement history differs"):
        GameLifecycle.from_payload(tampered)
    request = pending_request(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="order61:normal", option_id="normal_move"
    )
    assert status.decision_request is not None
    request = status.decision_request
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order61:move",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=PASSENGER_ID,
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL,
                witness=straight_line_witness_for_state(
                    state,
                    unit_instance_id=PASSENGER_ID,
                    dx=0,
                    dy=0,
                ),
            ).to_payload()
        ),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert status.decision_request is not None
    assert status.decision_request.decision_type != "select_embark_transport"
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none(PASSENGER_ID) is not None
    GameLifecycle.from_payload(session.lifecycle.to_payload())
    artifact = ReplayArtifact.capture(
        artifact_id="order61", final_lifecycle=session.lifecycle, initial_lifecycle_payload=initial
    )
    replay = ReplayRunner(artifact).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("drift", [False, True])
def test_embark_finite_submission_revalidates_setup_before_queue_pop(drift: bool) -> None:
    from tests.movement_submission_helpers import straight_line_witness_for_state
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalPayload,
        MovementProposalRequest,
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = embark_session()
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="order61:unit", option_id=UNIT_ID
    )
    assert status.decision_request is not None
    status = session.submit_option(
        request_id=status.decision_request.request_id,
        result_id="order61:normal",
        option_id="normal_move",
    )
    assert status.decision_request is not None
    request = status.decision_request
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order61:path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=UNIT_ID,
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL,
                witness=straight_line_witness_for_state(state, unit_instance_id=UNIT_ID),
            ).to_payload()
        ),
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request.decision_type == "select_embark_transport"
    if drift:
        assert state.battlefield_state is not None
        placement = state.battlefield_state.unit_placement_by_id(UNIT_ID)
        state.phase_movement_history.append(
            PhaseMovementRecord(
                event_id="order61:intervening-setup",
                battle_round=1,
                turn_player_id="player-a",
                phase=BattlePhase.MOVEMENT,
                unit_instance_id=UNIT_ID,
                model_instance_ids=tuple(
                    sorted(row.model_instance_id for row in placement.model_placements)
                ),
                is_surge=False,
                is_ingress=True,
                setup_kind=BattlefieldPlacementKind.DEEP_STRIKE,
            )
        )
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id, result_id="order61:embark", option_id=TRANSPORT_ID
    )
    if drift:
        assert status.status_kind is LifecycleStatusKind.INVALID
        assert session.lifecycle.to_payload() == before
    else:
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        assert state.battlefield_state is not None
        assert state.battlefield_state.unit_placement_or_none(UNIT_ID) is None


def test_setup_history_has_no_missing_field_or_surge_fallback() -> None:
    from warhammer40k_core.engine.phase import GameLifecycleError

    row = PhaseMovementRecord(
        event_id="order61:history",
        battle_round=1,
        turn_player_id="player-a",
        phase=BattlePhase.MOVEMENT,
        unit_instance_id=UNIT_ID,
        model_instance_ids=("model:one",),
        is_surge=False,
        is_ingress=False,
        setup_kind=BattlefieldPlacementKind.DISEMBARK,
    )
    assert PhaseMovementRecord.from_payload(row.to_payload()) == row
    missing = row.to_payload()
    del missing["setup_kind"]
    with pytest.raises(GameLifecycleError, match="schema drifted"):
        PhaseMovementRecord.from_payload(missing)
    invalid = row.to_payload()
    invalid["is_surge"] = True
    with pytest.raises(GameLifecycleError, match="schema drifted"):
        PhaseMovementRecord.from_payload(invalid)


def test_no_movement_embark_preserves_source_context_without_a_move() -> None:
    context = NoMovementEmbarkContext(
        source_rule_id="faq:c2df3e97-f21e-4fc9-943e-37072c08c10e",
        permission_effect_id="order114:permission",
        occasion_id="order114:occasion",
        battle_round=1,
        turn_player_id="player-a",
        phase=BattlePhase.MOVEMENT,
        unit_instance_id="army-alpha:passengers",
    )
    selection = EmbarkSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=context.unit_instance_id,
        transport_unit_instance_id="army-alpha:transport",
        movement_phase_action=TransportMovementStatus.NOT_MOVED,
        source_context=context,
        restriction_overrides=(
            TransportRestrictionOverride(
                override_kind=TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK,
                source_rule_id=context.source_rule_id,
            ),
        ),
    )
    assert EmbarkSelection.from_payload(json.loads(json.dumps(selection.to_payload()))) == selection
    assert selection.movement_phase_action is TransportMovementStatus.NOT_MOVED


@pytest.mark.parametrize("action", ["not_moved", "remain_stationary", "ingress_move"])
def test_ordinary_embark_still_requires_its_real_move(action: str) -> None:
    with pytest.raises(GameLifecycleError, match="requires"):
        EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:passengers",
            transport_unit_instance_id="army-alpha:transport",
            movement_phase_action=TransportMovementStatus(action),
        )


@pytest.mark.parametrize("decline", [False, True])
def test_source_embark_after_real_disembark_facade_restore_fork_replay(decline: bool) -> None:
    from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
    from tests.order114_embark_helpers import disembark_at_transport, source_embark_session
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session = source_embark_session()
    initial = session.lifecycle.to_payload()
    disembark_at_transport(session)
    request = pending_request(session)
    assert request.decision_type == "select_embark_transport"
    assert isinstance(request.payload, dict)
    assert "movement_context" not in request.payload
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    checkpoint = session.lifecycle.to_payload()
    restored = LocalGameSession(GameLifecycle.from_payload(json.loads(json.dumps(checkpoint))))
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    option = "decline_embark" if decline else TRANSPORT_ID
    for active in (session, restored):
        status = active.submit_option(
            request_id=request.request_id,
            result_id="order114:embark",
            option_id=option,
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        GameLifecycle.from_payload(json.loads(json.dumps(active.lifecycle.to_payload())))
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert not any(
        row.event_type == "movement_activation_completed"
        for row in session.lifecycle.decision_controller.event_log.records
    )
    assert (state.battlefield_state.unit_placement_or_none(PASSENGER_ID) is None) is not decline
    cargo = state.transport_cargo_state_for_transport(TRANSPORT_ID)
    assert cargo is not None
    assert cargo.contains_unit(PASSENGER_ID) is not decline
    artifact = ReplayArtifact.capture(
        artifact_id="order114",
        final_lifecycle=session.lifecycle,
        initial_lifecycle_payload=initial,
    )
    replay = ReplayRunner(artifact).run()
    assert replay.reproduced_exactly, replay


def test_source_embark_after_disembark_requires_the_distinct_explicit_permission() -> None:
    from tests.order114_embark_helpers import disembark_at_transport, source_embark_session
    from tests.psychic_modifier_helpers import pending_request

    session = source_embark_session(allow_after_disembark=False)
    disembark_at_transport(session)
    assert pending_request(session).decision_type == "select_movement_action"


@pytest.mark.parametrize("drift", ["permission", "capacity", "distance"])
def test_source_embark_revalidates_supported_drift_before_queue_pop(drift: str) -> None:
    from dataclasses import replace as dataclass_replace

    from tests.disembark_eligibility_helpers import PASSENGER_ID
    from tests.order114_embark_helpers import disembark_at_transport, source_embark_session
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.engine.phase import LifecycleStatusKind

    session = source_embark_session()
    disembark_at_transport(session)
    state = session.lifecycle.state
    assert state is not None
    request = pending_request(session)
    if drift == "permission":
        state.remove_persisting_effects_by_id(("order114:permission",))
    elif drift == "capacity":
        cargo = state.transport_cargo_state_for_transport(TRANSPORT_ID)
        assert cargo is not None
        state.replace_transport_cargo_state(
            dataclass_replace(
                cargo,
                capacity_profile=dataclass_replace(cargo.capacity_profile, max_model_count=1),
            )
        )
    else:
        from tests.core_stratagem_helpers import _replace_unit_poses

        from warhammer40k_core.geometry.pose import Pose

        _replace_unit_poses(state, unit_instance_id=TRANSPORT_ID, poses=(Pose.at(30, 10),))
    before = session.lifecycle.to_payload()
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order114:stale",
        option_id=TRANSPORT_ID,
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert pending_request(session) == request
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none(PASSENGER_ID) is not None


def test_attached_source_embark_moves_every_component_and_restores_replays() -> None:
    from tests.order114_embark_helpers import attached_source_embark_session, disembark_at_transport
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    session, unit_id = attached_source_embark_session()
    initial = session.lifecycle.to_payload()
    disembark_at_transport(session, unit_instance_id=unit_id)
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
    assert len(view.component_unit_instance_ids) == 2
    request = pending_request(session)
    assert request.decision_type == "select_embark_transport"
    fork = LocalGameSession(
        GameLifecycle.from_payload(
            json.loads(
                json.dumps(
                    session.lifecycle.to_payload(),
                )
            )
        )
    )
    status = session.submit_option(
        request_id=request.request_id,
        result_id="order114:attached-embark",
        option_id=TRANSPORT_ID,
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert pending_request(fork) == request
    cargo = state.transport_cargo_state_for_transport(TRANSPORT_ID)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == tuple(sorted(view.component_unit_instance_ids))
    assert state.battlefield_state is not None
    assert all(
        state.battlefield_state.unit_placement_or_none(component_id) is None
        for component_id in view.component_unit_instance_ids
    )
    restored = LocalGameSession(
        GameLifecycle.from_payload(
            json.loads(
                json.dumps(
                    session.lifecycle.to_payload(),
                )
            )
        )
    )
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order114:attached",
            final_lifecycle=session.lifecycle,
            initial_lifecycle_payload=initial,
        )
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("field", ["unit_instance_id", "battle_round"])
def test_no_movement_context_identity_cannot_be_forged_into_another_selection(field: str) -> None:
    from dataclasses import replace as dataclass_replace

    context = NoMovementEmbarkContext(
        source_rule_id="order114:source",
        permission_effect_id="order114:effect",
        occasion_id="order114:occasion",
        battle_round=1,
        turn_player_id="player-a",
        phase=BattlePhase.MOVEMENT,
        unit_instance_id=UNIT_ID,
    )
    wrong = (
        dataclass_replace(context, unit_instance_id="other-unit")
        if field == "unit_instance_id"
        else dataclass_replace(context, battle_round=2)
    )
    with pytest.raises(GameLifecycleError, match="source context drift"):
        EmbarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=UNIT_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            movement_phase_action=TransportMovementStatus.NOT_MOVED,
            source_context=wrong,
        )


def test_source_embark_then_rejected_disembark_retry_restores_and_replays() -> None:
    from tests.disembark_eligibility_helpers import PASSENGER_ID
    from tests.order60_emergency_disembark_helpers import emergency_disembark_unit_placement
    from tests.order114_embark_helpers import disembark_at_transport
    from tests.psychic_modifier_helpers import pending_request

    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.engine.damage_allocation import unit_by_id
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.movement_proposals import PlacementProposalPayload, ProposalKind
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
    from warhammer40k_core.engine.transport_source_embark import (
        no_movement_embark_permission_effect,
    )
    from warhammer40k_core.engine.transports import DisembarkModeKind

    session = embark_session()
    state = session.lifecycle.state
    assert state is not None
    state.record_persisting_effect(
        no_movement_embark_permission_effect(
            context=NoMovementEmbarkContext(
                source_rule_id="faq:c2df3e97-f21e-4fc9-943e-37072c08c10e",
                permission_effect_id="order114:retry-permission",
                occasion_id="order114:retry-occasion",
                battle_round=state.battle_round,
                turn_player_id="player-a",
                phase=BattlePhase.MOVEMENT,
                unit_instance_id=UNIT_ID,
            ),
            owner_player_id="player-a",
            allow_after_disembark=False,
        )
    )
    initial = session.lifecycle.to_payload()
    GameLifecycle.from_payload(json.loads(json.dumps(initial)))
    for option_id, result_id in (
        (UNIT_ID, "order114:retry-source-unit"),
        (TRANSPORT_ID, "order114:retry-source-embark"),
        (PASSENGER_ID, "order114:retry-passenger"),
        ("disembark", "order114:retry-disembark"),
    ):
        request = pending_request(session)
        status = session.submit_option(
            request_id=request.request_id, result_id=result_id, option_id=option_id
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
    request = pending_request(session)
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order114:retry-invalid-placement",
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=PASSENGER_ID,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=emergency_disembark_unit_placement(
                    unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
                    army_id="army-alpha",
                    player_id="player-a",
                    center_x=30,
                    center_y=10,
                ),
                transport_unit_instance_id=TRANSPORT_ID,
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert pending_request(session).decision_type == "select_movement_unit"
    assert any(
        event.event_type == "movement_setup_failed"
        for event in session.lifecycle.decision_controller.event_log.records
    )
    checkpoint = session.lifecycle.to_payload()
    restored = LocalGameSession(GameLifecycle.from_payload(json.loads(json.dumps(checkpoint))))
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == session.events_since(EventStreamCursor(), viewer_player_id=viewer)
    for active in (session, restored):
        disembark_at_transport(active)
        GameLifecycle.from_payload(json.loads(json.dumps(active.lifecycle.to_payload())))
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert (
        ReplayRunner(
            ReplayArtifact.capture(
                artifact_id="order114:retry-replay",
                final_lifecycle=session.lifecycle,
                initial_lifecycle_payload=initial,
            )
        )
        .run()
        .reproduced_exactly
    )
