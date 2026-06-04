from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.ruleset_descriptor import (
    MissionPolicyDescriptor,
    ReserveDestructionTimingKind,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    COMPLETE_REINFORCEMENTS_OPTION_ID,
    PLACE_REINFORCEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementPhaseStepKind,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS,
    BattlefieldEdge,
    LargeModelReservePlacementException,
    ReinforcementPlacement,
    ReserveArrivalCandidate,
    ReserveDestructionResult,
    ReserveDestructionResultPayload,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReservePlacementViolation,
    ReservePlacementViolationCode,
    ReservePostArrivalRestriction,
    ReserveState,
    ReserveStatus,
    StrategicReserveDeclaration,
    StrategicReserveRule,
    apply_reinforcement_placement_to_battlefield,
    apply_reserve_destruction_to_battlefield,
    battle_phase_token,
    battlefield_edge_from_token,
    reserve_kind_from_token,
    reserve_origin_from_token,
    reserve_placement_violation_code_from_token,
    reserve_post_arrival_restriction_from_token,
    reserve_status_from_token,
    resolve_reserve_arrival,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.unit_coherency import UnitCoherencyResult
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_movement_phase_requests_reserve_arrivals_inside_move_units() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    placed_unit_id = "army-alpha:intercessor-unit-2"
    state.movement_phase_state = MovementPhaseState(
        battle_round=1,
        active_player_id="player-a",
        selected_unit_ids=(placed_unit_id,),
        moved_unit_ids=(placed_unit_id,),
    )
    decisions = DecisionController()

    status = MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
        state=state,
        decisions=decisions,
    )

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    payload = cast(dict[str, object], status.payload)
    assert payload["step"] == MovementPhaseStepKind.MOVE_UNITS.value
    assert payload["phase_body_status"] == "move_units_waiting_for_arrival_choice"
    assert payload["unarrived_reserve_count"] == 1
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    request_payload = cast(dict[str, object], status.decision_request.payload)
    assert request_payload["step"] == MovementPhaseStepKind.MOVE_UNITS.value
    assert {option.option_id for option in status.decision_request.options} == {
        COMPLETE_REINFORCEMENTS_OPTION_ID,
        reserve_state.unit_instance_id,
    }
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.step is MovementPhaseStepKind.MOVE_UNITS
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_reinforcements_valid_strategic_reserves_arrival_mutates_state_atomically() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=3,
    )
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=reserve_state.unit_instance_id,
        result_id="phase10p-select-strategic",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == PLACE_REINFORCEMENT_UNIT_DECISION_TYPE

    result_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        option_id=BattlefieldPlacementKind.STRATEGIC_RESERVES.value,
        result_id="phase10p-place-strategic",
    )
    if result_status is None:
        result_status = handler.begin_phase(state=state, decisions=decisions)

    assert result_status.status_kind is LifecycleStatusKind.ADVANCED
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(reserve_unit.unit_instance_id)
    arrived_state = state.reserve_state_for_unit(reserve_state.unit_instance_id)
    assert arrived_state is not None
    assert arrived_state.status is ReserveStatus.ARRIVED
    assert arrived_state.arrived_phase == BattlePhase.MOVEMENT.value
    assert state.movement_phase_state is not None
    assert reserve_state.unit_instance_id in state.movement_phase_state.moved_unit_ids
    arrival_event = _last_event_payload(decisions, "reinforcement_unit_arrived")
    assert arrival_event["placement_kind"] == BattlefieldPlacementKind.STRATEGIC_RESERVES.value
    transition_batch = arrival_event["transition_batch"]
    assert isinstance(transition_batch, dict)
    placements = cast(list[dict[str, object]], transition_batch["placements"])
    assert placements[0]["placement_kind"] == BattlefieldPlacementKind.STRATEGIC_RESERVES.value


def test_reinforcements_valid_deep_strike_uses_deep_strike_placement_record() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    state.army_definitions = list(
        _with_replaced_unit(tuple(state.army_definitions), deep_strike_unit)
    )
    deep_strike_state = replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE)
    state.replace_reserve_state(deep_strike_state)
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=1,
    )
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=deep_strike_state.unit_instance_id,
        result_id="phase10p-select-deep-strike",
    )
    placement_request = _decision_request(placement_status)

    result_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        option_id=BattlefieldPlacementKind.DEEP_STRIKE.value,
        result_id="phase10p-place-deep-strike",
    )
    if result_status is None:
        result_status = handler.begin_phase(state=state, decisions=decisions)

    assert result_status.status_kind is LifecycleStatusKind.ADVANCED
    arrival_event = _last_event_payload(decisions, "reinforcement_unit_arrived")
    transition_batch = arrival_event["transition_batch"]
    assert isinstance(transition_batch, dict)
    placements = cast(list[dict[str, object]], transition_batch["placements"])
    assert placements[0]["placement_kind"] == BattlefieldPlacementKind.DEEP_STRIKE.value
    assert placements[0]["source_rule_id"] == "deep_strike"


def test_reinforcements_invalid_arrival_does_not_mutate_state() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    before_battlefield = state.battlefield_state.to_payload() if state.battlefield_state else None
    before_reserve_state = reserve_state
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=1,
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    placement_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=reserve_state.unit_instance_id,
        result_id="phase10p-select-invalid",
    )
    placement_request = _decision_request(placement_status)

    invalid_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        option_id=BattlefieldPlacementKind.STRATEGIC_RESERVES.value,
        result_id="phase10p-place-invalid",
    )

    assert invalid_status is not None
    assert invalid_status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == before_reserve_state


