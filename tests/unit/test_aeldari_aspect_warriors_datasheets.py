from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_aspect_warriors_rule_ir import (
    ASSURED_DESTRUCTION_ROW_ID,
    FLICKERJUMP_ROW_ID,
    GRENADE_PACK_FLYOVER_ROW_ID,
    OUTPUT_PATH,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollState,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import RangeProfileKind, WeaponProfile
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext, AdvanceMoveHookRegistry
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.attack_sequence import (
    _request_source_backed_damage_reroll_if_available,
    _request_source_backed_hit_reroll_if_available,
    _request_source_backed_wound_reroll_if_available,
)
from warhammer40k_core.engine.catalog_datasheet_rule_runtime import (
    CatalogDatasheetRuleRuntime,
    _rules_unit_has_any_keyword,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.engine.catalog_datasheet_rule_support import (
    CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
    CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.catalog_unit_move_completed_mortal_wounds_runtime import (
    CatalogUnitMoveCompletedMortalWoundsRuntime,
    apply_catalog_unit_move_completed_mortal_wounds_target_result,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_phase_end_mortal_wounds import (
    MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT,
    MOVEMENT_PHASE_END_MORTAL_WOUNDS_ROLLED_EVENT,
    resolve_movement_phase_end_mortal_wounds,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import MovementPhaseHandler
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    AttackRerollPermissionContext,
    MovementBudgetModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_effect_payload,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT,
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_mortal_wound_hooks,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_aspect_warriors_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_ASPECT_WARRIORS_HEIGHT_OVERRIDES,
)

FIRE_DRAGONS_ID = "000000596"
SWOOPING_HAWKS_ID = "000000600"
WARP_SPIDERS_ID = "000000601"
WRAITHLORD_ID = "000000613"
PRINCE_YRIEL_ID = "000004193"


@cache
def _package() -> Any:
    return _ability_support_catalog_package()


def test_generated_rule_ir_artifact_is_current_source_bound_and_fail_fast() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert source_package.supported_datasheet_source_row_ids() == (
        ASSURED_DESTRUCTION_ROW_ID,
        GRENADE_PACK_FLYOVER_ROW_ID,
        FLICKERJUMP_ROW_ID,
    )
    assert committed["package_hash"] == source_package.PACKAGE_HASH

    committed["package_hash"] = "0" * 64
    with pytest.raises(
        source_package.AeldariAspectWarriorsRuleIrArtifactError,
        match="hash is stale",
    ):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_exact_rules_have_source_linked_generic_consumers() -> None:
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(ASSURED_DESTRUCTION_ROW_ID)) == (
        CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
        CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(GRENADE_PACK_FLYOVER_ROW_ID)) == (
        CATALOG_IR_UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_CONSUMER_ID,
    )
    assert catalog_rule_ir_consumers_for_rule(_rule_ir(FLICKERJUMP_ROW_ID)) == (
        CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID,
    )


def test_catalog_preserves_aspect_warrior_profiles_geometry_loadouts_and_options() -> None:
    catalog = _package().army_catalog
    expected = {
        FIRE_DRAGONS_ID: ("Fire Dragon Exarch", "Fire Dragons", 7, 3, 3, 28.5),
        SWOOPING_HAWKS_ID: ("Swooping Hawk Exarch", "Swooping Hawks", 14, 3, 4, 32.0),
        WARP_SPIDERS_ID: ("Warp Spider Exarch", "Warp Spiders", 12, 3, 3, 28.5),
    }
    for datasheet_id, (
        exarch_name,
        warrior_name,
        movement,
        toughness,
        save,
        base_mm,
    ) in expected.items():
        datasheet = catalog.datasheet_by_id(datasheet_id)
        assert tuple(profile.name for profile in datasheet.model_profiles) == (
            exarch_name,
            warrior_name,
        )
        assert tuple(entry.min_models for entry in datasheet.composition) == (1, 4)
        assert tuple(entry.max_models for entry in datasheet.composition) == (1, 9)
        assert _profile_characteristic(datasheet.model_profiles[0], Characteristic.WOUNDS) == 2
        assert _profile_characteristic(datasheet.model_profiles[1], Characteristic.WOUNDS) == 1
        for profile in datasheet.model_profiles:
            assert _profile_characteristic(profile, Characteristic.MOVEMENT) == movement
            assert _profile_characteristic(profile, Characteristic.TOUGHNESS) == toughness
            assert _profile_characteristic(profile, Characteristic.SAVE) == save
            assert _profile_characteristic(profile, Characteristic.INVULNERABLE_SAVE) == 5
            assert abs(profile.base_size.diameter_mm - base_mm) < 1e-9
        assert any(ability.name == "Aspect Shrine Token" for ability in datasheet.abilities)
        assert any(
            option.selection_limit is not None
            and option.selection_limit.unit_resource_kind == "aeldari:aspect-shrine-token"
            for option in datasheet.wargear_options
        )

    assert {
        (row.datasheet_id, row.model_name, row.height)
        for row in AELDARI_ASPECT_WARRIORS_HEIGHT_OVERRIDES
    } == {
        (FIRE_DRAGONS_ID, "Fire Dragon Exarch", 2.0),
        (FIRE_DRAGONS_ID, "Fire Dragons", 2.0),
        (SWOOPING_HAWKS_ID, "Swooping Hawk Exarch", 2.75),
        (SWOOPING_HAWKS_ID, "Swooping Hawks", 2.75),
        (WARP_SPIDERS_ID, "Warp Spider Exarch", 2.0),
        (WARP_SPIDERS_ID, "Warp Spiders", 2.0),
    }

    factory = UnitFactory(catalog=catalog, model_geometries=_package().model_geometries)
    fire = _instantiate(
        factory,
        army_id="army-a",
        selection_id="fire-pistol-axe",
        datasheet_id=FIRE_DRAGONS_ID,
        wargear_selections=(
            WargearSelection(
                option_id=(
                    f"{FIRE_DRAGONS_ID}:fire-dragon-exarch-replacement-"
                    "dragon-fusion-pistol-dragon-axe:option-1"
                ),
                model_profile_id=f"{FIRE_DRAGONS_ID}:fire-dragon-exarch",
                wargear_ids=(
                    f"{FIRE_DRAGONS_ID}:dragon-axe",
                    f"{FIRE_DRAGONS_ID}:dragon-fusion-pistol",
                ),
            ),
        ),
    )
    exarch = fire.own_models[0]
    assert f"{FIRE_DRAGONS_ID}:exarchs-dragon-fusion-gun" not in exarch.wargear_ids
    assert {f"{FIRE_DRAGONS_ID}:dragon-axe", f"{FIRE_DRAGONS_ID}:dragon-fusion-pistol"}.issubset(
        exarch.wargear_ids
    )


def test_assured_destruction_composes_all_three_rerolls_and_builds_replay_safe_requests() -> None:
    fixture = _runtime_fixture(phase=BattlePhase.SHOOTING)
    runtime = CatalogDatasheetRuleRuntime(fixture.indexes, fixture.armies)
    registry = RuntimeModifierRegistry.from_bindings(
        attack_reroll_permission_bindings=runtime.attack_reroll_permission_bindings()
    )
    attacker = fixture.fire_dragons
    attacker_model = attacker.own_models[0]
    target = fixture.enemy_monster
    profile = _profile_for_wargear(f"{FIRE_DRAGONS_ID}:exarchs-dragon-fusion-gun")
    pool = _ranged_pool(attacker_model, target, profile)

    for roll_type in (
        "attack_sequence.hit",
        "attack_sequence.wound",
        "random_characteristic.damage.assured-destruction",
    ):
        permission = registry.attack_reroll_permission_context(
            AttackRerollPermissionContext(
                state=fixture.state,
                player_id="player-a",
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker_model.model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                source_phase=BattlePhase.SHOOTING,
                roll_type=roll_type,
                timing_window=roll_type,
            )
        )
        assert permission is not None
        assert permission.source_payload["roll_type"] in {
            "hit_roll",
            "wound_roll",
            "damage_roll",
        }

    infantry_context = replace(
        AttackRerollPermissionContext(
            state=fixture.state,
            player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attacker_model_instance_id=attacker_model.model_instance_id,
            target_unit_instance_id=target.unit_instance_id,
            source_phase=BattlePhase.SHOOTING,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        ),
        target_unit_instance_id=fixture.enemy_infantry.unit_instance_id,
    )
    assert registry.attack_reroll_permission_context(infantry_context) is None
    assert (
        registry.attack_reroll_permission_context(
            replace(
                infantry_context,
                target_unit_instance_id=target.unit_instance_id,
                source_phase=BattlePhase.FIGHT,
            )
        )
        is None
    )

    for roll_type in (
        "attack_sequence.hit",
        "attack_sequence.wound",
        "random_characteristic.damage.assured-destruction",
    ):
        _record_overlapping_attack_reroll_permission(
            fixture.state,
            unit_instance_id=attacker.unit_instance_id,
            roll_type=roll_type,
        )

    request_builders: tuple[
        tuple[str, Callable[[DiceRollState, DecisionController], LifecycleStatus | None]], ...
    ] = (
        (
            "attack_sequence.hit",
            lambda roll, decisions: _request_source_backed_hit_reroll_if_available(
                state=fixture.state,
                decisions=decisions,
                roll_state=roll,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker_model.model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                attack_context_id="assured-destruction:pool-001:attack-001",
                source_phase=BattlePhase.SHOOTING,
                weapon_profile_id=profile.profile_id,
                runtime_modifier_registry=registry,
            ),
        ),
        (
            "attack_sequence.wound",
            lambda roll, decisions: _request_source_backed_wound_reroll_if_available(
                state=fixture.state,
                decisions=decisions,
                roll_state=roll,
                pool=pool,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker_model.model_instance_id,
                attacker_keywords=attacker.keywords,
                attack_context_id="assured-destruction:pool-001:attack-001",
                source_phase=BattlePhase.SHOOTING,
                runtime_modifier_registry=registry,
            ),
        ),
        (
            "random_characteristic.damage.assured-destruction",
            lambda roll, decisions: _request_source_backed_damage_reroll_if_available(
                state=fixture.state,
                decisions=decisions,
                roll_state=roll,
                attacking_unit_instance_id=attacker.unit_instance_id,
                attacker_model_instance_id=attacker_model.model_instance_id,
                target_unit_instance_id=target.unit_instance_id,
                attack_context_id="assured-destruction:pool-001:attack-001",
                source_phase=BattlePhase.SHOOTING,
                weapon_profile_id=profile.profile_id,
                runtime_modifier_registry=registry,
            ),
        ),
    )
    for roll_type, build_request in request_builders:
        decisions = DecisionController()
        roll = DiceRollManager(fixture.state.game_id, event_log=decisions.event_log).roll_fixed(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Assured Destruction regression",
                roll_type=roll_type,
                actor_id="player-a",
            ),
            [1],
        )
        status = build_request(roll, decisions)
        assert status is not None
        request = status.decision_request
        assert request is not None
        assert (
            DecisionRequest.from_payload(request.to_payload()).to_payload() == request.to_payload()
        )
        payload = cast(dict[str, Any], request.payload)
        assert payload["source_rule_id"].startswith("catalog-ir:datasheet:")
        assert (
            cast(dict[str, Any], payload["attack_context"])["source_payload"]["effect_kind"]
            == "catalog_conditional_attack_reroll"
        )


def test_assured_destruction_applies_to_attached_leader_attacks() -> None:
    fixture = _runtime_fixture(
        phase=BattlePhase.SHOOTING,
        attach_leader_to="fire_dragons",
    )
    assert fixture.attached_leader is not None
    runtime = CatalogDatasheetRuleRuntime(fixture.indexes, fixture.armies)
    registry = RuntimeModifierRegistry.from_bindings(
        attack_reroll_permission_bindings=runtime.attack_reroll_permission_bindings()
    )

    permission = registry.attack_reroll_permission_context(
        AttackRerollPermissionContext(
            state=fixture.state,
            player_id="player-a",
            attacking_unit_instance_id=fixture.fire_dragons_rules_unit_id,
            attacker_model_instance_id=fixture.attached_leader.own_models[0].model_instance_id,
            target_unit_instance_id=fixture.enemy_monster.unit_instance_id,
            source_phase=BattlePhase.SHOOTING,
            roll_type="attack_sequence.hit",
            timing_window="attack_sequence.hit",
        )
    )

    assert permission is not None
    assert permission.source_payload["roll_type"] == "hit_roll"


def test_assured_destruction_requires_exact_canonical_target_keyword_tokens() -> None:
    fixture = _runtime_fixture(phase=BattlePhase.SHOOTING)
    target_view = rules_unit_view_by_id(
        state=fixture.state,
        unit_instance_id=fixture.enemy_monster.unit_instance_id,
    )

    assert _rules_unit_has_any_keyword(target_view, ("MONSTER",))
    assert not _rules_unit_has_any_keyword(target_view, ("monster",))
    assert not _rules_unit_has_any_keyword(target_view, ("MONSTER-UNIT",))


@pytest.mark.parametrize(
    ("event_type", "movement_action"),
    [
        ("movement_activation_completed", "normal_move"),
        ("reinforcement_unit_arrived", "set_up"),
    ],
)
def test_grenade_pack_requests_optional_visible_target_for_move_and_setup(
    event_type: str,
    movement_action: str,
) -> None:
    fixture = _runtime_fixture(phase=BattlePhase.MOVEMENT)
    decisions, registry = _grenade_pack_runtime(fixture)
    _record_move_completed_event(
        fixture.state,
        decisions,
        event_type=event_type,
        movement_action=movement_action,
    )

    status = resolve_unit_move_completed_mortal_wound_hooks(
        state=fixture.state,
        decisions=decisions,
        registry=registry,
        ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.MOVEMENT,
        event_type=event_type,
        movement_actions=(movement_action,),
        ability_indexes_by_player_id=fixture.indexes,
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    assert DecisionRequest.from_payload(request.to_payload()).to_payload() == request.to_payload()
    assert {option.label for option in request.options} == {
        "Decline ability",
        f"Inflict mortal wounds on {fixture.enemy_monster.unit_instance_id}",
    }
    payload = cast(dict[str, Any], request.payload)
    assert payload["movement_action"] == movement_action
    assert payload["target_range_inches"] == 8
    assert payload["target_requires_visibility"] is True
    assert payload["maximum_mortal_wounds"] == 6


def test_grenade_pack_rolls_only_for_surviving_keyworded_models_in_attached_unit() -> None:
    fixture = _runtime_fixture(
        phase=BattlePhase.MOVEMENT,
        swooping_hawk_count=5,
        attach_leader_to="swooping_hawks",
    )
    assert fixture.attached_leader is not None
    destroyed_hawk_id = fixture.swooping_hawks.own_models[0].model_instance_id
    _mark_model_destroyed(fixture.state, model_instance_id=destroyed_hawk_id)
    decisions, registry = _grenade_pack_runtime(fixture)
    _record_move_completed_event(
        fixture.state,
        decisions,
        event_type="movement_activation_completed",
        movement_action="normal_move",
        unit_instance_id=fixture.swooping_hawks_rules_unit_id,
    )

    status = resolve_unit_move_completed_mortal_wound_hooks(
        state=fixture.state,
        decisions=decisions,
        registry=registry,
        ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.MOVEMENT,
        event_type="movement_activation_completed",
        movement_actions=("normal_move",),
        ability_indexes_by_player_id=fixture.indexes,
    )

    assert status is not None
    assert status.decision_request is not None
    payload = cast(dict[str, Any], status.decision_request.payload)
    assert payload["roll_model_instance_ids"] == sorted(
        model.model_instance_id
        for model in fixture.swooping_hawks.own_models
        if model.model_instance_id != destroyed_hawk_id
    )
    assert (
        fixture.attached_leader.own_models[0].model_instance_id
        not in payload["roll_model_instance_ids"]
    )


@pytest.mark.parametrize("transport_movement_status", ["not_moved", "normal_move"])
def test_grenade_pack_consumes_pre_and_post_move_disembark_as_setup(
    transport_movement_status: str,
) -> None:
    fixture = _runtime_fixture(phase=BattlePhase.MOVEMENT)
    decisions, registry = _grenade_pack_runtime(fixture)
    _record_move_completed_event(
        fixture.state,
        decisions,
        event_type="unit_disembarked",
        movement_action=None,
        transport_movement_status=transport_movement_status,
    )
    handler = MovementPhaseHandler(
        ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
        unit_move_completed_mortal_wound_hooks=registry,
        ability_indexes_by_player_id=fixture.indexes,
    )

    status = handler.begin_phase(state=fixture.state, decisions=decisions)

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    payload = cast(dict[str, Any], status.decision_request.payload)
    assert payload["movement_action"] == "set_up"
    assert payload["trigger_event_id"] == decisions.event_log.records[0].event_id


def test_grenade_pack_resolves_per_hawk_caps_damage_restricts_grenades_and_is_once_per_turn() -> (
    None
):
    fixture = _runtime_fixture(phase=BattlePhase.MOVEMENT, swooping_hawk_count=10)
    decisions, registry = _grenade_pack_runtime(fixture)
    _record_move_completed_event(
        fixture.state,
        decisions,
        event_type="movement_activation_completed",
        movement_action="advance",
    )
    status = resolve_unit_move_completed_mortal_wound_hooks(
        state=fixture.state,
        decisions=decisions,
        registry=registry,
        ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        completed_phase=BattlePhase.MOVEMENT,
        event_type="movement_activation_completed",
        movement_actions=("advance",),
        ability_indexes_by_player_id=fixture.indexes,
    )
    assert status is not None
    assert status.decision_request is not None
    request = status.decision_request
    target_option = next(option for option in request.options if option.label != "Decline ability")
    result = DecisionResult.for_request(
        result_id="grenade-pack:select-target",
        request=request,
        selected_option_id=target_option.option_id,
    )
    decisions.submit_result(result)
    assert (
        apply_catalog_unit_move_completed_mortal_wounds_target_result(
            state=fixture.state,
            decisions=decisions,
            result=result,
            ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
        )
        is None
    )
    assert (
        resolve_unit_move_completed_mortal_wound_hooks(
            state=fixture.state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase.MOVEMENT,
            event_type="movement_activation_completed",
            movement_actions=("advance",),
            ability_indexes_by_player_id=fixture.indexes,
        )
        is None
    )
    resolved = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == UNIT_MOVE_COMPLETED_MORTAL_WOUNDS_RESOLVED_EVENT
    )
    inflicted = sum(
        cast(int, cast(dict[str, Any], event.payload)["mortal_wounds"]) for event in resolved
    )
    assert 0 <= inflicted <= 6
    restriction = next(
        effect
        for effect in fixture.state.persisting_effects_for_unit(
            fixture.swooping_hawks.unit_instance_id
        )
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("forbidden_stratagem_handler_ids") is not None
    )
    assert restriction.effect_payload == {
        "effect_kind": "catalog_stratagem_target_restriction",
        "catalog_record_id": cast(dict[str, Any], request.payload)["catalog_record_id"],
        "source_rule_id": cast(dict[str, Any], request.payload)["source_rule_id"],
        "source_rules_unit_instance_id": fixture.swooping_hawks.unit_instance_id,
        "forbidden_stratagem_handler_ids": ["core:explosives"],
    }

    _record_move_completed_event(
        fixture.state,
        decisions,
        event_type="movement_activation_completed",
        movement_action="fall_back",
    )
    assert (
        resolve_unit_move_completed_mortal_wound_hooks(
            state=fixture.state,
            decisions=decisions,
            registry=registry,
            ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
            completed_phase=BattlePhase.MOVEMENT,
            event_type="movement_activation_completed",
            movement_actions=("normal_move", "advance", "fall_back"),
            ability_indexes_by_player_id=fixture.indexes,
        )
        is None
    )
    assert decisions.queue.pending_requests == ()


def test_flickerjump_grant_sets_move_forbids_charge_and_resolves_phase_end_self_damage() -> None:
    fixture = _runtime_fixture(phase=BattlePhase.MOVEMENT)
    runtime = CatalogDatasheetRuleRuntime(fixture.indexes, fixture.armies)
    registry = AdvanceMoveHookRegistry.from_bindings(runtime.advance_move_hook_bindings())
    context = AdvanceMoveContext(
        state=fixture.state,
        player_id="player-a",
        battle_round=1,
        unit_instance_id=fixture.warp_spiders.unit_instance_id,
        movement_phase_action="normal_move",
        movement_request_id="flickerjump:movement-request",
        movement_result_id="flickerjump:movement-result",
    )
    grants = registry.grants_for(context)
    assert len(grants) == 1
    grant = grants[0]
    assert grant.label == "Flickerjump"
    payload = cast(dict[str, Any], grant.unit_effect_payload)
    assert payload["movement_characteristic"] == 24
    assert payload["charge_forbidden"] is True
    assert payload["phase_end_mortal_wounds"] == {
        "roll_expression": "D6",
        "roll_count_scope": "each_model_in_this_unit_at_phase_end",
        "success_value": 1,
        "mortal_wounds_per_success": 1,
    }
    assert registry.grants_for(replace(context, movement_phase_action="advance")) == ()

    effect = PersistingEffect(
        effect_id="flickerjump:active-effect",
        source_rule_id=grant.source_id,
        owner_player_id="player-a",
        target_unit_instance_ids=(fixture.warp_spiders.unit_instance_id,),
        started_battle_round=1,
        started_phase=BattlePhaseKind.MOVEMENT,
        expiration=EffectExpiration.end_turn(battle_round=1, player_id="player-a"),
        effect_payload=grant.unit_effect_payload,
    )
    fixture.state.record_persisting_effect(effect)
    movement_registry = RuntimeModifierRegistry.from_bindings(
        movement_budget_modifier_bindings=runtime.movement_budget_modifier_bindings()
    )
    model = fixture.warp_spiders.own_models[0]
    assert (
        movement_registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=fixture.state,
                unit_instance_id=fixture.warp_spiders.unit_instance_id,
                model_instance_id=model.model_instance_id,
                base_movement_inches=12.0,
                current_movement_inches=12.0,
            )
        )
        == 24.0
    )

    decisions = DecisionController()
    assert (
        resolve_movement_phase_end_mortal_wounds(state=fixture.state, decisions=decisions) is None
    )
    rolled = next(
        event
        for event in decisions.event_log.records
        if event.event_type == MOVEMENT_PHASE_END_MORTAL_WOUNDS_ROLLED_EVENT
    )
    rolled_payload = cast(dict[str, Any], rolled.payload)
    assert rolled_payload["model_ids"] == sorted(fixture.warp_spiders.own_model_ids())
    assert rolled_payload["success_value"] == 1
    assert any(
        event.event_type == MOVEMENT_PHASE_END_MORTAL_WOUNDS_RESOLVED_EVENT
        for event in decisions.event_log.records
    )
    assert (
        resolve_movement_phase_end_mortal_wounds(state=fixture.state, decisions=decisions) is None
    )
    assert (
        sum(
            event.event_type == MOVEMENT_PHASE_END_MORTAL_WOUNDS_ROLLED_EVENT
            for event in decisions.event_log.records
        )
        == 1
    )


