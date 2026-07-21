from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests.support.catalog_package_fixtures import (
    flesh_hounds_army,
    great_unclean_one_unit,
    keeper_of_secrets_unit,
    resolved_bloodthirster_model_wargear,
    resolved_great_unclean_one_model_wargear,
    resolved_keeper_of_secrets_model_wargear,
    resolved_soul_grinder_model_wargear,
    soul_grinder_unit,
)
from tests.support.wahapedia_bridge_fixtures import (
    bloodcrushers_bridge_artifacts,
    bloodthirster_bridge_artifacts,
    great_unclean_one_bridge_artifacts,
    jakhals_bridge_artifacts,
    kairos_fateweaver_bridge_artifacts,
    keeper_of_secrets_bridge_artifacts,
    lord_of_change_bridge_artifacts,
    no_equipment_daemon_fortification_bridge_artifacts,
    soul_grinder_bridge_artifacts,
    weirdboy_bridge_artifacts,
)
from tests.support.wahapedia_source_fixtures import (
    artifact_by_table,
    bridge_package_id,
    catalog_package_id,
    catalog_version,
    optional_artifact_rows,
    source_ids_from_row,
    support_attachment_source_artifacts,
    unit_resource_wargear_source_artifacts,
    wahapedia_source_artifacts,
)

from warhammer40k_core.core.attachment_eligibility import AttachmentRole
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    BaseSizeKind,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetMusteringOptionEffectKind,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometrySourceUnits,
)
from warhammer40k_core.core.weapon_profiles import (
    WeaponKeyword,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    AbilitySourceKind,
    AbilityTimingDescriptor,
    default_ability_handler_registry,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.catalog_command_point_support import (
    CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.dice_result_override_descriptors import (
    ASPECT_SHRINE_TOKEN_RESOURCE_KIND,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.orks import (
    army_rule as orks_army_rule,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    MusteringOptionSelection,
    UnitMusterSelection,
    resolve_mustering_option_selections,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.list_validation_errors import ListValidationError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.rules.attachment_wargear_requirements import AttachmentWargearRequirement
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleIR,
    RuleIRPayload,
    parameter_payload,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
    EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
    ModelHeightOverride,
    build_wahapedia_canonical_bridge_artifacts,
)


def test_phase17k_bloodcrushers_bridge_generates_pdf_corrected_canonical_catalog() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    profiles_by_id = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    composition_by_id = {part.model_profile_id: part for part in datasheet.composition}
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}

    assert datasheet.name == "Bloodcrushers"
    assert datasheet.keywords.keywords == (
        "BLOODCRUSHERS",
        "CHAOS",
        "DAEMON",
        "KHORNE",
        "MOUNTED",
    )
    assert "SHADOW LEGION" not in datasheet.keywords.keywords
    assert datasheet.keywords.faction_keywords == ("LEGIONES DAEMONICA",)
    assert composition_by_id["000001115:bloodhunter"].min_models == 1
    assert composition_by_id["000001115:bloodhunter"].max_models == 1
    assert composition_by_id["000001115:bloodcrushers"].min_models == 2
    assert composition_by_id["000001115:bloodcrushers"].max_models == 5

    bloodcrusher = profiles_by_id["000001115:bloodcrushers"]
    assert bloodcrusher.base_size.kind is BaseSizeKind.OVAL
    assert math.isclose(bloodcrusher.base_size.length_mm or 0.0, 90.0)
    assert math.isclose(bloodcrusher.base_size.width_mm or 0.0, 52.5)
    assert bloodcrusher.characteristic(Characteristic.MOVEMENT).raw == 10
    assert bloodcrusher.characteristic(Characteristic.TOUGHNESS).raw == 7
    assert bloodcrusher.characteristic(Characteristic.SAVE).raw == 3
    assert bloodcrusher.characteristic(Characteristic.INVULNERABLE_SAVE).raw == 5
    assert bloodcrusher.characteristic(Characteristic.WOUNDS).raw == 4
    assert bloodcrusher.characteristic(Characteristic.LEADERSHIP).raw == 7
    assert bloodcrusher.characteristic(Characteristic.OBJECTIVE_CONTROL).raw == 2
    assert package.model_geometries[0].height.height_inches == 2.75
    footprint_evidence = next(
        evidence
        for evidence in package.model_geometries[0].evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )
    assert footprint_evidence.source_id.endswith(":base-size:page-65-chaos-daemons-bloodcrushers")
    assert (
        footprint_evidence.document_reference == EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    )
    assert (
        Path(__file__).resolve().parents[3] / EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    ).is_file()
    assert EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID in bloodcrusher.source_ids
    assert footprint_evidence.source_id in bloodcrusher.source_ids

    assert wargear_by_id["000001115:hellblade"].weapon_profiles[0].attack_profile.fixed_attacks == 2
    horn = wargear_by_id["000001115:juggernauts-bladed-horn"].weapon_profiles[0]
    assert horn.attack_profile.fixed_attacks == 4
    assert tuple(keyword.value for keyword in horn.keywords) == ("Extra Attacks", "Lance")
    assert wargear_by_id["000001115:daemonic-icon"].weapon_profiles == ()
    assert wargear_by_id["000001115:instrument-of-chaos"].weapon_profiles == ()

    instrument_option = options_by_id["000001115:instrument-of-chaos:option-1"]
    assert instrument_option.model_profile_id == "000001115:bloodcrushers"
    assert instrument_option.allowed_wargear_ids == ("000001115:instrument-of-chaos",)
    assert (
        instrument_option.conditions[0].kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH
    )
    assert instrument_option.conditions[0].wargear_ids == ("000001115:daemonic-icon",)
    assert instrument_option.effects[0].kind is WargearOptionEffectKind.ADD_WARGEAR
    assert instrument_option.effects[0].wargear_id == "000001115:instrument-of-chaos"

    assert "Deep Strike" in abilities_by_name
    assert abilities_by_name["Deep Strike"].timing_tags == ("deployment", "reserves")
    assert "The Shadow of Chaos" in abilities_by_name
    assert "Brass Stampede" in abilities_by_name
    assert "Daemonic Icon" in abilities_by_name
    assert "Instrument of Chaos" in abilities_by_name
    daemonic_icon = abilities_by_name["Daemonic Icon"]
    instrument = abilities_by_name["Instrument of Chaos"]
    assert daemonic_icon.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert daemonic_icon.source_wargear_id == "000001115:daemonic-icon"
    assert daemonic_icon.support is CatalogAbilitySupport.GENERIC_RULE_IR
    assert instrument.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert instrument.source_wargear_id == "000001115:instrument-of-chaos"
    assert instrument.support is CatalogAbilitySupport.GENERIC_RULE_IR
    icon_ir = RuleIR.from_payload(cast(RuleIRPayload, daemonic_icon.rule_ir_payload))
    instrument_ir = RuleIR.from_payload(cast(RuleIRPayload, instrument.rule_ir_payload))
    icon_effect = icon_ir.clauses[0].effects[0]
    instrument_effect = instrument_ir.clauses[0].effects[0]
    assert icon_ir.clauses[0].target is not None
    assert icon_ir.clauses[0].target.kind.value == "this_unit"
    assert icon_effect.kind is RuleEffectKind.SET_CHARACTERISTIC
    assert parameter_payload(icon_effect.parameters) == {
        "characteristic": "leadership",
        "value": "6+",
    }
    assert instrument_ir.clauses[0].target is not None
    assert instrument_ir.clauses[0].target.kind.value == "this_unit"
    assert instrument_effect.kind is RuleEffectKind.MODIFY_DICE_ROLL
    assert parameter_payload(instrument_effect.parameters) == {
        "delta": 1,
        "roll_type": "charge",
    }
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_bridged_title_case_keywords_support_exact_runtime_keyword_gate() -> None:
    source_keywords = tuple(
        row.runtime_fields_payload()["keyword"]
        for row in artifact_by_table(
            wahapedia_source_artifacts(),
            "Datasheets_keywords",
        ).rows
        if row.runtime_fields_payload()["datasheet_id"] == "000000004"
    )
    assert "Orks" in source_keywords
    assert "Infantry" in source_keywords

    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=weirdboy_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000000004")
    assert datasheet.keywords.faction_keywords == ("ORKS",)
    assert "INFANTRY" in datasheet.keywords.keywords

    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-orks",
        selection=UnitMusterSelection(
            unit_selection_id="weirdboy-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000000004:weirdboy",
                    model_count=1,
                ),
            ),
        ),
        datasheet=datasheet,
    )

    assert unit.faction_keywords == ("ORKS",)
    assert "INFANTRY" in unit.keywords
    assert orks_army_rule._unit_has_waaagh(unit)  # pyright: ignore[reportPrivateUsage]


