from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveOrigin
from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    TurnEndHookBinding,
    TurnEndRequestContext,
    TurnEndResultContext,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_TURN_END_RESERVES_SUBMISSION_KIND = "catalog_ir_turn_end_reserves"
CATALOG_TURN_END_RESERVES_USED_EVENT = "catalog_ir_turn_end_reserves_used"
CATALOG_TURN_END_RESERVES_DECLINED_EVENT = "catalog_ir_turn_end_reserves_declined"


@dataclass(frozen=True, slots=True)
class CatalogTurnEndReserveRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        player_ids = {army.player_id for army in armies}
        missing_ids = player_ids - set(indexes)
        if missing_ids:
            raise GameLifecycleError("Catalog turn-end reserves missing player ability index.")
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[TurnEndHookBinding, ...]:
        if not _has_turn_end_reserve_records(self.ability_indexes_by_player_id):
            return ()
        return (
            TurnEndHookBinding(
                hook_id=CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
                source_id=CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
                request_handler=self.request_handler,
                result_handler=self.result_handler,
            ),
        )

    def request_handler(self, context: TurnEndRequestContext) -> DecisionRequest | None:
        if type(context) is not TurnEndRequestContext:
            raise GameLifecycleError("Catalog turn-end reserves require request context.")
        if context.completed_phase is not BattlePhase.FIGHT:
            return None
        active_player_id = _active_player_id(context)
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for unit, record, rule_ir in _turn_end_reserve_candidates(
                index=index,
                army=army,
                active_player_id=active_player_id,
                state=context.state,
            ):
                if _decision_recorded_this_turn(
                    context,
                    catalog_record_id=record.record_id,
                    unit_instance_id=unit.unit_instance_id,
                ):
                    continue
                if not _unit_can_enter_strategic_reserves(
                    context.state,
                    unit_instance_id=unit.unit_instance_id,
                ):
                    continue
                return DecisionRequest(
                    request_id=context.state.next_decision_request_id(),
                    decision_type=SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
                    actor_id=army.player_id,
                    payload={
                        "game_id": context.state.game_id,
                        "battle_round": context.state.battle_round,
                        "active_player_id": active_player_id,
                        "phase": context.completed_phase.value,
                        "source_rule_id": record.definition.source_id,
                        "hook_id": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
                        "catalog_record_id": record.record_id,
                        "ability_id": record.definition.ability_id,
                        "ability_name": record.definition.name,
                        "datasheet_id": record.datasheet_id,
                        "source_kind": record.source_kind.value,
                        "target_unit_instance_id": unit.unit_instance_id,
                        "rule_ir_hash": rule_ir.ir_hash(),
                    },
                    options=(
                        _catalog_turn_end_reserve_option(
                            player_id=army.player_id,
                            record=record,
                            unit_instance_id=unit.unit_instance_id,
                            use_ability=True,
                        ),
                        _catalog_turn_end_reserve_option(
                            player_id=army.player_id,
                            record=record,
                            unit_instance_id=unit.unit_instance_id,
                            use_ability=False,
                        ),
                    ),
                )
        return None

    def result_handler(self, context: TurnEndResultContext) -> bool:
        if type(context) is not TurnEndResultContext:
            raise GameLifecycleError("Catalog turn-end reserves require result context.")
        request_payload = _payload_object(context.request.payload)
        if request_payload.get("hook_id") != CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID:
            return False
        result_payload = _payload_object(context.result.payload)
        player_id = _payload_string(result_payload, "player_id")
        catalog_record_id = _payload_string(result_payload, "catalog_record_id")
        unit_instance_id = _payload_string(result_payload, "target_unit_instance_id")
        use_ability = _payload_bool(result_payload, "use_ability")
        _validate_request_payload_matches_result(
            request_payload=request_payload,
            result_payload=result_payload,
        )
        army = _army_for_player(self.armies, player_id=player_id)
        unit = _unit_in_army_by_id(army, unit_instance_id=unit_instance_id)
        record = _record_by_id(
            self.ability_indexes_by_player_id[player_id],
            catalog_record_id=catalog_record_id,
        )
        _validate_record_can_apply_to_unit(
            record=record,
            unit=unit,
            state=context.state,
        )
        if not use_ability:
            context.decisions.event_log.append(
                CATALOG_TURN_END_RESERVES_DECLINED_EVENT,
                _event_payload(
                    context=context,
                    record=record,
                    player_id=player_id,
                    unit_instance_id=unit_instance_id,
                    reserve_state_payload=None,
                    use_ability=False,
                ),
            )
            return True
        if not _unit_can_enter_strategic_reserves(
            context.state,
            unit_instance_id=unit_instance_id,
        ):
            raise GameLifecycleError("Catalog turn-end reserve unit is no longer eligible.")
        reserve_state = context.state.reposition_unit_to_strategic_reserves(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
            source_rule_ids=(record.definition.source_id,),
        )
        context.decisions.event_log.append(
            CATALOG_TURN_END_RESERVES_USED_EVENT,
            _event_payload(
                context=context,
                record=record,
                player_id=player_id,
                unit_instance_id=unit_instance_id,
                reserve_state_payload=cast(JsonValue, reserve_state.to_payload()),
                use_ability=True,
            ),
        )
        return True


