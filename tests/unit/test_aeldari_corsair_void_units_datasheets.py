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
from tools.generate_aeldari_corsair_void_units_rule_ir import (
    OUTPUT_PATH,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetCatalogError,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.datasheet_composition import validate_unit_composition_counts
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollResult,
    DiceRollSpec,
    DiceRollState,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attack_sequence import (
    _source_backed_hit_permission_for_attack,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_rule_consumption import (
    CatalogWeaponKeywordGrantRuntime,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_tracked_target_runtime import CatalogTrackedTargetRuntime
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
    resolve_model_profile_selections,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, SetupStep
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionContext,
    FailedSaveDamageReplacementContext,
    SaveOptionModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.tracked_targets import (
    TrackedTargetOwnerScope,
    TrackedTargetRole,
    apply_select_tracked_target_decision,
)
from warhammer40k_core.engine.unit_factory import UnitFactory
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_generation_composition import (
    allows_zero_models_from_row,
    composition_min_models_from_row,
)
from warhammer40k_core.rules.catalog_generation_errors import CatalogGenerationError
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import (
    RuleConditionKind,
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_corsair_void_units_2026_06 as void_units_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_CORSAIR_VOID_UNITS_HEIGHT_OVERRIDES,
)
from warhammer40k_core.rules.wahapedia_schema import NormalizedSourceRow

VOIDREAVERS_ID = "000002531"
VOIDSCARRED_ID = "000002532"
VOIDREAVER_PROFILE_ID = f"{VOIDREAVERS_ID}:corsair-voidreavers"
VOIDREAVER_FELARCH_PROFILE_ID = f"{VOIDREAVERS_ID}:voidreaver-felarch"
VOIDSCARRED_PROFILE_ID = f"{VOIDSCARRED_ID}:corsair-voidscarred"
VOIDSCARRED_FELARCH_PROFILE_ID = f"{VOIDSCARRED_ID}:voidscarred-felarch"


def _composition_source_row(fields: dict[str, str]) -> NormalizedSourceRow:
    return NormalizedSourceRow(
        source_package_id=DataPackageId(
            namespace="test",
            package_name="corsair-void-unit-composition",
            version="1",
        ),
        source_table="Datasheets_models",
        source_row_id="composition-row",
        source_row_number=2,
        fields=tuple(fields.items()),
        text_fields=(),
    )


@pytest.mark.parametrize(
    ("min_models", "max_models", "allows_zero_models", "message"),
    [
        (0, 1, object(), "allows_zero_models must be a bool"),
        ("0", 1, True, "min_models must be an integer"),
        (-1, 1, True, "must not be negative"),
        (0, 1, False, "must be at least 1"),
        (1, 1, True, "requires min_models 0"),
        (1, "1", False, "max_models must be an integer"),
        (1, 0, False, "max_models must be at least 1"),
        (2, 1, False, "max_models must be at least min_models"),
    ],
)
def test_optional_composition_count_validation_is_explicit_and_fail_fast(
    min_models: object,
    max_models: object,
    allows_zero_models: object,
    message: str,
) -> None:
    with pytest.raises(DatasheetCatalogError, match=message):
        validate_unit_composition_counts(
            min_models=min_models,
            max_models=max_models,
            allows_zero_models=allows_zero_models,
            error_type=DatasheetCatalogError,
        )

    assert validate_unit_composition_counts(
        min_models=0,
        max_models=1,
        allows_zero_models=True,
        error_type=DatasheetCatalogError,
    ) == (0, 1, True)


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"min_models": "1", "allows_zero_models": "sometimes"}, "true or false"),
        ({}, "requires field: min_models"),
        ({"min_models": "many"}, "must be an integer"),
        ({"min_models": "-1"}, "must not be negative"),
        ({"min_models": "0"}, "must be at least 1"),
    ],
)
def test_source_composition_fields_reject_implicit_or_malformed_optionality(
    fields: dict[str, str],
    message: str,
) -> None:
    row = _composition_source_row(fields)
    validator = (
        allows_zero_models_from_row
        if "allows_zero_models" in fields
        else composition_min_models_from_row
    )
    with pytest.raises(CatalogGenerationError, match=message):
        validator(row)

    optional_row = _composition_source_row({"min_models": "0", "allows_zero_models": "true"})
    assert allows_zero_models_from_row(optional_row)
    assert composition_min_models_from_row(optional_row) == 0


def test_void_units_generated_rule_ir_artifact_is_current_and_fail_fast() -> None:
    committed_payload = cast(
        dict[str, Any],
        json.loads(OUTPUT_PATH.read_text(encoding="utf-8")),
    )

    assert committed_payload == generated_artifact_payload()
    assert void_units_package.DATASHEETS == {
        VOIDREAVERS_ID: "Corsair Voidreavers",
        VOIDSCARRED_ID: "Corsair Voidscarred",
    }
    assert void_units_package.supported_datasheet_source_row_ids() == (
        "000002531:3",
        "000002531:4",
        "000002532:3",
        "000002532:4",
        "000002532:6",
    )
    assert committed_payload["package_hash"] == void_units_package.PACKAGE_HASH

    drifted = cast(dict[str, Any], json.loads(json.dumps(committed_payload)))
    drifted["package_hash"] = "0" * 64
    with pytest.raises(
        void_units_package.CorsairVoidUnitsRuleIrArtifactError,
        match="package hash is stale",
    ):
        void_units_package.validate_generated_artifact_bytes(json.dumps(drifted).encode())

    with pytest.raises(
        void_units_package.CorsairVoidUnitsRuleIrArtifactError,
        match="artifact is invalid",
    ):
        void_units_package.validate_generated_artifact_bytes(b"{")

    drifted = cast(dict[str, Any], json.loads(json.dumps(committed_payload)))
    records = cast(dict[str, Any], drifted["records"])
    cast(dict[str, Any], records["000002531:3"])["rule_ir"] = replace(
        _rule_ir("000002531:3"),
        source_id="drifted:source",
    ).to_payload()
    _rehash_artifact(drifted)
    with pytest.raises(
        void_units_package.CorsairVoidUnitsRuleIrArtifactError,
        match="source identity drifted",
    ):
        void_units_package.validate_generated_artifact_bytes(json.dumps(drifted).encode())


