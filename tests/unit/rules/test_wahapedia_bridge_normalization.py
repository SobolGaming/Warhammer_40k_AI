from __future__ import annotations

import json
from typing import cast

import pytest
from tests.support.wahapedia_bridge_fixtures import (
    bloodcrushers_bridge_artifacts,
    damaged_source_artifacts,
)
from tests.support.wahapedia_source_fixtures import (
    artifact_by_table,
    bridge_package_id,
    catalog_package_id,
    catalog_version,
    conditioned_weapon_keyword_bridge_artifacts,
    keyword_ability_source_artifacts,
    row_by_id,
    same_faction_source_artifacts,
    source_ids_from_row,
    wahapedia_source_artifacts,
    warlord_mustering_source_artifacts,
)
from tools.generate_ability_support_matrix import (
    BLOODLETTERS_HEIGHT_OVERRIDES,
)

from warhammer40k_core.core.datasheet import (
    MUSTERING_WARLORD_FORBIDDEN,
    MUSTERING_WARLORD_REQUIRED,
    MUSTERING_WARLORD_RULE_KEY,
    CatalogAbilitySupport,
    DamagedEffectKind,
    DamagedWeaponScope,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometrySourceUnits,
)
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    AntiKeywordMatchMode,
    TargetKeywordMatchMode,
    WeaponKeyword,
)
from warhammer40k_core.engine.ability_coverage import (
    WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,
    AbilityCoverageSupportStage,
    ability_coverage_row_for_descriptor,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
    CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
    CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
    CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
    CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
    catalog_rule_ir_hook_ids_for_rule,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.rule_ir import (
    RuleIR,
    RuleIRPayload,
)
from warhammer40k_core.rules.source_reference_generation import build_source_reference_catalog
from warhammer40k_core.rules.wahapedia_bridge import (
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_datasheet_ability_bridge import bridge_datasheet_abilities


def test_phase17k_bridge_datasheet_source_ids_include_pdf_correction_source_id() -> None:
    artifacts = bloodcrushers_bridge_artifacts()
    datasheet_row = row_by_id(artifact_by_table(artifacts, "Datasheets"), "000001115")
    shadow_legion_row = next(
        row
        for artifact in wahapedia_source_artifacts()
        if artifact.source_table == "Datasheets_keywords"
        for row in artifact.rows
        if row.runtime_fields_payload()["datasheet_id"] == "000001115"
        and row.runtime_fields_payload()["keyword"] == "Shadow Legion"
    )

    source_ids = source_ids_from_row(datasheet_row)

    assert shadow_legion_row.stable_source_id() in source_ids
    assert "pdf:chaos-daemons-faction-pack:2026-06-10:p30-p31" in source_ids


@pytest.mark.parametrize(
    ("description", "expected", "expected_wounds_max"),
    [
        (
            (
                "While this model has 1-7 wounds remaining, subtract 4 from this model's "
                "Objective Control characteristic, and each time this model makes an attack, "
                "subtract 1 from the Hit roll."
            ),
            (
                (DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER, -4, None, (), None, None, None),
                (DamagedEffectKind.HIT_ROLL_MODIFIER, -1, None, (), None, None, None),
            ),
            7,
        ),
        (
            (
                "DAMAGED: 1\N{EN DASH}7 WOUNDS REMAINING\n"
                "While this model has 1\N{EN DASH}7 wounds remaining, "
                "add 2 to the Attacks characteristic of this "
                "model\N{RIGHT SINGLE QUOTATION MARK}s melee weapons."
            ),
            (
                (
                    DamagedEffectKind.WEAPON_ATTACKS_MODIFIER,
                    2,
                    DamagedWeaponScope.MELEE,
                    (),
                    None,
                    None,
                    None,
                ),
            ),
            7,
        ),
        (
            (
                "While this model has 1-8 wounds remaining, subtract 4 from its Objective "
                "Control characteristic and you can only select one of the C'tan Powers "
                "weapons in your Shooting phase, instead of two."
            ),
            (
                (DamagedEffectKind.OBJECTIVE_CONTROL_MODIFIER, -4, None, (), None, None, None),
                (
                    DamagedEffectKind.SHOOTING_WEAPON_SELECTION_LIMIT,
                    None,
                    None,
                    (),
                    1,
                    2,
                    "C'tan Powers weapons",
                ),
            ),
            8,
        ),
        (
            (
                "While this model has 1-6 wounds remaining, the Attacks characteristics of "
                "all of its weapons are halved, and you can only select one ability when "
                "using its Relics of the Matriarchs ability, instead of up to two."
            ),
            (
                (
                    DamagedEffectKind.WEAPON_ATTACKS_HALVE,
                    None,
                    DamagedWeaponScope.ALL,
                    (),
                    None,
                    None,
                    None,
                ),
                (
                    DamagedEffectKind.ABILITY_SELECTION_LIMIT,
                    None,
                    None,
                    (),
                    1,
                    2,
                    "Relics of the Matriarchs ability",
                ),
            ),
            6,
        ),
    ],
)
def test_phase17k_bridge_normalizes_damaged_sections_to_structured_effects(
    description: str,
    expected: tuple[
        tuple[
            DamagedEffectKind,
            int | None,
            DamagedWeaponScope | None,
            tuple[str, ...],
            int | None,
            int | None,
            str | None,
        ],
        ...,
    ],
    expected_wounds_max: int,
) -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=damaged_source_artifacts(description),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-damaged",),
        pdf_corrections=(),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-damaged",
                model_name="Damaged Beast",
                height=2.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="geometry-review:test-damaged:height",
                height_document_reference="Test Faction Pack p.1",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    datasheet = package.army_catalog.datasheet_by_id("test-damaged")

    assert (
        tuple(
            (
                effect.effect_kind,
                effect.modifier,
                effect.weapon_scope,
                effect.weapon_names,
                effect.max_selections,
                effect.baseline_max_selections,
                effect.selection_group,
            )
            for effect in datasheet.damaged_effects
        )
        == expected
    )
    assert {effect.wounds_min for effect in datasheet.damaged_effects} == {1}
    assert {effect.wounds_max for effect in datasheet.damaged_effects} == {expected_wounds_max}


def test_phase17k_bridge_deduplicates_same_faction_rows_for_multiple_datasheets() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=same_faction_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-datasheet-a", "test-datasheet-b"),
        pdf_corrections=(),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-datasheet-a",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:alpha-height",
                height_document_reference="test-doc:alpha-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-datasheet-b",
                model_name="Beta",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:beta-height",
                height_document_reference="test-doc:beta-height",
            ),
        ),
    )
    faction_rows = artifact_by_table(artifacts, "Factions").rows

    assert tuple(row.source_row_id for row in faction_rows) == ("test-faction",)


