from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import resolve_faction_resource_refund_roll
from warhammer40k_core.engine.move_ability_choices import choice_fields
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.surge_choices import surge_choice_context
from warhammer40k_core.engine.take_to_the_skies import flight_selection
from warhammer40k_core.engine.triggered_movement_options import (
    triggered_movement_unit_selection_options as _triggered_movement_unit_selection_options,
)
from warhammer40k_core.engine.triggered_movement_physical_authority import (
    triggered_movement_placement,
    triggered_movement_unit_has_placed_living_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


# pyright: reportPrivateUsage=false
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND,
    TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
    TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND,
    TriggeredMovementDescriptor,
    TriggeredMovementDescriptorPayload,
    TriggeredMovementEligibleUnit,
    TriggeredMovementEligibleUnitPayload,
    TriggeredMovementKind,
    _battlefield_scenario,
    _decision_payload_object,
    _eligible_unit_by_id,
    _eligible_units_from_request_payload,
    _payload_optional_bool,
    _payload_string,
    _triggered_movement_unit_selection_declined_payload,
    _validate_eligible_units,
    _validate_identifier,
    _validate_reaction_window_matches_state,
    _validate_triggered_movement_state_ready,
    is_triggered_movement_distance_reroll_request,
)


def triggered_movement_unit_selection_request(
    *,
    state: GameState,
    player_id: str,
    descriptor: TriggeredMovementDescriptor,
    eligible_units: tuple[TriggeredMovementEligibleUnit, ...],
    decisions: DecisionController | None = None,
) -> DecisionRequest:
    _validate_triggered_movement_state_ready(state)
    actor_id = _validate_identifier("player_id", player_id)
    if type(descriptor) is not TriggeredMovementDescriptor:
        raise GameLifecycleError("Triggered movement unit selection requires a descriptor.")
    _validate_reaction_window_matches_state(state=state, descriptor=descriptor)
    from warhammer40k_core.engine.surge_authority import require_surge_trigger

    require_surge_trigger(state=state, decisions=decisions, descriptor=descriptor)
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Triggered movement requires active_player_id.")
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Triggered movement requires current battle phase.")
    unit_options = _eligible_units_after_normal_move_restriction(
        state=state,
        player_id=actor_id,
        descriptor=descriptor,
        eligible_units=_validate_eligible_units(
            tuple(
                replace(
                    unit,
                    unit_instance_id=rules_unit_view_by_id(
                        state=state, unit_instance_id=unit.unit_instance_id
                    ).unit_instance_id,
                )
                for unit in eligible_units
            )
        ),
    )
    if not unit_options and not descriptor.optional:
        raise GameLifecycleError(
            "Mandatory triggered movement unit selection requires an eligible unit."
        )
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
        actor_id=actor_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "current_phase": current_phase.value,
            "player_id": actor_id,
            "descriptor": validate_json_value(descriptor.to_payload()),
            "triggered_movement_kind": descriptor.movement_kind.value,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_timing": validate_json_value(descriptor.trigger_timing.to_payload()),
            "requires_movement_proposal": True,
            "movement_phase_action": TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
            "eligible_units": [validate_json_value(unit.to_payload()) for unit in unit_options],
        },
        options=_triggered_movement_unit_selection_options(
            state=state,
            descriptor=descriptor,
            eligible_units=unit_options,
        ),
    )


def _eligible_units_after_normal_move_restriction(
    *,
    state: GameState,
    player_id: str,
    descriptor: TriggeredMovementDescriptor,
    eligible_units: tuple[TriggeredMovementEligibleUnit, ...],
) -> tuple[TriggeredMovementEligibleUnit, ...]:
    from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
    from warhammer40k_core.engine.movement_locks import movement_lock_reason
    from warhammer40k_core.engine.surge_movement import surge_ineligibility

    living_source_units = tuple(
        unit
        for unit in eligible_units
        if (
            descriptor.movement_kind is TriggeredMovementKind.SURGE
            or large_model_activity_reason(
                state, unit.unit_instance_id, descriptor.movement_mode.value
            )
            is None
        )
        and movement_lock_reason(state, unit.unit_instance_id) is None
        and (
            descriptor.movement_kind is not TriggeredMovementKind.SURGE
            or surge_ineligibility(state, unit.unit_instance_id) is None
        )
        and triggered_movement_unit_has_placed_living_source(
            state=state,
            unit_instance_id=unit.unit_instance_id,
        )
    )
    if (
        descriptor.movement_mode is not MovementMode.NORMAL
        or descriptor.movement_kind is TriggeredMovementKind.SURGE
    ):
        return living_source_units
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Triggered movement requires current battle phase.")
    return tuple(
        unit
        for unit in living_source_units
        if not state.normal_move_states_for_unit_phase(
            player_id=player_id,
            battle_round=state.battle_round,
            phase=current_phase,
            unit_instance_id=unit.unit_instance_id,
        )
    )