def test_phase17k_bloodthirster_bridge_supports_replacement_wargear_loadouts() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodthirster_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000002582")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    model_profile_id = "000002582:bloodthirster"
    hellfire_breath_id = "000002582:hellfire-breath"
    great_axe_id = "000002582:great-axe-of-khorne"
    axe_id = "000002582:axe-of-khorne"
    bloodflail_id = "000002582:bloodflail"
    lash_id = "000002582:lash-of-khorne"
    bloodflail_option_id = "000002582:axe-of-khorne-bloodflail:option-1"
    lash_option_id = "000002582:axe-of-khorne-lash-of-khorne:option-1"

    assert wargear_by_id[great_axe_id].name == "Great axe of Khorne"
    assert tuple(profile.name for profile in wargear_by_id[great_axe_id].weapon_profiles) == (
        "Great axe of Khorne - strike",
        "Great axe of Khorne - sweep",
    )
    assert tuple(profile.name for profile in wargear_by_id[axe_id].weapon_profiles) == (
        "Axe of Khorne - strike",
        "Axe of Khorne - sweep",
    )
    assert resolved_bloodthirster_model_wargear(package, requested_selections=()) == (
        hellfire_breath_id,
        great_axe_id,
    )

    bloodflail_option = options_by_id[bloodflail_option_id]
    lash_option = options_by_id[lash_option_id]
    assert bloodflail_option.default_wargear_ids == ()
    assert bloodflail_option.allowed_wargear_ids == (axe_id, bloodflail_id)
    assert bloodflail_option.max_selections == 2
    assert bloodflail_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert bloodflail_option.effects[0].wargear_id == axe_id
    assert bloodflail_option.effects[0].replaced_wargear_id == great_axe_id
    assert bloodflail_option.effects[1].kind is WargearOptionEffectKind.ADD_WARGEAR
    assert bloodflail_option.effects[1].wargear_id == bloodflail_id
    assert (
        bloodflail_option.conditions[0].kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH
    )
    assert bloodflail_option.conditions[0].wargear_ids == (lash_id,)

    assert resolved_bloodthirster_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=bloodflail_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(axe_id, bloodflail_id),
            ),
        ),
    ) == (hellfire_breath_id, axe_id, bloodflail_id)
    assert resolved_bloodthirster_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=lash_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(axe_id, lash_id),
            ),
        ),
    ) == (hellfire_breath_id, axe_id, lash_id)

    with pytest.raises(ListValidationError, match="replacement count"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=bloodflail_option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(bloodflail_id,),
                ),
            ),
        )
    with pytest.raises(ListValidationError, match="structured wargear option condition"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=bloodflail_option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(axe_id, bloodflail_id),
                ),
                WargearSelection(
                    option_id=lash_option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(axe_id, lash_id),
                ),
            ),
        )

    assert lash_option.allowed_wargear_ids == (axe_id, lash_id)


