"""Shared Order 60 Emergency Disembark placement fixtures."""

from __future__ import annotations

from math import cos, radians, sin

from tests.core_stratagem_helpers import _replace_unit_poses
from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID, disembark_session
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.transports import (
    DisembarkModeKind,
    DisembarkResolution,
    DisembarkSelection,
    TransportMovementStatus,
    resolve_disembark_internal,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

_TRANSPORT_RADIUS_INCHES = 50.0 / 25.4
_INTERCESSOR_RADIUS_INCHES = 16.0 / 25.4
_CONTACT_GAP_INCHES = 0.02
_COHERENT_STEP_DEGREES = 40.0
ORDER60_BLOCKING_WALL_OUTER_X_INCHES = 14.0
ORDER60_TERRAIN_CLEAR_EXTRA_INCHES = 0.01
EMERGENCY_CONTACT_RADIUS_INCHES = (
    _TRANSPORT_RADIUS_INCHES + _INTERCESSOR_RADIUS_INCHES + _CONTACT_GAP_INCHES
)
EMERGENCY_TRANSPORT_CENTER = (10.0, 10.0)
ENEMY_TRANSPORT_CENTER = (35.0, 35.0)


def emergency_contact_radius_inches(model: ModelInstance) -> float:
    diameter_mm = model.base_size.diameter_mm
    if diameter_mm is None:
        raise AssertionError("Emergency Disembark poses require a circular base diameter.")
    return _TRANSPORT_RADIUS_INCHES + (diameter_mm / 50.8) + _CONTACT_GAP_INCHES


def emergency_disembark_contact_poses(
    models: tuple[ModelInstance, ...],
    *,
    center_x: float,
    center_y: float,
    z_inches: float = 0.0,
    start_degrees: float = 0.0,
    step_degrees: float = _COHERENT_STEP_DEGREES,
) -> tuple[Pose, ...]:
    if not models:
        raise AssertionError("Emergency Disembark poses require at least one model.")
    return tuple(
        Pose.at(
            center_x
            + emergency_contact_radius_inches(model)
            * cos(radians(start_degrees + step_degrees * index)),
            center_y
            + emergency_contact_radius_inches(model)
            * sin(radians(start_degrees + step_degrees * index)),
            z_inches,
        )
        for index, model in enumerate(models)
    )


def emergency_disembark_poses_around(
    *,
    center_x: float,
    center_y: float,
    count: int,
    z_inches: float = 0.0,
    radius_inches: float = EMERGENCY_CONTACT_RADIUS_INCHES,
    start_degrees: float = 0.0,
    step_degrees: float | None = None,
) -> tuple[Pose, ...]:
    if type(count) is not int or count < 1:
        raise AssertionError("Emergency Disembark poses require at least one model.")
    step = min(360.0 / count, 70.0) if step_degrees is None else step_degrees
    return tuple(
        Pose.at(
            center_x + radius_inches * cos(radians(start_degrees + step * index)),
            center_y + radius_inches * sin(radians(start_degrees + step * index)),
            z_inches,
        )
        for index in range(count)
    )


def emergency_disembark_unit_placement(
    unit: UnitInstance,
    *,
    army_id: str,
    player_id: str,
    center_x: float,
    center_y: float,
    omit_last: bool = False,
    model_count: int | None = None,
) -> UnitPlacement:
    models = unit.alive_own_models() if model_count is None else unit.own_models
    count = len(models) if model_count is None else model_count
    selected = models[:count]
    poses = emergency_disembark_contact_poses(
        selected,
        center_x=center_x,
        center_y=center_y,
    )
    placements = tuple(
        ModelPlacement(
            army_id=army_id,
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            model_instance_id=model.model_instance_id,
            pose=pose,
        )
        for model, pose in zip(selected, poses, strict=True)
    )[:count]
    if omit_last:
        placements = placements[:-1]
    return UnitPlacement(
        army_id=army_id,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        model_placements=placements,
    )


def order60_emergency_session(
    *,
    oversized_base_diameter_inches: float | None = None,
) -> LocalGameSession:
    return disembark_session(oversized_base_diameter_inches=oversized_base_diameter_inches)


def order60_passenger_placement(
    session: LocalGameSession,
    *,
    omit_last: bool = False,
    far: bool = False,
    omit_first: bool = False,
) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    unit = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    center_x, center_y = EMERGENCY_TRANSPORT_CENTER
    if far:
        return UnitPlacement(
            army_id="army-alpha",
            player_id="player-a",
            unit_instance_id=PASSENGER_ID,
            model_placements=tuple(
                ModelPlacement(
                    army_id="army-alpha",
                    player_id="player-a",
                    unit_instance_id=PASSENGER_ID,
                    model_instance_id=model.model_instance_id,
                    pose=Pose.at(13.1 + 0.4 * index, 8.5 + 0.7 * index),
                )
                for index, model in enumerate(unit.own_models)
            ),
        )
    placement = emergency_disembark_unit_placement(
        unit,
        army_id="army-alpha",
        player_id="player-a",
        center_x=center_x,
        center_y=center_y,
        omit_last=omit_last,
    )
    if omit_first:
        return UnitPlacement(
            army_id=placement.army_id,
            player_id=placement.player_id,
            unit_instance_id=placement.unit_instance_id,
            model_placements=placement.model_placements[1:],
        )
    return placement


def order60_resolve_emergency(
    session: LocalGameSession,
    attempted_placement: UnitPlacement,
    *,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> DisembarkResolution:
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    return resolve_disembark_internal(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        cargo_state=state.transport_cargo_states[0],
        selection=DisembarkSelection(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=PASSENGER_ID,
            transport_unit_instance_id=TRANSPORT_ID,
            attempted_placement=attempted_placement,
            disembark_mode=DisembarkModeKind.EMERGENCY_DISEMBARK,
            transport_movement_status=TransportMovementStatus.NOT_MOVED,
        ),
        unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
        turn_player_id="player-a",
        require_started_phase_embarked=False,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        terrain_features=terrain_features,
        objective_markers=(),
    )


def order60_place_enemies_near_transport(state: GameState, *, z_inches: float = 0.0) -> None:
    center_x, center_y = EMERGENCY_TRANSPORT_CENTER
    for army in state.army_definitions:
        if army.player_id != "player-b":
            continue
        for unit in army.units:
            _replace_unit_poses(
                state,
                unit_instance_id=unit.unit_instance_id,
                poses=emergency_disembark_poses_around(
                    center_x=center_x,
                    center_y=center_y,
                    count=len(unit.own_models),
                    z_inches=z_inches,
                    radius_inches=EMERGENCY_CONTACT_RADIUS_INCHES,
                    start_degrees=36.0,
                ),
            )


def order60_oversized_closest_placement(session: LocalGameSession) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    unit = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    large = unit.own_models[0]
    diameter_mm = large.base_size.diameter_mm
    assert diameter_mm is not None
    large_radius = diameter_mm / 50.8
    center_x, center_y = EMERGENCY_TRANSPORT_CENTER
    large_pose = Pose.at(
        center_x,
        center_y + _TRANSPORT_RADIUS_INCHES + large_radius + 0.02,
    )
    small_poses = tuple(
        Pose.at(
            center_x + EMERGENCY_CONTACT_RADIUS_INCHES * cos(radians(angle_degrees)),
            center_y + EMERGENCY_CONTACT_RADIUS_INCHES * sin(radians(angle_degrees)),
        )
        for angle_degrees in (20.0, 160.0, 200.0, 340.0)
    )
    poses = (large_pose, *small_poses)
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=PASSENGER_ID,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=PASSENGER_ID,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )


def order60_omit_unplaceable_large_placement(session: LocalGameSession) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    unit = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    small_models = unit.own_models[1:]
    poses = emergency_disembark_poses_around(
        center_x=EMERGENCY_TRANSPORT_CENTER[0],
        center_y=EMERGENCY_TRANSPORT_CENTER[1],
        count=len(small_models),
        step_degrees=30.0,
        start_degrees=180.0,
    )
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=PASSENGER_ID,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=PASSENGER_ID,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(small_models, poses, strict=True)
        ),
    )


