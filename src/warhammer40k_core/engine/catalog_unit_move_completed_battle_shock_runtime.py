from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
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
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedBattleShockEffect,
    UnitMoveCompletedBattleShockHookBinding,
    UnitMoveCompletedContext,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.rule_ir import RuleClause


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
            ability_index=index,
            unit=component.unit,
            current_model_instance_ids=component_model_ids,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        ):
            for clause in catalog_rule_clauses_from_record(record):
                effects.extend(
                    _effects_from_clause(
                        context=context,
                        record=record,
                        source_unit=component.unit,
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
    context: UnitMoveCompletedContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
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
            trigger_event_id=context.trigger_event_id,
            replay_payload=_effect_payload(
                context=context,
                record=record,
                source_unit=source_unit,
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
    context: UnitMoveCompletedContext,
    record: AbilityCatalogRecord,
    source_unit: UnitInstance,
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
    return validate_json_value(
        {
            "effect_kind": "catalog_unit_move_completed_battle_shock",
            "consumer_id": CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,
            "catalog_record_id": record.record_id,
            "ability_id": record.definition.ability_id,
            "ability_name": record.definition.name,
            "catalog_source_rule_id": record.definition.source_id,
            "player_id": context.triggering_player_id,
            "source_rules_unit_instance_id": source_rules_unit_id,
            "source_unit_instance_id": source_unit.unit_instance_id,
            "clause_id": clause.clause_id,
            "effect_index": effect_index,
            "reason": "forced_by_army_rule",
            "target_unit_instance_id": target_unit_id,
            "target_player_id": target_player,
            "trigger_event_id": context.trigger_event_id,
            "movement_action": context.movement_action,
        }
    )


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
    source_models = _placed_alive_geometry_models_for_rules_unit(
        state=state,
        rules_unit_instance_id=source_rules_unit.unit_instance_id,
    )
    if not source_models:
        return ()
    candidates: list[tuple[str, str]] = []
    for target_rules_unit in _rules_unit_views_for_other_players(
        state=state,
        player_id=source_rules_unit.owner_player_id,
    ):
        target_models = _placed_alive_geometry_models_for_rules_unit(
            state=state,
            rules_unit_instance_id=target_rules_unit.unit_instance_id,
        )
        if not target_models:
            continue
        if any(
            source_model.is_within_engagement_range(
                target_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            )
            for source_model in source_models
            for target_model in target_models
        ):
            candidates.append(
                (
                    target_rules_unit.unit_instance_id,
                    target_rules_unit.owner_player_id,
                )
            )
    return tuple(sorted(candidates))


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


def _placed_alive_geometry_models_for_rules_unit(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    rules_unit_id = _validate_identifier("rules_unit_instance_id", rules_unit_instance_id)
    if state.battlefield_state is None:
        return ()
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    model_by_id = {
        model.model_instance_id: model
        for model in rules_unit_view_by_id(
            state=state,
            unit_instance_id=rules_unit_id,
        ).alive_models()
    }
    models: list[GeometryModel] = []
    for model_id in _placed_alive_model_instance_ids_for_rules_unit(
        state=state,
        rules_unit_instance_id=rules_unit_id,
    ):
        placement = state.battlefield_state.model_placement_by_id(model_id)
        model = model_by_id.get(model_id)
        if model is None:
            raise GameLifecycleError("Catalog move-completed Battle-shock model placement drifted.")
        if scenario.model_instance_for_placement(placement).model_instance_id != model_id:
            raise GameLifecycleError(
                "Catalog move-completed Battle-shock placement references wrong model."
            )
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


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
