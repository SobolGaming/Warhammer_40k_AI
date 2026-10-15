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


def test_chaos_daemons_named_datasheet_rows_retain_active_runtime_consumer_evidence() -> None:
    records = chaos_daemons_descriptor_consumption.descriptor_consumption_records()
    datasheet_records = tuple(
        record for record in records if record.source_kind is CatalogAbilitySourceKind.DATASHEET
    )
    assert len(datasheet_records) == 17

    contribution = chaos_daemons_july_2026.runtime_contribution()
    active_consumer_ids = {
        *(binding.hook_id for binding in contribution.battle_shock_hook_bindings),
        *(binding.hook_id for binding in contribution.fight_phase_end_hook_bindings),
        *(binding.modifier_id for binding in contribution.hit_roll_modifier_bindings),
        *(binding.hook_id for binding in contribution.mortal_wound_feel_no_pain_hook_bindings),
        *(binding.modifier_id for binding in contribution.movement_budget_modifier_bindings),
        *(binding.modifier_id for binding in contribution.objective_control_modifier_bindings),
        *(binding.hook_id for binding in contribution.phase_end_objective_control_hook_bindings),
        *(binding.modifier_id for binding in contribution.weapon_profile_modifier_bindings),
    }
    assert all(set(record.runtime_consumer_ids) <= active_consumer_ids for record in records)

    rows_by_identity = {
        (row.source_kind, row.ability_id): row for row in ability_support_matrix_rows()
    }
    selected_roster_ability_ids = {
        "000001120:daemon-lord-of-tzeentch-aura",
        "000001120:greater-daemon-of-tzeentch-aura",
        "000001132:infected-outbreak",
        "000002582:daemon-lord-of-khorne-aura",
        "000002582:greater-daemon-of-khorne-aura",
        "000002582:relentless-carnage",
    }
    selected_roster_records = tuple(
        record for record in datasheet_records if record.ability_id in selected_roster_ability_ids
    )
    assert {record.ability_id for record in selected_roster_records} == selected_roster_ability_ids
    for record in selected_roster_records:
        row = rows_by_identity[record.identity]
        assert row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        assert row.semantic_categories == record.semantic_categories
        assert row.runtime_consumer_ids == record.runtime_consumer_ids


def test_defiler_faction_rows_retain_exact_executable_army_rule_evidence() -> None:
    rows_by_name: dict[str, list[AbilityCoverageRow]] = {}
    for row in ability_support_matrix_rows():
        rows_by_name.setdefault(row.ability_name, []).append(row)

    for ability_name, datasheet_id, runtime_consumer_ids in (
        ("Dark Pacts", "000000969", _ARMY_RULE_EVIDENCE[0].runtime_consumer_ids),
        ("Nurgle's Gift (Aura)", "000004209", _ARMY_RULE_EVIDENCE[1].runtime_consumer_ids),
        ("Blessings of Khorne", "000004207", _ARMY_RULE_EVIDENCE[2].runtime_consumer_ids),
    ):
        assert any(
            row.datasheet_id == datasheet_id
            and row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
            and frozenset(row.runtime_consumer_ids) == runtime_consumer_ids
            for row in rows_by_name[ability_name]
        )


__all__: list[str] = []
__all__ += ["ArmyRuleEvidence", "adepta_sororitas_army_rule", "adeptus_custodes_army_rule"]
__all__ += ["adeptus_mechanicus_army_rule", "chaos_space_marines_army_rule", "dataclass"]
__all__ += ["death_guard_army_rule", "emperors_children_army_rule"]
__all__ += ["genestealer_cults_cult_ambush", "imperial_knights_army_rule"]
__all__ += ["thousand_sons_army_rule", "tyranids_army_rule", "world_eaters_army_rule"]
