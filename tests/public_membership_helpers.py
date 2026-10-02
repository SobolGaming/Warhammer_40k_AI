"""Real source-backed formation fixtures for public membership consumers."""

from dataclasses import replace
from typing import cast

from tests.phase11c_command_phase_helpers import (
    default_unit_selection,
    phase11c_config,
    unit_selection,
)
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.list_validation import AttachmentDeclaration
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14 as keyword_source,
)


def attached_split_config() -> GameConfig:
    # Same reviewed Tactical Squad Combat Squads source shape used by the
    # engine split tests; this canonical fixture claims no faction support.
    source = "test-source:tactical-squad:combat-squads"
    text = (
        "At the start of the Declare Battle Formations step, before any units have been set up, "
        "this unit can be split into two units, each containing five models."
    )
    rule = compile_rule_source_text(
        RuleSourceText.from_raw(
            source_id=source, raw_text=text, objective_scope=ObjectiveRuleScope.NON_CORE_RULES
        ),
        source_keyword_sequence_parts=keyword_source.canonical_datasheet_keyword_sequence_parts(),
    ).rule_ir
    ability = DatasheetAbilityDescriptor(
        ability_id="test-combat-squads",
        name="Combat Squads",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
    config = phase11c_config(
        player_a_units=(
            default_unit_selection("bodyguard"),
            unit_selection(
                unit_selection_id="leader",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
        ),
        player_a_attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader", bodyguard_unit_selection_id="bodyguard"
            ),
        ),
    )
    catalog = replace(
        config.army_catalog,
        datasheets=tuple(
            replace(sheet, abilities=(*sheet.abilities, ability))
            if sheet.datasheet_id == "core-intercessor-like-infantry"
            else sheet
            for sheet in config.army_catalog.datasheets
        ),
    )
    return replace(config, army_catalog=catalog)
