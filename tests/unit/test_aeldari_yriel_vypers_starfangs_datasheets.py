from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    DEFAULT_SOURCE_JSON_DIR,
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_yriel_vypers_starfangs_rule_ir import (
    HALLUCINOGEN_GRENADES_ROW_ID,
    HARASSMENT_FIRE_ROW_ID,
    OUTPUT_PATH,
    PIRATICAL_HERO_ROW_ID,
    PRINCE_OF_CORSAIRS_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind, CatalogAbilitySupport
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponKeyword
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_prebattle_redeploy import (
    CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID,
    CatalogPrebattleRedeployPermission,
    apply_redeploy_to_strategic_reserves,
    clause_is_prebattle_redeploy_permission,
    effect_is_prebattle_redeploy_permission,
    rule_has_prebattle_redeploy_permission,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
    CatalogWeaponKeywordGrantRuntime,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_rule_selected_target_classification import (
    rule_has_post_shoot_hit_target_effect,
    rule_has_shooting_start_selected_target_effect,
)
from warhammer40k_core.engine.catalog_selected_target_decisions import (
    invalid_selected_target_effect_status,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ListValidationError,
    ModelProfileSelection,
    UnitMusterSelection,
    WargearSelection,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    SetupStep,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.prebattle import (
    redeploy_unit_selection_request,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionKind,
    setup_step_for_action_kind,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveStatus
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    ShootingPhaseStartHookRegistry,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
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
    aeldari_yriel_vypers_starfangs_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_YRIEL_VYPERS_STARFANGS_HEIGHT_OVERRIDES,
)

PRINCE_YRIEL_ID = "000004193"
VYPERS_ID = "000000605"
STARFANGS_ID = "000004195"
VOIDREAVERS_ID = "000002531"
VOIDREAVER_PROFILE_ID = f"{VOIDREAVERS_ID}:corsair-voidreavers"
VOIDREAVER_FELARCH_PROFILE_ID = f"{VOIDREAVERS_ID}:voidreaver-felarch"
PDF_SHA256 = "48cf09f605dc29b42555d5800c239879c1fc590f85a6a45b0a1f14739b03f0a9"


def test_generated_rule_ir_artifact_is_current_and_source_bound() -> None:
    committed_payload = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed_payload == generated_artifact_payload()
    assert source_package.SOURCE_PDF_SHA256 == PDF_SHA256
    assert source_package.DATASHEET_SOURCE_PAGES == {
        PRINCE_YRIEL_ID: (12, 13),
        VYPERS_ID: (16, 17),
        STARFANGS_ID: (18, 19),
    }
    assert source_package.supported_datasheet_source_row_ids() == (
        HARASSMENT_FIRE_ROW_ID,
        PIRATICAL_HERO_ROW_ID,
        PRINCE_OF_CORSAIRS_ROW_ID,
        HALLUCINOGEN_GRENADES_ROW_ID,
    )
    assert committed_payload["package_hash"] == source_package.PACKAGE_HASH


def test_generated_rule_ir_loader_rejects_package_hash_drift() -> None:
    payload = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))
    payload["package_hash"] = "0" * 64

    with pytest.raises(source_package.AeldariDatasheetRuleIrArtifactError, match="hash is stale"):
        source_package.validate_generated_artifact_bytes(json.dumps(payload).encode())


def test_all_four_datasheet_rules_have_exact_generic_ir_consumers() -> None:
    piratical = _rule_ir(PIRATICAL_HERO_ROW_ID)
    prince = _rule_ir(PRINCE_OF_CORSAIRS_ROW_ID)
    harassment = _rule_ir(HARASSMENT_FIRE_ROW_ID)
    hallucinogen = _rule_ir(HALLUCINOGEN_GRENADES_ROW_ID)

    assert catalog_rule_ir_consumers_for_rule(piratical) == (
        CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
        f"{CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID}:sustained-hits",
    )
    assert rule_has_prebattle_redeploy_permission(prince)
    assert catalog_rule_ir_consumers_for_rule(prince) == (
        CATALOG_IR_PREBATTLE_REDEPLOY_PERMISSION_CONSUMER_ID,
    )
    assert rule_has_post_shoot_hit_target_effect(harassment)
    assert catalog_rule_ir_consumers_for_rule(harassment) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    )
    assert rule_has_shooting_start_selected_target_effect(hallucinogen)
    assert catalog_rule_ir_consumers_for_rule(hallucinogen) == (
        CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID,
    )

    redeploy = prince.clauses[0]
    assert redeploy.trigger is not None
    assert redeploy.trigger.kind is RuleTriggerKind.SETUP
    assert redeploy.target is not None
    assert redeploy.target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert parameter_payload(redeploy.target.parameters) == {
        "allegiance": "friendly",
        "required_keyword": "AELDARI",
    }
    assert tuple(condition.kind for condition in redeploy.conditions) == (
        RuleConditionKind.TARGET_CONSTRAINT,
        RuleConditionKind.FREQUENCY_LIMIT,
    )
    assert {parameter_payload(effect.parameters)["action"] for effect in redeploy.effects} == {
        "redeploy",
        "redeploy_to_strategic_reserves",
    }

    selection, stealth = hallucinogen.clauses
    assert selection.trigger is not None
    assert parameter_payload(selection.trigger.parameters) == {
        "edge": "start",
        "optional": True,
        "owner": "opponent",
        "phase": "shooting",
        "subject": "this_unit",
    }
    assert tuple(condition.kind for condition in selection.conditions) == (
        RuleConditionKind.VISIBILITY_PREDICATE,
        RuleConditionKind.DISTANCE_PREDICATE,
    )
    assert selection.target is not None
    assert selection.target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert parameter_payload(selection.target.parameters)["required_keyword_sequence"] == (
        "AELDARI",
        "INFANTRY",
    )
    assert stealth.target is not None
    assert stealth.target.kind is RuleTargetKind.SELECTED_UNIT
    assert stealth.effects[0].kind is RuleEffectKind.GRANT_ABILITY
    assert stealth.duration is not None
    assert stealth.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT


