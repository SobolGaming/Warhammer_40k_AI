from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import DiceRollResult, DiceRollState
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.engine.aircraft import (
    AircraftMovementPolicy,
    AircraftMovementPolicyPayload,
    AircraftMovementViolationCode,
    AircraftReserveTransition,
    AircraftReserveTransitionPayload,
    AircraftReserveTransitionReason,
    HoverModeState,
    HoverModeStatePayload,
    aircraft_model_ids_for_scenario,
    aircraft_movement_violation_code_from_token,
    aircraft_reserve_transition_reason_from_token,
    apply_aircraft_reserve_transition_to_battlefield,
    resolve_aircraft_arrival,
    resolve_aircraft_reserve_transition,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    ModelPlacement,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
    AdvanceRollRequest,
    AdvanceRollResult,
    MovementActionAvailabilityContext,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementPhaseStepKind,
    _aircraft_minimum_move_unavailable,  # pyright: ignore[reportPrivateUsage]
    _model_base_movement_inches,  # pyright: ignore[reportPrivateUsage]
    _model_movement_budget_inches,  # pyright: ignore[reportPrivateUsage]
    _translated_forward_pose,  # pyright: ignore[reportPrivateUsage]
    resolve_advance_move,
    resolve_normal_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveOrigin,
    ReservePlacementViolationCode,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.movement_envelope import MovementDistanceWitness
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
    PathWitnessPayload,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_aircraft_policy_uses_zero_pivot_cost_and_validates_forward_move() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    ruleset = _ruleset()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    moving_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(model_placement),
        placement=model_placement,
    )
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=ruleset)

    witness = PathWitness.for_paths(
        (
            (
                moving_model.model_id,
                (
                    moving_model.pose,
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=moving_model.pose.facing.degrees,
                    ),
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=90.0,
                    ),
                ),
            ),
        )
    )
    distance = MovementDistanceWitness.for_model_path(
        model=moving_model,
        poses=witness.poses_for_model(moving_model.model_id),
        pivot_cost_policy=policy.to_pivot_cost_policy(moving_model.model_id),
    )

    assert policy.uses_aircraft_rules
    assert policy.minimum_move_inches == 20.0
    assert policy.maximum_pivot_degrees == 90.0
    assert distance.pivot_cost_inches == 0.0
    assert policy.validate_normal_move_witness(moving_model=moving_model, witness=witness) == ()


def test_hover_mode_state_changes_aircraft_policy_and_round_trips() -> None:
    _scenario, aircraft, _enemy = _aircraft_scenario()
    hover_state = HoverModeState.active_for_unit(
        player_id="player-a",
        unit_instance_id=aircraft.unit_instance_id,
        decision_request_id="hover-request",
        decision_result_id="hover-result",
    )
    policy = AircraftMovementPolicy.from_unit(
        unit=aircraft,
        ruleset_descriptor=_ruleset(),
        hover_mode_state=hover_state,
    )

    assert not policy.uses_aircraft_rules
    assert "AIRCRAFT" not in policy.effective_keywords
    assert policy.can_declare_charge
    assert policy.minimum_move_inches is None

    hover_payload = cast(
        HoverModeStatePayload,
        json.loads(json.dumps(hover_state.to_payload(), sort_keys=True)),
    )
    policy_payload = cast(
        AircraftMovementPolicyPayload,
        json.loads(json.dumps(policy.to_payload(), sort_keys=True)),
    )
    assert "<" not in json.dumps(policy_payload, sort_keys=True)
    assert "object at 0x" not in json.dumps(policy_payload, sort_keys=True)
    assert HoverModeState.from_payload(hover_payload) == hover_state
    assert AircraftMovementPolicy.from_payload(policy_payload) == policy


def test_persisted_hover_mode_state_changes_movement_action_availability() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))

    _handler, _decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )

    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    }
    normal_payload = next(
        option.payload
        for option in action_request.options
        if option.option_id == MovementPhaseActionKind.NORMAL_MOVE.value
    )
    assert isinstance(normal_payload, dict)
    aircraft_policy_payload = cast(dict[str, object], normal_payload["aircraft_movement_policy"])
    assert aircraft_policy_payload["hover_mode_active"] is True
    assert aircraft_policy_payload["uses_aircraft_rules"] is False


def test_persisted_hover_mode_disables_aircraft_minimum_move_and_pivot_restrictions() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    hover_witness = PathWitness.for_paths(
        (
            (
                model_placement.model_instance_id,
                (
                    model_placement.pose,
                    Pose.at(
                        model_placement.pose.position.x + 6.0,
                        model_placement.pose.position.y,
                        facing_degrees=model_placement.pose.facing.degrees,
                    ),
                    Pose.at(
                        model_placement.pose.position.x + 6.0,
                        model_placement.pose.position.y,
                        facing_degrees=90.0,
                    ),
                ),
            ),
        )
    )

    result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=hover_witness,
        hover_mode_states=tuple(state.hover_mode_states),
    )

    assert result.is_valid
    policy_payload = cast(dict[str, object], result.movement_payload["aircraft_movement_policy"])
    assert policy_payload["uses_aircraft_rules"] is False
    assert all(
        not violation.violation_code.startswith("aircraft_")
        for path_result in result.path_validation_results
        for violation in path_result.violations
    )


