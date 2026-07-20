from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_night_spinner_rule_ir import (
    MONOFILAMENT_WEB_ROW_ID,
    OUTPUT_PATH,
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
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    CatalogSelectedTargetEffectRuntime,
    apply_catalog_post_shoot_hit_target_effect_result,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    selected_target_persisting_effect_clause_is_supported,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpirationBoundary, EffectExpirationKind
from warhammer40k_core.engine.game_state import GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    ChargeRollModifierContext,
    MovementBudgetModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
    WargearSelection,
)
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import (
    RuleDurationKind,
    RuleEffectKind,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_night_spinner_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_NIGHT_SPINNER_HEIGHT_OVERRIDES,
)

NIGHT_SPINNER_ID = "000000611"
TEST_DETACHMENT_ID = "aeldari-night-spinner-test"


@cache
def _package() -> CanonicalCatalogPackage:
    return _ability_support_catalog_package()


def test_generated_rule_ir_artifact_is_current_source_bound_and_fail_fast() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert source_package.supported_datasheet_source_row_ids() == (MONOFILAMENT_WEB_ROW_ID,)
    assert committed["package_hash"] == source_package.PACKAGE_HASH

    committed["package_hash"] = "0" * 64
    with pytest.raises(source_package.NightSpinnerRuleIrArtifactError, match="hash is stale"):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_night_spinner_catalog_preserves_complete_datasheet_and_rule_semantics() -> None:
    package = _package()
    datasheet = package.army_catalog.datasheet_by_id(NIGHT_SPINNER_ID)
    values = {
        value.characteristic: value.final for value in datasheet.model_profiles[0].characteristics
    }

    assert (
        values[Characteristic.MOVEMENT],
        values[Characteristic.TOUGHNESS],
        values[Characteristic.SAVE],
        values[Characteristic.WOUNDS],
        values[Characteristic.LEADERSHIP],
        values[Characteristic.OBJECTIVE_CONTROL],
    ) == (14, 9, 3, 12, 7, 3)
    assert datasheet.model_profiles[0].base_size.diameter_mm == 60.0
    assert datasheet.keywords.keywords == ("AELDARI", "FLY", "NIGHT SPINNER", "VEHICLE")
    assert datasheet.keywords.faction_keywords == ("ASURYANI",)
    assert {ability.name for ability in datasheet.abilities} == {
        "Battle Focus",
        "Deadly Demise",
        "Monofilament Web",
    }
    assert {_profile_summary(profile) for profile in _profiles()} == {
        (48, "D6+3", 3, 7, -1, "2", ("Blast", "Indirect Fire", "Twin-linked")),
        (24, "3", 3, 6, -1, "2", ("Lethal Hits",)),
        (18, "2", 3, 4, -1, "1", ("Assault", "Twin-linked")),
        ("melee", "3", 4, 6, 0, "1", ()),
    }
    assert {
        (row.datasheet_id, row.model_name, row.height, row.height_source_id)
        for row in AELDARI_NIGHT_SPINNER_HEIGHT_OVERRIDES
    } == {
        (
            NIGHT_SPINNER_ID,
            "Night Spinner",
            2.75,
            "geometry-review:aeldari:night-spinner:height",
        )
    }

    rule = _rule_ir()
    assert catalog_rule_ir_consumers_for_rule(rule) == (
        CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID,
    )
    selection, movement, charge = rule.clauses
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
        "weapon_names": ("Doomweaver",),
    }
    assert movement.target is not None
    assert movement.target.kind is RuleTargetKind.SELECTED_UNIT
    assert movement.effects[0].kind is RuleEffectKind.MODIFY_CHARACTERISTIC
    assert parameter_payload(movement.effects[0].parameters) == {
        "characteristic": Characteristic.MOVEMENT.value,
        "delta": -2,
    }
    assert charge.target is not None
    assert charge.target.kind is RuleTargetKind.SELECTED_UNIT
    assert charge.effects[0].kind is RuleEffectKind.MODIFY_DICE_ROLL
    assert parameter_payload(charge.effects[0].parameters) == {
        "delta": -2,
        "roll_type": "charge",
    }
    assert movement.duration is not None
    assert charge.duration is not None
    assert movement.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert charge.duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
    assert selected_target_persisting_effect_clause_is_supported(movement)
    assert selected_target_persisting_effect_clause_is_supported(charge)


