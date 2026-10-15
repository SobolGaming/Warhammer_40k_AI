from __future__ import annotations

from tests.shared.category_migration.reporting__test_support_evidence_inventories import (
    DATASHEET_SUPPORT_OVERALL_VALUES,
    MUSTERING_SUPPORT_STAGE_VALUES,
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
    ability_support_matrix_rows,
    army_mustering,
    datasheet_support_rows,
    datasheet_support_rows_payload,
    faction_detachments_2026_27,
    mustering_support_rows,
    mustering_support_rows_payload,
    runtime_content_semantic_coverage_payload,
)


def test_support_evidence_inventories_are_complete() -> None:
    ability_rows = ability_support_matrix_rows()
    category_rows = ability_coverage_category_rows(ability_rows)
    support_rows = datasheet_support_rows()
    mustering_rows = mustering_support_rows()
    runtime_payload = runtime_content_semantic_coverage_payload()

    ability_row_ids = {row.coverage_row_id for row in ability_rows}
    category_ability_row_ids = {
        coverage_row_id
        for category_row in category_rows
        for coverage_row_id in category_row.coverage_row_ids
    }
    assert len(ability_row_ids) == len(ability_rows)
    assert category_ability_row_ids == ability_row_ids

    faction_ids = {row.faction_id for row in faction_detachments_2026_27.faction_rows()}
    detachment_ids_by_faction = {
        faction_id: {
            row.detachment_id
            for row in faction_detachments_2026_27.detachment_rows()
            if row.faction_id == faction_id
        }
        for faction_id in faction_ids
    }
    assert len({(row.faction_id, row.datasheet_id) for row in support_rows}) == len(support_rows)
    for support_row in support_rows:
        assert support_row.overall in DATASHEET_SUPPORT_OVERALL_VALUES
        assert support_row.faction_id in faction_ids
        assert set(support_row.ability_coverage_row_ids) <= ability_row_ids
        assert set(support_row.detachment_ids) <= detachment_ids_by_faction[support_row.faction_id]
        assert set(support_row.supported_detachment_ids) <= set(support_row.detachment_ids)
        if support_row.overall != "Full":
            assert support_row.notes or support_row.ability_coverage_row_ids

    known_mustering_source_ids = {
        value
        for name, value in vars(army_mustering).items()
        if name.endswith("_SOURCE_ID") and type(value) is str
    }
    assert len({row.rule_id for row in mustering_rows}) == len(mustering_rows)
    assert known_mustering_source_ids <= {row.source_id for row in mustering_rows}
    for mustering_row in mustering_rows:
        assert mustering_row.source_id
        assert mustering_row.support_stage in MUSTERING_SUPPORT_STAGE_VALUES

    runtime_factions = runtime_payload["factions"]
    assert {row["faction_id"] for row in runtime_factions} == faction_ids
    assert len({row["faction_id"] for row in runtime_factions}) == len(runtime_factions)
    for faction in runtime_factions:
        assert {row["detachment_id"] for row in faction["detachments"]} == (
            detachment_ids_by_faction[faction["faction_id"]]
        )


__all__: list[str] = []
__all__ += ["AbilityCoverageSupportStage", "ability_coverage_category_rows_payload"]
__all__ += ["ability_coverage_rows_payload", "datasheet_support_rows_payload"]
__all__ += ["mustering_support_rows_payload"]