class _RuntimeFixture:
    def __init__(
        self,
        *,
        armies: tuple[ArmyDefinition, ...],
        state: GameState,
        indexes: dict[str, Any],
        fire_dragons: UnitInstance,
        swooping_hawks: UnitInstance,
        warp_spiders: UnitInstance,
        enemy_monster: UnitInstance,
        enemy_infantry: UnitInstance,
        fire_dragons_rules_unit_id: str,
        swooping_hawks_rules_unit_id: str,
        attached_leader: UnitInstance | None,
    ) -> None:
        self.armies = armies
        self.state = state
        self.indexes = indexes
        self.fire_dragons = fire_dragons
        self.swooping_hawks = swooping_hawks
        self.warp_spiders = warp_spiders
        self.enemy_monster = enemy_monster
        self.enemy_infantry = enemy_infantry
        self.fire_dragons_rules_unit_id = fire_dragons_rules_unit_id
        self.swooping_hawks_rules_unit_id = swooping_hawks_rules_unit_id
        self.attached_leader = attached_leader


def _runtime_fixture(
    *,
    phase: BattlePhase,
    swooping_hawk_count: int = 5,
    attach_leader_to: str | None = None,
) -> _RuntimeFixture:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    fire_dragons = _instantiate(
        factory,
        army_id="army-a",
        selection_id="fire-dragons",
        datasheet_id=FIRE_DRAGONS_ID,
    )
    swooping_hawks = _instantiate(
        factory,
        army_id="army-a",
        selection_id="swooping-hawks",
        datasheet_id=SWOOPING_HAWKS_ID,
        total_models=swooping_hawk_count,
    )
    warp_spiders = _instantiate(
        factory,
        army_id="army-a",
        selection_id="warp-spiders",
        datasheet_id=WARP_SPIDERS_ID,
    )
    enemy_monster = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy-wraithlord",
        datasheet_id=WRAITHLORD_ID,
    )
    enemy_infantry = _instantiate(
        factory,
        army_id="army-b",
        selection_id="enemy-fire-dragons",
        datasheet_id=FIRE_DRAGONS_ID,
    )
    attached_leader = None
    attached_units: tuple[AttachedUnitFormation, ...] = ()
    fire_dragons_rules_unit_id = fire_dragons.unit_instance_id
    swooping_hawks_rules_unit_id = swooping_hawks.unit_instance_id
    player_a_units = [fire_dragons, swooping_hawks, warp_spiders]
    if attach_leader_to is not None:
        attached_leader = _instantiate(
            factory,
            army_id="army-a",
            selection_id=f"{attach_leader_to}-leader",
            datasheet_id=PRINCE_YRIEL_ID,
        )
        source_unit = {
            "fire_dragons": fire_dragons,
            "swooping_hawks": swooping_hawks,
        }.get(attach_leader_to)
        if source_unit is None:
            raise ValueError("Unsupported attached Aspect Warrior source.")
        attached_rules_unit_id = f"attached-unit:army-a:{attach_leader_to}-leader"
        attached_units = (
            AttachedUnitFormation(
                attached_unit_instance_id=attached_rules_unit_id,
                bodyguard_unit_instance_id=source_unit.unit_instance_id,
                leader_unit_instance_ids=(attached_leader.unit_instance_id,),
                component_unit_instance_ids=tuple(
                    sorted((source_unit.unit_instance_id, attached_leader.unit_instance_id))
                ),
                source_id=f"test:{attach_leader_to}:attachment",
                attachment_source_ids=(f"test:{attach_leader_to}:leader-eligibility",),
            ),
        )
        if attach_leader_to == "fire_dragons":
            fire_dragons_rules_unit_id = attached_rules_unit_id
        else:
            swooping_hawks_rules_unit_id = attached_rules_unit_id
        player_a_units.append(attached_leader)
    armies = (
        _army(
            catalog,
            "army-a",
            "player-a",
            tuple(player_a_units),
            attached_units=attached_units,
        ),
        _army(catalog, "army-b", "player-b", (enemy_monster, enemy_infantry)),
    )
    state = _state(armies, phase=phase)
    _move_unit(state, swooping_hawks.unit_instance_id, x=10.0, y=10.0)
    if attach_leader_to == "swooping_hawks":
        assert attached_leader is not None
        _move_unit(state, attached_leader.unit_instance_id, x=10.0, y=20.0)
    _move_unit(state, enemy_monster.unit_instance_id, x=15.0, y=10.0)
    _move_unit(state, enemy_infantry.unit_instance_id, x=50.0, y=10.0)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return _RuntimeFixture(
        armies=armies,
        state=state,
        indexes=indexes,
        fire_dragons=fire_dragons,
        swooping_hawks=swooping_hawks,
        warp_spiders=warp_spiders,
        enemy_monster=enemy_monster,
        enemy_infantry=enemy_infantry,
        fire_dragons_rules_unit_id=fire_dragons_rules_unit_id,
        swooping_hawks_rules_unit_id=swooping_hawks_rules_unit_id,
        attached_leader=attached_leader,
    )


