from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.active_player_scopes import begin_reactive_move, end_reactive_move
from warhammer40k_core.engine.charge_movement_source import charge_placement_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.move_ability_choices import CHOICE_KEY, movement_keyword_options
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalPayloadPayload,
)
from warhammer40k_core.engine.normal_move_history import (
    NormalMoveSourceKind,
    NormalMoveState,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.surge_choices import selected_surge_target
from warhammer40k_core.engine.take_to_the_skies import flight_selection
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    TriggeredMovementDescriptor,
    TriggeredMovementDescriptorPayload,
    TriggeredMovementKind,
    TriggeredMovementRequest,
    _battlefield_scenario,
    _decision_payload_object,
    _descriptor_from_proposal_request,
    _payload_object,
    _payload_optional_bool,
    _payload_path_witness,
    _payload_string,
    _reject_invalid_triggered_movement_proposal,
    _request_payload_for_result,
    _ruleset_descriptor_for_handler,
    _triggered_movement_declined_payload,
    _triggered_movement_invalid_payload,
    _triggered_movement_proposal_request_from_request,
    _triggered_movement_proposal_retry_request,
    _triggered_movement_resolved_payload,
    _triggered_movement_violation_code,
    _validate_path_witness_tuple,
    _validate_reaction_window_matches_state,
    _validate_triggered_movement_declined_payload,
    _validate_triggered_movement_state_ready,
)
from warhammer40k_core.engine.triggered_movement_physical_authority import (
    triggered_movement_placement,
)
from warhammer40k_core.engine.triggered_movement_resolution import (
    apply_triggered_movement_to_battlefield,
    resolve_triggered_movement,
)
from warhammer40k_core.engine.triggered_movement_selection import (
    _apply_triggered_movement_unit_selection_decision,
)
from warhammer40k_core.geometry.pathing import PathWitness

if TYPE_CHECKING:
    from warhammer40k_core.engine.triggered_movement import TriggeredMovementHandler


def request_from_state(
    *,
    handler: TriggeredMovementHandler,
    state: GameState,
    unit_instance_id: str,
    descriptor: TriggeredMovementDescriptor,
    candidate_witnesses: tuple[PathWitness, ...],
    decisions: DecisionController | None = None,
) -> DecisionRequest:
    _validate_triggered_movement_state_ready(state)
    ruleset_descriptor = _ruleset_descriptor_for_handler(handler)
    if type(descriptor) is not TriggeredMovementDescriptor:
        raise GameLifecycleError("Triggered movement requires a descriptor.")
    _validate_reaction_window_matches_state(state=state, descriptor=descriptor)
    from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
    from warhammer40k_core.engine.surge_authority import require_surge_trigger
    from warhammer40k_core.engine.surge_movement import (
        closest_surge_targets,
        surge_ineligibility,
    )

    if descriptor.movement_kind is not TriggeredMovementKind.SURGE:
        reason = large_model_activity_reason(
            state, unit_instance_id, descriptor.movement_mode.value
        )
        if reason is not None:
            raise GameLifecycleError(reason)
    from warhammer40k_core.engine.movement_locks import movement_lock_reason

    lock = movement_lock_reason(state, unit_instance_id)
    if lock is not None:
        raise GameLifecycleError(lock)
    require_surge_trigger(state=state, decisions=decisions, descriptor=descriptor)
    if descriptor.movement_kind is TriggeredMovementKind.SURGE:
        reason = surge_ineligibility(state, unit_instance_id)
        if reason is not None:
            raise GameLifecycleError(reason)
    candidate_witness_tuple = _validate_path_witness_tuple(candidate_witnesses)
    if not candidate_witness_tuple:
        raise GameLifecycleError("Triggered movement requires at least one movement choice.")
    scenario = _battlefield_scenario(state)
    unit_placement = triggered_movement_placement(
        scenario=scenario, unit_instance_id=unit_instance_id
    )
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    selections = (
        (False, True)
        if "FLY" in view.keywords
        and descriptor.movement_kind is not TriggeredMovementKind.SURGE
        and descriptor.movement_mode is MovementMode.NORMAL
        and ruleset_descriptor.fly_policy.take_to_the_skies_supported
        else (False,)
    )
    keyword_options = movement_keyword_options(
        options=(
            DecisionOption(
                option_id="move",
                label="Move",
                payload=validate_json_value({"descriptor": descriptor.to_payload()}),
            ),
        ),
        unit=view,
    )
    resolutions = tuple(
        resolve_triggered_movement(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            descriptor=descriptor,
            path_witness=witness,
            take_to_the_skies=selected,
            move_keyword_choice=cast(dict[str, JsonValue], keyword_option.payload).get(CHOICE_KEY),
            surge_target_unit_instance_id=target_id,
            battle_round=state.battle_round,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            normal_move_states=tuple(state.normal_move_states),
            hover_mode_states=tuple(state.hover_mode_states),
        )
        for witness in candidate_witness_tuple
        for selected in selections
        for keyword_option in keyword_options
        for target_id in (
            closest_surge_targets(scenario=scenario, unit_instance_id=unit_instance_id)
            if descriptor.movement_kind is TriggeredMovementKind.SURGE
            else (None,)
        )
    )
    for witness in candidate_witness_tuple:
        matches = tuple(resolution for resolution in resolutions if resolution.witness == witness)
        if not any(resolution.is_valid for resolution in matches):
            raise GameLifecycleError(
                "Triggered movement request candidates must all be valid: "
                f"{_triggered_movement_violation_code(matches[0])}."
            )
    resolutions = tuple(resolution for resolution in resolutions if resolution.is_valid)
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Triggered movement requires current battle phase.")
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Triggered movement requires active_player_id.")
    return TriggeredMovementRequest(
        request_id=state.next_decision_request_id(),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=unit_placement.player_id,
        active_player_id=active_player_id,
        current_phase=current_phase.value,
        unit_instance_id=charge_placement_id(unit_placement),
        descriptor=descriptor,
        resolutions=resolutions,
    ).to_decision_request()


