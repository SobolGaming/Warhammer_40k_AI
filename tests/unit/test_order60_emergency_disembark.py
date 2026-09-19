from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction

import pytest
from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
from tests.order60_emergency_disembark_helpers import (
    order60_blocking_wall_feature,
    order60_emergency_session,
    order60_just_beyond_terrain_clear_placement,
    order60_omit_unplaceable_large_placement,
    order60_passenger_placement,
    order60_place_enemies_near_transport,
    order60_resolve_emergency,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import UnitPlacement, geometry_model_for_placement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.emergency_disembark_placement import (
    append_emergency_disembark_rules_unit_omission_violations,
)
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transports import TransportOperationViolationCode
from warhammer40k_core.geometry.emergency_disembark_fit import (
    AxisAlignedRectObstacle,
    CircularEmergencyPoseQuery,
    circular_emergency_pose_exists,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_emergency_disembark_placement_2026_09 as placement_source,
)


def test_circular_emergency_pose_existence_excludes_axis_aligned_walls() -> None:
    query = CircularEmergencyPoseQuery(
        transport_x=Fraction(10),
        transport_y=Fraction(10),
        transport_radius=Fraction("197/100"),
        passenger_radius=Fraction("63/100"),
        containment_center_limit=Fraction("734/100"),
        battlefield_width=Fraction(60),
        battlefield_depth=Fraction(44),
        overlap_obstacles=(),
        unengaged_obstacles=(),
        require_unengaged=False,
        closer_than_center=Fraction("460/100"),
        neighbor_obstacles=(),
        span_obstacles=(),
    )
    assert circular_emergency_pose_exists(query) is True
    blocked = CircularEmergencyPoseQuery(
        transport_x=query.transport_x,
        transport_y=query.transport_y,
        transport_radius=query.transport_radius,
        passenger_radius=query.passenger_radius,
        containment_center_limit=query.containment_center_limit,
        battlefield_width=query.battlefield_width,
        battlefield_depth=query.battlefield_depth,
        overlap_obstacles=(),
        unengaged_obstacles=(),
        require_unengaged=False,
        closer_than_center=query.closer_than_center,
        neighbor_obstacles=(),
        span_obstacles=(),
        rect_obstacles=(
            AxisAlignedRectObstacle(
                min_x=Fraction(0),
                max_x=Fraction(14),
                min_y=Fraction(0),
                max_y=Fraction(44),
            ),
        ),
    )
    assert circular_emergency_pose_exists(blocked) is False


def test_emergency_disembark_places_every_survivor_on_the_closest_ring() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid, result.violations
    assert result.updated_cargo_state is not None
    assert result.disembarked_unit_state is not None
    assert result.disembarked_unit_state.battle_shocked_until == "end_of_turn"
    assert type(result).from_payload(result.to_payload()) == result
    assert placement_source.PLACEMENT_POLICY.destroys_only_unplaceable_models is True


def test_emergency_disembark_rejects_omitting_a_placeable_survivor() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(
        session,
        order60_passenger_placement(session, omit_last=True),
    )
    assert result.is_valid is False
    assert any(
        violation.violation_code
        is TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
        and violation.source_rule_id == placement_source.EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID
        for violation in result.violations
    )
    assert result.updated_cargo_state is None


def test_emergency_disembark_rejects_a_pose_that_is_not_closest() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session, far=True))
    assert result.is_valid is False
    assert any(
        violation.violation_code is TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST
        and violation.source_rule_id == placement_source.EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID
        for violation in result.violations
    )


def test_emergency_disembark_rejects_engaged_when_unengaged_exists() -> None:
    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    order60_place_enemies_near_transport(state)
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid is False
    assert any(
        violation.violation_code is TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE
        for violation in result.violations
    )


