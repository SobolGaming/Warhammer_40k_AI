from __future__ import annotations

import json
from fractions import Fraction

from tests.disembark_eligibility_helpers import PASSENGER_ID
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
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.transports import TransportOperationViolationCode
from warhammer40k_core.geometry.emergency_disembark_fit import (
    AxisAlignedRectObstacle,
    CircularEmergencyPoseQuery,
    circular_emergency_pose_exists,
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