def _apply_triggered_movement_unit_selection_decision(  # pyright: ignore[reportUnusedFunction]
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    descriptor: TriggeredMovementDescriptor,
    request_payload: dict[str, JsonValue],
) -> LifecycleStatus | None:
    payload = _decision_payload_object(result.payload)
    player_id = _payload_string(request_payload, "player_id")
    actor_id = _validate_identifier("Triggered movement result actor_id", result.actor_id)
    if actor_id != player_id:
        raise GameLifecycleError("Triggered movement unit selection actor drift.")
    eligible_units = _eligible_units_from_request_payload(request_payload)
    if _payload_optional_bool(payload, "declined"):
        if result.selected_option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID:
            raise GameLifecycleError("Declined triggered movement result option drift.")
        if not descriptor.optional:
            raise GameLifecycleError("Mandatory triggered movement cannot be declined.")
        decisions.event_log.append(
            "triggered_movement_declined",
            _triggered_movement_unit_selection_declined_payload(
                state=state,
                result=result,
                descriptor=descriptor,
                eligible_units=eligible_units,
            ),
        )
        return None
    unit_instance_id = _payload_string(payload, "unit_instance_id")
    selected_unit = _eligible_unit_by_id(eligible_units, unit_instance_id=unit_instance_id)
    scenario = _battlefield_scenario(state)
    unit_placement = triggered_movement_placement(
        scenario=scenario, unit_instance_id=unit_instance_id
    )
    if actor_id != unit_placement.player_id:
        raise GameLifecycleError("Triggered movement actor must own the selected unit.")
    if payload.get("eligible_unit") != selected_unit.to_payload():
        raise GameLifecycleError("Triggered movement eligible unit payload drift.")
    from warhammer40k_core.engine.active_player_scopes import begin_reactive_move

    begin_reactive_move(
        state=state,
        decisions=decisions,
        result=result,
        unit_instance_id=unit_instance_id,
        source_rule_id=descriptor.source_rule_id,
    )
    decision_effect = _record_triggered_movement_decision_effect_if_needed(
        state=state,
        decisions=decisions,
        selected_unit=selected_unit,
        result=result,
        descriptor=descriptor,
    )
    if selected_unit.distance_reroll_permission is not None:
        roll_state = selected_unit.distance_roll_state
        if roll_state is None:
            raise GameLifecycleError("Triggered movement reroll distance roll is missing.")
        reroll_request = DiceRollManager(
            state.game_id,
            event_log=decisions.event_log,
        ).build_reroll_request(
            roll_state,
            request_id=state.next_decision_request_id(),
            actor_id=actor_id,
            permission=selected_unit.distance_reroll_permission,
            extra_payload={
                **surge_choice_context(payload, descriptor),
                "context_kind": TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND,
                "descriptor": validate_json_value(descriptor.to_payload()),
                "selected_unit": validate_json_value(selected_unit.to_payload()),
                "selection_request_id": result.request_id,
                "selection_result_id": result.result_id,
                "selection_option_id": result.selected_option_id,
                **choice_fields(payload),
                "take_to_the_skies": flight_selection(payload)
                if descriptor.movement_mode is MovementMode.NORMAL
                else False,
            },
        )
        decisions.request_decision(reroll_request)
        decisions.event_log.append(
            "triggered_movement_distance_reroll_requested",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": descriptor.trigger_timing.phase.value,
                    "player_id": actor_id,
                    "unit_instance_id": unit_instance_id,
                    "selection_request_id": result.request_id,
                    "selection_result_id": result.result_id,
                    "reroll_request_id": reroll_request.request_id,
                    "decision_persisting_effect": (
                        None if decision_effect is None else decision_effect.to_payload()
                    ),
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=reroll_request,
            payload={
                "phase": descriptor.trigger_timing.phase.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "unit_instance_id": unit_instance_id,
                "decision_type": DICE_REROLL_DECISION_TYPE,
                "phase_body_status": "triggered_movement_distance_reroll_pending",
            },
        )
    request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=descriptor.trigger_timing.phase.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=ProposalKind.SURGE_MOVE,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action=TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
        context={
            **surge_choice_context(payload, descriptor),
            "context_kind": TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND,
            "descriptor": validate_json_value(descriptor.to_payload()),
            "selected_unit": validate_json_value(selected_unit.to_payload()),
            "selection_request_id": result.request_id,
            "selection_result_id": result.result_id,
            "selection_option_id": result.selected_option_id,
            **choice_fields(payload),
            "take_to_the_skies": flight_selection(payload)
            if descriptor.movement_mode is MovementMode.NORMAL
            else False,
        },
    ).to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "triggered_movement_unit_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": descriptor.trigger_timing.phase.value,
            "unit_instance_id": unit_instance_id,
            "triggered_movement_kind": descriptor.movement_kind.value,
            "source_rule_id": descriptor.source_rule_id,
            "trigger_timing": descriptor.trigger_timing.to_payload(),
            "request_id": result.request_id,
            "result_id": result.result_id,
            "proposal_request_id": request.request_id,
            "eligible_unit": selected_unit.to_payload(),
            "decision_persisting_effect": (
                None if decision_effect is None else decision_effect.to_payload()
            ),
            "phase_body_status": "triggered_movement_proposal_pending",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": descriptor.trigger_timing.phase.value,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "unit_instance_id": unit_instance_id,
            "decision_type": MOVEMENT_PROPOSAL_DECISION_TYPE,
            "phase_body_status": "triggered_movement_proposal_pending",
        },
    )