def test_void_units_rule_ir_encodes_every_exact_ability_with_generic_semantics() -> None:
    rules = {
        source_row_id: _rule_ir(source_row_id)
        for source_row_id in void_units_package.supported_datasheet_source_row_ids()
    }

    reavers = rules["000002531:3"]
    assert catalog_rule_ir_consumers_for_rule(reavers) == (
        "catalog-ir:hit-roll-reroll",
        "catalog-ir:passive-hit-reroll",
    )
    assert reavers.clauses[0].target is not None
    assert reavers.clauses[0].target.kind is RuleTargetKind.THIS_UNIT
    assert reavers.clauses[0].effects[0].kind is RuleEffectKind.REROLL_PERMISSION
    assert parameter_payload(reavers.clauses[0].effects[0].parameters) == {
        "full_reroll_if_target_within_objective_range": True,
        "reroll_unmodified_value": 1,
        "roll_type": "hit",
    }

    for source_row_id in ("000002531:4", "000002532:6"):
        mistshield = rules[source_row_id]
        clause = mistshield.clauses[0]
        assert catalog_rule_ir_consumers_for_rule(mistshield) == (
            "catalog-ir:invulnerable-save-characteristic-query",
        )
        assert clause.target is not None
        assert clause.target.kind is RuleTargetKind.THIS_MODEL
        assert parameter_payload(clause.effects[0].parameters) == {
            "characteristic": "invulnerable_save",
            "value": 4,
        }

    piratical = rules["000002532:3"]
    assert catalog_rule_ir_consumers_for_rule(piratical) == (
        "catalog-ir:tracked-target-selection",
        "catalog-ir:weapon-keyword-grant",
        "catalog-ir:weapon-keyword-grant:lethal-hits",
        "catalog-ir:weapon-keyword-grant:precision",
    )
    assert len(piratical.clauses) == 3
    selection = piratical.clauses[0]
    assert selection.trigger is not None
    assert selection.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert selection.target is not None
    assert selection.target.kind is RuleTargetKind.ENEMY_UNIT
    assert selection.effects[0].kind is RuleEffectKind.SELECT_TRACKED_TARGET
    assert tuple(
        parameter_payload(clause.effects[0].parameters)["weapon_ability"]
        for clause in piratical.clauses[1:]
    ) == ("Lethal Hits", "Precision")
    assert all(
        clause.conditions[0].kind is RuleConditionKind.TARGET_CONSTRAINT
        for clause in piratical.clauses[1:]
    )

    channeller = rules["000002532:4"]
    clause = channeller.clauses[0]
    assert catalog_rule_ir_consumers_for_rule(channeller) == (
        "catalog-ir:first-failed-save-damage-replacement",
    )
    assert clause.trigger is not None
    assert clause.trigger.kind is RuleTriggerKind.DICE_ROLL
    assert clause.conditions[0].kind is RuleConditionKind.FREQUENCY_LIMIT
    assert parameter_payload(clause.effects[0].parameters) == {
        "attack_role": "defender",
        "characteristic": "damage",
        "value": 0,
    }


def test_void_units_catalog_preserves_stats_composition_keywords_and_abilities() -> None:
    catalog = _ability_support_catalog_package().army_catalog
    expected_profiles = {
        VOIDREAVERS_ID: {
            VOIDREAVER_PROFILE_ID: "Corsair Voidreavers",
            VOIDREAVER_FELARCH_PROFILE_ID: "Voidreaver Felarch",
        },
        VOIDSCARRED_ID: {
            VOIDSCARRED_PROFILE_ID: "Corsair Voidscarred",
            f"{VOIDSCARRED_ID}:shade-runner": "Shade Runner",
            f"{VOIDSCARRED_ID}:soul-weaver": "Soul Weaver",
            VOIDSCARRED_FELARCH_PROFILE_ID: "Voidscarred Felarch",
            f"{VOIDSCARRED_ID}:way-seeker": "Way Seeker",
        },
    }
    expected_oc = {VOIDREAVERS_ID: 2, VOIDSCARRED_ID: 1}

    for datasheet_id, profiles_by_id in expected_profiles.items():
        datasheet = catalog.datasheet_by_id(datasheet_id)
        profiles = {profile.model_profile_id: profile for profile in datasheet.model_profiles}
        assert {profile_id: profile.name for profile_id, profile in profiles.items()} == (
            profiles_by_id
        )
        for profile in profiles.values():
            assert profile.characteristic(Characteristic.MOVEMENT).final == 7
            assert profile.characteristic(Characteristic.TOUGHNESS).final == 3
            assert profile.characteristic(Characteristic.SAVE).final == 4
            assert profile.characteristic(Characteristic.WOUNDS).final == 1
            assert profile.characteristic(Characteristic.LEADERSHIP).final == 7
            assert (
                profile.characteristic(Characteristic.OBJECTIVE_CONTROL).final
                == (expected_oc[datasheet_id])
            )
            assert profile.base_size.diameter_mm == 28.5
        assert datasheet.keywords.faction_keywords == ("ASURYANI",)
        assert not datasheet.mustering_options
        assert not datasheet.damaged_effects

    voidreavers = catalog.datasheet_by_id(VOIDREAVERS_ID)
    assert voidreavers.name == "Corsair Voidreavers"
    assert voidreavers.keywords.keywords == (
        "AELDARI",
        "ANHRATHE",
        "BATTLELINE",
        "CORSAIR VOIDREAVERS",
        "GRENADES",
        "INFANTRY",
    )
    assert tuple(
        (part.model_profile_id, part.min_models, part.max_models)
        for part in voidreavers.composition
    ) == (
        (VOIDREAVER_PROFILE_ID, 4, 9),
        (VOIDREAVER_FELARCH_PROFILE_ID, 1, 1),
    )
    assert _ability_signatures(voidreavers.abilities) == {
        ("Battle Focus", CatalogAbilitySourceKind.FACTION, CatalogAbilitySupport.DESCRIPTOR_ONLY),
        ("Mistshield", CatalogAbilitySourceKind.WARGEAR, CatalogAbilitySupport.GENERIC_RULE_IR),
        (
            "Reavers of the Void",
            CatalogAbilitySourceKind.DATASHEET,
            CatalogAbilitySupport.GENERIC_RULE_IR,
        ),
        ("Scouts", CatalogAbilitySourceKind.CORE, CatalogAbilitySupport.DESCRIPTOR_ONLY),
    }
    assert next(
        ability for ability in voidreavers.abilities if ability.name == "Scouts"
    ).parameter_tokens == ("7",)

    voidscarred = catalog.datasheet_by_id(VOIDSCARRED_ID)
    assert voidscarred.name == "Corsair Voidscarred"
    assert voidscarred.max_unit_models == 10
    assert voidscarred.keywords.keywords == (
        "AELDARI",
        "ANHRATHE",
        "CORSAIR VOIDSCARRED",
        "GRENADES",
        "INFANTRY",
        "PSYKER",
    )
    assert tuple(
        (part.model_profile_id, part.min_models, part.max_models)
        for part in voidscarred.composition
    ) == (
        (VOIDSCARRED_PROFILE_ID, 4, 9),
        (f"{VOIDSCARRED_ID}:shade-runner", 0, 1),
        (f"{VOIDSCARRED_ID}:soul-weaver", 0, 1),
        (VOIDSCARRED_FELARCH_PROFILE_ID, 1, 1),
        (f"{VOIDSCARRED_ID}:way-seeker", 0, 1),
    )
    assert _ability_signatures(voidscarred.abilities) == {
        ("Battle Focus", CatalogAbilitySourceKind.FACTION, CatalogAbilitySupport.DESCRIPTOR_ONLY),
        (
            "Channeller Stones",
            CatalogAbilitySourceKind.WARGEAR,
            CatalogAbilitySupport.GENERIC_RULE_IR,
        ),
        ("Faolchú", CatalogAbilitySourceKind.WARGEAR, CatalogAbilitySupport.GENERIC_RULE_IR),
        ("Mistshield", CatalogAbilitySourceKind.WARGEAR, CatalogAbilitySupport.GENERIC_RULE_IR),
        (
            "Piratical Raiders",
            CatalogAbilitySourceKind.DATASHEET,
            CatalogAbilitySupport.GENERIC_RULE_IR,
        ),
        ("Scouts", CatalogAbilitySourceKind.CORE, CatalogAbilitySupport.DESCRIPTOR_ONLY),
    }


