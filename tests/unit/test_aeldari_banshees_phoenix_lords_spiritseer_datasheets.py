from __future__ import annotations

import json
from dataclasses import dataclass, replace
from functools import cache
from typing import Any, cast

import pytest
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)
from tools.generate_aeldari_banshees_phoenix_lords_spiritseer_rule_ir import (
    OUTPUT_PATH,
    RULE_TEXT_BY_SOURCE_ROW_ID,
    generated_artifact_payload,
)

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.ability_catalog import (
    build_player_ability_index,
    catalog_ability_records_from_catalog,
)
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.catalog_command_restoration_runtime import (
    CATALOG_COMMAND_RESTORATION_SELECTED_EVENT,
    CatalogCommandRestorationRuntime,
)
from warhammer40k_core.engine.catalog_conditional_leader_abilities import (
    CatalogConditionalLeaderAbilityRuntime,
)
from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_charge_after_movement_action_allowed,
)
from warhammer40k_core.engine.catalog_conditional_leading_runtime import (
    CatalogConditionalLeadingRuntime,
)
from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
    CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT,
    SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE,
    CatalogMovementTargetPairRuntime,
    invalid_catalog_movement_target_pair_status,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_rule_ir_consumers_for_rule,
)
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartRequestContext,
    CommandPhaseStartResultContext,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import HealingEffect
from warhammer40k_core.engine.healing_revival import (
    SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    apply_healing_revival_placement_decision,
    healing_effect_from_revival_request,
)
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    FallBackModeKind,
    MovementPhaseActionKind,
    MovementPhaseState,
    MovementUnitSelection,
    PendingMovementActionSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_mortal_wound_hooks,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.rule_ir import RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_banshees_phoenix_lords_spiritseer_2026_06 as source_package,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    AELDARI_BANSHEES_PHOENIX_LORDS_SPIRITSEER_HEIGHT_OVERRIDES,
)

HOWLING_BANSHEES_ID = "000000594"
JAIN_ZAR_ID = "000000572"
LHYKHIS_ID = "000003909"
SPIRITSEER_ID = "000000588"
FUEGAN_ID = "000000574"
FIRE_DRAGONS_ID = "000000596"
WARP_SPIDERS_ID = "000000601"
WRAITHBLADES_ID = "000000598"
WRAITHLORD_ID = "000000613"

JAIN_ATTACHED_ID = "attached-unit:army-a:jain-banshees"
FUEGAN_ATTACHED_ID = "attached-unit:army-a:fuegan-dragons"
LHYKHIS_ATTACHED_ID = "attached-unit:army-a:lhykhis-spiders"
SPIRITSEER_ATTACHED_ID = "attached-unit:army-a:spiritseer-wraithblades"


@cache
def _package() -> Any:
    return _ability_support_catalog_package()


def test_generated_artifact_is_current_source_bound_and_fail_fast() -> None:
    committed = cast(dict[str, Any], json.loads(OUTPUT_PATH.read_text(encoding="utf-8")))

    assert committed == generated_artifact_payload()
    assert source_package.supported_datasheet_source_row_ids() == tuple(
        sorted(RULE_TEXT_BY_SOURCE_ROW_ID)
    )
    assert committed["package_hash"] == source_package.PACKAGE_HASH

    committed["package_hash"] = "0" * 64
    with pytest.raises(
        source_package.AeldariBansheesPhoenixLordsSpiritseerRuleIrArtifactError,
        match="hash is stale",
    ):
        source_package.validate_generated_artifact_bytes(json.dumps(committed).encode())


def test_exact_rules_route_to_generic_runtime_consumers() -> None:
    expected = {
        "000000572:4": (
            "catalog-ir:conditional-leading-fixed-advance",
            "catalog-ir:dice-result-override",
        ),
        "000000572:5": ("catalog-ir:wound-roll-reroll",),
        "000000574:3": ("catalog-ir:conditional-leading-weapon-range-modifier",),
        "000000574:4": ("catalog-ir:first-death-return",),
        "000000588:3": ("catalog-ir:conditional-ability:lone-operative",),
        "000000588:4": ("catalog-ir:movement-friendly-enemy-target-pair",),
        "000000588:5": ("catalog-ir:command-restoration",),
        "000000594:3": (
            "catalog-ir:can-advance-and-charge",
            "catalog-ir:can-fallback-and-charge",
        ),
        "000003909:4": ("catalog-ir:conditional-leading-charge-after-movement-action",),
        "000003909:5": ("catalog-ir:minimum-unmodified-hit-success",),
    }

    assert {
        source_row_id: catalog_rule_ir_consumers_for_rule(_rule_ir(source_row_id))
        for source_row_id in sorted(expected)
    } == expected