def test_hover_aircraft_uses_twenty_inch_move_budget_for_normal_move() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))
    assert _model_movement_inches(aircraft.own_models[0]) < 20

    scenario = _scenario_from_state(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    hover_witness = _single_model_forward_witness(unit_placement, movement_inches=20.0)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=hover_witness,
        hover_mode_states=tuple(state.hover_mode_states),
    )

    assert resolution.is_valid
    model_payload = _single_model_movement_payload(resolution.movement_payload)
    assert model_payload["base_movement_inches"] == 20.0
    assert model_payload["movement_inches"] == 20.0
    distance_witness = cast(dict[str, object], model_payload["movement_distance_witness"])
    budget = cast(dict[str, object], distance_witness["budget"])
    assert budget["max_distance_inches"] == 20.0


def test_hover_aircraft_can_advance_twenty_plus_d6() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))

    scenario = _scenario_from_state(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    hover_witness = _single_model_forward_witness(unit_placement, movement_inches=21.0)

    resolution = resolve_advance_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        advance_roll=_advance_roll_result(aircraft.unit_instance_id),
        path_witness=hover_witness,
        hover_mode_states=tuple(state.hover_mode_states),
    )

    assert resolution.is_valid
    model_payload = _single_model_movement_payload(resolution.movement_payload)
    assert model_payload["base_movement_inches"] == 20.0
    assert model_payload["movement_inches"] == 21.0
    distance_witness = cast(dict[str, object], model_payload["movement_distance_witness"])
    budget = cast(dict[str, object], distance_witness["budget"])
    assert budget["max_distance_inches"] == 21.0


def test_aircraft_movement_budget_helpers_fail_fast() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    model = scenario.model_instance_for_placement(model_placement)
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=_ruleset())

    with pytest.raises(GameLifecycleError, match="Movement model must be"):
        _model_base_movement_inches(
            model=cast(ModelInstance, object()),
            aircraft_policy=policy,
        )
    with pytest.raises(GameLifecycleError, match="AircraftMovementPolicy"):
        _model_base_movement_inches(
            model=model,
            aircraft_policy=cast(AircraftMovementPolicy, object()),
        )
    with pytest.raises(GameLifecycleError, match="movement_phase_action"):
        _model_movement_budget_inches(
            model=model,
            aircraft_policy=policy,
            movement_bonus_inches=0,
            movement_phase_action=cast(MovementPhaseActionKind, object()),
        )
    with pytest.raises(GameLifecycleError, match="geometry Model"):
        _aircraft_minimum_move_unavailable(
            moving_model=cast(Model, object()),
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            minimum_move_inches=20.0,
        )
    with pytest.raises(GameLifecycleError, match="movement_inches must be a number"):
        _translated_forward_pose(Pose.at(0.0, 0.0), movement_inches=cast(float, object()))
    with pytest.raises(GameLifecycleError, match="movement_inches must be finite"):
        _translated_forward_pose(Pose.at(0.0, 0.0), movement_inches=float("inf"))
    with pytest.raises(GameLifecycleError, match="movement_inches must be at least 1"):
        _translated_forward_pose(Pose.at(0.0, 0.0), movement_inches=0.0)


def test_persisted_hover_mode_state_round_trips_through_lifecycle_payload() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))
    lifecycle = GameLifecycle(state=state)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


@pytest.mark.parametrize(
    "mutation",
    [
        {"player_id": "player-b"},
        {"unit_instance_id": "army-alpha:missing-unit"},
        {"player_id": "player-b", "unit_instance_id": "army-beta:enemy-unit"},
        {"source_id": "unsupported-hover-source"},
    ],
)
def test_lifecycle_rejects_hover_mode_state_replay_drift(
    mutation: dict[str, object],
) -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))
    lifecycle = GameLifecycle(state=state)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    cast(dict[str, object], payload["state"]["hover_mode_states"][0]).update(mutation)

    with pytest.raises(GameLifecycleError, match="hover_mode_states"):
        GameLifecycle.from_payload(payload)


def test_game_state_hover_mode_state_recording_is_fail_fast_and_queryable() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))

    with pytest.raises(GameLifecycleError, match="hover_mode_state must be"):
        state.record_hover_mode_state(cast(HoverModeState, object()))
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        state.record_hover_mode_state(
            HoverModeState.active_for_unit(
                player_id="player-c",
                unit_instance_id=aircraft.unit_instance_id,
            )
        )

    hover_state = _hover_state_for_aircraft(aircraft)
    state.record_hover_mode_state(hover_state)

    assert state.hover_mode_state_for_unit(aircraft.unit_instance_id) == hover_state
    assert state.hover_mode_state_for_unit("army-alpha:missing-hover-unit") is None
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_hover_mode_state(hover_state)