def test_phase17k_great_unclean_one_bridge_supports_single_replacement_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=great_unclean_one_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001130")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}
    model_profile_id = "000001130:great-unclean-one"
    plague_flail_id = "000001130:plague-flail"
    putrid_vomit_id = "000001130:putrid-vomit"
    bilesword_id = "000001130:bilesword"
    bileblade_id = "000001130:bileblade"
    doomsday_bell_id = "000001130:doomsday-bell"
    bileblade_option_id = "000001130:bileblade:option-1"
    doomsday_bell_option_id = "000001130:doomsday-bell:option-2"

    assert resolved_great_unclean_one_model_wargear(package, requested_selections=()) == (
        plague_flail_id,
        putrid_vomit_id,
        bilesword_id,
    )

    bileblade_option = options_by_id[bileblade_option_id]
    doomsday_bell_option = options_by_id[doomsday_bell_option_id]
    assert bileblade_option.default_wargear_ids == ()
    assert bileblade_option.allowed_wargear_ids == (bileblade_id,)
    assert bileblade_option.max_selections == 1
    assert bileblade_option.conditions == ()
    assert bileblade_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert bileblade_option.effects[0].wargear_id == bileblade_id
    assert bileblade_option.effects[0].replaced_wargear_id == plague_flail_id
    assert doomsday_bell_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert doomsday_bell_option.effects[0].wargear_id == doomsday_bell_id
    assert doomsday_bell_option.effects[0].replaced_wargear_id == bilesword_id
    assert wargear_by_id[doomsday_bell_id].weapon_profiles[0].keywords == (
        WeaponKeyword.LETHAL_HITS,
    )
    assert "000001130:reverberating-summons" not in wargear_by_id
    reverberating_summons = abilities_by_name["Reverberating Summons"]
    assert reverberating_summons.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert reverberating_summons.source_wargear_id == doomsday_bell_id

    assert resolved_great_unclean_one_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=bileblade_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(bileblade_id,),
            ),
        ),
    ) == (putrid_vomit_id, bilesword_id, bileblade_id)
    assert resolved_great_unclean_one_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=bileblade_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(bileblade_id,),
            ),
            WargearSelection(
                option_id=doomsday_bell_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(doomsday_bell_id,),
            ),
        ),
    ) == (putrid_vomit_id, bileblade_id, doomsday_bell_id)
    reverberating_record = AbilityCatalogRecord(
        record_id="phase17k:test:great-unclean-one:reverberating-summons",
        definition=AbilityDefinition(
            ability_id=reverberating_summons.ability_id,
            name=reverberating_summons.name,
            source_id=reverberating_summons.source_id,
            when_descriptor="Catalog bridge wargear profile source test.",
            effect_descriptor=reverberating_summons.effect_description,
            restrictions_descriptor=(
                f"Selected wargear required: {reverberating_summons.source_wargear_id}."
            ),
            timing=AbilityTimingDescriptor(trigger_kind=TimingTriggerKind.ANY_PHASE),
            replay_payload=validate_json_value(
                {
                    "source_wargear_id": reverberating_summons.source_wargear_id,
                }
            ),
        ),
        source_kind=AbilitySourceKind.WARGEAR,
        datasheet_id=datasheet.datasheet_id,
        wargear_id=reverberating_summons.source_wargear_id,
    )
    default_unit = great_unclean_one_unit(package=package, requested_selections=())
    doomsday_bell_unit = great_unclean_one_unit(
        package=package,
        requested_selections=(
            WargearSelection(
                option_id=doomsday_bell_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(doomsday_bell_id,),
            ),
        ),
    )
    default_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (reverberating_record,),
            army=flesh_hounds_army(
                package=package,
                unit=default_unit,
                army_id="army-nurgle",
                player_id="player-nurgle-default",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    doomsday_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            (reverberating_record,),
            army=flesh_hounds_army(
                package=package,
                unit=doomsday_bell_unit,
                army_id="army-nurgle",
                player_id="player-nurgle-doomsday",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    assert "Reverberating Summons" not in default_records_by_name
    assert doomsday_records_by_name["Reverberating Summons"].wargear_id == doomsday_bell_id


def test_phase17k_keeper_of_secrets_bridge_supports_optional_one_of_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=keeper_of_secrets_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001137")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    model_profile_id = "000001137:keeper-of-secrets"
    living_whip_id = "000001137:living-whip"
    ritual_knife_id = "000001137:ritual-knife"
    shining_aegis_id = "000001137:shining-aegis"
    option_id = "000001137:equipment-choice:option-1"

    option = options_by_id[option_id]
    assert option.model_profile_id == model_profile_id
    assert option.default_wargear_ids == ()
    assert option.allowed_wargear_ids == (living_whip_id, ritual_knife_id, shining_aegis_id)
    assert option.min_selections == 0
    assert option.max_selections == 1
    assert option.conditions == ()
    assert tuple(effect.kind for effect in option.effects) == (
        WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
        WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
        WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
    )
    assert tuple(effect.wargear_id for effect in option.effects) == option.allowed_wargear_ids
    assert wargear_by_id[shining_aegis_id].weapon_profiles == ()

    shining_aegis = abilities_by_name["Shining Aegis"]
    assert shining_aegis.source_kind is CatalogAbilitySourceKind.WARGEAR
    assert shining_aegis.source_wargear_id == shining_aegis_id
    assert shining_aegis.support is CatalogAbilitySupport.GENERIC_RULE_IR
    shining_aegis_ir = RuleIR.from_payload(cast(RuleIRPayload, shining_aegis.rule_ir_payload))
    shining_aegis_effect = shining_aegis_ir.clauses[0].effects[0]
    assert shining_aegis_effect.kind is RuleEffectKind.SET_CHARACTERISTIC
    assert parameter_payload(shining_aegis_effect.parameters) == {
        "characteristic": "save",
        "value": "3+",
    }
    assert resolved_keeper_of_secrets_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(living_whip_id,),
            ),
        ),
    ) == (
        "000001137:phantasmagoria",
        "000001137:snapping-claws",
        "000001137:witstealer-sword",
        living_whip_id,
    )
    assert resolved_keeper_of_secrets_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(shining_aegis_id,),
            ),
        ),
    ) == (
        "000001137:phantasmagoria",
        "000001137:snapping-claws",
        "000001137:witstealer-sword",
        shining_aegis_id,
    )

    assert resolved_keeper_of_secrets_model_wargear(
        package,
        requested_selections=(),
    ) == (
        "000001137:phantasmagoria",
        "000001137:snapping-claws",
        "000001137:witstealer-sword",
    )
    assert resolved_keeper_of_secrets_model_wargear(
        package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(),
                selection_count=0,
            ),
        ),
    ) == (
        "000001137:phantasmagoria",
        "000001137:snapping-claws",
        "000001137:witstealer-sword",
    )
    with pytest.raises(ListValidationError, match="exceeds maximum selections"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=option_id,
                    model_profile_id=model_profile_id,
                    wargear_ids=(living_whip_id, ritual_knife_id),
                ),
            ),
        )

    whip_unit = keeper_of_secrets_unit(
        package=package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(living_whip_id,),
            ),
        ),
    )
    aegis_unit = keeper_of_secrets_unit(
        package=package,
        requested_selections=(
            WargearSelection(
                option_id=option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(shining_aegis_id,),
            ),
        ),
    )
    all_records = catalog_ability_records_from_catalog(package.army_catalog)
    whip_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            all_records,
            army=flesh_hounds_army(
                package=package,
                unit=whip_unit,
                army_id="army-slaanesh",
                player_id="player-whip",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }
    aegis_records_by_name = {
        record.definition.name: record
        for record in build_player_ability_index(
            all_records,
            army=flesh_hounds_army(
                package=package,
                unit=aegis_unit,
                army_id="army-slaanesh",
                player_id="player-aegis",
            ),
            catalog=package.army_catalog,
        ).all_records()
    }

    assert "Shining Aegis" not in whip_records_by_name
    assert aegis_records_by_name["Shining Aegis"].wargear_id == shining_aegis_id
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_lord_of_change_bridge_keeps_extra_weapon_choice_optional() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=lord_of_change_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001120")
    option = next(
        option
        for option in datasheet.wargear_options
        if option.option_id == "000001120:equipment-choice:option-1"
    )

    assert option.default_wargear_ids == ()
    assert option.allowed_wargear_ids == (
        "000001120:baleful-sword",
        "000001120:rod-of-sorcery",
    )
    assert option.min_selections == 0
    assert option.max_selections == 1
    resolved = resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id=option.option_id,
                model_profile_id="000001120:lord-of-change",
                wargear_ids=(),
                selection_count=0,
            ),
        ),
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="000001120:lord-of-change",
                model_count=1,
            ),
        ),
    )
    assert (
        next(
            selection for selection in resolved if selection.option_id == option.option_id
        ).wargear_ids
        == ()
    )