def test_night_spinner_wargear_replacement_round_trips_through_real_unit_factory() -> None:
    package = _package()
    factory = UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    )
    datasheet = package.army_catalog.datasheet_by_id(NIGHT_SPINNER_ID)
    profile_id = datasheet.model_profiles[0].model_profile_id
    selection = UnitMusterSelection(
        unit_selection_id="night-spinner-with-cannon",
        datasheet_id=NIGHT_SPINNER_ID,
        model_profile_selections=(ModelProfileSelection(profile_id, 1),),
        wargear_selections=(
            WargearSelection(
                option_id=f"{NIGHT_SPINNER_ID}:shuriken-cannon:option-1",
                model_profile_id=profile_id,
                wargear_ids=(f"{NIGHT_SPINNER_ID}:shuriken-cannon",),
            ),
        ),
    )

    restored_selection = UnitMusterSelection.from_payload(
        json.loads(json.dumps(selection.to_payload()))
    )
    unit = factory.instantiate_unit(
        army_id="army-a",
        datasheet=datasheet,
        selection=restored_selection,
    )

    assert set(unit.own_models[0].wargear_ids) == {
        f"{NIGHT_SPINNER_ID}:doomweaver",
        f"{NIGHT_SPINNER_ID}:shuriken-cannon",
        f"{NIGHT_SPINNER_ID}:wraithbone-hull",
    }


def test_monofilament_web_pins_only_doomweaver_hit_target_until_next_turn() -> None:
    armies, state, indexes, night_spinner, enemy_one, enemy_two = _runtime_fixture()
    decisions = DecisionController()
    attacker = night_spinner.own_models[0]
    sequence = AttackSequence(
        sequence_id="attack-sequence:monofilament-web",
        attacker_player_id="player-a",
        attacking_unit_instance_id=night_spinner.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(
            _ranged_pool(attacker, enemy_one, _profile("Doomweaver")),
            _ranged_pool(attacker, enemy_two, _profile("Shuriken cannon")),
        ),
    )
    for pool_index in (0, 1):
        decisions.event_log.append(
            "attack_sequence_step",
            {
                "sequence_id": sequence.sequence_id,
                "step": AttackSequenceStep.HIT.value,
                "pool_index": pool_index,
                "payload": {"successful": True},
            },
        )

    status = CatalogSelectedTargetEffectRuntime(indexes, armies).post_shoot_hit_target_request(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=sequence,
            attack_sequence_completed_event_id="event:monofilament-web",
        )
    )

    assert status is not None
    request = decisions.queue.peek_next()
    assert cast(dict[str, Any], request.payload)["available_target_unit_instance_ids"] == [
        enemy_one.unit_instance_id
    ]
    assert len(request.options) == 1
    result = DecisionResult.for_request(
        result_id="result:monofilament-web",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_post_shoot_hit_target_effect_result(
            state=state,
            decisions=decisions,
            result=result,
            battle_shock_hooks=BattleShockHookRegistry.empty(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            ability_indexes_by_player_id=indexes,
        )
        is None
    )

    assert len(state.persisting_effects) == 2
    source_id = next(
        ability.source_id
        for ability in _package().army_catalog.datasheet_by_id(NIGHT_SPINNER_ID).abilities
        if ability.name == "Monofilament Web"
    )
    for effect in state.persisting_effects:
        assert effect.source_rule_id == source_id
        assert effect.target_unit_instance_ids == (enemy_one.unit_instance_id,)
        assert effect.expiration.expiration_kind is EffectExpirationKind.START_TURN
        assert effect.expiration.battle_round == 2
        assert effect.expiration.player_id == "player-a"
        payload = cast(dict[str, Any], effect.effect_payload)
        effect_payload = cast(dict[str, Any], payload["effect"])
        parameters = {
            parameter["key"]: parameter["value"]
            for parameter in cast(list[dict[str, Any]], effect_payload["parameters"])
        }
        assert "attack_role" not in parameters
        assert "weapon_scope" not in parameters
        assert parameters["selected_target_unit_instance_id"] == enemy_one.unit_instance_id

    registry = RuntimeModifierRegistry.empty()
    assert registry.modified_movement_inches(_movement_context(state, enemy_one)) == 12.0
    assert registry.modified_movement_inches(_movement_context(state, enemy_two)) == 14.0
    charge_modifiers = registry.charge_roll_modifiers(
        ChargeRollModifierContext(
            state=state,
            unit_instance_id=enemy_one.unit_instance_id,
            current_roll_modifiers=(),
        )
    )
    assert tuple(modifier.operand for modifier in charge_modifiers) == (-2,)
    assert (
        registry.charge_roll_modifiers(
            ChargeRollModifierContext(
                state=state,
                unit_instance_id=enemy_two.unit_instance_id,
                current_roll_modifiers=(),
            )
        )
        == ()
    )

    for effect in tuple(state.persisting_effects):
        state.record_persisting_effect(replace(effect, effect_id=f"{effect.effect_id}:reapplied"))
    assert len(state.persisting_effects) == 4
    assert registry.modified_movement_inches(_movement_context(state, enemy_one)) == 12.0
    assert tuple(
        modifier.operand
        for modifier in registry.charge_roll_modifiers(
            ChargeRollModifierContext(
                state=state,
                unit_instance_id=enemy_one.unit_instance_id,
                current_roll_modifiers=(),
            )
        )
    ) == (-2,)

    restored = GameState.from_payload(
        cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    )
    assert registry.modified_movement_inches(_movement_context(restored, enemy_one)) == 12.0
    assert tuple(
        modifier.operand
        for modifier in registry.charge_roll_modifiers(
            ChargeRollModifierContext(
                state=restored,
                unit_instance_id=enemy_one.unit_instance_id,
                current_roll_modifiers=(),
            )
        )
    ) == (-2,)
    expired = restored.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_start(battle_round=2, player_id="player-a")
    )
    assert len(expired) == 4
    assert registry.modified_movement_inches(_movement_context(restored, enemy_one)) == 14.0