def test_normal_move_rejects_stale_aircraft_policy_after_hover_state_changes() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )
    state.record_hover_mode_state(_hover_state_for_aircraft(aircraft))

    status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10r-stale-aircraft-policy",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    status_payload = cast(dict[str, object], status.payload)
    assert status_payload["violation_code"] == "normal_move_aircraft_policy_drift"


def test_other_models_can_transit_aircraft_but_not_end_on_them() -> None:
    mover = _geometry_model("mover", x=1.0, y=1.0)
    enemy_aircraft = _geometry_model("enemy-aircraft", x=3.0, y=1.0)
    transit_witness = PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(6.0, 1.0))),))
    blocked = PathValidationContext(
        moving_model=mover,
        witness=transit_witness,
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_models=(enemy_aircraft,),
    ).validate()
    allowed = PathValidationContext(
        moving_model=mover,
        witness=transit_witness,
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_models=(enemy_aircraft,),
        aircraft_model_ids=(enemy_aircraft.model_id,),
    ).validate()
    endpoint = PathValidationContext(
        moving_model=mover,
        witness=PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(3.0, 1.0))),)),
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_models=(enemy_aircraft,),
        aircraft_model_ids=(enemy_aircraft.model_id,),
    ).validate()

    assert not blocked.is_valid
    assert blocked.violations[0].violation_code == "enemy_model_base_crossed"
    assert allowed.is_valid
    assert not endpoint.is_valid
    assert endpoint.violations[0].violation_code == "end_on_model_overlap"


def test_standard_aircraft_action_policy_allows_only_normal_move_even_in_engagement() -> None:
    _scenario, aircraft, _enemy = _aircraft_scenario()
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=_ruleset())
    context = MovementActionAvailabilityContext(
        ruleset_descriptor_hash=_ruleset().descriptor_hash,
        unit_instance_id=aircraft.unit_instance_id,
        player_id="player-a",
        enemy_engagement_model_ids=("army-beta:enemy-unit:core-intercessor-like:001",),
        aircraft_movement_policy=policy,
    )
    result = context.evaluate()
    context_payload = context.to_payload()

    assert "aircraft_movement_policy" in context_payload
    assert result.available_actions == (MovementPhaseActionKind.NORMAL_MOVE,)
    assert MovementPhaseActionKind.FALL_BACK in result.unavailable_actions
    assert MovementPhaseActionKind.ADVANCE in result.unavailable_actions


def test_aircraft_normal_move_rejects_short_or_non_forward_paths() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    short_witness = PathWitness.for_paths(
        (
            (
                model_placement.model_instance_id,
                (
                    model_placement.pose,
                    Pose.at(
                        model_placement.pose.position.x + 10.0,
                        model_placement.pose.position.y,
                    ),
                ),
            ),
        )
    )
    sideways_witness = PathWitness.for_paths(
        (
            (
                model_placement.model_instance_id,
                (
                    model_placement.pose,
                    Pose.at(
                        model_placement.pose.position.x,
                        model_placement.pose.position.y + 20.0,
                    ),
                ),
            ),
        )
    )

    short_result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=short_witness,
    )
    sideways_result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=sideways_witness,
    )

    assert not short_result.is_valid
    assert (
        short_result.path_validation_results[0].violations[0].violation_code
        == "aircraft_minimum_move_required"
    )
    assert not sideways_result.is_valid
    assert (
        sideways_result.path_validation_results[0].violations[0].violation_code
        == "aircraft_forward_move_required"
    )


def test_aircraft_policy_rejects_invalid_pivot_sequences() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    moving_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(model_placement),
        placement=model_placement,
    )
    policy = AircraftMovementPolicy.from_unit(unit=aircraft, ruleset_descriptor=_ruleset())

    pivot_before_move = PathWitness.for_paths(
        (
            (
                moving_model.model_id,
                (
                    moving_model.pose,
                    Pose.at(
                        moving_model.pose.position.x,
                        moving_model.pose.position.y,
                        facing_degrees=90.0,
                    ),
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=90.0,
                    ),
                ),
            ),
        )
    )
    simultaneous_move_and_pivot = PathWitness.for_paths(
        (
            (
                moving_model.model_id,
                (
                    moving_model.pose,
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=90.0,
                    ),
                ),
            ),
        )
    )
    excessive_second_pivot = PathWitness.for_paths(
        (
            (
                moving_model.model_id,
                (
                    moving_model.pose,
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=0.0,
                    ),
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=100.0,
                    ),
                    Pose.at(
                        moving_model.pose.position.x + 20.0,
                        moving_model.pose.position.y,
                        facing_degrees=120.0,
                    ),
                ),
            ),
        )
    )

    before_move_codes = {
        violation.violation_code
        for violation in policy.validate_normal_move_witness(
            moving_model=moving_model,
            witness=pivot_before_move,
        )
    }
    simultaneous_codes = {
        violation.violation_code
        for violation in policy.validate_normal_move_witness(
            moving_model=moving_model,
            witness=simultaneous_move_and_pivot,
        )
    }
    excessive_codes = {
        violation.violation_code
        for violation in policy.validate_normal_move_witness(
            moving_model=moving_model,
            witness=excessive_second_pivot,
        )
    }

    assert AircraftMovementViolationCode.AIRCRAFT_PIVOT_BEFORE_MOVE in before_move_codes
    assert AircraftMovementViolationCode.AIRCRAFT_TRANSLATION_AFTER_PIVOT in before_move_codes
    assert AircraftMovementViolationCode.AIRCRAFT_PIVOT_DURING_TRANSLATION in simultaneous_codes
    assert AircraftMovementViolationCode.AIRCRAFT_PIVOT_LIMIT_EXCEEDED in excessive_codes
    assert AircraftMovementViolationCode.AIRCRAFT_MULTIPLE_PIVOTS in excessive_codes