def test_phase17k_bridge_normalizes_core_keyword_ability_timing_and_parameters() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=keyword_ability_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-keyword-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-keyword-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:keyword-height",
                height_document_reference="test-doc:keyword-height",
            ),
        ),
    )
    ability_rows = artifact_by_table(artifacts, "Datasheets_abilities").rows
    fields_by_name = {
        row.runtime_fields_payload()["name"]: row.runtime_fields_payload()
        for row in ability_rows
        if row.runtime_fields_payload()["type"] == "Core"
    }

    assert fields_by_name["Deep Strike"]["timing_tags"] == "deployment,reserves"
    assert fields_by_name["Infiltrators"]["timing_tags"] == "deployment"
    assert fields_by_name["Leader"]["timing_tags"] == "declare_battle_formations,attachments"
    assert fields_by_name["Support"]["timing_tags"] == "declare_battle_formations,attachments"
    assert fields_by_name['Scouts 6"']["timing_tags"] == "before_battle,scouts"
    assert fields_by_name['Scouts 6"']["parameter_tokens"] == "6"
    assert fields_by_name["Firing Deck 2"]["timing_tags"] == "shooting"
    assert fields_by_name["Firing Deck 2"]["parameter_tokens"] == "2"
    assert fields_by_name["Deadly Demise D3"]["timing_tags"] == "after_destroyed,deadly_demise"
    assert fields_by_name["Deadly Demise D3"]["parameter_tokens"] == "D3"


def test_phase17k_bridge_normalizes_conditioned_wargear_weapon_keywords() -> None:
    artifacts = conditioned_weapon_keyword_bridge_artifacts(
        "[LETHAL HITS: non-MONSTER/VEHICLE, RAPID FIRE 1, C'tan Power]"
    )
    wargear_row = artifact_by_table(artifacts, "Datasheets_wargear").rows[0]
    wargear_fields = wargear_row.runtime_fields_payload()
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=artifacts,
    )
    profile = package.army_catalog.wargear[0].weapon_profiles[0]
    abilities_by_kind = {ability.ability_kind: ability for ability in profile.abilities}
    lethal = abilities_by_kind[AbilityKind.LETHAL_HITS]

    assert wargear_fields["weapon_keywords"] == "C'tan Power,Lethal Hits,Rapid Fire"
    assert wargear_fields["weapon_abilities"]
    assert tuple(keyword.value for keyword in profile.keywords) == (
        WeaponKeyword.CTAN_POWER.value,
        WeaponKeyword.LETHAL_HITS.value,
        WeaponKeyword.RAPID_FIRE.value,
    )
    assert lethal.target_keywords == ("MONSTER", "VEHICLE")
    assert {parameter.name: parameter.value for parameter in lethal.parameters} == {
        "target_keyword_match_mode": TargetKeywordMatchMode.MISSING_KEYWORD.value
    }
    assert abilities_by_kind[AbilityKind.RAPID_FIRE].parameters[0].value == 1


