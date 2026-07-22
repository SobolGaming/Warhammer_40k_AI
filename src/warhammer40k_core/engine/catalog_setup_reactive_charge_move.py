from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_setup_reactive_shoot_charge import (
    CATALOG_SETUP_REACTIVE_CHARGE_MOVE_EVENT,
    CATALOG_SETUP_REACTIVE_SOURCE_KIND,
    setup_reactive_active_player_id,
    setup_reactive_battlefield_scenario,
    setup_reactive_payload_distance_map,
    setup_reactive_payload_int,
    setup_reactive_payload_object,
    setup_reactive_payload_string,
    setup_reactive_proposal_context,
    setup_reactive_proposal_context_string_or_none,
    setup_reactive_target_limited_reachable_charge_distances,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    ChargeMoveProposal,
    ChargeMoveProposalPayload,
    ChargeMoveResolution,
    charge_move_violation_code,
    resolve_charge_move,
)
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def is_catalog_setup_reactive_charge_move_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Setup-reactive charge request check requires request.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    return (
        setup_reactive_proposal_context_string_or_none(
            proposal_request,
            key="source_kind",
        )
        == CATALOG_SETUP_REACTIVE_SOURCE_KIND
    )


def invalid_catalog_setup_reactive_charge_move_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    parsed = _parse_setup_reactive_charge_move_proposal_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    submitted_request, proposal = parsed
    proposal_validation = proposal.validation_result_for_request(submitted_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_setup_reactive_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=proposal_validation,
            message="Setup-reactive Charge Move proposal does not match the pending request.",
        )
    context = setup_reactive_proposal_context(proposal_request)
    maximum_distance = setup_reactive_payload_int(context, key="maximum_distance_inches")
    current_reachable = setup_reactive_target_limited_reachable_charge_distances(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
        player_id=proposal_request.actor_id,
        target_unit_instance_id=setup_reactive_payload_string(
            context,
            key="target_unit_instance_id",
        ),
        maximum_distance_inches=maximum_distance,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    requested_reachable = setup_reactive_payload_distance_map(
        context,
        key="reachable_target_distances_inches",
    )
    if current_reachable != requested_reachable:
        return _reject_invalid_setup_reactive_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="setup_reactive_charge_reachable_targets_drift",
                message="Setup-reactive Charge Move reachable target snapshot drifted.",
                field="reachable_target_unit_instance_ids",
                status="stale",
            ),
            message="Setup-reactive Charge Move reachable target snapshot is stale.",
        )
    return None


def apply_catalog_setup_reactive_charge_move(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex | None = None,
) -> LifecycleStatus | None:
    parsed = _parse_setup_reactive_charge_move_proposal_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal_request, proposal = parsed
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_setup_reactive_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=proposal_validation,
            message="Setup-reactive Charge Move proposal does not match the pending request.",
        )
    if proposal.is_no_move_choice:
        decisions.event_log.append(
            "catalog_setup_reactive_charge_move_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": setup_reactive_active_player_id(state),
                    "phase": BattlePhase.MOVEMENT.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "proposal_request_id": proposal_request.request_id,
                    "proposal_validation": proposal_validation.to_payload(),
                }
            ),
        )
        return None
    if proposal.witness is None:
        raise GameLifecycleError("Validated setup-reactive Charge Move requires a witness.")
    scenario = setup_reactive_battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    context = setup_reactive_proposal_context(proposal_request)
    maximum_distance = setup_reactive_payload_int(context, key="maximum_distance_inches")
    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=proposal.charge_target_unit_instance_ids,
        maximum_distance_inches=maximum_distance,
        path_witness=proposal.witness,
        hover_mode_states=tuple(state.hover_mode_states),
        unit_persisting_effects=tuple(state.persisting_effects_for_unit(proposal.unit_instance_id)),
        ability_index=ability_index,
    )
    violation_code = charge_move_violation_code(
        resolution=resolution,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=maximum_distance,
    )
    if violation_code is not None:
        return _reject_invalid_setup_reactive_charge_move_resolution(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            resolution=resolution,
            violation_code=violation_code,
            message=f"Setup-reactive Charge Move is invalid: {violation_code}.",
        )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Setup-reactive Charge Move requires battlefield_state.")
    transition_batch = resolution.transition_batch(before=unit_placement)
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(resolution.attempted_placement)
    )
    decisions.event_log.append(
        CATALOG_SETUP_REACTIVE_CHARGE_MOVE_EVENT,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": setup_reactive_active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": resolution.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
                "proposal_validation": proposal_validation.to_payload(),
                "transition_batch": transition_batch.to_payload(),
                "charge_bonus_suppressed": True,
                "suppressed_charge_bonus": "fights_first",
                **resolution.movement_payload,
            }
        ),
    )
    return None


