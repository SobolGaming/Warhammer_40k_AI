from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement import (
    FallBackModeKind,
    MovementPhaseActionKind,
    MovementPhaseHandler,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def straight_line_witness_for_unit(
    lifecycle: GameLifecycle,
    *,
    unit_instance_id: str,
    dx: float = 0.0,
    dy: float = 0.0,
    dz: float = 0.0,
) -> PathWitness:
    state = lifecycle.state
    if state is None or state.battlefield_state is None:
        raise GameLifecycleError("Movement proposal test helper requires battlefield_state.")
    return straight_line_witness_for_state(
        state,
        unit_instance_id=unit_instance_id,
        dx=dx,
        dy=dy,
        dz=dz,
    )


def straight_line_witness_for_state(
    state: GameState,
    *,
    unit_instance_id: str,
    dx: float = 0.0,
    dy: float = 0.0,
    dz: float = 0.0,
) -> PathWitness:
    if state.battlefield_state is None:
        raise GameLifecycleError("Movement proposal test helper requires battlefield_state.")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        midpoint = Pose.at(
            start.position.x + (dx / 2.0),
            start.position.y + (dy / 2.0),
            start.position.z + (dz / 2.0),
            facing_degrees=start.facing.degrees,
        )
        end = Pose.at(
            start.position.x + dx,
            start.position.y + dy,
            start.position.z + dz,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def submit_action_and_movement_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    action_result_id: str,
    proposal_result_id: str,
    unit_instance_id: str,
    movement_phase_action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    witness: PathWitness,
    fall_back_mode: FallBackModeKind | None = None,
) -> LifecycleStatus:
    proposal_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=action_result_id,
            request=request,
            selected_option_id=option_id,
        )
    )
    proposal_request = require_movement_proposal_request(proposal_status)
    return submit_movement_proposal(
        lifecycle,
        request=proposal_request,
        result_id=proposal_result_id,
        unit_instance_id=unit_instance_id,
        movement_phase_action=movement_phase_action,
        movement_mode=movement_mode,
        witness=witness,
        fall_back_mode=fall_back_mode,
    )


def submit_movement_proposal(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    result_id: str,
    unit_instance_id: str,
    movement_phase_action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    witness: PathWitness,
    fall_back_mode: FallBackModeKind | None = None,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=proposal_request.proposal_kind,
                    unit_instance_id=unit_instance_id,
                    movement_phase_action=movement_phase_action.value,
                    witness=witness,
                    movement_mode=movement_mode.value,
                    fall_back_mode=None if fall_back_mode is None else fall_back_mode.value,
                ).to_payload()
            ),
        )
    )


def submit_default_movement_proposal_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
    dx: float | None = None,
    dy: float | None = None,
) -> LifecycleStatus:
    if status.decision_request is None:
        return status
    if status.decision_request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return status
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    if proposal_request.movement_phase_action is None:
        return status
    action = MovementPhaseActionKind(proposal_request.movement_phase_action)
    context = proposal_request.context or {}
    movement_mode = MovementMode(
        _proposal_context_string(
            context,
            key="movement_mode",
            default=_default_movement_mode(action).value,
        )
    )
    fall_back_mode_payload = _optional_proposal_context_string(context, key="fall_back_mode")
    fall_back_mode = (
        None if fall_back_mode_payload is None else FallBackModeKind(fall_back_mode_payload)
    )
    default_dx, default_dy = _default_displacement(action)
    witness = straight_line_witness_for_unit(
        lifecycle,
        unit_instance_id=proposal_request.unit_instance_id,
        dx=default_dx if dx is None else dx,
        dy=default_dy if dy is None else dy,
    )
    return submit_movement_proposal(
        lifecycle,
        request=status.decision_request,
        result_id=result_id,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action=action,
        movement_mode=movement_mode,
        witness=witness,
        fall_back_mode=fall_back_mode,
    )


def submit_default_handler_movement_proposal_if_pending(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    status: LifecycleStatus | None,
    result_id: str,
    dx: float | None = None,
    dy: float | None = None,
) -> LifecycleStatus | None:
    if status is None or status.decision_request is None:
        return status
    if status.decision_request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return status
    proposal_request = MovementProposalRequest.from_decision_request_payload(
        status.decision_request.payload
    )
    if proposal_request.movement_phase_action is None:
        return status
    action = MovementPhaseActionKind(proposal_request.movement_phase_action)
    context = proposal_request.context or {}
    movement_mode = MovementMode(
        _proposal_context_string(
            context,
            key="movement_mode",
            default=_default_movement_mode(action).value,
        )
    )
    fall_back_mode_payload = _optional_proposal_context_string(context, key="fall_back_mode")
    fall_back_mode = (
        None if fall_back_mode_payload is None else FallBackModeKind(fall_back_mode_payload)
    )
    default_dx, default_dy = _default_displacement(action)
    witness = straight_line_witness_for_state(
        state,
        unit_instance_id=proposal_request.unit_instance_id,
        dx=default_dx if dx is None else dx,
        dy=default_dy if dy is None else dy,
    )
    return submit_handler_movement_proposal(
        handler=handler,
        state=state,
        decisions=decisions,
        request=status.decision_request,
        result_id=result_id,
        unit_instance_id=proposal_request.unit_instance_id,
        movement_phase_action=action,
        movement_mode=movement_mode,
        witness=witness,
        fall_back_mode=fall_back_mode,
    )


def submit_handler_movement_proposal(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result_id: str,
    unit_instance_id: str,
    movement_phase_action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    witness: PathWitness,
    fall_back_mode: FallBackModeKind | None = None,
    payload_mutation: Callable[[dict[str, JsonValue]], None] | None = None,
) -> LifecycleStatus | None:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload_value = validate_json_value(
        MovementProposalPayload(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            unit_instance_id=unit_instance_id,
            movement_phase_action=movement_phase_action.value,
            witness=witness,
            movement_mode=movement_mode.value,
            fall_back_mode=None if fall_back_mode is None else fall_back_mode.value,
        ).to_payload()
    )
    if not isinstance(payload_value, dict):
        raise GameLifecycleError("Movement proposal test helper payload must be an object.")
    payload = payload_value
    if payload_mutation is not None:
        payload_mutation(payload)
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
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


def require_movement_proposal_request(status: LifecycleStatus) -> DecisionRequest:
    if status.decision_request is None:
        raise GameLifecycleError("Expected pending movement proposal request.")
    if status.decision_request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Expected submit_movement_proposal request.")
    return status.decision_request


def _default_movement_mode(action: MovementPhaseActionKind) -> MovementMode:
    if action is MovementPhaseActionKind.ADVANCE:
        return MovementMode.ADVANCE
    if action is MovementPhaseActionKind.FALL_BACK:
        return MovementMode.FALL_BACK
    return MovementMode.NORMAL


def _default_displacement(action: MovementPhaseActionKind) -> tuple[float, float]:
    if action is MovementPhaseActionKind.FALL_BACK:
        return (0.0, 6.0)
    return (6.0, 0.0)


def _proposal_context_string(
    context: dict[str, JsonValue],
    *,
    key: str,
    default: str,
) -> str:
    value = context.get(key)
    if value is None:
        return default
    if type(value) is not str:
        raise GameLifecycleError(f"Movement proposal context {key} must be a string.")
    return value


def _optional_proposal_context_string(
    context: dict[str, JsonValue],
    *,
    key: str,
) -> str | None:
    value = context.get(key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Movement proposal context {key} must be a string.")
    return value
