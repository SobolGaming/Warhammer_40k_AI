from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.unit import Unit, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup
from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.collision import CollisionSet
from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceBudget,
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
    MovementEnvelope,
    MovementSegment,
)
from warhammer40k_core.geometry.pathing import (
    PathFailureReason,
    PathQuery,
    PathValidationContext,
    PathWitness,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    "base",
    [
        CircularBase(radius=0.5),
        OvalBase(length=2.0, width=1.0),
        RectangularBase(length=3.0, width=2.0),
    ],
)
def test_rotations_cost_zero_for_every_base_shape(
    base: CircularBase | OvalBase | RectangularBase,
) -> None:
    model = _model("rotating-model", base=base)

    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(
            model.pose,
            Pose.at(2.0, 0.0, facing_degrees=90.0),
            Pose.at(4.0, 0.0, facing_degrees=180.0),
        ),
        max_distance_inches=4.0,
    )

    assert witness.straight_line_distance_inches == 4.0
    assert witness.total_distance_inches == 4.0
    assert len(witness.rotation_events) == 2
    assert witness.rotation_events[0].facing_delta_degrees == 90.0
    assert witness.rotation_events[1].facing_delta_degrees == 90.0
    assert witness.budget is not None
    assert witness.budget.remaining_distance_inches == 0.0


def test_distance_budget_tolerates_floating_point_boundary_noise() -> None:
    budget = MovementDistanceBudget.from_totals(
        max_distance_inches=7.0,
        straight_line_distance_inches=7.000000000000001,
    )

    assert budget.is_within_budget
    assert budget.remaining_distance_inches == 0.0
    assert budget.exceeded_by_inches == 0.0