def test_prince_of_corsairs_redeploy_descriptor_guards_fail_fast() -> None:
    clause = _rule_ir(PRINCE_OF_CORSAIRS_ROW_ID).clauses[0]

    assert not clause_is_prebattle_redeploy_permission(replace(clause, conditions=()))
    assert not clause_is_prebattle_redeploy_permission(
        replace(clause, effects=(clause.effects[0],))
    )
    assert not effect_is_prebattle_redeploy_permission(
        _rule_ir(PIRATICAL_HERO_ROW_ID).clauses[0].effects[0]
    )
    with pytest.raises(GameLifecycleError, match="requires RuleClause"):
        clause_is_prebattle_redeploy_permission(object())  # type: ignore[arg-type]
    with pytest.raises(GameLifecycleError, match="requires RuleEffectSpec"):
        effect_is_prebattle_redeploy_permission(object())  # type: ignore[arg-type]

    with pytest.raises(GameLifecycleError, match="maximum_units"):
        CatalogPrebattleRedeployPermission(
            source_rule_id="test:prince-of-corsairs",
            source_unit_instance_id="army-a:yriel",
            required_keyword="AELDARI",
            maximum_units=0,
            allow_strategic_reserves=True,
            ignore_strategic_reserves_limit=True,
        )
    with pytest.raises(GameLifecycleError, match="Strategic Reserves flag"):
        CatalogPrebattleRedeployPermission(
            source_rule_id="test:prince-of-corsairs",
            source_unit_instance_id="army-a:yriel",
            required_keyword="AELDARI",
            maximum_units=3,
            allow_strategic_reserves=cast(Any, "yes"),
            ignore_strategic_reserves_limit=True,
        )
    with pytest.raises(GameLifecycleError, match="reserve-limit flag"):
        CatalogPrebattleRedeployPermission(
            source_rule_id="test:prince-of-corsairs",
            source_unit_instance_id="army-a:yriel",
            required_keyword="AELDARI",
            maximum_units=3,
            allow_strategic_reserves=True,
            ignore_strategic_reserves_limit=cast(Any, "yes"),
        )
    assert setup_step_for_action_kind(PreBattleActionKind.REDEPLOY) is SetupStep.REDEPLOY_UNITS
    assert (
        setup_step_for_action_kind(PreBattleActionKind.SCOUT_MOVE)
        is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    )