def test_emergency_disembark_destroys_only_a_genuinely_unplaceable_model() -> None:
    session = order60_emergency_session(oversized_base_diameter_inches=45)
    result = order60_resolve_emergency(session, order60_omit_unplaceable_large_placement(session))
    state = session.lifecycle.state
    assert state is not None
    passenger = unit_by_id(state=state, unit_instance_id=PASSENGER_ID)
    large_id = passenger.own_models[0].model_instance_id
    assert result.is_valid, result.violations
    assert all(
        violation.violation_code
        is not TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
        for violation in result.violations
    )
    omitted = {model.model_instance_id for model in passenger.own_models} - {
        placement.model_instance_id
        for placement in result.selection.attempted_placement.model_placements
    }
    assert omitted == {large_id}


def test_emergency_disembark_does_not_treat_wall_interior_as_closer() -> None:
    session = order60_emergency_session()
    placement = order60_just_beyond_terrain_clear_placement(session)
    terrain_free = order60_resolve_emergency(session, placement)
    assert any(
        violation.violation_code is TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST
        for violation in terrain_free.violations
    )
    result = order60_resolve_emergency(
        session,
        placement,
        terrain_features=(order60_blocking_wall_feature(),),
    )
    assert result.is_valid, result.violations
    assert all(
        violation.violation_code
        is not TransportOperationViolationCode.EMERGENCY_DISEMBARK_NOT_CLOSEST
        for violation in result.violations
    )


def test_emergency_disembark_ignores_vertically_separated_enemies() -> None:
    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    order60_place_enemies_near_transport(state, z_inches=12.0)
    placement = order60_passenger_placement(session)
    scenario = battlefield_scenario_for_state(state=state)
    ruleset = state.runtime_ruleset_descriptor()
    passengers = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in placement.model_placements
    )
    enemies = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for army in scenario.battlefield_state.placed_armies
        for unit_placement in army.unit_placements
        for model_placement in unit_placement.model_placements
        if model_placement.player_id == "player-b"
    )
    assert passengers
    assert enemies
    assert all(
        not passenger.is_within_engagement_range(
            enemy,
            horizontal_inches=ruleset.engagement_policy.horizontal_inches,
            vertical_inches=ruleset.engagement_policy.vertical_inches,
        )
        for passenger in passengers
        for enemy in enemies
    )
    result = order60_resolve_emergency(session, placement)
    assert result.is_valid, result.violations
    assert all(
        violation.violation_code is not TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE
        for violation in result.violations
    )


def test_emergency_disembark_restore_preserves_valid_resolution() -> None:
    session = order60_emergency_session()
    result = order60_resolve_emergency(session, order60_passenger_placement(session))
    assert result.is_valid
    restored_lifecycle = GameLifecycle.from_payload(
        json.loads(json.dumps(session.lifecycle.to_payload()))
    )
    restored = LocalGameSession(lifecycle=restored_lifecycle)
    restored_result = order60_resolve_emergency(
        restored,
        order60_passenger_placement(restored),
    )
    assert restored_result.to_payload() == result.to_payload()
    for viewer in ("player-a", "player-b"):
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)


