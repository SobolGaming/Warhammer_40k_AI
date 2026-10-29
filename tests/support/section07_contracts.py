"""Explicit constructed timing text on fresh native models; no fabricated policy."""

from dataclasses import replace
from typing import cast

from tests.support.section02_fixtures import Section02Definitions

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.ability_catalog import catalog_ability_records_from_catalog
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText

SOURCE = "constructed:section07:phase-timing"


def selected_effect_runtime(
    definitions: Section02Definitions, state: GameState, qualification: str
) -> CatalogSelectedTargetEffectRuntime:
    text = (
        f'At the start of {qualification}Fight phase, select one enemy unit within 100" '
        "of this model. Until the end of the phase, each time this model makes a melee "
        "attack that targets that unit, add 1 to the Damage characteristic of that attack."
    )
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=SOURCE, raw_text=text, objective_scope=ObjectiveRuleScope.CORE_RULES
        ),
        source_keyword_sequence_parts=("INFANTRY", "CHARACTER"),
    ).rule_ir
    assert not rule.diagnostics
    ability = DatasheetAbilityDescriptor(
        ability_id=SOURCE,
        name="Constructed Core timing contract",
        source_id=SOURCE,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    catalog = replace(
        definitions.package.army_catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, ability))
            if sheet.datasheet_id == "000004078"
            else sheet
            for sheet in definitions.package.army_catalog.datasheets
        ),
    )
    state.army_definitions[:] = [
        replace(
            army,
            units=tuple(
                replace(unit, datasheet_abilities=(*unit.datasheet_abilities, ability))
                for unit in army.units
            ),
        )
        if army.player_id == "owner"
        else army
        for army in state.army_definitions
    ]
    index = AbilityCatalogIndex.from_records(
        tuple(
            record
            for record in catalog_ability_records_from_catalog(catalog)
            if record.definition.source_id == SOURCE
        )
    )
    assert index.all_records()
    return CatalogSelectedTargetEffectRuntime(
        {"owner": index, "opponent": AbilityCatalogIndex.from_records(())},
        tuple(state.army_definitions),
    )
