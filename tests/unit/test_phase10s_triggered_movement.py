from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.aircraft import HoverModeState
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    SurgeMoveState,
    SurgeMoveStatePayload,
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
    TriggeredMovementRequest,
    TriggeredMovementResolution,
    TriggeredMovementViolation,
    TriggeredMovementViolationCode,
    apply_triggered_movement_to_battlefield,
    resolve_triggered_movement,
    triggered_movement_kind_from_token,
    triggered_movement_violation_code_from_token,
)
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    UnitCoherencyResult,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import (
    PathValidationResult,
    PathWitness,
    TerrainPathLegalityResult,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_blood_surge_like_movement_is_triggered_decision_with_model_choices() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()

    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(
            _shift_witness(unit_placement, dx=2.0),
            _shift_witness(unit_placement, dx=3.0),
        ),
    )

    assert request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    assert request.actor_id == "player-a"
    assert {option.option_id for option in request.options} == {
        DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        "surge_move_001",
        "surge_move_002",
    }
    first_option_payload = _option_payload(request, "surge_move_001")
    model_movements = cast(list[dict[str, JsonValue]], first_option_payload["model_movements"])
    assert first_option_payload["movement_phase_action"] is None
    assert first_option_payload["triggered_movement_kind"] == TriggeredMovementKind.SURGE.value
    assert len(model_movements) == len(unit_placement.model_placements)
    assert {cast(str, movement["model_instance_id"]) for movement in model_movements} == {
        placement.model_instance_id for placement in unit_placement.model_placements
    }

    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-000001",
        request=request,
        selected_option_id="surge_move_002",
    )
    decisions.submit_result(result)
    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is None
    moved_placement = _unit_placement(state)
    for before, after in zip(
        unit_placement.model_placements,
        moved_placement.model_placements,
        strict=True,
    ):
        assert after.pose.position.x == before.pose.position.x + 3.0
    assert len(state.surge_move_states) == 1
    assert state.surge_move_states[0].source_rule_id == "blood_surge"
    resolved_payload = _last_event_payload(decisions, "triggered_movement_resolved")
    transition_batch = cast(dict[str, JsonValue], resolved_payload["transition_batch"])
    displacements = cast(list[dict[str, JsonValue]], transition_batch["displacements"])
    assert resolved_payload["source_rule_id"] == "blood_surge"
    trigger_timing = cast(dict[str, JsonValue], resolved_payload["trigger_timing"])
    assert trigger_timing["phase"] == "movement"
    assert len(displacements) == len(unit_placement.model_placements)
    assert {cast(str, record["displacement_kind"]) for record in displacements} == {"surge_move"}
    assert {cast(str, record["source_rule_id"]) for record in displacements} == {"blood_surge"}


def test_optional_triggered_movement_can_be_declined_without_mutation() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )

    assert DECLINE_TRIGGERED_MOVEMENT_OPTION_ID in {option.option_id for option in request.options}

    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-decline-001",
        request=request,
        selected_option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    )
    decisions.submit_result(result)
    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is None
    assert _unit_placement(state).to_payload() == unit_placement.to_payload()
    assert state.surge_move_states == []
    declined_payload = _last_event_payload(decisions, "triggered_movement_declined")
    assert declined_payload["phase_body_status"] == "triggered_movement_declined"
    assert declined_payload["declined"] is True
    assert declined_payload["movement_phase_action"] is None
    assert declined_payload["unit_instance_id"] == unit_placement.unit_instance_id


def test_mandatory_triggered_movement_omits_decline_choice() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0, optional=False)

    request = TriggeredMovementHandler(ruleset_descriptor=_ruleset()).request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )

    assert DECLINE_TRIGGERED_MOVEMENT_OPTION_ID not in {
        option.option_id for option in request.options
    }
    assert {option.option_id for option in request.options} == {"surge_move_001"}


def test_declined_triggered_movement_event_payload_is_replay_safe() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _reactive_step_descriptor(max_distance_inches=2.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=2.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-decline-payload-001",
        request=request,
        selected_option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    )
    decisions.submit_result(result)

    handler.apply_decision(state=state, result=result, decisions=decisions)

    declined_payload = _last_event_payload(decisions, "triggered_movement_declined")
    blob = json.dumps(declined_payload, sort_keys=True)
    assert "<" not in blob
    assert "object at 0x" not in blob
    assert declined_payload["triggered_movement_kind"] == TriggeredMovementKind.TRIGGERED.value
    assert declined_payload["source_rule_id"] == "reactive_step"
    assert declined_payload["request_id"] == request.request_id
    assert declined_payload["result_id"] == result.result_id
    assert declined_payload["descriptor"] == descriptor.to_payload()


def test_triggered_movement_request_rejects_reaction_window_phase_mismatch() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)

    with pytest.raises(
        GameLifecycleError,
        match="Triggered movement trigger phase must match current battle phase",
    ):
        TriggeredMovementHandler(ruleset_descriptor=_ruleset()).request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=_blood_surge_descriptor(max_distance_inches=3.0),
            candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
        )


def test_triggered_movement_apply_rejects_reaction_window_phase_drift() -> None:
    state = _battle_ready_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    unit_placement = _unit_placement(state)
    descriptor = _blood_surge_descriptor(max_distance_inches=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-phase-drift-001",
        request=request,
        selected_option_id="surge_move_001",
    )
    decisions.submit_result(result)
    _set_current_battle_phase(state, BattlePhase.MOVEMENT)

    with pytest.raises(
        GameLifecycleError,
        match="Triggered movement trigger phase must match current battle phase",
    ):
        handler.apply_decision(state=state, result=result, decisions=decisions)


