from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    CatalogAnyPhaseOncePerBattleRuntime,
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
    CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
    CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
    clause_is_conditional_lone_operative,
    clause_is_fight_selected_weapon_ability_choice,
    clause_is_passive_characteristic_modifier,
    clause_is_stealth_aura,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_clauses_from_record,
    catalog_rule_record_source_matches_unit,
)
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventHandlerBinding,
    RuntimeContentEventSubscription,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
    FightUnitSelectedGrantBinding,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
    rule_ir_from_execution_payload,
)
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_modified_weapon_profile,
)
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierBinding,
    HitRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    UnitCharacteristicModifierBinding,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectSpec,
    RuleIR,
    parameter_payload,
)


@dataclass(frozen=True, slots=True)
class _CatalogClauseSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    rule_ir: RuleIR

    @property
    def binding_id(self) -> str:
        return f"catalog-ir:datasheet:{self.unit.unit_instance_id}:{self.clause.clause_id}"


@dataclass(frozen=True, slots=True)
class CatalogDatasheetRuleRuntime:
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex]
    armies: tuple[ArmyDefinition, ...]

    def __post_init__(self) -> None:
        indexes = _validate_indexes(self.ability_indexes_by_player_id)
        armies = _validate_armies(self.armies)
        if set(indexes) != {army.player_id for army in armies}:
            raise GameLifecycleError("Catalog datasheet runtime indexes must match armies.")
        object.__setattr__(self, "ability_indexes_by_player_id", indexes)
        object.__setattr__(self, "armies", armies)

    def unit_characteristic_modifier_bindings(
        self,
    ) -> tuple[UnitCharacteristicModifierBinding, ...]:
        return tuple(
            UnitCharacteristicModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._unit_characteristic_handler(source),
            )
            for source in self._sources(clause_is_passive_characteristic_modifier)
            if _source_characteristic(source) is Characteristic.TOUGHNESS
        )

    def event_handler_bindings(self) -> tuple[RuntimeContentEventHandlerBinding, ...]:
        return CatalogAnyPhaseOncePerBattleRuntime(
            self.ability_indexes_by_player_id, self.armies
        ).event_handler_bindings()

    def event_subscriptions(self) -> tuple[RuntimeContentEventSubscription, ...]:
        return CatalogAnyPhaseOncePerBattleRuntime(
            self.ability_indexes_by_player_id, self.armies
        ).event_subscriptions()

    def movement_budget_modifier_bindings(self) -> tuple[MovementBudgetModifierBinding, ...]:
        return tuple(
            MovementBudgetModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._movement_handler(source),
            )
            for source in self._sources(clause_is_passive_characteristic_modifier)
            if _source_characteristic(source) is Characteristic.MOVEMENT
        )

    def weapon_profile_modifier_bindings(self) -> tuple[WeaponProfileModifierBinding, ...]:
        return tuple(
            WeaponProfileModifierBinding(
                modifier_id=source.binding_id,
                source_id=source.rule_ir.source_id,
                handler=self._weapon_handler(source),
            )
            for source in self._sources(clause_is_passive_characteristic_modifier)
            if _source_characteristic(source) in {Characteristic.ATTACKS, Characteristic.STRENGTH}
        )

    def hit_roll_modifier_bindings(self) -> tuple[HitRollModifierBinding, ...]:
        sources = self._sources(clause_is_stealth_aura)
        if not sources:
            return ()
        return (
            HitRollModifierBinding(
                modifier_id=CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
                source_id=CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
                handler=self._stealth_handler(sources),
            ),
        )

    def shooting_target_restriction_bindings(
        self,
    ) -> tuple[ShootingTargetRestrictionHookBinding, ...]:
        sources = self._sources(clause_is_conditional_lone_operative)
        if not sources:
            return ()
        return (
            ShootingTargetRestrictionHookBinding(
                hook_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                source_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                handler=self._lone_operative_handler(sources),
            ),
        )

    def fight_unit_selected_grant_bindings(
        self,
    ) -> tuple[FightUnitSelectedGrantBinding, ...]:
        bindings: list[FightUnitSelectedGrantBinding] = []
        for source in self._sources(clause_is_fight_selected_weapon_ability_choice):
            for effect in source.clause.effects:
                option_id = _required_string(
                    parameter_payload(effect.parameters), "selection_option_id"
                )
                hook_id = f"{source.binding_id}:{option_id}"
                bindings.append(
                    FightUnitSelectedGrantBinding(
                        hook_id=hook_id,
                        source_id=source.rule_ir.source_id,
                        handler=self._fight_grant_handler(
                            source=source,
                            effect=effect,
                            hook_id=hook_id,
                        ),
                    )
                )
        return tuple(bindings)

    def _sources(self, predicate: Callable[[RuleClause], bool]) -> tuple[_CatalogClauseSource, ...]:
        sources: list[_CatalogClauseSource] = []
        for army in self.armies:
            index = self.ability_indexes_by_player_id[army.player_id]
            for record in index.all_records():
                if record.definition.handler_id != GENERIC_RULE_IR_ABILITY_HANDLER_ID:
                    continue
                rule_ir = rule_ir_from_execution_payload(record.definition.replay_payload)
                for unit in army.units:
                    if not catalog_rule_record_source_matches_unit(
                        record=record,
                        unit=unit,
                        current_model_instance_ids=unit.own_model_ids(),
                    ):
                        continue
                    sources.extend(
                        _CatalogClauseSource(
                            player_id=army.player_id,
                            record=record,
                            unit=unit,
                            clause=clause,
                            rule_ir=rule_ir,
                        )
                        for clause in catalog_rule_clauses_from_record(record)
                        if predicate(clause)
                    )
        return tuple(sorted(sources, key=lambda source: source.binding_id))

    def _unit_characteristic_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[UnitCharacteristicModifierContext], int]:
        def handler(context: UnitCharacteristicModifierContext) -> int:
            if not _source_applies_to_rules_unit(
                source=source, context_unit_id=context.unit_instance_id, state=context.state
            ):
                return context.current_value
            characteristic, delta = _source_characteristic_delta(source)
            if characteristic is not context.characteristic or not _source_keyword_gate_applies(
                source
            ):
                return context.current_value
            return context.current_value + delta

        return handler

    def _movement_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[MovementBudgetModifierContext], float]:
        def handler(context: MovementBudgetModifierContext) -> float:
            if not _source_applies_to_rules_unit(
                source=source, context_unit_id=context.unit_instance_id, state=context.state
            ):
                return context.current_movement_inches
            if (
                context.model_instance_id not in source.unit.own_model_ids()
                or not _source_keyword_gate_applies(source)
            ):
                return context.current_movement_inches
            return context.current_movement_inches + float(_source_characteristic_delta(source)[1])

        return handler

    def _weapon_handler(
        self, source: _CatalogClauseSource
    ) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
        def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
            if not _source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.attacking_unit_instance_id,
                state=context.state,
            ):
                return context.weapon_profile
            if (
                context.attacker_model_instance_id not in source.unit.own_model_ids()
                or not _source_keyword_gate_applies(source)
            ):
                return context.weapon_profile
            return rule_ir_modified_weapon_profile(
                parameters=parameter_payload(source.clause.effects[0].parameters),
                profile=context.weapon_profile,
                source_id=source.rule_ir.source_id,
            )

        return handler

    def _stealth_handler(
        self, sources: tuple[_CatalogClauseSource, ...]
    ) -> Callable[[HitRollModifierContext], int]:
        def handler(context: HitRollModifierContext) -> int:
            if (
                context.target_unit_instance_id == context.attacking_unit_instance_id
                or context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE
            ):
                return 0
            target = rules_unit_view_by_id(
                state=context.state, unit_instance_id=context.target_unit_instance_id
            )
            for source in sources:
                if (
                    not _source_is_alive(source)
                    or target.owner_player_id != source.player_id
                    or not _rules_unit_has_required_aura_keyword(target, source.clause)
                ):
                    continue
                if _rules_units_within(
                    context.state,
                    source.unit.unit_instance_id,
                    target.unit_instance_id,
                    _clause_distance(source.clause),
                ):
                    return -1
            return 0

        return handler

    def _lone_operative_handler(
        self, sources: tuple[_CatalogClauseSource, ...]
    ) -> Callable[[ShootingTargetRestrictionContext], TargetRestriction | None]:
        def handler(context: ShootingTargetRestrictionContext) -> TargetRestriction | None:
            for source in sources:
                if not _source_applies_to_rules_unit(
                    source=source,
                    context_unit_id=context.target_unit_instance_id,
                    state=context.state,
                ) or not _friendly_keyworded_unit_within(source=source, state=context.state):
                    continue
                if _rules_units_within(
                    context.state,
                    context.attacking_unit_instance_id,
                    context.target_unit_instance_id,
                    12,
                    attacker_model_instance_id=context.attacker_model_instance_id,
                ):
                    return None
                return TargetRestriction(
                    hook_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                    source_id=CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                    violation_code="conditional_lone_operative_range",
                    message=(
                        'Target has Lone Operative and the attacking model is not within 12".'
                    ),
                    replay_payload={
                        "consumer_id": CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                        "catalog_record_id": source.record.record_id,
                        "source_rule_id": source.rule_ir.source_id,
                        "source_unit_instance_id": source.unit.unit_instance_id,
                        "target_unit_instance_id": context.target_unit_instance_id,
                    },
                )
            return None

        return handler

    def _fight_grant_handler(
        self, *, source: _CatalogClauseSource, effect: RuleEffectSpec, hook_id: str
    ) -> Callable[[FightUnitSelectedContext], FightUnitSelectedGrant | None]:
        def handler(context: FightUnitSelectedContext) -> FightUnitSelectedGrant | None:
            if context.player_id != source.player_id or not _source_applies_to_rules_unit(
                source=source, context_unit_id=context.unit_instance_id, state=context.state
            ):
                return None
            source_model_id = _alive_source_model_id(source)
            execution_context = RuleExecutionContext(
                game_id=context.state.game_id,
                player_id=source.player_id,
                battle_round=context.state.battle_round,
                phase=BattlePhaseKind.FIGHT,
                active_player_id=context.state.active_player_id,
                timing_window_id="selected_to_fight",
                source_unit_instance_id=context.unit_instance_id,
                source_model_instance_id=source_model_id,
                target_unit_instance_ids=(context.unit_instance_id,),
                source_keywords=tuple(
                    sorted((*source.unit.keywords, *source.unit.faction_keywords))
                ),
                trigger_payload={
                    "catalog_record_id": source.record.record_id,
                    "consumer_id": CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
                    "activation_request_id": context.request_id,
                    "activation_result_id": context.result_id,
                },
                state=context.state,
                event_log=None,
                record_persisting_effects=False,
            )
            parameters = parameter_payload(effect.parameters)
            return FightUnitSelectedGrant(
                hook_id=hook_id,
                source_id=source.rule_ir.source_id,
                label=_required_string(parameters, "weapon_ability"),
                replay_payload={
                    "catalog_record_id": source.record.record_id,
                    "clause_id": source.clause.clause_id,
                    "rule_ir_hash": source.rule_ir.ir_hash(),
                },
                unit_effect_payload=generic_rule_effect_payload(
                    rule_ir=source.rule_ir,
                    clause=source.clause,
                    effect=effect,
                    context=execution_context,
                    target_unit_instance_ids=(context.unit_instance_id,),
                ),
                unit_effect_expiration="end_phase",
                decline_allowed=False,
            )

        return handler