def test_aircraft_reserve_transition_removes_unit_and_records_reserve_state() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)

    transition = resolve_aircraft_reserve_transition(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        battle_round=1,
        reason=AircraftReserveTransitionReason.BATTLEFIELD_EDGE_CROSSED,
        source_event_id="phase10r-edge",
    )
    updated_battlefield = apply_aircraft_reserve_transition_to_battlefield(
        battlefield_state=scenario.battlefield_state,
        transition=transition,
    )
    payload = cast(
        AircraftReserveTransitionPayload,
        json.loads(json.dumps(transition.to_payload(), sort_keys=True)),
    )

    assert transition.is_valid
    assert transition.reserve_state is not None
    assert transition.reserve_state.reserve_origin is ReserveOrigin.DURING_BATTLE_OTHER
    assert transition.reserve_state.entered_reserves_phase == BattlePhase.MOVEMENT.value
    assert transition.reserve_state.required_arrival_battle_round == 2
    assert transition.reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
    assert transition.reserve_state.required_arrival_source_rule_id == (
        AircraftReserveTransitionReason.BATTLEFIELD_EDGE_CROSSED.value
    )
    assert transition.transition_batch is not None
    assert {record.removal_kind for record in transition.transition_batch.removals} == {
        BattlefieldRemovalKind.INTO_RESERVES
    }
    assert aircraft.unit_instance_id not in {
        placement.unit_instance_id
        for army in updated_battlefield.placed_armies
        for placement in army.unit_placements
    }
    assert AircraftReserveTransition.from_payload(payload).to_payload() == payload


def test_invalid_aircraft_reserve_transition_is_typed_and_cannot_mutate() -> None:
    scenario, _aircraft, enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)

    transition = resolve_aircraft_reserve_transition(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        battle_round=1,
        reason=AircraftReserveTransitionReason.MINIMUM_MOVE_UNAVAILABLE,
    )
    payload = cast(
        AircraftReserveTransitionPayload,
        json.loads(json.dumps(transition.to_payload(), sort_keys=True)),
    )

    assert not transition.is_valid
    assert transition.reserve_state is None
    assert transition.transition_batch is None
    assert (
        transition.violations[0].violation_code is AircraftMovementViolationCode.UNIT_NOT_AIRCRAFT
    )
    assert AircraftReserveTransition.from_payload(payload).to_payload() == payload
    with pytest.raises(GameLifecycleError, match="Invalid AircraftReserveTransition"):
        apply_aircraft_reserve_transition_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            transition=transition,
        )


def test_aircraft_default_normal_move_witness_moves_twenty_forward_without_reserves() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )
    normal_payload = cast(
        dict[str, object],
        action_request.option_by_id(MovementPhaseActionKind.NORMAL_MOVE.value).payload,
    )
    default_witness = PathWitness.from_payload(cast(PathWitnessPayload, normal_payload["witness"]))
    model_id = aircraft.own_models[0].model_instance_id

    assert default_witness.final_pose_for_model(model_id) == Pose.at(30.0, 10.0)

    status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10r-aircraft-default-normal-move",
    )

    assert status is None
    assert state.reserve_state_for_unit(aircraft.unit_instance_id) is None
    assert state.battlefield_state is not None
    moved_placement = state.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    assert moved_placement.model_placements[0].pose == Pose.at(30.0, 10.0)
    completed_payload = _last_event_payload(decisions, "movement_activation_completed")
    assert completed_payload["displacement_kind"] == "normal_move"
    transition_batch = cast(dict[str, object], completed_payload["transition_batch"])
    assert len(cast(list[object], transition_batch["displacements"])) == 1
    assert transition_batch["removals"] == []
    model_payload = _single_model_movement_payload(completed_payload)
    distance_witness = cast(dict[str, object], model_payload["movement_distance_witness"])
    assert distance_witness["budget"] is None