def order60_model_radius_inches(model: ModelInstance) -> float:
    diameter_mm = model.base_size.diameter_mm
    if diameter_mm is None:
        raise AssertionError("Emergency Disembark wall poses require a circular base diameter.")
    return diameter_mm / 50.8


def order60_blocking_wall_feature() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        display_template_id="order60-emergency-blocking-wall",
        center_x_inches=7.0,
        center_y_inches=22.0,
        width_inches=14.0,
        depth_inches=44.0,
    )
    return TerrainFeatureDefinition(
        feature_id="order60-emergency-blocking-wall",
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=7.0,
        footprint_center_y_inches=22.0,
        footprint_width_inches=14.0,
        footprint_depth_inches=44.0,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="solid",
                center_x_inches=7.0,
                center_y_inches=22.0,
                bottom_z_inches=0.0,
                width_inches=14.0,
                depth_inches=44.0,
                height_inches=4.0,
            ),
        ),
    )


def order60_just_beyond_terrain_clear_placement(
    session: LocalGameSession,
    *,
    extra_inches: float = ORDER60_TERRAIN_CLEAR_EXTRA_INCHES,
) -> UnitPlacement:
    state = session.lifecycle.state
    assert state is not None
    unit = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    radii = tuple(order60_model_radius_inches(model) for model in unit.own_models)
    relative = [0.0]
    for index in range(1, len(radii)):
        relative.append(relative[-1] + radii[index - 1] + radii[index] + _CONTACT_GAP_INCHES)
    offset = relative[-1] / 2.0
    poses = tuple(
        Pose.at(
            ORDER60_BLOCKING_WALL_OUTER_X_INCHES + radius + extra_inches,
            10.0 - offset + relative_y,
        )
        for radius, relative_y in zip(radii, relative, strict=True)
    )
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=PASSENGER_ID,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=PASSENGER_ID,
                model_instance_id=model.model_instance_id,
                pose=pose,
            )
            for model, pose in zip(unit.own_models, poses, strict=True)
        ),
    )
