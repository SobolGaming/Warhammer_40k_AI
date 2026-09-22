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
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import UnitPlacement, geometry_model_for_placement
from warhammer40k_core.engine.damage_allocation import unit_by_id
from warhammer40k_core.engine.emergency_disembark_placement import (
    append_emergency_disembark_placement_violations,
    append_emergency_disembark_rules_unit_omission_violations,
)
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.transport_disembark_geometry import geometry_models_for_unit_placement
from warhammer40k_core.engine.transports import (
    TransportOperationViolation,
    TransportOperationViolationCode,
)
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.emergency_setup_proof import (
    EmergencySetupQuery,
    SetupTerrain,
    emergency_setup_pose_exists,
    emergency_setup_pose_is_legal,
)
from warhammer40k_core.geometry.measurement import objective_marker_endpoint_is_clear
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_emergency_disembark_placement_2026_09 as placement_source,
)


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
    placement = order60_passenger_placement(session)
    placement = replace(
        placement,
        model_placements=tuple(
            replace(
                row,
                pose=Pose.at(
                    10 + 1.2 * (row.pose.position.x - 10),
                    10 + 1.2 * (row.pose.position.y - 10),
                ),
            )
            for row in placement.model_placements
        ),
    )
    result = order60_resolve_emergency(session, placement)
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
    result = order60_resolve_emergency(session, placement, terrain_features=(feature,))
    assert result.is_valid, result.violations
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
        violations: list[TransportOperationViolation] = []
        append_emergency_disembark_rules_unit_omission_violations(
            violations=violations,
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
        assert any(
            row.violation_code
            is TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
            for row in violations
        )
    else:
        result = order60_resolve_emergency(session, partial, terrain_features=(feature,))
        assert any(
            row.violation_code
            is TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
            for row in result.violations
        )
    assert session.lifecycle.to_payload() == before
    # Complete proposals use the same support-aware closest/unengaged proof.
    result = order60_resolve_emergency(session, elevated, terrain_features=(feature,))
    assert result.is_valid, result.violations


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


def _analytic_query(passenger: BaseShape, transport: BaseShape) -> EmergencySetupQuery:
    return EmergencySetupQuery(
        passenger=Model("passenger", Pose.at(0, 0), passenger, ModelVolume(2)),
        transports=(
            Model("transport", Pose.at(10, 10, facing_degrees=37), transport, ModelVolume(3)),
        ),
        blockers=(),
        enemies=(),
        partners=(),
        terrain=(),
        objective_disks=(),
        width=Fraction(30),
        depth=Fraction(30),
        neighbor_limit=Fraction(2),
        vertical_limit=Fraction(5),
        span_limit=Fraction(8),
        engagement=Fraction(1),
        engagement_vertical=Fraction(5),
        setup_distance=Fraction(6),
        oversized_distance=Fraction(1),
        ordinary_size_fit=True,
        require_unengaged=True,
        closer_than=None,
        closest_tolerance=Fraction("0.04"),
    )


@pytest.mark.parametrize("passenger", [CircularBase(0.5), OvalBase(2, 1), RectangularBase(2, 1)])
@pytest.mark.parametrize("transport", [CircularBase(2), OvalBase(4, 2), RectangularBase(4, 2)])
def test_emergency_proof_covers_analytic_base_pairs(
    passenger: BaseShape, transport: BaseShape
) -> None:
    query = _analytic_query(passenger, transport)
    assert emergency_setup_pose_exists(query)
    assert not emergency_setup_pose_exists(replace(query, width=Fraction("0.4")))


@pytest.mark.parametrize("allowed", [False, True])
def test_emergency_proof_respects_supported_elevation_permissions(allowed: bool) -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    terrain = SetupTerrain(_elevated_support_feature(), True, allowed, True, False)
    assert emergency_setup_pose_exists(replace(query, terrain=(terrain,))) is allowed


@pytest.mark.parametrize(("wall_width", "expected"), [(2.0, True), (30.0, False)])
def test_emergency_proof_uses_rotated_wall_geometry(wall_width: float, expected: bool) -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    feature = _elevated_support_feature()
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        display_template_id="rotated-wall-footprint",
        center_x_inches=10,
        center_y_inches=10,
        width_inches=50,
        depth_inches=50,
    )
    feature = replace(
        feature,
        footprint_width_inches=50,
        footprint_depth_inches=50,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        floors=(),
        walls=(
            replace(
                feature.walls[0], width_inches=wall_width, depth_inches=30, rotation_degrees=37
            ),
        ),
    )
    terrain = SetupTerrain(feature, True, True, True, False)
    assert emergency_setup_pose_exists(replace(query, terrain=(terrain,))) is expected


