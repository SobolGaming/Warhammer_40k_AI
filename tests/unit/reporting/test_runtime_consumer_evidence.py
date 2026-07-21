from __future__ import annotations

from dataclasses import dataclass

from tools.generate_ability_support_matrix import ability_support_matrix_rows

from warhammer40k_core.engine import cult_ambush as genestealer_cults_cult_ambush
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adepta_sororitas import (
    army_rule as adepta_sororitas_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_custodes import (
    army_rule as adeptus_custodes_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.adeptus_mechanicus import (
    army_rule as adeptus_mechanicus_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as chaos_space_marines_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule as death_guard_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    army_rule as emperors_children_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.imperial_knights import (
    army_rule as imperial_knights_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.thousand_sons import (
    army_rule as thousand_sons_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.tyranids import (
    army_rule as tyranids_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
)


@dataclass(frozen=True, slots=True)
class ArmyRuleEvidence:
    ability_name: str
    datasheet_name: str
    runtime_consumer_ids: frozenset[str]


_ARMY_RULE_EVIDENCE = (
    ArmyRuleEvidence(
        ability_name="Dark Pacts",
        datasheet_name="Chaos Space Marines",
        runtime_consumer_ids=frozenset(
            {
                chaos_space_marines_army_rule.ATTACK_SEQUENCE_COMPLETED_HOOK_ID,
                chaos_space_marines_army_rule.FIGHT_LETHAL_HITS_HOOK_ID,
                chaos_space_marines_army_rule.FIGHT_SUSTAINED_HITS_HOOK_ID,
                chaos_space_marines_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
                chaos_space_marines_army_rule.SHOOTING_LETHAL_HITS_HOOK_ID,
                chaos_space_marines_army_rule.SHOOTING_SUSTAINED_HITS_HOOK_ID,
                chaos_space_marines_army_rule.WEAPON_PROFILE_MODIFIER_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Nurgle's Gift",
        datasheet_name="Death Guard",
        runtime_consumer_ids=frozenset(
            {
                death_guard_army_rule.HOOK_ID,
                f"{death_guard_army_rule.HOOK_ID}:armour-save-option",
                f"{death_guard_army_rule.HOOK_ID}:leadership",
                f"{death_guard_army_rule.HOOK_ID}:melee-hit-roll",
                f"{death_guard_army_rule.HOOK_ID}:movement-budget",
                f"{death_guard_army_rule.HOOK_ID}:objective-control",
                f"{death_guard_army_rule.HOOK_ID}:toughness",
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Blessings of Khorne",
        datasheet_name="World Eaters",
        runtime_consumer_ids=frozenset(
            {
                world_eaters_army_rule.HOOK_ID,
                world_eaters_army_rule.RAGE_FUELLED_INVIGORATION_HOOK_ID,
                world_eaters_army_rule.TOTAL_CARNAGE_HOOK_ID,
                world_eaters_army_rule.UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID,
                f"{world_eaters_army_rule.HOOK_ID}:weapon-profile-keywords",
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Thrill Seekers",
        datasheet_name="Emperor's Children",
        runtime_consumer_ids=frozenset(
            {
                emperors_children_army_rule.ADVANCE_ELIGIBILITY_HOOK_ID,
                emperors_children_army_rule.FALL_BACK_ELIGIBILITY_HOOK_ID,
                emperors_children_army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID,
                emperors_children_army_rule.CHARGE_TARGET_RESTRICTION_HOOK_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Prioritised Efficiency",
        datasheet_name="Leagues of Votann",
        runtime_consumer_ids=frozenset(
            {
                "warhammer_40000_11th:leagues_of_votann:army_rule:"
                "prioritised_efficiency:command-phase-start",
                "warhammer_40000_11th:leagues_of_votann:army_rule:prioritised_efficiency:hit-roll",
                "warhammer_40000_11th:leagues_of_votann:army_rule:"
                "prioritised_efficiency:wound-roll",
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Cabal of Sorcerers",
        datasheet_name="Thousand Sons",
        runtime_consumer_ids=frozenset(
            {
                thousand_sons_army_rule.HOOK_ID,
                thousand_sons_army_rule.MORTAL_WOUND_FEEL_NO_PAIN_HOOK_ID,
                thousand_sons_army_rule.WEAPON_PROFILE_MODIFIER_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Cult Ambush",
        datasheet_name="Genestealer Cults",
        runtime_consumer_ids=frozenset(
            {
                genestealer_cults_cult_ambush.SOURCE_RULE_ID,
                genestealer_cults_cult_ambush.BATTLE_FORMATION_HOOK_ID,
                genestealer_cults_cult_ambush.UNIT_DESTROYED_HOOK_ID,
                genestealer_cults_cult_ambush.TURN_END_HOOK_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Acts of Faith",
        datasheet_name="Adepta Sororitas",
        runtime_consumer_ids=frozenset(
            {
                adepta_sororitas_army_rule.BATTLE_ROUND_START_HOOK_ID,
                adepta_sororitas_army_rule.UNIT_DESTROYED_HOOK_ID,
                adepta_sororitas_army_rule.TRIUMPH_RELICS_BATTLE_ROUND_START_HOOK_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Martial Ka'tah",
        datasheet_name="Adeptus Custodes",
        runtime_consumer_ids=frozenset(
            {
                adeptus_custodes_army_rule.DACATARAI_HOOK_ID,
                adeptus_custodes_army_rule.RENDAX_HOOK_ID,
                adeptus_custodes_army_rule.WEAPON_PROFILE_MODIFIER_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Doctrina Imperatives",
        datasheet_name="Adeptus Mechanicus",
        runtime_consumer_ids=frozenset(
            {
                adeptus_mechanicus_army_rule.HOOK_ID,
                adeptus_mechanicus_army_rule.PROTECTOR_HIT_MODIFIER_ID,
                adeptus_mechanicus_army_rule.WEAPON_PROFILE_MODIFIER_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Shadow in the Warp / Synapse",
        datasheet_name="Tyranids",
        runtime_consumer_ids=frozenset(
            {
                tyranids_army_rule.HOOK_ID,
                tyranids_army_rule.BATTLE_SHOCK_HOOK_ID,
                tyranids_army_rule.WEAPON_PROFILE_MODIFIER_ID,
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Code Chivalric",
        datasheet_name="Imperial Knights",
        runtime_consumer_ids=frozenset(
            {
                imperial_knights_army_rule.HOOK_ID,
                imperial_knights_army_rule.SETUP_HOOK_ID,
                imperial_knights_army_rule.UNIT_DESTROYED_HOOK_ID,
                imperial_knights_army_rule.END_TURN_EVENT_HANDLER_ID,
                imperial_knights_army_rule.END_BATTLE_ROUND_EVENT_HANDLER_ID,
                f"{imperial_knights_army_rule.HOOK_ID}:martial-valour:shooting",
                f"{imperial_knights_army_rule.HOOK_ID}:martial-valour:fight",
                f"{imperial_knights_army_rule.HOOK_ID}:eager:movement-budget",
                f"{imperial_knights_army_rule.HOOK_ID}:eager:charge-roll",
                f"{imperial_knights_army_rule.HOOK_ID}:legacy:objective-control",
                f"{imperial_knights_army_rule.HOOK_ID}:legacy:leadership",
            }
        ),
    ),
    ArmyRuleEvidence(
        ability_name="Bondsman",
        datasheet_name="Imperial Knights",
        runtime_consumer_ids=frozenset({imperial_knights_army_rule.BONDSMAN_HOOK_ID}),
    ),
)


def test_cross_faction_army_rule_rows_retain_runtime_consumer_evidence() -> None:
    rows_by_name: dict[str, list[AbilityCoverageRow]] = {}
    for row in ability_support_matrix_rows():
        rows_by_name.setdefault(row.ability_name, []).append(row)

    for evidence in _ARMY_RULE_EVIDENCE:
        matching_rows = [
            row
            for row in rows_by_name[evidence.ability_name]
            if row.datasheet_name == evidence.datasheet_name
        ]
        assert len(matching_rows) == 1
        row = matching_rows[0]
        assert row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        assert frozenset(row.runtime_consumer_ids) == evidence.runtime_consumer_ids


def test_cross_faction_descriptor_rows_remain_distinct_from_executable_army_rules() -> None:
    rows_by_name: dict[str, list[AbilityCoverageRow]] = {}
    for row in ability_support_matrix_rows():
        rows_by_name.setdefault(row.ability_name, []).append(row)

    for ability_name, datasheet_id in (
        ("Blessings of Khorne", "000004207"),
        ("Thrill Seekers", "000004208"),
    ):
        rows = rows_by_name[ability_name]
        assert any(
            row.datasheet_id == datasheet_id
            and row.support_stage is AbilityCoverageSupportStage.DESCRIPTOR_ONLY
            and row.runtime_consumer_ids == ()
            for row in rows
        )
        assert any(row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED for row in rows)
