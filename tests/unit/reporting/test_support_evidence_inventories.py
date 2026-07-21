from __future__ import annotations

from tools.generate_ability_support_matrix import (
    DATASHEET_SUPPORT_OVERALL_VALUES,
    MUSTERING_SUPPORT_STAGE_VALUES,
    ability_support_matrix_rows,
    datasheet_support_rows,
    datasheet_support_rows_payload,
    mustering_support_rows,
    mustering_support_rows_payload,
    runtime_content_semantic_coverage_payload,
)

from warhammer40k_core.engine import army_mustering
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27,
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


def test_support_evidence_payloads_preserve_row_order_and_identity() -> None:
    ability_rows = ability_support_matrix_rows()
    category_rows = ability_coverage_category_rows(ability_rows)
    support_rows = datasheet_support_rows()
    mustering_rows = mustering_support_rows()

    assert tuple(row["coverage_row_id"] for row in ability_coverage_rows_payload(ability_rows)) == (
        tuple(row.coverage_row_id for row in ability_rows)
    )
    assert tuple(
        row["category_id"] for row in ability_coverage_category_rows_payload(category_rows)
    ) == tuple(row.category_id for row in category_rows)
    assert tuple(
        (row["faction_id"], row["datasheet_id"])
        for row in datasheet_support_rows_payload(support_rows)
    ) == tuple((row.faction_id, row.datasheet_id) for row in support_rows)
    assert tuple(row["rule_id"] for row in mustering_support_rows_payload(mustering_rows)) == tuple(
        row.rule_id for row in mustering_rows
    )


def test_support_categories_retain_structured_ability_and_datasheet_evidence() -> None:
    categories = {
        row.category_name: row
        for row in ability_coverage_category_rows(ability_support_matrix_rows())
    }

    leadership = categories["Leadership Characteristic"]
    assert leadership.ability_names == ("Daemonic Icon",)
    assert leadership.datasheet_names == ("Bloodcrushers", "Bloodletters")
    assert leadership.coverage_row_count == 2
    assert leadership.source_kind_counts == (("wargear", 2),)
    assert tuple(
        (pair.ability_name, pair.datasheet_name) for pair in leadership.ability_datasheet_pairs
    ) == (("Daemonic Icon", "Bloodcrushers"), ("Daemonic Icon", "Bloodletters"))
    assert leadership.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)

    charge = categories["Charge Roll Modifier"]
    assert charge.ability_names == ("Instrument of Chaos",)
    assert charge.datasheet_names == ("Bloodcrushers", "Bloodletters")
    assert charge.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)

    deep_strike = categories["Deep Strike Reserve Arrival"]
    assert deep_strike.ability_names == ("Deep Strike",)
    assert deep_strike.runtime_consumer_ids == (
        "descriptor:movement:deep-strike-placement",
        "descriptor:reserve-declaration:deep-strike",
    )
    assert deep_strike.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)

    feel_no_pain = categories["Feel No Pain Source"]
    assert feel_no_pain.ability_names == ("Collar of Khorne",)
    assert feel_no_pain.datasheet_names == ("Flesh Hounds",)
    assert feel_no_pain.runtime_consumer_ids == ("catalog-ir:feel-no-pain-source",)
    assert feel_no_pain.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)

    reserves = categories["Datasheet Rule Ir Placement Permission This Unit"]
    assert reserves.ability_names == ("Hunters from the Warp",)
    assert reserves.datasheet_names == ("Flesh Hounds",)
    assert reserves.runtime_consumer_ids == ("catalog-ir:can-be-placed-in-reserves",)
    assert reserves.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)


def test_faction_army_rule_categories_are_engine_consumed() -> None:
    categories = {
        row.category_name: row
        for row in ability_coverage_category_rows(ability_support_matrix_rows())
    }
    expected_abilities = {
        "Chaos Daemons Army Rule": "The Shadow of Chaos",
        "Chaos Space Marines Army Rule": "Dark Pacts",
        "Death Guard Army Rule": "Nurgle's Gift",
        "World Eaters Army Rule": "Blessings of Khorne",
        "Emperor's Children Army Rule": "Thrill Seekers",
        "Faction Army Rule Prioritised Efficiency": "Prioritised Efficiency",
        "Faction Army Rule Cabal Of Sorcerers": "Cabal of Sorcerers",
        "Faction Army Rule Cult Ambush": "Cult Ambush",
        "Faction Army Rule Acts Of Faith": "Acts of Faith",
        "Faction Army Rule Martial Katah": "Martial Ka'tah",
        "Faction Army Rule Doctrina Imperatives": "Doctrina Imperatives",
        "Faction Army Rule Shadow In The Warp Synapse": "Shadow in the Warp / Synapse",
        "Faction Army Rule Code Chivalric": "Code Chivalric",
        "Faction Army Rule Bondsman": "Bondsman",
    }

    for category_name, ability_name in expected_abilities.items():
        category = categories[category_name]
        assert category.ability_names == (ability_name,)
        assert category.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)
        assert category.runtime_consumer_ids
