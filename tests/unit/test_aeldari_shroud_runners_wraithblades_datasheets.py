from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_shroud_runners_wraithblades_rule_ir import (
    FORCESHIELD_ROW_ID,
    MALEVOLENT_SOULS_ROW_ID,
    OUTPUT_PATH,
    TARGET_ACQUISITION_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequenceStep
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
    CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID,
    CATALOG_IR_LEADERSHIP_CHARACTERISTIC_QUERY_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
    CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    CatalogPostShootHitTargetStatusRuntime,
    apply_catalog_post_shoot_hit_target_status_result,
    catalog_leadership_characteristic_for_unit,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionKind,
    DestructionReactionSource,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    RuntimeModifierRegistry,
    SaveOptionModifierContext,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.saves import SaveKind, SaveOption
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_shroud_runners_wraithblades_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_SHROUD_RUNNERS_WRAITHBLADES_HEIGHT_OVERRIDES,
)

SHROUD_RUNNERS_ID = "000002533"
WRAITHBLADES_ID = "000000598"
WRAITH_PROFILE_ID = f"{WRAITHBLADES_ID}:wraithblades"
SHIELD_OPTION_ID = f"{WRAITHBLADES_ID}:ghostaxe-forceshield:option-1"


@cache
def _package() -> Any:
    return _ability_support_catalog_package()