def test_void_units_catalog_preserves_every_weapon_profile() -> None:
    catalog = _ability_support_catalog_package().army_catalog
    assert _weapon_signatures(catalog, VOIDREAVERS_ID) == {
        "blaster": (18, "1", 3, 8, -4, "D6+1", ("Assault",), ()),
        "close-combat-weapon": ("melee", "2", 3, 3, 0, "1", (), ()),
        "neuro-disruptor": (
            12,
            "1",
            3,
            4,
            -2,
            "1",
            ("Assault", "Pistol"),
            ("Anti-Infantry 2+",),
        ),
        "power-sword": ("melee", "2", 3, 4, -2, "1", (), ()),
        "shredder": (18, "D6", 0, 6, 0, "1", ("Assault", "Torrent"), ()),
        "shuriken-cannon": (24, "3", 3, 6, -1, "2", ("Lethal Hits",), ("Lethal Hits",)),
        "shuriken-pistol": (12, "1", 3, 4, -1, "1", ("Assault", "Pistol"), ()),
        "shuriken-rifle": (
            24,
            "1",
            3,
            4,
            -1,
            "1",
            ("Assault", "Rapid Fire"),
            ("Rapid Fire 1",),
        ),
        "wraithcannon": (18, "1", 3, 14, -4, "D6+1", (), ()),
    }
    assert _non_weapon_wargear_ids(catalog, VOIDREAVERS_ID) == {"mistshield"}

    assert _weapon_signatures(catalog, VOIDSCARRED_ID) == {
        "blaster": (18, "1", 3, 8, -4, "D6+1", ("Assault",), ()),
        "close-combat-weapon": ("melee", "3", 3, 3, 0, "1", (), ()),
        "executioner": (18, "3", 3, 6, -2, "D3", ("Psychic",), ("Anti-Infantry 2+",)),
        "fusion-pistol": (
            6,
            "1",
            3,
            8,
            -4,
            "D6",
            ("Assault", "Melta", "Pistol"),
            ("Melta 2",),
        ),
        "long-rifle": (36, "1", 3, 4, -1, "2", ("Heavy", "Precision"), ("Heavy",)),
        "neuro-disruptor": (
            12,
            "1",
            3,
            4,
            -2,
            "1",
            ("Assault", "Pistol"),
            ("Anti-Infantry 2+",),
        ),
        "paired-hekatarii-blades": (
            "melee",
            "4",
            2,
            3,
            -2,
            "1",
            ("Twin-linked",),
            (),
        ),
        "power-sword": ("melee", "3", 3, 4, -2, "1", (), ()),
        "shredder": (18, "D6", 0, 6, 0, "1", ("Assault", "Torrent"), ()),
        "shuriken-cannon": (24, "3", 3, 6, -1, "2", ("Lethal Hits",), ("Lethal Hits",)),
        "shuriken-pistol": (12, "1", 3, 4, -1, "1", ("Assault", "Pistol"), ()),
        "shuriken-rifle": (
            24,
            "1",
            3,
            4,
            -1,
            "1",
            ("Assault", "Rapid Fire"),
            ("Rapid Fire 1",),
        ),
        "witch-staff": (
            "melee",
            "2",
            2,
            3,
            0,
            "D3",
            ("Psychic",),
            ("Anti-Infantry 2+",),
        ),
        "wraithcannon": (18, "1", 3, 14, -4, "D6+1", (), ()),
    }
    assert _non_weapon_wargear_ids(catalog, VOIDSCARRED_ID) == {
        "channeller-stones",
        "faolchu",
        "mistshield",
    }


