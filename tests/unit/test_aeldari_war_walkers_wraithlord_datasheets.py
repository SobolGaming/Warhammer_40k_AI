from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_war_walkers_wraithlord_rule_ir import (
    CRYSTALLINE_TARGETING_ROW_ID,
    FATED_HERO_ROW_ID,
    OUTPUT_PATH,
    PSYCHIC_GUIDANCE_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
)
from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequenceStep
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import CatalogDatasheetRuleRuntime
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
)
from warhammer40k_core.engine.catalog_start_battle_keyword_choice import (
    CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID,
    CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
)
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
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
    aeldari_war_walkers_wraithlord_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_WAR_WALKERS_WRAITHLORD_HEIGHT_OVERRIDES,
)

WAR_WALKERS_ID = "000000612"
WRAITHLORD_ID = "000000613"
KHARSETH_ID = "000004194"
CORE_ENEMY_ID = "core-intercessor-like-infantry"
TEST_DETACHMENT_ID = "aeldari-war-walkers-wraithlord-test"


@cache
def _package() -> CanonicalCatalogPackage:
    return _ability_support_catalog_package()


def test_generated_rule_ir_artifact_is_current_source_bound_and_fail_fast() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert source_package.supported_datasheet_source_row_ids() == (
        CRYSTALLINE_TARGETING_ROW_ID,
        FATED_HERO_ROW_ID,
        PSYCHIC_GUIDANCE_ROW_ID,
    )
    assert committed["package_hash"] == source_package.PACKAGE_HASH

    committed["package_hash"] = "0" * 64
    with pytest.raises(
        source_package.AeldariWarWalkersWraithlordRuleIrArtifactError,
        match="hash is stale",
    ):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_exact_rules_have_source_linked_generic_consumers() -> None:
    crystalline = _rule_ir(CRYSTALLINE_TARGETING_ROW_ID)
    fated = _rule_ir(FATED_HERO_ROW_ID)
    psychic = _rule_ir(PSYCHIC_GUIDANCE_ROW_ID)

    assert catalog_rule_ir_consumers_for_rule(crystalline) == (
        "catalog-ir:post-shoot-hit-target-effect",
    )
    assert catalog_rule_ir_consumers_for_rule(fated) == (
        CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_START_BATTLE_KEYWORD_CHOICE_CONSUMER_ID,
        CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(psychic) == (
        "catalog-ir:ballistic-skill-characteristic-modifier",
        "catalog-ir:leadership-characteristic-query",
        "catalog-ir:weapon-skill-characteristic-modifier",
    )

    selection, effect = crystalline.clauses
    assert selection.trigger is not None
    assert selection.trigger.kind is RuleTriggerKind.TIMING_WINDOW
    assert selection.target is not None
    assert selection.target.kind is RuleTargetKind.ENEMY_UNIT
    assert len(selection.conditions) == 1
    assert selection.conditions[0].kind is RuleConditionKind.FREQUENCY_LIMIT
    assert parameter_payload(selection.conditions[0].parameters) == {
        "maximum_uses": 1,
        "scope": "turn",
        "subject": "selected_target_unit",
    }
    assert effect.target is not None
    assert effect.target.kind is RuleTargetKind.FRIENDLY_UNIT
    assert parameter_payload(effect.target.parameters) == {
        "allegiance": "friendly",
        "required_keyword": "AELDARI",
    }
    assert effect.conditions[0].kind is RuleConditionKind.TARGET_CONSTRAINT
    assert parameter_payload(effect.effects[0].parameters) == {
        "attack_role": "attacker",
        "characteristic": Characteristic.ARMOR_PENETRATION.value,
        "delta": -1,
    }
    assert effect.duration is not None
    assert effect.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT

    fated_clause = fated.clauses[0]
    assert fated_clause.trigger is not None
    assert parameter_payload(fated_clause.trigger.parameters)["keyword_options"] == (
        "INFANTRY",
        "MONSTER",
        "MOUNTED",
        "VEHICLE",
    )
    assert tuple(effect.kind for effect in fated_clause.effects) == (
        RuleEffectKind.REROLL_PERMISSION,
        RuleEffectKind.REROLL_PERMISSION,
    )
    assert fated_clause.duration is not None
    assert fated_clause.duration.kind is RuleDurationKind.PERMANENT


def test_catalog_preserves_stats_geometry_abilities_and_wargear() -> None:
    catalog = _package().army_catalog
    walkers = catalog.datasheet_by_id(WAR_WALKERS_ID)
    wraithlord = catalog.datasheet_by_id(WRAITHLORD_ID)

    assert _characteristics(walkers) == (10, 7, 3, 6, 7, 2, 5)
    assert walkers.model_profiles[0].base_size.diameter_mm == 60.0
    assert walkers.keywords.keywords == ("AELDARI", "VEHICLE", "WALKER", "WAR WALKERS")
    assert (walkers.composition[0].min_models, walkers.composition[0].max_models) == (1, 2)
    assert {ability.name for ability in walkers.abilities} == {
        "Battle Focus",
        "Crystalline Targeting",
        "Scouts",
    }
    assert _weapon_names(WAR_WALKERS_ID) == {
        "Bright lance",
        "Missile launcher - starshot",
        "Missile launcher - sunburst",
        "Scatter laser",
        "Shuriken cannon",
        "Starcannon",
        "War Walker feet",
    }

    assert _characteristics(wraithlord) == (8, 10, 2, 10, 8, 3, 0)
    assert wraithlord.model_profiles[0].base_size.diameter_mm == 60.0
    assert wraithlord.keywords.keywords == (
        "AELDARI",
        "MONSTER",
        "WALKER",
        "WRAITH CONSTRUCT",
        "WRAITHLORD",
    )
    assert (wraithlord.composition[0].min_models, wraithlord.composition[0].max_models) == (1, 1)
    assert {ability.name for ability in wraithlord.abilities} == {
        "Deadly Demise",
        "Fated Hero",
        "Psychic Guidance",
    }
    assert _weapon_names(WRAITHLORD_ID) == {
        "Bright lance",
        "Flamer",
        "Ghostglaive - strike",
        "Ghostglaive - sweep",
        "Missile launcher - starshot",
        "Missile launcher - sunburst",
        "Scatter laser",
        "Shuriken cannon",
        "Shuriken catapult",
        "Starcannon",
        "Wraithbone fists",
    }
    assert {
        (row.datasheet_id, row.model_name, row.height)
        for row in AELDARI_WAR_WALKERS_WRAITHLORD_HEIGHT_OVERRIDES
    } == {
        (WAR_WALKERS_ID, "War Walkers", 3.25),
        (WRAITHLORD_ID, "Wraithlord", 4.75),
    }


def test_repeated_default_weapons_and_all_source_options_resolve_per_model() -> None:
    package = _package()
    factory = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    )
    walkers_datasheet = package.army_catalog.datasheet_by_id(WAR_WALKERS_ID)
    walkers_profile_id = walkers_datasheet.model_profiles[0].model_profile_id
    walkers = factory.instantiate_unit(
        army_id="army-wargear",
        datasheet=walkers_datasheet,
        selection=UnitMusterSelection(
            unit_selection_id="walkers-bright-lances",
            datasheet_id=WAR_WALKERS_ID,
            model_profile_selections=(ModelProfileSelection(walkers_profile_id, 1),),
            wargear_selections=(
                WargearSelection(
                    option_id=(f"{WAR_WALKERS_ID}:shuriken-cannon-bright-lance:option-1"),
                    model_profile_id=walkers_profile_id,
                    wargear_ids=(f"{WAR_WALKERS_ID}:bright-lance",),
                    selection_count=2,
                ),
            ),
        ),
    )
    assert walkers.own_models[0].wargear_ids.count(f"{WAR_WALKERS_ID}:bright-lance") == 2
    assert f"{WAR_WALKERS_ID}:shuriken-cannon" not in walkers.own_models[0].wargear_ids

    wraithlord_datasheet = package.army_catalog.datasheet_by_id(WRAITHLORD_ID)
    wraithlord_profile_id = wraithlord_datasheet.model_profiles[0].model_profile_id
    wraithlord = factory.instantiate_unit(
        army_id="army-wargear",
        datasheet=wraithlord_datasheet,
        selection=UnitMusterSelection(
            unit_selection_id="wraithlord-options",
            datasheet_id=WRAITHLORD_ID,
            model_profile_selections=(ModelProfileSelection(wraithlord_profile_id, 1),),
            wargear_selections=(
                WargearSelection(
                    option_id=(f"{WRAITHLORD_ID}:shuriken-catapults-flamer:option-1"),
                    model_profile_id=wraithlord_profile_id,
                    wargear_ids=(f"{WRAITHLORD_ID}:flamer",),
                    selection_count=2,
                ),
                WargearSelection(
                    option_id=f"{WRAITHLORD_ID}:ghostglaive:option-2",
                    model_profile_id=wraithlord_profile_id,
                    wargear_ids=(f"{WRAITHLORD_ID}:ghostglaive",),
                ),
                WargearSelection(
                    option_id=f"{WRAITHLORD_ID}:additive-choice:option-3",
                    model_profile_id=wraithlord_profile_id,
                    wargear_ids=(
                        f"{WRAITHLORD_ID}:bright-lance",
                        f"{WRAITHLORD_ID}:starcannon",
                    ),
                ),
            ),
        ),
    )
    equipped = wraithlord.own_models[0].wargear_ids
    assert equipped.count(f"{WRAITHLORD_ID}:flamer") == 2
    assert f"{WRAITHLORD_ID}:shuriken-catapult" not in equipped
    assert {
        f"{WRAITHLORD_ID}:ghostglaive",
        f"{WRAITHLORD_ID}:bright-lance",
        f"{WRAITHLORD_ID}:starcannon",
    }.issubset(equipped)


