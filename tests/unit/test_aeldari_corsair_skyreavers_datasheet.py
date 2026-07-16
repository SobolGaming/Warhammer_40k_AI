from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    DEFAULT_SOURCE_JSON_DIR,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_corsair_skyreavers_rule_ir import (
    OUTPUT_PATH,
    RAID_AND_RUN_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import CatalogAbilitySupport
from warhammer40k_core.core.wargear_selection_limits import (
    DatasheetWargearSelectionLimit,
    WargearSelectionLimitError,
)
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.catalog_fight_end_triggered_movement_support import (
    CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
    CatalogFightEndTriggeredMovementDescriptor,
    clause_is_fight_end_triggered_movement,
    effect_is_fight_end_triggered_movement,
    fight_end_triggered_movement_descriptor,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.list_validation import (
    UnitMusterSelection,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.list_validation_errors import (
    ListValidationError,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scaled_wargear_limits import (
    ScaledWargearSelection,
    validate_scaled_wargear_selections,
)
from warhammer40k_core.engine.unit_factory import UnitFactory
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.rules.rule_ir import (
    RuleConditionKind,
    RuleEffectKind,
    RuleIR,
    RuleParameter,
    RuleParseDiagnostic,
    RuleTargetKind,
    RuleTriggerKind,
    RuleUnsupportedReason,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_corsair_skyreavers_2026_06 as skyreavers_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_CORSAIR_SKYREAVERS_HEIGHT_OVERRIDES,
)

SKYREAVERS_DATASHEET_ID = "000004196"
SKYREAVERS_PDF_SHA256 = "48cf09f605dc29b42555d5800c239879c1fc590f85a6a45b0a1f14739b03f0a9"
FELARCH_PROFILE_ID = "000004196:skyreaver-felarch"
SKYREAVER_PROFILE_ID = "000004196:skyreavers"


def test_skyreavers_generated_rule_ir_artifact_is_current_and_source_bound() -> None:
    committed_payload = cast(
        dict[str, Any],
        json.loads(OUTPUT_PATH.read_text(encoding="utf-8")),
    )

    assert committed_payload == generated_artifact_payload()
    assert skyreavers_package.SOURCE_PDF_SHA256 == SKYREAVERS_PDF_SHA256
    assert skyreavers_package.SOURCE_PAGE_NUMBERS == (20, 21)
    assert skyreavers_package.DATASHEET_ID == SKYREAVERS_DATASHEET_ID
    assert skyreavers_package.DATASHEET_NAME == "Corsair Skyreavers"
    assert skyreavers_package.supported_datasheet_source_row_ids() == (RAID_AND_RUN_ROW_ID,)
    assert committed_payload["package_hash"] == skyreavers_package.PACKAGE_HASH


def test_skyreavers_generated_rule_ir_loader_rejects_package_hash_drift() -> None:
    payload = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))
    payload["package_hash"] = "0" * 64

    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="package hash is stale",
    ):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("artifact_schema", "unknown", "schema is unsupported"),
        ("source_package_id", "", "source_package_id must be non-empty"),
        ("source_pdf_filename", " invalid ", "source_pdf_filename must be non-empty"),
        ("source_pdf_sha256", "invalid", "source_pdf_sha256 must be lowercase SHA-256"),
        ("source_page_numbers", [19, 20], "source page provenance drifted"),
        ("datasheet_id", "000000000", "datasheet identity drifted"),
        ("records", {}, "source-row inventory drifted"),
    ],
)
def test_skyreavers_generated_rule_ir_loader_rejects_provenance_drift(
    field_name: str,
    value: object,
    message: str,
) -> None:
    payload = _generated_artifact_payload_copy()
    payload[field_name] = value
    _rehash_artifact(payload)

    with pytest.raises(skyreavers_package.CorsairSkyreaversRuleIrArtifactError, match=message):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())