def _runtime_fixture() -> tuple[
    tuple[ArmyDefinition, ...],
    GameState,
    dict[str, Any],
    UnitInstance,
    UnitInstance,
    UnitInstance,
]:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    night_spinner = _instantiate(factory, "army-a", "night-spinner")
    enemy_one = _instantiate(factory, "army-b", "enemy-one")
    enemy_two = _instantiate(factory, "army-b", "enemy-two")
    armies = (
        _army(catalog, "army-a", "player-a", (night_spinner,)),
        _army(catalog, "army-b", "player-b", (enemy_one, enemy_two)),
    )
    state = _battle_state(armies)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return armies, state, indexes, night_spinner, enemy_one, enemy_two


def _battle_state(armies: tuple[ArmyDefinition, ...]) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="aeldari-night-spinner-test",
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
        battlefield_id="aeldari-night-spinner-battlefield",
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
            detachment_ids=(TEST_DETACHMENT_ID,),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
    )


def _instantiate(factory: UnitFactory, army_id: str, selection_id: str) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(NIGHT_SPINNER_ID)
    model_profile = datasheet.model_profiles[0]
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=NIGHT_SPINNER_ID,
            model_profile_selections=(ModelProfileSelection(model_profile.model_profile_id, 1),),
        ),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _rule_ir() -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(MONOFILAMENT_WEB_ROW_ID)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _profiles() -> tuple[WeaponProfile, ...]:
    return tuple(
        profile
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{NIGHT_SPINNER_ID}:")
        for profile in wargear.weapon_profiles
    )


def _profile(name: str) -> WeaponProfile:
    return next(profile for profile in _profiles() if profile.name == name)


def _profile_summary(
    profile: WeaponProfile,
) -> tuple[object, str, int, int, int, str, tuple[str, ...]]:
    range_value: object = (
        "melee"
        if profile.range_profile.kind is RangeProfileKind.MELEE
        else profile.range_profile.distance_inches
    )
    if profile.attack_profile.fixed_attacks is not None:
        attacks = str(profile.attack_profile.fixed_attacks)
    else:
        assert profile.attack_profile.dice_expression is not None
        attacks = profile.attack_profile.dice_expression.canonical()
    if profile.damage_profile.fixed_damage is not None:
        damage = str(profile.damage_profile.fixed_damage)
    else:
        assert profile.damage_profile.dice_expression is not None
        damage = profile.damage_profile.dice_expression.canonical()
    return (
        range_value,
        attacks,
        profile.skill.final,
        profile.strength.final,
        profile.armor_penetration.final,
        damage,
        tuple(keyword.value for keyword in profile.keywords),
    )


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


def _movement_context(state: GameState, unit: UnitInstance) -> MovementBudgetModifierContext:
    return MovementBudgetModifierContext(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        model_instance_id=unit.own_models[0].model_instance_id,
        base_movement_inches=14.0,
        current_movement_inches=14.0,
    )
