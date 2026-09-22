from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.charge_budget_value import ChargeMovementBudget
from warhammer40k_core.engine.charge_movement_source import (
    battlefield_with_charge_placement,
    charge_movement_placement,
)
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.charge_target_continuation import current_charge_targets
from warhammer40k_core.engine.take_to_the_skies import (
    selected_charge_flight as flight_selection_for_charge,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.charge_declaration import ChargeRollResult
from warhammer40k_core.engine.charge_required_targets import (
    CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
)
from warhammer40k_core.engine.charge_required_targets import (
    required_charge_target_unit_instance_ids as _required_charge_target_unit_instance_ids,
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
from warhammer40k_core.engine.phases import charge as _charge
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry


def invalid_charge_move_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    handler: _charge.ChargePhaseHandler,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus | None:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    parsed = _charge._parse_charge_move_proposal_submission_or_invalid(
        state=state, request=request, result=result, decisions=decisions
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    submitted_proposal_request, proposal = parsed
    proposal_validation = proposal.validation_result_for_request(submitted_proposal_request)
    if not proposal_validation.is_valid:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=proposal_validation,
            message="Charge Move proposal does not match the pending request.",
        )
    charge_state = state.charge_phase_state
    if charge_state is None:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_phase_state_missing",
                message="Charge Move proposal has no active charge phase state.",
                field="charge_phase_state",
            ),
            message="Charge Move proposal has no active phase state.",
        )
    pending_distance = charge_state.move_pending_distance_state()
    if pending_distance is None:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_distance_state_missing",
                message="Charge Move proposal has no pending charge distance state.",
                field="charge_phase_state",
            ),
            message="Charge Move proposal has no pending distance state.",
        )
    if pending_distance.roll_result.request.unit_instance_id != proposal.unit_instance_id:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="proposal_unit_drift",
                message="Charge Move proposal unit does not match the pending charge roll.",
                field="unit_instance_id",
            ),
            message="Charge Move proposal unit drifted.",
        )
    budget, current_reachable = current_charge_targets(state=state, handler=handler)
    context = proposal_request.context
    selected = charge_state.target_selection
    if (
        context is None
        or selected is None
        or context.get("movement_budget") != budget.to_payload()
        or context.get("maximum_distance_inches") != budget.maximum_distance_inches
        or context.get("target_selection") != selected.to_payload()
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge movement budget or selected target context drift.",
            payload={"invalid_reason": "charge_movement_context_drift"},
        )
    if (
        not proposal.is_no_move_choice
        and proposal.charge_target_unit_instance_ids != selected.target_ids
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge path must use its recorded targets.",
            payload={"invalid_reason": "charge_selected_targets_drift"},
        )
    requested_reachable = _charge._payload_distance_map(
        _charge._proposal_context(proposal_request),
        key="reachable_target_distances_inches",
    )
    if current_reachable != requested_reachable:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_reachable_targets_drift",
                message="Charge Move reachable target snapshot no longer matches state.",
                field="reachable_target_unit_instance_ids",
                status="stale",
            ),
            message="Charge Move reachable target snapshot is stale.",
        )
    current_required = _required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=proposal.unit_instance_id,
        reachable_target_unit_instance_ids=tuple(current_reachable),
    )
    requested_required = _charge._payload_optional_identifier_list(
        _charge._proposal_context(proposal_request),
        key=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
    )
    if current_required != requested_required:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="charge_required_targets_drift",
                message="Charge Move required target snapshot no longer matches state.",
                field=CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY,
                status="stale",
            ),
            message="Charge Move required target snapshot is stale.",
        )
    if proposal.witness is not None:
        witness_validation = _charge._charge_witness_matches_current_unit_status(
            state=state, proposal_request=proposal_request, proposal=proposal
        )
        if witness_validation is not None:
            return _charge._reject_invalid_charge_proposal(
                state=state,
                result=result,
                proposal_validation=witness_validation,
                message="Charge Move witness does not match the current unit.",
            )
    return None


def request_charge_move_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    charge_state: ChargePhaseState,
    roll_result: ChargeRollResult,
    budget: ChargeMovementBudget,
    reachable: dict[str, float],
) -> LifecycleStatus:
    if charge_state.active_selection is None:
        raise GameLifecycleError("Charge Move proposal requires active_selection.")
    if charge_state.target_selection is None:
        raise GameLifecycleError("Charge movement requires selected targets.")
    required_target_ids = _required_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=roll_result.request.unit_instance_id,
        reachable_target_unit_instance_ids=tuple(reachable),
    )
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=charge_state.active_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=roll_result.request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=charge_state.active_selection.request_id,
        source_decision_result_id=charge_state.active_selection.result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action=_charge.CHARGE_MOVE_ACTION,
        context={
            "source_selected_option_id": charge_state.active_selection.unit_instance_id,
            "movement_mode": MovementMode.CHARGE.value,
            "maximum_distance_inches": budget.maximum_distance_inches,
            "reachable_target_unit_instance_ids": list(reachable),
            "reachable_target_distances_inches": dict(sorted(reachable.items())),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
            "charge_roll": validate_json_value(roll_result.to_payload()),
            "movement_budget": budget.to_payload(),
            "target_selection": validate_json_value(charge_state.target_selection.to_payload()),
        },
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "charge_move_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": charge_state.active_player_id,
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": roll_result.request.unit_instance_id,
                "movement_phase_action": _charge.CHARGE_MOVE_ACTION,
                "movement_mode": MovementMode.CHARGE.value,
                "proposal_kind": ProposalKind.CHARGE_MOVE.value,
                "request_id": request.request_id,
                "source_decision_request_id": charge_state.active_selection.request_id,
                "source_decision_result_id": charge_state.active_selection.result_id,
                "maximum_distance_inches": budget.maximum_distance_inches,
                "reachable_target_unit_instance_ids": list(reachable),
                CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
                "phase_body_status": _charge._CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,  # pyright: ignore[reportPrivateUsage]
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.CHARGE.value,
            "phase_body_status": _charge._CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,  # pyright: ignore[reportPrivateUsage]
            "battle_round": state.battle_round,
            "active_player_id": charge_state.active_player_id,
            "unit_instance_id": roll_result.request.unit_instance_id,
            "movement_phase_action": _charge.CHARGE_MOVE_ACTION,
            "proposal_kind": ProposalKind.CHARGE_MOVE.value,
            "maximum_distance_inches": budget.maximum_distance_inches,
            "reachable_target_unit_instance_ids": list(reachable),
            CHARGE_MOVE_REQUIRED_TARGET_UNIT_INSTANCE_IDS_KEY: list(required_target_ids),
        },
    )