def test_generated_rule_ir_artifact_is_current_source_bound_and_fail_fast() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert source_package.supported_datasheet_source_row_ids() == (
        MALEVOLENT_SOULS_ROW_ID,
        FORCESHIELD_ROW_ID,
        TARGET_ACQUISITION_ROW_ID,
    )
    assert committed["package_hash"] == source_package.PACKAGE_HASH

    committed["package_hash"] = "0" * 64
    with pytest.raises(
        source_package.AeldariShroudWraithRuleIrArtifactError, match="hash is stale"
    ):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_exact_rules_have_registered_generic_consumers() -> None:
    target = _static_rule(TARGET_ACQUISITION_ROW_ID)
    malevolent = _static_rule(MALEVOLENT_SOULS_ROW_ID)
    forceshield = _static_rule(FORCESHIELD_ROW_ID)
    psychic = _catalog_rule(WRAITHBLADES_ID, "Psychic Guidance")

    assert catalog_rule_ir_consumers_for_rule(target) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_STATUS_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(malevolent) == (
        CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(forceshield) == (
        CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(psychic) == (
        CATALOG_IR_HIT_ROLL_MODIFIER_CONSUMER_ID,
        CATALOG_IR_LEADERSHIP_CHARACTERISTIC_QUERY_CONSUMER_ID,
    )


def test_catalog_preserves_stats_geometry_abilities_weapons_and_fixed_loadout_choice() -> None:
    catalog = _package().army_catalog
    shroud = catalog.datasheet_by_id(SHROUD_RUNNERS_ID)
    wraith = catalog.datasheet_by_id(WRAITHBLADES_ID)

    assert _characteristics(shroud) == (14, 4, 5, 3, 7, 2, 0)
    assert shroud.model_profiles[0].base_size.diameter_mm == 60.0
    assert shroud.keywords.keywords == ("AELDARI", "FLY", "MOUNTED", "SHROUD RUNNERS")
    assert (shroud.composition[0].min_models, shroud.composition[0].max_models) == (3, 6)
    assert {ability.name for ability in shroud.abilities} == {
        "Battle Focus",
        "Ranged Invulnerable Save",
        "Scouts",
        "Stealth",
        "Target Acquisition",
    }
    assert _weapon_names(SHROUD_RUNNERS_ID) == {
        "Close combat weapon",
        "Long rifle",
        "Scatter laser",
        "Shuriken pistol",
    }

    assert _characteristics(wraith) == (6, 6, 2, 3, 8, 1, 0)
    assert wraith.model_profiles[0].base_size.diameter_mm == 40.0
    assert wraith.keywords.keywords == (
        "AELDARI",
        "INFANTRY",
        "WRAITH CONSTRUCT",
        "WRAITHBLADES",
    )
    assert (wraith.composition[0].min_models, wraith.composition[0].max_models) == (5, 5)
    assert {ability.name for ability in wraith.abilities} == {
        "Forceshield",
        "Malevolent Souls",
        "Psychic Guidance",
    }
    assert _weapon_names(WRAITHBLADES_ID) == {"Ghostaxe", "Ghostswords"}
    option = next(
        option for option in wraith.wargear_options if option.option_id == SHIELD_OPTION_ID
    )
    assert (option.min_selections, option.max_selections) == (0, 2)
    assert {effect.model_count for effect in option.effects} == {5}

    assert {
        (row.datasheet_id, row.model_name, row.height)
        for row in AELDARI_SHROUD_RUNNERS_WRAITHBLADES_HEIGHT_OVERRIDES
    } == {
        (SHROUD_RUNNERS_ID, "Shroud Runners", 3.25),
        (WRAITHBLADES_ID, "Wraithblades", 2.5),
    }


def test_wraithblade_all_model_choice_replaces_every_ghostsword_and_grants_forceshields() -> None:
    factory = UnitFactory(
        catalog=_package().army_catalog,
        model_geometries=_package().model_geometries,
    )
    unit = _instantiate(
        factory,
        army_id="army-a",
        selection_id="wraith-shields",
        datasheet_id=WRAITHBLADES_ID,
        wargear_selections=(
            WargearSelection(
                option_id=SHIELD_OPTION_ID,
                model_profile_id=WRAITH_PROFILE_ID,
                wargear_ids=(
                    f"{WRAITHBLADES_ID}:forceshield",
                    f"{WRAITHBLADES_ID}:ghostaxe",
                ),
            ),
        ),
    )

    assert len(unit.own_models) == 5
    assert all(
        set(model.wargear_ids) == {f"{WRAITHBLADES_ID}:forceshield", f"{WRAITHBLADES_ID}:ghostaxe"}
        for model in unit.own_models
    )


def test_conditional_and_wargear_invulnerable_saves_use_attack_and_bearer_context() -> None:
    fixture = _runtime_fixture()
    runtime = fixture.runtime
    registry = RuntimeModifierRegistry.from_bindings(
        save_option_modifier_bindings=runtime.save_option_modifier_bindings()
    )
    armour = (SaveOption(SaveKind.ARMOUR, 5, 5, 0),)
    ranged = _profile(SHROUD_RUNNERS_ID, "Long rifle")
    melee = _profile(SHROUD_RUNNERS_ID, "Close combat weapon")

    shroud_model = fixture.shroud.own_models[0]
    assert (
        _invulnerable_target(
            registry.modified_save_options(
                SaveOptionModifierContext(
                    state=fixture.state,
                    target_unit_instance_id=fixture.shroud.unit_instance_id,
                    save_options=armour,
                    source_phase=BattlePhase.SHOOTING,
                    weapon_profile=ranged,
                    allocated_model_instance_id=shroud_model.model_instance_id,
                )
            )
        )
        == 5
    )
    assert (
        _invulnerable_target(
            registry.modified_save_options(
                SaveOptionModifierContext(
                    state=fixture.state,
                    target_unit_instance_id=fixture.shroud.unit_instance_id,
                    save_options=armour,
                    source_phase=BattlePhase.FIGHT,
                    weapon_profile=melee,
                    allocated_model_instance_id=shroud_model.model_instance_id,
                )
            )
        )
        is None
    )

    shield_model = fixture.wraith_shields.own_models[0]
    sword_model = fixture.wraith_swords.own_models[0]
    assert (
        _invulnerable_target(
            registry.modified_save_options(
                SaveOptionModifierContext(
                    state=fixture.state,
                    target_unit_instance_id=fixture.wraith_shields.unit_instance_id,
                    save_options=armour,
                    source_phase=BattlePhase.FIGHT,
                    weapon_profile=melee,
                    allocated_model_instance_id=shield_model.model_instance_id,
                )
            )
        )
        == 4
    )
    assert (
        _invulnerable_target(
            registry.modified_save_options(
                SaveOptionModifierContext(
                    state=fixture.state,
                    target_unit_instance_id=fixture.wraith_swords.unit_instance_id,
                    save_options=armour,
                    source_phase=BattlePhase.FIGHT,
                    weapon_profile=melee,
                    allocated_model_instance_id=sword_model.model_instance_id,
                )
            )
        )
        is None
    )


def test_psychic_guidance_is_proximity_gated_for_leadership_and_hit_rolls() -> None:
    fixture = _runtime_fixture()
    registry = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=(
            fixture.runtime.unit_characteristic_modifier_bindings()
        ),
        hit_roll_modifier_bindings=fixture.runtime.hit_roll_modifier_bindings(),
    )
    wraith = fixture.wraith_shields
    enemy = fixture.enemy_one
    model = wraith.own_models[0]
    index = fixture.indexes["player-a"]
    _move_unit(fixture.state, wraith.unit_instance_id, x=10.0, y=10.0)
    _move_unit(fixture.state, fixture.psyker.unit_instance_id, x=20.0, y=10.0)

    assert (
        catalog_leadership_characteristic_for_unit(
            ability_index=index,
            unit=wraith,
            current_model_instance_ids=wraith.own_model_ids(),
        )
        is None
    )
    characteristic_context = UnitCharacteristicModifierContext(
        state=fixture.state,
        unit_instance_id=wraith.unit_instance_id,
        characteristic=Characteristic.LEADERSHIP,
        base_value=8,
        current_value=8,
    )
    hit_context = HitRollModifierContext(
        state=fixture.state,
        attacking_unit_instance_id=wraith.unit_instance_id,
        attacker_model_instance_id=model.model_instance_id,
        target_unit_instance_id=enemy.unit_instance_id,
        weapon_profile=_profile(WRAITHBLADES_ID, "Ghostaxe"),
        source_phase=BattlePhase.FIGHT,
    )
    assert registry.modified_unit_characteristic(characteristic_context) == 6
    assert registry.hit_roll_modifier(hit_context) == 1

    _move_unit(fixture.state, fixture.psyker.unit_instance_id, x=50.0, y=10.0)
    assert registry.modified_unit_characteristic(characteristic_context) == 8
    assert registry.hit_roll_modifier(hit_context) == 0


def test_malevolent_souls_registers_idempotent_serializable_model_sources() -> None:
    fixture = _runtime_fixture()

    first = fixture.runtime.record_static_destruction_reaction_sources(state=fixture.state)
    second = fixture.runtime.record_static_destruction_reaction_sources(state=fixture.state)

    assert first == second
    assert len(first) == 20
    for unit in (
        fixture.wraith_shields,
        fixture.wraith_swords,
        fixture.enemy_one,
        fixture.enemy_two,
    ):
        for model in unit.own_models:
            sources = fixture.state.destruction_reaction_sources_for_model(
                model_instance_id=model.model_instance_id
            )
            assert len(sources) == 1
            source = sources[0]
            assert source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH
            assert DestructionReactionSource.from_payload(source.to_payload()) == source
            payload = cast(dict[str, Any], source.payload)
            assert payload["trigger_roll_threshold"] == 3
            assert payload["trigger_roll_type"] == "aeldari_malevolent_souls"
            assert payload["requires_destroyed_by_melee_attack"] is True
            assert payload["requires_not_fought_this_phase"] is True

    restored = GameState.from_payload(
        json.loads(json.dumps(fixture.state.to_payload(), sort_keys=True))
    )
    assert restored.destruction_reaction_sources_by_model_id == (
        fixture.state.destruction_reaction_sources_by_model_id
    )


def test_target_acquisition_only_enumerates_units_hit_by_long_rifles_and_applies_status() -> None:
    fixture = _runtime_fixture()
    decisions = DecisionController()
    attacker = fixture.shroud.own_models[0]
    scatter = _profile(SHROUD_RUNNERS_ID, "Scatter laser")
    long_rifle = _profile(SHROUD_RUNNERS_ID, "Long rifle")
    sequence = AttackSequence(
        sequence_id="attack-sequence:shroud-target-acquisition",
        attacker_player_id="player-a",
        attacking_unit_instance_id=fixture.shroud.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            _ranged_pool(attacker, fixture.enemy_one, scatter),
            _ranged_pool(attacker, fixture.enemy_two, long_rifle),
        ),
    )
    for pool_index in range(2):
        decisions.event_log.append(
            "attack_sequence_step",
            {
                "sequence_id": sequence.sequence_id,
                "step": AttackSequenceStep.HIT.value,
                "pool_index": pool_index,
                "payload": {"successful": True},
            },
        )

    status = CatalogPostShootHitTargetStatusRuntime(
        fixture.indexes,
        fixture.armies,
    ).request_handler(
        AttackSequenceCompletedContext(
            state=fixture.state,
            decisions=decisions,
            dice_manager=DiceRollManager(fixture.state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id="event:shroud-target-acquisition",
        )
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = decisions.queue.peek_next()
    assert isinstance(request.payload, dict)
    assert request.payload["available_target_unit_instance_ids"] == [
        fixture.enemy_two.unit_instance_id
    ]
    assert len(request.options) == 1
    result = DecisionResult.for_request(
        result_id="result:shroud-target-acquisition",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_status_result(
            state=fixture.state,
            decisions=decisions,
            result=result,
        )
        is None
    )
    effects = fixture.state.persisting_effects_for_unit(fixture.enemy_two.unit_instance_id)
    assert len(effects) == 1
    assert cast(dict[str, Any], effects[0].effect_payload)["status"] == "benefit_of_cover"
    assert fixture.state.persisting_effects_for_unit(fixture.enemy_one.unit_instance_id) == ()


class _RuntimeFixture:
    def __init__(
        self,
        *,
        armies: tuple[ArmyDefinition, ...],
        state: GameState,
        indexes: dict[str, Any],
        shroud: UnitInstance,
        wraith_shields: UnitInstance,
        wraith_swords: UnitInstance,
        psyker: UnitInstance,
        enemy_one: UnitInstance,
        enemy_two: UnitInstance,
    ) -> None:
        self.armies = armies
        self.state = state
        self.indexes = indexes
        self.shroud = shroud
        self.wraith_shields = wraith_shields
        self.wraith_swords = wraith_swords
        self.psyker = psyker
        self.enemy_one = enemy_one
        self.enemy_two = enemy_two
        self.runtime = CatalogDatasheetRuleRuntime(indexes, armies)


def _runtime_fixture() -> _RuntimeFixture:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    shroud = _instantiate(
        factory,
        army_id="army-a",
        selection_id="shroud",
        datasheet_id=SHROUD_RUNNERS_ID,
    )
    wraith_shields = _instantiate(
        factory,
        army_id="army-a",
        selection_id="wraith-shields",
        datasheet_id=WRAITHBLADES_ID,
        wargear_selections=(
            WargearSelection(
                option_id=SHIELD_OPTION_ID,
                model_profile_id=WRAITH_PROFILE_ID,
                wargear_ids=(
                    f"{WRAITHBLADES_ID}:forceshield",
                    f"{WRAITHBLADES_ID}:ghostaxe",
                ),
            ),
        ),
    )
    wraith_swords = _instantiate(
        factory,
        army_id="army-a",
        selection_id="wraith-swords",
        datasheet_id=WRAITHBLADES_ID,
    )
    psyker = replace(
        _instantiate(
            factory,
            army_id="army-a",
            selection_id="psyker",
            datasheet_id=SHROUD_RUNNERS_ID,
        ),
        keywords=("AELDARI", "INFANTRY", "PSYKER"),
    )
    enemy_one = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy-one",
        datasheet_id=WRAITHBLADES_ID,
    )
    enemy_two = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy-two",
        datasheet_id=WRAITHBLADES_ID,
    )
    armies = (
        _army(catalog, "army-a", "player-a", (shroud, wraith_shields, wraith_swords, psyker)),
        _army(catalog, "army-b", "player-b", (enemy_one, enemy_two)),
    )
    state = _state(armies)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return _RuntimeFixture(
        armies=armies,
        state=state,
        indexes=indexes,
        shroud=shroud,
        wraith_shields=wraith_shields,
        wraith_swords=wraith_swords,
        psyker=psyker,
        enemy_one=enemy_one,
        enemy_two=enemy_two,
    )