@pytest.mark.parametrize(
    ("datasheet_id", "name", "characteristics", "base", "keywords", "abilities", "count"),
    [
        (
            PRINCE_YRIEL_ID,
            "Prince Yriel",
            (7, 3, 3, 5, 6, 1, 4),
            ("circular", 40.0, None),
            ("AELDARI", "ANHRATHE", "CHARACTER", "EPIC HERO", "INFANTRY", "PRINCE YRIEL"),
            ("Battle Focus", "Leader", "Piratical Hero", "Prince of Corsairs", "Scouts"),
            (1, 1),
        ),
        (
            VYPERS_ID,
            "Vypers",
            (14, 6, 3, 6, 7, 2, 0),
            ("oval", 105.0, 70.0),
            ("AELDARI", "FLY", "VEHICLE", "VYPERS"),
            ("Battle Focus", "Deadly Demise", "Harassment Fire"),
            (1, 2),
        ),
        (
            STARFANGS_ID,
            "Starfangs",
            (14, 6, 3, 6, 7, 2, 0),
            ("oval", 105.0, 70.0),
            ("AELDARI", "ANHRATHE", "FLY", "GRENADES", "SMOKE", "STARFANGS", "VEHICLE"),
            ("Battle Focus", "Deadly Demise", "Hallucinogen Grenades", "Scouts"),
            (1, 2),
        ),
    ],
)
def test_catalog_preserves_datasheet_stats_keywords_composition_and_abilities(
    datasheet_id: str,
    name: str,
    characteristics: tuple[int, ...],
    base: tuple[str, float, float | None],
    keywords: tuple[str, ...],
    abilities: tuple[str, ...],
    count: tuple[int, int],
) -> None:
    datasheet = _catalog().datasheet_by_id(datasheet_id)
    model = datasheet.model_profiles[0]
    values = {value.characteristic: value.final for value in model.characteristics}

    assert datasheet.name == name
    assert (
        values[Characteristic.MOVEMENT],
        values[Characteristic.TOUGHNESS],
        values[Characteristic.SAVE],
        values[Characteristic.WOUNDS],
        values[Characteristic.LEADERSHIP],
        values[Characteristic.OBJECTIVE_CONTROL],
        values[Characteristic.INVULNERABLE_SAVE],
    ) == characteristics
    assert model.base_size.kind.value == base[0]
    if base[0] == "circular":
        assert model.base_size.diameter_mm == base[1]
    else:
        assert round(model.base_size.length_mm, 6) == base[1]
        assert model.base_size.width_mm == base[2]
    assert datasheet.keywords.keywords == keywords
    assert datasheet.keywords.faction_keywords == ("ASURYANI",)
    assert (datasheet.composition[0].min_models, datasheet.composition[0].max_models) == count
    assert tuple(sorted(ability.name for ability in datasheet.abilities)) == abilities
    assert not datasheet.mustering_options
    for ability in datasheet.abilities:
        if ability.source_kind is CatalogAbilitySourceKind.DATASHEET:
            assert ability.support is CatalogAbilitySupport.GENERIC_RULE_IR
            assert ability.rule_ir_payload is not None


def test_catalog_preserves_every_weapon_profile() -> None:
    expected = {
        (PRINCE_YRIEL_ID, "Eye of Wrath"): (6, "3", 2, 6, -2, "2", ("Assault", "Pistol")),
        (PRINCE_YRIEL_ID, "Shuriken pistol"): (
            12,
            "1",
            2,
            4,
            -1,
            "1",
            ("Assault", "Pistol"),
        ),
        (PRINCE_YRIEL_ID, "Spear of Twilight"): ("melee", "5", 2, 7, -3, "3", ("Lance",)),
        (VYPERS_ID, "Bright lance"): (36, "1", 3, 12, -3, "D6+2", ()),
        (VYPERS_ID, "Missile launcher - starshot"): (48, "1", 3, 10, -2, "D6", ()),
        (VYPERS_ID, "Missile launcher - sunburst"): (48, "D6", 3, 4, -1, "1", ("Blast",)),
        (VYPERS_ID, "Scatter laser"): (36, "6", 3, 5, 0, "1", ("Sustained Hits",)),
        (VYPERS_ID, "Shuriken cannon"): (24, "3", 3, 6, -1, "2", ("Lethal Hits",)),
        (VYPERS_ID, "Starcannon"): (36, "2", 2, 8, -3, "2", ()),
        (VYPERS_ID, "Wraithbone hull"): ("melee", "3", 4, 6, 0, "1", ()),
        (STARFANGS_ID, "Disintegrator cannon"): (36, "3", 3, 6, -3, "2", ("Assault",)),
        (STARFANGS_ID, "Starfang grenade launcher"): (
            36,
            "D3",
            3,
            6,
            -3,
            "2",
            ("Assault", "Blast"),
        ),
        (STARFANGS_ID, "Wraithbone hull"): ("melee", "3", 4, 6, 0, "1", ()),
    }

    assert {
        (datasheet_id, profile.name): _profile_summary(profile)
        for datasheet_id in (PRINCE_YRIEL_ID, VYPERS_ID, STARFANGS_ID)
        for wargear in _catalog().wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
    } == expected