def test_void_units_loadouts_points_leaders_and_geometry_are_source_bound() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    voidreavers = catalog.datasheet_by_id(VOIDREAVERS_ID)
    voidscarred = catalog.datasheet_by_id(VOIDSCARRED_ID)

    reaver_structured = {
        option.option_id: option for option in voidreavers.wargear_options if option.effects
    }
    assert len(reaver_structured) == 9
    assert reaver_structured[f"{VOIDREAVERS_ID}:shuriken-rifle:option-3"].effects[-1].kind is (
        WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED
    )
    assert reaver_structured[f"{VOIDREAVERS_ID}:mistshield:option-2"].model_profile_id == (
        VOIDREAVER_FELARCH_PROFILE_ID
    )

    scarred_structured = {
        option.option_id: option for option in voidscarred.wargear_options if option.effects
    }
    assert len(scarred_structured) == 10
    faolchu = scarred_structured[f"{VOIDSCARRED_ID}:faolchu:option-8"]
    assert faolchu.conditions[0].kind is WargearOptionConditionKind.MODEL_EQUIPPED_WITH
    assert faolchu.conditions[0].wargear_ids == (
        f"{VOIDSCARRED_ID}:power-sword",
        f"{VOIDSCARRED_ID}:shuriken-pistol",
    )
    assert scarred_structured[f"{VOIDSCARRED_ID}:mistshield:option-3"].model_profile_id == (
        VOIDSCARRED_FELARCH_PROFILE_ID
    )

    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    selection = _voidscarred_selection(
        regular_count=4,
        optional_count=1,
        wargear_selections=(
            WargearSelection(
                option_id=f"{VOIDSCARRED_ID}:shuriken-rifle:option-1",
                model_profile_id=VOIDSCARRED_PROFILE_ID,
                wargear_ids=(f"{VOIDSCARRED_ID}:shuriken-rifle",),
            ),
            WargearSelection(
                option_id=f"{VOIDSCARRED_ID}:shuriken-rifle-to-blaster:option-4",
                model_profile_id=VOIDSCARRED_PROFILE_ID,
                wargear_ids=(f"{VOIDSCARRED_ID}:blaster",),
            ),
            WargearSelection(
                option_id=f"{VOIDSCARRED_ID}:faolchu:option-8",
                model_profile_id=VOIDSCARRED_PROFILE_ID,
                wargear_ids=(f"{VOIDSCARRED_ID}:faolchu",),
            ),
            WargearSelection(
                option_id=f"{VOIDSCARRED_ID}:mistshield:option-3",
                model_profile_id=VOIDSCARRED_FELARCH_PROFILE_ID,
                wargear_ids=(f"{VOIDSCARRED_ID}:mistshield",),
            ),
        ),
    )
    unit = factory.instantiate_unit(
        army_id="army-voidscarred-loadout",
        datasheet=voidscarred,
        selection=selection,
    )
    regular_models = tuple(
        model for model in unit.own_models if model.model_profile_id == VOIDSCARRED_PROFILE_ID
    )
    assert sum(f"{VOIDSCARRED_ID}:blaster" in model.wargear_ids for model in regular_models) == 1
    assert sum(f"{VOIDSCARRED_ID}:faolchu" in model.wargear_ids for model in regular_models) == 1
    blaster_bearer = next(
        model for model in regular_models if f"{VOIDSCARRED_ID}:blaster" in model.wargear_ids
    )
    assert blaster_bearer.wargear_ids == (
        f"{VOIDSCARRED_ID}:close-combat-weapon",
        f"{VOIDSCARRED_ID}:faolchu",
        f"{VOIDSCARRED_ID}:blaster",
    )
    felarch = next(
        model
        for model in unit.own_models
        if model.model_profile_id == VOIDSCARRED_FELARCH_PROFILE_ID
    )
    assert f"{VOIDSCARRED_ID}:mistshield" in felarch.wargear_ids
    soul_weaver = next(
        model
        for model in unit.own_models
        if model.model_profile_id == f"{VOIDSCARRED_ID}:soul-weaver"
    )
    assert f"{VOIDSCARRED_ID}:channeller-stones" in soul_weaver.wargear_ids

    oversized_selection = _voidscarred_selection(regular_count=8, optional_count=1)
    with pytest.raises(ListValidationError, match="unit-size maximum"):
        resolve_model_profile_selections(
            datasheet=voidscarred,
            selections=oversized_selection.model_profile_selections,
        )

    points_payload = cast(
        dict[str, Any],
        json.loads((DEFAULT_SOURCE_JSON_DIR / "Datasheets_models_cost.json").read_text()),
    )
    points = {
        datasheet_id: tuple(
            (row["fields"]["description"], row["fields"]["cost"])
            for row in cast(list[dict[str, Any]], points_payload["rows"])
            if row["fields"]["datasheet_id"] == datasheet_id
        )
        for datasheet_id in (VOIDREAVERS_ID, VOIDSCARRED_ID)
    }
    assert points == {
        VOIDREAVERS_ID: (("5 models", "65"), ("10 models", "110")),
        VOIDSCARRED_ID: (("5 models", "80"), ("10 models", "160")),
    }

    leader_payload = cast(
        dict[str, Any],
        json.loads((DEFAULT_SOURCE_JSON_DIR / "Datasheets_leader.json").read_text()),
    )
    source_links = {
        (row["fields"]["leader_id"], row["fields"]["attached_id"])
        for row in cast(list[dict[str, Any]], leader_payload["rows"])
        if row["fields"]["attached_id"] in {VOIDREAVERS_ID, VOIDSCARRED_ID}
    }
    assert source_links == {
        (leader_id, datasheet_id)
        for leader_id in ("000000569", "000002542", "000002543", "000004193", "000004194")
        for datasheet_id in (VOIDREAVERS_ID, VOIDSCARRED_ID)
    }
    kharseth = catalog.datasheet_by_id("000004194")
    assert {
        target.bodyguard_datasheet_id
        for eligibility in kharseth.attachment_eligibilities
        for target in eligibility.targets
    } == {VOIDREAVERS_ID, VOIDSCARRED_ID}

    assert len(AELDARI_CORSAIR_VOID_UNITS_HEIGHT_OVERRIDES) == 7
    assert {override.height for override in AELDARI_CORSAIR_VOID_UNITS_HEIGHT_OVERRIDES} == {2.0}
    assert {override.datasheet_id for override in AELDARI_CORSAIR_VOID_UNITS_HEIGHT_OVERRIDES} == {
        VOIDREAVERS_ID,
        VOIDSCARRED_ID,
    }