def test_catalog_preserves_profiles_geometry_and_leader_targets() -> None:
    catalog = _package().army_catalog
    expected_profiles = {
        JAIN_ZAR_ID: ("Jain Zar - EPIC HERO", (8, 3, 2, 5, 6, 1, 4), 40.0),
        FUEGAN_ID: ("Fuegan - EPIC HERO", (7, 3, 2, 5, 6, 1, 4), 40.0),
        SPIRITSEER_ID: ("Spiritseer", (7, 3, 6, 3, 6, 1, 4), 25.0),
        LHYKHIS_ID: ("Lhykhis - EPIC HERO", (12, 3, 2, 5, 6, 1, 4), 40.0),
    }
    for datasheet_id, (name, characteristics, base_mm) in expected_profiles.items():
        datasheet = catalog.datasheet_by_id(datasheet_id)
        profile = datasheet.model_profiles[0]
        assert profile.name == name
        assert _characteristics(profile) == characteristics
        assert profile.base_size.diameter_mm == base_mm

    assert _leader_target_ids(catalog.datasheet_by_id(JAIN_ZAR_ID)) == {HOWLING_BANSHEES_ID}
    assert _leader_target_ids(catalog.datasheet_by_id(FUEGAN_ID)) == {FIRE_DRAGONS_ID}
    assert _leader_target_ids(catalog.datasheet_by_id(LHYKHIS_ID)) == {WARP_SPIDERS_ID}
    assert {
        (override.datasheet_id, override.model_name, override.height)
        for override in AELDARI_BANSHEES_PHOENIX_LORDS_SPIRITSEER_HEIGHT_OVERRIDES
    } == {
        (JAIN_ZAR_ID, "Jain Zar - EPIC HERO", 2.5),
        (FUEGAN_ID, "Fuegan - EPIC HERO", 2.25),
        (SPIRITSEER_ID, "Spiritseer", 2.0),
        (LHYKHIS_ID, "Lhykhis - EPIC HERO", 3.0),
    }


def test_live_leader_rules_fix_advance_extend_melta_and_allow_flickerjump_charge() -> None:
    fixture = _fixture(phase=BattlePhase.MOVEMENT)
    conditional = CatalogConditionalLeaderAbilityRuntime(fixture.indexes, fixture.armies)
    conditional.record_static_effects(state=fixture.state)
    runtime = CatalogConditionalLeadingRuntime(fixture.indexes, fixture.armies)

    grant = runtime.fixed_advance_grant(
        AdvanceMoveContext(
            state=fixture.state,
            player_id="player-a",
            battle_round=1,
            unit_instance_id=JAIN_ATTACHED_ID,
            movement_phase_action="advance",
            movement_request_id="advance-request",
            movement_result_id="advance-result",
        )
    )
    assert grant is not None
    assert grant.fixed_advance_inches == 6
    assert grant.ignores_vertical_distance
    assert grant.automatic
    assert grant.to_payload().get("fixed_advance_inches") == 6

    melta_profile = _melta_profile(FIRE_DRAGONS_ID)
    modified = runtime.weapon_range_modifier(
        WeaponProfileModifierContext(
            state=fixture.state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=FUEGAN_ATTACHED_ID,
            attacker_model_instance_id=fixture.fire_dragons.own_models[0].model_instance_id,
            target_unit_instance_id=fixture.enemy.unit_instance_id,
            weapon_profile=melta_profile,
        )
    )
    assert melta_profile.range_profile.kind is RangeProfileKind.DISTANCE
    assert modified.range_profile.distance_inches == (
        cast(float, melta_profile.range_profile.distance_inches) + 6
    )
    assert conditional_charge_after_movement_action_allowed(
        state=fixture.state,
        rules_unit_instance_id=LHYKHIS_ATTACHED_ID,
        movement_action_effect_kind="catalog_movement_action_grant",
    )

    _set_model_wounds(
        fixture.state,
        model_instance_id=fixture.fuegan.own_models[0].model_instance_id,
        wounds=0,
    )
    _set_model_wounds(
        fixture.state,
        model_instance_id=fixture.lhykhis.own_models[0].model_instance_id,
        wounds=0,
    )
    assert (
        runtime.weapon_range_modifier(
            WeaponProfileModifierContext(
                state=fixture.state,
                source_phase=BattlePhase.SHOOTING,
                attacking_unit_instance_id=FUEGAN_ATTACHED_ID,
                attacker_model_instance_id=fixture.fire_dragons.own_models[0].model_instance_id,
                target_unit_instance_id=fixture.enemy.unit_instance_id,
                weapon_profile=melta_profile,
            )
        )
        == melta_profile
    )
    assert not conditional_charge_after_movement_action_allowed(
        state=fixture.state,
        rules_unit_instance_id=LHYKHIS_ATTACHED_ID,
        movement_action_effect_kind="catalog_movement_action_grant",
    )
    for model in fixture.howling_banshees.own_models:
        _remove_model(fixture.state, model_instance_id=model.model_instance_id)
    assert _model_from_state(
        fixture.state,
        fixture.jain_zar.own_models[0].model_instance_id,
    ).is_alive
    assert (
        runtime.fixed_advance_grant(
            AdvanceMoveContext(
                state=fixture.state,
                player_id="player-a",
                battle_round=1,
                unit_instance_id=JAIN_ATTACHED_ID,
                movement_phase_action="advance",
                movement_request_id="advance-after-bodyguard-destroyed-request",
                movement_result_id="advance-after-bodyguard-destroyed-result",
            )
        )
        is None
    )


