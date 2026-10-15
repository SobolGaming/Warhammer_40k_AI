"""Negative certificates include continuous height and every passenger."""

from dataclasses import replace

import pytest

from warhammer40k_core.geometry.base import CircularBase, OvalBase
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.tactical_setup_proof import (
    TacticalSetupProofQuery,
    TacticalSupportRegion,
    TacticalSupportSurface,
    tactical_setup_is_excluded,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume


def query_for(*passengers: Model) -> TacticalSetupProofQuery:
    carrier = Model("carrier", Pose.at(10, 10), CircularBase(2), ModelVolume(1))
    return TacticalSetupProofQuery(
        passengers=passengers,
        transports=(carrier,),
        blockers=(carrier,),
        enemies=(),
        distance_inches=3,
        oversized_distance_inches=1,
        engagement_horizontal_inches=1,
        engagement_vertical_inches=5,
    )


def test_negative_proof_cannot_discard_a_legal_continuous_height() -> None:
    passenger = Model(
        "passenger",
        Pose.at(12.6, 10, -2),
        CircularBase(0.5),
        ModelVolume(5),
        measures_every_part=True,
    )
    query = query_for(passenger)
    assert DistanceMeasurementContext.from_models(
        query.transports[0], passenger
    ).target_wholly_within_distance(3)
    assert not tactical_setup_is_excluded(query)


def test_tall_frame_has_no_tactical_height_but_can_fit_combat_distance() -> None:
    passenger = Model(
        "passenger",
        Pose.at(13, 10, -3.5),
        CircularBase(0.5),
        ModelVolume(8),
        measures_every_part=True,
    )
    query = query_for(passenger)
    context = DistanceMeasurementContext.from_models(query.transports[0], passenger)
    assert not context.target_wholly_within_distance(3)
    assert context.target_wholly_within_distance(6)
    assert tactical_setup_is_excluded(query)


def test_all_passengers_vary_jointly_instead_of_fixing_other_submitted_poses() -> None:
    first = Model("first", Pose.at(100, 100), CircularBase(0.5), ModelVolume(1))
    second = replace(first, model_id="second")
    assert not tactical_setup_is_excluded(query_for(first, second))


def test_noncircular_relaxation_does_not_claim_sampled_absence_is_impossible() -> None:
    passenger = Model("passenger", Pose.at(100, 100), OvalBase(2, 1), ModelVolume(1))
    assert not tactical_setup_is_excluded(query_for(passenger))


def test_negative_proof_declines_unbounded_numeric_inputs() -> None:
    passenger = Model("passenger", Pose.at(1e20, 0), CircularBase(0.5), ModelVolume(1))
    with pytest.raises(GeometryError, match="numeric proof domain"):
        tactical_setup_is_excluded(query_for(passenger))


def test_elevated_support_constraint_proves_crowded_top_without_discarding_other_planes() -> None:
    passenger = Model("passenger", Pose.at(15.8, 10), CircularBase(0.75), ModelVolume(2))
    query = query_for(passenger)
    carrier = replace(query.transports[0], pose=Pose.at(10, 10, 5.5))
    query = replace(query, transports=(carrier,), blockers=(carrier,))
    assert not tactical_setup_is_excluded(query)
    region = TacticalSupportRegion((5, 5, 15, 15), (TacticalSupportSurface((8, 8, 12, 12), 5.5),))
    assert tactical_setup_is_excluded(replace(query, support_regions=(region,)))
    for surface in (
        TacticalSupportSurface((6, 6, 14, 14), 5.5),
        TacticalSupportSurface((5, 5, 15, 15), 3),
    ):
        # More floor area or a distinct lower plane admits real Tactical poses.
        permissive = replace(region, surfaces=(*region.surfaces, surface))
        assert not tactical_setup_is_excluded(replace(query, support_regions=(permissive,)))


def test_support_certificate_does_not_impose_a_ground_or_floor_only_domain() -> None:
    passenger = Model("passenger", Pose.at(10, 10, -2), CircularBase(0.5), ModelVolume(1))
    region = TacticalSupportRegion((5, 5, 15, 15), ())
    assert not tactical_setup_is_excluded(replace(query_for(passenger), support_regions=(region,)))