def test_shooting_reaction_window_resolves_with_matching_event_and_transition_phase() -> None:
    state = _battle_ready_state()
    _set_current_battle_phase(state, BattlePhase.SHOOTING)
    unit_placement = _unit_placement(state)
    descriptor = _blood_surge_descriptor(max_distance_inches=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-shooting-001",
        request=request,
        selected_option_id="surge_move_001",
    )
    decisions.submit_result(result)

    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is None
    resolved_payload = _last_event_payload(decisions, "triggered_movement_resolved")
    transition_batch = cast(dict[str, JsonValue], resolved_payload["transition_batch"])
    displacements = cast(list[dict[str, JsonValue]], transition_batch["displacements"])
    assert resolved_payload["phase"] == BattlePhase.SHOOTING.value
    assert {cast(str, record["source_phase"]) for record in displacements} == {
        BattlePhase.SHOOTING.value
    }


def test_triggered_payloads_round_trip_without_object_reprs() -> None:
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state = SurgeMoveState.from_resolution(
        player_id="player-a",
        battle_round=1,
        unit_instance_id="army-alpha:intercessor-unit-1",
        descriptor=descriptor,
        request_id="decision-request-000100",
        result_id="phase10s-result-000100",
    )

    descriptor_payload = descriptor.to_payload()
    state_payload = state.to_payload()
    descriptor_blob = json.dumps(descriptor_payload, sort_keys=True)
    state_blob = json.dumps(state_payload, sort_keys=True)

    assert "<" not in descriptor_blob
    assert "object at 0x" not in descriptor_blob
    assert "<" not in state_blob
    assert "object at 0x" not in state_blob
    assert TriggeredMovementDescriptor.from_payload(descriptor_payload) == descriptor
    assert SurgeMoveState.from_payload(state_payload) == state
    assert ReactionWindow.from_payload(descriptor.trigger_timing.to_payload()) == (
        descriptor.trigger_timing
    )


def test_triggered_resolution_payloads_include_model_destinations_without_reprs() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=_movement_surge_descriptor(max_distance_inches=3.0),
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
    )

    payload = resolution.to_payload()
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert payload["rollback_record"] is None
    movement_payload = payload["movement_payload"]
    assert movement_payload["movement_phase_action"] is None
    model_movements = cast(list[dict[str, JsonValue]], movement_payload["model_movements"])
    assert len(model_movements) == len(unit_placement.model_placements)
    assert {cast(str, movement["model_instance_id"]) for movement in model_movements} == {
        placement.model_instance_id for placement in unit_placement.model_placements
    }
    assert all("end_pose" in movement for movement in model_movements)


def test_triggered_violation_payload_round_trips_without_object_reprs() -> None:
    violation = TriggeredMovementViolation(
        violation_code=TriggeredMovementViolationCode.ENGAGEMENT_RANGE_SURGE_FORBIDDEN,
        message="Units within Engagement Range cannot make surge moves.",
    )

    payload = violation.to_payload()
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert TriggeredMovementViolation.from_payload(payload) == violation
    assert triggered_movement_kind_from_token(TriggeredMovementKind.SURGE) is (
        TriggeredMovementKind.SURGE
    )
    assert (
        triggered_movement_violation_code_from_token(
            TriggeredMovementViolationCode.ENGAGEMENT_RANGE_SURGE_FORBIDDEN
        )
        is TriggeredMovementViolationCode.ENGAGEMENT_RANGE_SURGE_FORBIDDEN
    )

    with pytest.raises(GameLifecycleError, match="TriggeredMovementKind token must be a string"):
        triggered_movement_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported TriggeredMovementKind token"):
        triggered_movement_kind_from_token("unsupported")
    with pytest.raises(
        GameLifecycleError,
        match="TriggeredMovementViolationCode token must be a string",
    ):
        triggered_movement_violation_code_from_token(1)
    with pytest.raises(
        GameLifecycleError,
        match="Unsupported TriggeredMovementViolationCode token",
    ):
        triggered_movement_violation_code_from_token("unsupported")


def test_non_surge_triggered_movement_records_triggered_displacement_without_surge_state() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _reactive_step_descriptor(max_distance_inches=2.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=2.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-triggered-001",
        request=request,
        selected_option_id="triggered_move_001",
    )
    decisions.submit_result(result)

    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is None
    assert state.surge_move_states == []
    resolved_payload = _last_event_payload(decisions, "triggered_movement_resolved")
    transition_batch = cast(dict[str, JsonValue], resolved_payload["transition_batch"])
    displacements = cast(list[dict[str, JsonValue]], transition_batch["displacements"])
    assert {cast(str, record["displacement_kind"]) for record in displacements} == {
        "triggered_move"
    }


def test_apply_triggered_movement_to_battlefield_uses_valid_resolution() -> None:
    state = _battle_ready_state()
    assert state.battlefield_state is not None
    unit_placement = _unit_placement(state)
    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=_movement_surge_descriptor(max_distance_inches=3.0),
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
    )

    updated = apply_triggered_movement_to_battlefield(
        battlefield_state=state.battlefield_state,
        resolution=resolution,
    )

    moved = updated.unit_placement_by_id(unit_placement.unit_instance_id)
    assert moved.model_placements[0].pose.position.x == (
        unit_placement.model_placements[0].pose.position.x + 3.0
    )


def test_triggered_movement_apply_invalidates_if_state_changes_after_request() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-drift-001",
        request=request,
        selected_option_id="surge_move_001",
    )
    decisions.submit_result(result)
    _move_first_friendly_model(state, dx=1.0)

    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = _last_event_payload(decisions, "triggered_movement_invalid")
    assert invalid_payload["violation_code"] == "triggered_movement_model_movement_witness_drift"