def test_straight_distance_budget_rejects_path_query_when_exceeded() -> None:
    model = _model("oval-infantry", base=OvalBase(length=2.0, width=1.0))
    witness = PathWitness.for_paths(
        (
            (
                model.model_id,
                (
                    model.pose,
                    Pose.at(2.0, 0.0, facing_degrees=90.0),
                    Pose.at(5.0, 0.0, facing_degrees=90.0),
                ),
            ),
        )
    )

    result = PathQuery(
        unit_group=UnitGroup.single(_unit("movers", model.model_id)),
        spatial_index=SpatialIndex.empty().with_model(model),
        witness=witness,
        movement_envelope=_movement_envelope(max_distance_inches=4.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.MOVEMENT_DISTANCE_EXCEEDED
    assert result.failure.model_id == model.model_id


def test_path_validation_context_rejects_straight_distance_budget_exceeded() -> None:
    model = _model_at("oval-infantry", x=2.0, y=2.0, base=OvalBase(length=2.0, width=1.0))
    witness = PathWitness.for_paths(
        (
            (
                model.model_id,
                (
                    model.pose,
                    Pose.at(4.0, 2.0, facing_degrees=90.0),
                    Pose.at(7.0, 2.0, facing_degrees=90.0),
                ),
            ),
        )
    )

    result = PathValidationContext(
        moving_model=model,
        witness=witness,
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        enemy_engagement_horizontal_inches=_engagement_horizontal_inches(),
        enemy_engagement_vertical_inches=_engagement_vertical_inches(),
        movement_distance_budget_inches=4.0,
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "movement_distance_exceeded"
    assert result.movement_distance_witness is not None
    assert result.movement_distance_witness.total_distance_inches == 5.0


def test_straight_line_segment_uses_same_point_measurement_semantics() -> None:
    segment = MovementSegment.from_poses(
        model_id="mover",
        segment_index=0,
        start_pose=Pose.at(0.0, 0.0, facing_degrees=0.0),
        end_pose=Pose.at(3.0, 4.0, facing_degrees=90.0),
    )

    assert segment.measurement_point == "pose_anchor"
    assert segment.distance_inches == 5.0


def test_movement_distance_witness_round_trips_without_object_reprs() -> None:
    model = _model("oval-infantry", base=OvalBase(length=2.0, width=1.0))
    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(model.pose, Pose.at(2.0, 0.0, facing_degrees=90.0)),
        max_distance_inches=2.0,
    )

    payload = cast(
        MovementDistanceWitnessPayload,
        json.loads(json.dumps(witness.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert MovementDistanceWitness.from_payload(payload).to_payload() == payload


def test_movement_distance_witness_rejects_missing_rotation_event_for_facing_change() -> None:
    payload = _oval_rotation_witness_payload()
    payload["rotation_events"] = []

    with pytest.raises(GeometryError, match="rotation events must match facing-change segments"):
        MovementDistanceWitness.from_payload(payload)


def test_movement_distance_witness_rejects_rotation_delta_drift() -> None:
    payload = _oval_rotation_witness_payload()
    payload["rotation_events"][0]["facing_delta_degrees"] = 45.0

    with pytest.raises(GeometryError, match="facing_delta_degrees drift"):
        MovementDistanceWitness.from_payload(payload)


def test_movement_distance_witness_rejects_rotation_event_pose_drift() -> None:
    payload = _oval_rotation_witness_payload()
    payload["rotation_events"][0]["end_pose"] = Pose.at(
        2.0,
        1.0,
        facing_degrees=90.0,
    ).to_payload()

    with pytest.raises(GeometryError, match="rotation event poses must match segment poses"):
        MovementDistanceWitness.from_payload(payload)


def test_movement_distance_witness_rejects_non_contiguous_segments() -> None:
    model = _model("oval-infantry", base=OvalBase(length=2.0, width=1.0))
    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(
            model.pose,
            Pose.at(2.0, 0.0, facing_degrees=90.0),
            Pose.at(4.0, 0.0, facing_degrees=90.0),
        ),
        max_distance_inches=4.0,
    )
    payload = cast(
        MovementDistanceWitnessPayload,
        json.loads(json.dumps(witness.to_payload(), sort_keys=True)),
    )
    payload["segments"][1]["start_pose"] = Pose.at(
        3.0,
        0.0,
        facing_degrees=90.0,
    ).to_payload()
    payload["segments"][1]["distance_inches"] = 1.0
    _rewrite_budget(payload, straight_line_distance_inches=3.0)

    with pytest.raises(GeometryError, match="segments must form a contiguous path"):
        MovementDistanceWitness.from_payload(payload)


def _model(model_id: str, *, base: CircularBase | OvalBase | RectangularBase) -> Model:
    return _model_at(model_id, x=0.0, y=0.0, base=base)


def _model_at(
    model_id: str,
    *,
    x: float,
    y: float,
    base: CircularBase | OvalBase | RectangularBase,
) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x, y),
        base=base,
        volume=ModelVolume(height=2.0),
    )


def _unit(unit_id: str, *model_ids: str) -> Unit:
    return Unit(
        unit_id=unit_id,
        name=unit_id.title(),
        own_models=tuple(
            UnitMember.ready(model_id=model_id, name=model_id.title()) for model_id in model_ids
        ),
    )


def _movement_envelope(*, max_distance_inches: float) -> MovementEnvelope:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    coherency_policy = descriptor.coherency_policy
    assert coherency_policy.max_horizontal_inches is not None
    assert coherency_policy.max_vertical_inches is not None
    assert coherency_policy.required_neighbors_small_unit is not None
    return MovementEnvelope(
        max_distance_inches=max_distance_inches,
        coherency_horizontal_inches=coherency_policy.max_horizontal_inches,
        coherency_vertical_inches=coherency_policy.max_vertical_inches,
        engagement_horizontal_inches=descriptor.engagement_policy.horizontal_inches,
        engagement_vertical_inches=descriptor.engagement_policy.vertical_inches,
        required_coherency_neighbors=coherency_policy.required_neighbors_small_unit,
    )


def _engagement_horizontal_inches() -> float:
    return RulesetDescriptor.warhammer_40000_eleventh().engagement_policy.horizontal_inches


def _engagement_vertical_inches() -> float:
    return RulesetDescriptor.warhammer_40000_eleventh().engagement_policy.vertical_inches


def _oval_rotation_witness_payload() -> MovementDistanceWitnessPayload:
    model = _model("oval-infantry", base=OvalBase(length=2.0, width=1.0))
    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(model.pose, Pose.at(2.0, 0.0, facing_degrees=90.0)),
        max_distance_inches=2.0,
    )
    return cast(
        MovementDistanceWitnessPayload,
        json.loads(json.dumps(witness.to_payload(), sort_keys=True)),
    )


def _rewrite_budget(
    payload: MovementDistanceWitnessPayload,
    *,
    straight_line_distance_inches: float,
) -> None:
    budget = payload["budget"]
    assert budget is not None
    max_distance_inches = budget["max_distance_inches"]
    budget["straight_line_distance_inches"] = straight_line_distance_inches
    budget["total_distance_inches"] = straight_line_distance_inches
    budget["remaining_distance_inches"] = max(
        max_distance_inches - straight_line_distance_inches,
        0.0,
    )
    budget["exceeded_by_inches"] = max(
        straight_line_distance_inches - max_distance_inches,
        0.0,
    )