def test_phase17k_kairos_bridge_consumes_both_command_point_abilities_and_height() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=kairos_fateweaver_bridge_artifacts(),
    )
    records_by_name = {
        record.definition.name: record
        for record in catalog_ability_records_from_catalog(package.army_catalog)
    }

    looks_forward = records_by_name["One Head Looks Forward"]
    looks_back = records_by_name["One Head Looks Back (Aura)"]
    looks_forward_payload = cast(dict[str, JsonValue], looks_forward.definition.replay_payload)
    looks_back_payload = cast(dict[str, JsonValue], looks_back.definition.replay_payload)
    looks_forward_ir = RuleIR.from_payload(cast(RuleIRPayload, looks_forward_payload["rule_ir"]))
    looks_back_ir = RuleIR.from_payload(cast(RuleIRPayload, looks_back_payload["rule_ir"]))
    assert looks_forward_ir.is_supported
    assert looks_back_ir.is_supported
    assert catalog_rule_ir_consumers_for_rule(looks_forward_ir) == (
        CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(looks_back_ir) == (
        CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID,
    )

    geometry = package.model_geometries[0]
    assert geometry.model_profile_id == "000001117:kairos-fateweaver-epic-hero"
    assert geometry.height.height_inches == 7.0
    height_evidence = next(
        evidence
        for evidence in geometry.evidence
        if evidence.evidence_id == geometry.height.evidence_id
    )
    assert height_evidence.evidence_kind is GeometryEvidenceKind.CROWD_SOURCED_MEASUREMENT
    assert height_evidence.document_reference == (
        "https://www.adeptusars.com/miniatures/kairos-fateweaver"
    )
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()


def test_phase17k_soul_grinder_bridge_supports_warpclaw_replacement_wargear() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=soul_grinder_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001151")
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    mustering_options_by_id = {option.option_id: option for option in datasheet.mustering_options}
    model_profile_id = "000001151:soul-grinder"
    harvester_cannon_id = "000001151:harvester-cannon"
    iron_claw_id = "000001151:iron-claw"
    warpsword_id = "000001151:warpsword"
    warpclaw_id = "000001151:warpclaw"
    torrent_id = "000001151:torrent-of-burning-blood"
    scream_id = "000001151:scream-of-despair"
    warpclaw_option_id = "000001151:warpclaw:option-1"
    khorne_allegiance_option_id = "000001151:daemonic-allegiance:khorne"
    slaanesh_allegiance_option_id = "000001151:daemonic-allegiance:slaanesh"

    with pytest.raises(ListValidationError, match="required option group"):
        resolve_mustering_option_selections(datasheet=datasheet, requested_selections=())

    khorne_allegiance = mustering_options_by_id[khorne_allegiance_option_id]
    assert khorne_allegiance.required is True
    assert khorne_allegiance.selection_group_id == "000001151:daemonic-allegiance"
    assert khorne_allegiance.effects[0].kind is DatasheetMusteringOptionEffectKind.ADD_KEYWORD
    assert khorne_allegiance.effects[0].keyword == "KHORNE"
    assert khorne_allegiance.effects[1].kind is DatasheetMusteringOptionEffectKind.ADD_WARGEAR
    assert khorne_allegiance.effects[1].wargear_id == torrent_id

    khorne_unit = soul_grinder_unit(
        package,
        requested_wargear_selections=(),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=khorne_allegiance_option_id),
        ),
    )
    assert "KHORNE" in khorne_unit.keywords
    assert khorne_unit.own_models[0].wargear_ids == (
        harvester_cannon_id,
        iron_claw_id,
        warpsword_id,
        torrent_id,
    )

    warpclaw_option = options_by_id[warpclaw_option_id]
    assert warpclaw_option.default_wargear_ids == ()
    assert warpclaw_option.allowed_wargear_ids == (warpclaw_id,)
    assert warpclaw_option.max_selections == 1
    assert warpclaw_option.conditions == ()
    assert warpclaw_option.effects[0].kind is WargearOptionEffectKind.REPLACE_WARGEAR
    assert warpclaw_option.effects[0].wargear_id == warpclaw_id
    assert warpclaw_option.effects[0].replaced_wargear_id == warpsword_id

    assert resolved_soul_grinder_model_wargear(
        package,
        requested_wargear_selections=(
            WargearSelection(
                option_id=warpclaw_option_id,
                model_profile_id=model_profile_id,
                wargear_ids=(warpclaw_id,),
            ),
        ),
        mustering_option_selections=(
            MusteringOptionSelection(option_id=slaanesh_allegiance_option_id),
        ),
    ) == (harvester_cannon_id, iron_claw_id, warpclaw_id, scream_id)