def _state(armies: tuple[ArmyDefinition, ...], *, phase: BattlePhase) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id="aeldari-aspect-warriors-regression",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=phases,
        setup_step_index=None,
        battle_phase_index=phases.index(phase),
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
        battlefield_id="aeldari-aspect-warriors-battlefield",
        armies=armies,
    ).battlefield_state
    return state


def _army(
    catalog: Any,
    army_id: str,
    player_id: str,
    units: tuple[UnitInstance, ...],
    *,
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
            detachment_ids=("aspect-host",),
        ),
        force_disposition_id="purge-the-foe",
        units=units,
        attached_units=attached_units,
    )


def _instantiate(
    factory: UnitFactory,
    *,
    army_id: str,
    selection_id: str,
    datasheet_id: str,
    total_models: int | None = None,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    counts = [entry.min_models for entry in datasheet.composition]
    if total_models is not None:
        counts[-1] = total_models - sum(counts[:-1])
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(entry.model_profile_id, count)
                for entry, count in zip(datasheet.composition, counts, strict=True)
            ),
            wargear_selections=wargear_selections,
        ),
    )


def _grenade_pack_runtime(
    fixture: _RuntimeFixture,
) -> tuple[DecisionController, UnitMoveCompletedMortalWoundHookRegistry]:
    runtime = CatalogUnitMoveCompletedMortalWoundsRuntime(fixture.indexes, fixture.armies)
    return DecisionController(), UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        runtime.bindings()
    )


