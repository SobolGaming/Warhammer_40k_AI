from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.adapters.contracts import (
    FiniteOptionSubmission,
    ParameterizedSubmission,
)
from warhammer40k_core.adapters.decisions import (
    result_for_option,
    result_for_payload,
    submit_option,
)
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest, parameterized_decision_option
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_DISEMBARK_UNIT_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    FallBackModeKind,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementPhaseStepKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    TransportCapacityProfile,
    TransportCargoState,
    TransportMovementStatus,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack

_ORDERED_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}"
)
_DESPERATE_FALL_BACK_OPTION_ID = (
    f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}"
)


def test_normal_move_uses_parameterized_proposal_without_finite_endpoint_options() -> None:
    session, action_request = _local_session_at_first_movement_action()
    normal_option = action_request.option_by_id(MovementPhaseActionKind.NORMAL_MOVE.value)
    normal_payload = cast(dict[str, object], normal_option.payload)

    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert set(normal_payload) == {"movement_phase_action", "unit_instance_id", "movement_mode"}
    assert normal_payload["movement_mode"] == MovementMode.NORMAL.value

    proposal_status = session.submit_option(
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase11d-normal-action",
    )
    proposal_request = _decision_request(proposal_status)
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _session_state(session)
    before = _unit_placement(state, "army-alpha:intercessor-unit-1")

    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.NORMAL_MOVE
    assert proposal.movement_phase_action == MovementPhaseActionKind.NORMAL_MOVE.value
    assert proposal.context is not None
    assert proposal.context["movement_mode"] == MovementMode.NORMAL.value

    status = session.submit_payload(
        payload=_json(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.NORMAL_MOVE,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
                movement_mode=MovementMode.NORMAL.value,
                witness=_shift_witness(before, dx=3.0),
            ).to_payload()
        ),
        result_id="phase11d-normal-proposal",
    )
    after = _unit_placement(state, "army-alpha:intercessor-unit-1")
    terminal_event = _last_event_payload(
        session.lifecycle.decision_controller,
        "movement_activation_completed",
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert after.model_placements[0].pose.position.x == (
        before.model_placements[0].pose.position.x + 3.0
    )
    assert terminal_event["proposal_request_id"] == proposal.request_id


def test_parameterized_lifecycle_resume_preserves_pending_movement_proposal_mode() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(session.lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    pending_requests = restored.decision_controller.queue.pending_requests
    assert payload["parameterized_movement_proposals"] is True
    assert len(pending_requests) == 1

    status = restored.submit_decision(
        DecisionResult.for_request(
            result_id="phase11d-restored-normal-action",
            request=pending_requests[0],
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        )
    )
    proposal_request = _decision_request(status)

    assert restored.parameterized_movement_proposals is True
    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal_request.is_parameterized_submission_request()


def test_non_parameterized_movement_mode_is_rejected() -> None:
    with pytest.raises(GameLifecycleError, match="requires parameterized movement proposals"):
        GameLifecycle(parameterized_movement_proposals=False)
    with pytest.raises(GameLifecycleError, match="requires parameterized proposals"):
        MovementPhaseHandler(parameterized_proposals=False)


def test_parameterized_normal_move_proposal_request_matches_golden_fixture() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-golden-normal-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    view = session.view(viewer_player_id=proposal.actor_id)

    assert proposal.to_payload() == _golden_json("phase11d_normal_move_proposal_request.json")
    assert view["pending_proposal"] == proposal.to_payload()


def test_invalid_movement_proposal_returns_typed_invalid_without_mutation() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-invalid-normal-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _session_state(session)
    before = _unit_placement(state, proposal.unit_instance_id)
    before_payload = state.battlefield_state.to_payload() if state.battlefield_state else None
    before_record_count = len(session.lifecycle.decision_controller.records)

    status = session.submit_payload(
        payload=_json(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.NORMAL_MOVE,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
                movement_mode=MovementMode.NORMAL.value,
                witness=_shift_witness(before, dx=80.0),
            ).to_payload()
        ),
        result_id="phase11d-invalid-normal-proposal",
    )
    payload = cast(dict[str, object], status.payload)
    proposal_validation = cast(dict[str, object], payload["proposal_validation"])

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert payload["violation_code"] == "movement_distance_exceeded"
    assert proposal_validation["is_valid"] is False
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_payload
    assert len(session.lifecycle.decision_controller.records) == before_record_count + 1
    pending_requests = session.lifecycle.decision_controller.queue.pending_requests
    assert len(pending_requests) == 1
    retry_proposal = MovementProposalRequest.from_decision_request_payload(
        pending_requests[0].payload
    )
    assert retry_proposal.request_id != proposal.request_id
    assert retry_proposal.proposal_kind is proposal.proposal_kind
    assert retry_proposal.unit_instance_id == proposal.unit_instance_id
    assert retry_proposal.source_decision_request_id == proposal.source_decision_request_id
    assert retry_proposal.source_decision_result_id == proposal.source_decision_result_id


def test_stale_proposal_submission_is_rejected() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-stale-normal-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _session_state(session)
    before = _unit_placement(state, proposal.unit_instance_id)
    before_record_count = len(session.lifecycle.decision_controller.records)

    status = session.submit_payload(
        payload=_json(
            MovementProposalPayload(
                proposal_request_id="stale-proposal-request",
                proposal_kind=ProposalKind.NORMAL_MOVE,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
                movement_mode=MovementMode.NORMAL.value,
                witness=_shift_witness(before, dx=3.0),
            ).to_payload()
        ),
        result_id="phase11d-stale-normal-proposal",
    )
    payload = cast(dict[str, object], status.payload)
    validation = cast(dict[str, object], payload["proposal_validation"])

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert validation["status"] == "stale"
    assert cast(list[dict[str, object]], validation["violations"])[0]["violation_code"] == (
        "stale_proposal_request"
    )
    assert len(session.lifecycle.decision_controller.records) == before_record_count
    assert session.lifecycle.decision_controller.queue.pending_requests == (proposal_request,)


def test_movement_proposal_drift_rejections_keep_pending_request_and_records_clean() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-drift-normal-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    state = _session_state(session)
    before = _unit_placement(state, proposal.unit_instance_id)
    base_payload = MovementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=ProposalKind.NORMAL_MOVE,
        unit_instance_id=proposal.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        movement_mode=MovementMode.NORMAL.value,
        witness=_shift_witness(before, dx=3.0),
    ).to_payload()
    drift_cases = (
        (
            "phase11d-kind-drift",
            {**base_payload, "proposal_kind": ProposalKind.ADVANCE.value},
            "proposal_kind_drift",
        ),
        (
            "phase11d-unit-drift",
            {**base_payload, "unit_instance_id": "army-alpha:wrong-unit"},
            "proposal_unit_drift",
        ),
        (
            "phase11d-action-drift",
            {**base_payload, "movement_phase_action": MovementPhaseActionKind.ADVANCE.value},
            "proposal_action_drift",
        ),
        (
            "phase11d-movement-mode-drift",
            {**base_payload, "movement_mode": MovementMode.ADVANCE.value},
            "proposal_movement_mode_drift",
        ),
    )
    before_record_count = len(session.lifecycle.decision_controller.records)

    for result_id, payload, violation_code in drift_cases:
        status = session.submit_payload(payload=_json(payload), result_id=result_id)
        violation = cast(
            list[dict[str, object]],
            _proposal_validation(status)["violations"],
        )[0]

        assert status.status_kind is LifecycleStatusKind.INVALID
        assert violation["violation_code"] == violation_code
        assert len(session.lifecycle.decision_controller.records) == before_record_count
        assert session.lifecycle.decision_controller.queue.pending_requests == (proposal_request,)