def test_reinforcements_completion_choice_leaves_reserve_unarrived_and_advances_phase() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    _set_movement_ready_for_reinforcements(state=state, battle_round=3)
    flow = BattleRoundFlow(phase_handlers={BattlePhase.MOVEMENT: handler})
    selection_status = flow.advance(state=state, decisions=decisions)
    selection_request = _decision_request(selection_status)

    decision_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
        result_id="phase10p-complete-reinforcements",
    )
    assert decision_status is None
    advanced_status = flow.advance(state=state, decisions=decisions)

    assert advanced_status.status_kind is LifecycleStatusKind.ADVANCED
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert state.reserve_state_for_unit(reserve_state.unit_instance_id) == reserve_state


def test_oversized_strategic_reserve_model_can_touch_required_edge() -> None:
    state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert result.is_valid
    assert result.transition_batch is not None
    assert {record.placement_kind for record in result.transition_batch.placements} == {
        BattlefieldPlacementKind.STRATEGIC_RESERVES
    }
    arrived_state = result.arrived_reserve_state()
    assert arrived_state.large_model_exception_used
    assert set(arrived_state.post_arrival_restrictions) == set(
        LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS
    )
    assert state.battlefield_state is not None
    updated_battlefield = apply_reinforcement_placement_to_battlefield(
        battlefield_state=state.battlefield_state,
        placement=result,
    )
    assert updated_battlefield.unit_placement_by_id(reserve_unit.unit_instance_id) == placement


def test_oversized_strategic_reserve_exception_still_rejects_enemy_distance() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    pose = _south_edge_touching_pose(base_diameter_mm=200.0, x=15.0)
    enemy_model_id = (
        scenario.army_by_id("army-beta")
        .unit_by_id("army-beta:intercessor-unit-3")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=enemy_model_id,
        pose=Pose.at(x=15.0, y=16.0, z=0.0, facing_degrees=180.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=pose,
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert not result.is_valid
    assert _violation_codes(result) == (ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,)


def test_strategic_reserves_enemy_distance_message_is_limit_agnostic() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    reserve_pose = _south_edge_touching_pose(base_diameter_mm=32.0, x=15.0)
    enemy_model_id = (
        scenario.army_by_id("army-beta")
        .unit_by_id("army-beta:intercessor-unit-3")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=enemy_model_id,
        pose=Pose.at(
            x=reserve_pose.position.x + (radius * 2.0) + 0.25,
            y=reserve_pose.position.y,
            z=10.0,
            facing_degrees=180.0,
        ),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=reserve_pose,
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        strategic_reserve_rule=StrategicReserveRule(enemy_horizontal_distance_inches=0.5),
    )

    distance_violations = tuple(
        violation
        for violation in result.violations
        if violation.violation_code is ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE
    )
    assert len(distance_violations) == 1
    assert distance_violations[0].message == (
        "Reserve placement is within the configured reserve enemy-distance limit."
    )


def test_strategic_reserves_reject_setup_within_enemy_engagement_range() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    reserve_pose = _south_edge_touching_pose(base_diameter_mm=32.0, x=15.0)
    enemy_model_id = (
        scenario.army_by_id("army-beta")
        .unit_by_id("army-beta:intercessor-unit-3")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=enemy_model_id,
        pose=Pose.at(
            x=reserve_pose.position.x + (radius * 2.0) + 0.75,
            y=reserve_pose.position.y,
            z=3.0,
            facing_degrees=180.0,
        ),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=reserve_pose,
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        strategic_reserve_rule=StrategicReserveRule(enemy_horizontal_distance_inches=0.5),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.RESERVE_ENEMY_ENGAGEMENT_RANGE in codes
    assert ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE not in codes


def test_oversized_exception_preserves_other_placement_limits() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=200.0,
        reserve_model_count=2,
    )
    large_pose = _south_edge_touching_pose(base_diameter_mm=200.0, x=15.0)
    blocker_model_id = (
        scenario.army_by_id("army-alpha")
        .unit_by_id("army-alpha:intercessor-unit-2")
        .own_models[0]
        .model_instance_id
    )
    scenario = _with_model_pose(
        scenario,
        model_instance_id=blocker_model_id,
        pose=large_pose,
    )
    placement = _reserve_placement(
        reserve_unit=reserve_unit,
        poses=(
            large_pose,
            _south_edge_touching_pose(base_diameter_mm=32.0, x=50.0),
        ),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        enemy_deployment_zones=(
            DeploymentZone(
                deployment_zone_id="enemy-south-zone",
                player_id="player-b",
                min_x=0.0,
                min_y=0.0,
                max_x=60.0,
                max_y=10.0,
            ),
        ),
        terrain_features=(_blocking_wall_feature(x=15.0, y=large_pose.position.y),),
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_ENEMY_DEPLOYMENT_ZONE in codes
    assert ReservePlacementViolationCode.MODEL_OVERLAP in codes
    assert ReservePlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL in codes
    assert ReservePlacementViolationCode.UNIT_COHERENCY_BROKEN in codes


def test_model_that_fits_cannot_use_large_model_exception_for_extra_positioning() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=Pose.at(x=15.0, y=6.5 + radius, z=0.0, facing_degrees=0.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert not result.is_valid
    assert ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_MODEL_CAN_FIT in set(
        _violation_codes(result)
    )


def test_large_model_exception_records_all_turn_restrictions() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert set(result.post_arrival_restrictions) == {
        ReservePostArrivalRestriction.NO_NORMAL_MOVE,
        ReservePostArrivalRestriction.NO_ADVANCE,
        ReservePostArrivalRestriction.NO_FALL_BACK,
        ReservePostArrivalRestriction.NO_REMAIN_STATIONARY,
        ReservePostArrivalRestriction.NO_RANGED_ATTACKS,
        ReservePostArrivalRestriction.NO_CHARGE,
    }


def test_core_policy_destroys_unarrived_reserves_only_at_end_of_battle() -> None:
    _state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    policy = ReserveDestructionTimingPolicy.from_mission_policy(_ruleset().mission_policy)

    round_three = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=policy,
        battle_round=3,
        end_of_battle=False,
    )
    end_battle = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=policy,
        battle_round=5,
        end_of_battle=True,
    )

    assert round_three.destroyed_unit_instance_ids == ()
    assert end_battle.destroyed_unit_instance_ids == (reserve_state.unit_instance_id,)


def test_chapter_approved_policy_destroys_declare_battle_formation_reserves_at_br3() -> None:
    _state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    policy = ReserveDestructionTimingPolicy.from_mission_policy(
        _chapter_approved_ruleset().mission_policy
    )

    result = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=policy,
        battle_round=3,
        end_of_battle=False,
    )

    assert result.destroyed_unit_instance_ids == (reserve_state.unit_instance_id,)
    assert result.updated_reserve_states[0].destroyed_battle_round == 3


def test_chapter_approved_policy_destroys_embarked_units_in_unarrived_transport() -> None:
    state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    embarked_unit_id = "army-alpha:intercessor-unit-2"
    scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.without_unit_placement(embarked_unit_id),
    )
    reserve_state = replace(
        reserve_state,
        embarked_unit_instance_ids=(embarked_unit_id,),
    )
    state.replace_reserve_state(reserve_state)

    result = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _chapter_approved_ruleset().mission_policy
        ),
        battle_round=3,
        end_of_battle=False,
    )

    assert set(result.destroyed_unit_instance_ids) == {
        reserve_state.unit_instance_id,
        embarked_unit_id,
    }