def test_vypers_any_number_replacement_options_are_model_count_bounded() -> None:
    datasheet = _catalog().datasheet_by_id(VYPERS_ID)
    replacement_options = tuple(option for option in datasheet.wargear_options if option.effects)

    assert {
        (
            option.option_id,
            option.max_selections,
            option.effects[0].replaced_wargear_id,
            option.effects[0].wargear_id,
        )
        for option in replacement_options
    } == {
        (
            f"{VYPERS_ID}:bright-lance-scatter-laser:option-1",
            2,
            f"{VYPERS_ID}:bright-lance",
            f"{VYPERS_ID}:scatter-laser",
        ),
        (
            f"{VYPERS_ID}:bright-lance-starcannon:option-1",
            2,
            f"{VYPERS_ID}:bright-lance",
            f"{VYPERS_ID}:starcannon",
        ),
        (
            f"{VYPERS_ID}:shuriken-cannon-missile-launcher:option-2",
            2,
            f"{VYPERS_ID}:shuriken-cannon",
            f"{VYPERS_ID}:missile-launcher",
        ),
    }
    assert {
        (
            option.selection_limit.selection_group_id,
            option.selection_limit.models_per_increment,
            option.selection_limit.max_group_selections_per_increment,
            option.selection_limit.max_option_selections_per_increment,
        )
        for option in replacement_options
        if option.selection_limit is not None
    } == {
        (f"{VYPERS_ID}:any-number-replacement-option-1", 1, 1, 1),
        (f"{VYPERS_ID}:any-number-replacement-option-2", 1, 1, 1),
    }


def test_vypers_replacement_loadouts_resolve_for_each_model_and_reject_overflow() -> None:
    catalog = _catalog()
    datasheet = catalog.datasheet_by_id(VYPERS_ID)
    profile_id = datasheet.model_profiles[0].model_profile_id
    two_models = (ModelProfileSelection(profile_id, 2),)
    scatter_option = f"{VYPERS_ID}:bright-lance-scatter-laser:option-1"
    starcannon_option = f"{VYPERS_ID}:bright-lance-starcannon:option-1"
    missile_option = f"{VYPERS_ID}:shuriken-cannon-missile-launcher:option-2"

    resolved = resolve_wargear_selections(
        catalog=catalog,
        datasheet=datasheet,
        requested_selections=(
            WargearSelection(
                option_id=scatter_option,
                model_profile_id=profile_id,
                wargear_ids=(f"{VYPERS_ID}:scatter-laser",),
            ),
            WargearSelection(
                option_id=starcannon_option,
                model_profile_id=profile_id,
                wargear_ids=(f"{VYPERS_ID}:starcannon",),
            ),
            WargearSelection(
                option_id=missile_option,
                model_profile_id=profile_id,
                wargear_ids=(f"{VYPERS_ID}:missile-launcher",),
                selection_count=2,
            ),
        ),
        model_profile_selections=two_models,
    )

    assert {
        selection.option_id: selection.resolved_selection_count
        for selection in resolved
        if selection.option_id in {scatter_option, starcannon_option, missile_option}
    } == {scatter_option: 1, starcannon_option: 1, missile_option: 2}

    with pytest.raises(ListValidationError, match="scaled limit"):
        resolve_wargear_selections(
            catalog=catalog,
            datasheet=datasheet,
            requested_selections=(
                WargearSelection(
                    option_id=scatter_option,
                    model_profile_id=profile_id,
                    wargear_ids=(f"{VYPERS_ID}:scatter-laser",),
                    selection_count=2,
                ),
                WargearSelection(
                    option_id=starcannon_option,
                    model_profile_id=profile_id,
                    wargear_ids=(f"{VYPERS_ID}:starcannon",),
                ),
            ),
            model_profile_selections=two_models,
        )