def _parse_setup_reactive_charge_move_proposal_submission_or_invalid(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> tuple[MovementProposalRequest, ChargeMoveProposal] | LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    try:
        proposal = ChargeMoveProposal.from_payload(
            cast(ChargeMoveProposalPayload, setup_reactive_payload_object(result.payload))
        )
    except (GameLifecycleError, GeometryError, KeyError, TypeError) as exc:
        return _reject_invalid_setup_reactive_charge_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=_setup_reactive_charge_payload_parse_failure(
                proposal_request=proposal_request,
                error=exc,
            ),
            message="Setup-reactive Charge Move proposal payload is malformed.",
        )
    return (proposal_request, proposal)


def _setup_reactive_charge_payload_parse_failure(
    *,
    proposal_request: MovementProposalRequest,
    error: GameLifecycleError | GeometryError | KeyError | TypeError,
) -> ProposalValidationResult:
    if type(error) is KeyError:
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="proposal_payload_missing_field",
            message=f"Setup-reactive Charge Move proposal payload missing {error.args[0]}.",
            field=str(error.args[0]),
        )
    field = "payload"
    message = str(error)
    if "proposal_kind" in message:
        field = "proposal_kind"
    elif "movement_mode" in message or "MovementMode" in message:
        field = "movement_mode"
    elif "movement_phase_action" in message:
        field = "movement_phase_action"
    elif "charge_target_unit_instance_ids" in message:
        field = "charge_target_unit_instance_ids"
    elif "witness" in message or "PathWitness" in message:
        field = "witness"
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code="proposal_payload_malformed",
        message=f"Setup-reactive Charge Move proposal payload is malformed: {message}",
        field=field,
    )


def _reject_invalid_setup_reactive_charge_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_validation: ProposalValidationResult,
    message: str,
) -> LifecycleStatus:
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": setup_reactive_active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": proposal_validation.status,
            "proposal_validation": proposal_validation.to_payload(),
        }
    )
    decisions.event_log.append(
        "catalog_setup_reactive_charge_move_proposal_invalid",
        payload,
    )
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload=payload,
    )


def _reject_invalid_setup_reactive_charge_move_resolution(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    proposal_validation: ProposalValidationResult,
    resolution: ChargeMoveResolution,
    violation_code: str,
    message: str,
) -> LifecycleStatus:
    invalid_validation = ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=message,
        field="witness",
    )
    invalid_payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": setup_reactive_active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": resolution.unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "catalog_setup_reactive_charge_move_invalid",
            "violation_code": violation_code,
            "proposal_request_id": proposal_request.request_id,
            "proposal_validation": invalid_validation.to_payload(),
            "pre_apply_proposal_validation": proposal_validation.to_payload(),
            **resolution.movement_payload,
        }
    )
    decisions.event_log.append("catalog_setup_reactive_charge_move_invalid", invalid_payload)
    retry_request = _request_setup_reactive_charge_move_proposal_retry(
        state=state,
        decisions=decisions,
        proposal_request=proposal_request,
        rejected_result=result,
    )
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "catalog_setup_reactive_charge_move_invalid",
            "battle_round": state.battle_round,
            "active_player_id": setup_reactive_active_player_id(state),
            "unit_instance_id": resolution.unit_instance_id,
            "movement_phase_action": CHARGE_MOVE_ACTION,
            "violation_code": violation_code,
            "proposal_request_id": proposal_request.request_id,
            "retry_request_id": retry_request.request_id,
        },
    )


def _request_setup_reactive_charge_move_proposal_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context=dict(proposal_request.context or {}),
    )
    request = decisions.request_decision(retry_proposal.to_decision_request())
    decisions.event_log.append(
        "catalog_setup_reactive_charge_move_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": setup_reactive_active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": proposal_request.unit_instance_id,
                "movement_phase_action": CHARGE_MOVE_ACTION,
                "movement_mode": MovementMode.CHARGE.value,
                "proposal_kind": ProposalKind.CHARGE_MOVE.value,
                "request_id": request.request_id,
                "source_decision_request_id": proposal_request.source_decision_request_id,
                "source_decision_result_id": proposal_request.source_decision_result_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "phase_body_status": "catalog_setup_reactive_charge_move_proposal_required",
            }
        ),
    )
    return request