def test_chapter_approved_policy_exempts_during_battle_strategic_reserves_at_br3() -> None:
    _state, scenario, reserve_state, _reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    during_battle_state = replace(
        reserve_state,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        declared_during_step=None,
        entered_reserves_battle_round=2,
        entered_reserves_phase=BattlePhase.MOVEMENT.value,
    )

    result = resolve_unarrived_reserve_destruction(
        reserve_states=(during_battle_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _chapter_approved_ruleset().mission_policy
        ),
        battle_round=3,
        end_of_battle=False,
    )

    assert result.destroyed_unit_instance_ids == ()
    assert result.updated_reserve_states == (during_battle_state,)


def test_reserve_origin_source_serializes_for_replay() -> None:
    state, _scenario, reserve_state, _reserve_unit = _battle_state_with_reserve()
    during_battle_state = ReserveState(
        player_id="player-b",
        unit_instance_id="army-beta:intercessor-unit-3",
        reserve_origin=ReserveOrigin.DURING_BATTLE_STRATAGEM,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        declared_during_step=None,
        entered_reserves_battle_round=2,
        entered_reserves_phase=BattlePhase.MOVEMENT.value,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default(),
    )
    state.record_reserve_state(during_battle_state)
    payload = state.to_payload()
    decoded = cast(GameStatePayload, json.loads(json.dumps(payload, sort_keys=True)))

    restored = GameState.from_payload(decoded)

    restored_declared_state = restored.reserve_state_for_unit(reserve_state.unit_instance_id)
    restored_during_battle_state = restored.reserve_state_for_unit(
        during_battle_state.unit_instance_id
    )
    assert restored_declared_state is not None
    assert restored_during_battle_state is not None
    assert restored_declared_state.reserve_origin is ReserveOrigin.DECLARE_BATTLE_FORMATIONS
    assert restored_during_battle_state.reserve_origin is ReserveOrigin.DURING_BATTLE_STRATAGEM
    assert restored_during_battle_state.entered_reserves_battle_round == 2