def test_emergency_proof_excludes_overhang_and_out_of_range_elevations() -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    feature = _elevated_support_feature()
    floor = feature.floors[0]
    tiny = replace(feature, floors=(replace(floor, width_inches=0.8, depth_inches=0.8),))
    high = replace(feature, floors=(replace(floor, bottom_z_inches=10),))
    for blocked in (tiny, high):
        assert not emergency_setup_pose_exists(
            replace(query, terrain=(SetupTerrain(blocked, True, True, True, False),))
        )
    # Cached negative results cannot survive a support-policy or elevation change.
    assert emergency_setup_pose_exists(
        replace(query, terrain=(SetupTerrain(feature, True, True, True, False),))
    )
    assert emergency_setup_pose_exists(
        replace(query, terrain=(SetupTerrain(tiny, True, True, False, False),))
    )


@pytest.mark.parametrize("passenger", [OvalBase(4, 1), RectangularBase(4, 1)])
def test_emergency_proof_searches_orientations(passenger: BaseShape) -> None:
    query = _analytic_query(passenger, CircularBase(0.25))
    transport = replace(query.transports[0], pose=Pose.at(0.55, 6))
    query = replace(query, transports=(transport,), width=Fraction("1.1"), depth=Fraction(12))
    assert emergency_setup_pose_exists(query)


def test_emergency_proof_keeps_vertical_coherency_and_unengaged_preference() -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    feature = _elevated_support_feature()
    query = replace(query, terrain=(SetupTerrain(feature, True, True, True, False),))
    partner = Model("partner", Pose.at(10, 10, 20), CircularBase(0.5), ModelVolume(2))
    assert not emergency_setup_pose_exists(replace(query, partners=(partner,)))
    enemy = Model("enemy", Pose.at(10, 10, 6), CircularBase(12), ModelVolume(1))
    # All supported endpoints are engaged, but the explicit engaged alternative survives.
    assert not emergency_setup_pose_exists(replace(query, enemies=(enemy,)))
    assert emergency_setup_pose_exists(replace(query, enemies=(enemy,), require_unengaged=False))


@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("rectangular", [False, True])
def test_emergency_geometry_facade_restore_and_replay(attached: bool, rectangular: bool) -> None:
    from tests.emergency_geometry_helpers import emergency_geometry_session

    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    session, proposal = emergency_geometry_session(attached=attached, rectangular=rectangular)
    state = session.lifecycle.state
    assert state is not None
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    for kind in ("malformed", "stale", "wrong_context"):
        raw = validate_json_value(proposal.to_payload())
        assert isinstance(raw, dict)
        if kind == "malformed":
            del raw["disembark_mode"]
        elif kind == "stale":
            raw["proposal_request_id"] = "stale-request"
        else:
            raw["transport_unit_instance_id"] = "other-transport"
        before = state.to_payload()
        records = tuple(session.lifecycle.decision_controller.records)
        rejected = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=kind, payload=raw
        )
        assert rejected.status_kind is LifecycleStatusKind.INVALID
        assert state.to_payload() == before
        assert tuple(session.lifecycle.decision_controller.records) == records
        assert session.lifecycle.pending_decision_request() == request
    initial = session.lifecycle.to_payload()
    components = (
        proposal.attempted_rules_unit_placement.component_unit_placements
        if proposal.attempted_rules_unit_placement is not None
        else (proposal.require_unit_placement(),)
    )
    floating = tuple(
        replace(
            component,
            model_placements=tuple(
                replace(row, pose=Pose.at(row.pose.position.x, row.pose.position.y, 20))
                for row in component.model_placements
            ),
        )
        for component in components
    )
    invalid_proposal = replace(
        proposal,
        attempted_placement=None if attached else floating[0],
        attempted_rules_unit_placement=RulesUnitPlacement(
            rules_unit_instance_id=proposal.unit_instance_id,
            component_unit_placements=floating,
        )
        if attached
        else None,
    )
    battlefield_before = state.battlefield_state
    cargo_before = tuple(state.transport_cargo_states)
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="floating-endpoint",
        payload=validate_json_value(invalid_proposal.to_payload()),
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == battlefield_before
    assert tuple(state.transport_cargo_states) == cargo_before
    request = session.lifecycle.pending_decision_request()
    assert request is not None
    assert request.request_id != proposal.proposal_request_id
    proposal = replace(proposal, proposal_request_id=request.request_id)
    restored = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
    )
    for target in (session, restored):
        accepted = target.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="emergency-place",
            payload=validate_json_value(proposal.to_payload()),
        )
        assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    restored = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
    )
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="emergency-geometry",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
    assert state.battlefield_state is not None
    placed = proposal.attempted_rules_unit_placement
    model_ids = (
        tuple(row.model_instance_id for row in placed.model_placements)
        if placed is not None
        else tuple(
            row.model_instance_id for row in proposal.require_unit_placement().model_placements
        )
    )
    assert set(model_ids).issubset(state.battlefield_state.placed_model_ids())
    assert "object at 0x" not in json.dumps(session.lifecycle.to_payload(), sort_keys=True)


