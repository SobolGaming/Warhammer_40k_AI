from __future__ import annotations

import json
from typing import cast

from warhammer40k_core.core.unit import Unit, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup
from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.collision import CollisionSet
from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
    MovementEnvelope,
    MovementSegment,
    PivotCostPolicy,
)
from warhammer40k_core.geometry.pathing import PathFailureReason, PathQuery, PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_circular_base_without_facing_change_has_zero_pivot_cost() -> None:
    model = _model("round-infantry", base=CircularBase(radius=0.5))
    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(model.pose, Pose.at(2.0, 0.0), Pose.at(4.0, 0.0)),
        pivot_cost_policy=PivotCostPolicy(),
        max_distance_inches=4.0,
    )

    assert witness.pivot_cost_inches == 0.0
    assert witness.total_distance_inches == 4.0
    assert witness.budget is not None
    assert witness.budget.remaining_distance_inches == 0.0


def test_non_round_infantry_base_pays_one_inch_once_for_multiple_pivots() -> None:
    model = _model("oval-infantry", base=OvalBase(length=2.0, width=1.0))

    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(
            model.pose,
            Pose.at(2.0, 0.0, facing_degrees=90.0),
            Pose.at(4.0, 0.0, facing_degrees=180.0),
        ),
        pivot_cost_policy=PivotCostPolicy(),
        max_distance_inches=5.0,
    )

    assert witness.straight_line_distance_inches == 4.0
    assert witness.pivot_cost_inches == 1.0
    assert witness.total_distance_inches == 5.0
    assert len(witness.pivot_events) == 2
    assert witness.pivot_events[0].pivot_value_inches == 1.0
    assert witness.pivot_events[0].applied_cost_inches == 1.0
    assert witness.pivot_events[0].first_pivot_for_model
    assert witness.pivot_events[1].pivot_value_inches == 1.0
    assert witness.pivot_events[1].applied_cost_inches == 0.0
    assert not witness.pivot_events[1].first_pivot_for_model


def test_non_round_vehicle_or_monster_pays_two_inches() -> None:
    vehicle = _model("vehicle", base=RectangularBase(length=3.0, width=2.0))
    monster = _model("monster", base=OvalBase(length=3.0, width=2.0))
    policy = PivotCostPolicy(vehicle_or_monster_model_ids=("vehicle", "monster"))

    for model in (vehicle, monster):
        witness = MovementDistanceWitness.for_model_path(
            model=model,
            poses=(model.pose, Pose.at(1.0, 0.0, facing_degrees=90.0)),
            pivot_cost_policy=policy,
        )

        assert witness.pivot_cost_inches == 2.0
        assert witness.pivot_events[0].pivot_value_inches == 2.0


def test_round_base_large_flying_stem_or_hover_vehicle_pays_two_inches() -> None:
    large_round_vehicle = _model("large-round-vehicle", base=_circular_mm(40.0))
    normal_round_vehicle = _model("normal-round-vehicle", base=_circular_mm(32.0))
    policy = PivotCostPolicy(
        round_base_flying_stem_or_hover_stand_vehicle_model_ids=(
            "large-round-vehicle",
            "normal-round-vehicle",
        )
    )

    large_witness = MovementDistanceWitness.for_model_path(
        model=large_round_vehicle,
        poses=(large_round_vehicle.pose, Pose.at(1.0, 0.0, facing_degrees=90.0)),
        pivot_cost_policy=policy,
    )
    normal_witness = MovementDistanceWitness.for_model_path(
        model=normal_round_vehicle,
        poses=(normal_round_vehicle.pose, Pose.at(1.0, 0.0, facing_degrees=90.0)),
        pivot_cost_policy=policy,
    )

    assert large_witness.pivot_cost_inches == 2.0
    assert normal_witness.pivot_cost_inches == 0.0


def test_aircraft_pays_zero_in_generic_pivot_policy() -> None:
    model = _model("aircraft", base=OvalBase(length=4.0, width=2.0))
    policy = PivotCostPolicy(
        aircraft_model_ids=("aircraft",),
        vehicle_or_monster_model_ids=("aircraft",),
    )

    witness = MovementDistanceWitness.for_model_path(
        model=model,
        poses=(model.pose, Pose.at(1.0, 0.0, facing_degrees=90.0)),
        pivot_cost_policy=policy,
    )

    assert witness.pivot_cost_inches == 0.0
    assert witness.pivot_events[0].pivot_value_inches == 0.0


def test_insufficient_budget_after_pivot_cost_rejects_path_query() -> None:
    model = _model("oval-infantry", base=OvalBase(length=2.0, width=1.0))
    witness = PathWitness.for_paths(
        (
            (
                model.model_id,
                (
                    model.pose,
                    Pose.at(2.0, 0.0, facing_degrees=90.0),
                    Pose.at(4.0, 0.0, facing_degrees=90.0),
                ),
            ),
        )
    )

    result = PathQuery(
        unit_group=UnitGroup.single(_unit("movers", model.model_id)),
        spatial_index=SpatialIndex.empty().with_model(model),
        witness=witness,
        movement_envelope=MovementEnvelope(max_distance_inches=4.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.MOVEMENT_DISTANCE_EXCEEDED
    assert result.failure.model_id == model.model_id


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
        pivot_cost_policy=PivotCostPolicy(),
        max_distance_inches=3.0,
    )

    payload = cast(
        MovementDistanceWitnessPayload,
        json.loads(json.dumps(witness.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert MovementDistanceWitness.from_payload(payload).to_payload() == payload


def _model(model_id: str, *, base: CircularBase | OvalBase | RectangularBase) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(0.0, 0.0),
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


def _circular_mm(diameter_mm: float) -> CircularBase:
    return CircularBase(radius=(diameter_mm / 25.4) / 2.0)