def test_phase10p_reserve_payloads_round_trip_without_object_repr() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    assert result.is_valid
    arrived_state = result.arrived_reserve_state()
    destroyed_state = reserve_state.mark_destroyed(battle_round=3)
    declaration = StrategicReserveDeclaration.for_unit(
        unit=reserve_unit,
        player_id="player-a",
        unit_points=100,
        embarked_unit_points=25,
        points_limit=200,
        embarked_unit_instance_ids=("army-alpha:intercessor-unit-2",),
    )
    violation = ReservePlacementViolation(
        violation_code=ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,
        message="enemy-distance",
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        blocker_id="enemy-model",
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    destruction = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=5,
        end_of_battle=True,
    )

    policy_payload = ReserveDestructionTimingPolicy.chapter_approved_2025_26().to_payload()
    assert (
        ReserveDestructionTimingPolicy.from_payload(policy_payload).to_payload() == policy_payload
    )
    assert ReserveState.from_payload(arrived_state.to_payload()).to_payload() == (
        arrived_state.to_payload()
    )
    assert ReserveState.from_payload(destroyed_state.to_payload()).to_payload() == (
        destroyed_state.to_payload()
    )
    assert StrategicReserveDeclaration.from_payload(declaration.to_payload()).to_payload() == (
        declaration.to_payload()
    )
    assert (
        declaration.to_reserve_state(
            destruction_deadline_policy=ReserveDestructionTimingPolicy.core_rules_default()
        ).reserve_kind
        is ReserveKind.STRATEGIC_RESERVES
    )
    assert (
        LargeModelReservePlacementException.from_payload(large_exception.to_payload()).to_payload()
        == large_exception.to_payload()
    )
    assert ReservePlacementViolation.from_payload(violation.to_payload()).to_payload() == (
        violation.to_payload()
    )
    assert ReserveArrivalCandidate.from_payload(result.candidate.to_payload()).to_payload() == (
        result.candidate.to_payload()
    )
    destruction_payload = cast(
        ReserveDestructionResultPayload,
        json.loads(json.dumps(destruction.to_payload(), sort_keys=True)),
    )
    assert destruction_payload == destruction.to_payload()
    encoded = json.dumps(result.to_payload(), sort_keys=True)
    assert "object at 0x" not in encoded
    assert "<" not in encoded


def test_phase10p_reserve_domain_validators_are_fail_fast() -> None:
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
    )

    with pytest.raises(GameLifecycleError, match="must not set battle_round"):
        ReserveDestructionTimingPolicy(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE,
            battle_round=3,
        )
    with pytest.raises(GameLifecycleError, match="requires battle_round"):
        ReserveDestructionTimingPolicy(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N,
            battle_round=None,
        )
    with pytest.raises(GameLifecycleError, match="must not have arrival fields"):
        replace(reserve_state, arrived_battle_round=2, arrived_phase=BattlePhase.MOVEMENT.value)
    with pytest.raises(GameLifecycleError, match="Arrived ReserveState requires arrival fields"):
        replace(reserve_state, status=ReserveStatus.ARRIVED)
    with pytest.raises(GameLifecycleError, match="Destroyed ReserveState requires"):
        replace(reserve_state, status=ReserveStatus.DESTROYED)
    with pytest.raises(GameLifecycleError, match="must not keep restrictions"):
        replace(
            reserve_state,
            status=ReserveStatus.DESTROYED,
            destroyed_battle_round=3,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
            restriction_battle_round=3,
        )
    with pytest.raises(GameLifecycleError, match="restrictions require"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
        )
    with pytest.raises(GameLifecycleError, match="Large-model ReserveState"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            large_model_exception_used=True,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
            restriction_battle_round=3,
        )


def test_phase10p_strategic_reserve_declaration_rejects_forbidden_inputs() -> None:
    _state, _scenario, _reserve_state, reserve_unit = _battle_state_with_reserve()

    with pytest.raises(GameLifecycleError, match="FORTIFICATIONS"):
        StrategicReserveDeclaration(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            declared_during_step="declare_battle_formations",
            unit_points=100,
            embarked_unit_points=0,
            points_limit=200,
            has_fortification_keyword=True,
        )
    with pytest.raises(GameLifecycleError, match="exceeds points limit"):
        StrategicReserveDeclaration(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            declared_during_step="declare_battle_formations",
            unit_points=175,
            embarked_unit_points=50,
            points_limit=200,
        )
    with pytest.raises(GameLifecycleError, match="requires a UnitInstance"):
        StrategicReserveDeclaration.for_unit(
            unit=cast(UnitInstance, object()),
            player_id="player-a",
            unit_points=100,
            embarked_unit_points=0,
            points_limit=200,
        )


def test_phase10p_reserve_token_parsers_reject_unsupported_tokens() -> None:
    with pytest.raises(GameLifecycleError, match="ReserveKind token must be a string"):
        reserve_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveKind"):
        reserve_kind_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReserveOrigin token must be a string"):
        reserve_origin_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveOrigin"):
        reserve_origin_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReserveStatus token must be a string"):
        reserve_status_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReserveStatus"):
        reserve_status_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="BattlefieldEdge token must be a string"):
        battlefield_edge_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported BattlefieldEdge"):
        battlefield_edge_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReservePostArrivalRestriction token"):
        reserve_post_arrival_restriction_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReservePostArrivalRestriction"):
        reserve_post_arrival_restriction_from_token("unknown")
    with pytest.raises(GameLifecycleError, match="ReservePlacementViolationCode token"):
        reserve_placement_violation_code_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported ReservePlacementViolationCode"):
        reserve_placement_violation_code_from_token("unknown")


def test_phase10p_reserve_arrival_invalid_state_and_edge_paths_are_typed() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )

    br1_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    kind_mismatch_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=replace(reserve_state, reserve_kind=ReserveKind.RESERVES),
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    destroyed_state_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state.mark_destroyed(battle_round=3),
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    missing_exception_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=3.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id="missing-reserve-model",
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )
    contact_missing_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=5.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )

    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1 in set(
        _violation_codes(br1_result)
    )
    assert ReservePlacementViolationCode.RESERVE_KIND_MISMATCH in set(
        _violation_codes(kind_mismatch_result)
    )
    assert ReservePlacementViolationCode.RESERVE_STATE_NOT_UNARRIVED in set(
        _violation_codes(destroyed_state_result)
    )
    assert ReservePlacementViolationCode.UNIT_PLACEMENT_DRIFT in set(
        _violation_codes(missing_exception_result)
    )
    assert ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_EDGE_CONTACT_MISSING in set(
        _violation_codes(contact_missing_result)
    )
    with pytest.raises(GameLifecycleError, match="cannot mark arrival"):
        br1_result.arrived_reserve_state()
    with pytest.raises(GameLifecycleError, match="Invalid reserve placement"):
        apply_reinforcement_placement_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            placement=br1_result,
        )


