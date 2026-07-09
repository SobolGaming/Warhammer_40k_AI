from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_once_per_battle_support import (
    clause_is_fight_start_once_per_battle_activation,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
    catalog_rule_clauses_from_record,
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_current_wargear_bearer_model_ids,
)
from warhammer40k_core.engine.catalog_selected_target_effects_support import (
    runtime_clause_id_from_record,
    unit_scoped_generic_records_for_timing,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    FightPhaseStartHookBinding,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    execute_rule_ir,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_frequency import (
    optional_ability_frequency_condition,
    optional_ability_frequency_unavailable_reason,
    optional_ability_frequency_usage_key,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR, parameter_payload

CATALOG_ONCE_PER_BATTLE_FIGHT_START_SUBMISSION_KIND = "catalog_once_per_battle_fight_start_ability"
CATALOG_ONCE_PER_BATTLE_ABILITY_ACTIVATED_EVENT = "catalog_once_per_battle_ability_activated"
CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT = "catalog_once_per_battle_ability_declined"


@dataclass(frozen=True, slots=True)
class _OncePerBattleActivation:
    record: AbilityCatalogRecord
    player_id: str
    unit: UnitInstance
    source_rules_unit: RulesUnitView
    source_model_instance_id: str | None
    clause: RuleClause
    rule_ir: RuleIR
    usage_key: str

    @property
    def sort_key(self) -> tuple[str, str, str, str, str]:
        return (
            self.player_id,
            self.unit.unit_instance_id,
            "" if self.source_model_instance_id is None else self.source_model_instance_id,
            self.record.record_id,
            self.clause.clause_id,
        )


@dataclass(frozen=True, slots=True)
class CatalogOncePerBattleRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if {army.player_id for army in armies} - set(indexes):
            raise GameLifecycleError("Catalog once-per-battle runtime missing ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def fight_phase_start_bindings(self) -> tuple[FightPhaseStartHookBinding, ...]:
        if not _has_fight_start_once_per_battle_records(self.ability_indexes_by_player_id):
            return ()
        return (
            FightPhaseStartHookBinding(
                hook_id=CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
                source_id=CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
                request_handler=self.fight_phase_start_request,
                result_handler=self.apply_fight_phase_start_result,
            ),
        )

    def fight_phase_start_request(
        self,
        context: FightPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        activations = _available_activations(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=context,
        )
        if not activations:
            return None
        return _activation_request(state=context.state, activation=activations[0])

    def apply_fight_phase_start_result(
        self,
        context: FightPhaseStartResultContext,
    ) -> bool | LifecycleStatus:
        if type(context) is not FightPhaseStartResultContext:
            raise GameLifecycleError("Catalog once-per-battle Fight-start requires context.")
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID:
            return False
        payload = _payload_object(context.result.payload)
        activations = _available_activations(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            armies=self.armies,
            context=FightPhaseStartRequestContext(
                state=context.state,
                decisions=context.decisions,
            ),
        )
        usage_key = _payload_string(payload, "usage_key")
        activation = next(
            (candidate for candidate in activations if candidate.usage_key == usage_key),
            None,
        )
        if activation is None:
            return _invalid_status(context, reason="once_per_battle_activation_drift")
        activate = payload.get("activate")
        if type(activate) is not bool:
            raise GameLifecycleError("Catalog once-per-battle activate must be boolean.")
        expected = validate_json_value(
            {**_base_payload(state=context.state, activation=activation), "activate": activate}
        )
        if context.result.payload != expected:
            return _invalid_status(context, reason="once_per_battle_payload_drift")
        if not activate:
            context.decisions.event_log.append(
                CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT,
                {
                    **_base_payload(state=context.state, activation=activation),
                    "request_id": context.request.request_id,
                    "result_id": context.result.result_id,
                },
            )
            return True
        execution = execute_rule_ir(
            rule_ir=activation.rule_ir,
            context=RuleExecutionContext(
                game_id=context.state.game_id,
                player_id=activation.player_id,
                battle_round=context.state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                active_player_id=context.state.active_player_id,
                timing_window_id="fight_phase_start",
                source_unit_instance_id=activation.source_rules_unit.unit_instance_id,
                source_model_instance_id=activation.source_model_instance_id,
                target_unit_instance_ids=(activation.source_rules_unit.unit_instance_id,),
                target_player_id=activation.player_id,
                source_keywords=tuple(
                    sorted(
                        (
                            *activation.source_rules_unit.keywords,
                            *activation.source_rules_unit.faction_keywords,
                        )
                    )
                ),
                trigger_payload={
                    "catalog_record_id": activation.record.record_id,
                    "request_id": context.request.request_id,
                    "result_id": context.result.result_id,
                    "submission_kind": CATALOG_ONCE_PER_BATTLE_FIGHT_START_SUBMISSION_KIND,
                    "usage_key": activation.usage_key,
                },
                state=context.state,
                event_log=context.decisions.event_log,
            ),
        )
        if execution.status is not RuleExecutionStatus.APPLIED:
            return _invalid_status(
                context,
                reason=(
                    "once_per_battle_execution_failed"
                    if execution.reason is None
                    else execution.reason
                ),
            )
        context.decisions.event_log.append(
            CATALOG_ONCE_PER_BATTLE_ABILITY_ACTIVATED_EVENT,
            {
                **_base_payload(state=context.state, activation=activation),
                "request_id": context.request.request_id,
                "result_id": context.result.result_id,
                "rule_execution": execution.to_payload(),
            },
        )
        return True


def _available_activations(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
    context: FightPhaseStartRequestContext,
) -> tuple[_OncePerBattleActivation, ...]:
    if context.state.current_battle_phase is not BattlePhase.FIGHT:
        return ()
    activations: list[_OncePerBattleActivation] = []
    for army in armies:
        index = ability_indexes_by_player_id.get(army.player_id)
        if index is None:
            raise GameLifecycleError("Catalog once-per-battle ability index is missing.")
        for unit in sorted(army.units, key=lambda item: item.unit_instance_id):
            current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
                state=context.state,
                unit=unit,
            )
            if not current_model_ids:
                continue
            records = unit_scoped_generic_records_for_timing(
                ability_index=index,
                unit=unit,
                current_model_instance_ids=current_model_ids,
                trigger_kind=TimingTriggerKind.START_PHASE,
            )
            for record in records:
                activations.extend(
                    _record_activations(
                        context=context,
                        record=record,
                        player_id=army.player_id,
                        unit=unit,
                        current_model_instance_ids=current_model_ids,
                    )
                )
    return tuple(sorted(activations, key=lambda activation: activation.sort_key))


def _record_activations(
    *,
    context: FightPhaseStartRequestContext,
    record: AbilityCatalogRecord,
    player_id: str,
    unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[_OncePerBattleActivation, ...]:
    full_rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
    runtime_clause_id = runtime_clause_id_from_record(record)
    source_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=unit.unit_instance_id,
    )
    activations: list[_OncePerBattleActivation] = []
    for clause in catalog_rule_clauses_from_record(record):
        if runtime_clause_id is not None and runtime_clause_id != clause.clause_id:
            continue
        if not clause_is_fight_start_once_per_battle_activation(clause):
            continue
        rule_ir = replace(full_rule_ir, clauses=(clause,), diagnostics=clause.diagnostics)
        for source_model_id in _source_model_ids(
            record=record,
            unit=unit,
            clause=clause,
            current_model_instance_ids=current_model_instance_ids,
        ):
            usage_key = optional_ability_frequency_usage_key(
                rule_ir=rule_ir,
                clause=clause,
                player_id=player_id,
                source_unit_instance_id=source_rules_unit.unit_instance_id,
                source_model_instance_id=source_model_id,
            )
            unavailable = optional_ability_frequency_unavailable_reason(
                rule_ir=rule_ir,
                clause=clause,
                event_log=context.decisions.event_log,
                player_id=player_id,
                source_unit_instance_id=source_rules_unit.unit_instance_id,
                source_model_instance_id=source_model_id,
            )
            if unavailable == "frequency_limit_exhausted:battle":
                continue
            if unavailable is not None:
                raise GameLifecycleError(
                    f"Catalog once-per-battle frequency lookup failed: {unavailable}."
                )
            activation = _OncePerBattleActivation(
                record=record,
                player_id=player_id,
                unit=unit,
                source_rules_unit=source_rules_unit,
                source_model_instance_id=source_model_id,
                clause=clause,
                rule_ir=rule_ir,
                usage_key=usage_key,
            )
            if not _activation_declined_in_current_window(
                context=context,
                activation=activation,
            ):
                activations.append(activation)
    return tuple(activations)


def _source_model_ids(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    clause: RuleClause,
    current_model_instance_ids: tuple[str, ...],
) -> tuple[str | None, ...]:
    condition = optional_ability_frequency_condition(clause)
    if condition is None:
        raise GameLifecycleError("Catalog once-per-battle clause requires frequency condition.")
    usage_subject = parameter_payload(condition.parameters).get("usage_subject")
    if usage_subject == "this_unit":
        return (None,)
    if record.source_kind is AbilitySourceKind.WARGEAR:
        return tuple(
            catalog_rule_record_current_wargear_bearer_model_ids(
                record=record,
                unit=unit,
                current_model_instance_ids=current_model_instance_ids,
            )
        )
    if usage_subject in {"this_model", "bearer"}:
        return tuple(current_model_instance_ids)
    raise GameLifecycleError("Catalog once-per-battle usage_subject is unsupported.")


def _activation_request(
    *,
    state: object,
    activation: _OncePerBattleActivation,
) -> DecisionRequest:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog once-per-battle request requires GameState.")
    base = _base_payload(state=state, activation=activation)
    decline_id = f"{activation.usage_key}:decline"
    use_id = f"{activation.usage_key}:use"
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        actor_id=activation.player_id,
        payload={**base, "available_option_ids": [decline_id, use_id]},
        options=(
            DecisionOption(
                option_id=decline_id,
                label=f"Do not use {activation.record.definition.name}",
                payload={**base, "activate": False},
            ),
            DecisionOption(
                option_id=use_id,
                label=f"Use {activation.record.definition.name}",
                payload={**base, "activate": True},
            ),
        ),
    )


def _base_payload(*, state: object, activation: _OncePerBattleActivation) -> dict[str, JsonValue]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog once-per-battle payload requires GameState.")
    if state.active_player_id is None:
        raise GameLifecycleError("Catalog once-per-battle payload requires active player.")
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "submission_kind": CATALOG_ONCE_PER_BATTLE_FIGHT_START_SUBMISSION_KIND,
                "hook_id": CATALOG_IR_ONCE_PER_BATTLE_ABILITY_CONSUMER_ID,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": state.active_player_id,
                "player_id": activation.player_id,
                "catalog_record_id": activation.record.record_id,
                "ability_id": activation.record.definition.ability_id,
                "ability_name": activation.record.definition.name,
                "source_rule_id": activation.record.definition.source_id,
                "rule_ir_hash": activation.rule_ir.ir_hash(),
                "clause_id": activation.clause.clause_id,
                "source_unit_instance_id": activation.unit.unit_instance_id,
                "source_rules_unit_instance_id": (activation.source_rules_unit.unit_instance_id),
                "source_model_instance_id": activation.source_model_instance_id,
                "usage_key": activation.usage_key,
                "decline_window_key": _decline_window_key(state, activation.usage_key),
            }
        ),
    )