def test_phase17k_bridge_supports_pdf_declared_no_equipment_and_no_wargear_options() -> None:
    artifacts = no_equipment_daemon_fortification_bridge_artifacts()
    wargear_rows = optional_artifact_rows(artifacts, "Datasheets_wargear")
    option_rows = optional_artifact_rows(artifacts, "Datasheets_options")
    model_rows = artifact_by_table(artifacts, "Datasheets_models").rows
    model_fields_by_datasheet_id = {
        row.runtime_fields_payload()["datasheet_id"]: row.runtime_fields_payload()
        for row in model_rows
    }

    for datasheet_id in ("000001470", "000001588"):
        assert not any(
            row.runtime_fields_payload()["datasheet_id"] == datasheet_id for row in wargear_rows
        )
        assert not any(
            row.runtime_fields_payload()["datasheet_id"] == datasheet_id for row in option_rows
        )
        assert model_fields_by_datasheet_id[datasheet_id]["base_size"] == "Hull"
    assert model_fields_by_datasheet_id["000001588"]["height"] == "6.5"
    assert (
        model_fields_by_datasheet_id["000001588"]["height_document_reference"]
        == "Reddit r/ChaosDaemons40k community measurement; "
        "Battle Foam BFS-4.5 tray storage evidence"
    )