def test_phase10p_regular_models_must_remain_wholly_inside_edge_band() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        reserve_base_diameter_mm=32.0,
    )
    radius = _base_radius_inches(32.0)
    edge_crossing_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=radius - 0.1, y=radius, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    unneeded_exception_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=3.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )
    outside_band_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=Pose.at(x=15.0, y=8.0, z=0.0, facing_degrees=0.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )

    assert ReservePlacementViolationCode.BATTLEFIELD_EDGE_CROSSED in set(
        _violation_codes(edge_crossing_result)
    )
    assert ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_UNNEEDED in set(
        _violation_codes(unneeded_exception_result)
    )
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_EDGE_DISTANCE in set(
        _violation_codes(outside_band_result)
    )


def test_phase10p_deep_strike_requires_keyword_and_uses_same_arrival_path() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    deep_strike_state = replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE)
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )

    missing_keyword = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=deep_strike_state,
        attempted_placement=placement,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    deep_strike_scenario = BattlefieldScenario(
        armies=_with_replaced_unit(scenario.armies, deep_strike_unit),
        battlefield_state=scenario.battlefield_state,
    )
    valid = resolve_reserve_arrival(
        scenario=deep_strike_scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=deep_strike_state,
        attempted_placement=placement,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert ReservePlacementViolationCode.DEEP_STRIKE_KEYWORD_REQUIRED in set(
        _violation_codes(missing_keyword)
    )
    assert valid.is_valid
    assert valid.transition_batch is not None
    assert {record.source_rule_id for record in valid.transition_batch.placements} == {
        "deep_strike"
    }


def test_chapter_approved_declared_deep_strike_cannot_arrive_in_battle_round_1() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    deep_strike_scenario = BattlefieldScenario(
        armies=_with_replaced_unit(scenario.armies, deep_strike_unit),
        battlefield_state=scenario.battlefield_state,
    )
    result = resolve_reserve_arrival(
        scenario=deep_strike_scenario,
        ruleset_descriptor=_chapter_approved_ruleset(),
        reserve_state=replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE),
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=deep_strike_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN in set(
        _violation_codes(result)
    )


def test_chapter_approved_declared_strategic_reserves_cannot_arrive_in_battle_round_1() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_chapter_approved_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN in codes
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1 in codes


def test_chapter_approved_during_battle_strategic_reserves_arrival_exemption_is_honored() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve(
        ruleset_descriptor=_chapter_approved_ruleset(),
    )
    during_battle_state = replace(
        reserve_state,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        declared_during_step=None,
        entered_reserves_battle_round=1,
        entered_reserves_phase=BattlePhase.MOVEMENT.value,
    )
    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_chapter_approved_ruleset(),
        reserve_state=during_battle_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    codes = set(_violation_codes(result))
    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN not in codes
    assert ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1 in codes


def test_core_rules_deep_strike_has_no_mission_pack_battle_round_1_block() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    deep_strike_unit = replace(reserve_unit, keywords=(*reserve_unit.keywords, "DEEP_STRIKE"))
    deep_strike_scenario = BattlefieldScenario(
        armies=_with_replaced_unit(scenario.armies, deep_strike_unit),
        battlefield_state=scenario.battlefield_state,
    )
    result = resolve_reserve_arrival(
        scenario=deep_strike_scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=replace(reserve_state, reserve_kind=ReserveKind.DEEP_STRIKE),
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=deep_strike_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=1,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE,
    )

    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN not in set(
        _violation_codes(result)
    )
    assert result.is_valid


def test_reserve_arrival_with_embarked_units_is_deferred_until_transport_cargo_state() -> None:
    state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    cargo_reserve_state = replace(
        reserve_state,
        embarked_unit_instance_ids=("army-alpha:intercessor-unit-2",),
    )
    state.replace_reserve_state(cargo_reserve_state)
    before_battlefield = state.battlefield_state.to_payload() if state.battlefield_state else None

    result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=cargo_reserve_state,
        attempted_placement=_single_model_reserve_placement(
            reserve_unit=reserve_unit,
            pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
        ),
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                battlefield_edge=BattlefieldEdge.SOUTH,
            ),
        ),
    )

    assert ReservePlacementViolationCode.RESERVE_EMBARKED_CARGO_UNSUPPORTED in set(
        _violation_codes(result)
    )
    assert not result.is_valid
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == before_battlefield
    assert state.reserve_state_for_unit(cargo_reserve_state.unit_instance_id) == cargo_reserve_state