def test_yriel_leader_targets_and_all_geometry_rows_have_source_evidence() -> None:
    leader_payload = cast(
        dict[str, Any],
        json.loads(
            (DEFAULT_SOURCE_JSON_DIR / "Datasheets_leader.json").read_text(encoding="utf-8")
        ),
    )
    target_ids = {
        cast(str, row["fields"]["attached_id"])
        for row in cast(list[dict[str, Any]], leader_payload["rows"])
        if row["fields"]["leader_id"] == PRINCE_YRIEL_ID
    }
    assert target_ids == {"000002531", "000002532"}

    assert {
        (row.datasheet_id, row.model_name, row.height)
        for row in AELDARI_YRIEL_VYPERS_STARFANGS_HEIGHT_OVERRIDES
    } == {
        (PRINCE_YRIEL_ID, "Prince Yriel - EPIC HERO", 2.5),
        (VYPERS_ID, "Vypers", 2.75),
        (STARFANGS_ID, "Starfangs", 2.75),
    }
    assert all(row.height_source_id for row in AELDARI_YRIEL_VYPERS_STARFANGS_HEIGHT_OVERRIDES)
    assert all(
        "Warhammer Event Companion 2026-06-12 p.59" in row.height_document_reference
        for row in AELDARI_YRIEL_VYPERS_STARFANGS_HEIGHT_OVERRIDES
    )


def test_piratical_hero_grants_only_while_yriel_is_leading_an_attached_unit() -> None:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    yriel = _instantiate(
        factory,
        army_id="army-a",
        selection_id="yriel",
        datasheet_id=PRINCE_YRIEL_ID,
    )
    voidreavers = factory.instantiate_unit(
        army_id="army-a",
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
    enemy_vyper = _instantiate(
        factory,
        army_id="army-b",
        selection_id="vypers",
        datasheet_id=VYPERS_ID,
    )
    attached_id = "attached-unit:army-a:yriel-voidreavers"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=voidreavers.unit_instance_id,
        leader_unit_instance_ids=(yriel.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((voidreavers.unit_instance_id, yriel.unit_instance_id))
        ),
        source_id="test:prince-yriel-attachment",
        attachment_source_ids=("test:prince-yriel-leader-eligibility",),
    )
    attached_armies = (
        _army(
            catalog,
            army_id="army-a",
            player_id="player-a",
            units=(yriel, voidreavers),
            attached_units=(formation,),
        ),
        _army(catalog, army_id="army-b", player_id="player-b", units=(enemy_vyper,)),
    )
    records = catalog_ability_records_from_catalog(catalog)
    attached_indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in attached_armies
    }
    attached_state = _state_for_armies(attached_armies, stage=GameLifecycleStage.BATTLE)
    attacker = voidreavers.own_models[0]
    rifle = _weapon_profile(VOIDREAVERS_ID, "Shuriken rifle")
    hit_context = HitRollModifierContext(
        state=attached_state,
        attacking_unit_instance_id=attached_id,
        attacker_model_instance_id=attacker.model_instance_id,
        target_unit_instance_id=enemy_vyper.unit_instance_id,
        weapon_profile=rifle,
        source_phase=BattlePhase.SHOOTING,
    )
    piratical_source_id = _rule_ir(PIRATICAL_HERO_ROW_ID).source_id
    hit_binding = next(
        binding
        for binding in CatalogDatasheetRuleRuntime(
            attached_indexes,
            attached_armies,
        ).hit_roll_modifier_bindings()
        if binding.source_id == piratical_source_id
    )
    assert hit_binding.handler(hit_context) == 1

    weapon_context = WeaponProfileModifierContext(
        state=attached_state,
        source_phase=BattlePhase.SHOOTING,
        attacking_unit_instance_id=attached_id,
        attacker_model_instance_id=attacker.model_instance_id,
        target_unit_instance_id=enemy_vyper.unit_instance_id,
        weapon_profile=rifle,
    )
    modified = CatalogWeaponKeywordGrantRuntime(
        attached_indexes,
        attached_armies,
    ).weapon_profile_modifier(weapon_context)
    assert WeaponKeyword.SUSTAINED_HITS in modified.keywords
    assert "sustained-hits:1" in {ability.ability_id for ability in modified.abilities}

    unled_armies = (
        _army(
            catalog,
            army_id="army-a",
            player_id="player-a",
            units=(yriel, voidreavers),
        ),
        attached_armies[1],
    )
    unled_indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in unled_armies
    }
    unled_state = _state_for_armies(unled_armies, stage=GameLifecycleStage.BATTLE)
    yriel_profile = _weapon_profile(PRINCE_YRIEL_ID, "Spear of Twilight")
    unled_context = WeaponProfileModifierContext(
        state=unled_state,
        source_phase=BattlePhase.FIGHT,
        attacking_unit_instance_id=yriel.unit_instance_id,
        attacker_model_instance_id=yriel.own_models[0].model_instance_id,
        target_unit_instance_id=enemy_vyper.unit_instance_id,
        weapon_profile=yriel_profile,
    )
    assert (
        CatalogWeaponKeywordGrantRuntime(
            unled_indexes,
            unled_armies,
        ).weapon_profile_modifier(unled_context)
        == yriel_profile
    )

    attached_setup_state = _state_for_armies(attached_armies, stage=GameLifecycleStage.SETUP)
    redeploy_request = redeploy_unit_selection_request(
        state=attached_setup_state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        player_id="player-a",
    )
    option_ids = {option.option_id for option in redeploy_request.options}
    assert f"redeploy:{attached_id}" in option_ids
    assert f"redeploy_to_strategic_reserves:{attached_id}" not in option_ids