def test_triggered_movement_apply_invalidates_if_restrictions_change_after_request() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-invalidated-001",
        request=request,
        selected_option_id="surge_move_001",
    )
    decisions.submit_result(result)
    state.battle_shocked_unit_ids.append(unit_placement.unit_instance_id)

    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = _last_event_payload(decisions, "triggered_movement_invalid")
    assert invalid_payload["violation_code"] == "battle_shocked_surge_forbidden"
    assert _unit_placement(state).model_placements[0].pose == (
        unit_placement.model_placements[0].pose
    )


def test_invalid_triggered_resolution_cannot_mutate_or_emit_transitions() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state.battle_shocked_unit_ids.append(unit_placement.unit_instance_id)
    assert state.battlefield_state is not None
    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )

    assert not resolution.is_valid
    with pytest.raises(
        GameLifecycleError,
        match="Invalid triggered movement cannot emit displacement records",
    ):
        resolution.transition_batch(before=unit_placement)
    with pytest.raises(
        GameLifecycleError,
        match="Invalid triggered movement cannot mutate battlefield_state",
    ):
        apply_triggered_movement_to_battlefield(
            battlefield_state=state.battlefield_state,
            resolution=resolution,
        )


def test_lifecycle_submit_decision_routes_triggered_movement_choice() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(_config())
    state = lifecycle.state
    assert state is not None
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    request = TriggeredMovementHandler(ruleset_descriptor=_ruleset()).request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
    )
    lifecycle.decision_controller = DecisionController()
    lifecycle.decision_controller.request_decision(request)

    status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase10s-result-lifecycle-route-001",
            request=request,
            selected_option_id="surge_move_001",
        )
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert len(state.surge_move_states) == 1
    assert _unit_placement(state).model_placements[0].pose.position.x == (
        unit_placement.model_placements[0].pose.position.x + 3.0
    )


def test_triggered_movement_request_rejects_invalid_candidate() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state.battle_shocked_unit_ids.append(unit_placement.unit_instance_id)

    with pytest.raises(GameLifecycleError, match="battle_shocked_surge_forbidden"):
        TriggeredMovementHandler(ruleset_descriptor=_ruleset()).request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            candidate_witnesses=(_shift_witness(unit_placement, dx=3.0),),
        )


def test_triggered_movement_handler_rejects_malformed_requests_and_results() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    witness = _shift_witness(unit_placement, dx=3.0)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())

    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        TriggeredMovementHandler().request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            candidate_witnesses=(witness,),
        )
    with pytest.raises(GameLifecycleError, match="requires a descriptor"):
        handler.request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=cast(TriggeredMovementDescriptor, "not-a-descriptor"),
            candidate_witnesses=(witness,),
        )
    with pytest.raises(GameLifecycleError, match="candidate_witnesses must be a tuple"):
        handler.request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            candidate_witnesses=cast(tuple[PathWitness, ...], [witness]),
        )
    with pytest.raises(GameLifecycleError, match="candidate_witnesses must contain PathWitness"):
        handler.request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            candidate_witnesses=cast(tuple[PathWitness, ...], ("not-a-witness",)),
        )
    with pytest.raises(GameLifecycleError, match="at least one movement choice"):
        handler.request_from_state(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            candidate_witnesses=(),
        )

    unsupported_result = DecisionResult(
        result_id="phase10s-result-unsupported-type",
        request_id="decision-request-unsupported-type",
        decision_type="select_other_decision",
        actor_id=unit_placement.player_id,
        selected_option_id="other-option",
        payload={},
    )
    with pytest.raises(GameLifecycleError, match="unsupported decision_type"):
        handler.apply_decision(
            state=state,
            result=unsupported_result,
            decisions=DecisionController(),
        )

    missing_request_result = DecisionResult(
        result_id="phase10s-result-missing-request",
        request_id="decision-request-missing",
        decision_type=SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
        actor_id=unit_placement.player_id,
        selected_option_id="surge_move_001",
        payload={},
    )
    with pytest.raises(GameLifecycleError, match="known triggered movement request"):
        handler.apply_decision(
            state=state,
            result=missing_request_result,
            decisions=DecisionController(),
        )

    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=descriptor,
        candidate_witnesses=(witness,),
    )
    decisions = DecisionController()
    decisions.request_decision(request)
    selected_payload = cast(dict[str, JsonValue], request.option_by_id("surge_move_001").payload)

    unit_drift_payload = dict(selected_payload)
    unit_drift_payload["unit_instance_id"] = "army-alpha:unknown-unit"
    with pytest.raises(GameLifecycleError, match="result unit drift"):
        handler.apply_decision(
            state=state,
            result=DecisionResult(
                result_id="phase10s-result-unit-drift",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id="surge_move_001",
                payload=unit_drift_payload,
            ),
            decisions=decisions,
        )

    with pytest.raises(GameLifecycleError, match="actor must own"):
        handler.apply_decision(
            state=state,
            result=DecisionResult(
                result_id="phase10s-result-actor-drift",
                request_id=request.request_id,
                decision_type=request.decision_type,
                actor_id="player-b",
                selected_option_id="surge_move_001",
                payload=selected_payload,
            ),
            decisions=decisions,
        )

    descriptor_drift_payload = dict(selected_payload)
    descriptor_payload = dict(cast(dict[str, JsonValue], descriptor_drift_payload["descriptor"]))
    descriptor_payload["source_rule_id"] = "other_rule"
    descriptor_drift_payload["descriptor"] = descriptor_payload
    descriptor_status = handler.apply_decision(
        state=state,
        result=DecisionResult(
            result_id="phase10s-result-descriptor-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="surge_move_001",
            payload=descriptor_drift_payload,
        ),
        decisions=decisions,
    )
    assert descriptor_status is not None
    assert descriptor_status.status_kind is LifecycleStatusKind.INVALID
    assert _last_event_payload(decisions, "triggered_movement_invalid")["violation_code"] == (
        "triggered_movement_descriptor_drift"
    )

    witness_drift_payload = dict(selected_payload)
    witness_payload = dict(cast(dict[str, JsonValue], witness_drift_payload["witness"]))
    model_paths = cast(list[dict[str, JsonValue]], witness_payload["model_paths"])
    witness_payload["model_paths"] = list(reversed(model_paths))
    witness_drift_payload["witness"] = witness_payload
    witness_status = handler.apply_decision(
        state=state,
        result=DecisionResult(
            result_id="phase10s-result-witness-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id="surge_move_001",
            payload=witness_drift_payload,
        ),
        decisions=decisions,
    )
    assert witness_status is not None
    assert witness_status.status_kind is LifecycleStatusKind.INVALID
    assert _last_event_payload(decisions, "triggered_movement_invalid")["violation_code"] == (
        "triggered_movement_witness_drift"
    )