def test_emergency_proof_must_reconnect_both_halves_of_an_attached_unit() -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    left = Model("left", Pose.at(2, 10), CircularBase(0.5), ModelVolume(2))
    right = replace(left, model_id="right", pose=Pose.at(18, 10))
    # Each half admits a nearby placement, but no placement can join both.
    assert not emergency_setup_pose_exists(replace(query, partners=(left, right), span_limit=None))
    assert emergency_setup_pose_exists(replace(query, partners=(left,), span_limit=None))


def test_emergency_endpoint_rejects_floating_and_out_of_range_supported_poses() -> None:
    from warhammer40k_core.geometry.emergency_setup_proof import emergency_setup_pose_is_legal

    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    query = replace(query, passenger=replace(query.passenger, pose=Pose.at(10, 10, 6)))
    assert not emergency_setup_pose_is_legal(query)
    feature = _elevated_support_feature()
    assert emergency_setup_pose_is_legal(
        replace(query, terrain=(SetupTerrain(feature, True, True, True, False),))
    )
    feature = replace(feature, floors=(replace(feature.floors[0], bottom_z_inches=20),))
    assert not emergency_setup_pose_is_legal(
        replace(
            query,
            passenger=replace(query.passenger, pose=Pose.at(10, 10, 20)),
            terrain=(SetupTerrain(feature, True, True, True, False),),
        )
    )


def test_emergency_proof_fits_a_thin_base_on_a_rotated_floor() -> None:
    query = _analytic_query(RectangularBase(4, 0.2), CircularBase(2))
    feature = _elevated_support_feature()
    feature = replace(
        feature,
        floors=(
            replace(feature.floors[0], width_inches=4.2, depth_inches=0.4, rotation_degrees=13),
        ),
    )
    # No 0/90/Transport-facing pose fits; the floor-oriented pose must be checked.
    assert emergency_setup_pose_exists(
        replace(query, terrain=(SetupTerrain(feature, True, True, True, False),))
    )


def test_emergency_proof_cache_tracks_objective_presence_and_restoration() -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    emergency_setup_pose_exists.cache_clear()
    assert emergency_setup_pose_exists(query)
    blocked = replace(query, objective_disks=((10, 10, 0, 100),))
    assert not emergency_setup_pose_exists(blocked)
    assert emergency_setup_pose_exists(query)
    assert not emergency_setup_pose_exists.__wrapped__(blocked)
    assert emergency_setup_pose_exists.__wrapped__(query)


@pytest.mark.parametrize(
    ("marker_z", "clear"),
    [(1.0, True), (0.0, False), (5e-10, False), (1e-9, False), (2e-9, True), (-5e-10, False)],
)
def test_emergency_objective_proofs_match_endpoint_contact_planes(
    marker_z: float, clear: bool
) -> None:
    query = _analytic_query(CircularBase(0.5), CircularBase(2))
    passenger = replace(query.passenger, pose=Pose.at(13, 10))
    # Cover the entire battlefield so an alternative cannot bypass the marker.
    query = replace(query, passenger=passenger, objective_disks=((13, 10, marker_z, 100),))
    assert (
        objective_marker_endpoint_is_clear(
            Pose.at(13, 10, marker_z), passenger, marker_diameter_inches=200
        )
        is clear
    )
    assert emergency_setup_pose_is_legal(query) is clear
    assert emergency_setup_pose_exists(query) is clear
    # The same contact-plane definition governs closer and unengaged alternatives.
    assert (
        emergency_setup_pose_exists(
            replace(query, closer_than=replace(passenger, pose=Pose.at(14, 10)))
        )
        is clear
    )