def test_spirit_mark_uses_finite_decision_current_state_validation_and_target_gate() -> None:
    fixture = _fixture(phase=BattlePhase.MOVEMENT)
    runtime = CatalogMovementTargetPairRuntime(fixture.indexes, fixture.armies)
    decisions = DecisionController()
    pending = _pending_movement_action(fixture.spiritseer.unit_instance_id)
    fixture.state.replace_movement_phase_state(_movement_state(pending))

    status = runtime.start_move_request(
        state=fixture.state,
        decisions=decisions,
        pending_action=pending,
    )
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = status.decision_request
    assert request is not None
    assert request.decision_type == SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE
    option = next(
        option for option in request.options if cast(dict[str, Any], option.payload)["use_ability"]
    )
    result = DecisionResult.for_request(
        result_id="spirit-mark-result",
        request=request,
        selected_option_id=option.option_id,
    )
    assert (
        invalid_catalog_movement_target_pair_status(
            state=fixture.state,
            decisions=decisions,
            request=request,
            result=result,
            ability_indexes_by_player_id=fixture.indexes,
        )
        is None
    )
    decisions.submit_result(result)
    runtime.apply_result(
        state=fixture.state,
        decisions=decisions,
        request=request,
        result=result,
    )
    assert DecisionController.from_payload(decisions.to_payload()).to_payload() == (
        decisions.to_payload()
    )

    assert any(
        event.event_type == CATALOG_MOVEMENT_TARGET_PAIR_SELECTED_EVENT
        for event in decisions.event_log.records
    )
    effect = next(
        effect
        for effect in fixture.state.persisting_effects
        if isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("catalog_effect_kind") == "catalog_movement_target_pair"
    )
    assert effect.target_unit_instance_ids == (fixture.wraith_construct.unit_instance_id,)
    assert effect.expiration.to_payload() == {
        "expiration_kind": "start_phase",
        "battle_round": 2,
        "phase": "movement",
        "player_id": "player-a",
    }

    profile = _first_weapon_profile(fixture.wraith_construct)
    registry = RuntimeModifierRegistry.empty()
    marked = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=fixture.state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=fixture.wraith_construct.unit_instance_id,
            attacker_model_instance_id=(fixture.wraith_construct.own_models[0].model_instance_id),
            target_unit_instance_id=fixture.enemy.unit_instance_id,
            weapon_profile=profile,
        )
    )
    assert WeaponKeyword.SUSTAINED_HITS in marked.keywords
    sustained_hits = next(
        ability
        for ability in marked.abilities
        if ability.ability_kind is AbilityKind.SUSTAINED_HITS
    )
    assert sustained_hits.parameters[0].value == 1

    unmarked = registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=fixture.state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=fixture.wraith_construct.unit_instance_id,
            attacker_model_instance_id=(fixture.wraith_construct.own_models[0].model_instance_id),
            target_unit_instance_id=fixture.other_enemy.unit_instance_id,
            weapon_profile=profile,
        )
    )
    assert WeaponKeyword.SUSTAINED_HITS not in unmarked.keywords

    drifted_fixture = _fixture(phase=BattlePhase.MOVEMENT)
    drifted_runtime = CatalogMovementTargetPairRuntime(
        drifted_fixture.indexes, drifted_fixture.armies
    )
    drifted_decisions = DecisionController()
    drifted_pending = _pending_movement_action(drifted_fixture.spiritseer.unit_instance_id)
    drifted_fixture.state.replace_movement_phase_state(_movement_state(drifted_pending))
    drifted_status = drifted_runtime.start_move_request(
        state=drifted_fixture.state,
        decisions=drifted_decisions,
        pending_action=drifted_pending,
    )
    assert drifted_status is not None
    assert drifted_status.decision_request is not None
    drifted_request = drifted_status.decision_request
    drifted_option = next(
        option
        for option in drifted_request.options
        if cast(dict[str, Any], option.payload)["use_ability"]
    )
    drifted_result = DecisionResult.for_request(
        result_id="drifted-spirit-mark-result",
        request=drifted_request,
        selected_option_id=drifted_option.option_id,
    )
    _move_unit(
        drifted_fixture.state,
        drifted_fixture.wraith_construct.unit_instance_id,
        x=50.0,
        y=40.0,
    )
    invalid = invalid_catalog_movement_target_pair_status(
        state=drifted_fixture.state,
        decisions=drifted_decisions,
        request=drifted_request,
        result=drifted_result,
        ability_indexes_by_player_id=drifted_fixture.indexes,
    )
    assert invalid is not None
    assert invalid.status_kind is LifecycleStatusKind.INVALID


