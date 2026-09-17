from __future__ import annotations

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    CatalogDescriptorConsumptionRecord,
)
from warhammer40k_core.engine.core_catalog_ability_ids import (
    CORE_FIGHTS_FIRST_CATALOG_ABILITY_ID,
    CORE_INFILTRATORS_CATALOG_ABILITY_ID,
    CORE_LEADER_CATALOG_ABILITY_ID,
    CORE_LONE_OPERATIVE_CATALOG_ABILITY_ID,
    CORE_SCOUTS_CATALOG_ABILITY_ID,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_super_heavy_walker_2026_09 as movement_source,
)

CORE_FIGHTS_FIRST_CONSUMER_ID = "descriptor:fight-order:fights-first"
CORE_LEADER_ATTACHMENT_CONSUMER_ID = "descriptor:army-mustering:leader-attachment"
CORE_LONE_OPERATIVE_SHOOTING_TARGET_CONSUMER_ID = "descriptor:shooting-target:lone-operative"
CORE_INFILTRATORS_PREBATTLE_CONSUMER_ID = "descriptor:prebattle:infiltrators"
CORE_SCOUTS_PREBATTLE_CONSUMER_ID = "descriptor:prebattle:scouts"


def core_descriptor_consumption_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    movement_records = tuple(
        CatalogDescriptorConsumptionRecord(
            ability_id=ability_id,
            source_kind=CatalogAbilitySourceKind.CORE,
            semantic_categories=("core.movement_ability",),
            runtime_consumer_ids=movement_source.source_rules()[0].runtime_consumer_ids,
        )
        for descriptor in movement_source.movement_abilities()
        for ability_id in descriptor.ability_ids
    )
    return (
        *movement_records,
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
            ability_id=CORE_LONE_OPERATIVE_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.CORE,
            semantic_categories=("core.lone_operative",),
            runtime_consumer_ids=(CORE_LONE_OPERATIVE_SHOOTING_TARGET_CONSUMER_ID,),
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