def test_crystalline_targeting_uses_hit_target_choice_and_scopes_ap_modifier() -> None:
    fixture = _runtime_fixture()
    decisions = DecisionController()
    attacker = fixture.walkers.own_models[0]
    profile = _profile(WAR_WALKERS_ID, "Bright lance")
    sequence = AttackSequence(
        sequence_id="attack-sequence:crystalline-targeting",
        attacker_player_id="player-a",
        attacking_unit_instance_id=fixture.walkers.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            _ranged_pool(attacker, fixture.enemy_one, profile),
            _ranged_pool(attacker, fixture.enemy_two, profile),
        ),
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 1,
            "payload": {"successful": False},
        },
    )

    status = CatalogSelectedTargetEffectRuntime(
        fixture.indexes,
        fixture.armies,
    ).post_shoot_hit_target_request(
        AttackSequenceCompletedContext(
            state=fixture.state,
            decisions=decisions,
            dice_manager=DiceRollManager(fixture.state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id="event:crystalline-targeting",
        )
    )

    assert status is not None
    request = decisions.queue.peek_next()
    assert len(request.options) == 1
    assert cast(dict[str, Any], request.payload)["available_target_unit_instance_ids"] == [
        fixture.enemy_one.unit_instance_id
    ]
    result = DecisionResult.for_request(
        result_id="result:crystalline-targeting",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=fixture.state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=fixture.indexes,
        )
        is None
    )

    registry = RuntimeModifierRegistry.empty()
    friendly_profile = _profile(WRAITHLORD_ID, "Bright lance")
    selected = registry.modified_weapon_profile(
        _weapon_context(
            fixture,
            profile=friendly_profile,
            target=fixture.enemy_one,
        )
    )
    unselected = registry.modified_weapon_profile(
        _weapon_context(
            fixture,
            profile=friendly_profile,
            target=fixture.enemy_two,
        )
    )
    assert selected.armor_penetration.final == friendly_profile.armor_penetration.final - 1
    assert unselected.armor_penetration.final == friendly_profile.armor_penetration.final

    repeat_sequence = AttackSequence(
        sequence_id="attack-sequence:crystalline-targeting-repeat",
        attacker_player_id="player-a",
        attacking_unit_instance_id=fixture.walkers.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(_ranged_pool(attacker, fixture.enemy_one, profile),),
    )
    decisions.event_log.append(
        "attack_sequence_step",
        {
            "sequence_id": repeat_sequence.sequence_id,
            "step": AttackSequenceStep.HIT.value,
            "pool_index": 0,
            "payload": {"successful": True},
        },
    )
    assert (
        CatalogSelectedTargetEffectRuntime(
            fixture.indexes,
            fixture.armies,
        ).post_shoot_hit_target_request(
            AttackSequenceCompletedContext(
                state=fixture.state,
                decisions=decisions,
                dice_manager=DiceRollManager(
                    fixture.state.game_id,
                    event_log=decisions.event_log,
                ),
                runtime_modifier_registry=RuntimeModifierRegistry.empty(),
                source_phase=BattlePhase.SHOOTING,
                attack_sequence=repeat_sequence,
                attack_sequence_completed_event_id="event:crystalline-targeting-repeat",
            )
        )
        is None
    )


