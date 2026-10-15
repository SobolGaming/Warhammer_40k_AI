from __future__ import annotations

from tests.shared.category_migration.reporting__test_runtime_consumer_evidence import (
    _ARMY_RULE_EVIDENCE,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    ArmyRuleEvidence,
    CatalogAbilitySourceKind,
    ability_support_matrix_rows,
    adepta_sororitas_army_rule,
    adeptus_custodes_army_rule,
    adeptus_mechanicus_army_rule,
    chaos_daemons_descriptor_consumption,
    chaos_daemons_july_2026,
    chaos_space_marines_army_rule,
    dataclass,
    death_guard_army_rule,
    emperors_children_army_rule,
    genestealer_cults_cult_ambush,
    imperial_knights_army_rule,
    thousand_sons_army_rule,
    tyranids_army_rule,
    world_eaters_army_rule,
)


def test_emperors_children_defiler_thrill_seekers_retains_exact_runtime_evidence() -> None:
    rows = ability_support_matrix_rows()
    defiler_row = next(
        row
        for row in rows
        if row.datasheet_id == "000004208"
        and row.ability_id == emperors_children_army_rule.THRILL_SEEKERS_SOURCE_ABILITY_ID
    )

    assert defiler_row.source_kind is CatalogAbilitySourceKind.FACTION
    assert defiler_row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert defiler_row.semantic_categories == ("faction.army_rule.thrill_seekers",)
    assert frozenset(defiler_row.runtime_consumer_ids) == frozenset(
        {
            emperors_children_army_rule.ADVANCE_ELIGIBILITY_HOOK_ID,
            emperors_children_army_rule.FALL_BACK_ELIGIBILITY_HOOK_ID,
            emperors_children_army_rule.SHOOTING_TARGET_RESTRICTION_HOOK_ID,
            emperors_children_army_rule.CHARGE_TARGET_RESTRICTION_HOOK_ID,
        }
    )

    other_runtime_backed_defiler_rows = tuple(
        row
        for row in rows
        if row.datasheet_name == "Defiler"
        and row.source_kind is CatalogAbilitySourceKind.FACTION
        and row.ability_id != emperors_children_army_rule.THRILL_SEEKERS_SOURCE_ABILITY_ID
    )
    assert other_runtime_backed_defiler_rows
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        and row.runtime_consumer_ids
        for row in other_runtime_backed_defiler_rows
    )


__all__: list[str] = []
__all__ += ["_ARMY_RULE_EVIDENCE", "AbilityCoverageRow", "ArmyRuleEvidence"]
__all__ += ["adepta_sororitas_army_rule", "adeptus_custodes_army_rule"]
__all__ += ["adeptus_mechanicus_army_rule", "chaos_daemons_descriptor_consumption"]
__all__ += ["chaos_daemons_july_2026", "chaos_space_marines_army_rule", "dataclass"]
__all__ += ["death_guard_army_rule", "genestealer_cults_cult_ambush"]
__all__ += ["imperial_knights_army_rule", "thousand_sons_army_rule", "tyranids_army_rule"]
__all__ += ["world_eaters_army_rule"]
