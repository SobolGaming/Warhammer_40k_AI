from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    selected_target_charge_constraint_for_unit,
)
from warhammer40k_core.engine.charge_declaration import (
    ChargeRollRequest,
    ChargeRollRequestPayload,
    ChargeRollResult,
    phase15a_charge_roll_payload,
)
from warhammer40k_core.engine.charge_movement_budget import current_charge_movement_budget
from warhammer40k_core.engine.charge_phase_state import ChargingUnitSelection
from warhammer40k_core.engine.charge_required_targets import (
    charge_target_constraints_satisfied as _charge_target_constraints_satisfied,
)
from warhammer40k_core.engine.charge_roll_permissions import (
    charge_reroll_permission_for_unit as _charge_reroll_permission_for_unit,
)
from warhammer40k_core.engine.charge_roll_reroll_requests import build_charge_roll_reroll_request
from warhammer40k_core.engine.charge_target_continuation import request_charge_targets
from warhammer40k_core.engine.command_reroll_windows import request_command_reroll_if_available
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mutation_decision_authority import validate_mutation_decision_closure
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases import charge as _charge
from warhammer40k_core.engine.phases import charge_modifier_ignore as _modifier_ignore
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def pending_charge_roll(
    *, state: GameState, decisions: DecisionController
) -> tuple[ChargeRollRequest, DiceRollState]:
    phase = state.charge_phase_state
    if (
        phase is None
        or phase.active_selection is None
        or state.current_battle_phase is not BattlePhase.CHARGE
        or phase.active_selection.player_id != state.active_player_id
    ):
        raise GameLifecycleError("Pending Charge roll requires an active selection.")
    selection = phase.active_selection
    matches: list[tuple[ChargeRollRequest, DiceRollState]] = []
    for index, event in enumerate(decisions.event_log.records):
        if event.event_type != "charge_roll_started":
            continue
        payload = _charge._decision_payload_object(event.payload)
        request = ChargeRollRequest.from_payload(
            cast(
                ChargeRollRequestPayload,
                _charge._payload_object(payload, key="charge_roll_request"),
            )
        )
        if request.source_decision_result_id != selection.result_id:
            continue
        record = validate_mutation_decision_closure(
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            mutation_index=index,
            request_id=selection.request_id,
            result_id=selection.result_id,
        )
        if (
            request.game_id != state.game_id
            or request.battle_round != state.battle_round
            or request.player_id != selection.player_id
            or request.unit_instance_id != selection.unit_instance_id
            or request.source_decision_request_id != selection.request_id
            or request.request_id != f"charge-roll:{selection.result_id}"
            or record.request.decision_type != "select_charging_unit"
            or not isinstance(record.result.payload, dict)
            or record.result.payload.get("unit_instance_id") != selection.unit_instance_id
            or record.result.actor_id != selection.player_id
        ):
            raise GameLifecycleError("Pending Charge roll selection authority drift.")
        roll = DiceRollState.from_payload(
            cast(DiceRollStatePayload, _charge._payload_object(payload, key="charge_roll_state"))
        )
        if roll.original_result.spec != request.spec or roll.rerolls:
            raise GameLifecycleError("Pending Charge original roll drift.")
        dice_events = [
            e
            for e in decisions.event_log.records[:index]
            if e.event_type == "dice_rolled" and e.payload == roll.original_result.to_payload()
        ]
        if len(dice_events) != 1:
            raise GameLifecycleError("Pending Charge roll has no unique dice authority.")
        matches.append((request, roll))
    if len(matches) != 1:
        raise GameLifecycleError("Pending Charge requires exactly one started roll.")
    return matches[0]