def test_hallucinogen_grenades_uses_opponent_shooting_start_decision_and_grants_stealth() -> None:
    catalog, armies, state = _runtime_fixture(stage=GameLifecycleStage.BATTLE)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    restriction_hooks = ShootingTargetRestrictionHookRegistry.empty()
    request = runtime.shooting_phase_start_request(
        ShootingPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            shooting_target_restriction_hooks=restriction_hooks,
        )
    )

    assert request is not None
    assert request.actor_id == "player-a"
    assert isinstance(request.payload, dict)
    assert request.payload["optional"] is True
    target_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and option.payload.get("use_ability") is True
        and cast(dict[str, Any], option.payload["selected_catalog_target_effect"])[
            "target_unit_instance_id"
        ]
        == "army-a:yriel"
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="hallucinogen-grenades-select-yriel",
        request=request,
        selected_option_id=target_option.option_id,
    )
    decisions.submit_result(result)

    applied = runtime.apply_shooting_phase_start_result(
        ShootingPhaseStartResultContext(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            shooting_target_restriction_hooks=restriction_hooks,
        )
    )
    assert applied is True
    assert len(state.persisting_effects_for_unit("army-a:yriel")) == 1

    stealth_binding = next(
        binding
        for binding in CatalogDatasheetRuleRuntime(indexes, armies).hit_roll_modifier_bindings()
        if binding.modifier_id == CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID
    )
    enemy_vyper = _unit(armies, "army-b:vypers")
    assert (
        stealth_binding.handler(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=enemy_vyper.unit_instance_id,
                attacker_model_instance_id=enemy_vyper.own_models[0].model_instance_id,
                target_unit_instance_id="army-a:yriel",
                weapon_profile=_weapon_profile(VYPERS_ID, "Bright lance"),
                source_phase=BattlePhase.SHOOTING,
            )
        )
        == -1
    )


def test_hallucinogen_grenades_rejects_malformed_finite_results() -> None:
    catalog, armies, state = _runtime_fixture(stage=GameLifecycleStage.BATTLE)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    request = CatalogSelectedTargetEffectRuntime(indexes, armies).shooting_phase_start_request(
        ShootingPhaseStartRequestContext(
            state=state,
            decisions=DecisionController(),
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            shooting_target_restriction_hooks=ShootingTargetRestrictionHookRegistry.empty(),
        )
    )
    assert request is not None
    option = next(
        candidate
        for candidate in request.options
        if isinstance(candidate.payload, dict) and candidate.payload.get("use_ability") is True
    )
    valid = DecisionResult.for_request(
        result_id="hallucinogen-grenades-finite-validation",
        request=request,
        selected_option_id=option.option_id,
    )
    invalid_results = (
        (replace(valid, request_id="wrong-request"), "request_id"),
        (replace(valid, decision_type="wrong-decision"), "decision_type"),
        (replace(valid, actor_id="wrong-player"), "actor_id"),
        (replace(valid, selected_option_id="wrong-option"), "selected_option_id"),
        (replace(valid, payload={"submission_kind": "wrong"}), "payload"),
    )
    assert isinstance(option.payload, dict)
    submission_kind = cast(str, option.payload["submission_kind"])
    for result, expected_field in invalid_results:
        status = invalid_selected_target_effect_status(
            state=state,
            request=request,
            result=result,
            expected_decision_type=request.decision_type,
            expected_submission_kind=submission_kind,
            expected_phase=BattlePhase.SHOOTING,
            invalid_reason="invalid_hallucinogen_grenades_test_result",
        )
        assert status is not None
        assert isinstance(status.payload, dict)
        assert status.payload["field"] == expected_field