def test_malformed_movement_proposal_payload_returns_typed_invalid_and_keeps_request() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-malformed-normal-action",
        )
    )
    before_record_count = len(session.lifecycle.decision_controller.records)

    status = session.submit_payload(
        payload={
            "proposal_kind": ProposalKind.NORMAL_MOVE.value,
            "unit_instance_id": "army-alpha:intercessor-unit-1",
            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
            "witness": {"model_paths": []},
        },
        result_id="phase11d-missing-proposal-request-id",
    )
    validation = _proposal_validation(status)
    pending_requests = session.lifecycle.decision_controller.queue.pending_requests

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert validation["status"] == "invalid"
    assert cast(list[dict[str, object]], validation["violations"])[0] == {
        "violation_code": "proposal_payload_missing_field",
        "message": "Proposal payload missing required field: proposal_request_id.",
        "field": "proposal_request_id",
    }
    assert len(session.lifecycle.decision_controller.records) == before_record_count
    assert len(pending_requests) == 1
    assert pending_requests[0].request_id == proposal_request.request_id


def test_malformed_movement_proposal_witness_and_kind_return_typed_invalid() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-malformed-witness-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)

    witness_status = session.submit_payload(
        payload={
            "proposal_request_id": proposal.request_id,
            "proposal_kind": ProposalKind.NORMAL_MOVE.value,
            "unit_instance_id": proposal.unit_instance_id,
            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
            "witness": {"model_paths": "not-a-list"},
        },
        result_id="phase11d-malformed-witness",
    )
    witness_violation = cast(
        list[dict[str, object]],
        _proposal_validation(witness_status)["violations"],
    )[0]

    assert witness_status.status_kind is LifecycleStatusKind.INVALID
    assert witness_violation["violation_code"] == "proposal_payload_malformed"
    assert witness_violation["field"] == "witness"

    kind_status = session.submit_payload(
        payload={
            "proposal_request_id": proposal.request_id,
            "proposal_kind": "unsupported_proposal_kind",
            "unit_instance_id": proposal.unit_instance_id,
            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
            "witness": {"model_paths": []},
        },
        result_id="phase11d-unsupported-kind",
    )
    kind_violation = cast(
        list[dict[str, object]],
        _proposal_validation(kind_status)["violations"],
    )[0]

    assert kind_status.status_kind is LifecycleStatusKind.INVALID
    assert kind_violation["violation_code"] == "unsupported_proposal_kind"
    assert kind_violation["field"] == "proposal_kind"