@pytest.mark.parametrize(
    ("movement_action", "expected_request"),
    [
        (MovementPhaseActionKind.NORMAL_MOVE, True),
        (MovementPhaseActionKind.ADVANCE, True),
        (MovementPhaseActionKind.FALL_BACK, True),
        (MovementPhaseActionKind.REMAIN_STATIONARY, False),
    ],
)
def test_spirit_mark_start_edge_requires_an_actual_move(
    movement_action: MovementPhaseActionKind,
    expected_request: bool,
) -> None:
    fixture = _fixture(phase=BattlePhase.MOVEMENT)
    runtime = CatalogMovementTargetPairRuntime(fixture.indexes, fixture.armies)
    decisions = DecisionController()
    pending = _pending_movement_action(
        fixture.spiritseer.unit_instance_id,
        movement_action=movement_action,
    )
    fixture.state.replace_movement_phase_state(_movement_state(pending))

    status = runtime.start_move_request(
        state=fixture.state,
        decisions=decisions,
        pending_action=pending,
    )

    assert (status is not None) is expected_request
    assert bool(decisions.queue.pending_requests) is expected_request


@pytest.mark.parametrize(
    ("event_type", "movement_action", "expected_request"),
    [
        ("movement_activation_completed", "normal_move", True),
        ("movement_activation_completed", "advance", True),
        ("movement_activation_completed", "fall_back", True),
        ("movement_activation_completed", "remain_stationary", False),
        ("reinforcement_unit_arrived", "set_up", False),
        ("unit_disembarked", "set_up", False),
    ],
)
def test_spirit_mark_move_completion_registry_rejects_stationary_and_setup_events(
    event_type: str,
    movement_action: str,
    expected_request: bool,
) -> None:
    fixture = _fixture(phase=BattlePhase.MOVEMENT)
    runtime = CatalogMovementTargetPairRuntime(fixture.indexes, fixture.armies)
    decisions = DecisionController()
    _record_move_completed_event(
        state=fixture.state,
        decisions=decisions,
        event_type=event_type,
        movement_action=movement_action,
        unit_instance_id=fixture.spiritseer.unit_instance_id,
    )
    registry = UnitMoveCompletedMortalWoundHookRegistry.from_bindings(
        runtime.move_completed_bindings()
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

    assert (status is not None) is expected_request
    assert bool(decisions.queue.pending_requests) is expected_request


@pytest.mark.parametrize("destroyed_model", [False, True])
def test_tears_of_isha_heals_or_returns_one_model_and_is_once_per_target(
    destroyed_model: bool,
) -> None:
    fixture = _fixture(phase=BattlePhase.COMMAND)
    target_model = fixture.wraith_construct.own_models[0]
    assert fixture.state.battlefield_state is not None
    target_placement = fixture.state.battlefield_state.model_placement_by_id(
        target_model.model_instance_id
    )
    if destroyed_model:
        _remove_model(fixture.state, model_instance_id=target_model.model_instance_id)
    else:
        _set_model_wounds(
            fixture.state,
            model_instance_id=target_model.model_instance_id,
            wounds=1,
        )
    runtime = CatalogCommandRestorationRuntime(fixture.indexes, fixture.armies)
    decisions = DecisionController()
    request = runtime.request(
        CommandPhaseStartRequestContext(
            state=fixture.state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    assert request is not None
    decisions.request_decision(request)
    option = next(
        option
        for option in request.options
        if cast(dict[str, Any], option.payload)["target_unit_instance_id"]
        == fixture.wraith_construct.unit_instance_id
    )
    result = DecisionResult.for_request(
        result_id=f"tears-result-{destroyed_model}",
        request=request,
        selected_option_id=option.option_id,
    )
    assert runtime.selection_is_current(
        state=fixture.state,
        decisions=decisions,
        request=request,
        result=result,
    )
    decisions.submit_result(result)
    assert runtime.apply_result(
        CommandPhaseStartResultContext(
            state=fixture.state,
            decisions=decisions,
            request=request,
            result=result,
            active_player_id="player-a",
        )
    )
    if destroyed_model:
        placement_request = decisions.queue.peek_next()
        assert placement_request.decision_type == (SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE)
        placement_effect = healing_effect_from_revival_request(request=placement_request)
        assert fixture.state.battlefield_state is not None
        anchor = fixture.state.battlefield_state.unit_placement_by_id(
            fixture.wraith_construct.unit_instance_id
        ).model_placements[0]
        old_default = target_placement.with_pose(
            Pose.at(
                x=anchor.pose.position.x + 0.5,
                y=anchor.pose.position.y,
                z=anchor.pose.position.z,
            )
        )
        with pytest.raises(GameLifecycleError, match="overlaps another model"):
            apply_healing_revival_placement_decision(
                state=fixture.state,
                decisions=decisions,
                ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
                effect=placement_effect,
                result=_healing_revival_result(
                    request=placement_request,
                    placement=old_default,
                    result_id="tears-overlapping-default-placement-result",
                ),
            )
        assert decisions.queue.pending_requests == (placement_request,)
        _resolved, follow_up = apply_healing_revival_placement_decision(
            state=fixture.state,
            decisions=decisions,
            ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
            effect=placement_effect,
            result=_healing_revival_result(
                request=placement_request,
                placement=target_placement,
                result_id="tears-placement-result",
            ),
        )
        assert follow_up is None
    restored = _model_from_state(fixture.state, target_model.model_instance_id)
    if destroyed_model:
        assert restored.wounds_remaining == restored.starting_wounds
    else:
        assert restored.wounds_remaining <= restored.starting_wounds
    assert restored.wounds_remaining > (0 if destroyed_model else 1)
    selected_events = [
        event
        for event in decisions.event_log.records
        if event.event_type == CATALOG_COMMAND_RESTORATION_SELECTED_EVENT
    ]
    assert len(selected_events) == 1
    payload = cast(dict[str, Any], selected_events[0].payload)
    assert (payload["d3_result"] is None) is destroyed_model
    assert (
        runtime.request(
            CommandPhaseStartRequestContext(
                state=fixture.state,
                decisions=decisions,
                active_player_id="player-a",
            )
        )
        is None
    )


def test_tears_of_isha_revival_rejects_terrain_and_base_crossing_edge() -> None:
    terrain_fixture = _fixture(phase=BattlePhase.COMMAND)
    terrain_decisions, terrain_request, terrain_effect, terrain_placement = _start_tears_revival(
        fixture=terrain_fixture,
        target_rules_unit_id=terrain_fixture.wraith_construct.unit_instance_id,
    )
    terrain_pose = terrain_placement.pose.position
    terrain = TerrainFeatureDefinition(
        feature_id="tears-of-isha-adjacent-wall",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=terrain_pose.x,
        footprint_center_y_inches=terrain_pose.y,
        footprint_width_inches=1.0,
        footprint_depth_inches=1.0,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=terrain_pose.x,
            center_y_inches=terrain_pose.y,
            width_inches=1.0,
            depth_inches=1.0,
            display_template_id="tears-of-isha-adjacent-wall-display",
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="tears-of-isha-adjacent-wall-volume",
                center_x_inches=terrain_pose.x,
                center_y_inches=terrain_pose.y,
                bottom_z_inches=0.0,
                width_inches=0.5,
                depth_inches=1.0,
                height_inches=4.0,
            ),
        ),
        source_id="test:tears-of-isha-adjacent-terrain",
    )
    battlefield = terrain_fixture.state.battlefield_state
    assert battlefield is not None
    terrain_fixture.state.replace_battlefield_state(
        replace(battlefield, terrain_features=(*battlefield.terrain_features, terrain))
    )
    with pytest.raises(GameLifecycleError, match="intersects terrain"):
        apply_healing_revival_placement_decision(
            state=terrain_fixture.state,
            decisions=terrain_decisions,
            ruleset_descriptor=terrain_fixture.state.runtime_ruleset_descriptor(),
            effect=terrain_effect,
            result=_healing_revival_result(
                request=terrain_request,
                placement=terrain_placement,
                result_id="tears-terrain-placement-result",
            ),
        )
    assert terrain_decisions.queue.pending_requests == (terrain_request,)

    edge_fixture = _fixture(phase=BattlePhase.COMMAND)
    edge_decisions, edge_request, edge_effect, edge_placement = _start_tears_revival(
        fixture=edge_fixture,
        target_rules_unit_id=edge_fixture.wraith_construct.unit_instance_id,
    )
    with pytest.raises(GameLifecycleError, match="crosses the battlefield edge"):
        apply_healing_revival_placement_decision(
            state=edge_fixture.state,
            decisions=edge_decisions,
            ruleset_descriptor=edge_fixture.state.runtime_ruleset_descriptor(),
            effect=edge_effect,
            result=_healing_revival_result(
                request=edge_request,
                placement=edge_placement.with_pose(Pose.at(x=0.1, y=10.0)),
                result_id="tears-edge-placement-result",
            ),
        )
    assert edge_decisions.queue.pending_requests == (edge_request,)


def test_tears_of_isha_attached_wraith_revival_uses_component_ownership() -> None:
    fixture = _fixture(phase=BattlePhase.COMMAND, attach_spiritseer=True)
    decisions, request, effect, placement = _start_tears_revival(
        fixture=fixture,
        target_rules_unit_id=SPIRITSEER_ATTACHED_ID,
    )
    request_payload = cast(dict[str, Any], request.payload)
    assert request_payload["component_unit_instance_id"] == (
        fixture.wraith_construct.unit_instance_id
    )
    assert fixture.state.battlefield_state is not None
    wrong_component = fixture.state.battlefield_state.model_placement_by_id(
        fixture.spiritseer.own_models[0].model_instance_id
    )
    with pytest.raises(GameLifecycleError, match=r"attempted_placement unit drift|unit ownership"):
        apply_healing_revival_placement_decision(
            state=fixture.state,
            decisions=decisions,
            ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
            effect=effect,
            result=_healing_revival_result(
                request=request,
                placement=wrong_component,
                result_id="tears-attached-wrong-component-result",
            ),
        )
    assert decisions.queue.pending_requests == (request,)

    resolved, follow_up = apply_healing_revival_placement_decision(
        state=fixture.state,
        decisions=decisions,
        ruleset_descriptor=fixture.state.runtime_ruleset_descriptor(),
        effect=effect,
        result=_healing_revival_result(
            request=request,
            placement=placement,
            result_id="tears-attached-placement-result",
        ),
    )
    assert follow_up is None
    assert resolved.is_complete()
    restored = _model_from_state(fixture.state, placement.model_instance_id)
    assert restored.wounds_remaining == restored.starting_wounds
    assert fixture.state.battlefield_state is not None
    assert (
        fixture.state.battlefield_state.model_placement_by_id(
            placement.model_instance_id
        ).unit_instance_id
        == fixture.wraith_construct.unit_instance_id
    )


@dataclass(frozen=True, slots=True)
class _Fixture:
    armies: tuple[ArmyDefinition, ...]
    state: GameState
    indexes: dict[str, Any]
    howling_banshees: UnitInstance
    jain_zar: UnitInstance
    fire_dragons: UnitInstance
    fuegan: UnitInstance
    warp_spiders: UnitInstance
    lhykhis: UnitInstance
    spiritseer: UnitInstance
    wraith_construct: UnitInstance
    enemy: UnitInstance
    other_enemy: UnitInstance


def _fixture(*, phase: BattlePhase, attach_spiritseer: bool = False) -> _Fixture:
    package = _package()
    catalog = package.army_catalog
    factory = UnitFactory(catalog=catalog, model_geometries=package.model_geometries)
    howling_banshees = _instantiate(factory, "army-a", "banshees", HOWLING_BANSHEES_ID)
    jain_zar = _instantiate(factory, "army-a", "jain", JAIN_ZAR_ID)
    fire_dragons = _instantiate(factory, "army-a", "dragons", FIRE_DRAGONS_ID)
    fuegan = _instantiate(factory, "army-a", "fuegan", FUEGAN_ID)
    warp_spiders = _instantiate(factory, "army-a", "spiders", WARP_SPIDERS_ID)
    lhykhis = _instantiate(factory, "army-a", "lhykhis", LHYKHIS_ID)
    spiritseer = _instantiate(factory, "army-a", "spiritseer", SPIRITSEER_ID)
    wraith_construct = _instantiate(
        factory,
        "army-a",
        "wraithblades",
        WRAITHBLADES_ID,
    )
    enemy = _instantiate(factory, "army-b", "enemy", WRAITHLORD_ID)
    other_enemy = _instantiate(factory, "army-b", "other-enemy", FIRE_DRAGONS_ID)
    attached = (
        _attachment(JAIN_ATTACHED_ID, howling_banshees, jain_zar),
        _attachment(FUEGAN_ATTACHED_ID, fire_dragons, fuegan),
        _attachment(LHYKHIS_ATTACHED_ID, warp_spiders, lhykhis),
        *(
            (_attachment(SPIRITSEER_ATTACHED_ID, wraith_construct, spiritseer),)
            if attach_spiritseer
            else ()
        ),
    )
    armies = (
        _army(
            catalog,
            "army-a",
            "player-a",
            (
                howling_banshees,
                jain_zar,
                fire_dragons,
                fuegan,
                warp_spiders,
                lhykhis,
                spiritseer,
                wraith_construct,
            ),
            attached_units=attached,
        ),
        _army(catalog, "army-b", "player-b", (enemy, other_enemy)),
    )
    state = _state(armies, phase=phase)
    _move_unit(state, spiritseer.unit_instance_id, x=10.0, y=10.0)
    _move_unit(state, wraith_construct.unit_instance_id, x=13.0, y=10.0)
    _move_unit(state, enemy.unit_instance_id, x=15.0, y=10.0)
    _move_unit(state, other_enemy.unit_instance_id, x=30.0, y=30.0)
    records = catalog_ability_records_from_catalog(catalog)
    indexes = {
        army.player_id: build_player_ability_index(records, army=army, catalog=catalog)
        for army in armies
    }
    return _Fixture(
        armies=armies,
        state=state,
        indexes=indexes,
        howling_banshees=howling_banshees,
        jain_zar=jain_zar,
        fire_dragons=fire_dragons,
        fuegan=fuegan,
        warp_spiders=warp_spiders,
        lhykhis=lhykhis,
        spiritseer=spiritseer,
        wraith_construct=wraith_construct,
        enemy=enemy,
        other_enemy=other_enemy,
    )


def _state(armies: tuple[ArmyDefinition, ...], *, phase: BattlePhase) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    phases = tuple(descriptor.battle_phase_sequence.phases)
    state = GameState(
        game_id=f"aeldari-banshees-phoenix-lords-{phase.value}",
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
        battlefield_id=f"aeldari-banshees-phoenix-lords-{phase.value}-battlefield",
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
    army_id: str,
    selection_id: str,
    datasheet_id: str,
) -> UnitInstance:
    datasheet = factory.catalog.datasheet_by_id(datasheet_id)
    return factory.instantiate_unit(
        army_id=army_id,
        datasheet=datasheet,
        selection=UnitMusterSelection(
            unit_selection_id=selection_id,
            datasheet_id=datasheet_id,
            model_profile_selections=tuple(
                ModelProfileSelection(entry.model_profile_id, entry.min_models)
                for entry in datasheet.composition
            ),
        ),
    )


def _attachment(
    attached_id: str,
    bodyguard: UnitInstance,
    leader: UnitInstance,
) -> AttachedUnitFormation:
    return AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=tuple(
            sorted((bodyguard.unit_instance_id, leader.unit_instance_id))
        ),
        source_id=f"test:{attached_id}",
        attachment_source_ids=(f"test:{attached_id}:eligibility",),
    )