def test_skyreavers_generated_rule_ir_loader_rejects_invalid_json_and_record_drift() -> None:
    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="artifact is invalid",
    ):
        skyreavers_package.validate_generated_artifact_bytes(b"{")

    payload = _generated_artifact_payload_copy()
    record = cast(dict[str, Any], cast(dict[str, Any], payload["records"])[RAID_AND_RUN_ROW_ID])
    record["ability_name"] = ""
    _rehash_artifact(payload)
    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="ability_name must be non-empty",
    ):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())

    payload = _generated_artifact_payload_copy()
    record = cast(dict[str, Any], cast(dict[str, Any], payload["records"])[RAID_AND_RUN_ROW_ID])
    record["normalized_text_sha256"] = "0" * 64
    _rehash_artifact(payload)
    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="normalized rule text hash is stale",
    ):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())

    payload = _generated_artifact_payload_copy()
    record = cast(dict[str, Any], cast(dict[str, Any], payload["records"])[RAID_AND_RUN_ROW_ID])
    record["rule_ir"] = {}
    _rehash_artifact(payload)
    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="RuleIR payload is invalid",
    ):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())

    payload = _generated_artifact_payload_copy()
    record = cast(dict[str, Any], cast(dict[str, Any], payload["records"])[RAID_AND_RUN_ROW_ID])
    record["rule_ir"] = replace(_raid_and_run_rule_ir(), source_id="drifted:source").to_payload()
    _rehash_artifact(payload)
    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="source identity drifted",
    ):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())

    payload = _generated_artifact_payload_copy()
    record = cast(dict[str, Any], cast(dict[str, Any], payload["records"])[RAID_AND_RUN_ROW_ID])
    rule_ir = _raid_and_run_rule_ir()
    record["rule_ir"] = replace(
        rule_ir,
        clauses=(
            replace(
                rule_ir.clauses[0],
                unsupported_reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
                diagnostics=(
                    RuleParseDiagnostic(
                        reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
                        message="unsupported test rule",
                        source_span=rule_ir.clauses[0].source_span,
                    ),
                ),
            ),
        ),
    ).to_payload()
    _rehash_artifact(payload)
    with pytest.raises(
        skyreavers_package.CorsairSkyreaversRuleIrArtifactError,
        match="must be fully supported",
    ):
        skyreavers_package.validate_generated_artifact_bytes(json.dumps(payload).encode())


def test_raid_and_run_rule_ir_encodes_exact_generic_semantics() -> None:
    rule_ir = _raid_and_run_rule_ir()

    assert rule_ir.is_supported
    assert len(rule_ir.clauses) == 1
    clause = rule_ir.clauses[0]
    assert clause_is_fight_end_triggered_movement(clause)
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert parameter_payload(clause.trigger.parameters) == {
        "edge": "end",
        "owner": "either_player",
        "phase": "fight",
        "subject": "this_unit",
        "timing_window": "end_fight_phase",
    }
    assert clause.conditions[0].kind is RuleConditionKind.TARGET_CONSTRAINT
    assert parameter_payload(clause.conditions[0].parameters) == {
        "gate_subject": "this_unit",
        "relationship": "eligible_to_fight_this_phase",
    }
    assert clause.target is not None
    assert clause.target.kind is RuleTargetKind.THIS_UNIT
    assert tuple(effect.kind for effect in clause.effects) == (
        RuleEffectKind.OUT_OF_PHASE_ACTION,
        RuleEffectKind.OUT_OF_PHASE_ACTION,
    )
    descriptor = fight_end_triggered_movement_descriptor(clause)
    assert descriptor.distance_dice_quantity == 1
    assert descriptor.distance_dice_sides == 3
    assert descriptor.distance_bonus == 3
    assert catalog_rule_ir_consumers_for_rule(rule_ir) == (
        CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID,
    )


