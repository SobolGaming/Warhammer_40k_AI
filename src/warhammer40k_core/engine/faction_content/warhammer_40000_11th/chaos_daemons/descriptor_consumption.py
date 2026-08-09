from __future__ import annotations

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.engine.catalog_descriptor_consumption import (
    CatalogDescriptorConsumptionRecord,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons import (
    army_rule,
    datasheets,
)

SHADOW_OF_CHAOS_CATALOG_ABILITY_ID = "000008433"


def descriptor_consumption_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    return (
        CatalogDescriptorConsumptionRecord(
            ability_id=SHADOW_OF_CHAOS_CATALOG_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.FACTION,
            semantic_categories=("faction.army_rule.shadow_of_chaos",),
            runtime_consumer_ids=(army_rule.JULY_HOOK_ID,),
        ),
        *(
            CatalogDescriptorConsumptionRecord(
                ability_id=ability_id,
                source_kind=CatalogAbilitySourceKind.DATASHEET,
                semantic_categories=("datasheet.aura.shadow_of_chaos",),
                runtime_consumer_ids=(army_rule.JULY_HOOK_ID,),
            )
            for ability_id in datasheets.GREATER_DAEMON_SHADOW_AURA_ABILITY_IDS
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.BLOODTHIRSTER_DAEMON_LORD_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.aura.melee_hit_roll_modifier",),
            runtime_consumer_ids=(datasheets.KHORNE_HIT_MODIFIER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.BLOODTHIRSTER_RELENTLESS_CARNAGE_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.fight_phase_end.mortal_wounds",),
            runtime_consumer_ids=(
                datasheets.RELENTLESS_CARNAGE_HOOK_ID,
                datasheets.RELENTLESS_CARNAGE_FNP_HOOK_ID,
            ),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.SKARBRAND_RAGE_EMBODIED_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.aura.melee_attacks_modifier",),
            runtime_consumer_ids=(datasheets.RAGE_EMBODIED_ATTACKS_MODIFIER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.LORD_OF_CHANGE_DAEMON_LORD_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.aura.ranged_strength_modifier",),
            runtime_consumer_ids=(datasheets.TZEENTCH_STRENGTH_MODIFIER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.PLAGUEBEARERS_INFECTED_OUTBREAK_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.objective_control.sticky",),
            runtime_consumer_ids=(datasheets.INFECTED_OUTBREAK_HOOK_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.KEEPER_DAEMON_LORD_SLAANESH_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.aura.melee_armor_penetration_modifier",),
            runtime_consumer_ids=(datasheets.SLAANESH_AP_MODIFIER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.ROTIGUS_DELUGE_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=(
                "datasheet.aura.movement_modifier",
                "datasheet.aura.objective_control_modifier",
            ),
            runtime_consumer_ids=(
                datasheets.DELUGE_MOVEMENT_MODIFIER_ID,
                datasheets.DELUGE_OBJECTIVE_CONTROL_MODIFIER_ID,
            ),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.NURGLINGS_MISCHIEF_MAKERS_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.engagement_range.melee_hit_roll_modifier",),
            runtime_consumer_ids=(datasheets.MISCHIEF_MAKERS_HIT_MODIFIER_ID,),
        ),
        CatalogDescriptorConsumptionRecord(
            ability_id=datasheets.POXBRINGER_FECULENT_DESPAIR_ABILITY_ID,
            source_kind=CatalogAbilitySourceKind.DATASHEET,
            semantic_categories=("datasheet.aura.battle_shock_modifier",),
            runtime_consumer_ids=(datasheets.FECULENT_DESPAIR_HOOK_ID,),
        ),
    )