@pytest.mark.parametrize("grouped_omission", [False, True])
def test_noncontact_objective_cannot_authorize_emergency_survivor_omission(
    grouped_omission: bool,
) -> None:
    session = order60_emergency_session()
    state = session.lifecycle.state
    assert state is not None
    scenario = battlefield_scenario_for_state(state=state)
    complete = order60_passenger_placement(session)
    assert order60_resolve_emergency(session, complete).is_valid
    partial = replace(complete, model_placements=complete.model_placements[:-1])
    marker = ObjectiveMarker(
        objective_marker_id="r73-noncontact-marker",
        name="Non-contact marker",
        x_inches=10,
        y_inches=10,
        z_inches=1,
        marker_diameter_mm=200 * 25.4,
        blocks_placement=True,
    )
    complete_models = geometry_models_for_unit_placement(scenario=scenario, unit_placement=complete)
    assert all(
        objective_marker_endpoint_is_clear(
            Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
            model,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        for model in complete_models
    )
    before = session.lifecycle.to_payload()
    transport = scenario.battlefield_state.unit_placement_by_id(TRANSPORT_ID)
    violations: list[TransportOperationViolation] = []
    if grouped_omission:
        append_emergency_disembark_rules_unit_omission_violations(
            violations=violations,
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            rules_unit=rules_unit_view_from_armies(
                armies=scenario.armies, unit_instance_id=PASSENGER_ID
            ),
            attempted_placement=RulesUnitPlacement.single(partial),
            transport_placement=transport,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            terrain_features=(),
            objective_markers=(marker,),
        )
    else:
        append_emergency_disembark_placement_violations(
            violations=violations,
            scenario=scenario,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit=unit_by_id(state=state, unit_instance_id=PASSENGER_ID),
            attempted_placement=partial,
            models=geometry_models_for_unit_placement(scenario=scenario, unit_placement=partial),
            transport_models=geometry_models_for_unit_placement(
                scenario=scenario, unit_placement=transport
            ),
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            terrain_features=(),
            objective_markers=(marker,),
        )
    omitted = {row.model_instance_id for row in complete.model_placements} - {
        row.model_instance_id for row in partial.model_placements
    }
    assert {row.model_instance_id for row in violations} == omitted
    assert all(
        row.violation_code
        is TransportOperationViolationCode.EMERGENCY_DISEMBARK_OMITTED_MODEL_PLACEABLE
        and row.source_rule_id == placement_source.EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID
        for row in violations
    )
    assert session.lifecycle.to_payload() == before


@pytest.mark.parametrize(("x", "expected"), [(0.0, True), (0.01, False)])
def test_analytic_ellipse_containment_does_not_substitute_its_bounding_box(
    x: float, expected: bool
) -> None:
    from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates
    from warhammer40k_core.geometry.visibility_algebra import decide, term

    context = PlacementPredicates()
    ellipse = Footprint.fixed(OvalBase(4, 2), Pose.at(x, 0))
    circle = Footprint.fixed(CircularBase(1), Pose.at(0, 0))
    formula = context.contained(ellipse, circle, term(1))
    assert decide(formula, tuple(context.names)) is expected
    enclosure = Footprint.fixed(RectangularBase(4, 2), Pose.at(x, 0))
    formula = context.contained(enclosure, circle, term(1))
    assert not decide(formula, tuple(context.names))


@pytest.mark.parametrize(("x", "expected"), [(0.0, True), (20.0, False)])
def test_analytic_mixed_curved_contact_uses_actual_base_membership(
    x: float, expected: bool
) -> None:
    from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates
    from warhammer40k_core.geometry.visibility_algebra import decide, term

    context = PlacementPredicates()
    ellipse = Footprint.fixed(OvalBase(4, 2), Pose.at(x, 0))
    rectangle = Footprint.fixed(RectangularBase(2, 1), Pose.at(0, 0, facing_degrees=37))
    formula = context.near(ellipse, rectangle, term(0))
    assert decide(formula, tuple(context.names)) is expected