def _source_characteristic(source: _CatalogClauseSource) -> Characteristic:
    return _source_characteristic_delta(source)[0]


def _source_characteristic_delta(source: _CatalogClauseSource) -> tuple[Characteristic, int]:
    parameters = parameter_payload(source.clause.effects[0].parameters)
    try:
        characteristic = Characteristic(_required_string(parameters, "characteristic"))
    except ValueError as exc:
        raise GameLifecycleError("Catalog datasheet characteristic is invalid.") from exc
    delta = parameters.get("delta")
    if type(delta) is not int:
        raise GameLifecycleError("Catalog datasheet characteristic delta must be integer.")
    return characteristic, delta


def _source_keyword_gate_applies(source: _CatalogClauseSource) -> bool:
    required = {
        _required_string(parameter_payload(condition.parameters), "required_keyword")
        for condition in source.clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    }
    keywords = {*source.unit.keywords, *source.unit.faction_keywords}
    return required.issubset(keywords)


def _source_applies_to_rules_unit(
    *, source: _CatalogClauseSource, context_unit_id: str, state: object
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet runtime requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=context_unit_id)
    return (
        source.unit.unit_instance_id in rules_unit.component_unit_instance_ids
        and _source_is_alive(source)
    )


def _source_is_alive(source: _CatalogClauseSource) -> bool:
    return any(model.is_alive for model in source.unit.own_models)