def _move_unit(state: GameState, unit_instance_id: str, *, x: float, y: float) -> None:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(model, pose=Pose.at(x=x, y=y + (index * 2.0)))
                    for index, model in enumerate(placement.model_placements)
                ),
            )
        )
    )


def _set_model_wounds(state: GameState, *, model_instance_id: str, wounds: int) -> None:
    found = False
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        units: list[UnitInstance] = []
        for unit in army.units:
            models = tuple(
                replace(model, wounds_remaining=wounds)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            found = found or models != unit.own_models
            units.append(replace(unit, own_models=models))
        updated_armies.append(replace(army, units=tuple(units)))
    assert found
    state.replace_army_definitions(updated_armies)


def _start_tears_revival(
    *,
    fixture: _Fixture,
    target_rules_unit_id: str,
) -> tuple[DecisionController, DecisionRequest, HealingEffect, ModelPlacement]:
    target_model = fixture.wraith_construct.own_models[0]
    placement = _remove_model(
        fixture.state,
        model_instance_id=target_model.model_instance_id,
    )
    runtime = CatalogCommandRestorationRuntime(fixture.indexes, fixture.armies)
    decisions = DecisionController()
    selection_request = runtime.request(
        CommandPhaseStartRequestContext(
            state=fixture.state,
            decisions=decisions,
            active_player_id="player-a",
        )
    )
    assert selection_request is not None
    decisions.request_decision(selection_request)
    option = next(
        option
        for option in selection_request.options
        if cast(dict[str, Any], option.payload)["target_unit_instance_id"] == target_rules_unit_id
    )
    selection_result = DecisionResult.for_request(
        result_id=f"tears-start:{target_rules_unit_id}",
        request=selection_request,
        selected_option_id=option.option_id,
    )
    decisions.submit_result(selection_result)
    assert runtime.apply_result(
        CommandPhaseStartResultContext(
            state=fixture.state,
            decisions=decisions,
            request=selection_request,
            result=selection_result,
            active_player_id="player-a",
        )
    )
    placement_request = decisions.queue.peek_next()
    assert placement_request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE
    return (
        decisions,
        placement_request,
        healing_effect_from_revival_request(request=placement_request),
        placement,
    )


def _healing_revival_result(
    *,
    request: DecisionRequest,
    placement: ModelPlacement,
    result_id: str,
) -> DecisionResult:
    return DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(
            {
                "proposal_request_id": request.request_id,
                "proposal_kind": "healing_revival_placement",
                "unit_instance_id": placement.unit_instance_id,
                "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
                "attempted_placement": UnitPlacement(
                    army_id=placement.army_id,
                    player_id=placement.player_id,
                    unit_instance_id=placement.unit_instance_id,
                    model_placements=(placement,),
                ).to_payload(),
            }
        ),
    )