def test_surge_movement_cannot_occur_if_battle_shocked() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state.battle_shocked_unit_ids.append(unit_placement.unit_instance_id)

    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
    )

    assert not resolution.is_valid
    assert resolution.restriction_violations[0].violation_code is (
        TriggeredMovementViolationCode.BATTLE_SHOCKED_SURGE_FORBIDDEN
    )


def test_surge_movement_cannot_occur_while_within_engagement_range() -> None:
    state = _battle_ready_state()
    _move_first_enemy_model_into_engagement(state)
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)

    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
    )

    assert not resolution.is_valid
    assert resolution.restriction_violations[0].violation_code is (
        TriggeredMovementViolationCode.ENGAGEMENT_RANGE_SURGE_FORBIDDEN
    )


def test_one_surge_move_per_phase_is_enforced() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state.record_surge_move_state(
        SurgeMoveState.from_resolution(
            player_id=unit_placement.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            request_id="decision-request-existing",
            result_id="phase10s-result-existing",
        )
    )

    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
        surge_move_states=tuple(state.surge_move_states),
    )

    assert not resolution.is_valid
    assert resolution.restriction_violations[0].violation_code is (
        TriggeredMovementViolationCode.SURGE_MOVE_ALREADY_USED_THIS_PHASE
    )


def test_record_surge_move_state_rejects_duplicate_same_phase_unit_state() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state.record_surge_move_state(
        SurgeMoveState.from_resolution(
            player_id=unit_placement.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            request_id="decision-request-existing",
            result_id="phase10s-result-existing",
        )
    )

    with pytest.raises(GameLifecycleError, match="already exists for unit in this phase"):
        state.record_surge_move_state(
            SurgeMoveState.from_resolution(
                player_id=unit_placement.player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                descriptor=descriptor,
                request_id="decision-request-duplicate-phase",
                result_id="phase10s-result-duplicate-phase",
            )
        )


def test_lifecycle_payload_rejects_duplicate_same_phase_surge_states() -> None:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(_config())
    state = lifecycle.state
    assert state is not None
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    state.record_surge_move_state(
        SurgeMoveState.from_resolution(
            player_id=unit_placement.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            request_id="decision-request-existing",
            result_id="phase10s-result-existing",
        )
    )
    payload = lifecycle.to_payload()
    duplicate_payload = dict(payload["state"]["surge_move_states"][0])
    duplicate_payload["request_id"] = "decision-request-duplicate-phase"
    duplicate_payload["result_id"] = "phase10s-result-duplicate-phase"
    payload["state"]["surge_move_states"].append(cast(SurgeMoveStatePayload, duplicate_payload))

    with pytest.raises(GameLifecycleError, match="unique by unit phase"):
        GameLifecycle.from_payload(payload)


def test_surge_move_state_allows_same_unit_in_different_phases_or_rounds() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    movement_descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    shooting_descriptor = _blood_surge_descriptor(max_distance_inches=3.0)

    state.record_surge_move_state(
        SurgeMoveState.from_resolution(
            player_id=unit_placement.player_id,
            battle_round=1,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=movement_descriptor,
            request_id="decision-request-movement-round-one",
            result_id="phase10s-result-movement-round-one",
        )
    )
    state.record_surge_move_state(
        SurgeMoveState.from_resolution(
            player_id=unit_placement.player_id,
            battle_round=1,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=shooting_descriptor,
            request_id="decision-request-shooting-round-one",
            result_id="phase10s-result-shooting-round-one",
        )
    )
    state.record_surge_move_state(
        SurgeMoveState.from_resolution(
            player_id=unit_placement.player_id,
            battle_round=2,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=movement_descriptor,
            request_id="decision-request-movement-round-two",
            result_id="phase10s-result-movement-round-two",
        )
    )

    assert len(state.surge_move_states) == 3


def test_triggered_movement_does_not_appear_in_select_movement_action() -> None:
    _lifecycle, action_request = _advance_to_movement_action_request(_config())

    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE not in {
        option.option_id for option in action_request.options
    }
    assert TriggeredMovementKind.SURGE.value not in {
        option.option_id for option in action_request.options
    }
    assert {
        cast(str, cast(dict[str, JsonValue], option.payload)["movement_phase_action"])
        for option in action_request.options
    } <= {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
        MovementPhaseActionKind.FALL_BACK.value,
    }


def test_triggered_movement_can_transit_enemy_aircraft_but_not_end_in_engagement() -> None:
    state, mover, enemy_aircraft = _aircraft_transit_battle_state()
    scenario = _scenario_from_state(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(mover.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    aircraft_placement = scenario.battlefield_state.unit_placement_by_id(
        enemy_aircraft.unit_instance_id
    ).model_placements[0]
    descriptor = _reactive_step_descriptor(max_distance_inches=12.0)
    transit_witness = PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(12.0, model_placement.pose.position.y),
            ),
        )
    )
    endpoint_witness = PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(
                    aircraft_placement.pose.position.x,
                    model_placement.pose.position.y,
                ),
            ),
        )
    )

    transit_result = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=transit_witness,
        battle_round=state.battle_round,
        hover_mode_states=tuple(state.hover_mode_states),
    )
    endpoint_result = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=endpoint_witness,
        battle_round=state.battle_round,
        hover_mode_states=tuple(state.hover_mode_states),
    )

    assert transit_result.is_valid
    assert not endpoint_result.is_valid
    assert endpoint_result.path_validation_results[0].violations[0].violation_code == (
        "enemy_engagement_range_end_forbidden"
    )