def test_wraithlord_psychic_guidance_modifies_live_weapon_skills_and_leadership() -> None:
    fixture = _runtime_fixture()
    runtime = CatalogDatasheetRuleRuntime(fixture.indexes, fixture.armies)
    registry = RuntimeModifierRegistry.from_bindings(
        unit_characteristic_modifier_bindings=runtime.unit_characteristic_modifier_bindings(),
        weapon_profile_modifier_bindings=runtime.weapon_profile_modifier_bindings(),
    )
    _move_unit(fixture.state, fixture.wraithlord.unit_instance_id, x=10.0, y=10.0)
    _move_unit(fixture.state, fixture.psyker.unit_instance_id, x=20.0, y=10.0)

    assert (
        registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=fixture.state,
                unit_instance_id=fixture.wraithlord.unit_instance_id,
                characteristic=Characteristic.LEADERSHIP,
                base_value=8,
                current_value=8,
            )
        )
        == 6
    )
    bright_lance = _profile(WRAITHLORD_ID, "Bright lance")
    fists = _profile(WRAITHLORD_ID, "Wraithbone fists")
    assert (
        registry.modified_weapon_profile(
            _weapon_context(fixture, profile=bright_lance, target=fixture.enemy_one)
        ).skill.final
        == 3
    )
    assert (
        registry.modified_weapon_profile(
            _weapon_context(fixture, profile=fists, target=fixture.enemy_one)
        ).skill.final
        == 3
    )

    _move_unit(fixture.state, fixture.psyker.unit_instance_id, x=30.0, y=10.0)
    assert (
        registry.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=fixture.state,
                unit_instance_id=fixture.wraithlord.unit_instance_id,
                characteristic=Characteristic.LEADERSHIP,
                base_value=8,
                current_value=8,
            )
        )
        == 8
    )
    assert (
        registry.modified_weapon_profile(
            _weapon_context(fixture, profile=bright_lance, target=fixture.enemy_one)
        ).skill.final
        == 4
    )


