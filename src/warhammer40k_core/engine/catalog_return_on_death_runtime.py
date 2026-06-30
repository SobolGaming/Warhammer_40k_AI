from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
    CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
    catalog_rule_clause_is_supported_first_death_return,
    catalog_rule_clauses_from_record,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.event_log import EventLog, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
)
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookBinding,
    StickyObjectiveControlState,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookBinding,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleTriggerKind,
    parameter_payload,
)


@dataclass(frozen=True, slots=True)
class CatalogReturnOnDeathRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def phase_end_bindings(self) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
        if not _has_return_on_death_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            PhaseEndObjectiveControlHookBinding(
                hook_id=CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
                source_id=CATALOG_IR_FIRST_DEATH_RETURN_PHASE_END_CONSUMER_ID,
                handler=self.phase_end_handler,
            ),
        )

    def unit_destroyed_bindings(self) -> tuple[UnitDestroyedHookBinding, ...]:
        if not _has_return_on_death_records(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id
        ):
            return ()
        return (
            UnitDestroyedHookBinding(
                hook_id=CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
                source_id=CATALOG_IR_FIRST_DEATH_RETURN_CONSUMER_ID,
                handler=self.unit_destroyed_handler,
            ),
        )

    def unit_destroyed_handler(self, context: UnitDestroyedContext) -> None:
        army, unit = _army_and_unit_for_unit_id(
            armies=self.armies,
            unit_instance_id=context.destroyed_unit_instance_id,
        )
        if army.player_id != context.destroyed_player_id:
            raise GameLifecycleError("Return-on-death destroyed player drift.")
        index = self.ability_indexes_by_player_id.get(context.destroyed_player_id)
        if index is None:
            raise GameLifecycleError("Return-on-death runtime missing player ability index.")
        current_model_ids = unit.own_model_ids()
        for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED):
            if not catalog_rule_record_source_matches_unit(
                record=record,
                unit=unit,
                current_model_instance_ids=current_model_ids,
            ):
                continue
            for clause in catalog_rule_clauses_from_record(record):
                pending = _pending_return_on_death_for_event(
                    state=context.state,
                    completed_phase=context.completed_phase.value,
                    model_destroyed_event_id=context.model_destroyed_event_id,
                    model_destroyed_payload=context.model_destroyed_payload,
                    destroyed_player_id=context.destroyed_player_id,
                    destroyed_unit_instance_id=context.destroyed_unit_instance_id,
                    record=record,
                    clause=clause,
                )
                if pending is None:
                    continue
                if _record_pending_return_on_death(
                    pending=pending,
                    event_log=context.decisions.event_log,
                    state=context.state,
                    phase=context.completed_phase.value,
                    model_destroyed_event_id=context.model_destroyed_event_id,
                ):
                    return

    def phase_end_handler(
        self,
        context: PhaseEndObjectiveControlContext,
    ) -> tuple[StickyObjectiveControlState, ...]:
        for event_id, payload in _model_destroyed_events_for_phase(context):
            destroyed_unit_id = _payload_string(payload, key="target_unit_instance_id")
            destroyed_model_id = _payload_string(payload, key="model_instance_id")
            army, unit = _army_and_unit_for_unit_id(
                armies=self.armies,
                unit_instance_id=destroyed_unit_id,
            )
            index = self.ability_indexes_by_player_id.get(army.player_id)
            if index is None:
                raise GameLifecycleError("Return-on-death runtime missing player ability index.")
            for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED):
                for clause in catalog_rule_clauses_from_record(record):
                    if not catalog_rule_clause_is_supported_first_death_return(clause):
                        continue
                    target_scope = _target_scope_for_trigger(clause)
                    if (
                        target_scope is ReturnDestroyedTargetScope.DESTROYED_UNIT
                        and not _unit_is_destroyed(
                            context=context,
                            unit_instance_id=destroyed_unit_id,
                        )
                    ):
                        continue
                    if not _record_source_matches_destroyed_target(
                        record=record,
                        unit=unit,
                        destroyed_model_instance_id=destroyed_model_id,
                        target_scope=target_scope,
                    ):
                        continue
                    pending = _pending_return_on_death_for_event(
                        state=context.state,
                        completed_phase=context.completed_phase.value,
                        model_destroyed_event_id=event_id,
                        model_destroyed_payload=payload,
                        destroyed_player_id=army.player_id,
                        destroyed_unit_instance_id=destroyed_unit_id,
                        record=record,
                        clause=clause,
                    )
                    if pending is None:
                        continue
                    _record_pending_return_on_death(
                        pending=pending,
                        event_log=context.event_log,
                        state=context.state,
                        phase=context.completed_phase.value,
                        model_destroyed_event_id=event_id,
                    )
        return ()