def _remove_model(state: GameState, *, model_instance_id: str) -> ModelPlacement:
    assert state.battlefield_state is not None
    placement = state.battlefield_state.model_placement_by_id(model_instance_id)
    _set_model_wounds(state, model_instance_id=model_instance_id, wounds=0)
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models((model_instance_id,))
    )
    return placement


def _model_from_state(state: GameState, model_instance_id: str) -> Any:
    return next(
        model
        for army in state.army_definitions
        for unit in army.units
        for model in unit.own_models
        if model.model_instance_id == model_instance_id
    )


def _pending_movement_action(
    unit_instance_id: str,
    *,
    movement_action: MovementPhaseActionKind = MovementPhaseActionKind.NORMAL_MOVE,
) -> PendingMovementActionSelection:
    movement_mode = {
        MovementPhaseActionKind.REMAIN_STATIONARY: MovementMode.NORMAL,
        MovementPhaseActionKind.NORMAL_MOVE: MovementMode.NORMAL,
        MovementPhaseActionKind.ADVANCE: MovementMode.ADVANCE,
        MovementPhaseActionKind.FALL_BACK: MovementMode.FALL_BACK,
    }[movement_action]
    return PendingMovementActionSelection(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_phase_action=movement_action,
        movement_mode=movement_mode,
        fall_back_mode=(
            FallBackModeKind.ORDERED_RETREAT
            if movement_action is MovementPhaseActionKind.FALL_BACK
            else None
        ),
        request_id="movement-action-request",
        result_id="movement-action-result",
        selected_option_id=movement_action.value,
    )