def test_raid_and_run_generic_classifier_rejects_semantic_drift() -> None:
    clause = _raid_and_run_rule_ir().clauses[0]
    assert clause.trigger is not None
    assert clause.target is not None
    normal_effect, fall_back_effect = clause.effects

    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        clause_is_fight_end_triggered_movement(cast(Any, None))
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        fight_end_triggered_movement_descriptor(cast(Any, None))
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec"):
        effect_is_fight_end_triggered_movement(cast(Any, None))
    with pytest.raises(GameLifecycleError, match="not supported"):
        fight_end_triggered_movement_descriptor(replace(clause, trigger=None))

    drifted_clauses = (
        replace(clause, trigger=None),
        replace(clause, trigger=replace(clause.trigger, kind=RuleTriggerKind.DICE_ROLL)),
        replace(clause, trigger=replace(clause.trigger, parameters=())),
        replace(clause, target=None),
        replace(
            clause,
            target=replace(
                clause.target,
                parameters=(RuleParameter(key="drift", value="drift"),),
            ),
        ),
        replace(clause, conditions=()),
        replace(
            clause,
            conditions=(replace(clause.conditions[0], kind=RuleConditionKind.AURA),),
        ),
        replace(clause, conditions=(replace(clause.conditions[0], parameters=()),)),
        replace(clause, effects=(normal_effect,)),
        replace(clause, effects=(normal_effect, normal_effect)),
    )
    assert not any(clause_is_fight_end_triggered_movement(item) for item in drifted_clauses)

    assert not effect_is_fight_end_triggered_movement(
        replace(normal_effect, kind=RuleEffectKind.MODIFY_DICE_ROLL)
    )
    assert not effect_is_fight_end_triggered_movement(replace(normal_effect, parameters=()))
    assert not effect_is_fight_end_triggered_movement(
        replace(
            normal_effect,
            parameters=tuple(
                replace(parameter, value=4) if parameter.key == "distance_bonus" else parameter
                for parameter in normal_effect.parameters
            ),
        )
    )
    assert not effect_is_fight_end_triggered_movement(
        replace(
            normal_effect,
            parameters=tuple(
                replace(parameter, value="within")
                if parameter.key == "engagement_state"
                else parameter
                for parameter in normal_effect.parameters
            ),
        )
    )

    descriptor = fight_end_triggered_movement_descriptor(clause)
    with pytest.raises(GameLifecycleError, match="normal effect is invalid"):
        replace(descriptor, normal_effect=cast(Any, None))
    with pytest.raises(GameLifecycleError, match="Fall Back effect is invalid"):
        replace(descriptor, fall_back_effect=cast(Any, None))
    with pytest.raises(GameLifecycleError, match="distance_dice_sides is invalid"):
        replace(descriptor, distance_dice_sides=0)
    with pytest.raises(GameLifecycleError, match="engagement state must be boolean"):
        descriptor.effect_for_engagement_state(is_engaged=cast(Any, 1))

    assert (
        CatalogFightEndTriggeredMovementDescriptor(
            normal_effect=normal_effect,
            fall_back_effect=fall_back_effect,
            distance_dice_quantity=1,
            distance_dice_sides=3,
            distance_bonus=0,
        ).distance_bonus
        == 0
    )


def test_skyreavers_scaled_wargear_limit_types_fail_fast() -> None:
    limit = DatasheetWargearSelectionLimit(
        selection_group_id="skyreavers-special-weapons",
        models_per_increment=5,
        max_group_selections_per_increment=2,
        max_option_selections_per_increment=1,
    )
    assert DatasheetWargearSelectionLimit.from_payload(limit.to_payload()) == limit
    with pytest.raises(WargearSelectionLimitError, match="cannot exceed its group limit"):
        replace(limit, max_option_selections_per_increment=3)
    with pytest.raises(WargearSelectionLimitError, match="must be a positive integer"):
        replace(limit, models_per_increment=0)

    selection = ScaledWargearSelection(
        option_id="blaster-option",
        selection_group_id="skyreavers-special-weapons",
        models_per_increment=5,
        max_group_selections_per_increment=2,
        max_option_selections_per_increment=1,
        selected_count=1,
    )
    invalid_calls = (
        (0, (selection,), "positive integer"),
        (5, cast(tuple[ScaledWargearSelection, ...], []), "requires selections"),
        (5, (cast(ScaledWargearSelection, object()),), "invalid value"),
        (5, (replace(selection, option_id=""),), "non-empty stripped text"),
        (5, (replace(selection, selected_count=-1),), "non-negative integer"),
        (5, (replace(selection, models_per_increment=0),), "positive integer"),
        (
            5,
            (
                selection,
                replace(selection, option_id="flamer-option", models_per_increment=10),
            ),
            "share limit metadata",
        ),
    )
    for unit_model_count, selections, message in invalid_calls:
        with pytest.raises(ListValidationError, match=message):
            validate_scaled_wargear_selections(
                unit_model_count=unit_model_count,
                selections=selections,
                error_type=ListValidationError,
            )