def test_advance_resolves_dice_then_requests_parameterized_movement() -> None:
    session, _action_request = _local_session_at_first_movement_action()
    proposal_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.ADVANCE.value,
            result_id="phase11d-advance-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    assert proposal.context is not None
    advance_roll = cast(dict[str, object], proposal.context["advance_roll"])
    advance_value = cast(int, advance_roll["value"])
    state = _session_state(session)
    before = _unit_placement(state, proposal.unit_instance_id)

    assert proposal_request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.ADVANCE
    assert proposal.context["movement_mode"] == MovementMode.ADVANCE.value
    assert "advance_roll_resolved" in {
        event.event_type for event in session.lifecycle.decision_controller.event_log.records
    }

    status = session.submit_payload(
        payload=_json(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.ADVANCE,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.ADVANCE.value,
                movement_mode=MovementMode.ADVANCE.value,
                witness=_shift_witness(before, dx=6.0 + advance_value),
            ).to_payload()
        ),
        result_id="phase11d-advance-proposal",
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert (
        state.advanced_unit_state_for_unit(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=proposal.unit_instance_id,
        )
        is not None
    )


def test_fall_back_proposal_preserves_desperate_escape_follow_up() -> None:
    session, movement_status = _local_session_at_movement_unit_selection(
        game_id="phase10o-one-v2-new-0000"
    )
    state = _session_state(session)
    _mark_first_unit_battle_shocked(state)
    _move_first_enemy_model_into_overflight_engagement(state)
    action_request = _decision_request(
        session.submit_option(
            option_id="army-alpha:intercessor-unit-1",
            result_id="phase11d-select-fall-back-unit",
        )
    )
    assert movement_status.decision_request is not None
    assert _DESPERATE_FALL_BACK_OPTION_ID in {option.option_id for option in action_request.options}
    proposal_request = _decision_request(
        session.submit_option(
            option_id=_DESPERATE_FALL_BACK_OPTION_ID,
            result_id="phase11d-fall-back-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    before = _unit_placement(state, proposal.unit_instance_id)

    assert proposal.context is not None
    assert proposal.context["movement_mode"] == MovementMode.FALL_BACK.value
    assert proposal.context["fall_back_mode"] == FallBackModeKind.DESPERATE_ESCAPE.value

    status = session.submit_payload(
        payload=_json(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.FALL_BACK,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
                movement_mode=MovementMode.FALL_BACK.value,
                fall_back_mode=FallBackModeKind.DESPERATE_ESCAPE.value,
                witness=_shift_witness(before, dx=0.0, dy=6.0),
            ).to_payload()
        ),
        result_id="phase11d-fall-back-proposal",
    )
    request = _decision_request(status)

    assert request.decision_type == "select_desperate_escape_model"


def test_fall_back_mode_drift_and_malformed_payload_keep_pending_request() -> None:
    session, _movement_status = _local_session_at_movement_unit_selection()
    state = _session_state(session)
    _mark_first_unit_battle_shocked(state)
    _move_first_enemy_model_into_overflight_engagement(state)
    action_request = _decision_request(
        session.submit_option(
            option_id="army-alpha:intercessor-unit-1",
            result_id="phase11d-select-fall-back-mode-drift-unit",
        )
    )
    proposal_request = _decision_request(
        session.submit_option(
            option_id=_DESPERATE_FALL_BACK_OPTION_ID,
            result_id="phase11d-fall-back-mode-drift-action",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(proposal_request.payload)
    before = _unit_placement(state, proposal.unit_instance_id)
    before_record_count = len(session.lifecycle.decision_controller.records)

    drift_status = session.submit_payload(
        payload=_json(
            MovementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.FALL_BACK,
                unit_instance_id=proposal.unit_instance_id,
                movement_phase_action=MovementPhaseActionKind.FALL_BACK.value,
                movement_mode=MovementMode.FALL_BACK.value,
                fall_back_mode=FallBackModeKind.ORDERED_RETREAT.value,
                witness=_shift_witness(before, dx=0.0, dy=6.0),
            ).to_payload()
        ),
        result_id="phase11d-fall-back-mode-drift",
    )
    drift_violation = cast(
        list[dict[str, object]],
        _proposal_validation(drift_status)["violations"],
    )[0]

    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert drift_status.status_kind is LifecycleStatusKind.INVALID
    assert drift_violation["violation_code"] == "proposal_fall_back_mode_drift"
    assert len(session.lifecycle.decision_controller.records) == before_record_count
    assert session.lifecycle.decision_controller.queue.pending_requests == (proposal_request,)

    malformed_status = session.submit_payload(
        payload=validate_json_value(
            {
                "proposal_request_id": proposal.request_id,
                "proposal_kind": ProposalKind.FALL_BACK.value,
                "unit_instance_id": proposal.unit_instance_id,
                "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                "movement_mode": MovementMode.FALL_BACK.value,
                "fall_back_mode": 7,
                "witness": _shift_witness(before, dx=0.0, dy=6.0).to_payload(),
            }
        ),
        result_id="phase11d-fall-back-mode-malformed",
    )
    malformed_violation = cast(
        list[dict[str, object]],
        _proposal_validation(malformed_status)["violations"],
    )[0]

    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert malformed_violation["violation_code"] == "proposal_payload_malformed"
    assert malformed_violation["field"] == "fall_back_mode"
    assert len(session.lifecycle.decision_controller.records) == before_record_count
    assert session.lifecycle.decision_controller.queue.pending_requests == (proposal_request,)


def test_valid_reserve_placement_proposal_emits_placement_records() -> None:
    state, reserve_state, reserve_unit = _battle_state_with_reserve()
    handler, decisions, selection_request = _enter_reinforcements_choice(state=state)
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11d-select-reserve",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        payload=_json(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=reserve_state.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_placement=_reserve_placement(reserve_unit=reserve_unit),
            ).to_payload()
        ),
        result_id="phase11d-place-reserve",
    )
    arrival_event = _last_event_payload(decisions, "reinforcement_unit_arrived")
    transition_batch = cast(dict[str, object], arrival_event["transition_batch"])

    assert status is None
    assert placement_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
    assert proposal.proposal_kind is ProposalKind.STRATEGIC_RESERVES
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(reserve_state.unit_instance_id)
    assert cast(list[dict[str, object]], transition_batch["placements"])[0]["placement_kind"] == (
        BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    )