def test_emergency_disembark_floor_interior_cannot_prove_a_closer_pose() -> None:
    session = order60_emergency_session()
    wall_feature = order60_blocking_wall_feature()
    (wall,) = wall_feature.walls
    feature = replace(
        wall_feature,
        walls=(),
        floors=(
            TerrainFloorDefinition(
                floor_id="blocking-slab",
                center_x_inches=wall.center_x_inches,
                center_y_inches=wall.center_y_inches,
                bottom_z_inches=1.0,
                width_inches=wall.width_inches,
                depth_inches=wall.depth_inches,
                thickness_inches=0.5,
            ),
        ),
    )
    placement = order60_just_beyond_terrain_clear_placement(session)
    _assert_terrain_endpoints(session, placement, feature, legal=True)
    _assert_terrain_endpoints(session, order60_passenger_placement(session), feature, legal=False)
    before = session.lifecycle.to_payload()
    with pytest.raises(GameLifecycleError, match="placement proof is unresolved"):
        order60_resolve_emergency(session, placement, terrain_features=(feature,))
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize("grouped_omission", [False, True])
def test_emergency_disembark_ground_failure_cannot_authorize_elevated_survivor_omission(
    grouped_omission: bool,
) -> None:
    session = order60_emergency_session()
    feature = _elevated_support_feature()
    ground = order60_passenger_placement(session)
    elevated = replace(
        ground,
        model_placements=tuple(
            replace(row, pose=Pose.at(row.pose.position.x, row.pose.position.y, 6.0))
            for row in ground.model_placements
        ),
    )
    # All five survivors have legal supported endpoints; ground is blocked.
    _assert_terrain_endpoints(session, elevated, feature, legal=True)
    _assert_terrain_endpoints(session, ground, feature, legal=False)
    partial = replace(elevated, model_placements=elevated.model_placements[:-1])
    state = session.lifecycle.state
    assert state is not None
    before = session.lifecycle.to_payload()
    if grouped_omission:
        scenario = battlefield_scenario_for_state(state=state)
        with pytest.raises(GameLifecycleError, match="placement proof is unresolved"):
            append_emergency_disembark_rules_unit_omission_violations(
                violations=[],
                scenario=scenario,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
                rules_unit=rules_unit_view_from_armies(
                    armies=scenario.armies, unit_instance_id=PASSENGER_ID
                ),
                attempted_placement=RulesUnitPlacement.single(partial),
                transport_placement=scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID),
                battlefield_width_inches=60,
                battlefield_depth_inches=44,
                terrain_features=(feature,),
                objective_markers=(),
            )
    else:
        with pytest.raises(GameLifecycleError, match="placement proof is unresolved"):
            order60_resolve_emergency(session, partial, terrain_features=(feature,))
    assert session.lifecycle.to_payload() == before
    # Complete elevated proposals also need a support-aware closest/unengaged proof.
    with pytest.raises(GameLifecycleError, match="placement proof is unresolved"):
        order60_resolve_emergency(session, elevated, terrain_features=(feature,))


@pytest.mark.parametrize("floor_z", [0.0, 1.0, 6.0])
def test_emergency_disembark_irrelevant_floor_does_not_block_the_proof(floor_z: float) -> None:
    session = order60_emergency_session()
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        display_template_id="distant-floor",
        center_x_inches=50.0,
        center_y_inches=30.0,
        width_inches=2.0,
        depth_inches=2.0,
    )
    feature = TerrainFeatureDefinition(
        feature_id="distant-floor",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=50.0,
        footprint_center_y_inches=30.0,
        footprint_width_inches=2.0,
        footprint_depth_inches=2.0,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(
            TerrainFloorDefinition(
                floor_id="floor",
                center_x_inches=50.0,
                center_y_inches=30.0,
                bottom_z_inches=floor_z,
                width_inches=2.0,
                depth_inches=2.0,
                thickness_inches=0.5,
            ),
        ),
    )
    result = order60_resolve_emergency(
        session, order60_passenger_placement(session), terrain_features=(feature,)
    )
    assert result.is_valid, result.violations


def _assert_terrain_endpoints(
    session: LocalGameSession,
    placement: UnitPlacement,
    feature: TerrainFeatureDefinition,
    *,
    legal: bool,
) -> None:
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    for row in placement.model_placements:
        violation = terrain_endpoint_placement_violation(
            model=geometry_model_for_placement(
                model=scenario.model_instance_for_placement(row), placement=row
            ),
            unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            terrain_features=(feature,),
            violation_code=TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Emergency Disembark regression",
        )
        assert (violation is None) is legal, violation


def _elevated_support_feature() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        display_template_id="elevated-support",
        center_x_inches=10.0,
        center_y_inches=10.0,
        width_inches=20.0,
        depth_inches=20.0,
    )
    return TerrainFeatureDefinition(
        feature_id="elevated-support",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=10.0,
        footprint_center_y_inches=10.0,
        footprint_width_inches=20.0,
        footprint_depth_inches=20.0,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="ground-blocker",
                center_x_inches=10.0,
                center_y_inches=10.0,
                bottom_z_inches=0.0,
                width_inches=20.0,
                depth_inches=20.0,
                height_inches=4.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="supported-floor",
                center_x_inches=10.0,
                center_y_inches=10.0,
                bottom_z_inches=6.0,
                width_inches=20.0,
                depth_inches=20.0,
                thickness_inches=0.5,
            ),
        ),
    )