def test_aircraft_normal_move_lifecycle_crossing_edge_transitions_to_reserves() -> None:
    pose = Pose.at(55.0, 10.0)
    expected_reason = AircraftReserveTransitionReason.BATTLEFIELD_EDGE_CROSSED
    state, aircraft = _aircraft_battle_state(aircraft_pose=pose)
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )

    status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id=f"phase10r-{expected_reason.value}",
    )

    assert status is None
    assert state.battlefield_state is not None
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        state.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    reserve_state = state.reserve_state_for_unit(aircraft.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
    assert reserve_state.required_arrival_battle_round == 2
    assert reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
    assert reserve_state.required_arrival_source_rule_id == expected_reason.value
    movement_state = state.movement_phase_state
    assert movement_state is not None
    assert movement_state.active_selection is None
    assert movement_state.moved_unit_ids == (aircraft.unit_instance_id,)

    completed_payload = _last_event_payload(decisions, "movement_activation_completed")
    assert "displacement_kind" not in completed_payload
    transition_batch = cast(dict[str, object], completed_payload["transition_batch"])
    assert transition_batch["displacements"] == []
    assert len(cast(list[object], transition_batch["removals"])) == 1
    transition_payload = cast(dict[str, object], completed_payload["aircraft_reserve_transition"])
    assert transition_payload["reason"] == expected_reason.value
    assert not any(
        isinstance(event.payload, dict)
        and event.payload.get("phase_body_status") == "embark_choice_required"
        for event in decisions.event_log.records
    )

    lifecycle = GameLifecycle(state=state, decision_controller=decisions)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    assert GameLifecycle.from_payload(payload).to_payload() == lifecycle.to_payload()


def test_aircraft_submitted_short_witness_is_invalid_when_minimum_move_fits() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(10.0, 10.0))
    assert state.battlefield_state is not None
    original_battlefield_payload = state.battlefield_state.to_payload()
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )
    unit_placement = _scenario_from_state(state).battlefield_state.unit_placement_by_id(
        aircraft.unit_instance_id
    )
    short_witness = _single_model_forward_witness(unit_placement, movement_inches=10.0)

    status = _submit_custom_normal_move_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        unit_placement=unit_placement,
        witness=short_witness,
        result_id="phase10r-aircraft-short-witness-invalid",
    )

    assert status is not None
    assert status.status_kind is LifecycleStatusKind.INVALID
    status_payload = cast(dict[str, object], status.payload)
    assert status_payload["violation_code"] == "aircraft_minimum_move_required"
    assert state.reserve_state_for_unit(aircraft.unit_instance_id) is None
    assert state.battlefield_state is not None
    assert state.battlefield_state.to_payload() == original_battlefield_payload


def test_aircraft_short_witness_transitions_when_mandatory_minimum_move_cannot_fit() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(40.0, 10.0))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )
    unit_placement = _scenario_from_state(state).battlefield_state.unit_placement_by_id(
        aircraft.unit_instance_id
    )
    short_witness = _single_model_forward_witness(unit_placement, movement_inches=10.0)

    status = _submit_custom_normal_move_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        unit_placement=unit_placement,
        witness=short_witness,
        result_id="phase10r-aircraft-short-witness-minimum-unavailable",
    )

    assert status is None
    assert state.battlefield_state is not None
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        state.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    reserve_state = state.reserve_state_for_unit(aircraft.unit_instance_id)
    assert reserve_state is not None
    assert reserve_state.required_arrival_source_rule_id == (
        AircraftReserveTransitionReason.MINIMUM_MOVE_UNAVAILABLE.value
    )
    completed_payload = _last_event_payload(decisions, "movement_activation_completed")
    transition_payload = cast(dict[str, object], completed_payload["aircraft_reserve_transition"])
    assert (
        transition_payload["reason"]
        == AircraftReserveTransitionReason.MINIMUM_MOVE_UNAVAILABLE.value
    )


def test_aircraft_arrival_uses_reserve_battlefield_and_terrain_validation() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)
    transition = resolve_aircraft_reserve_transition(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        battle_round=1,
        reason=AircraftReserveTransitionReason.MINIMUM_MOVE_UNAVAILABLE,
    )
    assert transition.reserve_state is not None
    reserve_scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=apply_aircraft_reserve_transition_to_battlefield(
            battlefield_state=scenario.battlefield_state,
            transition=transition,
        ),
    )
    battlefield_invalid = resolve_aircraft_arrival(
        scenario=reserve_scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=transition.reserve_state,
        attempted_placement=_single_model_placement(aircraft, pose=Pose.at(-1.0, 3.0)),
        battle_round=2,
    )
    terrain_invalid = resolve_aircraft_arrival(
        scenario=reserve_scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=transition.reserve_state,
        attempted_placement=_single_model_placement(aircraft, pose=Pose.at(12.0, 3.0)),
        battle_round=2,
        terrain_features=(_blocking_wall_feature(x=12.0, y=3.0),),
    )

    assert ReservePlacementViolationCode.BATTLEFIELD_EDGE_CROSSED in {
        violation.violation_code for violation in battlefield_invalid.violations
    }
    assert ReservePlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL in {
        violation.violation_code for violation in terrain_invalid.violations
    }