def test_phase17k_bridge_normalizes_conditioned_valued_and_anti_weapon_keywords() -> None:
    artifacts = conditioned_weapon_keyword_bridge_artifacts(
        "[SUSTAINED HITS 2: non-MONSTER/VEHICLE, MELTA 3: MONSTER, "
        "CLEAVE 4: INFANTRY, DEVASTATING WOUNDS: MONSTER, "
        "HUNTER: non-MONSTER/VEHICLE, ANTI-non-PSYKER 2+]"
    )
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=artifacts,
    )
    profile = package.army_catalog.wargear[0].weapon_profiles[0]
    abilities_by_kind = {ability.ability_kind: ability for ability in profile.abilities}
    sustained = abilities_by_kind[AbilityKind.SUSTAINED_HITS]
    melta = abilities_by_kind[AbilityKind.MELTA]
    cleave = abilities_by_kind[AbilityKind.CLEAVE]
    devastating = abilities_by_kind[AbilityKind.DEVASTATING_WOUNDS]
    hunter = abilities_by_kind[AbilityKind.HUNTER]
    anti = abilities_by_kind[AbilityKind.ANTI_KEYWORD]

    assert tuple(keyword.value for keyword in profile.keywords) == (
        WeaponKeyword.CLEAVE.value,
        WeaponKeyword.DEVASTATING_WOUNDS.value,
        WeaponKeyword.HUNTER.value,
        WeaponKeyword.MELTA.value,
        WeaponKeyword.SUSTAINED_HITS.value,
    )
    assert sustained.target_keywords == ("MONSTER", "VEHICLE")
    assert {parameter.name: parameter.value for parameter in sustained.parameters} == {
        "target_keyword_match_mode": TargetKeywordMatchMode.MISSING_KEYWORD.value,
        "value": 2,
    }
    assert melta.target_keywords == ("MONSTER",)
    assert melta.parameters[0].value == 3
    assert cleave.target_keywords == ("INFANTRY",)
    assert cleave.parameters[0].value == 4
    assert devastating.target_keywords == ("MONSTER",)
    assert hunter.target_keywords == ("MONSTER", "VEHICLE")
    assert {parameter.name: parameter.value for parameter in hunter.parameters} == {
        "target_keyword_match_mode": TargetKeywordMatchMode.MISSING_KEYWORD.value
    }
    assert {parameter.name: parameter.value for parameter in anti.parameters} == {
        "keyword": "PSYKER",
        "match_mode": AntiKeywordMatchMode.MISSING_KEYWORD.value,
        "threshold": 2,
    }


def test_phase17k_bridge_allows_duplicate_anti_weapon_keyword_descriptors() -> None:
    artifacts = conditioned_weapon_keyword_bridge_artifacts("[ANTI-INFANTRY 2+, ANTI-VEHICLE 4+]")
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=artifacts,
    )
    profile = package.army_catalog.wargear[0].weapon_profiles[0]
    anti_abilities = tuple(
        ability for ability in profile.abilities if ability.ability_kind is AbilityKind.ANTI_KEYWORD
    )

    assert len(anti_abilities) == 2
    assert {
        ability.parameters[0].value
        for ability in anti_abilities
        if ability.parameters[0].name == "keyword"
    } == {"INFANTRY", "VEHICLE"}


def test_phase17k_bridge_tags_warlord_mustering_datasheet_abilities() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=warlord_mustering_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-supreme-commander", "test-warlord-forbidden"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-supreme-commander",
                model_name="Commander",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:supreme-height",
                height_document_reference="test-doc:supreme-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-warlord-forbidden",
                model_name="Forbidden",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:forbidden-height",
                height_document_reference="test-doc:forbidden-height",
            ),
        ),
    )
    ability_fields_by_datasheet = {
        row.runtime_fields_payload()["datasheet_id"]: row.runtime_fields_payload()
        for row in artifact_by_table(artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] in {"SUPREME COMMANDER", "ENSLAVED STAR GOD"}
    }
    supreme_fields = ability_fields_by_datasheet["test-supreme-commander"]
    forbidden_fields = ability_fields_by_datasheet["test-warlord-forbidden"]
    plain_datasheet_fields = next(
        row.runtime_fields_payload()
        for row in artifact_by_table(artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] == "TACTICAL ACUMEN"
    )
    plain_rule_ir_payload = plain_datasheet_fields["rule_ir_payload"]

    assert supreme_fields["source_kind"] == "datasheet"
    assert forbidden_fields["source_kind"] == "datasheet"
    assert plain_datasheet_fields["source_kind"] == "datasheet"
    assert json.loads(supreme_fields["rule_ir_payload"]) == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_REQUIRED,
    }
    assert json.loads(forbidden_fields["rule_ir_payload"]) == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_FORBIDDEN,
    }
    assert not plain_rule_ir_payload or MUSTERING_WARLORD_RULE_KEY not in json.loads(
        plain_rule_ir_payload
    )
    semantic_rows = bridge_datasheet_abilities(
        source_artifacts=warlord_mustering_source_artifacts(),
        datasheet_ids=("test-supreme-commander", "test-warlord-forbidden"),
    )
    forbidden_descriptor = next(
        row
        for row in semantic_rows
        if row.datasheet_id == "test-warlord-forbidden"
        and row.descriptor.name == "ENSLAVED STAR GOD"
    ).descriptor
    forbidden_coverage = ability_coverage_row_for_descriptor(
        catalog_id="test-warlord-semantic-bridge",
        datasheet_id="test-warlord-forbidden",
        datasheet_name="Forbidden Warlord",
        ability=forbidden_descriptor,
    )
    assert forbidden_coverage.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
    assert forbidden_coverage.runtime_consumer_ids == (WARLORD_RESTRICTION_MUSTERING_CONSUMER_ID,)