def _activation_declined_in_current_window(
    *,
    context: FightPhaseStartRequestContext,
    activation: _OncePerBattleActivation,
) -> bool:
    expected = _decline_window_key(context.state, activation.usage_key)
    for event in context.decisions.event_log.records:
        if event.event_type != CATALOG_ONCE_PER_BATTLE_ABILITY_DECLINED_EVENT:
            continue
        payload = _payload_object(event.payload)
        if _payload_string(payload, "decline_window_key") == expected:
            return True
    return False


def _decline_window_key(state: object, usage_key: str) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.active_player_id is None:
        raise GameLifecycleError("Catalog once-per-battle decline window requires battle state.")
    return f"{usage_key}:{state.battle_round}:{state.active_player_id}:fight-start"


def _has_fight_start_once_per_battle_records(
    indexes: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        clause_is_fight_start_once_per_battle_activation(clause)
        for index in indexes.values()
        for record in index.all_records()
        if record.definition.handler_id == GENERIC_RULE_IR_ABILITY_HANDLER_ID
        for clause in catalog_rule_clauses_from_record(record)
    )


def _invalid_status(
    context: FightPhaseStartResultContext,
    *,
    reason: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Catalog once-per-battle Fight-start activation is invalid.",
        payload={
            "invalid_reason": reason,
            "request_id": context.request.request_id,
            "result_id": context.result.result_id,
        },
    )


def _validate_ability_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog once-per-battle indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in cast(Mapping[object, object], value).items():
        player_id = _validate_identifier("player_id", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog once-per-battle mapping requires indexes.")
        indexes[player_id] = raw_index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog once-per-battle armies must be a tuple.")
    armies = cast(tuple[object, ...], value)
    if any(type(army) is not ArmyDefinition for army in armies):
        raise GameLifecycleError("Catalog once-per-battle armies require definitions.")
    return tuple(sorted(cast(tuple[ArmyDefinition, ...], armies), key=lambda army: army.player_id))


def _payload_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Catalog once-per-battle payload must be an object.")
    return cast(dict[str, object], value)


def _payload_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog once-per-battle payload {key} must be a string.")
    return _validate_identifier(key, value)


_validate_identifier = IdentifierValidator(GameLifecycleError)