def _record_triggered_movement_decision_effect_if_needed(
    *,
    state: GameState,
    decisions: DecisionController,
    selected_unit: TriggeredMovementEligibleUnit,
    result: DecisionResult,
    descriptor: TriggeredMovementDescriptor,
) -> PersistingEffect | None:
    if type(selected_unit) is not TriggeredMovementEligibleUnit:
        raise GameLifecycleError("Triggered movement decision effect requires an eligible unit.")
    if type(descriptor) is not TriggeredMovementDescriptor:
        raise GameLifecycleError("Triggered movement decision effect requires a descriptor.")
    if selected_unit.decision_effect_payload is None:
        return None
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Triggered movement decision effect requires a battle phase.")
    effect = PersistingEffect(
        effect_id=f"{result.result_id}:{selected_unit.hook_id}:decision",
        source_rule_id=selected_unit.source_id,
        owner_player_id=_validate_identifier("actor_id", result.actor_id),
        target_unit_instance_ids=(selected_unit.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind(current_phase.value),
        expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
        effect_payload=selected_unit.decision_effect_payload,
    )
    state.record_persisting_effect(effect)
    resolve_faction_resource_refund_roll(
        state=state,
        decisions=decisions,
        spend_effect=effect,
    )
    return effect


def apply_triggered_movement_distance_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_triggered_movement_distance_reroll_request(request):
        raise GameLifecycleError("Triggered movement distance reroll request is required.")
    payload = _decision_payload_object(request.payload)
    raw_descriptor = payload.get("descriptor")
    raw_selected_unit = payload.get("selected_unit")
    if not isinstance(raw_descriptor, dict) or not isinstance(raw_selected_unit, dict):
        raise GameLifecycleError("Triggered movement reroll context is malformed.")
    descriptor = TriggeredMovementDescriptor.from_payload(
        cast(TriggeredMovementDescriptorPayload, raw_descriptor)
    )
    selected_unit = TriggeredMovementEligibleUnit.from_payload(
        cast(TriggeredMovementEligibleUnitPayload, raw_selected_unit)
    )
    initial_roll_state = selected_unit.distance_roll_state
    if initial_roll_state is None or selected_unit.distance_reroll_permission is None:
        raise GameLifecycleError("Triggered movement reroll source context is missing.")
    rerolled_state = DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
    ).resolve_reroll(
        initial_roll_state,
        request=request,
        result=result,
        record_decision=False,
    )
    updated_descriptor = replace(
        descriptor,
        max_distance_inches=float(
            rerolled_state.current_total + selected_unit.distance_roll_bonus_inches
        ),
    )
    selection_request_id = _payload_string(payload, "selection_request_id")
    selection_result_id = _payload_string(payload, "selection_result_id")
    selection_option_id = _payload_string(payload, "selection_option_id")
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=_validate_identifier("actor_id", result.actor_id),
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=updated_descriptor.trigger_timing.phase.value,
        unit_instance_id=selected_unit.unit_instance_id,
        proposal_kind=ProposalKind.SURGE_MOVE,
        source_decision_request_id=selection_request_id,
        source_decision_result_id=selection_result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        movement_phase_action=TRIGGERED_MOVEMENT_PROPOSAL_ACTION,
        context={
            **surge_choice_context(payload, descriptor),
            "context_kind": TRIGGERED_MOVEMENT_PROPOSAL_CONTEXT_KIND,
            "descriptor": validate_json_value(updated_descriptor.to_payload()),
            "selected_unit": validate_json_value(selected_unit.to_payload()),
            "selection_request_id": selection_request_id,
            "selection_result_id": selection_result_id,
            "selection_option_id": selection_option_id,
            **choice_fields(payload),
            "take_to_the_skies": flight_selection(payload),
            "distance_reroll_request_id": request.request_id,
            "distance_reroll_result_id": result.result_id,
            "distance_roll_state": validate_json_value(rerolled_state.to_payload()),
        },
    ).to_decision_request()
    decisions.request_decision(proposal_request)
    decisions.event_log.append(
        "triggered_movement_distance_reroll_resolved",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": updated_descriptor.trigger_timing.phase.value,
                "player_id": result.actor_id,
                "unit_instance_id": selected_unit.unit_instance_id,
                "selection_request_id": selection_request_id,
                "selection_result_id": selection_result_id,
                "reroll_request_id": request.request_id,
                "reroll_result_id": result.result_id,
                "distance_roll_state": rerolled_state.to_payload(),
                "descriptor": updated_descriptor.to_payload(),
                "proposal_request_id": proposal_request.request_id,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=proposal_request,
        payload={
            "phase": updated_descriptor.trigger_timing.phase.value,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "unit_instance_id": selected_unit.unit_instance_id,
            "decision_type": MOVEMENT_PROPOSAL_DECISION_TYPE,
            "phase_body_status": "triggered_movement_proposal_pending",
        },
    )
