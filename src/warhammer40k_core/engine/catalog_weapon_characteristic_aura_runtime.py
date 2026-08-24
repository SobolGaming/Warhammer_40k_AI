from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    current_source_model_ids,
)
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    CatalogChargedMeleeWeaponCharacteristicAuraDescriptor,
)
from warhammer40k_core.engine.fights_first import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_aura_resolution import aura_affected_unit_ids
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_modified_weapon_profile,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.rules.rule_ir import parameter_payload


def charged_melee_weapon_characteristic_aura_binding(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogChargedMeleeWeaponCharacteristicAuraDescriptor,
) -> WeaponProfileModifierBinding:
    return WeaponProfileModifierBinding(
        modifier_id=f"{source.binding_id}:charged-melee-weapon-characteristic-aura",
        source_id=source.rule_ir.source_id,
        handler=_charged_melee_weapon_characteristic_aura_handler(source, descriptor),
    )


def _charged_melee_weapon_characteristic_aura_handler(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogChargedMeleeWeaponCharacteristicAuraDescriptor,
) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
    def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
        if type(context.state) is not GameState:
            raise GameLifecycleError("Catalog weapon aura requires GameState.")
        aura_rule_source_id = source.rule_ir.source_id
        if aura_rule_source_id in context.weapon_profile.source_ids:
            return context.weapon_profile
        source_model_ids = current_source_model_ids(state=context.state, source=source)
        if not source_model_ids:
            return context.weapon_profile
        if len(source_model_ids) != 1:
            raise GameLifecycleError(
                "Catalog this-model weapon aura requires exactly one current source model."
            )
        attacking_rules_unit = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=context.attacking_unit_instance_id,
        )
        if attacking_rules_unit.unit_instance_id not in aura_affected_unit_ids(
            clause=source.clause,
            state=context.state,
            source_unit_instance_id=source.unit.unit_instance_id,
            source_model_instance_id=source_model_ids[0],
        ):
            return context.weapon_profile
        if not _rules_unit_charged_this_turn(
            state=context.state,
            unit_instance_id=attacking_rules_unit.unit_instance_id,
        ):
            return context.weapon_profile
        effect_parameters = parameter_payload(source.clause.effects[0].parameters)
        if (
            effect_parameters.get("characteristic") != descriptor.characteristic.value
            or effect_parameters.get("delta") != descriptor.delta
        ):
            raise GameLifecycleError("Catalog weapon aura descriptor drifted.")
        return rule_ir_modified_weapon_profile(
            parameters=effect_parameters,
            profile=context.weapon_profile,
            source_id=aura_rule_source_id,
        )

    return handler


def _rules_unit_charged_this_turn(*, state: GameState, unit_instance_id: str) -> bool:
    return FightsFirstRegistry.from_state(state).has_unit_lineage(
        state=state,
        unit_instance_id=unit_instance_id,
        effect_kind=CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    )
