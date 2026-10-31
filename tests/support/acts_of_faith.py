"""Canonical analytical Acts fixture; no official Sororitas roster admission."""

from dataclasses import replace

from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.weapon_profiles import AttackProfile, DamageProfile
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import army_rule
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.geometry.pose import Pose


def session(
    *,
    both_armies: bool = True,
    combat: bool = False,
    extra_friendly: bool = False,
) -> LocalGameSession:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    base = catalog.datasheet_by_id("core-character-leader")
    sheet = replace(
        base,
        datasheet_id="canonical-acts-consumer",
        name="Canonical Acts consumer",
        keywords=replace(base.keywords, faction_keywords=("ADEPTA SORORITAS",)),
    )
    catalog = replace(
        catalog,
        datasheets=(*catalog.datasheets, sheet),
        wargear=tuple(
            replace(
                item,
                weapon_profiles=tuple(
                    replace(
                        profile,
                        attack_profile=AttackProfile.fixed(12),
                        skill=CharacteristicValue.from_raw(Characteristic.WEAPON_SKILL, 2),
                        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 20),
                        armor_penetration=CharacteristicValue.from_raw(
                            Characteristic.ARMOR_PENETRATION, -6
                        ),
                        damage_profile=DamageProfile.fixed(20),
                    )
                    for profile in item.weapon_profiles
                ),
            )
            if combat and item.wargear_id == "core-leader-blade"
            else item
            for item in catalog.wargear
        ),
        factions=(
            *catalog.factions,
            FactionDefinition(
                faction_id=army_rule.ADEPTA_SORORITAS_FACTION_ID,
                name="Adepta Sororitas",
                faction_keywords=("ADEPTA SORORITAS",),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
        detachments=(
            *catalog.detachments,
            DetachmentDefinition(
                canonical_detachment_id="canonical-acts-test",
                detachment_id="canonical-acts-test",
                name="Canonical Acts test",
                faction_id=army_rule.ADEPTA_SORORITAS_FACTION_ID,
                detachment_point_cost=1,
                unit_datasheet_ids=(sheet.datasheet_id,),
                force_disposition_ids=("take-and-hold", "purge-the-foe"),
                source_ids=(army_rule.SOURCE_RULE_ID,),
            ),
        ),
    )
    lifecycle, _ = fight_lifecycle(
        alpha_unit_ids=("source", "witness") if extra_friendly else ("source",),
        enemy_unit_ids=("enemy",),
        origins={
            "source": Pose.at(10, 10),
            **({"witness": Pose.at(16, 10)} if extra_friendly else {}),
            "enemy": Pose.at(11, 10) if combat else Pose.at(40, 30),
        },
        game_id="acts-turn-start",
        catalog=catalog,
        datasheet_id="core-character-leader",
        model_profile_id="core-character-leader",
        model_count=1,
        alpha_unit_specs={
            "source": (sheet.datasheet_id, "core-character-leader", 1),
            **(
                {"witness": (sheet.datasheet_id, "core-character-leader", 1)}
                if extra_friendly
                else {}
            ),
        },
        enemy_unit_specs={
            "enemy": (
                sheet.datasheet_id,
                "core-character-leader",
                1,
            )
        }
        if both_armies
        else None,
        alpha_faction_id=army_rule.ADEPTA_SORORITAS_FACTION_ID,
        alpha_detachment_ids=("canonical-acts-test",),
        enemy_faction_id=army_rule.ADEPTA_SORORITAS_FACTION_ID
        if both_armies
        else "core-marine-force",
        enemy_detachment_ids=("canonical-acts-test",) if both_armies else ("core-combined-arms",),
        battle_phase=BattlePhase.FIGHT if combat else BattlePhase.COMMAND,
        fights_first_unit_keys=("source",) if combat else (),
        charge_fights_first_unit_keys=("source",) if combat else (),
    )
    return LocalGameSession(lifecycle)