def test_invalid_placement_proposal_returns_invalid_without_mutation() -> None:
    state, reserve_state, reserve_unit = _battle_state_with_reserve()
    before = state.battlefield_state.to_payload() if state.battlefield_state is not None else None
    handler, decisions, selection_request = _enter_reinforcements_choice(state=state)
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11d-select-invalid-reserve",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)
    before_record_count = len(decisions.records)

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        payload=_json(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=reserve_state.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_placement=_reserve_placement(reserve_unit=reserve_unit, y=30.0),
            ).to_payload()
        ),
        result_id="phase11d-place-invalid-reserve",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before
    assert len(decisions.records) == before_record_count + 1
    pending_requests = decisions.queue.pending_requests
    assert len(pending_requests) == 1
    retry_proposal = MovementProposalRequest.from_decision_request_payload(
        pending_requests[0].payload
    )
    assert retry_proposal.request_id != proposal.request_id
    assert retry_proposal.proposal_kind is proposal.proposal_kind
    assert retry_proposal.unit_instance_id == proposal.unit_instance_id
    assert retry_proposal.source_decision_request_id == proposal.source_decision_request_id
    assert retry_proposal.source_decision_result_id == proposal.source_decision_result_id


def test_malformed_placement_proposal_payload_returns_typed_invalid_without_mutation() -> None:
    state, reserve_state, _reserve_unit = _battle_state_with_reserve()
    before = state.battlefield_state.to_payload() if state.battlefield_state is not None else None
    handler, decisions, selection_request = _enter_reinforcements_choice(state=state)
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11d-select-malformed-reserve",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        payload={
            "proposal_request_id": proposal.request_id,
            "proposal_kind": proposal.proposal_kind.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "placement_kind": BattlefieldPlacementKind.STRATEGIC_RESERVES.value,
            "attempted_placement": [],
        },
        result_id="phase11d-place-malformed-reserve",
    )
    assert status is not None
    violation = cast(
        list[dict[str, object]],
        _proposal_validation(status)["violations"],
    )[0]

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert violation["violation_code"] == "proposal_payload_malformed"
    assert violation["field"] == "attempted_placement"
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before


def test_placement_proposal_drift_rejections_keep_pending_request_and_records_clean() -> None:
    state, reserve_state, reserve_unit = _battle_state_with_reserve()
    handler, decisions, selection_request = _enter_reinforcements_choice(state=state)
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11d-select-drift-reserve",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)
    base_payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=reserve_state.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=_reserve_placement(reserve_unit=reserve_unit),
    ).to_payload()
    drift_cases = (
        (
            "phase11d-place-stale",
            {**base_payload, "proposal_request_id": "stale-placement-request"},
            "stale_proposal_request",
        ),
        (
            "phase11d-place-kind-drift",
            {**base_payload, "proposal_kind": ProposalKind.REINFORCEMENT.value},
            "proposal_kind_drift",
        ),
        (
            "phase11d-place-unit-drift",
            {**base_payload, "unit_instance_id": "army-alpha:wrong-unit"},
            "PlacementProposalPayload attempted_placement unit drift",
        ),
        (
            "phase11d-place-placement-kind-drift",
            {**base_payload, "placement_kind": BattlefieldPlacementKind.DEEP_STRIKE.value},
            "proposal_placement_kind_drift",
        ),
    )
    before_record_count = len(decisions.records)

    for result_id, payload, violation_text in drift_cases:
        status = _submit_parameterized_handler_payload(
            handler=handler,
            state=state,
            decisions=decisions,
            request=placement_request,
            payload=_json(payload),
            result_id=result_id,
        )
        assert status is not None
        violation = cast(
            list[dict[str, object]],
            _proposal_validation(status)["violations"],
        )[0]

        assert status.status_kind is LifecycleStatusKind.INVALID
        assert violation_text in json.dumps(violation, sort_keys=True)
        assert len(decisions.records) == before_record_count
        assert decisions.queue.pending_requests == (placement_request,)


