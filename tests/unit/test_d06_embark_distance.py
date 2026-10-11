"""Embark measures actual 3D base/FRAME separation, inclusively."""

# pyright: reportPrivateUsage=false
from dataclasses import replace

import pytest

from warhammer40k_core.engine.transport_embark_validation import _model_within_any_transport_model
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(("distance", "expected"), [(2.999, True), (3.0, True), (3.001, False)])
@pytest.mark.parametrize("translation", [(0.0, 0.0, 0.0), (19.0, -11.0, 7.0)])
@pytest.mark.parametrize("axis", ["horizontal", "vertical"])
def test_embark_actual_base_distance_boundary(
    distance: float, expected: bool, translation: tuple[float, float, float], axis: str
) -> None:
    x, y, z = translation
    carrier = Model("carrier", Pose.at(x, y, z), CircularBase(0.5), ModelVolume(10))
    passenger = Model(
        "passenger",
        Pose.at(x + distance + 1, y, z) if axis == "horizontal" else Pose.at(x, y, z + distance),
        CircularBase(0.5),
        ModelVolume(10),
    )
    assert (
        _model_within_any_transport_model(passenger, transport_models=(carrier,), distance_inches=3)
        is expected
    )


@pytest.mark.parametrize("vertical", [2.399, 2.4, 2.401])
@pytest.mark.parametrize("translation", [(0.0, 0.0, 0.0), (19.0, 11.0, 7.0)])
def test_embark_diagonal_distance_is_not_separate_axis_limits(
    vertical: float, translation: tuple[float, float, float]
) -> None:
    x, y, z = translation
    carrier = Model("carrier", Pose.at(x, y, z), CircularBase(0.5), ModelVolume(10))
    passenger = Model(
        "passenger", Pose.at(x + 2.8, y, z + vertical), CircularBase(0.5), ModelVolume(10)
    )
    assert passenger.base_distance_to(carrier) < 3
    assert _model_within_any_transport_model(
        passenger, transport_models=(carrier,), distance_inches=3
    ) is (vertical <= 2.4)


@pytest.mark.parametrize("axis", ["horizontal", "vertical", "diagonal"])
@pytest.mark.parametrize("translation", [(0.0, 0.0, 0.0), (19.0, 11.0, 7.0)])
def test_embark_comparison_allowance_does_not_admit_distance_beyond_envelope(
    axis: str, translation: tuple[float, float, float]
) -> None:
    x, y, z = translation
    carrier = Model("carrier", Pose.at(x, y, z), CircularBase(0.5), ModelVolume(20))
    outside = 3.0 + 2e-9
    endpoint = (
        Pose.at(x + outside + 1, y, z)
        if axis == "horizontal"
        else Pose.at(x, y, z + outside)
        if axis == "vertical"
        else Pose.at(x + 1 + 0.6 * outside, y, z + 0.8 * outside)
    )
    passenger = Model("passenger", endpoint, CircularBase(0.5), ModelVolume(20))
    assert not _model_within_any_transport_model(
        passenger, transport_models=(carrier,), distance_inches=3
    )


@pytest.mark.parametrize("frame_role", ["passenger", "carrier"])
def test_embark_frame_closest_part_preserves_ordinary_base_plane(frame_role: str) -> None:
    part = ModelBodyPart(
        part_id="arm",
        base=CircularBase(0.5),
        offset_x_inches=2,
        offset_y_inches=0,
        bottom_inches=0,
        height_inches=1,
        evidence_id="d06:analytical-arm",
    )
    frame = Model(
        "frame",
        Pose.at(0, 0),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(part,),
        measures_every_part=True,
    )
    ordinary = Model("ordinary", Pose.at(5, 0), CircularBase(0.5), ModelVolume(20))
    passenger, carrier = (frame, ordinary) if frame_role == "passenger" else (ordinary, frame)
    assert passenger.base_distance_to(carrier) == 4
    assert _model_within_any_transport_model(
        passenger, transport_models=(carrier,), distance_inches=3
    )
    assert not _model_within_any_transport_model(
        replace(passenger, measures_every_part=False),
        transport_models=(replace(carrier, measures_every_part=False),),
        distance_inches=3,
    )
    # The ordinary model's tall body is not an alternative measurement subject.
    elevated = replace(ordinary, pose=Pose.at(5, 0, 5))
    passenger, carrier = (frame, elevated) if frame_role == "passenger" else (elevated, frame)
    assert not _model_within_any_transport_model(
        passenger, transport_models=(carrier,), distance_inches=3
    )


def test_embark_any_carrier_model_can_be_closest() -> None:
    passenger = Model("passenger", Pose.at(0, 0, 5), CircularBase(0.5), ModelVolume(1))
    far = Model("far", Pose.at(0, 0), CircularBase(0.5), ModelVolume(10))
    near = Model("near", Pose.at(3, 0, 5), CircularBase(0.5), ModelVolume(1))
    assert not _model_within_any_transport_model(
        passenger, transport_models=(far,), distance_inches=3
    )
    assert _model_within_any_transport_model(
        passenger, transport_models=(far, near), distance_inches=3
    )