def catalog_return_on_death_unit_destroyed_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitDestroyedHookBinding, ...]:
    return CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).unit_destroyed_bindings()


def catalog_return_on_death_phase_end_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[PhaseEndObjectiveControlHookBinding, ...]:
    return CatalogReturnOnDeathRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).phase_end_bindings()


def _pending_return_on_death_for_event(
    *,
    state: object,
    completed_phase: str,
    model_destroyed_event_id: str,
    model_destroyed_payload: dict[str, JsonValue],
    destroyed_player_id: str,
    destroyed_unit_instance_id: str,
    record: AbilityCatalogRecord,
    clause: RuleClause,
) -> PendingReturnOnDeath | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Return-on-death capture requires GameState.")
    if not catalog_rule_clause_is_supported_first_death_return(clause):
        return None
    if clause.trigger is None:
        raise GameLifecycleError("Return-on-death supported clause missing trigger.")
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    destroyed_model_id = _payload_string(model_destroyed_payload, key="model_instance_id")
    target_scope = _target_scope_for_trigger(clause)
    if target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL:
        destroyed_target = trigger_parameters.get("destroyed_target")
        if destroyed_target != "this_model":
            return None
    effect_index, effect_parameters = _return_effect_parameters(clause)
    roll_parameters = _roll_gate_parameters(clause)
    wounds_remaining = effect_parameters.get("wounds_remaining")
    return PendingReturnOnDeath(
        pending_id=(
            f"return-on-death:{model_destroyed_event_id}:{record.record_id}:{clause.clause_id}"
        ),
        source_rule_id=record.definition.source_id,
        source_ability_id=record.definition.ability_id,
        source_clause_id=clause.clause_id,
        source_effect_index=effect_index,
        owner_player_id=destroyed_player_id,
        target_scope=target_scope,
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        destroyed_model_instance_id=(
            destroyed_model_id
            if target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL
            else None
        ),
        destroyed_position_payload=_destroyed_position_payload(
            model_destroyed_event_id=model_destroyed_event_id,
            model_destroyed_payload=model_destroyed_payload,
        ),
        trigger_battle_round=state.battle_round,
        trigger_phase=completed_phase,
        resolution_timing=_parameter_string(trigger_parameters, key="resolution_timing"),
        roll_expression=_parameter_string(roll_parameters, key="roll_expression"),
        roll_count=_parameter_int(roll_parameters, key="roll_count"),
        success_threshold=_parameter_int(roll_parameters, key="success_threshold"),
        placement_anchor=_parameter_string(effect_parameters, key="placement_anchor"),
        placement_preference=_parameter_string(effect_parameters, key="placement_preference"),
        engagement_range_restriction=True,
        restore_wounds_mode=ReturnRestoreWoundsMode(
            _parameter_string(effect_parameters, key="restore_wounds_mode")
        ),
        wounds_remaining=(
            None
            if wounds_remaining is None
            else _parameter_int(effect_parameters, key="wounds_remaining")
        ),
        resolved=False,
    )


def _target_scope_for_trigger(clause: RuleClause) -> ReturnDestroyedTargetScope:
    if clause.trigger is None:
        raise GameLifecycleError("Return-on-death supported clause missing trigger.")
    if clause.trigger.kind is RuleTriggerKind.MODEL_DESTROYED:
        return ReturnDestroyedTargetScope.DESTROYED_MODEL
    if clause.trigger.kind is RuleTriggerKind.UNIT_DESTROYED:
        return ReturnDestroyedTargetScope.DESTROYED_UNIT
    raise GameLifecycleError("Return-on-death supported clause has unsupported trigger.")


def _return_effect_parameters(clause: RuleClause) -> tuple[int, Mapping[str, object]]:
    for effect_index, effect in enumerate(clause.effects):
        if effect.kind is RuleEffectKind.RETURN_DESTROYED_TARGET:
            return effect_index, parameter_payload(effect.parameters)
    raise GameLifecycleError("Return-on-death supported clause missing return effect.")