def test_aircraft_transition_reserve_state_is_required_next_controller_turn_only() -> None:
    state, aircraft = _aircraft_battle_state(aircraft_pose=Pose.at(55.0, 10.0))
    handler, decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=aircraft.unit_instance_id,
    )
    _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        result_id="phase10r-aircraft-edge-transition",
    )
    reserve_state = state.reserve_state_for_unit(aircraft.unit_instance_id)
    assert reserve_state is not None
    assert not reserve_state.arrival_is_eligible_at(battle_round=1, phase=BattlePhase.MOVEMENT)
    assert reserve_state.arrival_is_required_at(battle_round=2, phase=BattlePhase.MOVEMENT)
    assert not reserve_state.arrival_is_eligible_at(battle_round=3, phase=BattlePhase.MOVEMENT)

    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    attempted_placement = _single_model_placement(aircraft, pose=Pose.at(12.0, 3.0))
    early = resolve_aircraft_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        battle_round=1,
    )
    due = resolve_aircraft_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        battle_round=2,
    )
    late = resolve_aircraft_arrival(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        battle_round=3,
    )

    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN in {
        violation.violation_code for violation in early.violations
    }
    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN not in {
        violation.violation_code for violation in due.violations
    }
    assert ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN in {
        violation.violation_code for violation in late.violations
    }

    state.battle_round = 2
    state.active_player_id = "player-a"
    state.movement_phase_state = MovementPhaseState(
        battle_round=2,
        active_player_id="player-a",
        step=MovementPhaseStepKind.REINFORCEMENTS,
    )
    reinforcement_decisions = DecisionController()
    reinforcement_request = _decision_request(
        MovementPhaseHandler(ruleset_descriptor=_ruleset()).begin_phase(
            state=state,
            decisions=reinforcement_decisions,
        )
    )

    assert reinforcement_request.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE
    assert {option.option_id for option in reinforcement_request.options} == {
        aircraft.unit_instance_id
    }


def test_non_aircraft_engaged_only_by_enemy_aircraft_can_normal_move_and_advance() -> None:
    state, mover, _aircraft = _aircraft_engagement_battle_state(include_non_aircraft_enemy=False)
    _handler, _decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=mover.unit_instance_id,
    )

    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    }


def test_non_aircraft_engaged_by_aircraft_and_enemy_unit_must_remain_or_fall_back() -> None:
    state, mover, _aircraft = _aircraft_engagement_battle_state(include_non_aircraft_enemy=True)
    _handler, _decisions, action_request = _movement_action_request_for_unit(
        state=state,
        unit_instance_id=mover.unit_instance_id,
    )

    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.FALL_BACK.value,
    }


def test_normal_and_advance_can_transit_enemy_aircraft_but_not_end_in_engagement() -> None:
    state, mover, enemy_aircraft = _aircraft_transit_battle_state()
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id(mover.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    aircraft_placement = scenario.battlefield_state.unit_placement_by_id(
        enemy_aircraft.unit_instance_id
    ).model_placements[0]

    transit_witness = PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(12.0, model_placement.pose.position.y),
            ),
        )
    )
    endpoint_witness = PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(
                    aircraft_placement.pose.position.x,
                    model_placement.pose.position.y,
                ),
            ),
        )
    )

    normal_result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=transit_witness,
    )
    advance_result = resolve_advance_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        advance_roll=_advance_roll_result(mover.unit_instance_id),
        path_witness=transit_witness,
    )
    endpoint_result = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=endpoint_witness,
    )

    assert normal_result.is_valid
    assert advance_result.is_valid
    assert not endpoint_result.is_valid
    assert endpoint_result.path_validation_results[0].violations[0].violation_code == (
        "enemy_engagement_range_end_forbidden"
    )


def test_aircraft_model_ids_and_token_validators_fail_fast() -> None:
    scenario, aircraft, _enemy = _aircraft_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(aircraft.unit_instance_id)

    assert aircraft_model_ids_for_scenario(scenario) == tuple(
        placement.model_instance_id for placement in unit_placement.model_placements
    )
    with pytest.raises(GameLifecycleError, match="Unsupported AircraftReserveTransitionReason"):
        aircraft_reserve_transition_reason_from_token("unsupported-aircraft-reason")
    with pytest.raises(GameLifecycleError, match="Unsupported AircraftMovementViolationCode"):
        aircraft_movement_violation_code_from_token("unsupported-aircraft-violation")


def _aircraft_battle_state(*, aircraft_pose: Pose) -> tuple[GameState, UnitInstance]:
    scenario, aircraft, _enemy = _aircraft_scenario()
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=aircraft.unit_instance_id,
        pose=aircraft_pose,
    )
    return _battle_state_from_scenario(scenario), aircraft


