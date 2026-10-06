from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.setup_fit import model_fits_regions, model_wholly_within_regions
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("body", [CircularBase(4), OvalBase(12, 4), RectangularBase(12, 4)])
def test_whole_model_fit_searches_all_rotations_and_preserves_offset(body: object) -> None:
    assert isinstance(body, CircularBase | OvalBase | RectangularBase)
    model = Model(
        "large",
        Pose.at(0, 0),
        CircularBase(1),
        ModelVolume(1),
        (ModelBodyPart("wing", body, 2, 0, 1, 1, "measured:wing"),),
    )
    narrow = ((((0.0, 0.0), (8.0, 0.0), (8.0, 16.0), (0.0, 16.0)),), (), ())
    assert model_fits_regions(model, (narrow,))
    tiny = ((((0.0, 0.0), (3.0, 0.0), (3.0, 16.0), (0.0, 16.0)),), (), ())
    assert not model_fits_regions(model, (tiny,))
    assert model_fits_regions(replace(model, body_parts=()), (tiny,))


def test_compound_parts_require_one_common_pose_not_independent_fits() -> None:
    model = Model(
        "large",
        Pose.at(0, 0),
        CircularBase(1),
        ModelVolume(1),
        tuple(ModelBodyPart(str(x), CircularBase(2), x, 0, 1, 1, "measured") for x in (-8, 8)),
    )
    square = ((((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),), (), ())
    assert not model_fits_regions(model, (square,))


@pytest.mark.parametrize(
    ("base_radius", "body_radius", "fits"), [(1, 2, True), (1, 4, False), (4, 2, False)]
)
def test_concentric_cutout_fit_preserves_largest_base_or_body(
    base_radius: float, body_radius: float, fits: bool
) -> None:
    model = Model(
        "cutout",
        Pose.at(11, 25),
        CircularBase(base_radius),
        ModelVolume(1),
        (ModelBodyPart("body", CircularBase(body_radius), 0, 0, 0, 1, "synthetic:cutout"),),
    )
    region = (
        (((0.0, 18.0), (14.0, 18.0), (14.0, 32.0), (0.0, 32.0)),),
        (((6.0, 18.0), (8.0, 18.0), (8.0, 32.0), (6.0, 32.0)),),
        (),
    )
    assert model_fits_regions(model, (region,)) is fits


@pytest.mark.parametrize(
    ("x", "y", "radius", "inside"),
    [(3, 5, 1, True), (3.1, 5, 1, False), (3, 3, 1, True), (3, 3, 1.5, False), (5, 5, 1, False)],
)
def test_circular_body_polygon_cutout_edge_corner_and_interior(
    x: float, y: float, radius: float, inside: bool
) -> None:
    model = Model(
        "cutout",
        Pose.at(x, y),
        CircularBase(0.25),
        ModelVolume(1),
        (ModelBodyPart("body", CircularBase(radius), 0, 0, 0, 1, "synthetic:cutout"),),
    )
    region = (
        (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),),
        (((4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)),),
        (),
    )
    assert model_wholly_within_regions(model, (region,)) is inside


@pytest.mark.parametrize(
    ("x", "y", "inside"), [(5.5, 5.5, True), (5.25, 5.25, False), (4.5, 4.5, False)]
)
def test_circular_body_concave_cutout_preserves_decomposition_seams(
    x: float, y: float, inside: bool
) -> None:
    model = Model(
        "concave",
        Pose.at(x, y),
        CircularBase(0.25),
        ModelVolume(1),
        (ModelBodyPart("body", CircularBase(0.5), 0, 0, 0, 1, "synthetic:cutout"),),
    )
    region = (
        (((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)),),
        (((4.0, 4.0), (6.0, 4.0), (6.0, 5.0), (5.0, 5.0), (5.0, 6.0), (4.0, 6.0)),),
        (),
    )
    assert model_wholly_within_regions(model, (region,)) is inside


def test_original_avoidable_overhang_probe_rejects_and_ordinary_fit_survives() -> None:
    from tests.order97_gap_probes_01_08 import avoidable_setup_body_overhang_observation

    assert avoidable_setup_body_overhang_observation()["observed"]
    assert avoidable_setup_body_overhang_observation(y=10)["observed"] == []


@pytest.mark.parametrize("heading", [90, 270])
@pytest.mark.parametrize("body", [OvalBase(12, 4), RectangularBase(12, 4)])
def test_cardinal_boundary_contact_is_wholly_contained(heading: float, body: object) -> None:
    assert isinstance(body, OvalBase | RectangularBase)
    model = Model(
        "large",
        Pose.at(2, 6, facing_degrees=heading),
        CircularBase(1),
        ModelVolume(1),
        (ModelBodyPart("body", body, 0, 0, 1, 1, "synthetic:analytic"),),
    )
    region = ((((0.0, 0.0), (4.0, 0.0), (4.0, 12.0), (0.0, 12.0)),), (), ())
    assert model_wholly_within_regions(model, (region,))


def test_impossible_zone_fit_does_not_excuse_avoidable_battlefield_overhang() -> None:
    from warhammer40k_core.core.deployment_zones import DeploymentZone
    from warhammer40k_core.engine.large_model_setup import deployment_body_containment

    model = Model(
        "large",
        Pose.at(3, 20),
        CircularBase(1),
        ModelVolume(1),
        (ModelBodyPart("wing", CircularBase(4), -4, 0, 1, 1, "synthetic:analytic"),),
    )
    zones = (DeploymentZone.rectangle("zone", "player-a", min_x=0, min_y=0, max_x=6, max_y=44),)
    assert deployment_body_containment(
        model=model, zones=zones, width=60, depth=44, unrestricted_zone=False
    ) == (True, False)
    assert deployment_body_containment(
        model=replace(model, pose=Pose.at(3, 20, facing_degrees=180)),
        zones=zones,
        width=60,
        depth=44,
        unrestricted_zone=False,
    ) == (True, True)
