from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_move_completed_hooks import (
    apply_unit_move_completed_mortal_wound_feel_no_pain_decision,
    is_unit_move_completed_mortal_wound_feel_no_pain_request,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


MOVEMENT_PHASE_END_MORTAL_WOUNDS_SOURCE_KIND = "movement_phase_end_mortal_wounds"
MOVEMENT_PHASE_END_MORTAL_WOUNDS_ROLLED_EVENT = "movement_phase_end_mortal_wounds_rolled"
MOVEMENT_PHASE_END_MORTAL_WOUNDS_PENDING_EVENT = "movement_phase_end_mortal_wounds_pending"
MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT = "movement_phase_end_mortal_wounds_resolved"


def apply_movement_fnp_if_applicable(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None | Literal[False]:
    if is_movement_phase_end_mortal_wound_feel_no_pain_request(request):
        return apply_movement_phase_end_mortal_wound_feel_no_pain_decision(
            state=state,
            result=result,
            decisions=decisions,
        )
    if is_unit_move_completed_mortal_wound_feel_no_pain_request(request):
        return apply_unit_move_completed_mortal_wound_feel_no_pain_decision(
            state=state,
            result=result,
            decisions=decisions,
        )
    return False


def resolve_movement_phase_end_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("Movement phase-end mortal wounds require the Movement phase.")
    if state.active_player_id is None:
        raise GameLifecycleError("Movement phase-end mortal wounds require an active player.")
    processed_effect_ids = _processed_effect_ids(decisions)
    for effect in sorted(state.persisting_effects, key=lambda item: item.effect_id):
        if effect.effect_id in processed_effect_ids:
            continue
        payload = effect.effect_payload
        if not _is_current_movement_phase_end_mortal_wound_effect(
            state=state,
            effect=effect,
            payload=payload,
        ):
            continue
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement phase-end mortal wound effect payload drifted.")
        status = _resolve_effect(
            state=state,
            decisions=decisions,
            effect=effect,
            payload=payload,
        )
        if status is not None:
            return status
    return None


def apply_movement_phase_end_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Movement phase-end Feel No Pain requires DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Movement phase-end Feel No Pain requires DecisionController.")
    record = decisions.record_for_result(result)
    request = record.request
    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError("Movement phase-end Feel No Pain requires mortal wound context.")
    source_context = mortal_wound_feel_no_pain_source_context(request)
    if not isinstance(source_context, dict) or source_context.get("source_kind") != (
        MOVEMENT_PHASE_END_MORTAL_WOUNDS_SOURCE_KIND
    ):
        raise GameLifecycleError("Movement phase-end Feel No Pain source context is invalid.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=routed.request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": source_context["source_rule_id"],
                "effect_id": source_context["effect_id"],
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Movement phase-end Feel No Pain did not finish routing.")
    decisions.event_log.append(
        MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT,
        {
            **source_context,
            "mortal_application": routed.application.to_payload(),
            "feel_no_pain_result_id": result.result_id,
        },
    )
    return None


def is_movement_phase_end_mortal_wound_feel_no_pain_request(request: object) -> bool:
    if type(request) is not DecisionRequest:
        return False
    if not is_mortal_wound_feel_no_pain_request(request):
        return False
    source_context = mortal_wound_feel_no_pain_source_context(request)
    return isinstance(source_context, dict) and source_context.get("source_kind") == (
        MOVEMENT_PHASE_END_MORTAL_WOUNDS_SOURCE_KIND
    )


def _resolve_effect(
    *,
    state: GameState,
    decisions: DecisionController,
    effect: PersistingEffect,
    payload: dict[str, JsonValue],
) -> LifecycleStatus | None:
    phase_end_payload = payload.get("phase_end_mortal_wounds")
    if not isinstance(phase_end_payload, dict):
        raise GameLifecycleError("Movement phase-end mortal wound payload is missing.")
    if len(effect.target_unit_instance_ids) != 1:
        raise GameLifecycleError("Movement phase-end mortal wounds require one target unit.")
    target_unit_instance_id = effect.target_unit_instance_ids[0]
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    if rules_unit.owner_player_id != effect.owner_player_id:
        raise GameLifecycleError("Movement phase-end mortal wound effect owner drifted.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Movement phase-end mortal wounds require battlefield state.")
    model_ids = tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.alive_models()
            if state.battlefield_state.model_placement_or_none(model.model_instance_id) is not None
        )
    )
    success_value = _required_d6_value(phase_end_payload, "success_value")
    mortal_wounds_per_success = _required_positive_int(
        phase_end_payload,
        "mortal_wounds_per_success",
    )
    if (
        phase_end_payload.get("roll_expression") != "D6"
        or phase_end_payload.get("roll_count_scope") != "each_model_in_this_unit_at_phase_end"
    ):
        raise GameLifecycleError("Movement phase-end mortal wound roll semantics drifted.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    trigger_roll_payload: JsonValue = None
    success_count = 0
    if model_ids:
        roll_state = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=len(model_ids), sides=6),
                reason=f"Movement phase-end mortal wounds for {effect.source_rule_id}",
                roll_type="movement_phase_end_mortal_wounds.trigger",
                actor_id=effect.owner_player_id,
            )
        )
        success_count = sum(value == success_value for value in roll_state.current_values)
        trigger_roll_payload = validate_json_value(roll_state.to_payload())
    mortal_wounds = success_count * mortal_wounds_per_success
    source_context: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.MOVEMENT.value,
        "active_player_id": state.active_player_id,
        "source_kind": MOVEMENT_PHASE_END_MORTAL_WOUNDS_SOURCE_KIND,
        "effect_id": effect.effect_id,
        "source_rule_id": effect.source_rule_id,
        "target_unit_instance_id": rules_unit.unit_instance_id,
        "target_player_id": rules_unit.owner_player_id,
        "model_ids": list(model_ids),
        "success_value": success_value,
        "mortal_wounds_per_success": mortal_wounds_per_success,
        "success_count": success_count,
        "mortal_wounds": mortal_wounds,
        "trigger_roll": trigger_roll_payload,
        "effect_payload": payload,
    }
    decisions.event_log.append(
        MOVEMENT_PHASE_END_MORTAL_WOUNDS_ROLLED_EVENT,
        source_context,
    )
    if mortal_wounds == 0:
        decisions.event_log.append(
            MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT,
            {**source_context, "mortal_application": None},
        )
        return None
    progress = MortalWoundApplicationProgress.start(
        application_id=f"movement-phase-end-mortal-wounds:{effect.effect_id}",
        source_rule_id=effect.source_rule_id,
        source_context=source_context,
        target_unit_instance_id=rules_unit.unit_instance_id,
        defender_player_id=rules_unit.owner_player_id,
        mortal_wounds=mortal_wounds,
        spill_over=True,
    )
    routed = continue_mortal_wound_application(
        state=state,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        decisions.event_log.append(
            MOVEMENT_PHASE_END_MORTAL_WOUNDS_PENDING_EVENT,
            {**source_context, "request_id": routed.request.request_id},
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=routed.request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": effect.source_rule_id,
                "effect_id": effect.effect_id,
                "target_unit_instance_id": rules_unit.unit_instance_id,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Movement phase-end mortal wounds did not resolve.")
    decisions.event_log.append(
        MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT,
        {**source_context, "mortal_application": routed.application.to_payload()},
    )
    return None


def _is_current_movement_phase_end_mortal_wound_effect(
    *,
    state: GameState,
    effect: PersistingEffect,
    payload: JsonValue,
) -> bool:
    return (
        effect.owner_player_id == state.active_player_id
        and effect.started_battle_round == state.battle_round
        and effect.started_phase is BattlePhase.MOVEMENT
        and isinstance(payload, dict)
        and payload.get("effect_kind") == "catalog_movement_action_grant"
        and isinstance(payload.get("phase_end_mortal_wounds"), dict)
    )


def _processed_effect_ids(decisions: DecisionController) -> set[str]:
    processed: set[str] = set()
    for record in decisions.event_log.records:
        if record.event_type not in {
            MOVEMENT_PHASE_END_MORTAL_WOUNDS_PENDING_EVENT,
            MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT,
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        effect_id = payload.get("effect_id")
        if type(effect_id) is str:
            processed.add(effect_id)
    return processed


def _required_positive_int(payload: dict[str, JsonValue], field_name: str) -> int:
    value = payload.get(field_name)
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"Movement phase-end mortal wound {field_name} must be positive.")
    return value


def _required_d6_value(payload: dict[str, JsonValue], field_name: str) -> int:
    value = _required_positive_int(payload, field_name)
    if value > 6:
        raise GameLifecycleError(
            f"Movement phase-end mortal wound {field_name} must be a D6 value."
        )
    return value
