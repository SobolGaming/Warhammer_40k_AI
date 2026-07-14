from __future__ import annotations

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    CatalogDescriptorConsumptionRecord,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari import army_rule

BATTLE_FOCUS_CATALOG_ABILITY_ID = "000009894"


def descriptor_consumption_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    return (
        CatalogDescriptorConsumptionRecord(
            ability_id=BATTLE_FOCUS_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.FACTION,
            semantic_categories=("faction.army_rule.battle_focus",),
            runtime_consumer_ids=(
                army_rule.FADE_BACK_HOOK_ID,
                army_rule.FLITTING_SHADOWS_HOOK_ID,
                army_rule.OPPORTUNITY_SEIZED_HOOK_ID,
                army_rule.STAR_ENGINES_HOOK_ID,
                army_rule.SUDDEN_STRIKE_HOOK_ID,
                army_rule.SWIFT_AS_THE_WIND_HOOK_ID,
            ),
        ),
    )
