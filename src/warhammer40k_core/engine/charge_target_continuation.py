"""Charge owns target eligibility and continuation; P04 owns replacement choices."""

from __future__ import annotations

import hashlib
from itertools import combinations
from typing import TYPE_CHECKING

from warhammer40k_core.engine.charge_budget_value import ChargeMovementBudget
from warhammer40k_core.engine.charge_movement_budget import current_charge_movement_budget
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState, ChargeTargetSelection
from warhammer40k_core.engine.charge_required_targets import charge_target_constraints_satisfied
from warhammer40k_core.engine.charge_targets import charge_target_candidates
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.target_replacement import (
    SELECT_TARGET_REPLACEMENT_DECISION_TYPE,
    TargetReplacementContext,
    TargetReplacementOption,
    replacement_request,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_charge_2026_09 import (
    CHARGE_TARGET_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler

SELECT_CHARGE_TARGETS_DECISION_TYPE = "select_charge_targets"
DECLINE_CHARGE_TARGETS_OPTION_ID = "decline_charge_targets"


def is_charge_target_replacement_request(*, state: GameState, request: DecisionRequest) -> bool:
    """Bind shared choices to their action, including during a Shooting interruption."""
    phase = state.charge_phase_state
    if (
        state.current_battle_phase is not BattlePhase.CHARGE
        or state.out_of_phase_shooting_state is not None
        or phase is None
    ):
        return False
    distance = phase.move_pending_distance_state()
    return (
        distance is not None
        and request.decision_type == SELECT_TARGET_REPLACEMENT_DECISION_TYPE
        and isinstance(request.payload, dict)
        and request.payload.get("action_id") == distance.roll_result.request.request_id
    )


def pending_charge(state: GameState) -> ChargePhaseState:
    phase = state.charge_phase_state
    if (
        phase is None
        or phase.active_selection is None
        or phase.move_pending_distance_state() is None
        or state.current_battle_phase is not BattlePhase.CHARGE
        or phase.active_player_id != state.active_player_id
        or phase.battle_round != state.battle_round
    ):
        raise GameLifecycleError("Charge continuation requires its current rolled action.")
    return phase


def current_charge_targets(
    *,
    state: GameState,
    handler: ChargePhaseHandler,
) -> tuple[ChargeMovementBudget, dict[str, float]]:
    phase = pending_charge(state)
    distance = phase.move_pending_distance_state()
    if distance is None:
        raise GameLifecycleError("Charge continuation lost its rolled action.")
    roll = distance.roll_result
    budget = current_charge_movement_budget(
        state=state,
        request=roll.request,
        roll_state=roll.roll_state,
        ability_index=handler.ability_index_for_player(phase.active_player_id),
        runtime_modifier_registry=handler.runtime_modifier_registry,
    )
    ruleset = handler.ruleset_descriptor
    if ruleset is None:
        raise GameLifecycleError("Charge continuation requires its ruleset descriptor.")
    targets = {
        candidate.target_unit_instance_id: candidate.closest_distance_inches
        for candidate in charge_target_candidates(
            state=state,
            unit_instance_id=roll.request.unit_instance_id,
            ruleset_descriptor=ruleset,
            charge_target_restriction_hooks=handler.charge_target_restriction_hooks,
        )
        if candidate.is_legal
        and candidate.closest_distance_inches <= budget.maximum_distance_inches
    }
    return budget, targets


def legal_charge_target_sets(
    *, state: GameState, target_ids: tuple[str, ...]
) -> tuple[tuple[str, ...], ...]:
    phase = pending_charge(state)
    if phase.active_selection is None:
        raise GameLifecycleError("Charge continuation lost its active selection.")
    return tuple(
        subset
        for count in range(1, len(target_ids) + 1)
        for subset in combinations(sorted(target_ids), count)
        if charge_target_constraints_satisfied(
            state=state,
            unit_instance_id=phase.active_selection.unit_instance_id,
            candidate_target_unit_instance_ids=subset,
        )
    )


def charge_target_selection_request(
    *,
    state: GameState,
    request_id: str,
    budget: ChargeMovementBudget,
    reachable: dict[str, float],
) -> DecisionRequest | None:
    """No legal nonempty target set means a failed continuation, not a choice."""
    phase = pending_charge(state)
    distance = phase.move_pending_distance_state()
    if distance is None:
        raise GameLifecycleError("Charge continuation lost its rolled action.")
    roll = distance.roll_result
    target_sets = legal_charge_target_sets(state=state, target_ids=tuple(reachable))
    if not target_sets:
        return None
    payload = validate_json_value(
        {
            "source_rule_id": CHARGE_TARGET_SOURCE_ID,
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "action_id": roll.request.request_id,
            "unit_instance_id": roll.request.unit_instance_id,
            "charge_roll": roll.to_payload(),
            "movement_budget": budget.to_payload(),
            "reachable_target_distances_inches": reachable,
            "charge_target_authority_sha256": state.physical_proposal_context_hash(),
        }
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_CHARGE_TARGETS_DECISION_TYPE,
        actor_id=phase.active_player_id,
        payload=payload,
        options=(
            *(
                DecisionOption(
                    option_id=f"charge-targets:{index:04d}",
                    label=", ".join(targets),
                    payload={"context": payload, "target_ids": list(targets)},
                )
                for index, targets in enumerate(target_sets)
            ),
            *(
                (
                    DecisionOption(
                        option_id=DECLINE_CHARGE_TARGETS_OPTION_ID,
                        label="Do not make a Charge move",
                        payload={"context": payload, "target_ids": None},
                    ),
                )
                if charge_target_constraints_satisfied(
                    state=state,
                    unit_instance_id=roll.request.unit_instance_id,
                    candidate_target_unit_instance_ids=(),
                )
                else ()
            ),
        ),
    )


def request_charge_targets(
    *,
    state: GameState,
    decisions: DecisionController,
    budget: ChargeMovementBudget,
    reachable: dict[str, float],
) -> LifecycleStatus:
    request = charge_target_selection_request(
        state=state,
        request_id=state.next_decision_request_id(),
        budget=budget,
        reachable=reachable,
    )
    if request is None:
        phase = pending_charge(state)
        distance = phase.move_pending_distance_state()
        if distance is None:
            raise GameLifecycleError("Failed Charge continuation lost its rolled action.")
        roll = distance.roll_result
        state.replace_charge_phase_state(
            phase.with_charge_move_resolved(roll.request.unit_instance_id)
        )
        payload = validate_json_value(
            {
                "source_rule_id": CHARGE_TARGET_SOURCE_ID,
                "action_id": roll.request.request_id,
                "unit_instance_id": roll.request.unit_instance_id,
                "charge_roll": roll.to_payload(),
                "movement_budget": budget.to_payload(),
                "reachable_target_distances_inches": reachable,
                "reason": "no_legal_charge_target_sets",
            }
        )
        decisions.event_log.append("charge_continuation_failed", payload)
        return LifecycleStatus.advanced(stage=state.stage, payload=payload)
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.CHARGE.value,
            "phase_body_status": "charge_target_selection_required",
        },
    )


