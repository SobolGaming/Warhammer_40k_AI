"""Explicit geometry contracts: inches, closest support base and whole-model bounds."""

from dataclasses import replace
from math import isclose

import pytest

from warhammer40k_core.engine.table_quarters import scoring_table_quarter_id_or_none
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.measurement import (
    DistanceMeasurementContext,
    DistancePredicateEvaluator,
    WhollyWithinPredicate,
    WithinPredicate,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("gap", [0, 0.999, 1, 1.001, 2])
def test_01_04_closest_base_inches_and_inclusive_within(gap: float) -> None:
    a = Model("source", Pose.at(5, 5), CircularBase(0.5), ModelVolume(1))
    b = Model("target", Pose.at(6 + gap, 5), CircularBase(0.5), ModelVolume(8))
    context = DistanceMeasurementContext.from_models(a, b)
    assert isclose(context.closest_distance_inches(), gap, abs_tol=1e-9)
    evaluator = DistancePredicateEvaluator(context)
    assert evaluator.evaluate(WithinPredicate(1)) is (gap <= 1)
    assert evaluator.evaluate(WhollyWithinPredicate(2)) is (gap + 1 <= 2)
    assert a.base_distance_to(b) == b.base_distance_to(a)


@pytest.mark.parametrize("frame", [False, True])
@pytest.mark.parametrize("height", [1, 4])
def test_01_04_01_frame_whole_height_and_ordinary_base(frame: bool, height: float) -> None:
    source = Model("source", Pose.at(5, 5), CircularBase(0.5), ModelVolume(1))
    target = Model(
        "target",
        Pose.at(6, 5),
        CircularBase(0.5),
        ModelVolume(height),
        measures_every_part=frame,
    )
    context = DistanceMeasurementContext.from_models(source, target)
    assert context.target_wholly_within_distance(2) is (not frame or height == 1)


@pytest.mark.parametrize("xsign", [-1, 1])
@pytest.mark.parametrize("ysign", [-1, 1])
@pytest.mark.parametrize("gap", [0.019, 0.020])
def test_01_04_05_quarter_rectangles_exclude_half_mm_strip(
    xsign: int, ysign: int, gap: float
) -> None:
    model = Model(
        "quarter",
        Pose.at(30 + xsign * (0.5 + gap), 22 + ysign * 10),
        CircularBase(0.5),
        ModelVolume(1),
    )
    expected = (
        f"table-quarter:{'south' if ysign < 0 else 'north'}-{'west' if xsign < 0 else 'east'}"
        if gap > 0.5 / 25.4
        else None
    )
    assert (
        scoring_table_quarter_id_or_none(geometry_models=(model,), center_x=30, center_y=22)
        == expected
    )
    partner = replace(model, model_id="partner", pose=Pose.at(30 - xsign * 3, 22 + ysign * 10))
    assert (
        scoring_table_quarter_id_or_none(geometry_models=(model, partner), center_x=30, center_y=22)
        is None
    )
