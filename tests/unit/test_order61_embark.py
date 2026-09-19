from __future__ import annotations

import pytest
from msgspec.structs import replace
from tests.order61_embark_helpers import (
    TRANSPORT_ID,
    UNIT_ID,
    embark_option_ids,
    embark_session,
)

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phase_movement_history import PhaseMovementRecord
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
    state.phase_movement_history[0] = replace(record, setup_kind=None)
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