def test_valid_disembark_placement_proposal_updates_cargo_and_battlefield() -> None:
    state, passenger, transport = _battle_state_with_embarked_passenger()
    handler = MovementPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        parameterized_proposals=True,
    )
    decisions = DecisionController()
    disembark_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert disembark_request.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=passenger.unit_instance_id,
            result_id="phase11d-select-disembark",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)
    assert proposal.context is not None
    assert proposal.context["disembark_mode"] == DisembarkModeKind.TACTICAL_DISEMBARK.value

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        payload=_json(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=passenger.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=_disembark_placement(passenger),
                transport_unit_instance_id=transport.unit_instance_id,
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
        result_id="phase11d-place-disembark",
    )

    assert status is None
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(passenger.unit_instance_id)
    cargo = state.transport_cargo_state_for_transport(transport.unit_instance_id)
    assert cargo is not None
    assert cargo.embarked_unit_instance_ids == ()


def test_disembark_placement_wrong_mode_keeps_pending_request_clean() -> None:
    state, passenger, transport = _battle_state_with_embarked_passenger()
    handler = MovementPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        parameterized_proposals=True,
    )
    decisions = DecisionController()
    disembark_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=passenger.unit_instance_id,
            result_id="phase14h-select-disembark-mode-drift",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)
    before_record_count = len(decisions.records)

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        payload=_json(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=passenger.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=_disembark_placement(passenger),
                transport_unit_instance_id=transport.unit_instance_id,
                disembark_mode=DisembarkModeKind.RAPID_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
        result_id="phase14h-place-disembark-mode-drift",
    )
    assert status is not None
    violation = cast(
        list[dict[str, object]],
        _proposal_validation(status)["violations"],
    )[0]

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert violation["violation_code"] == "proposal_disembark_mode_drift"
    assert len(decisions.records) == before_record_count
    assert decisions.queue.pending_requests == (placement_request,)


def test_disembark_placement_missing_required_field_keeps_pending_request_clean() -> None:
    state, passenger, _transport = _battle_state_with_embarked_passenger()
    handler = MovementPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        parameterized_proposals=True,
    )
    decisions = DecisionController()
    disembark_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=disembark_request,
            option_id=passenger.unit_instance_id,
            result_id="phase11d-select-disembark-missing-field",
        )
    )
    proposal = MovementProposalRequest.from_decision_request_payload(placement_request.payload)
    before_record_count = len(decisions.records)

    status = _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        payload=_json(
            PlacementProposalPayload(
                proposal_request_id=proposal.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                unit_instance_id=passenger.unit_instance_id,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                attempted_placement=_disembark_placement(passenger),
                disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
                transport_movement_status=TransportMovementStatus.NOT_MOVED,
            ).to_payload()
        ),
        result_id="phase11d-place-disembark-missing-field",
    )
    assert status is not None
    violation = cast(
        list[dict[str, object]],
        _proposal_validation(status)["violations"],
    )[0]

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert violation["violation_code"] == "proposal_payload_missing_field"
    assert violation["field"] == "transport_unit_instance_id"
    assert len(decisions.records) == before_record_count
    assert decisions.queue.pending_requests == (placement_request,)


def test_projection_submission_helpers_and_event_cursor_are_viewer_scoped() -> None:
    session, action_request = _local_session_at_first_movement_action()
    view = session.view(viewer_player_id="player-b")
    direct_view = project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-b")
    event_delta = session.events_since(EventStreamCursor(), viewer_player_id="player-b")

    assert view == direct_view
    assert view["pending_decision"] is not None
    assert view["pending_decision"]["request_id"] == action_request.request_id
    assert view["pending_proposal"] is None
    assert view["public_secondary_mission_choices"][0] == {
        "player_id": "player-a",
        "selected": True,
        "mode": "fixed",
        "fixed_mission_ids": ["assassination", "bring_it_down"],
        "hidden": False,
    }
    assert event_delta["cursor"] == 0
    assert event_delta["viewer_player_id"] == "player-b"
    assert event_delta["next_cursor"] == len(
        session.lifecycle.decision_controller.event_log.records
    )
    assert event_delta["events"]
    assert "<" not in json.dumps(view, sort_keys=True)
    assert "object at 0x" not in json.dumps(view, sort_keys=True)


def test_projection_redacts_secret_pending_decisions_for_non_actor_viewers() -> None:
    session = LocalGameSession()
    session.start(_config())
    first_status = session.advance_until_decision_or_terminal()
    request = _decision_request(first_status)

    player_b_view = session.view(viewer_player_id="player-b")
    player_a_view = session.view(viewer_player_id="player-a")
    redacted_pending = player_b_view["pending_decision"]

    assert request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert redacted_pending == {
        "request_id": request.request_id,
        "decision_type": SECONDARY_MISSION_DECISION_TYPE,
        "actor_id": "player-a",
        "payload": {
            "secret": True,
            "hidden": True,
        },
        "options": [],
        "is_parameterized": False,
    }
    assert player_b_view["pending_proposal"] is None
    assert "assassination" not in json.dumps(player_b_view, sort_keys=True)
    assert "bring_it_down" not in json.dumps(player_b_view, sort_keys=True)
    assert player_a_view["pending_decision"] is not None
    assert "assassination" in json.dumps(player_a_view["pending_decision"], sort_keys=True)
    assert "bring_it_down" in json.dumps(player_a_view["pending_decision"], sort_keys=True)