def record_charge_target_selection(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    target_ids: tuple[str, ...] | None,
) -> None:
    phase = pending_charge(state)
    if phase.active_selection is None:
        raise GameLifecycleError("Charge continuation lost its active selection.")
    unit_id = phase.active_selection.unit_instance_id
    if target_ids is None:
        state.replace_charge_phase_state(phase.with_charge_move_resolved(unit_id))
    else:
        state.replace_charge_phase_state(
            phase.with_target_selection(
                ChargeTargetSelection(
                    request_id=request.request_id,
                    result_id=result.result_id,
                    unit_instance_id=unit_id,
                    target_ids=target_ids,
                )
            )
        )
    decisions.event_log.append(
        "charge_targets_selected",
        validate_json_value(
            {
                "unit_instance_id": unit_id,
                "request_id": request.request_id,
                "result_id": result.result_id,
                "target_ids": None if target_ids is None else list(target_ids),
            }
        ),
    )


def next_charge_target_replacement(
    *,
    state: GameState,
    handler: ChargePhaseHandler,
) -> TargetReplacementContext | None:
    phase = pending_charge(state)
    selected = phase.target_selection
    if selected is None:
        return None
    budget, reachable = current_charge_targets(state=state, handler=handler)
    invalid = tuple(target for target in selected.target_ids if target not in reachable)
    if not charge_target_constraints_satisfied(
        state=state,
        unit_instance_id=selected.unit_instance_id,
        candidate_target_unit_instance_ids=selected.target_ids,
    ):
        invalid = selected.target_ids
    if not invalid:
        return None
    distance = phase.move_pending_distance_state()
    if distance is None:
        raise GameLifecycleError("Charge continuation lost its rolled action.")
    commitment = validate_json_value(
        {
            "spatial_context": state.physical_proposal_context_hash(),
            "budget": budget.to_payload(),
            "reachable": reachable,
            "selection": selected.to_payload(),
            "roll": distance.roll_result.to_payload(),
        }
    )
    return TargetReplacementContext(
        action_id=distance.roll_result.request.request_id,
        selection_id=selected.result_id,
        actor_id=phase.active_player_id,
        source_unit_instance_id=selected.unit_instance_id,
        original_target_ids=selected.target_ids,
        invalid_target_ids=invalid,
        source_context_hash=hashlib.sha256(canonical_json(commitment).encode()).hexdigest(),
        options=tuple(
            TargetReplacementOption(f"charge-replacement:{index:04d}", targets)
            for index, targets in enumerate(
                legal_charge_target_sets(state=state, target_ids=tuple(reachable))
            )
        ),
    )