def test_replay_load_rejects_arrived_reserve_with_unaccounted_embarked_units() -> None:
    state, _scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    embarked_unit_id = "army-alpha:intercessor-unit-2"
    assert state.battlefield_state is not None
    parent_placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        embarked_unit_id
    ).with_added_unit_placement(parent_placement)
    state.replace_reserve_state(
        replace(
            reserve_state,
            embarked_unit_instance_ids=(embarked_unit_id,),
        ).mark_arrived(
            battle_round=3,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    )
    payload = cast(
        GameLifecyclePayload,
        {
            "config": None,
            "parameterized_movement_proposals": False,
            "state": state.to_payload(),
            "decisions": DecisionController().to_payload(),
            "reaction_queue": {"frames": []},
        },
    )

    with pytest.raises(GameLifecycleError, match="battlefield_state is invalid"):
        GameLifecycle.from_payload(payload)


def test_phase10p_reserve_destruction_application_marks_unplaced_models_removed() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    result = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=5,
        end_of_battle=True,
    )

    updated = apply_reserve_destruction_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        destruction=result,
    )
    unchanged = apply_reserve_destruction_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        destruction=resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=3,
            end_of_battle=False,
        ),
    )

    assert set(updated.removed_model_ids) == {
        model.model_instance_id for model in reserve_unit.own_models
    }
    assert unchanged is scenario.battlefield_state


def test_phase10p_reserve_type_guards_are_fail_fast() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    valid_result = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=placement,
        battle_round=3,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(large_exception,),
    )
    transition_batch = valid_result.transition_batch
    assert transition_batch is not None
    violation = ReservePlacementViolation(
        violation_code=ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,
        message="enemy-distance",
    )

    with pytest.raises(GameLifecycleError, match="MissionPolicyDescriptor"):
        ReserveDestructionTimingPolicy.from_mission_policy(cast(MissionPolicyDescriptor, object()))
    with pytest.raises(GameLifecycleError, match="reserve_state must be a ReserveState"):
        ReserveDestructionTimingPolicy.core_rules_default().applies_to_reserve_state(
            cast(ReserveState, object())
        )
    with pytest.raises(GameLifecycleError, match="destruction_deadline_policy"):
        replace(
            reserve_state,
            destruction_deadline_policy=cast(ReserveDestructionTimingPolicy, object()),
        )
    with pytest.raises(GameLifecycleError, match="must not have destruction fields"):
        replace(reserve_state, destroyed_battle_round=3)
    with pytest.raises(GameLifecycleError, match="must not have destruction fields"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            destroyed_battle_round=3,
        )
    with pytest.raises(GameLifecycleError, match="must not contain duplicates"):
        replace(
            reserve_state,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=3,
            arrived_phase=BattlePhase.MOVEMENT.value,
            post_arrival_restrictions=(
                ReservePostArrivalRestriction.NO_CHARGE,
                ReservePostArrivalRestriction.NO_CHARGE,
            ),
            restriction_battle_round=3,
        )
    arrived_state = valid_result.arrived_reserve_state()
    assert (
        arrived_state.clear_expired_post_arrival_restrictions(
            player_id="player-b",
            battle_round=3,
        )
        is arrived_state
    )
    assert (
        arrived_state.clear_expired_post_arrival_restrictions(
            player_id="player-a",
            battle_round=3,
        ).post_arrival_restrictions
        == ()
    )
    with pytest.raises(GameLifecycleError, match="battle_phase must be a string"):
        battle_phase_token(1)

    with pytest.raises(GameLifecycleError, match="ReserveArrivalCandidate reserve_state"):
        ReserveArrivalCandidate(
            reserve_state=cast(ReserveState, object()),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placement,
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="attempted_placement"):
        ReserveArrivalCandidate(
            reserve_state=reserve_state,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=cast(UnitPlacement, object()),
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="placement unit drift"):
        ReserveArrivalCandidate(
            reserve_state=replace(reserve_state, unit_instance_id="army-alpha:missing-unit"),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placement,
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="placement player drift"):
        ReserveArrivalCandidate(
            reserve_state=replace(reserve_state, player_id="player-b"),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placement,
            qualifying_edges=(BattlefieldEdge.SOUTH,),
        )
    with pytest.raises(GameLifecycleError, match="qualifying_edges must be a tuple"):
        ReserveArrivalCandidate(
            reserve_state=reserve_state,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placement,
            qualifying_edges=cast(tuple[BattlefieldEdge, ...], [BattlefieldEdge.SOUTH]),
        )
    with pytest.raises(GameLifecycleError, match="qualifying_edges must not contain duplicates"):
        ReserveArrivalCandidate(
            reserve_state=reserve_state,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            attempted_placement=placement,
            qualifying_edges=(BattlefieldEdge.SOUTH, BattlefieldEdge.SOUTH),
        )

    with pytest.raises(GameLifecycleError, match="ReinforcementPlacement candidate"):
        ReinforcementPlacement(
            candidate=cast(ReserveArrivalCandidate, object()),
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="coherency_result"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=cast(UnitCoherencyResult, object()),
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="transition_batch"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=cast(BattlefieldTransitionBatch, object()),
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="cannot have transitions"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(violation,),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="requires transitions"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=None,
            large_model_exception_used=False,
            post_arrival_restrictions=(),
        )
    with pytest.raises(GameLifecycleError, match="must apply all turn restrictions"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=True,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
        )
    with pytest.raises(GameLifecycleError, match="restrictions require"):
        ReinforcementPlacement(
            candidate=valid_result.candidate,
            violations=(),
            coherency_result=valid_result.coherency_result,
            transition_batch=transition_batch,
            large_model_exception_used=False,
            post_arrival_restrictions=(ReservePostArrivalRestriction.NO_CHARGE,),
        )

    with pytest.raises(GameLifecycleError, match="ReserveDestructionResult policy"):
        ReserveDestructionResult(
            policy=cast(ReserveDestructionTimingPolicy, object()),
            battle_round=3,
            end_of_battle=False,
            destroyed_unit_instance_ids=(),
            destroyed_model_instance_ids=(),
            transition_batch=BattlefieldTransitionBatch(),
            updated_reserve_states=(),
        )
    with pytest.raises(GameLifecycleError, match="transition_batch"):
        ReserveDestructionResult(
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=3,
            end_of_battle=False,
            destroyed_unit_instance_ids=(),
            destroyed_model_instance_ids=(),
            transition_batch=cast(BattlefieldTransitionBatch, object()),
            updated_reserve_states=(),
        )