def test_triggered_movement_uses_hover_effective_keywords_for_moving_aircraft() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))
    scenario = _scenario_from_state(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)

    request = TriggeredMovementHandler(ruleset_descriptor=_ruleset()).request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=_reactive_step_descriptor(max_distance_inches=10.0),
        candidate_witnesses=(_shift_witness(unit_placement, dx=6.0),),
    )

    option_payload = _option_payload(request, "triggered_move_001")
    aircraft_policy = cast(dict[str, JsonValue], option_payload["aircraft_movement_policy"])
    effective_keywords = cast(list[str], aircraft_policy["effective_keywords"])
    assert aircraft_policy["hover_mode_active"] is True
    assert aircraft_policy["uses_aircraft_rules"] is False
    assert "AIRCRAFT" not in effective_keywords


def test_triggered_movement_rejects_stale_hover_aircraft_policy_payload() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    scenario = _scenario_from_state(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    request = handler.request_from_state(
        state=state,
        unit_instance_id=unit_placement.unit_instance_id,
        descriptor=_reactive_step_descriptor(max_distance_inches=10.0),
        candidate_witnesses=(_shift_witness(unit_placement, dx=6.0),),
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="phase10s-result-stale-hover-policy-001",
        request=request,
        selected_option_id="triggered_move_001",
    )
    decisions.submit_result(result)
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))

    status = handler.apply_decision(state=state, result=result, decisions=decisions)

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    invalid_payload = _last_event_payload(decisions, "triggered_movement_invalid")
    assert invalid_payload["violation_code"] == "triggered_movement_aircraft_policy_drift"


