from __future__ import annotations

import json
import math
from dataclasses import replace
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import cast

import pytest
from tools.generate_ability_support_matrix import ability_support_matrix_rows

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    AttachmentRole,
    BaseSizeKind,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetDefinition,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryMeasurementKind,
    GeometrySourceUnits,
)
from warhammer40k_core.engine.abilities import (
    AbilityCatalogIndex,
    AbilityExecutionContext,
    AbilityResolutionStatus,
    default_ability_handler_registry,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.ability_coverage import (
    AbilityCoverageAbilityDatasheetPair,
    AbilityCoverageCategoryRow,
    AbilityCoverageRow,
    AbilityCoverageSupportStage,
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_from_catalog,
    ability_coverage_rows_payload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battle_shock import collect_battle_shock_test_requests
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    ModelPlacement,
    PlacedArmy,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_charge_roll_modifiers_for_unit,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.death_guard import (
    army_rule as death_guard_army_rule,
)
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.world_eaters import (
    army_rule as world_eaters_army_rule,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR, RuleIRPayload, parameter_payload
from warhammer40k_core.rules.source_reference_generation import build_source_reference_catalog
from warhammer40k_core.rules.wahapedia_bridge import (
    EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE,
    EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID,
    ModelHeightOverride,
    WahapediaBridgeError,
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
_REQUIRED_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)


def test_phase17k_bloodcrushers_bridge_generates_pdf_corrected_canonical_catalog() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    profiles_by_id = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
    composition_by_id = {part.model_profile_id: part for part in datasheet.composition}
    wargear_by_id = {wargear.wargear_id: wargear for wargear in package.army_catalog.wargear}
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    abilities_by_name = {ability.name: ability for ability in datasheet.abilities}

    assert datasheet.name == "Bloodcrushers"
    assert datasheet.keywords.keywords == (
        "Bloodcrushers",
        "Chaos",
        "Daemon",
        "Khorne",
        "Mounted",
    )
    assert "Shadow Legion" not in datasheet.keywords.keywords
    assert datasheet.keywords.faction_keywords == ("Legiones Daemonica",)
    assert composition_by_id["000001115:bloodhunter"].min_models == 1
    assert composition_by_id["000001115:bloodhunter"].max_models == 1
    assert composition_by_id["000001115:bloodcrushers"].min_models == 2
    assert composition_by_id["000001115:bloodcrushers"].max_models == 5

    bloodcrusher = profiles_by_id["000001115:bloodcrushers"]
    assert bloodcrusher.base_size.kind is BaseSizeKind.OVAL
    assert math.isclose(bloodcrusher.base_size.length_mm or 0.0, 90.0)
    assert math.isclose(bloodcrusher.base_size.width_mm or 0.0, 52.0)
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
    assert footprint_evidence.source_id == EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID
    assert (
        footprint_evidence.document_reference == EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    )
    assert (
        Path(__file__).resolve().parents[2] / EVENT_COMPANION_BASE_SIZE_GUIDE_DOCUMENT_REFERENCE
    ).is_file()
    assert EVENT_COMPANION_BASE_SIZE_GUIDE_SOURCE_ID in bloodcrusher.source_ids

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


def test_phase17k_bloodcrushers_runtime_instances_manifest_model_wargear_and_abilities() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
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
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
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


def test_phase17k_instrument_of_chaos_catalog_ir_modifies_charge_roll_result() -> None:
    package = _bloodcrushers_package()
    unit = _bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = _bloodcrushers_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            _model_bearing_wargear(
                unit,
                "000001115:instrument-of-chaos",
            ).model_instance_id,
        )
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}

    modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=battlefield,
            unit=unit,
        ),
    )
    destroyed_bearer_modifiers = catalog_charge_roll_modifiers_for_unit(
        ability_index=player_index,
        unit=unit,
        current_model_instance_ids=_current_model_ids(
            battlefield=destroyed_bearer_battlefield,
            unit=unit,
        ),
    )
    request = ChargeRollRequest(
        request_id="phase17k-charge-roll",
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="phase17k-charge-selection-request",
        source_decision_result_id="phase17k-charge-selection-result",
        roll_modifiers=modifiers,
    )
    roll_state = DiceRollManager("phase17k-game").roll_fixed(request.spec, [3, 4])
    result = ChargeRollResult.from_roll_state(
        request=request,
        roll_state=roll_state,
        reachable_target_distances_inches={},
    )
    destroyed_bearer_request = ChargeRollRequest(
        request_id="phase17k-charge-roll-destroyed-bearer",
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        unit_instance_id=unit.unit_instance_id,
        source_decision_request_id="phase17k-charge-selection-request",
        source_decision_result_id="phase17k-charge-selection-destroyed-bearer-result",
        roll_modifiers=destroyed_bearer_modifiers,
    )
    destroyed_bearer_roll_state = DiceRollManager("phase17k-game").roll_fixed(
        destroyed_bearer_request.spec,
        [3, 4],
    )
    destroyed_bearer_result = ChargeRollResult.from_roll_state(
        request=destroyed_bearer_request,
        roll_state=destroyed_bearer_roll_state,
        reachable_target_distances_inches={},
    )

    assert records_by_name["Instrument of Chaos"].definition.timing.trigger_kind is (
        TimingTriggerKind.AFTER_DICE_ROLL
    )
    assert len(modifiers) == 1
    assert destroyed_bearer_modifiers == ()
    assert modifiers[0].operand == 1
    assert request.spec.expression.modifier == 1
    assert destroyed_bearer_request.spec.expression.modifier == 0
    assert result.value == 8
    assert destroyed_bearer_result.value == 7
    assert result.to_payload()["request"]["roll_modifiers"][0]["operand"] == 1
    with pytest.raises(GameLifecycleError, match="current model evidence must be a tuple"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=cast(tuple[str, ...], ["not-a-tuple"]),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not be empty"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must not duplicate"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=(
                unit.own_models[0].model_instance_id,
                unit.own_models[0].model_instance_id,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence contains unknown"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("army-khorne:bloodcrushers-1:model:missing",),
        )
    with pytest.raises(GameLifecycleError, match="requires an AbilityCatalogIndex"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=cast(AbilityCatalogIndex, object()),
            unit=unit,
            current_model_instance_ids=_current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=cast(UnitInstance, object()),
            current_model_instance_ids=_current_model_ids(
                battlefield=battlefield,
                unit=unit,
            ),
        )
    with pytest.raises(GameLifecycleError, match="current model evidence must contain IDs"):
        catalog_charge_roll_modifiers_for_unit(
            ability_index=player_index,
            unit=unit,
            current_model_instance_ids=("",),
        )
    with pytest.raises(GameLifecycleError, match="classification requires RuleIR"):
        catalog_rule_ir_consumers_for_rule(cast(RuleIR, object()))


def test_phase17k_daemonic_icon_catalog_ir_modifies_battle_shock_leadership() -> None:
    package = _bloodcrushers_package()
    unit = _bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:daemonic-icon",
    )
    army = _bloodcrushers_army(package=package, unit=unit)
    player_index = _player_ability_index(package=package, army=army)
    battlefield = _bloodcrushers_battlefield_state(army=army, unit=unit)
    bearer = _model_bearing_wargear(unit, "000001115:daemonic-icon")
    alive_bearer_battlefield = battlefield.with_removed_models(
        tuple(model.model_instance_id for model in unit.own_models if model != bearer)
    )
    destroyed_bearer_battlefield = battlefield.with_removed_models(
        (
            bearer.model_instance_id,
            next(model.model_instance_id for model in unit.own_models if model != bearer),
        )
    )
    records_by_name = {record.definition.name: record for record in player_index.all_records()}
    starting_strength = (StartingStrengthRecord.from_unit(player_id=army.player_id, unit=unit),)

    requests_without_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
    )
    alive_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=alive_bearer_battlefield,
        starting_strength_records=starting_strength,
        ability_index=player_index,
    )
    destroyed_bearer_requests_with_index = collect_battle_shock_test_requests(
        game_id="phase17k-game",
        battle_round=1,
        player_id=army.player_id,
        army=army,
        battlefield_state=destroyed_bearer_battlefield,
        starting_strength_records=starting_strength,
        ability_index=player_index,
    )

    assert records_by_name["Daemonic Icon"].definition.timing.trigger_kind is (
        TimingTriggerKind.PASSIVE_QUERY
    )
    assert records_by_name["Daemonic Icon"].definition.name == "Daemonic Icon"
    assert len(requests_without_index) == 1
    assert len(alive_bearer_requests_with_index) == 1
    assert len(destroyed_bearer_requests_with_index) == 1
    assert requests_without_index[0].leadership_target == 7
    assert alive_bearer_requests_with_index[0].leadership_target == 6
    assert destroyed_bearer_requests_with_index[0].leadership_target == 7