def continue_charge_move(
    *,
    state: GameState,
    decisions: DecisionController,
    handler: ChargePhaseHandler,
) -> LifecycleStatus:
    from warhammer40k_core.engine.phases.charge_proposal_flow import request_charge_move_proposal

    phase = pending_charge(state)
    budget, reachable = current_charge_targets(state=state, handler=handler)
    if phase.target_selection is None:
        return request_charge_targets(
            state=state, decisions=decisions, budget=budget, reachable=reachable
        )
    replacement = next_charge_target_replacement(state=state, handler=handler)
    if replacement is not None:
        request = replacement_request(
            request_id=state.next_decision_request_id(), context=replacement
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "charge_target_replacement_required",
            },
        )
    distance = phase.move_pending_distance_state()
    if distance is None:
        raise GameLifecycleError("Charge continuation lost its rolled action.")
    return request_charge_move_proposal(
        state=state,
        decisions=decisions,
        charge_state=phase,
        roll_result=distance.roll_result,
        budget=budget,
        reachable=reachable,
    )


def refresh_pending_charge_move(
    *,
    state: GameState,
    decisions: DecisionController,
    handler: ChargePhaseHandler,
) -> LifecycleStatus | None:
    """An advance withdraws stale movement authority; a stale submission never pops it."""
    from warhammer40k_core.engine.movement_proposals import (
        MOVEMENT_PROPOSAL_DECISION_TYPE,
        MovementProposalRequest,
        ProposalKind,
    )

    phase = state.charge_phase_state
    if (
        state.current_battle_phase is not BattlePhase.CHARGE
        or phase is None
        or phase.active_selection is None
        or not decisions.queue.pending_requests
    ):
        return None
    request = decisions.queue.peek_next()
    if request.decision_type == SELECT_CHARGE_TARGETS_DECISION_TYPE:
        budget, reachable = current_charge_targets(state=state, handler=handler)
        if (
            charge_target_selection_request(
                state=state, request_id=request.request_id, budget=budget, reachable=reachable
            )
            == request
        ):
            return None
    elif phase.target_selection is None:
        return None
    elif request.decision_type == SELECT_TARGET_REPLACEMENT_DECISION_TYPE:
        context = TargetReplacementContext.from_payload(request.payload)
        distance = phase.move_pending_distance_state()
        if distance is None or context.action_id != distance.roll_result.request.request_id:
            return None
        current = next_charge_target_replacement(state=state, handler=handler)
        if (
            current is not None
            and replacement_request(request_id=request.request_id, context=current) == request
        ):
            return None
    elif request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        if proposal.proposal_kind is not ProposalKind.CHARGE_MOVE:
            return None
        context_payload = proposal.context
        budget, reachable = current_charge_targets(state=state, handler=handler)
        if (
            context_payload is not None
            and context_payload.get("movement_budget") == budget.to_payload()
            and context_payload.get("reachable_target_distances_inches") == reachable
            and proposal.spatial_context_hash == state.physical_proposal_context_hash()
            and next_charge_target_replacement(state=state, handler=handler) is None
        ):
            return None
    else:
        return None
    decisions.queue.remove_by_id(request.request_id)
    decisions.event_log.append(
        "charge_movement_request_withdrawn",
        {
            "request_id": request.request_id,
            "unit_instance_id": phase.active_selection.unit_instance_id,
            "target_selection_result_id": (
                None if phase.target_selection is None else phase.target_selection.result_id
            ),
            "reason": "charge_movement_context_changed",
        },
    )
    return continue_charge_move(state=state, decisions=decisions, handler=handler)