def test_void_units_generic_runtime_bindings_use_real_catalog_units() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    voidscarred = factory.instantiate_unit(
        army_id="army-a",
        datasheet=catalog.datasheet_by_id(VOIDSCARRED_ID),
        selection=_voidscarred_selection(
            regular_count=4,
            optional_count=1,
            wargear_selections=(
                WargearSelection(
                    option_id=f"{VOIDSCARRED_ID}:mistshield:option-3",
                    model_profile_id=VOIDSCARRED_FELARCH_PROFILE_ID,
                    wargear_ids=(f"{VOIDSCARRED_ID}:mistshield",),
                ),
            ),
        ),
    )
    voidreavers = factory.instantiate_unit(
        army_id="army-b",
        datasheet=catalog.datasheet_by_id(VOIDREAVERS_ID),
        selection=UnitMusterSelection(
            unit_selection_id="voidreavers",
            datasheet_id=VOIDREAVERS_ID,
            model_profile_selections=(
                ModelProfileSelection(VOIDREAVER_PROFILE_ID, 4),
                ModelProfileSelection(VOIDREAVER_FELARCH_PROFILE_ID, 1),
            ),
        ),
    )
    armies = (
        _army(catalog=catalog, army_id="army-a", player_id="player-a", unit=voidscarred),
        _army(catalog=catalog, army_id="army-b", player_id="player-b", unit=voidreavers),
    )
    all_records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(all_records, army=army, catalog=catalog)
        for army in armies
    }
    runtime = CatalogDatasheetRuleRuntime(indexes, armies)
    state = _battle_state(armies)
    felarch = next(
        model
        for model in voidscarred.own_models
        if model.model_profile_id == VOIDSCARRED_FELARCH_PROFILE_ID
    )
    regular = next(
        model
        for model in voidscarred.own_models
        if model.model_profile_id == VOIDSCARRED_PROFILE_ID
    )
    attacker = voidreavers.own_models[0]
    armour_save = (SaveOption(SaveKind.ARMOUR, 4, 4, 0),)

    save_binding = next(
        binding
        for binding in runtime.save_option_modifier_bindings()
        if VOIDSCARRED_ID in binding.source_id
    )
    felarch_saves = save_binding.handler(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=voidscarred.unit_instance_id,
            save_options=armour_save,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=voidreavers.unit_instance_id,
            attacker_model_instance_id=attacker.model_instance_id,
            allocated_model_instance_id=felarch.model_instance_id,
        )
    )
    regular_saves = save_binding.handler(
        SaveOptionModifierContext(
            state=state,
            target_unit_instance_id=voidscarred.unit_instance_id,
            save_options=armour_save,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=voidreavers.unit_instance_id,
            attacker_model_instance_id=attacker.model_instance_id,
            allocated_model_instance_id=regular.model_instance_id,
        )
    )
    assert tuple((save.save_kind, save.target_number) for save in felarch_saves) == (
        (SaveKind.ARMOUR, 4),
        (SaveKind.INVULNERABLE, 4),
    )
    assert regular_saves == armour_save

    replacement = runtime.failed_save_damage_replacement_bindings()[0].handler(
        FailedSaveDamageReplacementContext(
            state=state,
            attacking_unit_instance_id=voidreavers.unit_instance_id,
            attacker_model_instance_id=attacker.model_instance_id,
            target_unit_instance_id=voidscarred.unit_instance_id,
            allocated_model_instance_id=regular.model_instance_id,
            source_phase=BattlePhase.SHOOTING,
        )
    )
    assert replacement is not None
    assert replacement.replacement_damage == 0
    assert replacement.source_unit_instance_id == voidscarred.unit_instance_id

    reroll = runtime.attack_reroll_permission_bindings()[0].handler(
        AttackRerollPermissionContext(
            state=state,
            player_id="player-b",
            attacking_unit_instance_id=voidreavers.unit_instance_id,
            attacker_model_instance_id=attacker.model_instance_id,
            target_unit_instance_id=voidscarred.unit_instance_id,
            source_phase=BattlePhase.SHOOTING,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        )
    )
    assert reroll is not None
    assert reroll.source_payload["conditional_hit_reroll"] == {
        "reroll_unmodified_values": [1],
        "full_reroll_if_target_within_objective_range": True,
    }


