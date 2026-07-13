from __future__ import annotations

import json
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    DEFAULT_SOURCE_JSON_DIR,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_kharseth_rule_ir import (
    AETHERSENSE_ROW_ID,
    FURY_OF_THE_VOID_ROW_ID,
    OUTPUT_PATH,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
)
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword
from warhammer40k_core.rules.rule_ir import (
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_kharseth_2026_06 as kharseth_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_KHARSETH_HEIGHT_OVERRIDES,
)

KHARSETH_DATASHEET_ID = "000004194"
KHARSETH_PDF_SHA256 = "48cf09f605dc29b42555d5800c239879c1fc590f85a6a45b0a1f14739b03f0a9"


def test_kharseth_generated_rule_ir_artifact_is_current_and_source_bound() -> None:
    committed_payload = cast(
        dict[str, Any],
        json.loads(OUTPUT_PATH.read_text(encoding="utf-8")),
    )

    assert committed_payload == generated_artifact_payload()
    assert kharseth_package.SOURCE_PDF_SHA256 == KHARSETH_PDF_SHA256
    assert kharseth_package.SOURCE_PAGE_NUMBERS == (14, 15)
    assert kharseth_package.DATASHEET_ID == KHARSETH_DATASHEET_ID
    assert kharseth_package.DATASHEET_NAME == "Kharseth"
    assert kharseth_package.supported_datasheet_source_row_ids() == (
        AETHERSENSE_ROW_ID,
        FURY_OF_THE_VOID_ROW_ID,
    )
    assert committed_payload["package_hash"] == kharseth_package.PACKAGE_HASH


def test_kharseth_generated_rule_ir_loader_rejects_package_hash_drift() -> None:
    payload = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))
    payload["package_hash"] = "0" * 64

    with pytest.raises(kharseth_package.KharsethRuleIrArtifactError, match="package hash is stale"):
        kharseth_package.validate_generated_artifact_bytes(json.dumps(payload).encode())


def test_kharseth_rule_ir_encodes_exact_generic_semantics() -> None:
    aethersense = _rule_ir(AETHERSENSE_ROW_ID)
    fury = _rule_ir(FURY_OF_THE_VOID_ROW_ID)

    assert aethersense.is_supported
    assert len(aethersense.clauses) == 1
    restriction = aethersense.clauses[0]
    assert restriction.trigger is not None
    assert restriction.trigger.kind is RuleTriggerKind.SETUP
    assert parameter_payload(restriction.trigger.parameters) == {
        "setup_source": "reserves",
        "subject": "enemy_unit",
    }
    assert restriction.target is not None
    assert restriction.target.kind is RuleTargetKind.ENEMY_UNIT
    assert restriction.conditions[0].kind is RuleConditionKind.DISTANCE_PREDICATE
    assert parameter_payload(restriction.conditions[0].parameters) == {
        "distance_inches": 12.0,
        "object_kind": "model",
        "object_reference": "this_model",
        "predicate": "within",
        "range_kind": "numeric_range",
    }
    assert restriction.effects[0].kind is RuleEffectKind.PLACEMENT_RESTRICTION

    assert fury.is_supported
    assert len(fury.clauses) == 2
    selection, effect = fury.clauses
    assert selection.trigger is not None
    assert selection.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(selection.trigger.parameters) == {
        "attacker_model_reference": "this_model",
        "edge": "after",
        "owner": "active_player",
        "phase": "shooting",
        "subject": "this_model",
        "target_relationship": "hit_by_those_attacks",
        "timing_window": "just_after_friendly_unit_has_shot",
        "weapon_names": ("Dread of the Deep Void",),
    }
    assert effect.target is not None
    assert effect.target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert parameter_payload(effect.target.parameters)["required_keyword"] == "AELDARI"
    assert effect.effects[0].kind is RuleEffectKind.MODIFY_CHARACTERISTIC
    assert parameter_payload(effect.effects[0].parameters) == {
        "attack_role": "attacker",
        "characteristic": "strength",
        "delta": 1,
    }
    assert effect.duration is not None
    assert effect.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert parameter_payload(effect.duration.parameters) == {"endpoint": "turn"}