def test_phase17k_bloodcrushers_runtime_instances_manifest_model_wargear_and_abilities() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodcrushers-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001115:bloodcrushers",
                    model_count=2,
                ),
                ModelProfileSelection(
                    model_profile_id="000001115:bloodhunter",
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        ),
        datasheet=datasheet,
    )

    bloodcrushers = tuple(
        model for model in unit.own_models if model.model_profile_id == "000001115:bloodcrushers"
    )
    bearer = bloodcrushers[0]

    assert tuple(ability.name for ability in unit.datasheet_abilities) == (
        "Brass Stampede",
        "Daemonic Icon",
        "Instrument of Chaos",
        "Deep Strike",
        "The Shadow of Chaos",
    )
    assert all(
        model.characteristic(Characteristic.INVULNERABLE_SAVE).raw == 5 for model in unit.own_models
    )
    assert all(
        {
            "000001115:hellblade",
            "000001115:juggernauts-bladed-horn",
        }.issubset(model.wargear_ids)
        for model in unit.own_models
    )
    assert bearer.wargear_ids == (
        "000001115:hellblade",
        "000001115:juggernauts-bladed-horn",
        "000001115:instrument-of-chaos",
    )
    assert "000001115:instrument-of-chaos" not in bloodcrushers[1].wargear_ids
    assert UnitInstance.from_payload(unit.to_payload()).to_payload() == unit.to_payload()


def test_phase17k_selected_optional_wargear_adds_catalog_ir_ability_record() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-khorne",
        selection=UnitMusterSelection(
            unit_selection_id="bloodcrushers-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id="000001115:bloodcrushers",
                    model_count=2,
                ),
                ModelProfileSelection(
                    model_profile_id="000001115:bloodhunter",
                    model_count=1,
                ),
            ),
            wargear_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        ),
        datasheet=datasheet,
    )
    army = ArmyDefinition(
        army_id="army-khorne",
        player_id="player-khorne",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        force_disposition_id="phase17k-force",
        units=(unit,),
    )

    all_records = catalog_ability_records_from_catalog(package.army_catalog)
    player_index = build_player_ability_index(
        all_records,
        army=army,
        catalog=package.army_catalog,
    )
    player_records_by_name = {
        record.definition.name: record for record in player_index.all_records()
    }
    result = default_ability_handler_registry().execute(
        record=player_records_by_name["Instrument of Chaos"],
        context=AbilityExecutionContext(
            game_id="phase17k-game",
            player_id="player-khorne",
            battle_round=1,
            phase=None,
            active_player_id="player-khorne",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_unit_instance_id=unit.unit_instance_id,
            source_keywords=unit.keywords,
            trigger_payload={"roll_type": "charge"},
        ),
    )

    assert "Instrument of Chaos" in player_records_by_name
    assert "Daemonic Icon" not in player_records_by_name
    assert result.status is AbilityResolutionStatus.APPLIED
    assert isinstance(result.replay_payload, dict)
    rule_execution = result.replay_payload["rule_execution"]
    assert isinstance(rule_execution, dict)
    effect_payloads = rule_execution["effect_payloads"]
    assert isinstance(effect_payloads, list)
    effect_payload = effect_payloads[0]
    assert isinstance(effect_payload, dict)
    assert effect_payload["target_unit_instance_ids"] == [unit.unit_instance_id]


def test_phase17k_support_ability_marks_attachment_eligibility_role_as_support() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=support_attachment_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-support-unit", "test-bodyguard-unit"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-support-unit",
                model_name="Support",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:support-height",
                height_document_reference="test-doc:support-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-bodyguard-unit",
                model_name="Bodyguard",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:bodyguard-height",
                height_document_reference="test-doc:bodyguard-height",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    support = package.army_catalog.datasheet_by_id("test-support-unit")

    assert support.attachment_eligibilities[0].role is AttachmentRole.SUPPORT
    assert tuple(
        target.bodyguard_datasheet_id for target in support.attachment_eligibilities[0].targets
    ) == ("test-bodyguard-unit",)
    assert len(support.attachment_eligibilities[0].targets[0].source_ids) == 1
    assert "Datasheets_leader" in support.attachment_eligibilities[0].targets[0].source_ids[0]
    assert support.attachment_eligibilities[0].targets[0].required_wargear_ids == ()