def test_phase17k_daemon_wargear_ability_coverage_snapshot_is_current() -> None:
    rows = ability_support_matrix_rows()
    snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "ability_coverage_rows.json"
        ).read_text(encoding="utf-8")
    )
    category_rows = ability_coverage_category_rows(rows)
    category_snapshot = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / "data"
            / "generated"
            / "ability_coverage"
            / "ability_support_category_rows.json"
        ).read_text(encoding="utf-8")
    )
    rows_by_name: dict[str, list[AbilityCoverageRow]] = {}
    for row in rows:
        rows_by_name.setdefault(row.ability_name, []).append(row)
    categories_by_name = {row.category_name: row for row in category_rows}

    assert ability_coverage_rows_payload(rows) == snapshot
    assert ability_coverage_category_rows_payload(category_rows) == category_snapshot
    assert tuple(row.datasheet_name for row in rows_by_name["Instrument of Chaos"]) == (
        "Bloodletters",
        "Bloodcrushers",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Daemonic Icon"]) == (
        "Bloodletters",
        "Bloodcrushers",
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Deep Strike"]) == (
        "Bloodletters",
        "Bloodcrushers",
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Instrument of Chaos"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Daemonic Icon"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Deep Strike"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["The Shadow of Chaos"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Nurgle's Gift"]
    )
    assert all(
        row.support_stage is AbilityCoverageSupportStage.ENGINE_CONSUMED
        for row in rows_by_name["Blessings of Khorne"]
    )
    assert all(
        row.runtime_consumer_ids
        == ("warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos",)
        for row in rows_by_name["The Shadow of Chaos"]
    )
    assert tuple(row.datasheet_name for row in rows_by_name["Nurgle's Gift"]) == ("Death Guard",)
    assert tuple(row.datasheet_name for row in rows_by_name["Blessings of Khorne"]) == (
        "World Eaters",
    )
    assert set(rows_by_name["Nurgle's Gift"][0].runtime_consumer_ids) == {
        death_guard_army_rule.HOOK_ID,
        f"{death_guard_army_rule.HOOK_ID}:armour-save-option",
        f"{death_guard_army_rule.HOOK_ID}:leadership",
        f"{death_guard_army_rule.HOOK_ID}:melee-hit-roll",
        f"{death_guard_army_rule.HOOK_ID}:movement-budget",
        f"{death_guard_army_rule.HOOK_ID}:objective-control",
        f"{death_guard_army_rule.HOOK_ID}:toughness",
    }
    assert set(rows_by_name["Blessings of Khorne"][0].runtime_consumer_ids) == {
        world_eaters_army_rule.HOOK_ID,
        world_eaters_army_rule.RAGE_FUELLED_INVIGORATION_HOOK_ID,
        world_eaters_army_rule.TOTAL_CARNAGE_HOOK_ID,
        world_eaters_army_rule.UNBRIDLED_BLOODLUST_CHARGE_MODIFIER_ID,
        f"{world_eaters_army_rule.HOOK_ID}:weapon-profile-keywords",
    }
    assert categories_by_name["Leadership Characteristic"].ability_names == ("Daemonic Icon",)
    assert categories_by_name["Leadership Characteristic"].datasheet_names == (
        "Bloodcrushers",
        "Bloodletters",
    )
    assert categories_by_name["Leadership Characteristic"].coverage_row_count == 2
    assert categories_by_name["Leadership Characteristic"].source_kind_counts == (("wargear", 2),)
    assert tuple(
        (pair.ability_name, pair.datasheet_name)
        for pair in categories_by_name["Leadership Characteristic"].ability_datasheet_pairs
    ) == (
        ("Daemonic Icon", "Bloodcrushers"),
        ("Daemonic Icon", "Bloodletters"),
    )
    assert categories_by_name["Leadership Characteristic"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Charge Roll Modifier"].ability_names == ("Instrument of Chaos",)
    assert categories_by_name["Charge Roll Modifier"].datasheet_names == (
        "Bloodcrushers",
        "Bloodletters",
    )
    assert categories_by_name["Charge Roll Modifier"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Deep Strike Reserve Arrival"].ability_names == ("Deep Strike",)
    assert categories_by_name["Deep Strike Reserve Arrival"].runtime_consumer_ids == (
        "descriptor:movement:deep-strike-placement",
        "descriptor:reserve-declaration:deep-strike",
    )
    assert categories_by_name["Deep Strike Reserve Arrival"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Chaos Daemons Army Rule"].ability_names == ("The Shadow of Chaos",)
    assert categories_by_name["Chaos Daemons Army Rule"].runtime_consumer_ids == (
        "warhammer_40000_11th:chaos_daemons:army_rule:shadow_of_chaos",
    )
    assert categories_by_name["Chaos Daemons Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Death Guard Army Rule"].ability_names == ("Nurgle's Gift",)
    assert categories_by_name["Death Guard Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["World Eaters Army Rule"].ability_names == ("Blessings of Khorne",)
    assert categories_by_name["World Eaters Army Rule"].support_stages == (
        AbilityCoverageSupportStage.ENGINE_CONSUMED,
    )
    assert categories_by_name["Unknown Abilities"].ability_names == (
        "Bane of Cowards",
        "Brass Stampede",
    )
    assert categories_by_name["Unknown Abilities"].runtime_consumer_ids == ()
    assert categories_by_name["Unknown Abilities"].support_stages == (
        AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    )


def test_phase17k_ability_coverage_api_fails_fast_and_classifies_unsupported_ir() -> None:
    package = _bloodcrushers_package()
    unsupported_package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_unsupported_wargear_rule_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("test-unsupported-unit",),
            height_overrides=(
                ModelHeightOverride(
                    datasheet_id="test-unsupported-unit",
                    model_name="Alpha",
                    height=1.0,
                    height_units=GeometrySourceUnits.INCHES,
                    height_source_id="test-source:unsupported-height",
                    height_document_reference="test-doc:unsupported-height",
                ),
            ),
        ),
    )
    unsupported_rows = ability_coverage_rows_from_catalog(
        unsupported_package.army_catalog,
        datasheet_ids=("test-unsupported-unit",),
    )
    rows_by_name = {row.ability_name: row for row in unsupported_rows}
    scatter = rows_by_name["Scatter Icon"]
    broken_instrument = rows_by_name["Broken Instrument"]
    hit_charm = rows_by_name["Hit Charm"]
    tithe_charm = rows_by_name["Tithe Charm"]

    assert (
        ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=("not-a-datasheet",),
        )
        == ()
    )
    assert scatter.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    assert scatter.diagnostic_reasons == ("unsupported_language",)
    assert scatter.semantic_categories == ("wargear.unsupported.unsupported_language",)
    assert broken_instrument.support_stage is AbilityCoverageSupportStage.IR_COMPILED_UNSUPPORTED
    assert broken_instrument.runtime_consumer_ids == ("catalog-ir:charge-roll-modifier",)
    assert broken_instrument.semantic_categories == (
        "wargear.roll_modifier.charge.this_unit",
        "wargear.unsupported.unsupported_language",
    )
    assert hit_charm.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    assert hit_charm.semantic_categories == ("wargear.roll_modifier.hit.this_unit",)
    assert tithe_charm.support_stage is AbilityCoverageSupportStage.GENERIC_IR_EXECUTABLE
    assert tithe_charm.semantic_categories == ("wargear.rule_ir.modify_command_points.unscoped",)
    with pytest.raises(GameLifecycleError, match="requires an ArmyCatalog"):
        ability_coverage_rows_from_catalog(cast(ArmyCatalog, object()))
    with pytest.raises(GameLifecycleError, match="datasheet_ids must be a tuple"):
        ability_coverage_rows_from_catalog(
            package.army_catalog,
            datasheet_ids=cast(tuple[str, ...], ["000001115"]),
        )
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        ability_coverage_rows_payload(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="rows must be a tuple"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require coverage rows"):
        ability_coverage_category_rows(cast(tuple[AbilityCoverageRow, ...], (object(),)))
    with pytest.raises(GameLifecycleError, match="category rows must be a tuple"):
        ability_coverage_category_rows_payload(cast(tuple[AbilityCoverageCategoryRow, ...], []))
    with pytest.raises(GameLifecycleError, match="require category rows"):
        ability_coverage_category_rows_payload(
            cast(tuple[AbilityCoverageCategoryRow, ...], (object(),))
        )
    with pytest.raises(GameLifecycleError, match="catalog_id"):
        _ability_coverage_row(catalog_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_id"):
        _ability_coverage_row(datasheet_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_name"):
        _ability_coverage_row(datasheet_name="")
    with pytest.raises(GameLifecycleError, match="ability_id"):
        _ability_coverage_row(ability_id="")
    with pytest.raises(GameLifecycleError, match="ability_name"):
        _ability_coverage_row(ability_name="")
    with pytest.raises(GameLifecycleError, match="source_kind"):
        _ability_coverage_row(source_kind=cast(CatalogAbilitySourceKind, "bad"))
    with pytest.raises(GameLifecycleError, match="source_wargear_id"):
        _ability_coverage_row(source_wargear_id="")
    with pytest.raises(GameLifecycleError, match="catalog_support"):
        _ability_coverage_row(catalog_support=cast(CatalogAbilitySupport, "bad"))
    with pytest.raises(GameLifecycleError, match="support_stage"):
        _ability_coverage_row(support_stage=cast(AbilityCoverageSupportStage, "bad"))
    with pytest.raises(GameLifecycleError, match="semantic_categories"):
        _ability_coverage_row(semantic_categories=("",))
    with pytest.raises(GameLifecycleError, match="runtime_consumer_ids"):
        _ability_coverage_row(runtime_consumer_ids=cast(tuple[str, ...], []))
    with pytest.raises(GameLifecycleError, match="diagnostic_reasons"):
        _ability_coverage_row(diagnostic_reasons=("",))
    with pytest.raises(GameLifecycleError, match="coverage_row_id"):
        _ability_datasheet_pair(coverage_row_id="")
    with pytest.raises(GameLifecycleError, match="ability_id"):
        _ability_datasheet_pair(ability_id="")
    with pytest.raises(GameLifecycleError, match="ability_name"):
        _ability_datasheet_pair(ability_name="")
    with pytest.raises(GameLifecycleError, match="datasheet_id"):
        _ability_datasheet_pair(datasheet_id="")
    with pytest.raises(GameLifecycleError, match="datasheet_name"):
        _ability_datasheet_pair(datasheet_name="")
    with pytest.raises(GameLifecycleError, match="source_kind"):
        _ability_datasheet_pair(source_kind=cast(CatalogAbilitySourceKind, "bad"))
    with pytest.raises(GameLifecycleError, match="category_id"):
        _ability_coverage_category_row(category_id="")
    with pytest.raises(GameLifecycleError, match="category_name"):
        _ability_coverage_category_row(category_name="")
    with pytest.raises(GameLifecycleError, match="coverage_row_count"):
        _ability_coverage_category_row(coverage_row_count=0)
    with pytest.raises(GameLifecycleError, match="coverage_row_ids"):
        _ability_coverage_category_row(coverage_row_ids=())
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must be a tuple"):
        _ability_coverage_category_row(
            ability_datasheet_pairs=cast(tuple[AbilityCoverageAbilityDatasheetPair, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must match"):
        _ability_coverage_category_row(ability_datasheet_pairs=())
    with pytest.raises(GameLifecycleError, match="ability_datasheet_pairs must contain"):
        _ability_coverage_category_row(
            ability_datasheet_pairs=cast(
                tuple[AbilityCoverageAbilityDatasheetPair, ...],
                (object(),),
            )
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts must be a tuple"):
        _ability_coverage_category_row(source_kind_counts=cast(tuple[tuple[str, int], ...], []))
    with pytest.raises(GameLifecycleError, match="source_kind_counts entries must be pairs"):
        _ability_coverage_category_row(source_kind_counts=cast(tuple[tuple[str, int], ...], ((),)))
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be strings"):
        _ability_coverage_category_row(
            source_kind_counts=cast(tuple[tuple[str, int], ...], ((1, 1),))
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts keys must be unique"):
        _ability_coverage_category_row(
            coverage_row_count=2,
            coverage_row_ids=("test-row-1", "test-row-2"),
            ability_datasheet_pairs=(
                _ability_datasheet_pair(coverage_row_id="test-row-1"),
                _ability_datasheet_pair(coverage_row_id="test-row-2"),
            ),
            source_kind_counts=(("wargear", 1), ("wargear", 1)),
        )
    with pytest.raises(GameLifecycleError, match="source_kind_counts values"):
        _ability_coverage_category_row(source_kind_counts=(("wargear", 0),))
    with pytest.raises(GameLifecycleError, match="source_kind_counts must match"):
        _ability_coverage_category_row(source_kind_counts=(("wargear", 2),))
    with pytest.raises(GameLifecycleError, match="support_stages"):
        _ability_coverage_category_row(
            support_stages=cast(tuple[AbilityCoverageSupportStage, ...], [])
        )
    with pytest.raises(GameLifecycleError, match="support_stages"):
        _ability_coverage_category_row(
            support_stages=cast(tuple[AbilityCoverageSupportStage, ...], ("bad",))
        )


def test_phase17k_bridge_datasheet_source_ids_include_pdf_correction_source_id() -> None:
    artifacts = _bloodcrushers_bridge_artifacts()
    datasheet_row = _row_by_id(_artifact_by_table(artifacts, "Datasheets"), "000001115")
    shadow_legion_row = next(
        row
        for artifact in _wahapedia_source_artifacts()
        if artifact.source_table == "Datasheets_keywords"
        for row in artifact.rows
        if row.runtime_fields_payload()["datasheet_id"] == "000001115"
        and row.runtime_fields_payload()["keyword"] == "Shadow Legion"
    )

    source_ids = _source_ids_from_row(datasheet_row)

    assert shadow_legion_row.stable_source_id() in source_ids
    assert "pdf:chaos-daemons-faction-pack:2026-06-10:p30-p31" in source_ids


def test_phase17k_bridge_deduplicates_same_faction_rows_for_multiple_datasheets() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_same_faction_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
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
    faction_rows = _artifact_by_table(artifacts, "Factions").rows

    assert tuple(row.source_row_id for row in faction_rows) == ("test-faction",)


def test_phase17k_bridge_normalizes_core_keyword_ability_timing_and_parameters() -> None:
    artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_keyword_ability_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
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
    ability_rows = _artifact_by_table(artifacts, "Datasheets_abilities").rows
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


def test_phase17k_support_ability_marks_attachment_eligibility_role_as_support() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_support_attachment_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
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
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    support = package.army_catalog.datasheet_by_id("test-support-unit")

    assert support.attachment_eligibilities[0].role is AttachmentRole.SUPPORT
    assert support.attachment_eligibilities[0].allowed_bodyguard_datasheet_ids == (
        "test-bodyguard-unit",
    )


def test_phase17k_bridge_preserves_raw_source_text_for_reference_catalog() -> None:
    source_reference_catalog = build_source_reference_catalog(
        package_id=_bridge_package_id(),
        catalog_version=_catalog_version(),
        target_edition="warhammer-40000-11th",
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )
    deep_strike_text = source_reference_catalog.source_text_by_id(
        f"{_bridge_package_id().stable_identity()}:Datasheets_abilities:000001115:1:description"
    )
    option_text = source_reference_catalog.source_text_by_id(
        f"{_bridge_package_id().stable_identity()}:Datasheets_options:000001115:1:description"
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


def test_phase17k_bridge_preserves_unsupported_rule_ir_diagnostics() -> None:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_unsupported_wargear_rule_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("test-unsupported-unit",),
        height_overrides=(
            ModelHeightOverride(
                datasheet_id="test-unsupported-unit",
                model_name="Alpha",
                height=1.0,
                height_units=GeometrySourceUnits.INCHES,
                height_source_id="test-source:unsupported-height",
                height_document_reference="test-doc:unsupported-height",
            ),
        ),
    )
    ability_row = next(
        row
        for row in _artifact_by_table(bridge_artifacts, "Datasheets_abilities").rows
        if row.runtime_fields_payload()["name"] == "Scatter Icon"
    )
    fields = ability_row.runtime_fields_payload()
    diagnostics = json.loads(fields["rule_ir_diagnostics"])
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=bridge_artifacts,
    )
    abilities_by_name = {
        ability.name: ability
        for ability in package.army_catalog.datasheet_by_id("test-unsupported-unit").abilities
    }
    ability = abilities_by_name["Scatter Icon"]

    assert fields["support"] == "unsupported"
    assert fields["rule_ir_payload"]
    assert diagnostics[0]["reason"] == "unsupported_language"
    assert diagnostics[0]["source_span"]["text"] == (
        "Roll a scatter die and consult the legacy table."
    )
    assert ability.support is CatalogAbilitySupport.UNSUPPORTED
    assert ability.rule_ir_payload is not None
    assert ability.rule_ir_diagnostics == tuple(diagnostics)


def test_phase17k_structured_wargear_option_semantics_block_icon_and_instrument_together() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
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


def test_phase17k_structured_wargear_option_effects_are_count_aware() -> None:
    package = build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
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


def test_phase17k_bridge_requires_accepted_height_overrides() -> None:
    with pytest.raises(WahapediaBridgeError, match="height override"):
        build_wahapedia_canonical_bridge_artifacts(
            source_artifacts=_wahapedia_source_artifacts(),
            bridge_package_id=_bridge_package_id(),
            datasheet_ids=("000001115",),
            height_overrides=(),
        )


def _bloodcrushers_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_bloodcrushers_bridge_artifacts(),
    )


def _bloodcrushers_unit(
    *,
    package: CanonicalCatalogPackage,
    selected_wargear_id: str,
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id("000001115")
    option = _wargear_option_for_wargear(datasheet, selected_wargear_id)
    return UnitFactory(
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
                    option_id=option.option_id,
                    model_profile_id=option.model_profile_id,
                    wargear_ids=(selected_wargear_id,),
                ),
            ),
        ),
        datasheet=datasheet,
    )


def _wargear_option_for_wargear(
    datasheet: DatasheetDefinition,
    wargear_id: str,
) -> DatasheetWargearOption:
    for option in datasheet.wargear_options:
        if option.allowed_wargear_ids == (wargear_id,):
            return option
    raise AssertionError(f"Missing option for wargear: {wargear_id}.")


def _bloodcrushers_army(
    *,
    package: CanonicalCatalogPackage,
    unit: UnitInstance,
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id="army-khorne",
        player_id="player-khorne",
        catalog_id=package.army_catalog.catalog_id,
        source_package_id=package.army_catalog.source_package_id,
        ruleset_id=package.army_catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=package.army_catalog.factions[0].faction_id,
            detachment_ids=("phase17k-daemons",),
        ),
        units=(unit,),
    )


def _player_ability_index(
    *,
    package: CanonicalCatalogPackage,
    army: ArmyDefinition,
) -> AbilityCatalogIndex:
    return build_player_ability_index(
        catalog_ability_records_from_catalog(package.army_catalog),
        army=army,
        catalog=package.army_catalog,
    )


def _bloodcrushers_battlefield_state(
    *,
    army: ArmyDefinition,
    unit: UnitInstance,
) -> BattlefieldRuntimeState:
    placements = tuple(
        ModelPlacement(
            army_id=army.army_id,
            player_id=army.player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=Pose.at(12.0 + (index * 2.0), 12.0),
        )
        for index, model in enumerate(unit.own_models)
    )
    return BattlefieldRuntimeState(
        battlefield_id="phase17k-battlefield",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        placed_armies=(
            PlacedArmy(
                army_id=army.army_id,
                player_id=army.player_id,
                unit_placements=(
                    UnitPlacement(
                        army_id=army.army_id,
                        player_id=army.player_id,
                        unit_instance_id=unit.unit_instance_id,
                        model_placements=placements,
                    ),
                ),
            ),
        ),
    )


def _current_model_ids(
    *,
    battlefield: BattlefieldRuntimeState,
    unit: UnitInstance,
) -> tuple[str, ...]:
    return tuple(
        placement.model_instance_id
        for placement in battlefield.unit_placement_by_id(unit.unit_instance_id).model_placements
    )


def _model_bearing_wargear(
    unit: UnitInstance,
    wargear_id: str,
) -> ModelInstance:
    for model in unit.own_models:
        if wargear_id in model.wargear_ids:
            return model
    raise AssertionError(f"Missing bearer for wargear: {wargear_id}.")


def _ability_coverage_row(
    *,
    catalog_id: str = "test-catalog",
    datasheet_id: str = "test-datasheet",
    datasheet_name: str = "Test Datasheet",
    ability_id: str = "test-ability",
    ability_name: str = "Test Ability",
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.WARGEAR,
    source_wargear_id: str | None = "test-wargear",
    catalog_support: CatalogAbilitySupport = CatalogAbilitySupport.DESCRIPTOR_ONLY,
    support_stage: AbilityCoverageSupportStage = AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    semantic_categories: tuple[str, ...] = ("wargear.descriptor",),
    runtime_consumer_ids: tuple[str, ...] = (),
    diagnostic_reasons: tuple[str, ...] = (),
) -> AbilityCoverageRow:
    return AbilityCoverageRow(
        catalog_id=catalog_id,
        datasheet_id=datasheet_id,
        datasheet_name=datasheet_name,
        ability_id=ability_id,
        ability_name=ability_name,
        source_kind=source_kind,
        source_wargear_id=source_wargear_id,
        catalog_support=catalog_support,
        support_stage=support_stage,
        semantic_categories=semantic_categories,
        runtime_consumer_ids=runtime_consumer_ids,
        diagnostic_reasons=diagnostic_reasons,
    )


def _ability_datasheet_pair(
    *,
    coverage_row_id: str = "test-row",
    ability_id: str = "test-ability",
    ability_name: str = "Test Ability",
    datasheet_id: str = "test-datasheet",
    datasheet_name: str = "Test Datasheet",
    source_kind: CatalogAbilitySourceKind = CatalogAbilitySourceKind.WARGEAR,
) -> AbilityCoverageAbilityDatasheetPair:
    return AbilityCoverageAbilityDatasheetPair(
        coverage_row_id=coverage_row_id,
        ability_id=ability_id,
        ability_name=ability_name,
        datasheet_id=datasheet_id,
        datasheet_name=datasheet_name,
        source_kind=source_kind,
    )


def _ability_coverage_category_row(
    *,
    category_id: str = "wargear.roll_modifier.charge.this_unit",
    category_name: str = "Charge Roll Modifier",
    coverage_row_count: int = 1,
    coverage_row_ids: tuple[str, ...] = ("test-row",),
    ability_datasheet_pairs: tuple[AbilityCoverageAbilityDatasheetPair, ...] | None = None,
    source_kind_counts: tuple[tuple[str, int], ...] = (("wargear", 1),),
    support_stages: tuple[AbilityCoverageSupportStage, ...] = (
        AbilityCoverageSupportStage.DESCRIPTOR_ONLY,
    ),
    runtime_consumer_ids: tuple[str, ...] = (),
    ability_names: tuple[str, ...] = ("Test Ability",),
    datasheet_names: tuple[str, ...] = ("Test Datasheet",),
) -> AbilityCoverageCategoryRow:
    if ability_datasheet_pairs is None:
        ability_datasheet_pairs = (_ability_datasheet_pair(),)
    return AbilityCoverageCategoryRow(
        category_id=category_id,
        category_name=category_name,
        coverage_row_count=coverage_row_count,
        coverage_row_ids=coverage_row_ids,
        ability_datasheet_pairs=ability_datasheet_pairs,
        source_kind_counts=source_kind_counts,
        support_stages=support_stages,
        runtime_consumer_ids=runtime_consumer_ids,
        ability_names=ability_names,
        datasheet_names=datasheet_names,
    )


def _bloodcrushers_bridge_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_wahapedia_source_artifacts(),
        bridge_package_id=_bridge_package_id(),
        datasheet_ids=("000001115",),
    )


def _same_faction_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-datasheet-a,Alpha Unit,test-faction",
                    "test-datasheet-b,Beta Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-datasheet-a,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-datasheet-b,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-datasheet-a,Alpha,,false",
                    "test-datasheet-a,Test Faction,,true",
                    "test-datasheet-b,Beta,,false",
                    "test-datasheet-b,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-datasheet-a,1,6,4,3,-,2,7,1,32mm",
                    "test-datasheet-b,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-datasheet-a,1,1 Alpha",
                    "test-datasheet-b,1,1 Beta",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _keyword_ability_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                    "core-deep-strike,,Deep Strike,Deep Strike text.",
                    "core-infiltrators,,Infiltrators,Infiltrators text.",
                    "core-leader,,Leader,Leader text.",
                    "core-support,,Support,Support text.",
                    'core-scouts,,"Scouts 6""",Scouts text.',
                    "core-firing-deck,,Firing Deck 2,Firing Deck text.",
                    "core-deadly-demise,,Deadly Demise D3,Deadly Demise text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(("id,name,faction_id", "test-keyword-unit,Keyword Unit,test-faction")),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-keyword-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-keyword-unit,2,Core,core-deep-strike,,,",
                    "test-keyword-unit,3,Core,core-infiltrators,,,",
                    "test-keyword-unit,4,Core,core-leader,,,",
                    "test-keyword-unit,5,Core,core-support,,,",
                    "test-keyword-unit,6,Core,core-scouts,,,",
                    "test-keyword-unit,7,Core,core-firing-deck,,,",
                    "test-keyword-unit,8,Core,core-deadly-demise,,,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-keyword-unit,Infantry,,false",
                    "test-keyword-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-keyword-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-keyword-unit,1,1 Alpha")),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _support_attachment_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                    "core-support,,Support,Support text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-support-unit,Support Unit,test-faction",
                    "test-bodyguard-unit,Bodyguard Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    "test-support-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                    "test-support-unit,2,Core,core-support,,,",
                    "test-bodyguard-unit,1,Faction,test-army-rule,Test Army Rule,Test rule text.,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-support-unit,Character,,false",
                    "test-support-unit,Infantry,,false",
                    "test-support-unit,Test Faction,,true",
                    "test-bodyguard-unit,Infantry,,false",
                    "test-bodyguard-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_leader",
            "\n".join(
                (
                    "leader_id,attached_id",
                    "test-support-unit,test-bodyguard-unit",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_wargear",
            "\n".join(
                (
                    "datasheet_id,line,line_in_wargear,name,type,range,A,BS_WS,S,AP,D,description",
                    "test-support-unit,1,1,Support blade,Melee,Melee,1,3,4,0,1,",
                    "test-bodyguard-unit,1,1,Bodyguard blade,Melee,Melee,1,3,4,0,1,",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-support-unit,1,6,4,3,-,2,7,1,32mm",
                    "test-bodyguard-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(
                (
                    "datasheet_id,line,description",
                    "test-support-unit,1,1 Support",
                    "test-bodyguard-unit,1,1 Bodyguard",
                )
            ),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _unsupported_wargear_rule_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    return (
        _artifact_from_csv(
            "Abilities",
            "\n".join(
                (
                    "id,faction_id,name,description",
                    "test-army-rule,test-faction,Test Army Rule,Test rule text.",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets",
            "\n".join(
                (
                    "id,name,faction_id",
                    "test-unsupported-unit,Unsupported Unit,test-faction",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_abilities",
            "\n".join(
                (
                    "datasheet_id,line,type,ability_id,name,description,parameter",
                    (
                        "test-unsupported-unit,1,Faction,test-army-rule,"
                        "Test Army Rule,Test rule text.,"
                    ),
                    (
                        "test-unsupported-unit,2,Wargear,,Scatter Icon,"
                        "Roll a scatter die and consult the legacy table.,"
                    ),
                    (
                        "test-unsupported-unit,3,Wargear,,Hit Charm,"
                        "Add 1 to hit rolls for the bearer's unit.,"
                    ),
                    "test-unsupported-unit,4,Wargear,,Tithe Charm,Gain 1CP.,",
                    (
                        "test-unsupported-unit,5,Wargear,,Broken Instrument,"
                        "Add 1 to Charge rolls made for the bearer's unit. "
                        "Roll a scatter die and consult the legacy table.,"
                    ),
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_keywords",
            "\n".join(
                (
                    "datasheet_id,keyword,model,is_faction_keyword",
                    "test-unsupported-unit,Infantry,,false",
                    "test-unsupported-unit,Test Faction,,true",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_models",
            "\n".join(
                (
                    "datasheet_id,line,M,T,Sv,inv_sv,W,Ld,OC,base_size",
                    "test-unsupported-unit,1,6,4,3,-,2,7,1,32mm",
                )
            ),
        ),
        _artifact_from_csv(
            "Datasheets_unit_composition",
            "\n".join(("datasheet_id,line,description", "test-unsupported-unit,1,1 Alpha")),
        ),
        _artifact_from_csv(
            "Factions",
            "\n".join(("id,name", "test-faction,Test Faction")),
        ),
    )


def _artifact_from_csv(table_name: str, csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_bridge_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=f"{csv_text}\n"),
    )


@lru_cache(maxsize=1)
def _wahapedia_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in _REQUIRED_TABLES:
        payload = json.loads(
            (_WAHAPEDIA_10E_JSON / f"{table_name}.json").read_text(encoding="utf-8")
        )
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


def _artifact_by_table(
    artifacts: tuple[WahapediaJsonArtifact, ...],
    table_name: str,
) -> WahapediaJsonArtifact:
    for artifact in artifacts:
        if artifact.source_table == table_name:
            return artifact
    raise AssertionError(f"Missing artifact table: {table_name}.")


def _row_by_id(artifact: WahapediaJsonArtifact, row_id: str) -> NormalizedSourceRow:
    for row in artifact.rows:
        if row.source_row_id == row_id:
            return row
    raise AssertionError(f"Missing source row: {row_id}.")


def _source_ids_from_row(row: NormalizedSourceRow) -> tuple[str, ...]:
    return tuple(
        source_id.strip()
        for source_id in row.runtime_fields_payload()["source_ids"].split(",")
        if source_id.strip()
    )


def _bridge_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="wahapedia-" + "1" + "0" + "e-bridge",
        version="phase17k-test",
    )


def _catalog_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="chaos-daemons-bridge-catalog",
        version="phase17k-test",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="warhammer-40000-11th-phase17k",
        source_date=date(2026, 6, 10),
    )