def _request_charge_move_proposal_retry(
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
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action=_charge.CHARGE_MOVE_ACTION,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "charge_move_proposal_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _charge._active_player_id(state),
                "phase": BattlePhase.CHARGE.value,
                "unit_instance_id": proposal_request.unit_instance_id,
                "movement_phase_action": _charge.CHARGE_MOVE_ACTION,
                "movement_mode": MovementMode.CHARGE.value,
                "proposal_kind": ProposalKind.CHARGE_MOVE.value,
                "request_id": request.request_id,
                "source_decision_request_id": proposal_request.source_decision_request_id,
                "source_decision_result_id": proposal_request.source_decision_result_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "phase_body_status": _charge._CHARGE_MOVE_PROPOSAL_REQUIRED_STATUS,  # pyright: ignore[reportPrivateUsage]
            }
        ),
    )
    return request


def _apply_charge_move_proposal_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
    ability_index: AbilityCatalogIndex,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.move_completion_triggers import record_move_completion_event

    _charge._validate_charge_phase_state(state)
    active_player_id = _charge._active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Charge Move proposal actor must be the active player.")
    charge_state = state.charge_phase_state
    if charge_state is None or charge_state.active_selection is None:
        raise GameLifecycleError("Charge Move proposal requires active_selection.")
    record = decisions.record_for_result(result)
    parsed = _charge._parse_charge_move_proposal_submission_or_invalid(
        state=state, request=record.request, result=result, decisions=decisions
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal_request, proposal = parsed
    proposal_validation = proposal.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _charge._reject_invalid_charge_proposal(
            state=state,
            result=result,
            proposal_validation=proposal_validation,
            message="Charge Move proposal does not match the pending request.",
        )
    pending_distance = charge_state.move_pending_distance_state()
    if pending_distance is None:
        raise GameLifecycleError("Charge Move proposal requires pending distance state.")
    budget = ChargeMovementBudget.from_payload((proposal_request.context or {})["movement_budget"])
    if proposal.is_no_move_choice:
        state.replace_charge_phase_state(
            charge_state.with_charge_move_resolved(proposal.unit_instance_id)
        )
        decisions.event_log.append(
            "charge_move_declined",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.CHARGE.value,
                    "unit_instance_id": proposal.unit_instance_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "proposal_request_id": proposal_request.request_id,
                    "phase_body_status": _charge._CHARGE_MOVE_DECLINED_STATUS,  # pyright: ignore[reportPrivateUsage]
                    "proposal_validation": proposal_validation.to_payload(),
                }
            ),
        )
        return None
    if proposal.witness is None:
        raise GameLifecycleError("Validated Charge Move proposal must include a witness.")
    scenario = _charge._battlefield_scenario(state)
    unit_placement = charge_movement_placement(
        scenario=scenario, unit_instance_id=proposal.unit_instance_id
    )
    resolution = _charge.resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=proposal.charge_target_unit_instance_ids,
        maximum_distance_inches=budget.maximum_distance_inches,
        take_to_the_skies=flight_selection_for_charge(state),
        path_witness=proposal.witness,
        unit_persisting_effects=tuple(state.persisting_effects_for_unit(proposal.unit_instance_id)),
        ability_index=ability_index,
    )
    violation_code = _charge._charge_move_violation_code(
        resolution=resolution,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=budget.maximum_distance_inches,
    )
    if violation_code is not None:
        return _charge._reject_invalid_charge_move_resolution(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            resolution=resolution,
            violation_code=violation_code,
            message=_charge._charge_move_invalid_message(violation_code),
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Charge Move proposal requires battlefield_state.")
    state.replace_battlefield_state(
        battlefield_with_charge_placement(battlefield_state, resolution.attempted_placement)
    )
    state.replace_charge_phase_state(
        charge_state.with_charge_move_resolved(
            proposal.unit_instance_id,
            selected_target_unit_instance_ids=resolution.selected_target_unit_instance_ids,
        )
    )
    effect = _charge._record_fights_first_effect_if_needed(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        proposal_request=proposal_request,
        result=result,
        unit_instance_id=proposal.unit_instance_id,
    )
    payload = _charge._charge_move_completed_payload(
        state=state,
        result=result,
        proposal_request=proposal_request,
        proposal_validation=proposal_validation,
        resolution=resolution,
        transition_batch=transition_batch,
        persisting_effect=effect,
    )
    record_move_completion_event(
        state=state, decisions=decisions, event_type="charge_move_completed", payload=payload
    )
    return None


__all__ = (
    "_apply_charge_move_proposal_decision",
    "_request_charge_move_proposal_retry",
    "invalid_charge_move_proposal_status",
    "request_charge_move_proposal",
)