def _aircraft_engagement_battle_state(
    *,
    include_non_aircraft_enemy: bool,
) -> tuple[GameState, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="mover-unit",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    beta_selections = [
        _unit_selection(
            unit_selection_id="enemy-aircraft",
            datasheet_id="core-vehicle-monster",
            model_profile_id="core-vehicle-monster",
            model_count=1,
        )
    ]
    if include_non_aircraft_enemy:
        beta_selections.append(
            _unit_selection(
                unit_selection_id="enemy-infantry",
                datasheet_id="core-vehicle-monster",
                model_profile_id="core-vehicle-monster",
                model_count=1,
            )
        )
    beta = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=tuple(beta_selections),
        ),
    )
    enemy_aircraft = replace(
        beta.unit_by_id("army-beta:enemy-aircraft"),
        keywords=("Aircraft", "Fly", "Vehicle"),
    )
    beta = replace(
        beta,
        units=tuple(
            enemy_aircraft if unit.unit_instance_id == enemy_aircraft.unit_instance_id else unit
            for unit in beta.units
        ),
    )
    mover = alpha.unit_by_id("army-alpha:mover-unit")
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10r-engagement-battlefield",
        armies=(alpha, beta),
    )
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=mover.unit_instance_id,
        pose=Pose.at(20.0, 20.0),
    )
    scenario = _place_unit_in_engagement_of_mover(
        scenario=scenario,
        mover=mover,
        enemy=enemy_aircraft,
        direction=1.0,
    )
    if include_non_aircraft_enemy:
        enemy_infantry = beta.unit_by_id("army-beta:enemy-infantry")
        scenario = _place_unit_in_engagement_of_mover(
            scenario=scenario,
            mover=mover,
            enemy=enemy_infantry,
            direction=-1.0,
        )
    return _battle_state_from_scenario(scenario), mover, enemy_aircraft


def _aircraft_transit_battle_state() -> tuple[GameState, UnitInstance, UnitInstance]:
    state, mover, enemy_aircraft = _aircraft_engagement_battle_state(
        include_non_aircraft_enemy=False
    )
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=mover.unit_instance_id,
        pose=Pose.at(6.0, 20.0),
    )
    mover_radius = _first_model_radius_x(mover)
    aircraft_radius = _first_model_radius_x(enemy_aircraft)
    scenario = _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=enemy_aircraft.unit_instance_id,
        pose=Pose.at(9.0, 20.0 + mover_radius + aircraft_radius + 0.5),
    )
    state.battlefield_state = scenario.battlefield_state
    return state, mover, enemy_aircraft


def _battle_state_from_scenario(scenario: BattlefieldScenario) -> GameState:
    ruleset = _ruleset()
    return GameState(
        game_id="phase10r-game",
        ruleset_descriptor_hash=ruleset.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(ruleset.setup_sequence.steps),
        battle_phase_sequence=tuple(ruleset.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=tuple(ruleset.battle_phase_sequence.phases).index(BattlePhase.MOVEMENT),
        battle_round=1,
        active_player_id="player-a",
        army_definitions=list(scenario.armies),
        battlefield_state=scenario.battlefield_state,
    )


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    assert state.battlefield_state is not None
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _single_model_forward_witness(
    unit_placement: UnitPlacement,
    *,
    movement_inches: float,
) -> PathWitness:
    model_placement = unit_placement.model_placements[0]
    facing_radians = math.radians(model_placement.pose.facing.degrees)
    return PathWitness.for_straight_line_endpoints(
        (
            (
                model_placement.model_instance_id,
                model_placement.pose,
                Pose.at(
                    model_placement.pose.position.x + (movement_inches * math.cos(facing_radians)),
                    model_placement.pose.position.y + (movement_inches * math.sin(facing_radians)),
                    z=model_placement.pose.position.z,
                    facing_degrees=model_placement.pose.facing.degrees,
                ),
            ),
        )
    )


def _single_model_movement_payload(
    movement_payload: Mapping[str, object],
) -> dict[str, object]:
    model_movements = cast(list[object], movement_payload["model_movements"])
    assert len(model_movements) == 1
    return cast(dict[str, object], model_movements[0])


def _model_movement_inches(model: ModelInstance) -> int:
    for characteristic in model.characteristics:
        if characteristic.characteristic is Characteristic.MOVEMENT:
            return characteristic.final
    raise AssertionError("Missing Movement characteristic.")


def _submit_custom_normal_move_decision(
    handler: MovementPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    unit_placement: UnitPlacement,
    witness: PathWitness,
    result_id: str,
) -> LifecycleStatus | None:
    resolution = resolve_normal_move(
        scenario=_scenario_from_state(state),
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=witness,
        hover_mode_states=tuple(state.hover_mode_states),
    )
    custom_payload = validate_json_value(
        {
            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
            "displacement_kind": "normal_move",
            "unit_instance_id": unit_placement.unit_instance_id,
            "witness": resolution.witness.to_payload(),
            **resolution.movement_payload,
        }
    )
    custom_options = tuple(
        DecisionOption(
            option_id=option.option_id,
            label=option.label,
            payload=custom_payload,
        )
        if option.option_id == MovementPhaseActionKind.NORMAL_MOVE.value
        else option
        for option in request.options
    )
    custom_request = DecisionRequest(
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=request.payload,
        options=custom_options,
    )
    decisions.queue.remove_by_id(request.request_id)
    decisions.request_decision(custom_request)
    result = DecisionResult.for_request(
        result_id=result_id,
        request=custom_request,
        selected_option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
    )
    decisions.submit_result(result)
    return handler.apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )


