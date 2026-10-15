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
    assert leadership.datasheet_names == ("Bloodcrushers", "Bloodletters", "Plaguebearers")
    assert leadership.coverage_row_count == 3
    assert leadership.source_kind_counts == (("wargear", 3),)
    assert tuple(
        (pair.ability_name, pair.datasheet_name) for pair in leadership.ability_datasheet_pairs
    ) == (
        ("Daemonic Icon", "Bloodcrushers"),
        ("Daemonic Icon", "Bloodletters"),
        ("Daemonic Icon", "Plaguebearers"),
    )
    assert leadership.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)

    charge = categories["Charge Roll Modifier"]
    assert charge.ability_names == ("Instrument of Chaos",)
    assert charge.datasheet_names == ("Bloodcrushers", "Bloodletters", "Plaguebearers")
    assert charge.coverage_row_count == 3
    assert charge.source_kind_counts == (("wargear", 3),)
    assert tuple(
        (pair.ability_name, pair.datasheet_name) for pair in charge.ability_datasheet_pairs
    ) == (
        ("Instrument of Chaos", "Bloodcrushers"),
        ("Instrument of Chaos", "Bloodletters"),
        ("Instrument of Chaos", "Plaguebearers"),
    )
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
        "Chaos Daemons Army Rule": ("The Shadow of Chaos",),
        "Chaos Space Marines Army Rule": ("Dark Pacts",),
        "Death Guard Army Rule": ("Nurgle's Gift", "Nurgle's Gift (Aura)"),
        "World Eaters Army Rule": ("Blessings of Khorne",),
        "Emperor's Children Army Rule": ("Thrill Seekers",),
        "Faction Army Rule Prioritised Efficiency": ("Prioritised Efficiency",),
        "Faction Army Rule Cabal Of Sorcerers": ("Cabal of Sorcerers",),
        "Faction Army Rule Cult Ambush": ("Cult Ambush",),
        "Faction Army Rule Acts Of Faith": ("Acts of Faith",),
        "Faction Army Rule Martial Katah": ("Martial Ka'tah",),
        "Faction Army Rule Doctrina Imperatives": ("Doctrina Imperatives",),
        "Faction Army Rule Shadow In The Warp Synapse": ("Shadow in the Warp / Synapse",),
        "Faction Army Rule Code Chivalric": ("Code Chivalric",),
        "Faction Army Rule Bondsman": ("Bondsman",),
    }

    for category_name, ability_names in expected_abilities.items():
        category = categories[category_name]
        assert category.ability_names == ability_names
        assert category.support_stages == (AbilityCoverageSupportStage.ENGINE_CONSUMED,)
        assert category.runtime_consumer_ids


__all__: list[str] = []
__all__ += ["DATASHEET_SUPPORT_OVERALL_VALUES", "MUSTERING_SUPPORT_STAGE_VALUES"]
__all__ += ["army_mustering", "faction_detachments_2026_27"]
__all__ += ["runtime_content_semantic_coverage_payload"]