def _alive_source_model_id(source: _CatalogClauseSource) -> str:
    model = next((model for model in source.unit.own_models if model.is_alive), None)
    if model is None:
        raise GameLifecycleError("Catalog datasheet source model is destroyed.")
    return model.model_instance_id


def _friendly_keyworded_unit_within(*, source: _CatalogClauseSource, state: object) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Catalog conditional ability requires GameState.")
    distance_condition = next(
        condition
        for condition in source.clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    parameters = parameter_payload(distance_condition.parameters)
    required = parameters.get("required_keyword_sequence")
    if not isinstance(required, tuple) or not all(type(value) is str for value in required):
        raise GameLifecycleError("Catalog conditional ability keyword sequence is malformed.")
    required_tokens = set(required)
    seen: set[str] = set()
    for army in state.army_definitions:
        if army.player_id != source.player_id:
            continue
        for unit in army.units:
            view = rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id)
            if view.unit_instance_id in seen:
                continue
            seen.add(view.unit_instance_id)
            keywords = {*view.keywords, *view.faction_keywords}
            if required_tokens.issubset(keywords) and _rules_units_within(
                state,
                source.unit.unit_instance_id,
                view.unit_instance_id,
                _clause_distance(source.clause),
            ):
                return True
    return False


def _rules_unit_has_required_aura_keyword(view: RulesUnitView, clause: RuleClause) -> bool:
    required = {
        _required_string(parameter_payload(condition.parameters), "required_keyword")
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.KEYWORD_GATE
    }
    keywords = {*view.keywords, *view.faction_keywords}
    return required.issubset(keywords)