def test_triggered_movement_validators_fail_fast_for_bad_domain_objects() -> None:
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)

    with pytest.raises(GameLifecycleError, match="trigger_timing must be a ReactionWindow"):
        TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id="blood_surge",
            trigger_timing=cast(ReactionWindow, "not-a-reaction-window"),
            max_distance_inches=3.0,
        )
    with pytest.raises(GameLifecycleError, match="max_distance_inches must be positive"):
        TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id="blood_surge",
            trigger_timing=descriptor.trigger_timing,
            max_distance_inches=0.0,
        )
    with pytest.raises(GameLifecycleError, match="max_distance_inches must be finite"):
        TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id="blood_surge",
            trigger_timing=descriptor.trigger_timing,
            max_distance_inches=float("inf"),
        )
    with pytest.raises(GameLifecycleError, match="allow_battle_shocked must be a bool"):
        TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id="blood_surge",
            trigger_timing=descriptor.trigger_timing,
            max_distance_inches=3.0,
            allow_battle_shocked=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="optional must be a bool"):
        TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id="blood_surge",
            trigger_timing=descriptor.trigger_timing,
            max_distance_inches=3.0,
            optional=cast(bool, "yes"),
        )
    with pytest.raises(GameLifecycleError, match="trigger_timing must be a ReactionWindow"):
        SurgeMoveState(
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            unit_instance_id="army-alpha:intercessor-unit-1",
            source_rule_id="blood_surge",
            trigger_timing=cast(ReactionWindow, "not-a-reaction-window"),
            request_id="decision-request-invalid-trigger-window",
            result_id="phase10s-result-invalid-trigger-window",
        )
    with pytest.raises(GameLifecycleError, match="SurgeMoveState phase must match"):
        SurgeMoveState(
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            unit_instance_id="army-alpha:intercessor-unit-1",
            source_rule_id="blood_surge",
            trigger_timing=descriptor.trigger_timing,
            request_id="decision-request-invalid-phase",
            result_id="phase10s-result-invalid-phase",
        )
    with pytest.raises(GameLifecycleError, match="requires a TriggeredMovementDescriptor"):
        SurgeMoveState.from_resolution(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            descriptor=cast(TriggeredMovementDescriptor, "not-a-descriptor"),
            request_id="decision-request-bad-descriptor",
            result_id="phase10s-result-bad-descriptor",
        )
    with pytest.raises(GameLifecycleError, match="SurgeMoveState can record only surge movement"):
        SurgeMoveState.from_resolution(
            player_id="player-a",
            battle_round=1,
            unit_instance_id="army-alpha:intercessor-unit-1",
            descriptor=_reactive_step_descriptor(max_distance_inches=2.0),
            request_id="decision-request-non-surge",
            result_id="phase10s-result-non-surge",
        )

    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    first_model = unit_placement.model_placements[0]
    full_witness = _shift_witness(unit_placement, dx=3.0)
    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=full_witness,
        battle_round=state.battle_round,
    )
    assert state.battlefield_state is not None

    with pytest.raises(GameLifecycleError, match="requires a BattlefieldScenario"):
        resolve_triggered_movement(
            scenario=cast(BattlefieldScenario, "not-a-scenario"),
            ruleset_descriptor=_ruleset(),
            unit_placement=unit_placement,
            descriptor=descriptor,
            path_witness=full_witness,
            battle_round=state.battle_round,
        )
    with pytest.raises(GameLifecycleError, match="requires a RulesetDescriptor"):
        resolve_triggered_movement(
            scenario=_scenario_from_state(state),
            ruleset_descriptor=cast(RulesetDescriptor, "not-a-ruleset"),
            unit_placement=unit_placement,
            descriptor=descriptor,
            path_witness=full_witness,
            battle_round=state.battle_round,
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitPlacement"):
        resolve_triggered_movement(
            scenario=_scenario_from_state(state),
            ruleset_descriptor=_ruleset(),
            unit_placement=cast(UnitPlacement, "not-a-placement"),
            descriptor=descriptor,
            path_witness=full_witness,
            battle_round=state.battle_round,
        )
    with pytest.raises(GameLifecycleError, match="requires a descriptor"):
        resolve_triggered_movement(
            scenario=_scenario_from_state(state),
            ruleset_descriptor=_ruleset(),
            unit_placement=unit_placement,
            descriptor=cast(TriggeredMovementDescriptor, "not-a-descriptor"),
            path_witness=full_witness,
            battle_round=state.battle_round,
        )
    with pytest.raises(GameLifecycleError, match="requires a PathWitness"):
        resolve_triggered_movement(
            scenario=_scenario_from_state(state),
            ruleset_descriptor=_ruleset(),
            unit_placement=unit_placement,
            descriptor=descriptor,
            path_witness=cast(PathWitness, "not-a-witness"),
            battle_round=state.battle_round,
        )
    with pytest.raises(GameLifecycleError, match="battle_round must be positive"):
        resolve_triggered_movement(
            scenario=_scenario_from_state(state),
            ruleset_descriptor=_ruleset(),
            unit_placement=unit_placement,
            descriptor=descriptor,
            path_witness=full_witness,
            battle_round=0,
        )
    with pytest.raises(GameLifecycleError, match="apply requires battlefield_state"):
        apply_triggered_movement_to_battlefield(
            battlefield_state=cast(BattlefieldRuntimeState, "not-a-battlefield"),
            resolution=resolution,
        )
    with pytest.raises(GameLifecycleError, match="apply requires a resolution"):
        apply_triggered_movement_to_battlefield(
            battlefield_state=state.battlefield_state,
            resolution=cast(TriggeredMovementResolution, "not-a-resolution"),
        )

    first_model_path = full_witness.poses_for_model(first_model.model_instance_id)
    partial_witness = PathWitness.for_paths(((first_model.model_instance_id, first_model_path),))
    with pytest.raises(GameLifecycleError, match="witness must match selected unit models"):
        resolve_triggered_movement(
            scenario=_scenario_from_state(state),
            ruleset_descriptor=_ruleset(),
            unit_placement=unit_placement,
            descriptor=descriptor,
            path_witness=partial_witness,
            battle_round=state.battle_round,
        )


def test_triggered_movement_state_readiness_is_fail_fast() -> None:
    handler = TriggeredMovementHandler(ruleset_descriptor=_ruleset())

    setup_state = _battle_ready_state()
    setup_unit_placement = _unit_placement(setup_state)
    setup_state.stage = GameLifecycleStage.SETUP
    with pytest.raises(GameLifecycleError, match="requires battle stage"):
        handler.request_from_state(
            state=setup_state,
            unit_instance_id=setup_unit_placement.unit_instance_id,
            descriptor=_movement_surge_descriptor(max_distance_inches=3.0),
            candidate_witnesses=(_shift_witness(setup_unit_placement, dx=3.0),),
        )

    phase_state = _battle_ready_state()
    phase_unit_placement = _unit_placement(phase_state)
    phase_state.battle_phase_index = None
    with pytest.raises(GameLifecycleError, match="requires current battle phase"):
        handler.request_from_state(
            state=phase_state,
            unit_instance_id=phase_unit_placement.unit_instance_id,
            descriptor=_movement_surge_descriptor(max_distance_inches=3.0),
            candidate_witnesses=(_shift_witness(phase_unit_placement, dx=3.0),),
        )

    active_player_state = _battle_ready_state()
    active_player_unit_placement = _unit_placement(active_player_state)
    active_player_state.active_player_id = None
    with pytest.raises(GameLifecycleError, match="requires active_player_id"):
        handler.request_from_state(
            state=active_player_state,
            unit_instance_id=active_player_unit_placement.unit_instance_id,
            descriptor=_movement_surge_descriptor(max_distance_inches=3.0),
            candidate_witnesses=(_shift_witness(active_player_unit_placement, dx=3.0),),
        )

    battlefield_state = _battle_ready_state()
    battlefield_unit_placement = _unit_placement(battlefield_state)
    battlefield_state.battlefield_state = None
    with pytest.raises(GameLifecycleError, match="requires battlefield_state"):
        handler.request_from_state(
            state=battlefield_state,
            unit_instance_id=battlefield_unit_placement.unit_instance_id,
            descriptor=_movement_surge_descriptor(max_distance_inches=3.0),
            candidate_witnesses=(_shift_witness(battlefield_unit_placement, dx=3.0),),
        )


def test_triggered_movement_request_rejects_invalid_resolution_sets() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
    )
    assert state.active_player_id is not None
    assert state.current_battle_phase is not None

    with pytest.raises(
        GameLifecycleError,
        match="descriptor must be a TriggeredMovementDescriptor",
    ):
        TriggeredMovementRequest(
            request_id="decision-request-invalid-descriptor",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id=unit_placement.player_id,
            active_player_id=state.active_player_id,
            current_phase=state.current_battle_phase.value,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=cast(TriggeredMovementDescriptor, "not-a-descriptor"),
            resolutions=(resolution,),
        )
    with pytest.raises(GameLifecycleError, match="resolutions must be a tuple"):
        TriggeredMovementRequest(
            request_id="decision-request-resolution-list",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id=unit_placement.player_id,
            active_player_id=state.active_player_id,
            current_phase=state.current_battle_phase.value,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            resolutions=cast(tuple[TriggeredMovementResolution, ...], [resolution]),
        )
    with pytest.raises(GameLifecycleError, match="requires at least one resolution"):
        TriggeredMovementRequest(
            request_id="decision-request-resolution-empty",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id=unit_placement.player_id,
            active_player_id=state.active_player_id,
            current_phase=state.current_battle_phase.value,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            resolutions=(),
        )
    with pytest.raises(GameLifecycleError, match="resolutions must contain resolutions"):
        TriggeredMovementRequest(
            request_id="decision-request-resolution-bad-item",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id=unit_placement.player_id,
            active_player_id=state.active_player_id,
            current_phase=state.current_battle_phase.value,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            resolutions=cast(tuple[TriggeredMovementResolution, ...], ("not-a-resolution",)),
        )
    with pytest.raises(GameLifecycleError, match="resolution descriptor drift"):
        TriggeredMovementRequest(
            request_id="decision-request-resolution-descriptor-drift",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id=unit_placement.player_id,
            active_player_id=state.active_player_id,
            current_phase=state.current_battle_phase.value,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=_movement_surge_descriptor(max_distance_inches=2.0),
            resolutions=(resolution,),
        )

    invalid_resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
        battle_shocked_unit_ids=(unit_placement.unit_instance_id,),
    )
    with pytest.raises(GameLifecycleError, match="options must be valid choices"):
        TriggeredMovementRequest(
            request_id="decision-request-resolution-invalid",
            game_id=state.game_id,
            battle_round=state.battle_round,
            player_id=unit_placement.player_id,
            active_player_id=state.active_player_id,
            current_phase=state.current_battle_phase.value,
            unit_instance_id=unit_placement.unit_instance_id,
            descriptor=descriptor,
            resolutions=(invalid_resolution,),
        )


