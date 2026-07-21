from __future__ import annotations

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    CatalogDescriptorConsumptionRecord,
)

CORE_LEADER_CATALOG_ABILITY_ID = "000008346"
CORE_FIGHTS_FIRST_CATALOG_ABILITY_ID = "000008340"
CORE_INFILTRATORS_CATALOG_ABILITY_ID = "000008345"
CORE_SCOUTS_CATALOG_ABILITY_ID = "000008344"
CORE_FIGHTS_FIRST_CONSUMER_ID = "descriptor:fight-order:fights-first"
CORE_LEADER_ATTACHMENT_CONSUMER_ID = "descriptor:army-mustering:leader-attachment"
CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID = "descriptor:prebattle:infiltrators"
CORE_SCOUTS_PREBATTLE_CONSUMER_ID = "descriptor:prebattle:scouts"


def core_descriptor_consumption_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    return (
        CatalogDescriptorConsumptionRecord(
            ability_id=CORE_FIGHTS_FIRST_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.CORE,
            semantic_categories=("core.fights_first",),
            runtime_consumer_ids=(CORE_FIGHTS_FIRST_CONSUMER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=CORE_LEADER_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.CORE,
            semantic_categories=("core.leader",),
            runtime_consumer_ids=(CORE_LEADER_ATTACHMENT_CONSUMER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=CORE_INFILTRATORS_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.CORE,
            semantic_categories=("core.infiltrators",),
            runtime_consumer_ids=(CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=CORE_SCOUTS_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.CORE,
            semantic_categories=("core.scouts",),
            runtime_consumer_ids=(CORE_SCOUTS_PREBATTLE_CONSUMER_ID,),
        ),
    )
