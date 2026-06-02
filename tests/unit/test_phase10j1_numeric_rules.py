from __future__ import annotations

import json
import math
from typing import cast

import pytest

from warhammer40k_core.core.attributes import (
    BoundedCharacteristicValue,
    BoundedCharacteristicValuePayload,
    Characteristic,
    CharacteristicBoundPolicy,
)
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierOperation,
    ModifierScope,
    ModifierStack,
    ModifierTiming,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.measurement import (
    OBJECTIVE_MARKER_DIAMETER_INCHES,
    DistanceComparison,
    DistanceMeasurementContext,
    DistanceMeasurementContextPayload,
    DistancePredicateEvaluator,
    DistancePredicatePayload,
    HorizontalDistancePredicate,
    WhollyWithinPredicate,
    WithinPredicate,
    distance_predicate_from_payload,
    objective_marker_controls_model,
    objective_marker_endpoint_is_clear,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _model(
    model_id: str,
    x: float,
    y: float,
    z: float = 0.0,
    *,
    radius: float = 0.5,
    height: float = 2.0,
) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=radius),
        volume=ModelVolume(height=height),
    )


def _add_modifier(characteristic: Characteristic, operand: int) -> Modifier:
    return Modifier(
        modifier_id=f"{characteristic.value}-phase10j1-bound",
        scope=ModifierScope.for_characteristics((characteristic,)),
        timing=ModifierTiming.ADDITIVE,
        operation=ModifierOperation.ADD,
        operand=operand,
    )


def test_closest_base_distance_and_baseless_frame_measurement_work() -> None:
    source = _model("source", 0.0, 0.0)
    target = _model("target", 2.0, 0.0)
    based = DistanceMeasurementContext.from_models(source, target)
    baseless = DistanceMeasurementContext.from_baseless_source_to_model(
        source_id="hull-source",
        source_pose=Pose.at(0.0, 0.0),
        source_contact_radius_inches=0.25,
        source_height_inches=2.0,
        target=target,
    )
    frame = DistanceMeasurementContext.from_baseless_source_to_model(
        source_id="frame-source",
        source_pose=Pose.at(0.0, 0.0),
        source_contact_radius_inches=1.0,
        source_height_inches=2.0,
        target=_model("frame-target", 3.0, 0.0),
    )

    assert math.isclose(based.horizontal_distance_inches(), 1.0)
    assert math.isclose(based.closest_distance_inches(), 1.0)
    assert math.isclose(baseless.horizontal_distance_inches(), 1.25)
    assert math.isclose(frame.horizontal_distance_inches(), 1.5)
    assert math.isclose(frame.closest_distance_inches(), 1.5)


def test_distance_predicates_evaluate_within_wholly_more_than_and_horizontal_only() -> None:
    context = DistanceMeasurementContext.from_models(
        _model("source", 0.0, 0.0, radius=1.0),
        _model("target", 2.0, 0.0, radius=0.5),
    )
    evaluator = DistancePredicateEvaluator(context)

    assert evaluator.evaluate(WithinPredicate(0.5))
    assert evaluator.more_than(0.25)
    assert evaluator.evaluate(WhollyWithinPredicate(1.6))
    assert not evaluator.evaluate(WhollyWithinPredicate(1.4))

    elevated = DistancePredicateEvaluator(
        DistanceMeasurementContext.from_models(
            _model("low", 0.0, 0.0),
            _model("high", 0.0, 0.0, z=8.0),
        )
    )
    assert not elevated.evaluate(WithinPredicate(1.0))
    assert elevated.evaluate(HorizontalDistancePredicate(1.0, comparison=DistanceComparison.WITHIN))


def test_objective_marker_range_and_endpoint_overlap_use_core_dimensions() -> None:
    marker_pose = Pose.at(0.0, 0.0)
    marker_radius = OBJECTIVE_MARKER_DIAMETER_INCHES / 2.0
    controlled = _model("controlled", marker_radius + 0.5 + 2.95, 0.0)
    too_far = _model("too-far", marker_radius + 0.5 + 3.05, 0.0)
    vertically_inside = _model("vertically-inside", 0.0, 0.0, z=5.0)
    vertically_outside = _model("vertically-outside", 0.0, 0.0, z=5.1)
    overlapping_endpoint = _model("overlap", marker_radius + 0.5 - 0.1, 0.0)
    clear_endpoint = _model("clear", marker_radius + 0.5 + 0.1, 0.0)

    assert objective_marker_controls_model(marker_pose, controlled)
    assert not objective_marker_controls_model(marker_pose, too_far)
    assert objective_marker_controls_model(marker_pose, vertically_inside)
    assert not objective_marker_controls_model(marker_pose, vertically_outside)
    assert not objective_marker_endpoint_is_clear(marker_pose, overlapping_endpoint)
    assert objective_marker_endpoint_is_clear(marker_pose, clear_endpoint)