def test_viewer_scoped_event_cursor_redacts_opponent_secret_decision_payloads() -> None:
    session = LocalGameSession()
    session.start(_config())
    first_status = session.advance_until_decision_or_terminal()
    assert _decision_request(first_status).actor_id == "player-a"

    session.submit_option(
        option_id="fixed:assassination:bring_it_down",
        result_id="phase11d-secret-secondary-a",
    )
    player_b_delta = session.events_since(EventStreamCursor(), viewer_player_id="player-b")
    player_a_delta = session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    player_a_events_for_player_b = [
        event
        for event in player_b_delta["events"]
        if "player-a" in json.dumps(event["payload"], sort_keys=True)
    ]
    player_a_events_for_player_b_blob = json.dumps(player_a_events_for_player_b, sort_keys=True)
    secondary_event_payloads_for_player_b: list[dict[str, object]] = []
    for event in player_b_delta["events"]:
        if event["event_type"] != "secondary_mission_choice_recorded":
            continue
        payload = cast(dict[str, object], event["payload"])
        if payload["player_id"] == "player-a":
            secondary_event_payloads_for_player_b.append(payload)
    player_a_blob = json.dumps(player_a_delta, sort_keys=True)

    assert secondary_event_payloads_for_player_b == [
        {
            "game_id": "phase11d-game",
            "player_id": "player-a",
            "setup_step": "select_secondary_missions",
            "selected": True,
            "hidden": True,
        }
    ]
    assert "fixed_mission_ids" not in player_a_events_for_player_b_blob
    assert "fixed_choice_count" not in player_a_events_for_player_b_blob
    assert "mode" not in player_a_events_for_player_b_blob
    assert "fixed" not in player_a_events_for_player_b_blob.lower()
    assert "assassination" not in player_a_events_for_player_b_blob
    assert "bring_it_down" not in player_a_events_for_player_b_blob
    assert "fixed_mission_ids" in player_a_blob
    assert "fixed_choice_count" in player_a_blob
    assert "assassination" in player_a_blob
    assert "bring_it_down" in player_a_blob