def test_phase10p_reserve_resolution_type_guards_are_fail_fast() -> None:
    _state, scenario, reserve_state, reserve_unit = _battle_state_with_reserve()
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(base_diameter_mm=200.0, x=15.0),
    )
    large_exception = LargeModelReservePlacementException(
        model_instance_id=reserve_unit.own_models[0].model_instance_id,
        battlefield_edge=BattlefieldEdge.SOUTH,
    )
    destruction = resolve_unarrived_reserve_destruction(
        reserve_states=(reserve_state,),
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state,
        policy=ReserveDestructionTimingPolicy.core_rules_default(),
        battle_round=5,
        end_of_battle=True,
    )

    with pytest.raises(GameLifecycleError, match="scenario must be a scenario"):
        resolve_reserve_arrival(
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="RulesetDescriptor"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="reserve_state must be ReserveState"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=cast(ReserveState, object()),
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="attempted_placement"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=cast(UnitPlacement, object()),
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="battle_round must be at least 1"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=0,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_width_inches must be greater"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            battlefield_width_inches=0.0,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_depth_inches must be a number"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            battlefield_depth_inches=True,
        )
    with pytest.raises(GameLifecycleError, match="terrain_features must be a tuple"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            terrain_features=cast(tuple[TerrainFeatureDefinition, ...], [object()]),
        )
    with pytest.raises(GameLifecycleError, match="terrain_features must contain"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            terrain_features=cast(tuple[TerrainFeatureDefinition, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="enemy_deployment_zones must be a tuple"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            enemy_deployment_zones=cast(tuple[DeploymentZone, ...], [object()]),
        )
    with pytest.raises(GameLifecycleError, match="enemy_deployment_zones must contain"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            enemy_deployment_zones=cast(tuple[DeploymentZone, ...], (object(),)),
        )
    with pytest.raises(GameLifecycleError, match="large_model_exceptions must be a tuple"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            large_model_exceptions=cast(
                tuple[LargeModelReservePlacementException, ...],
                [large_exception],
            ),
        )
    with pytest.raises(GameLifecycleError, match="duplicate model IDs"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            large_model_exceptions=(large_exception, large_exception),
        )
    with pytest.raises(GameLifecycleError, match="strategic_reserve_rule"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=reserve_state,
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
            strategic_reserve_rule=cast(StrategicReserveRule, object()),
        )
    with pytest.raises(GameLifecycleError, match="unknown unit"):
        resolve_reserve_arrival(
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            reserve_state=replace(reserve_state, unit_instance_id="army-alpha:missing-unit"),
            attempted_placement=placement,
            battle_round=3,
            placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        )

    with pytest.raises(GameLifecycleError, match="reserve_states must be a tuple"):
        resolve_unarrived_reserve_destruction(
            reserve_states=cast(tuple[ReserveState, ...], [reserve_state]),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="ReserveState values"):
        resolve_unarrived_reserve_destruction(
            reserve_states=cast(tuple[ReserveState, ...], (object(),)),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="duplicate unit IDs"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state, reserve_state),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=scenario.armies,
            battlefield_state=cast(BattlefieldRuntimeState, object()),
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="policy must be"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=cast(ReserveDestructionTimingPolicy, object()),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="armies must be a tuple"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=cast(tuple[ArmyDefinition, ...], [scenario.armies[0]]),
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="ArmyDefinition values"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(reserve_state,),
            armies=cast(tuple[ArmyDefinition, ...], (object(),)),
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="unknown unit"):
        resolve_unarrived_reserve_destruction(
            reserve_states=(replace(reserve_state, unit_instance_id="army-alpha:missing-unit"),),
            armies=scenario.armies,
            battlefield_state=scenario.battlefield_state,
            policy=ReserveDestructionTimingPolicy.core_rules_default(),
            battle_round=5,
            end_of_battle=True,
        )
    with pytest.raises(GameLifecycleError, match="battlefield_state"):
        apply_reserve_destruction_to_battlefield(
            battlefield_state=cast(BattlefieldRuntimeState, object()),
            destruction=destruction,
        )
    with pytest.raises(GameLifecycleError, match="destruction must be"):
        apply_reserve_destruction_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            destruction=cast(ReserveDestructionResult, object()),
        )