def test_skyreavers_catalog_preserves_every_datasheet_section() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    datasheet = catalog.datasheet_by_id(SKYREAVERS_DATASHEET_ID)

    assert datasheet.name == "Corsair Skyreavers"
    assert datasheet.keywords.keywords == (
        "AELDARI",
        "ANHRATHE",
        "CORSAIR SKYREAVERS",
        "FLY",
        "GRENADES",
        "INFANTRY",
        "JUMP PACK",
    )
    assert datasheet.keywords.faction_keywords == ("ASURYANI",)
    assert not datasheet.mustering_options

    profiles = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    assert set(profiles) == {FELARCH_PROFILE_ID, SKYREAVER_PROFILE_ID}
    assert profiles[FELARCH_PROFILE_ID].name == "Skyreaver Felarch"
    assert profiles[SKYREAVER_PROFILE_ID].name == "Skyreavers"
    for profile in profiles.values():
        characteristics = {
            characteristic.characteristic: characteristic.final
            for characteristic in profile.characteristics
        }
        assert {
            Characteristic.MOVEMENT: 12,
            Characteristic.TOUGHNESS: 3,
            Characteristic.SAVE: 5,
            Characteristic.WOUNDS: 1,
            Characteristic.LEADERSHIP: 7,
            Characteristic.OBJECTIVE_CONTROL: 1,
        }.items() <= characteristics.items()
        assert profile.base_size.diameter_mm == 28.5
    assert tuple(
        (part.model_profile_id, part.min_models, part.max_models) for part in datasheet.composition
    ) == (
        (FELARCH_PROFILE_ID, 1, 1),
        (SKYREAVER_PROFILE_ID, 4, 9),
    )

    wargear = {
        item.wargear_id: item
        for item in catalog.wargear
        if item.wargear_id.startswith(f"{SKYREAVERS_DATASHEET_ID}:")
    }
    assert set(wargear) == {
        "000004196:blaster",
        "000004196:blast-pistol",
        "000004196:flamer",
        "000004196:fusion-gun",
        "000004196:neuro-disruptor",
        "000004196:shredder",
        "000004196:shuriken-pistol",
        "000004196:corsair-blade",
        "000004196:close-combat-weapon",
    }
    _assert_weapon_profile(
        wargear["000004196:blaster"].weapon_profiles[0],
        range_inches=18,
        attacks="1",
        skill=3,
        strength=8,
        armor_penetration=-4,
        damage="D6+1",
        keywords=(WeaponKeyword.ASSAULT,),
    )
    _assert_weapon_profile(
        wargear["000004196:blast-pistol"].weapon_profiles[0],
        range_inches=6,
        attacks="1",
        skill=3,
        strength=8,
        armor_penetration=-3,
        damage="D3",
        keywords=(WeaponKeyword.ASSAULT, WeaponKeyword.PISTOL),
    )
    flamer = wargear["000004196:flamer"].weapon_profiles[0]
    _assert_weapon_profile(
        flamer,
        range_inches=12,
        attacks="D6",
        skill=0,
        strength=4,
        armor_penetration=0,
        damage="1",
        keywords=(WeaponKeyword.ASSAULT, WeaponKeyword.IGNORES_COVER, WeaponKeyword.TORRENT),
    )
    fusion = wargear["000004196:fusion-gun"].weapon_profiles[0]
    assert tuple(ability.name for ability in fusion.abilities) == ("Melta 2",)
    neuro = wargear["000004196:neuro-disruptor"].weapon_profiles[0]
    assert tuple(ability.name for ability in neuro.abilities) == ("Anti-Infantry 2+",)
    assert wargear["000004196:shredder"].weapon_profiles[0].keywords == (
        WeaponKeyword.ASSAULT,
        WeaponKeyword.TORRENT,
    )
    assert wargear["000004196:corsair-blade"].weapon_profiles[0].range_profile.kind is (
        RangeProfileKind.MELEE
    )
    assert wargear["000004196:close-combat-weapon"].weapon_profiles[0].range_profile.kind is (
        RangeProfileKind.MELEE
    )

    abilities = {ability.name: ability for ability in datasheet.abilities}
    assert set(abilities) == {"Deep Strike", "Scouts", "Battle Focus", "Raid and Run"}
    assert abilities["Scouts"].parameter_tokens == ("7",)
    assert abilities["Raid and Run"].support is CatalogAbilitySupport.GENERIC_RULE_IR
    assert abilities["Raid and Run"].rule_ir_payload is not None

    structured_options = tuple(option for option in datasheet.wargear_options if option.effects)
    assert len(structured_options) == 5
    felarch_option = next(
        option for option in structured_options if option.model_profile_id == FELARCH_PROFILE_ID
    )
    assert felarch_option.allowed_wargear_ids == (
        "000004196:blast-pistol",
        "000004196:neuro-disruptor",
    )
    scaled_options = tuple(
        option for option in structured_options if option.model_profile_id == SKYREAVER_PROFILE_ID
    )
    assert len(scaled_options) == 4
    assert {
        option.allowed_wargear_ids[1]
        if option.allowed_wargear_ids[0] == "000004196:close-combat-weapon"
        else option.allowed_wargear_ids[0]
        for option in scaled_options
    } == {
        "000004196:blaster",
        "000004196:flamer",
        "000004196:fusion-gun",
        "000004196:shredder",
    }
    for option in scaled_options:
        assert option.selection_limit is not None
        assert option.selection_limit.models_per_increment == 5
        assert option.selection_limit.max_group_selections_per_increment == 2
        assert option.selection_limit.max_option_selections_per_increment == 1