def test_adapter_submission_contracts_are_fail_fast() -> None:
    session, action_request = _local_session_at_first_movement_action()
    parameterized_request = _decision_request(
        session.submit_option(
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-contract-normal-action",
        )
    )

    finite_result = result_for_option(
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase11d-contract-finite",
    )
    payload_result = result_for_payload(
        request=parameterized_request,
        payload={"accepted": True},
        result_id="phase11d-contract-parameterized",
    )

    assert finite_result.selected_option_id == MovementPhaseActionKind.NORMAL_MOVE.value
    assert payload_result.selected_option_id == "submit_parameterized_payload"

    with pytest.raises(GameLifecycleError, match="requires a DecisionRequest"):
        FiniteOptionSubmission(
            request_id=action_request.request_id,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-contract-bad-request-type",
        ).to_result(cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="cannot answer a parameterized request"):
        FiniteOptionSubmission(
            request_id=parameterized_request.request_id,
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-contract-finite-parameterized",
        ).to_result(parameterized_request)
    with pytest.raises(GameLifecycleError, match="request_id drift"):
        FiniteOptionSubmission(
            request_id="phase11d-other-request",
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-contract-finite-drift",
        ).to_result(action_request)
    with pytest.raises(GameLifecycleError, match="requires a DecisionRequest"):
        ParameterizedSubmission(
            request_id=parameterized_request.request_id,
            payload={"accepted": True},
            result_id="phase11d-contract-bad-parameterized-request-type",
        ).to_result(cast(DecisionRequest, object()))
    with pytest.raises(GameLifecycleError, match="requires a parameterized request"):
        ParameterizedSubmission(
            request_id=action_request.request_id,
            payload={"accepted": True},
            result_id="phase11d-contract-parameterized-finite",
        ).to_result(action_request)
    with pytest.raises(GameLifecycleError, match="request_id drift"):
        ParameterizedSubmission(
            request_id="phase11d-other-parameterized-request",
            payload={"accepted": True},
            result_id="phase11d-contract-parameterized-drift",
        ).to_result(parameterized_request)
    with pytest.raises(GameLifecycleError, match="must be a string"):
        FiniteOptionSubmission(
            request_id=cast(str, object()),
            selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-contract-non-string",
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        FiniteOptionSubmission(
            request_id="phase11d-contract-empty",
            selected_option_id=" ",
            result_id="phase11d-contract-empty-option",
        )


def test_adapter_helpers_and_cursor_reject_invalid_inputs() -> None:
    with pytest.raises(GameLifecycleError, match="requires a GameLifecycle"):
        submit_option(
            lifecycle=cast(GameLifecycle, object()),
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-helper-bad-lifecycle",
        )
    with pytest.raises(GameLifecycleError, match="pending DecisionRequest"):
        submit_option(
            lifecycle=GameLifecycle(),
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
            result_id="phase11d-helper-no-request",
        )

    with pytest.raises(GameLifecycleError, match="must be an integer"):
        EventStreamCursor(value=cast(int, "0"))
    with pytest.raises(GameLifecycleError, match="must not be negative"):
        EventStreamCursor(value=-1)
    event_log = EventLog()
    event_log.append("phase11d_cursor_event", {"accepted": True})
    with pytest.raises(GameLifecycleError, match="requires an EventLog"):
        EventStreamCursor().events_since(
            cast(EventLog, object()),
            viewer_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="viewer_player_id must be a string"):
        EventStreamCursor().events_since(event_log, viewer_player_id=cast(str, object()))
    with pytest.raises(GameLifecycleError, match="ahead of the event log"):
        EventStreamCursor(value=2).events_since(event_log, viewer_player_id="player-a")
    assert EventStreamCursor(value=1).events_since(event_log, viewer_player_id="player-a") == {
        "viewer_player_id": "player-a",
        "cursor": 1,
        "next_cursor": 1,
        "events": [],
    }


def test_projection_and_local_session_boundaries_are_fail_fast() -> None:
    with pytest.raises(GameLifecycleError, match="requires a GameLifecycle"):
        project_game_view(
            lifecycle=cast(GameLifecycle, object()),
            viewer_player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="started lifecycle"):
        project_game_view(lifecycle=GameLifecycle(), viewer_player_id="player-a")
    with pytest.raises(GameLifecycleError, match="config must be a GameConfig"):
        LocalGameSession().start(cast(GameConfig, object()))
    with pytest.raises(GameLifecycleError, match="requires EventStreamCursor"):
        LocalGameSession().events_since(
            cast(EventStreamCursor, object()),
            viewer_player_id="player-a",
        )

    session, _movement_status = _local_session_at_movement_unit_selection()
    with pytest.raises(GameLifecycleError, match="viewer_player_id must be a string"):
        project_game_view(
            lifecycle=session.lifecycle,
            viewer_player_id=cast(str, object()),
        )
    with pytest.raises(GameLifecycleError, match="must not be empty"):
        project_game_view(lifecycle=session.lifecycle, viewer_player_id=" ")
    with pytest.raises(GameLifecycleError, match="must be a player"):
        project_game_view(lifecycle=session.lifecycle, viewer_player_id="player-c")
    with pytest.raises(GameLifecycleError, match="viewer_player_id must be a player"):
        session.events_since(EventStreamCursor(), viewer_player_id="player-c")

    empty_lifecycle = GameLifecycle(
        state=_session_state(session),
        parameterized_movement_proposals=session.lifecycle.parameterized_movement_proposals,
    )
    empty_view = project_game_view(lifecycle=empty_lifecycle, viewer_player_id="player-a")
    assert empty_view["pending_decision"] is None
    assert empty_view["pending_proposal"] is None

    empty_lifecycle.decision_controller.request_decision(
        DecisionRequest(
            request_id="phase11d-malformed-parameterized-request",
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id="player-a",
            payload=[],
            options=(parameterized_decision_option(),),
        )
    )
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        project_game_view(lifecycle=empty_lifecycle, viewer_player_id="player-a")

    mismatched_lifecycle = GameLifecycle(
        state=_session_state(session),
        parameterized_movement_proposals=session.lifecycle.parameterized_movement_proposals,
    )
    mismatched_lifecycle.decision_controller.request_decision(
        DecisionRequest(
            request_id="phase11d-mismatched-parameterized-request",
            decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
            actor_id="player-a",
            payload={
                "proposal_request": {
                    "request_id": "phase11d-other-parameterized-request",
                    "proposal_kind": ProposalKind.NORMAL_MOVE.value,
                }
            },
            options=(parameterized_decision_option(),),
        )
    )
    with pytest.raises(GameLifecycleError, match="metadata must match DecisionRequest"):
        project_game_view(lifecycle=mismatched_lifecycle, viewer_player_id="player-a")


def _local_session_at_first_movement_action() -> tuple[LocalGameSession, DecisionRequest]:
    session, movement_status = _local_session_at_movement_unit_selection()
    action_status = session.submit_option(
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase11d-select-first-unit",
    )
    action_request = _decision_request(action_status)
    assert movement_status.decision_request is not None
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return session, action_request


def _local_session_at_movement_unit_selection(
    *, game_id: str = "phase11d-game"
) -> tuple[LocalGameSession, LifecycleStatus]:
    session = LocalGameSession()
    session.start(_config(game_id=game_id))
    first_status = session.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = session.submit_option(
        option_id="fixed:assassination:bring_it_down",
        result_id="phase11d-secondary-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = session.submit_option(
        option_id="fixed:assassination:bring_it_down",
        result_id="phase11d-secondary-b",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return session, movement_status


def _submit_handler_decision(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(state=state, result=result, decisions=decisions)


def _submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id="submit_parameterized_payload",
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, result=result, decisions=decisions)


def _json(value: object) -> JsonValue:
    return validate_json_value(value)


def _proposal_validation(status: LifecycleStatus) -> dict[str, object]:
    payload = cast(dict[str, object], status.payload)
    return cast(dict[str, object], payload["proposal_validation"])


def _golden_json(file_name: str) -> JsonValue:
    fixture_path = Path(__file__).parents[1] / "fixtures" / file_name
    return validate_json_value(json.loads(fixture_path.read_text(encoding="utf-8")))


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _session_state(session: LocalGameSession) -> GameState:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    return state


def _unit_placement(state: GameState, unit_instance_id: str) -> UnitPlacement:
    assert state.battlefield_state is not None
    return state.battlefield_state.unit_placement_by_id(unit_instance_id)


def _shift_witness(
    unit_placement: UnitPlacement,
    *,
    dx: float,
    dy: float = 0.0,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _config(*, game_id: str = "phase11d-game") -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id=game_id,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase11d-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2025_26_mission_pack(),
            mission_pool_entry_id="mission-a",
            terrain_layout_id="layout-1",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mark_first_unit_battle_shocked(state: GameState) -> None:
    state.battle_shocked_unit_ids = ["army-alpha:intercessor-unit-1"]


def _move_first_enemy_model_into_overflight_engagement(state: GameState) -> None:
    assert state.battlefield_state is not None
    friendly = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-3")
    first_friendly_pose = friendly.model_placements[0].pose
    target_pose = Pose.at(
        first_friendly_pose.position.x,
        first_friendly_pose.position.y + 2.0,
        first_friendly_pose.position.z,
        facing_degrees=180.0,
    )
    first_enemy = enemy.model_placements[0]
    delta_x = target_pose.position.x - first_enemy.pose.position.x
    delta_y = target_pose.position.y - first_enemy.pose.position.y
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        enemy.with_model_placements(
            tuple(
                placement.with_pose(
                    Pose.at(
                        placement.pose.position.x + delta_x,
                        placement.pose.position.y + delta_y,
                        placement.pose.position.z,
                        facing_degrees=180.0,
                    )
                )
                for placement in enemy.model_placements
            )
        )
    )


def _battle_state_with_reserve() -> tuple[GameState, ReserveState, UnitInstance]:
    config = _config()
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11d-reserve-battlefield",
        armies=armies,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    state.record_battlefield_state(
        scenario.battlefield_state.without_unit_placement(reserve_unit.unit_instance_id)
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 3
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=3,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-2",),
        moved_unit_ids=("army-alpha:intercessor-unit-2",),
    )
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
    )
    state.record_reserve_state(reserve_state)
    return state, reserve_state, reserve_unit


def _enter_reinforcements_choice(
    *,
    state: GameState,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    handler = MovementPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase11d-test"
        ),
        parameterized_proposals=True,
    )
    decisions = DecisionController()
    status = handler.begin_phase(state=state, decisions=decisions)
    request = _decision_request(status)
    assert request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.step is MovementPhaseStepKind.MOVE_UNITS
    return handler, decisions, request


