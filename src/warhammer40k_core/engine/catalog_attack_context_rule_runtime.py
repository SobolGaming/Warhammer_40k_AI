from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.abilities import AbilityCatalogRecord, AbilitySourceKind
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_current_placed_alive_model_instance_ids_for_unit,
    catalog_rule_record_current_wargear_bearer_model_ids,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_weapon_ability_granted_profile,
    rule_ir_weapon_selector_applies,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR, parameter_payload


@dataclass(frozen=True, slots=True)
class CatalogDatasheetClauseSource:
    player_id: str
    record: AbilityCatalogRecord
    unit: UnitInstance
    clause: RuleClause
    rule_ir: RuleIR

    @property
    def binding_id(self) -> str:
        return f"catalog-ir:datasheet:{self.unit.unit_instance_id}:{self.clause.clause_id}"


def half_range_weapon_ability_handler(
    source: CatalogDatasheetClauseSource,
) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
    def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
        if not source_applies_to_rules_unit(
            source=source,
            context_unit_id=context.attacking_unit_instance_id,
            state=context.state,
        ):
            return context.weapon_profile
        if context.attacker_model_instance_id not in current_source_model_ids(
            state=context.state,
            source=source,
        ):
            return context.weapon_profile
        range_profile = context.weapon_profile.range_profile
        if range_profile.kind is not RangeProfileKind.DISTANCE:
            return context.weapon_profile
        distance_inches = range_profile.distance_inches
        if type(distance_inches) is not int or distance_inches <= 0:
            raise GameLifecycleError(
                "Catalog half-range weapon ability requires positive ranged distance."
            )
        if not rules_units_within(
            context.state,
            context.attacking_unit_instance_id,
            context.target_unit_instance_id,
            distance_inches / 2.0,
            attacker_model_instance_id=context.attacker_model_instance_id,
        ):
            return context.weapon_profile
        parameters = parameter_payload(source.clause.effects[0].parameters)
        if not rule_ir_weapon_selector_applies(
            parameters=parameters,
            profile=context.weapon_profile,
        ):
            return context.weapon_profile
        return rule_ir_weapon_ability_granted_profile(
            parameters=parameters,
            profile=context.weapon_profile,
            source_id=source.rule_ir.source_id,
        )

    return handler


def defensive_strength_toughness_wound_handler(
    source: CatalogDatasheetClauseSource,
) -> Callable[[WoundRollModifierContext], int]:
    def handler(context: WoundRollModifierContext) -> int:
        if not source_applies_to_rules_unit(
            source=source,
            context_unit_id=context.target_unit_instance_id,
            state=context.state,
        ):
            return 0
        source_model_ids = current_source_model_ids(state=context.state, source=source)
        if not source_model_ids:
            return 0
        if len(source_model_ids) != 1:
            raise GameLifecycleError(
                "Catalog THIS_MODEL defensive wound modifier requires one current source model."
            )
        if context.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE:
            return 0
        if context.strength <= context.toughness:
            return 0
        delta = parameter_payload(source.clause.effects[0].parameters).get("delta")
        if type(delta) is not int:
            raise GameLifecycleError("Catalog defensive wound delta must be integer.")
        return delta

    return handler


def source_applies_to_rules_unit(
    *,
    source: CatalogDatasheetClauseSource,
    context_unit_id: str,
    state: object,
) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet runtime requires GameState.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=context_unit_id)
    return source.unit.unit_instance_id in rules_unit.component_unit_instance_ids and bool(
        current_source_model_ids(state=state, source=source)
    )


def current_source_model_ids(
    *,
    state: object,
    source: CatalogDatasheetClauseSource,
) -> tuple[str, ...]:
    if type(state) is not GameState:
        raise GameLifecycleError("Catalog datasheet source query requires GameState.")
    current_model_ids = catalog_rule_current_placed_alive_model_instance_ids_for_unit(
        state=state,
        unit=source.unit,
    )
    if source.record.source_kind is not AbilitySourceKind.WARGEAR:
        return current_model_ids
    return catalog_rule_record_current_wargear_bearer_model_ids(
        record=source.record,
        unit=source.unit,
        current_model_instance_ids=current_model_ids,
    )


def rules_units_within(
    state: GameState,
    first_unit_id: str,
    second_unit_id: str,
    distance: float,
    *,
    attacker_model_instance_id: str | None = None,
) -> bool:
    if type(state) is not GameState or state.battlefield_state is None:
        raise GameLifecycleError("Catalog datasheet range query requires battlefield state.")
    return target_within_shooting_selection_range(
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=state.battlefield_state,
        ),
        attacking_unit_instance_id=first_unit_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=second_unit_id,
        max_range_inches=distance,
    )
