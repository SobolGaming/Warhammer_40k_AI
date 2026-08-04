from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
)
from warhammer40k_core.engine.attached_unit_reconciliation import (
    split_attached_rules_unit_if_required,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    effect_is_immediate_selected_target_mortal_wounds,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    resolve_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.mortal_wound_feel_no_pain_hooks import (
    MortalWoundFeelNoPainContinuationContext,
    MortalWoundFeelNoPainContinuationHookBinding,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import (
    current_placed_alive_rules_unit_view_for_identity,
    current_rules_unit_views_for_identity,
)

CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_SOURCE_KIND = "catalog_selected_target_mortal_wounds"
CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_ROLLED_EVENT = "catalog_selected_target_mortal_wounds_rolled"
CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_PENDING_EVENT = (
    "catalog_selected_target_mortal_wounds_pending"
)
CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_RESOLVED_EVENT = (
    "catalog_selected_target_mortal_wounds_resolved"
)


@dataclass(frozen=True, slots=True)
class SelectedTargetMortalWoundResolution:
    resolved_payload: dict[str, JsonValue] | None
    pending_status: LifecycleStatus | None

    def __post_init__(self) -> None:
        if (self.resolved_payload is None) == (self.pending_status is None):
            raise GameLifecycleError(
                "Selected-target mortal wounds must resolve or await a decision."
            )


def catalog_selected_target_mortal_wound_feel_no_pain_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[MortalWoundFeelNoPainContinuationHookBinding, ...]:
    if not _has_selected_target_mortal_wound_records(ability_indexes_by_player_id):
        return ()
    return (
        MortalWoundFeelNoPainContinuationHookBinding(
            hook_id="catalog-ir:selected-target-mortal-wounds",
            source_id="catalog-ir:selected-target-mortal-wounds",
            source_kind=CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_SOURCE_KIND,
            handler=apply_catalog_selected_target_mortal_wound_feel_no_pain_decision,
        ),
    )


def resolve_selected_target_mortal_wound_effect(
    *,
    state: object,
    decisions: DecisionController,
    result: DecisionResult,
    selected_target_payload: Mapping[str, object],
    record: Mapping[str, object],
    effect_payload: Mapping[str, object],
    target_unit_ids: tuple[str, ...],
    recorded_effects_before_mortal_wounds: tuple[dict[str, JsonValue], ...],
    remaining_effect_records_after_mortal_wounds: tuple[dict[str, JsonValue], ...],
    remaining_effect_start_index: int,
) -> SelectedTargetMortalWoundResolution:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Selected-target mortal wounds require GameState.")
    if len(target_unit_ids) != 1:
        raise GameLifecycleError("Selected-target mortal wounds require one target unit.")
    parameters = _mortal_wound_parameters(effect_payload)
    selected_target_unit_id = target_unit_ids[0]
    identity_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=selected_target_unit_id,
    )
    target_owner_ids = {view.owner_player_id for view in identity_views}
    if len(target_owner_ids) != 1:
        raise GameLifecycleError("Selected-target mortal wound owner identity drifted.")
    target_player_id = next(iter(target_owner_ids))
    target = current_placed_alive_rules_unit_view_for_identity(
        state=state,
        unit_instance_id=selected_target_unit_id,
    )
    target_unit_id = selected_target_unit_id if target is None else target.unit_instance_id
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(
                quantity=_required_int(parameters, "roll_count"),
                sides=6,
            ),
            reason=(
                f"Selected-target mortal wounds from {_required_string(record, 'source_rule_id')}"
            ),
            roll_type="catalog.selected_target.mortal_wounds",
            actor_id=result.actor_id,
        )
    )
    threshold = _required_int(parameters, "success_threshold")
    mortal_wounds = sum(value >= threshold for value in roll_state.current_values)
    source_context = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": state.active_player_id,
                "source_kind": CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_SOURCE_KIND,
                "source_rule_id": _required_string(record, "source_rule_id"),
                "selected_target_unit_instance_id": selected_target_unit_id,
                "target_unit_instance_id": target_unit_id,
                "target_player_id": target_player_id,
                "mortal_wounds": mortal_wounds,
                "roll_state": roll_state.to_payload(),
                "selected_target_decision_result": result.to_payload(),
                "selected_target_payload": dict(selected_target_payload),
                "selected_target_effect_record": dict(record),
                "selected_target_recorded_effects_before_mortal_wounds": list(
                    recorded_effects_before_mortal_wounds
                ),
                "selected_target_remaining_effect_records_after_mortal_wounds": list(
                    remaining_effect_records_after_mortal_wounds
                ),
                "selected_target_remaining_effect_start_index": remaining_effect_start_index,
            }
        ),
    )
    decisions.event_log.append(
        CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_ROLLED_EVENT,
        validate_json_value(source_context),
    )
    if mortal_wounds == 0:
        return SelectedTargetMortalWoundResolution(
            resolved_payload=_resolved_payload(source_context, mortal_application=None),
            pending_status=None,
        )
    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"catalog-selected-target:{state.battle_round:02d}:{result.result_id}:{target_unit_id}"
        ),
        source_rule_id=_required_string(record, "source_rule_id"),
        source_context=source_context,
        target_unit_instance_id=target_unit_id,
        defender_player_id=target_player_id,
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
            CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_PENDING_EVENT,
            validate_json_value({**source_context, "request_id": routed.request.request_id}),
        )
        return SelectedTargetMortalWoundResolution(
            resolved_payload=None,
            pending_status=LifecycleStatus.waiting_for_decision(
                stage=state.stage,
                decision_request=routed.request,
                payload={
                    "phase": BattlePhase.SHOOTING.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "source_rule_id": _required_string(record, "source_rule_id"),
                    "target_unit_instance_id": target_unit_id,
                },
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Selected-target mortal wounds did not finish routing.")
    resolved_payload = _resolved_payload(
        source_context,
        mortal_application=routed.application.to_payload(),
    )
    decisions.event_log.append(
        CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_RESOLVED_EVENT,
        validate_json_value(resolved_payload),
    )
    split_attached_rules_unit_if_required(
        state=state,
        event_log=decisions.event_log,
        rules_unit_instance_id=target_unit_id,
    )
    return SelectedTargetMortalWoundResolution(
        resolved_payload=resolved_payload,
        pending_status=None,
    )


def apply_catalog_selected_target_mortal_wound_feel_no_pain_decision(
    context: MortalWoundFeelNoPainContinuationContext,
) -> LifecycleStatus | None:
    if type(context) is not MortalWoundFeelNoPainContinuationContext:
        raise GameLifecycleError(
            "Selected-target mortal wound Feel No Pain requires continuation context."
        )
    source_context = _payload_object(context.source_context)
    if source_context.get("source_kind") != CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Selected-target mortal wound source kind drifted.")
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=context.state,
        request=context.request,
        result=context.result,
        next_request_id=context.state.next_decision_request_id(),
        dice_manager=context.dice_manager,
    )
    if routed.request is not None:
        context.decisions.request_decision(routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage,
            decision_request=routed.request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": _required_string(source_context, "source_rule_id"),
                "target_unit_instance_id": _required_string(
                    source_context,
                    "target_unit_instance_id",
                ),
            },
        )
    if routed.application is None:
        raise GameLifecycleError(
            "Selected-target mortal wound Feel No Pain did not finish routing."
        )
    resolved_payload = _resolved_payload(
        source_context,
        mortal_application=routed.application.to_payload(),
    )
    context.decisions.event_log.append(
        CATALOG_SELECTED_TARGET_MORTAL_WOUNDS_RESOLVED_EVENT,
        validate_json_value(
            {**resolved_payload, "feel_no_pain_result_id": context.result.result_id}
        ),
    )
    split_attached_rules_unit_if_required(
        state=context.state,
        event_log=context.decisions.event_log,
        rules_unit_instance_id=_required_string(
            source_context,
            "target_unit_instance_id",
        ),
    )
    return _continue_selected_target_effects(
        context=context,
        source_context=source_context,
        resolved_mortal_wound_payload=resolved_payload,
    )