def _reserve_placement(
    *,
    reserve_unit: UnitInstance,
    y: float = 1.0,
) -> UnitPlacement:
    poses = tuple(Pose.at(12.0 + index * 2.0, y) for index in range(len(reserve_unit.own_models)))
    return _unit_placement_at(
        reserve_unit,
        army_id="army-alpha",
        player_id="player-a",
        poses=poses,
    )


def _battle_state_with_embarked_passenger() -> tuple[GameState, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    armies = (
        muster_army(
            catalog=catalog,
            request=_transport_army_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("enemy-unit",),
            ),
        ),
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11d-disembark-battlefield",
        armies=armies,
    )
    passenger = armies[0].unit_by_id("army-alpha:passenger-unit")
    transport = armies[0].unit_by_id("army-alpha:transport-1")
    battlefield = scenario.battlefield_state.without_unit_placement(passenger.unit_instance_id)
    ruleset = RulesetDescriptor.warhammer_40000_eleventh()
    state = GameState(
        game_id="phase11d-disembark-game",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(armies),
        battlefield_state=battlefield,
        movement_phase_state=MovementPhaseState(
            battle_round=1,
            active_player_id="player-a",
        ),
    )
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=transport.unit_instance_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger.unit_instance_id,),
            phase_battle_round=1,
            started_phase_embarked_unit_instance_ids=(passenger.unit_instance_id,),
        )
    )
    return state, passenger, transport


def _transport_army_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id="passenger-unit",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
            UnitMusterSelection(
                unit_selection_id="transport-1",
                datasheet_id="core-transport",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-transport",
                        model_count=1,
                    ),
                ),
            ),
        ),
    )


def _disembark_placement(unit: UnitInstance) -> UnitPlacement:
    return _unit_placement_at(
        unit,
        army_id="army-alpha",
        player_id="player-a",
        poses=(
            Pose.at(9.1, 12.5),
            Pose.at(10.0, 13.8),
            Pose.at(10.0, 15.2),
            Pose.at(9.1, 16.5),
            Pose.at(8.8, 14.5),
        ),
    )


def _unit_placement_at(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    poses: tuple[Pose, ...],
) -> UnitPlacement:
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id=army_id,
                player_id=player_id,
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, object]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