def test_fated_hero_finite_setup_choice_round_trips_and_gates_both_rerolls() -> None:
    lifecycle = GameLifecycle()
    status = lifecycle.start(_fated_hero_config())
    request = _advance_to_fated_hero_request(lifecycle, status)
    assert request.decision_type == "select_faction_rule_setup_option"
    assert cast(dict[str, Any], request.payload)["submission_kind"] == (
        "catalog_start_battle_keyword_choice"
    )
    infantry_option = next(
        option
        for option in request.options
        if cast(dict[str, Any], option.payload)["selected_keyword"] == "INFANTRY"
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=infantry_option.option_id,
        result_id="result:fated-hero-infantry",
    ).to_result(request)
    lifecycle.submit_decision(result)

    state = lifecycle.state
    assert state is not None
    selected_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == CATALOG_START_BATTLE_KEYWORD_SELECTED_EVENT
    )
    assert len(selected_events) == 1
    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert restored.to_payload() == state.to_payload()
    army = next(army for army in state.army_definitions if army.player_id == "player-a")
    wraithlord = next(unit for unit in army.units if unit.datasheet_id == WRAITHLORD_ID)
    enemy_army = next(army for army in state.army_definitions if army.player_id == "player-b")
    infantry = enemy_army.units[0]
    model_id = wraithlord.own_models[0].model_instance_id
    for roll_type in ("attack_sequence.hit", "attack_sequence.wound"):
        permission = generic_rule_reroll_permission_context_for_unit(
            state=state,
            player_id="player-a",
            unit_instance_id=wraithlord.unit_instance_id,
            model_instance_id=model_id,
            roll_type=roll_type,
            timing_window=roll_type,
            target_unit_instance_id=infantry.unit_instance_id,
        )
        assert permission is not None
        conditional_key = (
            "conditional_hit_reroll" if roll_type.endswith("hit") else "conditional_wound_reroll"
        )
        assert cast(dict[str, Any], permission.source_payload)[conditional_key] == {
            "reroll_unmodified_values": [1]
        }


