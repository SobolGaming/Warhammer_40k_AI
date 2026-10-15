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


def test_negative_proof_declines_unbounded_numeric_inputs() -> None:
    passenger = Model("passenger", Pose.at(1e20, 0), CircularBase(0.5), ModelVolume(1))
    with pytest.raises(GeometryError, match="numeric proof domain"):
        tactical_setup_is_excluded(query_for(passenger))


__all__: list[str] = []
__all__ += ["OvalBase", "TacticalSetupProofQuery", "TacticalSupportRegion"]
__all__ += ["TacticalSupportSurface", "replace"]