def _movement_action_request_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.movement_phase_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    selection_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert selection_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    selection_status = _submit_handler_decision(
        handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=unit_instance_id,
        result_id=f"{unit_instance_id}:select-move",
    )
    assert selection_status is None
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return handler, decisions, action_request


def _submit_handler_decision(
    handler: MovementPhaseHandler,
    *,
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
    return handler.apply_decision(
        state=state,
        result=result,
        decisions=decisions,
    )


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _last_event_payload(
    decisions: DecisionController,
    event_type: str,
) -> dict[str, object]:
    for event in reversed(decisions.event_log.records):
        if event.event_type == event_type:
            assert isinstance(event.payload, dict)
            return cast(dict[str, object], event.payload)
    raise AssertionError(f"Missing event type: {event_type}")


def _with_unit_first_model_pose(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    pose: Pose,
) -> BattlefieldScenario:
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    first_placement = unit_placement.model_placements[0].with_pose(pose)
    updated_placement = unit_placement.with_model_placements(
        (first_placement, *unit_placement.model_placements[1:])
    )
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=scenario.battlefield_state.with_unit_placement(updated_placement),
    )


def _place_unit_in_engagement_of_mover(
    *,
    scenario: BattlefieldScenario,
    mover: UnitInstance,
    enemy: UnitInstance,
    direction: float,
) -> BattlefieldScenario:
    mover_placement = scenario.battlefield_state.unit_placement_by_id(mover.unit_instance_id)
    mover_pose = mover_placement.model_placements[0].pose
    gap_inches = _first_model_radius_x(mover) + _first_model_radius_x(enemy) + 0.5
    return _with_unit_first_model_pose(
        scenario=scenario,
        unit_instance_id=enemy.unit_instance_id,
        pose=Pose.at(
            mover_pose.position.x + (direction * gap_inches),
            mover_pose.position.y,
        ),
    )


def _first_model_radius_x(unit: UnitInstance) -> float:
    return unit.own_models[0].geometry.primary_part().radius_x_inches


def _hover_state_for_aircraft(aircraft: UnitInstance) -> HoverModeState:
    return HoverModeState.active_for_unit(
        player_id="player-a",
        unit_instance_id=aircraft.unit_instance_id,
        decision_request_id="phase10r-hover-request",
        decision_result_id="phase10r-hover-result",
    )


def _advance_roll_result(unit_instance_id: str) -> AdvanceRollResult:
    request = AdvanceRollRequest.for_unit(
        request_id="phase10r-advance-roll-request",
        game_id="phase10r-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_result = DiceRollResult.from_values(
        roll_id="phase10r-advance-roll",
        spec=request.spec,
        values=[1],
        source="fixed",
    )
    return AdvanceRollResult.from_roll_state(
        request=request,
        roll_state=DiceRollState.from_result(roll_result),
    )


def _aircraft_scenario() -> tuple[BattlefieldScenario, UnitInstance, UnitInstance]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    alpha = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-a",
            army_id="army-alpha",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="aircraft-unit",
                    datasheet_id="core-vehicle-monster",
                    model_profile_id="core-vehicle-monster",
                    model_count=1,
                ),
            ),
        ),
    )
    beta = muster_army(
        catalog=catalog,
        request=_army_muster_request(
            catalog=catalog,
            player_id="player-b",
            army_id="army-beta",
            unit_selections=(
                _unit_selection(
                    unit_selection_id="enemy-unit",
                    datasheet_id="core-intercessor-like-infantry",
                    model_profile_id="core-intercessor-like",
                    model_count=5,
                ),
            ),
        ),
    )
    aircraft = replace(
        alpha.unit_by_id("army-alpha:aircraft-unit"),
        keywords=("Aircraft", "Fly", "Hover", "Vehicle"),
    )
    alpha = replace(
        alpha,
        units=tuple(
            aircraft if unit.unit_instance_id == aircraft.unit_instance_id else unit
            for unit in alpha.units
        ),
    )
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10r-battlefield",
        armies=(alpha, beta),
    )
    return scenario, aircraft, beta.unit_by_id("army-beta:enemy-unit")


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


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _single_model_placement(unit: UnitInstance, *, pose: Pose) -> UnitPlacement:
    model = unit.own_models[0]
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=unit.unit_instance_id,
                model_instance_id=model.model_instance_id,
                pose=pose,
            ),
        ),
    )


def _blocking_wall_feature(*, x: float, y: float) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase10r-wall",
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


def _geometry_model(model_id: str, *, x: float, y: float) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x, y),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_tenth(descriptor_version="core-v2-phase10r-test")