def test_fated_hero_rejects_option_payload_drift_before_state_mutation() -> None:
    lifecycle = GameLifecycle()
    status = lifecycle.start(_fated_hero_config())
    request = _advance_to_fated_hero_request(lifecycle, status)
    option = request.options[0]
    drifted_payload = dict(cast(dict[str, Any], option.payload))
    drifted_payload["selected_keyword"] = "TITANIC"
    invalid = lifecycle.submit_decision(
        DecisionResult(
            result_id="result:fated-hero-drift",
            request_id=request.request_id,
            decision_type=request.decision_type,
            actor_id=request.actor_id,
            selected_option_id=option.option_id,
            payload=drifted_payload,
        )
    )

    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(invalid.payload, dict)
    assert invalid.payload["invalid_reason"] == "invalid_faction_rule_setup_option_result"
    assert invalid.payload["field"] == "payload"
    assert lifecycle.decision_controller.queue.peek_next() == request
    assert lifecycle.state is not None
    assert lifecycle.state.persisting_effects == []


class _RuntimeFixture:
    def __init__(
        self,
        *,
        armies: tuple[ArmyDefinition, ...],
        state: GameState,
        indexes: dict[str, Any],
        walkers: UnitInstance,
        wraithlord: UnitInstance,
        psyker: UnitInstance,
        enemy_one: UnitInstance,
        enemy_two: UnitInstance,
    ) -> None:
        self.armies = armies
        self.state = state
        self.indexes = indexes
        self.walkers = walkers
        self.wraithlord = wraithlord
        self.psyker = psyker
        self.enemy_one = enemy_one
        self.enemy_two = enemy_two


def _runtime_fixture() -> _RuntimeFixture:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    walkers = _instantiate(
        factory, army_id="army-a", selection_id="walkers", datasheet_id=WAR_WALKERS_ID
    )
    wraithlord = _instantiate(
        factory,
        army_id="army-a",
        selection_id="wraithlord",
        datasheet_id=WRAITHLORD_ID,
    )
    psyker = _instantiate(
        factory, army_id="army-a", selection_id="psyker", datasheet_id=KHARSETH_ID
    )
    enemy_one = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy-one",
        datasheet_id=WRAITHLORD_ID,
    )
    enemy_two = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy-two",
        datasheet_id=WRAITHLORD_ID,
    )
    armies = (
        _army(catalog, "army-a", "player-a", (walkers, wraithlord, psyker)),
        _army(catalog, "army-b", "player-b", (enemy_one, enemy_two)),
    )
    state = _battle_state(armies)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return _RuntimeFixture(
        armies=armies,
        state=state,
        indexes=indexes,
        walkers=walkers,
        wraithlord=wraithlord,
        psyker=psyker,
        enemy_one=enemy_one,
        enemy_two=enemy_two,
    )


def _battle_state(armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="aeldari-war-walkers-wraithlord-test",
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
        mission_setup=_mission_setup(),
    )
    for army in armies:
        state.record_army_definition(army)
    state.battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="aeldari-war-walkers-wraithlord-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _army(
    catalog: Any, army_id: str, player_id: str, units: tuple[UnitInstance, ...]
) -> ArmyDefinition:
    return ArmyDefinition(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="AE",
            detachment_ids=(TEST_DETACHMENT_ID,),
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
        ),
    )