def apply_decision(
    *,
    handler: TriggeredMovementHandler,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.move_completion_triggers import record_move_completion_event

    _validate_triggered_movement_state_ready(state)
    if result.decision_type != SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE:
        raise GameLifecycleError("TriggeredMovementHandler received unsupported decision_type.")
    ruleset_descriptor = _ruleset_descriptor_for_handler(handler)
    request_payload = _request_payload_for_result(decisions=decisions, result=result)
    descriptor = TriggeredMovementDescriptor.from_payload(
        cast(TriggeredMovementDescriptorPayload, _payload_object(request_payload, "descriptor"))
    )
    _validate_reaction_window_matches_state(state=state, descriptor=descriptor)
    if _payload_optional_bool(request_payload, "requires_movement_proposal"):
        return _apply_triggered_movement_unit_selection_decision(
            state=state,
            result=result,
            decisions=decisions,
            descriptor=descriptor,
            request_payload=request_payload,
        )
    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, "unit_instance_id")
    if unit_instance_id != _payload_string(request_payload, "unit_instance_id"):
        raise GameLifecycleError("Triggered movement result unit drift.")
    scenario = _battlefield_scenario(state)
    unit_placement = triggered_movement_placement(
        scenario=scenario, unit_instance_id=unit_instance_id
    )
    if result.actor_id != unit_placement.player_id:
        raise GameLifecycleError("Triggered movement actor must own the moving unit.")
    if _payload_optional_bool(payload, "declined"):
        if result.selected_option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID:
            raise GameLifecycleError("Declined triggered movement result option drift.")
        if not descriptor.optional:
            raise GameLifecycleError("Mandatory triggered movement cannot be declined.")
        _validate_triggered_movement_declined_payload(
            payload=payload,
            descriptor=descriptor,
            unit_instance_id=unit_instance_id,
        )
        decisions.event_log.append(
            "triggered_movement_declined",
            _triggered_movement_declined_payload(
                state=state,
                result=result,
                unit_instance_id=unit_instance_id,
                descriptor=descriptor,
            ),
        )
        return None
    witness = _payload_path_witness(payload, "witness")
    resolution = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=witness,
        take_to_the_skies=flight_selection(payload),
        move_keyword_choice=payload.get(CHOICE_KEY),
        surge_target_unit_instance_id=selected_surge_target(payload, descriptor),
        battle_round=state.battle_round,
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        normal_move_states=tuple(state.normal_move_states),
        hover_mode_states=tuple(state.hover_mode_states),
    )
    drift_code = resolution.selected_payload_drift_code(payload)
    if drift_code is not None:
        invalid_payload = _triggered_movement_invalid_payload(
            state=state,
            result=result,
            unit_instance_id=unit_instance_id,
            descriptor=descriptor,
            resolution=resolution,
            violation_code=drift_code,
        )
        decisions.event_log.append("triggered_movement_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Triggered movement replay payload drift.",
            payload=invalid_payload,
        )
    if not resolution.is_valid:
        violation_code = _triggered_movement_violation_code(resolution)
        invalid_payload = _triggered_movement_invalid_payload(
            state=state,
            result=result,
            unit_instance_id=unit_instance_id,
            descriptor=descriptor,
            resolution=resolution,
            violation_code=violation_code,
        )
        decisions.event_log.append("triggered_movement_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Triggered movement is invalid.",
            payload=invalid_payload,
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Triggered movement requires battlefield_state.")
    begin_reactive_move(
        state=state,
        decisions=decisions,
        result=result,
        unit_instance_id=unit_instance_id,
        source_rule_id=descriptor.source_rule_id,
    )
    state.replace_battlefield_state(
        apply_triggered_movement_to_battlefield(
            battlefield_state=battlefield_state,
            resolution=resolution,
        )
    )
    if (
        descriptor.movement_mode is MovementMode.NORMAL
        and descriptor.movement_kind is not TriggeredMovementKind.SURGE
    ):
        state.record_normal_move_state(
            NormalMoveState(
                player_id=unit_placement.player_id,
                battle_round=state.battle_round,
                phase=descriptor.trigger_timing.phase,
                unit_instance_id=unit_instance_id,
                source_rule_id=descriptor.source_rule_id,
                source_kind=NormalMoveSourceKind.TRIGGERED,
                request_id=result.request_id,
                result_id=result.result_id,
            )
        )
    record_move_completion_event(
        state=state,
        decisions=decisions,
        event_type="triggered_movement_resolved",
        payload=_triggered_movement_resolved_payload(
            state=state,
            result=result,
            unit_instance_id=unit_instance_id,
            descriptor=descriptor,
            resolution=resolution,
            transition_batch=transition_batch,
        ),
    )
    end_reactive_move(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_instance_id,
        selection_request_id=result.request_id,
        selection_result_id=result.result_id,
        source_rule_id=descriptor.source_rule_id,
        result=result,
    )
    return None


def apply_proposal_decision(
    *,
    handler: TriggeredMovementHandler,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.move_completion_triggers import record_move_completion_event

    _validate_triggered_movement_state_ready(state)
    ruleset_descriptor = _ruleset_descriptor_for_handler(handler)
    proposal_request = _triggered_movement_proposal_request_from_request(request)
    if proposal_request.context is None:
        raise GameLifecycleError("Triggered movement proposal requires selection context.")
    submission = MovementProposalPayload.from_payload(
        cast(MovementProposalPayloadPayload, result.payload)
    )
    proposal_validation = submission.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_triggered_movement_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=proposal_validation,
            message="Triggered movement proposal does not match the pending request.",
        )
    descriptor = _descriptor_from_proposal_request(proposal_request)
    _validate_reaction_window_matches_state(state=state, descriptor=descriptor)
    scenario = _battlefield_scenario(state)
    unit_placement = triggered_movement_placement(
        scenario=scenario, unit_instance_id=proposal_request.unit_instance_id
    )
    if result.actor_id != unit_placement.player_id:
        raise GameLifecycleError("Triggered movement proposal actor must own the unit.")
    resolution = resolve_triggered_movement(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        descriptor=descriptor,
        path_witness=submission.witness,
        take_to_the_skies=flight_selection(proposal_request.context),
        move_keyword_choice=(proposal_request.context or {}).get(CHOICE_KEY),
        surge_target_unit_instance_id=selected_surge_target(proposal_request.context, descriptor),
        battle_round=state.battle_round,
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        normal_move_states=tuple(state.normal_move_states),
        hover_mode_states=tuple(state.hover_mode_states),
    )
    if not resolution.is_valid:
        violation_code = _triggered_movement_violation_code(resolution)
        invalid_payload = _triggered_movement_invalid_payload(
            state=state,
            result=result,
            unit_instance_id=proposal_request.unit_instance_id,
            descriptor=descriptor,
            resolution=resolution,
            violation_code=violation_code,
        )
        decisions.event_log.append("triggered_movement_invalid", invalid_payload)
        retry_request = _triggered_movement_proposal_retry_request(
            state=state,
            proposal_request=proposal_request,
            rejected_result=result,
        )
        decisions.request_decision(retry_request)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Triggered movement is invalid.",
            payload={**invalid_payload, "next_request_id": retry_request.request_id},
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Triggered movement requires battlefield_state.")
    state.replace_battlefield_state(
        apply_triggered_movement_to_battlefield(
            battlefield_state=battlefield_state,
            resolution=resolution,
        )
    )
    if (
        descriptor.movement_mode is MovementMode.NORMAL
        and descriptor.movement_kind is not TriggeredMovementKind.SURGE
    ):
        state.record_normal_move_state(
            NormalMoveState(
                player_id=unit_placement.player_id,
                battle_round=state.battle_round,
                phase=descriptor.trigger_timing.phase,
                unit_instance_id=proposal_request.unit_instance_id,
                source_rule_id=descriptor.source_rule_id,
                source_kind=NormalMoveSourceKind.TRIGGERED,
                request_id=result.request_id,
                result_id=result.result_id,
            )
        )
    record_move_completion_event(
        state=state,
        decisions=decisions,
        event_type="triggered_movement_resolved",
        payload=_triggered_movement_resolved_payload(
            state=state,
            result=result,
            unit_instance_id=proposal_request.unit_instance_id,
            descriptor=descriptor,
            resolution=resolution,
            transition_batch=transition_batch,
        ),
    )
    end_reactive_move(
        state=state,
        decisions=decisions,
        unit_instance_id=proposal_request.unit_instance_id,
        selection_request_id=_payload_string(proposal_request.context, "selection_request_id"),
        selection_result_id=_payload_string(proposal_request.context, "selection_result_id"),
        source_rule_id=descriptor.source_rule_id,
        result=result,
    )
    return None