def test_phase17k_bridge_loads_belakor_datasheet_rule_ir_support() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001148",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="000001148",
                model_name="Be'lakor - EPIC HERO",
                height=5.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:belakor-height",
                height_document_reference="test-doc:belakor-height",
            ),
        ),
    )
    ability_rows_by_id = {
        row.source_row_id: row.runtime_fields_payload()
        for row in artifact_by_table(artifacts, "Datasheets_abilities").rows
    }
    expected_consumers_by_row_id = {
        "000001148:5": {CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID},
        "000001148:6": {CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID},
        "000001148:8": {CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID},
        "000001148:9": {
            CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
            CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
        },
        "000001148:10": {CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID},
    }

    for row_id, expected_consumers in expected_consumers_by_row_id.items():
        fields = ability_rows_by_id[row_id]
        rule_ir = RuleIR.from_payload(cast(RuleIRPayload, json.loads(fields["rule_ir_payload"])))

        assert fields["support"] == CatalogAbilitySupport.GENERIC_RULE_IR.value
        assert json.loads(fields["rule_ir_diagnostics"]) == []
        assert expected_consumers <= set(catalog_rule_ir_consumers_for_rule(rule_ir))

    supreme_commander_fields = ability_rows_by_id["000001148:7"]
    assert supreme_commander_fields["support"] == CatalogAbilitySupport.DESCRIPTOR_ONLY.value
    assert json.loads(supreme_commander_fields["rule_ir_payload"]) == {
        MUSTERING_WARLORD_RULE_KEY: MUSTERING_WARLORD_REQUIRED,
    }


def test_phase17k_bridge_preserves_raw_source_text_for_reference_catalog() -> None:
    source_reference_catalog = build_source_reference_catalog(
        package_id=bridge_package_id(),
        catalog_version=catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )
    deep_strike_text = source_reference_catalog.source_text_by_id(
        f"{bridge_package_id().stable_identity()}:Datasheets_abilities:000001115:1:description"
    )
    option_text = source_reference_catalog.source_text_by_id(
        f"{bridge_package_id().stable_identity()}:Datasheets_options:000001115:1:description"
    )

    assert "<div" in deep_strike_text.raw_text
    assert "<div" not in deep_strike_text.sanitized_text
    assert option_text.raw_text.startswith("1 Bloodcrusher that is not equipped")
    assert (
        source_reference_catalog.to_payload()
        == type(source_reference_catalog)
        .from_payload(source_reference_catalog.to_payload())
        .to_payload()
    )


def test_phase17k_bridge_compiles_rule_ir_spans_from_sanitized_source_text() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=wahapedia_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("000001114",),
        height_overrides=BLOODLETTERS_HEIGHT_OVERRIDES,
    )
    ability_row = row_by_id(
        artifact_by_table(bridge_artifacts, "Datasheets_abilities"),
        "000001114:5",
    )
    fields = ability_row.runtime_fields_payload()
    description_text = next(
        text_field
        for text_field in ability_row.text_fields
        if text_field.column_name == "description"
    )
    rule_ir = RuleIR.from_payload(cast(RuleIRPayload, json.loads(fields["rule_ir_payload"])))

    assert fields["support"] == "generic_rule_ir"
    assert "<span" in description_text.raw_text
    assert "<span" not in fields["description"]
    assert rule_ir.normalized_text == fields["description"]
    assert {
        CATALOG_IR_DESPERATE_ESCAPE_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_FORCE_DESPERATE_ESCAPE_CONSUMER_ID,
    } <= set(catalog_rule_ir_hook_ids_for_rule(rule_ir))
    for clause in rule_ir.clauses:
        assert (
            rule_ir.normalized_text[clause.source_span.start : clause.source_span.end]
            == clause.source_span.text
        )
