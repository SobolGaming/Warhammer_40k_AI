# pyright: reportPrivateUsage=false
"""Order 100: based FRAME models are measured from every part."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from tests.charge_distance_helpers import add_modifier, request_from, select_targets
from tests.order85_overhang_helpers import overhang_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    ModelDisplacementKind,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.transport_disembark_geometry import (
    _model_wholly_within_any_transport_model,
)
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.base_contact_proof import endpoint_excluded_by_bodies
from warhammer40k_core.geometry.measurement import (
    OBJECTIVE_MARKER_DIAMETER_INCHES,
    DistanceMeasurementContext,
    objective_marker_controls_model,
)
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain_area_visibility import (
    TerrainVisibilityArea,
    model_intersects_terrain_area,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _session(*, frame: bool) -> LocalGameSession:
    return overhang_session(start_y=8, enemy_keywords=("FRAME",) if frame else ())


def _pair(session: LocalGameSession) -> tuple[Model, Model]:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    battlefield = state.battlefield_state
    return (
        geometry_model_for_placement(
            model=source.own_models[0],
            placement=battlefield.unit_placement_by_id(source.unit_instance_id).model_placements[0],
        ),
        geometry_model_for_placement(
            model=target.own_models[0],
            placement=battlefield.unit_placement_by_id(target.unit_instance_id).model_placements[0],
        ),
    )


def _terrain_strip() -> TerrainVisibilityArea:
    return TerrainVisibilityArea(
        "frame-area",
        ("frame-area",),
        TerrainAreaClassification.LIGHT,
        (((9.5, 10.25), (10.5, 10.25), (10.5, 10.75), (9.5, 10.75)),),
    )


def test_based_frame_wholly_within_includes_every_part() -> None:
    source, frame = _pair(_session(frame=True))
    _source, support_only = _pair(_session(frame=False))
    context = DistanceMeasurementContext.from_models(source, frame)
    support_context = DistanceMeasurementContext.from_models(source, support_only)

    assert frame.measures_every_part is True
    assert support_only.measures_every_part is False
    assert frame.body_parts[0].base.max_radius() > frame.base.max_radius()
    assert context.target_wholly_within_distance(8.5) is False
    assert support_context.target_wholly_within_distance(8.5) is True
    assert context.target_wholly_within_distance(12) is True
    assert (
        _model_wholly_within_any_transport_model(
            frame, transport_models=(source,), distance_inches=8.5
        )
        is False
    )


def test_based_frame_engagement_and_movement_use_the_body() -> None:
    session = _session(frame=True)
    state = session.lifecycle.state
    assert state is not None
    source, frame = _pair(session)
    plain = _session(frame=False)
    plain_state = plain.lifecycle.state
    assert plain_state is not None
    plain_source, support_only = _pair(plain)
    goal = MovementGoal(models=(source,), horizontal_inches=2.0, vertical_inches=5.0)

    assert source.base_distance_to(frame) > 2
    assert frame.rules_horizontal_distance_to(source) <= 2
    assert plain_source.range_to(support_only) == plain_source.base_distance_to(support_only)
    assert (
        unit_within_enemy_engagement_range(
            state=state, unit_instance_id=state.army_definitions[0].units[0].unit_instance_id
        )
        is True
    )
    assert (
        unit_within_enemy_engagement_range(
            state=plain_state,
            unit_instance_id=plain_state.army_definitions[0].units[0].unit_instance_id,
        )
        is False
    )
    assert goal.contains(frame) is True
    assert goal.contains(support_only) is False


def test_based_frame_terrain_and_objective_membership_use_the_body() -> None:
    _source, frame = _pair(_session(frame=True))
    area = _terrain_strip()
    support_only = replace(frame, measures_every_part=False)
    elevated = replace(frame, pose=Pose.at(frame.pose.position.x, frame.pose.position.y, 10))
    marker_radius = OBJECTIVE_MARKER_DIAMETER_INCHES / 2
    center_distance = frame.base.max_radius() + marker_radius + 3.2
    marker = Pose.at(frame.pose.position.x, frame.pose.position.y - center_distance)

    assert model_intersects_terrain_area(frame, area) is True
    assert model_intersects_terrain_area(support_only, area) is False
    assert model_intersects_terrain_area(elevated, area) is True
    assert objective_marker_controls_model(marker, frame) is True
    assert objective_marker_controls_model(marker, support_only) is False


def test_based_frame_engagement_restores_for_both_viewers_and_replays() -> None:
    session = _session(frame=True)
    state = session.lifecycle.state
    assert state is not None
    source_id = state.army_definitions[0].units[0].unit_instance_id
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    restored_state = restored.lifecycle.state
    assert restored_state is not None

    assert unit_within_enemy_engagement_range(state=state, unit_instance_id=source_id) is True
    assert (
        unit_within_enemy_engagement_range(state=restored_state, unit_instance_id=source_id) is True
    )
    assert restored.to_persistence_payload() == checkpoint
    assert restored.view(viewer_player_id="player-a") == session.view(viewer_player_id="player-a")
    assert restored.view(viewer_player_id="player-b") == session.view(viewer_player_id="player-b")
    assert restored.events_since(
        EventStreamCursor(), viewer_player_id="player-a"
    ) == session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order100")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def test_cooperating_frame_parts_leave_an_uncovered_interior_height() -> None:
    source = Model(
        "source",
        Pose.at(10, 10),
        CircularBase(1),
        ModelVolume(9),
        body_parts=(
            ModelBodyPart("lower", CircularBase(3), 3, 0, 0, 1, "lower"),
            ModelBodyPart("upper", CircularBase(3), 3, 0, 8, 1, "upper"),
        ),
        measures_every_part=True,
    )
    target = Model(
        "target",
        Pose.at(16.5, 10),
        CircularBase(0.25),
        ModelVolume(9),
        body_parts=(ModelBodyPart("body", CircularBase(0.25), 0, 0, 0, 9, "body"),),
        measures_every_part=True,
    )
    context = DistanceMeasurementContext.from_models(source, target)

    assert context.target_wholly_within_distance(1) is False


def test_frame_source_preserves_ordinary_target_support_base_containment() -> None:
    target = Model("target", Pose.at(12.5, 10), CircularBase(0.5), ModelVolume(10))
    ordinary = Model("source", Pose.at(10, 10), CircularBase(1), ModelVolume(1))
    framed = Model(
        "source",
        Pose.at(10, 10),
        CircularBase(1),
        ModelVolume(1),
        body_parts=(ModelBodyPart("body", CircularBase(1), 0, 0, 0, 1, "body"),),
        measures_every_part=True,
    )
    ordinary_context = DistanceMeasurementContext.from_models(ordinary, target)
    framed_context = DistanceMeasurementContext.from_models(framed, target)

    assert ordinary_context.target_wholly_within_distance(3) is True
    assert framed_context.target_wholly_within_distance(3) is True
    assert ordinary_context.target_wholly_within_distance(3, horizontal_only=True) is True
    assert framed_context.target_wholly_within_distance(3, horizontal_only=True) is True


def test_frame_wholly_within_rejects_a_tall_body_inside_the_horizontal_buffer() -> None:
    source = Model("source", Pose.at(10, 10), CircularBase(1), ModelVolume(1))
    frame = Model(
        "frame",
        Pose.at(12.5, 10),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(ModelBodyPart("body", CircularBase(1), 0, 0, 0, 10, "fixture:body"),),
        measures_every_part=True,
    )
    context = DistanceMeasurementContext.from_models(source, frame)
    ordinary = DistanceMeasurementContext.from_models(
        source, replace(frame, measures_every_part=False)
    )

    assert context.target_wholly_within_distance(3, horizontal_only=True) is True
    assert context.target_wholly_within_distance(3) is False
    assert ordinary.target_wholly_within_distance(3) is True


def test_offset_frame_rotation_is_reachable_within_the_translation_budget() -> None:
    moving = Model(
        "mover",
        Pose.at(10, 10),
        CircularBase(60 / 25.4),
        ModelVolume(2),
        body_parts=(ModelBodyPart("arm", CircularBase(0.5), 4, 0, 0, 2, "fixture:arm"),),
        measures_every_part=True,
    )
    target = Model("target", Pose.at(4.5, 10), CircularBase(0.5), ModelVolume(2))
    goal = MovementGoal(models=(target,), range_inches=1)
    witness = PathWitness.for_paths(((moving.model_id, (moving.pose, moving.pose)),))
    legality = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.CONSOLIDATE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )
    query = MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=moving,
            witness=witness,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            friendly_models=(),
            enemy_models=(target,),
            terrain=(),
            movement_distance_budget_inches=1,
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=moving, witness=witness, terrain=(), terrain_features=()
        ),
        goal=goal,
    )

    assert goal.distance_lower_bound(moving) <= 1
    result = movement_reachability(query)
    assert result.status is MovementReachabilityStatus.REACHABLE
    assert result.witness is not None
    final = result.witness.final_pose_for_model(moving.model_id)
    assert (final.position.x, final.position.y) == (10, 10)
    assert final.facing.degrees != moving.pose.facing.degrees
    assert replace(query.path_context, witness=result.witness).validate().is_valid


def test_frame_body_goal_is_not_certified_unreachable_by_support_base_proximity() -> None:
    mover = Model("mover", Pose.at(10, 10), CircularBase(0.5), ModelVolume(2))
    frame = Model(
        "frame",
        Pose.at(18, 10),
        CircularBase(60 / 25.4),
        ModelVolume(2),
        body_parts=(ModelBodyPart("body", CircularBase(4), 0, 0, 0, 2, "fixture:body"),),
        measures_every_part=True,
    )

    assert (
        endpoint_excluded_by_bodies(
            source=mover,
            targets=(frame,),
            range_inches=0.5,
            budget=4,
            supported_elevations=(0.0,),
        )
        is False
    )
    assert (
        endpoint_excluded_by_bodies(
            source=mover,
            targets=(replace(frame, measures_every_part=False),),
            range_inches=0.5,
            budget=4,
            supported_elevations=(0.0,),
        )
        is True
    )


def _body_but_not_base_engagement_end(source: Model, target: Model) -> Pose:
    center_gap = 0.5 + source.base.max_radius() + target.body_parts[0].base.max_radius()
    return Pose.at(source.pose.position.x, target.pose.position.y - center_gap)


def test_frame_charge_uses_body_engagement_and_replays_for_both_viewers() -> None:
    accepted, accepted_status = _submit_split_engagement_charge(frame=True)
    _rejected, rejected_status = _submit_split_engagement_charge(frame=False)
    checkpoint = json.loads(json.dumps(accepted.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)

    assert accepted_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert rejected_status.status_kind is LifecycleStatusKind.INVALID
    assert restored.to_persistence_payload() == checkpoint
    assert restored.view(viewer_player_id="player-a") == accepted.view(viewer_player_id="player-a")
    assert restored.view(viewer_player_id="player-b") == accepted.view(viewer_player_id="player-b")
    assert restored.events_since(
        EventStreamCursor(), viewer_player_id="player-a"
    ) == accepted.events_since(EventStreamCursor(), viewer_player_id="player-a")
    replay = ReplayRunner.from_payload(
        accepted.replay_artifact(artifact_id="order100-charge")
    ).run()
    assert replay.status is ReplayRunStatus.REPRODUCED


def _submit_split_engagement_charge(*, frame: bool) -> tuple[LocalGameSession, LifecycleStatus]:
    from warhammer40k_core.engine.movement_proposals import ProposalKind
    from warhammer40k_core.engine.phases.charge import ChargeMoveProposal

    session = overhang_session(start_y=6, enemy_keywords=("FRAME",) if frame else ())
    state = session.lifecycle.state
    assert state is not None
    add_modifier(state, effect_id="order100-charge-distance", kind="modify_dice_roll", delta=10)
    request = request_from(session.advance_until_decision_or_terminal())
    request = request_from(
        session.submit_option(
            request_id=request.request_id,
            option_id="army-alpha:source",
            result_id="order100-select-source",
        )
    )
    request = select_targets(session, request, ("army-beta:enemy",), result_id="order100-targets")
    source, target = _pair(session)
    end = _body_but_not_base_engagement_end(source, target)
    arrived = replace(source, pose=end)
    assert arrived.base_distance_to(target) > 2
    if frame:
        assert arrived.rules_horizontal_distance_to(target) <= 2
    proposal = ChargeMoveProposal(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        unit_instance_id="army-alpha:source",
        movement_phase_action="charge_move",
        movement_mode=MovementMode.CHARGE,
        charge_target_unit_instance_ids=("army-beta:enemy",),
        witness=PathWitness.for_paths(((source.model_id, (source.pose, end)),)),
    )
    status = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order100-charge",
        payload=cast(JsonValue, proposal.to_payload()),
    )
    return session, status