def test_phase17k_bridge_emits_only_explicit_attachment_wargear_requirements() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=support_attachment_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-support-unit", "test-bodyguard-unit"),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-support-unit",
                model_name="Support",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:support-height",
                height_document_reference="test-doc:support-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-bodyguard-unit",
                model_name="Bodyguard",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:bodyguard-height",
                height_document_reference="test-doc:bodyguard-height",
            ),
        ),
        attachment_wargear_requirements=(
            AttachmentWargearRequirement(
                leader_datasheet_id="test-support-unit",
                bodyguard_datasheet_id="test-bodyguard-unit",
                required_wargear_ids=("test-support-unit:support-blade",),
                source_ids=("test-source:explicit-attachment-wargear-restriction",),
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    target = (
        package.army_catalog.datasheet_by_id("test-support-unit")
        .attachment_eligibilities[0]
        .targets[0]
    )

    assert target.required_wargear_ids == ("test-support-unit:support-blade",)
    assert "test-source:explicit-attachment-wargear-restriction" in target.source_ids


def test_phase17k_bridge_omits_attachment_edges_with_an_excluded_bodyguard_endpoint() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=support_attachment_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-support-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-support-unit",
                model_name="Support",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:support-height",
                height_document_reference="test-doc:support-height",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bridge_artifacts,
    )

    assert "Datasheets_leader" not in {artifact.source_table for artifact in bridge_artifacts}
    assert package.army_catalog.datasheet_by_id("test-support-unit").attachment_eligibilities == ()


def test_phase17k_unit_resource_wargear_option_derives_source_capped_starting_balance() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=unit_resource_wargear_source_artifacts(),
        bridge_package_id=bridge_package_id(),
        datasheet_ids=("test-aspect-warriors",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-aspect-warriors",
                model_name="Aspect Exarch",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:aspect-exarch-height",
                height_document_reference="test-doc:aspect-exarch-height",
            ),
            ModelHeightOverride(
                datasheet_id="test-aspect-warriors",
                model_name="Aspect Warriors",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:aspect-warriors-height",
                height_document_reference="test-doc:aspect-warriors-height",
            ),
        ),
    )
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    datasheet = package.army_catalog.datasheet_by_id("test-aspect-warriors")
    option = next(
        option
        for option in datasheet.wargear_options
        if option.selection_limit is not None
        and option.selection_limit.unit_resource_kind is not None
    )
    token_wargear_id = "test-aspect-warriors:aspect-shrine-token"
    selection = WargearSelection(
        option_id=option.option_id,
        model_profile_id=option.model_profile_id,
        wargear_ids=(token_wargear_id,),
        selection_count=2,
    )
    model_selections = (
        ModelProfileSelection(
            model_profile_id="test-aspect-warriors:aspect-exarch",
            model_count=1,
        ),
        ModelProfileSelection(
            model_profile_id="test-aspect-warriors:aspect-warriors",
            model_count=9,
        ),
    )
    unit = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="army-aeldari",
        selection=UnitMusterSelection(
            unit_selection_id="aspect-warriors-1",
            datasheet_id=datasheet.datasheet_id,
            model_profile_selections=model_selections,
            wargear_selections=(selection,),
        ),
        datasheet=datasheet,
    )

    assert option.selection_limit is not None
    assert option.selection_limit.unit_resource_kind == ASPECT_SHRINE_TOKEN_RESOURCE_KIND
    assert option.selection_limit.unit_resource_amount_per_selection == 1
    assert option.selection_limit.models_per_increment == 5
    assert option.selection_limit.max_option_selections_per_increment == 1
    assert option.source_ids == (
        f"{bridge_package_id().stable_identity()}:Datasheets_options:test-aspect-warriors:1",
    )
    assert unit.starting_resources[0].resource_kind == ASPECT_SHRINE_TOKEN_RESOURCE_KIND
    assert unit.starting_resources[0].amount == 2
    assert all(token_wargear_id not in model.wargear_ids for model in unit.own_models)

    with pytest.raises(UnitFactoryError, match="UnitMusterSelection is invalid"):
        UnitFactory(
            catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        ).instantiate_unit(
            army_id="army-aeldari",
            selection=UnitMusterSelection(
                unit_selection_id="aspect-warriors-2",
                datasheet_id=datasheet.datasheet_id,
                model_profile_selections=(
                    model_selections[0],
                    replace(model_selections[1], model_count=4),
                ),
                wargear_selections=(selection,),
            ),
            datasheet=datasheet,
        )