def _roll_gate_parameters(clause: RuleClause) -> Mapping[str, object]:
    for condition in clause.conditions:
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE:
            return parameter_payload(condition.parameters)
    raise GameLifecycleError("Return-on-death supported clause missing dice gate.")


def _destroyed_position_payload(
    *,
    model_destroyed_event_id: str,
    model_destroyed_payload: dict[str, JsonValue],
) -> JsonValue:
    return validate_json_value(
        {
            "source": "model_destroyed_event",
            "model_destroyed_event_id": model_destroyed_event_id,
            "model_destroyed_payload": model_destroyed_payload,
        }
    )


def _record_pending_return_on_death(
    *,
    pending: PendingReturnOnDeath,
    event_log: EventLog,
    state: object,
    phase: str,
    model_destroyed_event_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Return-on-death pending capture requires GameState.")
    if pending.consumed_key() in set(state.return_on_death_consumed_keys):
        return False
    state.record_pending_return_on_death(pending)
    event_log.append(
        RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": phase,
            "model_destroyed_event_id": model_destroyed_event_id,
            "pending": pending.to_payload(),
        },
    )
    return True


def _model_destroyed_events_for_phase(
    context: PhaseEndObjectiveControlContext,
) -> tuple[tuple[str, dict[str, JsonValue]], ...]:
    if type(context) is not PhaseEndObjectiveControlContext:
        raise GameLifecycleError("Return-on-death phase-end capture requires context.")
    events: list[tuple[int, str, dict[str, JsonValue]]] = []
    for event_order, record in enumerate(context.event_log.records):
        if record.event_type != "model_destroyed":
            continue
        payload = validate_json_value(record.payload)
        if not isinstance(payload, dict):
            raise GameLifecycleError("model_destroyed event payload must be an object.")
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != context.state.active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        events.append((event_order, record.event_id, dict(payload)))
    return tuple((event_id, payload) for _order, event_id, payload in sorted(events))


def _record_source_matches_destroyed_target(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    destroyed_model_instance_id: str,
    target_scope: ReturnDestroyedTargetScope,
) -> bool:
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return record.datasheet_id == unit.datasheet_id
    if record.source_kind is not AbilitySourceKind.WARGEAR:
        return False
    if record.datasheet_id != unit.datasheet_id or record.wargear_id is None:
        return False
    if target_scope is ReturnDestroyedTargetScope.DESTROYED_MODEL:
        model = _model_by_id(unit=unit, model_instance_id=destroyed_model_instance_id)
        return record.wargear_id in model.wargear_ids
    return any(record.wargear_id in model.wargear_ids for model in unit.own_models)


def _unit_is_destroyed(
    *,
    context: PhaseEndObjectiveControlContext,
    unit_instance_id: str,
) -> bool:
    if context.state.battlefield_state is None:
        return False
    removed_model_ids = set(context.state.battlefield_state.removed_model_ids)
    _army, unit = _army_and_unit_for_unit_id(
        armies=tuple(context.state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    unit_model_ids = set(unit.own_model_ids())
    return bool(unit_model_ids) and unit_model_ids <= removed_model_ids


def _army_and_unit_for_unit_id(
    *,
    armies: tuple[ArmyDefinition, ...],
    unit_instance_id: str,
) -> tuple[ArmyDefinition, UnitInstance]:
    for army in armies:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return army, unit
    raise GameLifecycleError("Return-on-death runtime could not find destroyed unit.")


def _model_by_id(*, unit: UnitInstance, model_instance_id: str) -> ModelInstance:
    requested_id = _payload_string(
        {"model_instance_id": model_instance_id},
        key="model_instance_id",
    )
    for model in unit.own_models:
        if model.model_instance_id == requested_id:
            return model
    raise GameLifecycleError("Return-on-death runtime could not find destroyed model.")


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Return-on-death event payload missing {key}.")
    return value.strip()


def _parameter_string(payload: Mapping[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Return-on-death parameter {key} must be a string.")
    return value.strip()


def _parameter_int(payload: Mapping[str, object], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Return-on-death parameter {key} must be an integer.")
    return value


def _has_return_on_death_records(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        any(
            catalog_rule_clause_is_supported_first_death_return(clause)
            for clause in catalog_rule_clauses_from_record(record)
        )
        for index in ability_indexes_by_player_id.values()
        for record in index.records_for(TimingTriggerKind.AFTER_UNIT_DESTROYED)
    )
