from __future__ import annotations

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    CatalogDescriptorConsumptionRecord,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    army_rule,
)

SHADOW_OF_CHAOS_CATALOG_ABILITY_ID = "000008433"


def descriptor_consumption_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    return (
        CatalogDescriptorConsumptionRecord(
            ability_id=SHADOW_OF_CHAOS_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.FACTION,
            semantic_categories=("faction.army_rule.shadow_of_chaos",),
            runtime_consumer_ids=(army_rule.HOOK_ID,),
        ),
    )