def test_skyreavers_points_and_geometry_are_source_bound() -> None:
    points_payload = cast(
        dict[str, Any],
        json.loads((DEFAULT_SOURCE_JSON_DIR / "Datasheets_models_cost.json").read_text()),
    )
    points = tuple(
        (row["fields"]["description"], row["fields"]["cost"])
        for row in cast(list[dict[str, Any]], points_payload["rows"])
        if row["fields"]["datasheet_id"] == SKYREAVERS_DATASHEET_ID
    )
    assert points == (("5 models", "75"), ("10 models", "150"))

    assert len(AELDARI_CORSAIR_SKYREAVERS_HEIGHT_OVERRIDES) == 2
    assert {override.model_name for override in AELDARI_CORSAIR_SKYREAVERS_HEIGHT_OVERRIDES} == {
        "Skyreaver Felarch",
        "Skyreavers",
    }
    assert {override.height for override in AELDARI_CORSAIR_SKYREAVERS_HEIGHT_OVERRIDES} == {3.25}


def test_skyreavers_scaled_wargear_limits_and_model_assignment() -> None:
    package = _ability_support_catalog_package()
    datasheet = package.army_catalog.datasheet_by_id(SKYREAVERS_DATASHEET_ID)
    five_models = _model_selections(skyreaver_count=4)
    ten_models = _model_selections(skyreaver_count=9)
    blaster_option = "000004196:blaster-close-combat-weapon:option-2"
    flamer_option = "000004196:flamer-close-combat-weapon:option-2"
    fusion_option = "000004196:fusion-gun-close-combat-weapon:option-2"
    blaster_ids = ("000004196:blaster", "000004196:close-combat-weapon")
    flamer_ids = ("000004196:close-combat-weapon", "000004196:flamer")
    fusion_ids = ("000004196:close-combat-weapon", "000004196:fusion-gun")

    resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id="000004196:skyreaver-felarch-replacement:option-1",
                model_profile_id=FELARCH_PROFILE_ID,
                wargear_ids=("000004196:blast-pistol",),
            ),
        ),
        model_profile_selections=five_models,
    )

    with pytest.raises(ListValidationError, match="scaled option limit"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=blaster_option,
                    model_profile_id=SKYREAVER_PROFILE_ID,
                    wargear_ids=blaster_ids,
                    selection_count=2,
                ),
            ),
            model_profile_selections=five_models,
        )

    resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id=blaster_option,
                model_profile_id=SKYREAVER_PROFILE_ID,
                wargear_ids=blaster_ids,
            ),
            WargearSelection(
                option_id=flamer_option,
                model_profile_id=SKYREAVER_PROFILE_ID,
                wargear_ids=flamer_ids,
            ),
        ),
        model_profile_selections=five_models,
    )
    with pytest.raises(ListValidationError, match="scaled limit"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=blaster_option,
                    model_profile_id=SKYREAVER_PROFILE_ID,
                    wargear_ids=blaster_ids,
                ),
                WargearSelection(
                    option_id=flamer_option,
                    model_profile_id=SKYREAVER_PROFILE_ID,
                    wargear_ids=flamer_ids,
                ),
                WargearSelection(
                    option_id=fusion_option,
                    model_profile_id=SKYREAVER_PROFILE_ID,
                    wargear_ids=fusion_ids,
                ),
            ),
            model_profile_selections=five_models,
        )
    counted_selection = WargearSelection(
        option_id=blaster_option,
        model_profile_id=SKYREAVER_PROFILE_ID,
        wargear_ids=blaster_ids,
        selection_count=2,
    )
    assert WargearSelection.from_payload(counted_selection.to_payload()) == counted_selection
    resolved_ten = resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(counted_selection,),
        model_profile_selections=ten_models,
    )
    assert (
        next(
            selection for selection in resolved_ten if selection.option_id == blaster_option
        ).resolved_selection_count
        == 2
    )

    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="skyreavers-test-army",
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id="skyreavers-test-unit",
            datasheet_id=SKYREAVERS_DATASHEET_ID,
            model_profile_selections=ten_models,
            wargear_selections=(
                WargearSelection(
                    option_id=blaster_option,
                    model_profile_id=SKYREAVER_PROFILE_ID,
                    wargear_ids=blaster_ids,
                    selection_count=2,
                ),
            ),
        ),
    )
    skyreavers = tuple(
        model for model in unit.own_models if model.model_profile_id == SKYREAVER_PROFILE_ID
    )
    assert sum("000004196:blaster" in model.wargear_ids for model in skyreavers) == 2
    assert sum("000004196:close-combat-weapon" in model.wargear_ids for model in skyreavers) == 2
    assert sum("000004196:shuriken-pistol" in model.wargear_ids for model in skyreavers) == 7
    assert sum("000004196:corsair-blade" in model.wargear_ids for model in skyreavers) == 7