def _battle_state_with_reserve(
    *,
    reserve_base_diameter_mm: float = 200.0,
    reserve_model_count: int = 1,
    ruleset_descriptor: RulesetDescriptor | None = None,
) -> tuple[GameState, BattlefieldScenario, ReserveState, UnitInstance]:
    config = _config(ruleset_descriptor=ruleset_descriptor or _ruleset())
    armies = _mustered_armies(config)
    armies = _with_reserve_unit_geometry(
        armies=armies,
        base_diameter_mm=reserve_base_diameter_mm,
        reserve_model_count=reserve_model_count,
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10p-battlefield",
        armies=armies,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    scenario = BattlefieldScenario(armies=armies, battlefield_state=battlefield_state)
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            (ruleset_descriptor or _ruleset()).mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, scenario, reserve_state, reserve_unit


def _set_movement_ready_for_reinforcements(
    *,
    state: GameState,
    battle_round: int,
) -> None:
    placed_unit_id = "army-alpha:intercessor-unit-2"
    state.battle_round = battle_round
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=(placed_unit_id,),
        moved_unit_ids=(placed_unit_id,),
    )


def _enter_reinforcements_choice(
    *,
    state: GameState,
    battle_round: int,
    ruleset_descriptor: RulesetDescriptor | None = None,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    _set_movement_ready_for_reinforcements(state=state, battle_round=battle_round)
    handler = MovementPhaseHandler(ruleset_descriptor=ruleset_descriptor or _ruleset())
    decisions = DecisionController()
    status = handler.begin_phase(state=state, decisions=decisions)
    return handler, decisions, _decision_request(status)


def _submit_handler_decision(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, object]:
    for record in reversed(decisions.event_log.records):
        if record.event_type == event_type:
            payload = record.payload
            assert isinstance(payload, dict)
            return cast(dict[str, object], payload)
    raise AssertionError(f"event {event_type} not found")


def _with_reserve_unit_geometry(
    *,
    armies: tuple[ArmyDefinition, ...],
    base_diameter_mm: float,
    reserve_model_count: int,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id != "army-alpha":
            updated_armies.append(army)
            continue
        reserve_unit = army.unit_by_id("army-alpha:intercessor-unit-1")
        base_size = BaseSizeDefinition.circular(base_diameter_mm)
        updated_models = tuple(
            replace(
                model,
                base_size=base_size if index == 0 else model.base_size,
                geometry=(
                    ModelGeometry.from_base_size(
                        base_size,
                        geometry_source_id="phase10p-oversized-base",
                        keywords=reserve_unit.keywords,
                    )
                    if index == 0
                    else model.geometry
                ),
            )
            for index, model in enumerate(reserve_unit.own_models[:reserve_model_count])
        )
        updated_unit = replace(reserve_unit, own_models=updated_models)
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return tuple(updated_armies)


def _with_replaced_unit(
    armies: tuple[ArmyDefinition, ...],
    updated_unit: UnitInstance,
) -> tuple[ArmyDefinition, ...]:
    return tuple(
        replace(
            army,
            units=tuple(
                updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                for unit in army.units
            ),
        )
        if any(unit.unit_instance_id == updated_unit.unit_instance_id for unit in army.units)
        else army
        for army in armies
    )


def _single_model_reserve_placement(*, reserve_unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return _reserve_placement(reserve_unit=reserve_unit, poses=(pose,))


def _reserve_placement(*, reserve_unit: UnitInstance, poses: tuple[Pose, ...]) -> UnitPlacement:
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(reserve_unit.own_models, poses, strict=True)
        ),
    )


def _south_edge_touching_pose(*, base_diameter_mm: float, x: float) -> Pose:
    return Pose.at(
        x=x,
        y=_base_radius_inches(base_diameter_mm),
        z=0.0,
        facing_degrees=0.0,
    )


def _base_radius_inches(base_diameter_mm: float) -> float:
    return (base_diameter_mm / 25.4) / 2.0


def _with_model_pose(
    scenario: BattlefieldScenario,
    *,
    model_instance_id: str,
    pose: Pose,
) -> BattlefieldScenario:
    model_placement = scenario.battlefield_state.model_placement_by_id(model_instance_id)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        model_placement.unit_instance_id
    )
    updated_model_placements = tuple(
        replace(placement, pose=pose)
        if placement.model_instance_id == model_instance_id
        else placement
        for placement in unit_placement.model_placements
    )
    updated_unit_placement = replace(
        unit_placement,
        model_placements=updated_model_placements,
    )
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_unit_placement),
    )


def _blocking_wall_feature(*, x: float, y: float) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase10p-wall",
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        walls=(
            TerrainWallDefinition(
                wall_id="center-wall",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
    )


def _violation_codes(
    result: ReinforcementPlacement,
) -> tuple[ReservePlacementViolationCode, ...]:
    return tuple(sorted(violation.violation_code for violation in result.violations))


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase10p-test")


def _chapter_approved_ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
        descriptor_version="core-v2-phase10p-ca-test"
    )


def _config(*, ruleset_descriptor: RulesetDescriptor) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10p-game",
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selections=(
                    _unit_selection(unit_selection_id="intercessor-unit-1"),
                    _unit_selection(unit_selection_id="intercessor-unit-2"),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selections=(_unit_selection(unit_selection_id="intercessor-unit-3"),),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2025_26_mission_pack(),
            mission_pool_entry_id="mission-a",
            terrain_layout_id="layout-1",
            attacker_player_id="player-a",
            defender_player_id="player-b",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selections: tuple[UnitMusterSelection, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=unit_selections,
    )


def _unit_selection(*, unit_selection_id: str) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