def test_phase17k_structured_wargear_option_semantics_block_icon_and_instrument_together() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")

    resolved = resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id="000001115:instrument-of-chaos:option-1",
                model_profile_id="000001115:bloodcrushers",
                wargear_ids=("000001115:instrument-of-chaos",),
            ),
        ),
    )

    assert any(
        selection.option_id == "000001115:instrument-of-chaos:option-1" for selection in resolved
    )
    with pytest.raises(ListValidationError, match="structured wargear option condition"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
                WargearSelection(
                    option_id="000001115:daemonic-icon:option-2",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:daemonic-icon",),
                ),
            ),
        )

    resolved_for_distinct_bearers = resolve_wargear_selections(
        catalog=package.army_catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id="000001115:instrument-of-chaos:option-1",
                model_profile_id="000001115:bloodcrushers",
                wargear_ids=("000001115:instrument-of-chaos",),
            ),
            WargearSelection(
                option_id="000001115:daemonic-icon:option-2",
                model_profile_id="000001115:bloodcrushers",
                wargear_ids=("000001115:daemonic-icon",),
            ),
        ),
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="000001115:bloodcrushers",
                model_count=5,
            ),
            ModelProfileSelection(
                model_profile_id="000001115:bloodhunter",
                model_count=1,
            ),
        ),
    )

    assert {
        selection.option_id
        for selection in resolved_for_distinct_bearers
        if selection.option_id
        in {
            "000001115:daemonic-icon:option-2",
            "000001115:instrument-of-chaos:option-1",
        }
    } == {
        "000001115:daemonic-icon:option-2",
        "000001115:instrument-of-chaos:option-1",
    }


def test_phase17k_structured_wargear_option_effects_are_count_aware() -> None:
    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    options: list[DatasheetWargearOption] = []
    for option in datasheet.wargear_options:
        if option.option_id != "000001115:instrument-of-chaos:option-1":
            options.append(option)
            continue
        effect = option.effects[0]
        options.append(
            replace(
                option,
                effects=(
                    DatasheetWargearOptionEffect(
                        kind=effect.kind,
                        wargear_id=effect.wargear_id,
                        model_count=effect.model_count,
                        wargear_count=2,
                    ),
                ),
            )
        )
    counted_datasheet = replace(datasheet, wargear_options=tuple(options))

    with pytest.raises(ListValidationError, match="structured wargear option effect count"):
        resolve_wargear_selections(
            catalog=package.army_catalog,
            datasheet=counted_datasheet,
            requested_selections=(
                WargearSelection(
                    option_id="000001115:instrument-of-chaos:option-1",
                    model_profile_id="000001115:bloodcrushers",
                    wargear_ids=("000001115:instrument-of-chaos",),
                ),
            ),
        )


def test_phase17k_bridge_uses_event_companion_model_qualified_base_sizes() -> None:
    artifacts = jakhals_bridge_artifacts()
    model_rows = artifact_by_table(artifacts, "Datasheets_models").rows
    model_fields_by_name = {
        row.runtime_fields_payload()["name"]: row.runtime_fields_payload() for row in model_rows
    }
    dishonoured_row = next(
        row for row in model_rows if row.runtime_fields_payload()["name"] == "Dishonoured"
    )

    assert set(model_fields_by_name) == {"Dishonoured", "Jakhal Pack Leader", "Jakhals"}
    assert model_fields_by_name["Jakhal Pack Leader"]["base_size"] == "28.5mm"
    assert model_fields_by_name["Jakhal Pack Leader"]["min_models"] == "1"
    assert model_fields_by_name["Jakhal Pack Leader"]["max_models"] == "1"
    assert model_fields_by_name["Jakhals"]["base_size"] == "28.5mm"
    assert model_fields_by_name["Jakhals"]["min_models"] == "8"
    assert model_fields_by_name["Jakhals"]["max_models"] == "17"
    assert model_fields_by_name["Dishonoured"]["base_size"] == "40mm"
    assert model_fields_by_name["Dishonoured"]["min_models"] == "1"
    assert model_fields_by_name["Dishonoured"]["max_models"] == "2"
    assert model_fields_by_name["Dishonoured"]["base_size_source_id"].endswith(
        ":base-size:page-93-world-eaters-jakhals-dishonoured"
    )
    assert EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID in source_ids_from_row(dishonoured_row)

    package = build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=artifacts,
    )
    datasheet = package.army_catalog.datasheet_by_id("test-jakhals")
    profiles_by_id = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    dishonoured = profiles_by_id["test-jakhals:dishonoured"]
    dishonoured_geometry = next(
        geometry
        for geometry in package.model_geometries
        if geometry.model_profile_id == "test-jakhals:dishonoured"
    )
    dishonoured_footprint_evidence = next(
        evidence
        for evidence in dishonoured_geometry.evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )

    assert dishonoured.base_size.kind is BaseSizeKind.CIRCULAR
    assert math.isclose(dishonoured.base_size.diameter_mm or 0.0, 40.0)
    assert dishonoured_footprint_evidence.source_id.endswith(
        ":base-size:page-93-world-eaters-jakhals-dishonoured"
    )
    assert package.to_payload() == type(package).from_payload(package.to_payload()).to_payload()