def _raid_and_run_rule_ir() -> RuleIR:
    payload = skyreavers_package.datasheet_rule_ir_payload_by_source_row_id(RAID_AND_RUN_ROW_ID)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _generated_artifact_payload_copy() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(json.dumps(generated_artifact_payload())))


def _rehash_artifact(payload: dict[str, Any]) -> None:
    encoded = json.dumps(
        {**payload, "package_hash": ""},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    payload["package_hash"] = hashlib.sha256(encoded).hexdigest()


def _model_selections(*, skyreaver_count: int) -> tuple[ModelProfileSelection, ...]:
    return (
        ModelProfileSelection(model_profile_id=FELARCH_PROFILE_ID, model_count=1),
        ModelProfileSelection(model_profile_id=SKYREAVER_PROFILE_ID, model_count=skyreaver_count),
    )


def _assert_weapon_profile(
    profile: WeaponProfile,
    *,
    range_inches: int,
    attacks: str,
    skill: int,
    strength: int,
    armor_penetration: int,
    damage: str,
    keywords: tuple[WeaponKeyword, ...],
) -> None:
    assert profile.range_profile.kind is RangeProfileKind.DISTANCE
    assert profile.range_profile.distance_inches == range_inches
    if profile.attack_profile.fixed_attacks is not None:
        actual_attacks = str(profile.attack_profile.fixed_attacks)
    else:
        attack_dice = profile.attack_profile.dice_expression
        assert attack_dice is not None
        actual_attacks = attack_dice.canonical()
    assert actual_attacks == attacks
    assert profile.skill.final == skill
    assert profile.strength.final == strength
    assert profile.armor_penetration.final == armor_penetration
    if profile.damage_profile.fixed_damage is not None:
        actual_damage = str(profile.damage_profile.fixed_damage)
    else:
        damage_dice = profile.damage_profile.dice_expression
        assert damage_dice is not None
        actual_damage = damage_dice.canonical()
    assert actual_damage == damage
    assert profile.keywords == keywords