def continue_charge_roll(
    *, state: GameState, decisions: DecisionController, handler: _charge.ChargePhaseHandler
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.dice_roll_history import latest_reroll_state_for_original_roll

    roll_request, initial = pending_charge_roll(state=state, decisions=decisions)
    roll = latest_reroll_state_for_original_roll(
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        original_state=initial,
    )
    status = request_command_reroll_if_available(
        state=state,
        decisions=decisions,
        roll_state=roll,
        affected_unit_instance_id=roll_request.unit_instance_id,
        source_phase=BattlePhase.CHARGE,
        stratagem_index=handler.stratagem_index,
        stratagem_cost_modifier_registry=handler.stratagem_cost_modifier_registry,
        phase_body_status="charge_command_reroll_pending",
        trigger_context_extra={"charge_action_id": roll_request.request_id},
    )
    if status is not None:
        return status
    phase = state.charge_phase_state
    if phase is None or phase.active_selection is None:
        raise GameLifecycleError("Charge continuation selection is missing.")
    return _resolve_charge_roll_state(
        state=state,
        decisions=decisions,
        selection=phase.active_selection,
        roll_request=roll_request,
        roll_state=roll,
        ruleset_descriptor=_charge._ruleset_descriptor_for_handler(handler),
        ability_index=handler.ability_index_for_player(roll_request.player_id),
        runtime_modifier_registry=handler.runtime_modifier_registry,
        charge_target_restriction_hooks=handler.charge_target_restriction_hooks,
    )


def _resolve_charge_roll(
    *,
    state: GameState,
    selection: ChargingUnitSelection,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    unit = _charge._unit_for_selection(state=state, selection=selection)
    roll_modifiers = _modifier_ignore.charge_roll_modifiers_for_unit(
        state=state,
        ability_index=ability_index,
        unit=unit,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    roll_request = ChargeRollRequest(
        request_id=f"charge-roll:{selection.result_id}",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=selection.player_id,
        unit_instance_id=selection.unit_instance_id,
        source_decision_request_id=selection.request_id,
        source_decision_result_id=selection.result_id,
        roll_modifiers=roll_modifiers,
    )
    legal_target_ids = _charge.legal_charge_target_unit_instance_ids(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    reroll_permission = _charge_reroll_permission_for_unit(
        state=state,
        player_id=selection.player_id,
        unit_instance_id=selection.unit_instance_id,
        ability_index=ability_index,
    )
    selected_target_constraint = selected_target_charge_constraint_for_unit(
        state=state,
        unit_instance_id=selection.unit_instance_id,
    )
    if not _charge_target_constraints_satisfied(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        candidate_target_unit_instance_ids=legal_target_ids,
    ):
        raise GameLifecycleError(
            "Required Charge target constraint became unavailable after declaration."
        )
    roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
        roll_request.spec
    )
    decisions.event_log.append(
        "charge_roll_started",
        validate_json_value(
            {
                "charge_roll_request": roll_request.to_payload(),
                "charge_roll_state": roll_state.to_payload(),
            }
        ),
    )
    if reroll_permission is not None:
        reroll_request = build_charge_roll_reroll_request(
            state=state,
            decisions=decisions,
            roll_request=roll_request,
            roll_state=roll_state,
            permission=reroll_permission,
            selected_target_constraint=selected_target_constraint,
            legal_target_unit_instance_ids=legal_target_ids,
        )
        decisions.request_decision(reroll_request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=reroll_request,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "charge_roll_reroll_pending",
                "battle_round": state.battle_round,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
            },
        )
    return None


def _resolve_charge_roll_state(
    *,
    state: GameState,
    selection: ChargingUnitSelection,
    decisions: DecisionController,
    roll_request: ChargeRollRequest,
    roll_state: DiceRollState,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    budget = current_charge_movement_budget(
        state=state,
        request=roll_request,
        roll_state=roll_state,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    roll_request = replace(roll_request, roll_modifiers=budget.modified_roll.modifiers)
    reachable_distances = _charge._reachable_charge_target_distances(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        maximum_distance_inches=budget.maximum_distance_inches,
        ruleset_descriptor=ruleset_descriptor,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if not _charge_target_constraints_satisfied(
        state=state,
        unit_instance_id=selection.unit_instance_id,
        candidate_target_unit_instance_ids=tuple(reachable_distances),
    ):
        reachable_distances = {}
    roll_result = ChargeRollResult.from_roll_state(
        request=roll_request,
        roll_state=roll_state,
        reachable_target_distances_inches=reachable_distances,
        movement_budget=budget,
    )
    charge_state = state.charge_phase_state
    if charge_state is None:
        raise GameLifecycleError("Charge roll requires charge_phase_state.")
    state.replace_charge_phase_state(charge_state.with_charge_roll_result(roll_result))
    decisions.event_log.append(
        "charge_roll_resolved",
        phase15a_charge_roll_payload(roll_result=roll_result),
    )
    if not roll_result.move_available:
        decisions.event_log.append(
            "charge_no_move_possible",
            phase15a_charge_roll_payload(roll_result=roll_result),
        )
        return None
    decisions.event_log.append(
        "charge_move_required",
        phase15a_charge_roll_payload(roll_result=roll_result),
    )
    return request_charge_targets(
        state=state, decisions=decisions, budget=budget, reachable=reachable_distances
    )


def _apply_charge_roll_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    charge_state = state.charge_phase_state
    if charge_state is None or charge_state.active_selection is None:
        raise GameLifecycleError("Charge reroll requires active charge selection.")
    selection = charge_state.active_selection
    if result.actor_id != selection.player_id:
        raise GameLifecycleError("Charge reroll actor must match charging player.")
    record = decisions.record_for_result(result)
    request_payload = _charge._decision_payload_object(record.request.payload)
    context_payload = _charge._payload_object(request_payload, key="charge_context")
    unit_instance_id = _charge._payload_string(context_payload, key="unit_instance_id")
    if unit_instance_id != selection.unit_instance_id:
        raise GameLifecycleError("Charge reroll unit must match active charge selection.")
    roll_request_payload = _charge._payload_object(context_payload, key="charge_roll_request")
    initial_roll_payload = _charge._payload_object(context_payload, key="charge_roll_state")
    roll_request = ChargeRollRequest.from_payload(
        cast(ChargeRollRequestPayload, roll_request_payload)
    )
    if roll_request.unit_instance_id != selection.unit_instance_id:
        raise GameLifecycleError("Charge reroll request unit drift.")
    initial_roll_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, initial_roll_payload)
    )
    DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
    ).resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )
    return None


__all__ = (
    "_apply_charge_roll_reroll_decision",
    "_resolve_charge_roll",
    "_resolve_charge_roll_state",
    "continue_charge_roll",
    "pending_charge_roll",
)