def test_triggered_movement_resolution_rejects_invalid_components() -> None:
    state = _battle_ready_state()
    unit_placement = _unit_placement(state)
    descriptor = _movement_surge_descriptor(max_distance_inches=3.0)
    resolution = resolve_triggered_movement(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=_shift_witness(unit_placement, dx=3.0),
        battle_round=state.battle_round,
    )
    violation = TriggeredMovementViolation(
        violation_code=TriggeredMovementViolationCode.BATTLE_SHOCKED_SURGE_FORBIDDEN,
        message="Battle-shocked units cannot make surge moves.",
    )

    with pytest.raises(GameLifecycleError, match="descriptor must be a descriptor"):
        replace(resolution, descriptor=cast(TriggeredMovementDescriptor, "not-a-descriptor"))
    with pytest.raises(GameLifecycleError, match="attempted_placement must be a UnitPlacement"):
        replace(resolution, attempted_placement=cast(UnitPlacement, "not-a-placement"))
    with pytest.raises(GameLifecycleError, match="attempted placement drift"):
        replace(resolution, unit_instance_id="army-alpha:unknown-unit")
    with pytest.raises(GameLifecycleError, match="witness must be a PathWitness"):
        replace(resolution, witness=cast(PathWitness, "not-a-witness"))
    with pytest.raises(GameLifecycleError, match="coherency_result must be UnitCoherencyResult"):
        replace(resolution, coherency_result=cast(UnitCoherencyResult, "not-coherency"))
    with pytest.raises(GameLifecycleError, match="rollback_record must be MovementRollbackRecord"):
        replace(resolution, rollback_record=cast(MovementRollbackRecord, "not-rollback"))
    with pytest.raises(GameLifecycleError, match="violations must be a tuple"):
        replace(
            resolution,
            restriction_violations=cast(tuple[TriggeredMovementViolation, ...], [violation]),
        )
    with pytest.raises(GameLifecycleError, match="violations must contain violations"):
        replace(
            resolution,
            restriction_violations=cast(tuple[TriggeredMovementViolation, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="path_validation_results must be a tuple"):
        replace(
            resolution,
            path_validation_results=cast(tuple[PathValidationResult, ...], [object()]),
        )
    with pytest.raises(GameLifecycleError, match="must contain PathValidationResult"):
        replace(
            resolution,
            path_validation_results=cast(tuple[PathValidationResult, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="terrain_path_legality_results must be a tuple"):
        replace(
            resolution,
            terrain_path_legality_results=cast(tuple[TerrainPathLegalityResult, ...], [object()]),
        )
    with pytest.raises(GameLifecycleError, match="must contain TerrainPathLegalityResult"):
        replace(
            resolution,
            terrain_path_legality_results=cast(tuple[TerrainPathLegalityResult, ...], ("bad",)),
        )
    with pytest.raises(GameLifecycleError, match="movement_payload must be a JSON object"):
        replace(resolution, movement_payload=cast(dict[str, JsonValue], []))


def _battle_ready_state() -> GameState:
    lifecycle, _movement_status = _advance_to_movement_unit_selection(_config())
    state = lifecycle.state
    assert state is not None
    return state


def _advance_to_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10s-result-secondary-001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10s-result-secondary-002",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _advance_to_movement_action_request(
    config: GameConfig,
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10s-result-action-001",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return lifecycle, action_request


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10s-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_tenth(
            descriptor_version="core-v2-phase10s-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
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
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_tenth(descriptor_version="core-v2-phase10s-test")


def _blood_surge_descriptor(
    *,
    max_distance_inches: float,
    optional: bool = True,
) -> TriggeredMovementDescriptor:
    return TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.SURGE,
        source_rule_id="blood_surge",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.SHOOTING,
            window_kind=ReactionWindowKind.AFTER_UNIT_LOSES_WOUNDS,
            source_step="shooting_attacks",
            source_event_id="event-source-000001",
        ),
        max_distance_inches=max_distance_inches,
        optional=optional,
    )


def _movement_surge_descriptor(
    *,
    max_distance_inches: float,
    optional: bool = True,
) -> TriggeredMovementDescriptor:
    return TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.SURGE,
        source_rule_id="blood_surge",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="movement_step",
            source_event_id="event-source-movement-000001",
        ),
        max_distance_inches=max_distance_inches,
        optional=optional,
    )


def _reactive_step_descriptor(
    *,
    max_distance_inches: float,
    optional: bool = True,
) -> TriggeredMovementDescriptor:
    return TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id="reactive_step",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step=None,
            source_event_id=None,
        ),
        max_distance_inches=max_distance_inches,
        optional=optional,
    )