def _movement_state(pending: PendingMovementActionSelection) -> MovementPhaseState:
    selection = MovementUnitSelection(
        player_id=pending.player_id,
        battle_round=pending.battle_round,
        unit_instance_id=pending.unit_instance_id,
        request_id="movement-unit-request",
        result_id="movement-unit-result",
    )
    return MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=(pending.unit_instance_id,),
        active_selection=selection,
        pending_action=pending,
    )


def _record_move_completed_event(
    *,
    state: GameState,
    decisions: DecisionController,
    event_type: str,
    movement_action: str,
    unit_instance_id: str,
) -> None:
    decisions.event_log.append(
        event_type,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": "player-a",
            "unit_instance_id": unit_instance_id,
            "movement_phase_action": movement_action,
        },
    )


def _rule_ir(source_row_id: str) -> RuleIR:
    payload = source_package.datasheet_rule_ir_payload_by_source_row_id(source_row_id)
    assert payload is not None
    return RuleIR.from_payload(payload)


def _characteristics(profile: Any) -> tuple[int, ...]:
    values = {value.characteristic: value.final for value in profile.characteristics}
    return (
        values[Characteristic.MOVEMENT],
        values[Characteristic.TOUGHNESS],
        values[Characteristic.SAVE],
        values[Characteristic.WOUNDS],
        values[Characteristic.LEADERSHIP],
        values[Characteristic.OBJECTIVE_CONTROL],
        values[Characteristic.INVULNERABLE_SAVE],
    )


def _leader_target_ids(datasheet: Any) -> set[str]:
    return {
        target.bodyguard_datasheet_id
        for eligibility in datasheet.attachment_eligibilities
        for target in eligibility.targets
    }


def _melta_profile(datasheet_id: str) -> WeaponProfile:
    return next(
        cast(WeaponProfile, profile)
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id.startswith(f"{datasheet_id}:")
        for profile in wargear.weapon_profiles
        if WeaponKeyword.MELTA in profile.keywords
    )


def _first_weapon_profile(unit: UnitInstance) -> WeaponProfile:
    wargear_ids = set(unit.own_models[0].wargear_ids)
    return next(
        cast(WeaponProfile, profile)
        for wargear in _package().army_catalog.wargear
        if wargear.wargear_id in wargear_ids
        for profile in wargear.weapon_profiles
    )