def _state(armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="aeldari-shroud-wraith-test",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(BattlePhase.SHOOTING),
        battle_round=1,
        active_player_id="player-a",
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
        battlefield_id="aeldari-shroud-wraith-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _army(
    catalog: Any,
    army_id: str,
    player_id: str,
    units: tuple[UnitInstance, ...],
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
        force_disposition_id="purge-the-foe",
        units=units,
    )


def _instantiate(
    factory: UnitFactory,
    *,
    army_id: str,
    selection_id: str,
    datasheet_id: str,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    profile = datasheet.model_profiles[0]
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    profile.model_profile_id, datasheet.composition[0].min_models
                ),
            ),
            wargear_selections=wargear_selections,
        ),
    )


def _static_rule(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _catalog_rule(datasheet_id: str, ability_name: str) -> RuleIR:
    ability = next(
        ability
        for ability in _package().army_catalog.datasheet_by_id(datasheet_id).abilities
        if ability.name == ability_name
    )
    assert ability.rule_ir_payload is not None
    return RuleIR.from_payload(ability.rule_ir_payload)


def _characteristics(datasheet: Any) -> tuple[int, ...]:
    values = {
        value.characteristic: value.final for value in datasheet.model_profiles[0].characteristics
    }
    return (
        values[Characteristic.MOVEMENT],
        values[Characteristic.TOUGHNESS],
        values[Characteristic.SAVE],
        values[Characteristic.WOUNDS],
        values[Characteristic.LEADERSHIP],
        values[Characteristic.OBJECTIVE_CONTROL],
        values[Characteristic.INVULNERABLE_SAVE],
    )


def _weapon_names(datasheet_id: str) -> set[str]:
    return {
        profile.name
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
    }


def _profile(datasheet_id: str, name: str) -> WeaponProfile:
    return cast(
        WeaponProfile,
        next(
            profile
            for wargear in _package().army_catalog.wargear
            if wargear.wargear_id.startswith(f"{datasheet_id}:")
            for profile in wargear.weapon_profiles
            if profile.name == name
        ),
    )


def _invulnerable_target(options: tuple[SaveOption, ...]) -> int | None:
    return next(
        (option.target_number for option in options if option.save_kind is SaveKind.INVULNERABLE),
        None,
    )


def _move_unit(state: GameState, unit_instance_id: str, *, x: float, y: float) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    moved = replace(
        placement,
        model_placements=tuple(
            replace(model, pose=Pose.at(x=x, y=y + (index * 2.0)))
            for index, model in enumerate(placement.model_placements)
        ),
    )
    state.replace_battlefield_state(battlefield.with_unit_placement(moved))


def _ranged_pool(
    attacker: Any,
    target: UnitInstance,
    profile: WeaponProfile,
) -> RangedAttackPool:
    assert profile.range_profile.kind is RangeProfileKind.DISTANCE
    target_ids = target.own_model_ids()
    return RangedAttackPool(
        attacker_model_instance_id=attacker.model_instance_id,
        wargear_id=f"test:{profile.profile_id}:wargear",
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_ids,
        target_in_range_model_ids=target_ids,
    )