def _clause_distance(clause: RuleClause) -> float:
    condition = next(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    value = parameter_payload(condition.parameters).get("distance_inches")
    if not isinstance(value, int | float) or type(value) is bool or value <= 0:
        raise GameLifecycleError("Catalog datasheet distance must be positive numeric.")
    return float(value)


def _rules_units_within(
    state: object,
    first_unit_id: str,
    second_unit_id: str,
    distance: float,
    *,
    attacker_model_instance_id: str | None = None,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState or state.battlefield_state is None:
        raise GameLifecycleError("Catalog datasheet range query requires battlefield state.")
    return target_within_shooting_selection_range(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        attacking_unit_instance_id=first_unit_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=second_unit_id,
        max_range_inches=distance,
    )


def _required_string(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Catalog datasheet {key} must be a non-empty string.")
    return value


def _validate_indexes(value: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(value, Mapping):
        raise GameLifecycleError("Catalog datasheet runtime indexes must be a mapping.")
    indexes: dict[str, AbilityCatalogIndex] = {}
    for player_id, index in cast(Mapping[object, object], value).items():
        if type(player_id) is not str or type(index) is not AbilityCatalogIndex:
            raise GameLifecycleError("Catalog datasheet runtime index entry is invalid.")
        indexes[player_id] = index
    return MappingProxyType(indexes)


def _validate_armies(value: object) -> tuple[ArmyDefinition, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("Catalog datasheet runtime requires ArmyDefinition tuple.")
    armies = cast(tuple[object, ...], value)
    if not all(type(army) is ArmyDefinition for army in armies):
        raise GameLifecycleError("Catalog datasheet runtime requires ArmyDefinition tuple.")
    return cast(tuple[ArmyDefinition, ...], armies)