def _continue_selected_target_effects(
    *,
    context: MortalWoundFeelNoPainContinuationContext,
    source_context: Mapping[str, JsonValue],
    resolved_mortal_wound_payload: dict[str, JsonValue],
) -> LifecycleStatus | None:
    if context.battle_shock_hooks is None or context.ability_indexes_by_player_id is None:
        raise GameLifecycleError(
            "Selected-target continuation requires runtime Battle-shock content."
        )
    from warhammer40k_core.engine.catalog_selected_target_effects import (
        CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        append_selected_target_event,
        continue_selected_target_effect_records,
        selected_target_json_object_tuple,
    )
    from warhammer40k_core.engine.decision_result import DecisionResultPayload

    original_result = DecisionResult.from_payload(
        cast(
            DecisionResultPayload,
            _payload_object(source_context.get("selected_target_decision_result")),
        )
    )
    selected_target_payload = _payload_object(source_context.get("selected_target_payload"))
    initial_recorded = (
        *selected_target_json_object_tuple(
            source_context,
            key="selected_target_recorded_effects_before_mortal_wounds",
        ),
        resolved_mortal_wound_payload,
    )
    recording = continue_selected_target_effect_records(
        state=context.state,
        decisions=context.decisions,
        result=original_result,
        payload=selected_target_payload,
        effect_records=selected_target_json_object_tuple(
            source_context,
            key="selected_target_remaining_effect_records_after_mortal_wounds",
        ),
        phase=BattlePhase.SHOOTING,
        event_type=CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        battle_shock_hooks=context.battle_shock_hooks,
        runtime_modifier_registry=context.runtime_modifier_registry,
        ability_indexes_by_player_id=context.ability_indexes_by_player_id,
        initial_recorded=initial_recorded,
        effect_index_offset=_required_int(
            source_context,
            "selected_target_remaining_effect_start_index",
        ),
    )
    if recording.pending_status is not None:
        return recording.pending_status
    append_selected_target_event(
        state=context.state,
        decisions=context.decisions,
        result=original_result,
        payload=selected_target_payload,
        effects=recording.effects,
        event_type=CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_SELECTED_EVENT,
        phase=BattlePhase.SHOOTING,
    )
    return None