def _fated_hero_config() -> GameConfig:
    catalog = _fated_hero_catalog()
    return GameConfig(
        game_id="aeldari-fated-hero-lifecycle",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-aeldari-fated-hero-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _muster_request(
                catalog,
                army_id="army-a",
                player_id="player-a",
                faction_id="AE",
                detachment_id=TEST_DETACHMENT_ID,
                datasheet_id=WRAITHLORD_ID,
                selection_id="fated-wraithlord",
            ),
            _muster_request(
                catalog,
                army_id="army-b",
                player_id="player-b",
                faction_id="core-marine-force",
                detachment_id="core-combined-arms",
                datasheet_id=CORE_ENEMY_ID,
                selection_id="enemy-infantry",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down"),
        mission_setup=_mission_setup(),
    )


@cache
def _fated_hero_catalog() -> ArmyCatalog:
    generated = _package().army_catalog
    base = ArmyCatalog.phase9a_canonical_content_pack()
    datasheets = tuple(
        generated.datasheet_by_id(datasheet_id) for datasheet_id in (WAR_WALKERS_ID, WRAITHLORD_ID)
    )
    linked_wargear_ids = {
        wargear_id
        for datasheet in datasheets
        for option in datasheet.wargear_options
        for wargear_id in (*option.default_wargear_ids, *option.allowed_wargear_ids)
    }
    wargear = tuple(item for item in generated.wargear if item.wargear_id in linked_wargear_ids)
    return ArmyCatalog(
        catalog_id="aeldari-war-walkers-wraithlord-lifecycle-test",
        ruleset_id=base.ruleset_id,
        source_package_id="data-package:core-v2:aeldari-war-walkers-wraithlord-test",
        datasheets=(*base.datasheets, *datasheets),
        wargear=(*base.wargear, *wargear),
        factions=(
            *base.factions,
            FactionDefinition(
                faction_id="AE",
                name="Aeldari",
                faction_keywords=("ASURYANI",),
                source_ids=("source:aeldari-war-walkers-wraithlord-test",),
            ),
        ),
        army_rules=base.army_rules,
        detachments=(
            *base.detachments,
            DetachmentDefinition(
                detachment_id=TEST_DETACHMENT_ID,
                name="War Walkers and Wraithlord Test",
                faction_id="AE",
                detachment_point_cost=1,
                unit_datasheet_ids=(WAR_WALKERS_ID, WRAITHLORD_ID),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("source:aeldari-war-walkers-wraithlord-test",),
            ),
        ),
        enhancements=base.enhancements,
        stratagems=base.stratagems,
        source_ids=(generated.source_package_id,),
    )


def _muster_request(
    catalog: Any,
    *,
    army_id: str,
    player_id: str,
    faction_id: str,
    detachment_id: str,
    datasheet_id: str,
    selection_id: str,
) -> ArmyMusterRequest:
    datasheet = catalog.datasheet_by_id(datasheet_id)
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id=faction_id,
            detachment_ids=(detachment_id,),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        datasheet.model_profiles[0].model_profile_id,
                        datasheet.composition[0].min_models,
                    ),
                ),
            ),
        ),
    )


def _advance_to_fated_hero_request(lifecycle: GameLifecycle, status: Any) -> Any:
    while True:
        request = status.decision_request
        if request is not None:
            if request.decision_type == "select_faction_rule_setup_option":
                return request
            assert request.decision_type == "select_secondary_missions"
            status = lifecycle.submit_decision(
                DecisionResult.for_request(
                    result_id=f"result:{request.actor_id}:fixed-secondaries",
                    request=request,
                    selected_option_id="fixed:assassination:bring_it_down",
                )
            )
            continue
        assert status.status_kind is not LifecycleStatusKind.INVALID, status.payload
        status = lifecycle.advance_until_decision_or_terminal()


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


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
    return next(
        profile
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if profile.name == name
    )


def _ranged_pool(attacker: Any, target: UnitInstance, profile: WeaponProfile) -> RangedAttackPool:
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


def _weapon_context(
    fixture: _RuntimeFixture,
    *,
    profile: WeaponProfile,
    target: UnitInstance,
) -> WeaponProfileModifierContext:
    return WeaponProfileModifierContext(
        state=fixture.state,
        source_phase=BattlePhase.SHOOTING
        if profile.range_profile.kind is RangeProfileKind.DISTANCE
        else BattlePhase.FIGHT,
        attacking_unit_instance_id=fixture.wraithlord.unit_instance_id,
        attacker_model_instance_id=fixture.wraithlord.own_models[0].model_instance_id,
        target_unit_instance_id=target.unit_instance_id,
        weapon_profile=profile,
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
