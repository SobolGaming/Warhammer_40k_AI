from tests.shared.category_migration.order135_tactical_setup_proof import (
    CircularBase,
    DistanceMeasurementContext,
    GeometryError,
    Model,
    ModelVolume,
    OvalBase,
    Pose,
    TacticalSetupProofQuery,
    TacticalSupportRegion,
    TacticalSupportSurface,
    pytest,
    query_for,
    replace,
    tactical_setup_is_excluded,
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


def test_all_passengers_vary_jointly_instead_of_fixing_other_submitted_poses() -> None:
    first = Model("first", Pose.at(100, 100), CircularBase(0.5), ModelVolume(1))
    second = replace(first, model_id="second")
    assert not tactical_setup_is_excluded(query_for(first, second))


def test_noncircular_relaxation_does_not_claim_sampled_absence_is_impossible() -> None:
    passenger = Model("passenger", Pose.at(100, 100), OvalBase(2, 1), ModelVolume(1))
    assert not tactical_setup_is_excluded(query_for(passenger))


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


__all__: list[str] = []
__all__ += ["GeometryError", "TacticalSetupProofQuery", "pytest"]