def test_hallucinogen_grenades_revalidates_target_eligibility_before_queue_pop() -> None:
    catalog, armies, state = _runtime_fixture(stage=GameLifecycleStage.BATTLE)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    decisions = DecisionController()
    runtime = CatalogSelectedTargetEffectRuntime(indexes, armies)
    restriction_hooks = ShootingTargetRestrictionHookRegistry.empty()
    handler = ShootingPhaseHandler(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        shooting_phase_start_hooks=ShootingPhaseStartHookRegistry.from_bindings(
            runtime.shooting_phase_start_bindings()
        ),
        shooting_target_restriction_hooks=restriction_hooks,
    )
    request = handler.shooting_phase_start_hooks.next_request_for(
        ShootingPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            army_catalog=catalog,
            shooting_target_restriction_hooks=restriction_hooks,
        )
    )
    assert request is not None
    target_option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict)
        and cast(dict[str, Any], option.payload["selected_catalog_target_effect"])[
            "target_unit_instance_id"
        ]
        == "army-a:yriel"
    )
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="hallucinogen-grenades-stale-yriel",
        request=request,
        selected_option_id=target_option.option_id,
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement("army-a:yriel"))

    invalid = handler.invalid_shooting_phase_start_faction_rule_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )

    assert invalid is not None
    assert isinstance(invalid.payload, dict)
    assert invalid.payload["invalid_reason"] == "shooting_phase_start_selected_target_drift"
    assert decisions.queue.pending_requests == (request,)
    assert state.persisting_effects == []


def test_prince_of_corsairs_finite_option_moves_a_real_unit_to_cap_exempt_reserves() -> None:
    catalog, _, state = _runtime_fixture(stage=GameLifecycleStage.SETUP)
    request = redeploy_unit_selection_request(
        state=state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        player_id="player-a",
    )
    option_id = "redeploy_to_strategic_reserves:army-a:starfangs"
    assert option_id in {option.option_id for option in request.options}
    option = next(option for option in request.options if option.option_id == option_id)
    assert isinstance(option.payload, dict)
    assert option.payload["ignore_strategic_reserves_limit"] is True

    decisions = DecisionController()
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id="prince-of-corsairs-starfangs-to-reserves",
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    reserve_state = apply_redeploy_to_strategic_reserves(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        points_contribution=0,
    )

    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.status is ReserveStatus.IN_RESERVES
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none("army-a:starfangs") is None
    starfangs = _unit(state.army_definitions, "army-a:starfangs")
    assert set(state.unarrived_reserve_model_ids()) == {
        model.model_instance_id for model in starfangs.own_models
    }
    action = state.prebattle_action_records[-1]
    assert action.action_kind is PreBattleActionKind.REDEPLOY_TO_STRATEGIC_RESERVES
    assert action.source_rule_id == _rule_ir(PRINCE_OF_CORSAIRS_ROW_ID).source_id


def test_prince_of_corsairs_reserve_action_rejects_payload_drift_before_mutation() -> None:
    catalog, _, state = _runtime_fixture(stage=GameLifecycleStage.SETUP)
    request = redeploy_unit_selection_request(
        state=state,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        army_catalog=catalog,
        player_id="player-a",
    )
    option_id = "redeploy_to_strategic_reserves:army-a:starfangs"
    valid = DecisionResult.for_request(
        result_id="prince-of-corsairs-drift-validation",
        request=request,
        selected_option_id=option_id,
    )
    assert isinstance(valid.payload, dict)
    payload = valid.payload
    invalid_results = (
        (
            replace(valid, payload={**payload, "action_kind": "not-an-action"}),
            "action kind is invalid",
        ),
        (
            replace(
                valid,
                payload={**payload, "action_kind": PreBattleActionKind.REDEPLOY.value},
            ),
            "action kind drift",
        ),
        (
            replace(
                valid,
                payload={
                    key: value
                    for key, value in payload.items()
                    if key != "ignore_strategic_reserves_limit"
                },
            ),
            "requires cap exemption",
        ),
        (replace(valid, actor_id="player-b"), "player drift"),
        (
            replace(valid, payload={**payload, "source_rule_id": "test:wrong-source"}),
            "permission is unavailable",
        ),
    )
    for result, message in invalid_results:
        with pytest.raises(GameLifecycleError, match=message):
            apply_redeploy_to_strategic_reserves(
                state=state,
                request=request,
                result=result,
                decisions=DecisionController(),
                ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
                points_contribution=0,
            )
    assert state.reserve_states == []
    assert state.prebattle_action_records == []