def test_elevated_model_can_control_objective_without_ending_on_marker() -> None:
    marker_pose = Pose.at(0.0, 0.0)
    elevated = _model("elevated", 0.0, 0.0, z=5.0)

    assert objective_marker_controls_model(marker_pose, elevated)
    assert objective_marker_endpoint_is_clear(marker_pose, elevated)


def test_same_level_model_cannot_end_on_objective_marker() -> None:
    marker_pose = Pose.at(0.0, 0.0)
    overlapping = _model("overlap", 0.0, 0.0, z=0.0)

    assert not objective_marker_endpoint_is_clear(marker_pose, overlapping)


@pytest.mark.parametrize(
    ("characteristic", "raw", "operand", "expected"),
    [
        (Characteristic.MOVEMENT, 2, -5, 1),
        (Characteristic.TOUGHNESS, 2, -5, 1),
        (Characteristic.SAVE, 2, -1, 2),
        (Characteristic.LEADERSHIP, 6, -5, 4),
        (Characteristic.LEADERSHIP, 6, 5, 9),
        (Characteristic.OBJECTIVE_CONTROL, 1, -5, 0),
        (Characteristic.RANGE, 12, -20, 1),
        (Characteristic.ATTACKS, 2, -5, 1),
        (Characteristic.WEAPON_SKILL, 3, -5, 2),
        (Characteristic.BALLISTIC_SKILL, 3, -5, 2),
        (Characteristic.STRENGTH, 4, -10, 1),
        (Characteristic.ARMOR_PENETRATION, -1, 5, 0),
        (Characteristic.DAMAGE, 2, -5, 1),
    ],
)
def test_characteristic_cap_floor_is_enforced_after_modifiers(
    characteristic: Characteristic,
    raw: int,
    operand: int,
    expected: int,
) -> None:
    stack = ModifierStack(
        characteristic=characteristic,
        raw_value=raw,
        modifiers=(_add_modifier(characteristic, operand),),
    )
    bounded = stack.resolve_bounded()

    assert bounded.unbounded_final == raw + operand
    assert bounded.final == expected
    assert stack.resolve().final == expected


def test_damage_can_be_zero_only_when_bound_policy_explicitly_permits_it() -> None:
    stack = ModifierStack(
        characteristic=Characteristic.DAMAGE,
        raw_value=2,
        modifiers=(_add_modifier(Characteristic.DAMAGE, -5),),
    )
    default_value = stack.resolve_bounded()
    zero_permitted = stack.resolve_bounded(
        bound_policy=CharacteristicBoundPolicy.for_characteristic(
            Characteristic.DAMAGE,
            damage_zero_permitted=True,
        )
    )

    assert default_value.final == 1
    assert zero_permitted.final == 0


def test_phase10j1_payloads_round_trip_without_object_reprs() -> None:
    context = DistanceMeasurementContext.from_models(
        _model("source", 0.0, 0.0),
        _model("target", 2.0, 0.0),
    )
    predicate = HorizontalDistancePredicate(3.0, comparison=DistanceComparison.AT_MOST)
    bounded = BoundedCharacteristicValue.from_values(
        characteristic=Characteristic.MOVEMENT,
        raw=6,
        base=6,
        unbounded_final=-1,
        applied_modifier_ids=("slow-aura",),
    )

    context_payload = cast(
        DistanceMeasurementContextPayload,
        json.loads(json.dumps(context.to_payload(), sort_keys=True)),
    )
    predicate_payload = cast(
        DistancePredicatePayload,
        json.loads(json.dumps(predicate.to_payload(), sort_keys=True)),
    )
    bounded_payload = cast(
        BoundedCharacteristicValuePayload,
        json.loads(json.dumps(bounded.to_payload(), sort_keys=True)),
    )

    for payload in (context_payload, predicate_payload, bounded_payload):
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob

    assert (
        DistanceMeasurementContext.from_payload(context_payload).to_payload()
        == context.to_payload()
    )
    assert distance_predicate_from_payload(predicate_payload).to_payload() == predicate.to_payload()
    assert (
        BoundedCharacteristicValue.from_payload(bounded_payload).to_payload()
        == bounded.to_payload()
    )