def catalog_turn_end_reserve_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[TurnEndHookBinding, ...]:
    return CatalogTurnEndReserveRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _turn_end_reserve_candidates(
    *,
    index: AbilityCatalogIndex,
    army: ArmyDefinition,
    active_player_id: str,
    state: object,
) -> tuple[tuple[UnitInstance, AbilityCatalogRecord, RuleIR], ...]:
    candidates: list[tuple[UnitInstance, AbilityCatalogRecord, RuleIR]] = []
    for unit in sorted(army.units, key=lambda stored: stored.unit_instance_id):
        for record in index.all_records():
            if not _record_source_matches_unit(record=record, unit=unit, state=state):
                continue
            rule_ir = _rule_ir_from_record(record)
            if not _rule_ir_is_turn_end_reserve_rule(rule_ir):
                continue
            owner = _turn_owner(rule_ir)
            if not _turn_owner_matches(
                owner=owner,
                player_id=army.player_id,
                active_player_id=active_player_id,
            ):
                continue
            candidates.append((unit, record, rule_ir))
    return tuple(candidates)


def _record_source_matches_unit(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    state: object,
) -> bool:
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return record.datasheet_id == unit.datasheet_id
    if record.source_kind is AbilitySourceKind.WARGEAR:
        if record.datasheet_id != unit.datasheet_id or record.wargear_id is None:
            return False
        current_model_ids = _current_model_instance_ids(state=state, unit=unit)
        return any(
            model.model_instance_id in current_model_ids
            and model.is_alive
            and record.wargear_id in model.wargear_ids
            for model in unit.own_models
        )
    return False


def _rule_ir_is_turn_end_reserve_rule(rule_ir: RuleIR) -> bool:
    if not rule_ir.is_supported:
        return False
    if CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID not in (
        catalog_rule_ir_consumers_for_rule(rule_ir)
    ):
        return False
    return any(
        _clause_targets_this_unit(clause)
        and _clause_has_turn_end_reserve_effect(clause)
        and _clause_has_opponent_engagement_condition(clause)
        for clause in rule_ir.clauses
    )


def _clause_targets_this_unit(clause: RuleClause) -> bool:
    return clause.target is not None and clause.target.kind is RuleTargetKind.THIS_UNIT


def _clause_has_turn_end_reserve_effect(clause: RuleClause) -> bool:
    return any(_effect_is_turn_end_reserve_permission(effect) for effect in clause.effects)


def _effect_is_turn_end_reserve_permission(effect: RuleEffectSpec) -> bool:
    if effect.kind is not RuleEffectKind.PLACEMENT_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("placement_kind") == "turn_end_reserves"
        and parameters.get("reserve_kind") == "strategic_reserves"
        and parameters.get("action") == "remove_from_battlefield_to_strategic_reserves"
    )


