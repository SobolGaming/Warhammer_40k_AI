from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilitySourceKind,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock_historical_authority import (
    HistoricalBattleShockAuthorityContext,
)
from warhammer40k_core.engine.battlefield_presence import (
    battlefield_scenario_for_state,
    rules_unit_has_placed_alive_model,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_current_wargear_bearer_model_ids,
    catalog_rule_unit_scoped_generic_records,
)
from warhammer40k_core.engine.catalog_unit_move_completed_battle_shock_support import (
    CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
    clause_is_supported_unit_move_completed_battle_shock,
    effect_is_supported_unit_move_completed_battle_shock,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.bundle_validation import (
    validate_identifier as _validate_identifier,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    geometry_models_are_physically_engaged,
    scenario_rules_units_are_physically_engaged,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockEffect,
    UnitMoveCompletedBattleShockHookBinding,
    UnitMoveCompletedContext,
)
from warhammer40k_core.rules.rule_ir import RuleClause

CATALOG_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_REPLAY_PAYLOAD_KEYS = frozenset(
    {
        "effect_kind",
        "consumer_id",
        "catalog_record_id",
        "ability_id",
        "ability_name",
        "catalog_source_rule_id",
        "player_id",
        "source_rules_unit_instance_id",
        "source_unit_instance_id",
        "source_model_instance_id",
        "clause_id",
        "effect_index",
        "reason",
        "target_unit_instance_id",
        "target_player_id",
        "trigger_event_id",
        "movement_action",
    }
)


@dataclass(frozen=True, slots=True)
class CatalogUnitMoveCompletedBattleShockRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_ability_index_mapping(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        missing_ids = {army.player_id for army in armies} - set(indexes)
        if missing_ids:
            raise GameLifecycleError(
                "Catalog move-completed Battle-shock missing player ability index."
            )
        object.__setattr__(self, "ability_indexes_by_player_id", MappingProxyType(dict(indexes)))
        object.__setattr__(self, "armies", armies)

    def bindings(self) -> tuple[UnitMoveCompletedBattleShockHookBinding, ...]:
        if not _has_catalog_unit_move_completed_battle_shock_records(
            self.ability_indexes_by_player_id
        ):
            return ()
        return (
            UnitMoveCompletedBattleShockHookBinding(
                hook_id=CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
                source_id=CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
                handler=self.effect_handler,
            ),
        )

    def effect_handler(
        self,
        context: UnitMoveCompletedContext,
    ) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
        if type(context) is not UnitMoveCompletedContext:
            raise GameLifecycleError("Catalog move-completed Battle-shock requires context.")
        return _available_catalog_unit_move_completed_battle_shock_effects(
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            context=context,
        )


def catalog_unit_move_completed_battle_shock_hook_bindings(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    armies: tuple[ArmyDefinition, ...],
) -> tuple[UnitMoveCompletedBattleShockHookBinding, ...]:
    return CatalogUnitMoveCompletedBattleShockRuntime(
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        armies=armies,
    ).bindings()


def _available_catalog_unit_move_completed_battle_shock_effects(
    *,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
    context: UnitMoveCompletedContext,
) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
    if (
        context.completed_phase is not BattlePhase.CHARGE
        or context.movement_action != "charge_move"
    ):
        return ()
    source_rules_unit = rules_unit_view_by_id(
        state=context.state,
        unit_instance_id=context.triggering_unit_instance_id,
    )
    if source_rules_unit.owner_player_id != context.triggering_player_id:
        raise GameLifecycleError("Catalog move-completed Battle-shock source owner drifted.")
    index = ability_indexes_by_player_id.get(context.triggering_player_id)
    if index is None:
        raise GameLifecycleError("Catalog move-completed Battle-shock index is missing player.")
    source_model_ids = _placed_alive_model_instance_ids_for_rules_unit(
        state=context.state,
        rules_unit_instance_id=source_rules_unit.unit_instance_id,
    )
    if not source_model_ids:
        return ()
    target_candidates = _target_candidates(
        state=context.state,
        ruleset_descriptor=context.ruleset_descriptor,
        source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
    )
    if not target_candidates:
        return ()
    return _catalog_unit_move_completed_battle_shock_effects_for_source(
        ability_index=index,
        source_rules_unit=source_rules_unit,
        source_model_ids=source_model_ids,
        target_candidates=target_candidates,
        trigger_event_id=context.trigger_event_id,
        triggering_player_id=context.triggering_player_id,
        movement_action=context.movement_action,
    )


def historical_catalog_unit_move_completed_battle_shock_effects(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    ruleset_descriptor: RulesetDescriptor,
    trigger_event_id: str,
    triggering_unit_instance_id: str,
    triggering_player_id: str,
    movement_action: str,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
    """Recompute one trigger's effects from exact event-bound physical authority."""

    if type(historical) is not HistoricalBattleShockAuthorityContext:
        raise GameLifecycleError(
            "Historical catalog move-completed Battle-shock requires authority."
        )
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Historical catalog move-completed Battle-shock requires ruleset.")
    trigger_id = _validate_identifier("trigger_event_id", trigger_event_id)
    triggering_unit_id = _validate_identifier(
        "triggering_unit_instance_id",
        triggering_unit_instance_id,
    )
    triggering_player = _validate_identifier("triggering_player_id", triggering_player_id)
    action = _validate_identifier("movement_action", movement_action)
    if historical.phase is not BattlePhase.CHARGE or action != "charge_move":
        return ()
    source_rules_unit = historical.rules_unit(triggering_unit_id)
    if source_rules_unit.owner_player_id != triggering_player:
        raise GameLifecycleError(
            "Historical catalog move-completed Battle-shock source owner drifted."
        )
    index = ability_indexes_by_player_id.get(triggering_player)
    if index is None:
        raise GameLifecycleError(
            "Historical catalog move-completed Battle-shock index is missing player."
        )
    source_model_ids = historical.placed_alive_model_ids(source_rules_unit.unit_instance_id)
    if not source_model_ids:
        return ()
    target_candidates = _historical_target_candidates(
        historical=historical,
        ruleset_descriptor=ruleset_descriptor,
        source_rules_unit=source_rules_unit,
    )
    if not target_candidates:
        return ()
    return _catalog_unit_move_completed_battle_shock_effects_for_source(
        ability_index=index,
        source_rules_unit=_rules_unit_with_historical_wounds(
            historical=historical,
            rules_unit=source_rules_unit,
        ),
        source_model_ids=source_model_ids,
        target_candidates=target_candidates,
        trigger_event_id=trigger_id,
        triggering_player_id=triggering_player,
        movement_action=action,
    )


def _catalog_unit_move_completed_battle_shock_effects_for_source(
    *,
    ability_index: AbilityCatalogIndex,
    source_rules_unit: RulesUnitView,
    source_model_ids: tuple[str, ...],
    target_candidates: tuple[tuple[str, str], ...],
    trigger_event_id: str,
    triggering_player_id: str,
    movement_action: str,
) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
    source_model_id_set = frozenset(source_model_ids)
    effects: list[UnitMoveCompletedBattleShockEffect] = []
    for component in source_rules_unit.components:
        component_model_ids = tuple(
            sorted(
                model.model_instance_id
                for model in component.unit.own_models
                if model.is_alive and model.model_instance_id in source_model_id_set
            )
        )
        if not component_model_ids:
            continue
        for record in catalog_rule_unit_scoped_generic_records(
            ability_index=ability_index,
            unit=component.unit,
            current_model_instance_ids=component_model_ids,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        ):
            source_model_id = _source_model_instance_id_for_record(
                record=record,
                source_unit=component.unit,
                current_model_instance_ids=component_model_ids,
            )
            for clause in catalog_rule_clauses_from_record(record):
                effects.extend(
                    _effects_from_clause(
                        trigger_event_id=trigger_event_id,
                        triggering_player_id=triggering_player_id,
                        movement_action=movement_action,
                        record=record,
                        source_unit=component.unit,
                        source_model_instance_id=source_model_id,
                        source_rules_unit_instance_id=source_rules_unit.unit_instance_id,
                        target_candidates=target_candidates,
                        clause=clause,
                    )
                )
    return tuple(
        sorted(
            effects,
            key=lambda effect: (
                effect.trigger_event_id,
                effect.target_unit_instance_id,
                effect.source_rule_id,
                repr(effect.replay_payload),
            ),
        )
    )


def _effects_from_clause(
    *,
    trigger_event_id: str,
    triggering_player_id: str,
    movement_action: str,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_instance_id: str,
    source_rules_unit_instance_id: str,
    target_candidates: tuple[tuple[str, str], ...],
    clause: RuleClause,
) -> tuple[UnitMoveCompletedBattleShockEffect, ...]:
    _validate_unit(source_unit)
    source_rules_unit_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    if type(target_candidates) is not tuple:
        raise GameLifecycleError("Catalog move-completed Battle-shock targets must be a tuple.")
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog move-completed Battle-shock requires a clause.")
    if not clause_is_supported_unit_move_completed_battle_shock(clause):
        return ()
    supported_effects = tuple(
        (effect_index, effect)
        for effect_index, effect in enumerate(clause.effects)
        if effect_is_supported_unit_move_completed_battle_shock(effect)
    )
    if len(supported_effects) != 1:
        raise GameLifecycleError("Catalog move-completed Battle-shock requires one effect.")
    effect_index, _effect = supported_effects[0]
    return tuple(
        UnitMoveCompletedBattleShockEffect(
            hook_id=CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
            source_id=CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
            source_rule_id=record.definition.source_id,
            target_unit_instance_id=target_unit_id,
            target_player_id=target_player_id,
            trigger_event_id=trigger_event_id,
            replay_payload=_effect_payload(
                trigger_event_id=trigger_event_id,
                triggering_player_id=triggering_player_id,
                movement_action=movement_action,
                record=record,
                source_unit=source_unit,
                source_model_instance_id=source_model_instance_id,
                source_rules_unit_instance_id=source_rules_unit_id,
                clause=clause,
                effect_index=effect_index,
                target_unit_instance_id=target_unit_id,
                target_player_id=target_player_id,
            ),
        )
        for target_unit_id, target_player_id in target_candidates
    )


def _effect_payload(
    *,
    trigger_event_id: str,
    triggering_player_id: str,
    movement_action: str,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    source_model_instance_id: str,
    source_rules_unit_instance_id: str,
    clause: RuleClause,
    effect_index: int,
    target_unit_instance_id: str,
    target_player_id: str,
) -> JsonValue:
    source_rules_unit_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    if type(effect_index) is not int or effect_index < 0:
        raise GameLifecycleError(
            "Catalog move-completed Battle-shock effect_index must be non-negative."
        )
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    target_player = _validate_identifier("target_player_id", target_player_id)
    payload: dict[str, JsonValue] = {
        "effect_kind": "catalog_unit_move_completed_battle_shock",
        "consumer_id": CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
        "catalog_record_id": record.record_id,
        "ability_id": record.definition.ability_id,
        "ability_name": record.definition.name,
        "catalog_source_rule_id": record.definition.source_id,
        "player_id": _validate_identifier("triggering_player_id", triggering_player_id),
        "source_rules_unit_instance_id": source_rules_unit_id,
        "source_unit_instance_id": source_unit.unit_instance_id,
        "source_model_instance_id": _validate_identifier(
            "source_model_instance_id",
            source_model_instance_id,
        ),
        "clause_id": clause.clause_id,
        "effect_index": effect_index,
        "reason": "forced_by_army_rule",
        "target_unit_instance_id": target_unit_id,
        "target_player_id": target_player,
        "trigger_event_id": _validate_identifier("trigger_event_id", trigger_event_id),
        "movement_action": _validate_identifier("movement_action", movement_action),
    }
    if frozenset(payload) != CATALOG_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_REPLAY_PAYLOAD_KEYS:
        raise GameLifecycleError("Catalog move-completed Battle-shock replay schema drifted.")
    return validate_json_value(payload)


def _target_candidates(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    source_rules_unit_instance_id: str,
) -> tuple[tuple[str, str], ...]:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Catalog move-completed Battle-shock requires ruleset.")
    source_rules_unit_id = _validate_identifier(
        "source_rules_unit_instance_id",
        source_rules_unit_instance_id,
    )
    source_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=source_rules_unit_id)
    if not rules_unit_has_placed_alive_model(state=state, rules_unit=source_rules_unit):
        return ()
    scenario = battlefield_scenario_for_state(state=state)
    candidates: list[tuple[str, str]] = []
    for target_rules_unit in _rules_unit_views_for_other_players(
        state=state,
        player_id=source_rules_unit.owner_player_id,
    ):
        if not rules_unit_has_placed_alive_model(state=state, rules_unit=target_rules_unit):
            continue
        if scenario_rules_units_are_physically_engaged(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            first_unit_instance_id=source_rules_unit.unit_instance_id,
            second_unit_instance_id=target_rules_unit.unit_instance_id,
        ):
            candidates.append(
                (
                    target_rules_unit.unit_instance_id,
                    target_rules_unit.owner_player_id,
                )
            )
    return tuple(sorted(candidates))


def _historical_target_candidates(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    ruleset_descriptor: RulesetDescriptor,
    source_rules_unit: RulesUnitView,
) -> tuple[tuple[str, str], ...]:
    source_models = historical.geometry_models(source_rules_unit.unit_instance_id)
    if not source_models:
        return ()
    candidates = tuple(
        (
            target_rules_unit.unit_instance_id,
            target_rules_unit.owner_player_id,
        )
        for target_rules_unit in historical.all_rules_units()
        if target_rules_unit.owner_player_id != source_rules_unit.owner_player_id
        and geometry_models_are_physically_engaged(
            first_models=source_models,
            second_models=historical.geometry_models(target_rules_unit.unit_instance_id),
            ruleset_descriptor=ruleset_descriptor,
        )
    )
    return tuple(sorted(candidates))


def _source_model_instance_id_for_record(
    *,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
    current_model_instance_ids: tuple[str, ...],
) -> str:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError(
            "Catalog move-completed Battle-shock source requires an ability record."
        )
    if not current_model_instance_ids:
        raise GameLifecycleError(
            "Catalog move-completed Battle-shock source requires a current model."
        )
    if record.source_kind is AbilitySourceKind.DATASHEET:
        return current_model_instance_ids[0]
    if record.source_kind is AbilitySourceKind.WARGEAR:
        bearer_ids = catalog_rule_record_current_wargear_bearer_model_ids(
            record=record,
            unit=source_unit,
            current_model_instance_ids=current_model_instance_ids,
        )
        if not bearer_ids:
            raise GameLifecycleError(
                "Catalog move-completed Battle-shock wargear source has no current bearer."
            )
        return bearer_ids[0]
    raise GameLifecycleError(
        "Catalog move-completed Battle-shock record lacks unit-scoped source authority."
    )


def _rules_unit_with_historical_wounds(
    *,
    historical: HistoricalBattleShockAuthorityContext,
    rules_unit: RulesUnitView,
) -> RulesUnitView:
    wounds_by_model_id = {
        row.model_instance_id: row.wounds_remaining for row in historical.physical_models
    }
    try:
        components = tuple(
            replace(
                component,
                unit=replace(
                    component.unit,
                    own_models=tuple(
                        replace(
                            model,
                            wounds_remaining=wounds_by_model_id[model.model_instance_id],
                        )
                        for model in component.unit.own_models
                    ),
                ),
            )
            for component in rules_unit.components
        )
        return replace(rules_unit, components=components)
    except KeyError as exc:
        raise GameLifecycleError(
            "Historical catalog move-completed Battle-shock model inventory is incomplete."
        ) from exc


def _placed_alive_model_instance_ids_for_rules_unit(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> tuple[str, ...]:
    rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    if state.battlefield_state is None:
        return ()
    placed_model_ids = frozenset(state.battlefield_state.placed_model_ids())
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=rules_unit_id)
    return tuple(
        sorted(
            model.model_instance_id
            for model in rules_unit.alive_models()
            if model.model_instance_id in placed_model_ids
        )
    )


def _rules_unit_views_for_other_players(
    *,
    state: GameState,
    player_id: str,
) -> tuple[RulesUnitView, ...]:
    owner_player_id = _validate_identifier("player_id", player_id)
    views: list[RulesUnitView] = []
    seen: set[str] = set()
    for army in state.army_definitions:
        if army.player_id == owner_player_id:
            continue
        for unit in army.units:
            view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
            if view.unit_instance_id in seen:
                continue
            seen.add(view.unit_instance_id)
            views.append(view)
    return tuple(sorted(views, key=lambda view: view.unit_instance_id))


def _has_catalog_unit_move_completed_battle_shock_records(
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex],
) -> bool:
    return any(
        _record_can_trigger_catalog_unit_move_completed_battle_shock(record)
        for index in ability_indexes_by_player_id.values()
        for record in index.all_records()
    )


def _record_can_trigger_catalog_unit_move_completed_battle_shock(
    record: AbilityCatalogRecord,
) -> bool:
    if type(record) is not AbilityCatalogRecord:
        raise GameLifecycleError(
            "Catalog move-completed Battle-shock choices require ability records."
        )
    if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
        return False
    return any(
        clause_is_supported_unit_move_completed_battle_shock(clause)
        for clause in catalog_rule_clauses_from_record(record)
    )


def _validate_ability_index_mapping(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog move-completed Battle-shock indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in cast(Mapping[object, object], value).items():
        player_id = _validate_identifier("ability_indexes_by_player_id key", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "Catalog move-completed Battle-shock indexes must contain AbilityCatalogIndex."
            )
        indexes[player_id] = raw_index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog move-completed Battle-shock armies must be a tuple.")
    armies = cast(tuple[object, ...], value)
    if not all(type(army) is ArmyDefinition for army in armies):
        raise GameLifecycleError("Catalog move-completed Battle-shock armies must be a tuple.")
    return cast(tuple[ArmyDefinition, ...], armies)


def _validate_unit(unit: UnitInstance) -> UnitInstance:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Catalog move-completed Battle-shock requires a UnitInstance.")
    return unit