def _set_current_battle_phase(state: GameState, phase: BattlePhase) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(phase)


def _aircraft_battle_state(*, aircraft_pose: Pose) -> tuple[GameState, UnitInstance]:
    scenario, aircraft, _enemy = _aircraft_scenario()
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=aircraft.unit_instance_id,
        pose=aircraft_pose,
    )
    return _battle_state_from_scenario(scenario), aircraft


def _aircraft_transit_battle_state() -> tuple[GameState, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request_for_units(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="mover-unit",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    beta = muster_army(
        catalog=catalog,
        request=_army_muster_request_for_units(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="enemy-aircraft",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    enemy_aircraft = replace(
        beta.unit_by_id("army-beta:enemy-aircraft"),
        keywords=("Aircraft", "Fly", "Vehicle"),
    )
    beta = replace(
        beta,
        units=tuple(
            enemy_aircraft if unit.unit_instance_id == enemy_aircraft.unit_instance_id else unit
            for unit in beta.units
        ),
    )
    mover = alpha.unit_by_id("army-alpha:mover-unit")
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10s-aircraft-transit",
        armies=(alpha, beta),
    )
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=mover.unit_instance_id,
        pose=Pose.at(6.0, 20.0),
    )
    mover_radius = _first_model_radius_x(mover)
    aircraft_radius = _first_model_radius_x(enemy_aircraft)
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=enemy_aircraft.unit_instance_id,
        pose=Pose.at(9.0, 20.0 + mover_radius + aircraft_radius + 0.5),
    )
    return _battle_state_from_scenario(scenario), mover, enemy_aircraft


def _aircraft_scenario() -> tuple[BattlefieldScenario, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request_for_units(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="aircraft-unit",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    beta = muster_army(
        catalog=catalog,
        request=_army_muster_request_for_units(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="enemy-unit",
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
            ),
        ),
    )
    aircraft = replace(
        alpha.unit_by_id("army-alpha:aircraft-unit"),
        keywords=("Aircraft", "Fly", "Hover", "Vehicle"),
    )
    alpha = replace(
        alpha,
        units=tuple(
            aircraft if unit.unit_instance_id == aircraft.unit_instance_id else unit
            for unit in alpha.units
        ),
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10s-aircraft",
        armies=(alpha, beta),
    )
    return scenario, aircraft, beta.unit_by_id("army-beta:enemy-unit")


def _battle_state_from_scenario(scenario: BattlefieldScenario) -> GameState:
    ruleset = _ruleset()
    return GameState(
        game_id="phase10s-aircraft-game",
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
        army_definitions=list(scenario.armies),
        battlefield_state=scenario.battlefield_state,
    )


def _army_muster_request_for_units(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
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
        unit_selections=unit_selections,
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _with_unit_first_model_pose(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    pose: Pose,
) -> BattlefieldScenario:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    first_placement = unit_placement.model_placements[0].with_pose(pose)
    updated_placement = unit_placement.with_model_placements(
        (first_placement, *unit_placement.model_placements[1:])
    )
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_placement),
    )


def _first_model_radius_x(unit: UnitInstance) -> float:
    return unit.own_models[0].geometry.primary_part().radius_x_inches


def _hover_state_for_aircraft(aircraft: UnitInstance) -> HoverModeState:
    return HoverModeState.active_for_unit(
        player_id="player-a",
        unit_instance_id=aircraft.unit_instance_id,
        decision_request_id="phase10s-hover-request",
        decision_result_id="phase10s-hover-result",
    )


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    assert state.battlefield_state is not None
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _unit_placement(state: GameState) -> UnitPlacement:
    assert state.battlefield_state is not None
    return state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")


def _shift_witness(unit_placement: UnitPlacement, *, dx: float) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        midpoint = Pose.at(
            x=start.position.x + (dx / 2.0),
            y=start.position.y,
            z=start.position.z,
            facing_degrees=start.facing.degrees,
        )
        end = Pose.at(
            x=start.position.x + dx,
            y=start.position.y,
            z=start.position.z,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _move_first_enemy_model_into_engagement(state: GameState) -> None:
    assert state.battlefield_state is not None
    friendly = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    friendly_pose = friendly.model_placements[0].pose
    first, *rest = enemy.model_placements
    updated_enemy = enemy.with_model_placements(
        (
            first.with_pose(
                Pose.at(
                    x=friendly_pose.position.x + 2.0,
                    y=friendly_pose.position.y,
                    z=friendly_pose.position.z,
                    facing_degrees=180.0,
                )
            ),
            *rest,
        )
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(updated_enemy)


def _move_first_friendly_model(state: GameState, *, dx: float) -> None:
    assert state.battlefield_state is not None
    friendly = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    first, *rest = friendly.model_placements
    start = first.pose
    updated_friendly = friendly.with_model_placements(
        (
            first.with_pose(
                Pose.at(
                    x=start.position.x + dx,
                    y=start.position.y,
                    z=start.position.z,
                    facing_degrees=start.facing.degrees,
                )
            ),
            *rest,
        )
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(updated_friendly)


def _option_payload(request: DecisionRequest, option_id: str) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], request.option_by_id(option_id).payload)


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, JsonValue]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            return cast(dict[str, JsonValue], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")