def _clause_has_opponent_engagement_condition(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if parameters.get("predicate") != "within_engagement_range":
            continue
        if parameters.get("negated") is not True:
            continue
        if parameters.get("object_allegiance") != "enemy":
            continue
        if parameters.get("object_kind") != "unit":
            continue
        subject = parameters.get("subject")
        if subject is not None and subject != "this_unit":
            continue
        return True
    return False


def _turn_owner(rule_ir: RuleIR) -> str | None:
    for clause in rule_ir.clauses:
        if not _clause_has_turn_end_reserve_effect(clause):
            continue
        trigger = clause.trigger
        if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
            return None
        parameters = parameter_payload(trigger.parameters)
        if parameters.get("edge") != "end" or parameters.get("phase") != "turn":
            return None
        owner = parameters.get("owner")
        if owner is None:
            return None
        if type(owner) is not str:
            raise GameLifecycleError("Catalog turn-end reserve owner parameter is invalid.")
        return owner
    return None


def _turn_owner_matches(*, owner: str | None, player_id: str, active_player_id: str) -> bool:
    if owner == "opponent":
        return player_id != active_player_id
    if owner == "active_player":
        return player_id == active_player_id
    return False


def _unit_can_enter_strategic_reserves(
    state: object,
    *,
    unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog turn-end reserves require GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Catalog turn-end reserves require battlefield_state.")
    if state.reserve_state_for_unit(unit_instance_id) is not None:
        return False
    if not state.battlefield_state.is_unit_placed(unit_instance_id):
        return False
    return not unit_within_enemy_engagement_range(state=state, unit_instance_id=unit_instance_id)


def _catalog_turn_end_reserve_option(
    *,
    player_id: str,
    record: AbilityCatalogRecord,
    unit_instance_id: str,
    use_ability: bool,
) -> DecisionOption:
    action = "use" if use_ability else "decline"
    label = f"Use {record.definition.name}" if use_ability else f"Decline {record.definition.name}"
    return DecisionOption(
        option_id=f"catalog-ir:turn-end-reserves:{record.record_id}:{unit_instance_id}:{action}",
        label=label,
        payload={
            "submission_kind": CATALOG_TURN_END_RESERVES_SUBMISSION_KIND,
            "player_id": player_id,
            "source_rule_id": record.definition.source_id,
            "hook_id": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
            "catalog_record_id": record.record_id,
            "ability_id": record.definition.ability_id,
            "ability_name": record.definition.name,
            "target_unit_instance_id": unit_instance_id,
            "use_ability": use_ability,
        },
    )


def _event_payload(
    *,
    context: TurnEndResultContext,
    record: AbilityCatalogRecord,
    player_id: str,
    unit_instance_id: str,
    reserve_state_payload: JsonValue,
    use_ability: bool,
) -> dict[str, JsonValue]:
    return {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "active_player_id": context.state.active_player_id,
        "phase": context.state.current_battle_phase.value
        if context.state.current_battle_phase is not None
        else None,
        "player_id": player_id,
        "source_rule_id": record.definition.source_id,
        "hook_id": CATALOG_IR_CAN_BE_PLACED_IN_RESERVES_CONSUMER_ID,
        "catalog_record_id": record.record_id,
        "ability_id": record.definition.ability_id,
        "ability_name": record.definition.name,
        "target_unit_instance_id": unit_instance_id,
        "request_id": context.request.request_id,
        "result_id": context.result.result_id,
        "selected_option_id": context.result.selected_option_id,
        "use_ability": use_ability,
        "reserve_state": reserve_state_payload,
    }


def _validate_request_payload_matches_result(
    *,
    request_payload: dict[str, JsonValue],
    result_payload: dict[str, JsonValue],
) -> None:
    for key in ("source_rule_id", "hook_id", "catalog_record_id", "target_unit_instance_id"):
        if request_payload.get(key) != result_payload.get(key):
            raise GameLifecycleError("Catalog turn-end reserve result payload drift.")
    submission_kind = result_payload.get("submission_kind")
    if submission_kind != CATALOG_TURN_END_RESERVES_SUBMISSION_KIND:
        raise GameLifecycleError("Catalog turn-end reserve submission kind drift.")


def _decision_recorded_this_turn(
    context: TurnEndRequestContext,
    *,
    catalog_record_id: str,
    unit_instance_id: str,
) -> bool:
    active_player_id = _active_player_id(context)
    for record in context.decisions.event_log.records:
        if record.event_type not in {
            CATALOG_TURN_END_RESERVES_USED_EVENT,
            CATALOG_TURN_END_RESERVES_DECLINED_EVENT,
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != context.state.game_id:
            continue
        if payload.get("battle_round") != context.state.battle_round:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        if payload.get("phase") != context.completed_phase.value:
            continue
        if payload.get("catalog_record_id") != catalog_record_id:
            continue
        if payload.get("target_unit_instance_id") == unit_instance_id:
            return True
    return False


def _validate_record_can_apply_to_unit(
    *,
    record: AbilityCatalogRecord,
    unit: UnitInstance,
    state: object,
) -> None:
    if not _record_source_matches_unit(record=record, unit=unit, state=state):
        raise GameLifecycleError("Catalog turn-end reserve record no longer matches unit.")
    rule_ir = _rule_ir_from_record(record)
    if not _rule_ir_is_turn_end_reserve_rule(rule_ir):
        raise GameLifecycleError("Catalog turn-end reserve record is unsupported.")


def _record_by_id(
    index: AbilityCatalogIndex,
    *,
    catalog_record_id: str,
) -> AbilityCatalogRecord:
    requested_record_id = _validate_identifier("catalog_record_id", catalog_record_id)
    for record in index.all_records():
        if record.record_id == requested_record_id:
            return record
    raise GameLifecycleError("Catalog turn-end reserve record is unknown.")


def _rule_ir_from_record(record: AbilityCatalogRecord) -> RuleIR:
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        raise GameLifecycleError("Catalog turn-end reserve record requires generic Rule IR.")
    return rule_ir_from_execution_payload(record.definition.replay_payload)


def _current_model_instance_ids(
    *,
    state: object,
    unit: UnitInstance,
) -> frozenset[str]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog turn-end reserves require GameState.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Catalog turn-end reserves require battlefield_state.")
    placement = state.battlefield_state.unit_placement_or_none(unit.unit_instance_id)
    if placement is None:
        return frozenset()
    return frozenset(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )


def _has_turn_end_reserve_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_can_emit_turn_end_reserves(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
    )


def _record_can_emit_turn_end_reserves(record: AbilityCatalogRecord) -> bool:
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return _rule_ir_is_turn_end_reserve_rule(_rule_ir_from_record(record))


def _army_for_player(armies: tuple[ArmyDefinition, ...], *, player_id: str) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError("Catalog turn-end reserve player army is unknown.")


def _unit_in_army_by_id(army: ArmyDefinition, *, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for unit in army.units:
        if unit.unit_instance_id == requested_unit_id:
            return unit
    raise GameLifecycleError("Catalog turn-end reserve unit is unknown.")


def _active_player_id(context: TurnEndRequestContext) -> str:
    active_player_id = context.state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Catalog turn-end reserves require an active player.")
    return active_player_id


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Catalog turn-end reserve payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog turn-end reserve payload missing string {key}.")
    return _validate_identifier(key, value)


def _payload_bool(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Catalog turn-end reserve payload missing bool {key}.")
    return value


def _validate_ability_index_mapping(
    value: object,
) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog turn-end reserves require ability indexes.")
    mapping = cast(Mapping[object, object], value)
    validated: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in mapping.items():
        validated[_validate_identifier("player_id", player_id)] = _validate_ability_index(index)
    return MappingProxyType(validated)


def _validate_ability_index(index: object) -> AbilityCatalogIndex:
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("Catalog turn-end reserves require AbilityCatalogIndex.")
    return index


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog turn-end reserves require army tuple.")
    armies: list[ArmyDefinition] = []
    seen: set[str] = set()
    for army in cast(tuple[object, ...], value):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError("Catalog turn-end reserves require ArmyDefinition values.")
        if army.player_id in seen:
            raise GameLifecycleError("Catalog turn-end reserves duplicate player army.")
        seen.add(army.player_id)
        armies.append(army)
    return tuple(sorted(armies, key=lambda army: army.player_id))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Catalog turn-end reserve {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Catalog turn-end reserve {field_name} must not be empty.")
    return stripped