def _mortal_wound_parameters(
    effect_payload: Mapping[str, object],
) -> dict[str, JsonValue]:
    effect = _payload_object(effect_payload.get("effect"))
    if effect.get("kind") != "inflict_mortal_wounds":
        raise GameLifecycleError("Selected-target mortal wound effect kind drifted.")
    raw_parameters = effect.get("parameters")
    if type(raw_parameters) is not list:
        raise GameLifecycleError("Selected-target mortal wound parameters are malformed.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        parameter = _payload_object(raw_parameter)
        if set(parameter) != {"key", "value"}:
            raise GameLifecycleError("Selected-target mortal wound parameter is malformed.")
        key = _required_string(parameter, "key")
        if key in parameters:
            raise GameLifecycleError("Selected-target mortal wound parameter is duplicated.")
        parameters[key] = parameter["value"]
    expected = {
        "damage_kind": "mortal_wounds",
        "mortal_wounds_expression": "1",
        "roll_count": 3,
        "roll_expression": "D6",
        "success_threshold": 4,
        "target_scope": "selected_unit",
        "selected_target_unit_instance_id": effect.get("selected_target_unit_instance_id"),
    }
    without_selected = dict(parameters)
    without_selected.pop("selected_target_unit_instance_id", None)
    expected.pop("selected_target_unit_instance_id")
    if without_selected != expected:
        raise GameLifecycleError("Selected-target mortal wound parameters drifted.")
    return parameters


def _resolved_payload(
    source_context: Mapping[str, JsonValue],
    *,
    mortal_application: object,
) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                **source_context,
                "mortal_application": mortal_application,
            }
        ),
    )


def _has_selected_target_mortal_wound_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        effect_is_immediate_selected_target_mortal_wounds(effect)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        for clause in catalog_rule_clauses_from_record(record)
        for effect in clause.effects
    )


def _payload_object(value: object) -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError("Selected-target mortal wound payload must be an object.")
    return payload


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Selected-target mortal wound payload {key} must be text.")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Selected-target mortal wound payload {key} must be an integer.")
    return value