def test_piratical_raiders_uses_setup_decision_and_target_gated_weapon_grants() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    voidscarred_selection = _voidscarred_selection(regular_count=4, optional_count=0)
    voidreavers_selection = UnitMusterSelection(
        unit_selection_id="voidreavers",
        datasheet_id=VOIDREAVERS_ID,
        model_profile_selections=(
            ModelProfileSelection(VOIDREAVER_PROFILE_ID, 4),
            ModelProfileSelection(VOIDREAVER_FELARCH_PROFILE_ID, 1),
        ),
    )
    voidscarred = factory.instantiate_unit(
        army_id="army-a",
        datasheet=catalog.datasheet_by_id(VOIDSCARRED_ID),
        selection=voidscarred_selection,
    )
    voidreavers = factory.instantiate_unit(
        army_id="army-b",
        datasheet=catalog.datasheet_by_id(VOIDREAVERS_ID),
        selection=voidreavers_selection,
    )
    armies = (
        _army(catalog=catalog, army_id="army-a", player_id="player-a", unit=voidscarred),
        _army(catalog=catalog, army_id="army-b", player_id="player-b", unit=voidreavers),
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    setup_sequence = tuple(descriptor.setup_sequence.steps)
    setup_state = GameState(
        game_id="corsair-void-units-setup",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.SETUP,
        setup_sequence=setup_sequence,
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        setup_state.record_army_definition(army)
    config = GameConfig(
        game_id=setup_state.game_id,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(army=armies[0], selection=voidscarred_selection),
            _muster_request(army=armies[1], selection=voidreavers_selection),
        ),
        player_ids=setup_state.player_ids,
        turn_order=setup_state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        allow_legacy_non_strict_rosters=True,
    )
    decisions = DecisionController()
    piratical_source_rule_id = next(
        record.definition.source_id
        for record in indexes["player-a"].all_records()
        if record.definition.name == "Piratical Raiders"
    )
    request = CatalogTrackedTargetRuntime(indexes, armies).battle_formation_request(
        BattleFormationRequestContext(state=setup_state, decisions=decisions, config=config)
    )

    assert request is not None
    assert request.actor_id == "player-a"
    assert request.payload == {
        "submission_kind": "select_tracked_target",
        "source_rule_id": piratical_source_rule_id,
        "source_ability_id": "000002532:piratical-raiders",
        "source_clause_id": ("phase17k:aeldari:corsair-void-units:000002532:3:clause:001"),
        "source_effect_index": 0,
        "owner_scope": "this_unit",
        "tracked_target_role": "prey",
        "supported_attack_roll_pairs": [
            {"attack_kind": "melee", "roll_type": "attack_sequence.hit"},
            {"attack_kind": "ranged", "roll_type": "attack_sequence.hit"},
        ],
        "supported_attack_kinds": ["melee", "ranged"],
        "supported_roll_types": ["attack_sequence.hit"],
        "target_allegiance": "enemy",
        "target_scope": "enemy_unit",
        "replacement": False,
        "legal_target_unit_ids": [voidreavers.unit_instance_id],
        "source_unit_instance_id": voidscarred.unit_instance_id,
        "source_model_instance_id": None,
    }
    result = DecisionResult.for_request(
        result_id="piratical-raiders-result",
        request=request,
        selected_option_id=voidreavers.unit_instance_id,
    )
    tracked_target = apply_select_tracked_target_decision(
        state=setup_state,
        request=request,
        result=result,
        decisions_event_log=decisions.event_log,
    )
    assert tracked_target.selected_battle_round == 1
    assert tracked_target.target_unit_instance_id == voidreavers.unit_instance_id

    battle_state = _battle_state(armies)
    battle_state.record_tracked_target(tracked_target)
    profile = next(
        wargear.weapon_profiles[0]
        for wargear in catalog.wargear
        if wargear.wargear_id == f"{VOIDSCARRED_ID}:shuriken-pistol"
    )
    attacker = next(
        model
        for model in voidscarred.own_models
        if model.model_profile_id == VOIDSCARRED_PROFILE_ID
    )
    runtime = CatalogWeaponKeywordGrantRuntime(indexes, armies)
    context = WeaponProfileModifierContext(
        state=battle_state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=voidscarred.unit_instance_id,
        attacker_model_instance_id=attacker.model_instance_id,
        target_unit_instance_id=voidreavers.unit_instance_id,
        weapon_profile=profile,
    )
    modified = runtime.weapon_profile_modifier(context)
    unchanged = runtime.weapon_profile_modifier(
        replace(context, target_unit_instance_id=voidscarred.unit_instance_id)
    )

    assert WeaponKeyword.LETHAL_HITS in modified.keywords
    assert WeaponKeyword.PRECISION in modified.keywords
    assert unchanged == profile


def test_piratical_raiders_uses_canonical_attached_rules_unit_identities() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    source_selection = _voidscarred_selection(regular_count=4, optional_count=0)
    source = factory.instantiate_unit(
        army_id="army-a",
        datasheet=catalog.datasheet_by_id(VOIDSCARRED_ID),
        selection=source_selection,
    )
    target_selection = _voidreavers_selection(unit_selection_id="target-bodyguard")
    target = factory.instantiate_unit(
        army_id="army-b",
        datasheet=catalog.datasheet_by_id(VOIDREAVERS_ID),
        selection=target_selection,
    )
    unrelated = factory.instantiate_unit(
        army_id="army-b",
        datasheet=catalog.datasheet_by_id(VOIDREAVERS_ID),
        selection=_voidreavers_selection(unit_selection_id="unrelated"),
    )
    kharseth = catalog.datasheet_by_id("000004194")
    kharseth_profile_id = kharseth.model_profiles[0].model_profile_id

    def leader(*, army_id: str, selection_id: str) -> Any:
        return factory.instantiate_unit(
            army_id=army_id,
            datasheet=kharseth,
            selection=UnitMusterSelection(
                unit_selection_id=selection_id,
                datasheet_id=kharseth.datasheet_id,
                model_profile_selections=(ModelProfileSelection(kharseth_profile_id, 1),),
            ),
        )

    source_leader = leader(army_id="army-a", selection_id="source-leader")
    target_leader = leader(army_id="army-b", selection_id="target-leader")
    source_attached_id = "attached-unit:army-a:voidscarred-source"
    target_attached_id = "attached-unit:army-b:voidreavers-target"
    source_formation = _attached_formation(
        attached_unit_instance_id=source_attached_id,
        bodyguard_unit_instance_id=source.unit_instance_id,
        leader_unit_instance_id=source_leader.unit_instance_id,
    )
    target_formation = _attached_formation(
        attached_unit_instance_id=target_attached_id,
        bodyguard_unit_instance_id=target.unit_instance_id,
        leader_unit_instance_id=target_leader.unit_instance_id,
    )
    armies = (
        _army_with_units(
            catalog=catalog,
            army_id="army-a",
            player_id="player-a",
            units=(source, source_leader),
            attached_units=(source_formation,),
        ),
        _army_with_units(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            units=(target, target_leader, unrelated),
            attached_units=(target_formation,),
        ),
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    setup_sequence = tuple(descriptor.setup_sequence.steps)
    setup_state = GameState(
        game_id="corsair-attached-tracked-target",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.SETUP,
        setup_sequence=setup_sequence,
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        setup_step_index=setup_sequence.index(SetupStep.DECLARE_BATTLE_FORMATIONS),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        setup_state.record_army_definition(army)
    config = GameConfig(
        game_id=setup_state.game_id,
        ruleset_descriptor=descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(army=armies[0], selection=source_selection),
            _muster_request(army=armies[1], selection=target_selection),
        ),
        player_ids=setup_state.player_ids,
        turn_order=setup_state.turn_order,
        fixed_secondary_mission_ids=("assassination", "bring-it-down"),
        allow_legacy_non_strict_rosters=True,
    )
    decisions = DecisionController()
    request = CatalogTrackedTargetRuntime(indexes, armies).battle_formation_request(
        BattleFormationRequestContext(state=setup_state, decisions=decisions, config=config)
    )

    assert request is not None
    assert cast(dict[str, Any], request.payload)["source_unit_instance_id"] == source_attached_id
    assert cast(dict[str, Any], request.payload)["legal_target_unit_ids"] == [
        unrelated.unit_instance_id,
        target_attached_id,
    ]
    assert tuple(option.option_id for option in request.options) == (
        unrelated.unit_instance_id,
        target_attached_id,
    )
    tracked_target = apply_select_tracked_target_decision(
        state=setup_state,
        request=request,
        result=DecisionResult.for_request(
            result_id="attached-piratical-raiders-result",
            request=request,
            selected_option_id=target_attached_id,
        ),
        decisions_event_log=decisions.event_log,
    )
    assert tracked_target.source_unit_instance_id == source_attached_id
    assert tracked_target.target_unit_instance_id == target_attached_id
    assert (
        setup_state.active_tracked_target_for(
            source_rule_id=tracked_target.source_rule_id,
            source_unit_instance_id=source.unit_instance_id,
            source_model_instance_id=None,
            owner_scope=TrackedTargetOwnerScope.THIS_UNIT,
            role=TrackedTargetRole.PREY,
        )
        == tracked_target
    )
    assert setup_state.tracked_targets_for_destroyed_unit(
        destroyed_unit_instance_id=target_leader.unit_instance_id
    ) == (tracked_target,)

    battle_state = _battle_state(armies)
    battle_state.record_tracked_target(tracked_target)
    profile = next(
        wargear.weapon_profiles[0]
        for wargear in catalog.wargear
        if wargear.wargear_id == f"{VOIDSCARRED_ID}:shuriken-pistol"
    )
    attacker = next(
        model for model in source.own_models if model.model_profile_id == VOIDSCARRED_PROFILE_ID
    )
    runtime = CatalogWeaponKeywordGrantRuntime(indexes, armies)
    context = WeaponProfileModifierContext(
        state=battle_state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=source_attached_id,
        attacker_model_instance_id=attacker.model_instance_id,
        target_unit_instance_id=target_attached_id,
        weapon_profile=profile,
    )
    modified = runtime.weapon_profile_modifier(context)

    assert WeaponKeyword.LETHAL_HITS in modified.keywords
    assert WeaponKeyword.PRECISION in modified.keywords
    assert (
        runtime.weapon_profile_modifier(
            replace(context, target_unit_instance_id=unrelated.unit_instance_id)
        )
        == profile
    )


def test_reavers_of_the_void_full_reroll_checks_all_attached_target_models() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    source = factory.instantiate_unit(
        army_id="army-a",
        datasheet=catalog.datasheet_by_id(VOIDREAVERS_ID),
        selection=_voidreavers_selection(unit_selection_id="source-reavers"),
    )
    target = factory.instantiate_unit(
        army_id="army-b",
        datasheet=catalog.datasheet_by_id(VOIDSCARRED_ID),
        selection=replace(
            _voidscarred_selection(regular_count=4, optional_count=0),
            unit_selection_id="target-voidscarred",
        ),
    )
    kharseth = catalog.datasheet_by_id("000004194")
    target_leader = factory.instantiate_unit(
        army_id="army-b",
        datasheet=kharseth,
        selection=UnitMusterSelection(
            unit_selection_id="target-leader",
            datasheet_id=kharseth.datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(kharseth.model_profiles[0].model_profile_id, 1),
            ),
        ),
    )
    target_attached_id = "attached-unit:army-b:objective-target"
    armies = (
        _army(catalog=catalog, army_id="army-a", player_id="player-a", unit=source),
        _army_with_units(
            catalog=catalog,
            army_id="army-b",
            player_id="player-b",
            units=(target, target_leader),
            attached_units=(
                _attached_formation(
                    attached_unit_instance_id=target_attached_id,
                    bodyguard_unit_instance_id=target.unit_instance_id,
                    leader_unit_instance_id=target_leader.unit_instance_id,
                ),
            ),
        ),
    )
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    state = _battle_state(armies)
    state.mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    marker = state.mission_setup.objective_markers[0]
    assert state.battlefield_state is not None
    leader_placement = state.battlefield_state.unit_placement_by_id(target_leader.unit_instance_id)
    moved_model = leader_placement.model_placements[0].with_pose(
        Pose.at(marker.x_inches, marker.y_inches, marker.z_inches)
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        leader_placement.with_model_placements(
            (moved_model, *leader_placement.model_placements[1:])
        )
    )
    permission_context = (
        CatalogDatasheetRuleRuntime(indexes, armies)
        .attack_reroll_permission_bindings()[0]
        .handler(
            AttackRerollPermissionContext(
                state=state,
                player_id="player-a",
                attacking_unit_instance_id=source.unit_instance_id,
                attacker_model_instance_id=source.own_models[0].model_instance_id,
                target_unit_instance_id=target_attached_id,
                source_phase=BattlePhase.SHOOTING,
                roll_type="attack_sequence.hit",
                timing_window="attack_sequence.hit",
            )
        )
    )
    assert permission_context is not None
    roll_state = DiceRollState.from_result(
        DiceRollResult.from_values(
            roll_id="attached-objective-hit-roll",
            spec=DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="attached objective hit",
                roll_type="attack_sequence.hit",
                actor_id="player-a",
            ),
            values=(2,),
            source="fixed",
        )
    )

    assert (
        _source_backed_hit_permission_for_attack(
            permission_context=permission_context,
            roll_state=roll_state,
            state=state,
            target_unit_instance_id=target_attached_id,
        )
        == permission_context.permission
    )


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = void_units_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _rehash_artifact(payload: dict[str, Any]) -> None:
    encoded = json.dumps(
        {**payload, "package_hash": ""},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    payload["package_hash"] = hashlib.sha256(encoded).hexdigest()


def _ability_signatures(
    abilities: tuple[Any, ...],
) -> set[tuple[str, CatalogAbilitySourceKind, CatalogAbilitySupport]]:
    return {(ability.name, ability.source_kind, ability.support) for ability in abilities}


def _weapon_signatures(catalog: Any, datasheet_id: str) -> dict[str, tuple[Any, ...]]:
    signatures: dict[str, tuple[Any, ...]] = {}
    for wargear in catalog.wargear:
        prefix = f"{datasheet_id}:"
        if not wargear.wargear_id.startswith(prefix) or not wargear.weapon_profiles:
            continue
        profile = wargear.weapon_profiles[0]
        signatures[wargear.wargear_id.removeprefix(prefix)] = _weapon_signature(profile)
    return signatures


def _non_weapon_wargear_ids(catalog: Any, datasheet_id: str) -> set[str]:
    prefix = f"{datasheet_id}:"
    return {
        wargear.wargear_id.removeprefix(prefix)
        for wargear in catalog.wargear
        if wargear.wargear_id.startswith(prefix) and not wargear.weapon_profiles
    }


def _weapon_signature(profile: WeaponProfile) -> tuple[Any, ...]:
    range_value: int | str
    if profile.range_profile.kind is RangeProfileKind.MELEE:
        range_value = "melee"
    else:
        assert profile.range_profile.distance_inches is not None
        range_value = profile.range_profile.distance_inches
    if profile.attack_profile.fixed_attacks is not None:
        attacks = str(profile.attack_profile.fixed_attacks)
    else:
        attack_dice = profile.attack_profile.dice_expression
        assert attack_dice is not None
        attacks = attack_dice.canonical()
    if profile.damage_profile.fixed_damage is not None:
        damage = str(profile.damage_profile.fixed_damage)
    else:
        damage_dice = profile.damage_profile.dice_expression
        assert damage_dice is not None
        damage = damage_dice.canonical()
    return (
        range_value,
        attacks,
        profile.skill.final,
        profile.strength.final,
        profile.armor_penetration.final,
        damage,
        tuple(keyword.value for keyword in profile.keywords),
        tuple(ability.name for ability in profile.abilities),
    )


def _voidscarred_selection(
    *,
    regular_count: int,
    optional_count: int,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitMusterSelection:
    optional_profiles = (
        ()
        if optional_count == 0
        else (
            ModelProfileSelection(f"{VOIDSCARRED_ID}:shade-runner", optional_count),
            ModelProfileSelection(f"{VOIDSCARRED_ID}:soul-weaver", optional_count),
            ModelProfileSelection(f"{VOIDSCARRED_ID}:way-seeker", optional_count),
        )
    )
    return UnitMusterSelection(
        unit_selection_id="voidscarred",
        datasheet_id=VOIDSCARRED_ID,
        model_profile_selections=(
            ModelProfileSelection(VOIDSCARRED_PROFILE_ID, regular_count),
            ModelProfileSelection(VOIDSCARRED_FELARCH_PROFILE_ID, 1),
            *optional_profiles,
        ),
        wargear_selections=wargear_selections,
    )


def _voidreavers_selection(*, unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=VOIDREAVERS_ID,
        model_profile_selections=(
            ModelProfileSelection(VOIDREAVER_PROFILE_ID, 4),
            ModelProfileSelection(VOIDREAVER_FELARCH_PROFILE_ID, 1),
        ),
    )


def _army(*, catalog: Any, army_id: str, player_id: str, unit: Any) -> ArmyDefinition:
    return _army_with_units(
        catalog=catalog,
        army_id=army_id,
        player_id=player_id,
        units=(unit,),
    )


def _army_with_units(
    *,
    catalog: Any,
    army_id: str,
    player_id: str,
    units: tuple[Any, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=catalog.factions[0].faction_id,
            detachment_ids=("void-unit-test-detachment",),
        ),
        units=units,
        attached_units=attached_units,
    )


def _attached_formation(
    *,
    attached_unit_instance_id: str,
    bodyguard_unit_instance_id: str,
    leader_unit_instance_id: str,
) -> AttachedUnitFormation:
    return AttachedUnitFormation(
        attached_unit_instance_id=attached_unit_instance_id,
        bodyguard_unit_instance_id=bodyguard_unit_instance_id,
        leader_unit_instance_ids=(leader_unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard_unit_instance_id, leader_unit_instance_id))
        ),
        source_id=f"{attached_unit_instance_id}:source",
        attachment_source_ids=(f"{attached_unit_instance_id}:eligibility",),
    )


def _muster_request(
    *,
    army: ArmyDefinition,
    selection: UnitMusterSelection,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army.army_id,
        player_id=army.player_id,
        catalog_id=army.catalog_id,
        source_package_id=army.source_package_id,
        ruleset_id=army.ruleset_id,
        detachment_selection=army.detachment_selection,
        unit_selections=(selection,),
    )


def _battle_state(armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="corsair-void-units-runtime",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(BattlePhase.SHOOTING),
        battle_round=1,
        active_player_id="player-b",
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="corsair-void-units-battlefield",
        armies=armies,
    ).battlefield_state
    return state