def _record_move_completed_event(
    state: GameState,
    decisions: DecisionController,
    *,
    event_type: str,
    movement_action: str | None,
    unit_instance_id: str = "army-a:swooping-hawks",
    transport_movement_status: str | None = None,
) -> None:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.MOVEMENT.value,
        "active_player_id": "player-a",
        "unit_instance_id": unit_instance_id,
    }
    if movement_action is not None:
        payload["movement_phase_action"] = movement_action
    if transport_movement_status is not None:
        payload["transport_unit_instance_id"] = "army-a:test-transport"
        payload["transport_movement_status"] = transport_movement_status
    decisions.event_log.append(
        event_type,
        payload,
    )


def _record_overlapping_attack_reroll_permission(
    state: GameState,
    *,
    unit_instance_id: str,
    roll_type: str,
) -> None:
    source_id = f"zzzz:test:overlapping-reroll:{roll_type}"
    permission = RerollPermission(
        source_id=source_id,
        timing_window=roll_type,
        owning_player_id="player-a",
        eligible_roll_type=roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    state.record_persisting_effect(
        PersistingEffect(
            effect_id=f"{source_id}:effect",
            source_rule_id=source_id,
            owner_player_id="player-a",
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.SHOOTING,
            expiration=EffectExpiration.end_turn(
                battle_round=state.battle_round,
                player_id="player-a",
            ),
            effect_payload=source_backed_reroll_permission_effect_payload(
                target_unit_instance_ids=(unit_instance_id,),
                permission=permission,
                source_payload={
                    "effect_kind": "test_overlapping_attack_reroll",
                    "attack_kind": "ranged",
                },
            ),
        )
    )


def _mark_model_destroyed(state: GameState, *, model_instance_id: str) -> None:
    updated_armies: list[ArmyDefinition] = []
    found = False
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models = tuple(
                replace(model, wounds_remaining=0)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            if updated_models != unit.own_models:
                found = True
            updated_units.append(replace(unit, own_models=updated_models))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    assert found
    state.replace_army_definitions(updated_armies)


def _move_unit(state: GameState, unit_instance_id: str, *, x: float, y: float) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    moved = replace(
        placement,
        model_placements=tuple(
            replace(model, pose=Pose.at(x=x, y=y + (index * 1.5)))
            for index, model in enumerate(placement.model_placements)
        ),
    )
    state.replace_battlefield_state(battlefield.with_unit_placement(moved))


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _profile_characteristic(profile: Any, characteristic: Characteristic) -> int:
    return cast(
        int,
        next(
            value.final
            for value in profile.characteristics
            if value.characteristic is characteristic
        ),
    )


def _profile_for_wargear(wargear_id: str) -> WeaponProfile:
    wargear = next(
        item for item in _package().army_catalog.wargear if item.wargear_id == wargear_id
    )
    assert len(wargear.weapon_profiles) == 1
    return cast(WeaponProfile, wargear.weapon_profiles[0])


def _ranged_pool(
    attacker_model: Any,
    target: UnitInstance,
    profile: WeaponProfile,
) -> RangedAttackPool:
    assert profile.range_profile.kind is RangeProfileKind.DISTANCE
    target_model_ids = target.own_model_ids()
    return RangedAttackPool(
        attacker_model_instance_id=attacker_model.model_instance_id,
        wargear_id=f"test:{profile.profile_id}:wargear",
        weapon_profile_id=profile.profile_id,
        weapon_profile=profile,
        target_unit_instance_id=target.unit_instance_id,
        shooting_type=ShootingType.NORMAL,
        attacks=1,
        target_visible_model_ids=target_model_ids,
        target_in_range_model_ids=target_model_ids,
    )