def _catalog() -> Any:
    return _ability_support_catalog_package().army_catalog


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _profile_summary(profile: Any) -> tuple[object, str, int, int, int, str, tuple[str, ...]]:
    range_value: object = (
        "melee"
        if profile.range_profile.kind is RangeProfileKind.MELEE
        else profile.range_profile.distance_inches
    )
    attacks = (
        str(profile.attack_profile.fixed_attacks)
        if profile.attack_profile.fixed_attacks is not None
        else profile.attack_profile.dice_expression.canonical()
    )
    damage = (
        str(profile.damage_profile.fixed_damage)
        if profile.damage_profile.fixed_damage is not None
        else profile.damage_profile.dice_expression.canonical()
    )
    return (
        range_value,
        attacks,
        profile.skill.final,
        profile.strength.final,
        profile.armor_penetration.final,
        damage,
        tuple(keyword.value for keyword in profile.keywords),
    )


def _runtime_fixture(
    *, stage: GameLifecycleStage
) -> tuple[Any, tuple[ArmyDefinition, ...], GameState]:
    package = _ability_support_catalog_package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    yriel = _instantiate(
        factory,
        army_id="army-a",
        selection_id="yriel",
        datasheet_id=PRINCE_YRIEL_ID,
    )
    starfangs = _instantiate(
        factory,
        army_id="army-a",
        selection_id="starfangs",
        datasheet_id=STARFANGS_ID,
    )
    vypers = _instantiate(
        factory,
        army_id="army-b",
        selection_id="vypers",
        datasheet_id=VYPERS_ID,
    )
    armies = (
        _army(catalog, army_id="army-a", player_id="player-a", units=(yriel, starfangs)),
        _army(catalog, army_id="army-b", player_id="player-b", units=(vypers,)),
    )
    return catalog, armies, _state_for_armies(armies, stage=stage)


def _state_for_armies(
    armies: tuple[ArmyDefinition, ...],
    *,
    stage: GameLifecycleStage,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    setup_index = (
        tuple(descriptor.setup_sequence.steps).index(SetupStep.REDEPLOY_UNITS)
        if stage is GameLifecycleStage.SETUP
        else None
    )
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="aeldari-yriel-vypers-starfangs-test",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=stage,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=setup_index,
        battle_phase_index=(
            phases.index(BattlePhase.SHOOTING) if stage is GameLifecycleStage.BATTLE else None
        ),
        battle_round=(1 if stage is GameLifecycleStage.BATTLE else 0),
        active_player_id=("player-b" if stage is GameLifecycleStage.BATTLE else None),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="aeldari-yriel-vypers-starfangs-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _instantiate(
    factory: UnitFactory,
    *,
    army_id: str,
    selection_id: str,
    datasheet_id: str,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    profile = datasheet.model_profiles[0]
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(ModelProfileSelection(profile.model_profile_id, 1),),
        ),
    )


def _army(
    catalog: Any,
    *,
    army_id: str,
    player_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...] = (),
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="AE",
            detachment_ids=("corsair-coterie",),
        ),
        units=units,
        attached_units=attached_units,
    )


def _unit(
    armies: tuple[ArmyDefinition, ...] | list[ArmyDefinition],
    unit_instance_id: str,
) -> UnitInstance:
    return next(
        unit for army in armies for unit in army.units if unit.unit_instance_id == unit_instance_id
    )


def _weapon_profile(datasheet_id: str, profile_name: str) -> Any:
    return next(
        profile
        for wargear in _catalog().wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if profile.name == profile_name
    )
