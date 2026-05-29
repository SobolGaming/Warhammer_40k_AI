from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
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
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement import (
    MovementActionAvailabilityContext,
    MovementPhaseActionKind,
    resolve_normal_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import ReserveOrigin, ReservePlacementViolationCode
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.movement_envelope import MovementDistanceWitness
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
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