def test_kharseth_catalog_preserves_every_datasheet_section() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    datasheet = next(row for row in catalog.datasheets if row.datasheet_id == KHARSETH_DATASHEET_ID)

    assert datasheet.name == "Kharseth"
    assert datasheet.keywords.keywords == (
        "AELDARI",
        "ANHRATHE",
        "CHARACTER",
        "EPIC HERO",
        "INFANTRY",
        "KHARSETH",
        "PSYKER",
    )
    assert datasheet.keywords.faction_keywords == ("ASURYANI",)
    assert len(datasheet.model_profiles) == 1
    model = datasheet.model_profiles[0]
    assert model.name == "Kharseth - EPIC HERO"
    characteristics = {value.characteristic: value.final for value in model.characteristics}
    assert {
        Characteristic.MOVEMENT: 7,
        Characteristic.TOUGHNESS: 3,
        Characteristic.SAVE: 6,
        Characteristic.WOUNDS: 4,
        Characteristic.LEADERSHIP: 6,
        Characteristic.OBJECTIVE_CONTROL: 1,
        Characteristic.INVULNERABLE_SAVE: 4,
    }.items() <= characteristics.items()
    assert model.base_size.diameter_mm is not None
    assert abs(model.base_size.diameter_mm - 32.0) < 1e-12
    assert datasheet.composition[0].model_profile_id == model.model_profile_id
    assert (datasheet.composition[0].min_models, datasheet.composition[0].max_models) == (1, 1)
    assert {
        (option.default_wargear_ids, option.allowed_wargear_ids)
        for option in datasheet.wargear_options
    } == {
        (("000004194:dread-of-the-deep-void",), ("000004194:dread-of-the-deep-void",)),
        (("000004194:waystave",), ("000004194:waystave",)),
    }
    assert not datasheet.mustering_options

    wargear = {
        item.wargear_id: item
        for item in catalog.wargear
        if item.wargear_id.startswith(f"{KHARSETH_DATASHEET_ID}:")
    }
    assert set(wargear) == {
        "000004194:dread-of-the-deep-void",
        "000004194:waystave",
    }
    dread = wargear["000004194:dread-of-the-deep-void"].weapon_profiles[0]
    assert dread.range_profile.kind is RangeProfileKind.DISTANCE
    assert dread.range_profile.distance_inches == 24
    assert dread.attack_profile.dice_expression is not None
    assert dread.attack_profile.dice_expression.canonical() == "D6+2"
    assert (dread.skill.final, dread.strength.final, dread.armor_penetration.final) == (3, 3, -2)
    assert dread.damage_profile.fixed_damage == 1
    assert dread.keywords == (
        WeaponKeyword.BLAST,
        WeaponKeyword.HAZARDOUS,
        WeaponKeyword.IGNORES_COVER,
        WeaponKeyword.PSYCHIC,
    )
    assert tuple(ability.name for ability in dread.abilities) == ("Anti-Infantry 2+",)

    waystave = wargear["000004194:waystave"].weapon_profiles[0]
    assert waystave.range_profile.kind is RangeProfileKind.MELEE
    assert waystave.attack_profile.fixed_attacks == 3
    assert (waystave.skill.final, waystave.strength.final, waystave.armor_penetration.final) == (
        2,
        3,
        0,
    )
    assert waystave.damage_profile.fixed_damage == 3
    assert waystave.keywords == (WeaponKeyword.PSYCHIC,)
    assert tuple(ability.name for ability in waystave.abilities) == ("Anti-Infantry 2+",)

    abilities = {ability.name: ability for ability in datasheet.abilities}
    assert set(abilities) == {
        "Leader",
        "Scouts",
        "Aethersense (Psychic)",
        "Fury of the Void (Psychic)",
        "Battle Focus",
    }
    assert abilities["Scouts"].parameter_tokens == ("7",)
    assert abilities["Leader"].source_kind is CatalogAbilitySourceKind.CORE
    assert abilities["Battle Focus"].source_kind is CatalogAbilitySourceKind.FACTION
    for ability_name in ("Aethersense (Psychic)", "Fury of the Void (Psychic)"):
        assert abilities[ability_name].support is CatalogAbilitySupport.GENERIC_RULE_IR
        assert abilities[ability_name].rule_ir_payload is not None


def test_kharseth_leader_targets_and_geometry_have_source_evidence() -> None:
    leader_payload = cast(
        dict[str, Any],
        json.loads(
            (DEFAULT_SOURCE_JSON_DIR / "Datasheets_leader.json").read_text(encoding="utf-8")
        ),
    )
    target_ids = {
        cast(str, row["fields"]["attached_id"])
        for row in cast(list[dict[str, Any]], leader_payload["rows"])
        if row["fields"]["leader_id"] == KHARSETH_DATASHEET_ID
    }
    datasheet_payload = cast(
        dict[str, Any],
        json.loads((DEFAULT_SOURCE_JSON_DIR / "Datasheets.json").read_text(encoding="utf-8")),
    )
    names_by_id = {
        cast(str, row["fields"]["id"]): cast(str, row["fields"]["name"])
        for row in cast(list[dict[str, Any]], datasheet_payload["rows"])
    }
    assert {names_by_id[target_id] for target_id in target_ids} == {
        "Corsair Voidreavers",
        "Corsair Voidscarred",
    }

    assert len(AELDARI_KHARSETH_HEIGHT_OVERRIDES) == 1
    geometry = AELDARI_KHARSETH_HEIGHT_OVERRIDES[0]
    assert geometry.datasheet_id == KHARSETH_DATASHEET_ID
    assert geometry.model_name == "Kharseth - EPIC HERO"
    assert geometry.height == 2.5
    assert geometry.height_units is GeometrySourceUnits.INCHES
    assert geometry.reviewer_status is GeometryReviewStatus.ACCEPTED
    assert geometry.evidence_kind is GeometryEvidenceKind.MANUAL_MEASUREMENT
    assert "Warhammer Event Companion 2026-06-12 p.59 (32mm base)" in (
        geometry.height_document_reference
    )


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = kharseth_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)
