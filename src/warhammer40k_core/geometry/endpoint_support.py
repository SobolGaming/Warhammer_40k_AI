"""The physical support domain shared by endpoint validation and contact proofs."""

from __future__ import annotations

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model


def endpoint_support_elevations(
    *, terrain: tuple[TerrainVolume, ...], features: tuple[TerrainFeatureDefinition, ...]
) -> tuple[float, ...]:
    return tuple(
        sorted(
            {
                0.0,
                *(v.top_z_inches() for v in terrain),
                *(
                    s.z_inches
                    for f in features
                    for s in f.support_surfaces(no_overhang_required=False)
                ),
            }
        )
    )


def model_has_endpoint_support(
    model: Model,
    *,
    terrain: tuple[TerrainVolume, ...],
    features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    """Raised endpoints require a physical support; feature policy further restricts it.

    Support elevations are explicit serialized planes, not neighborhoods around
    them. Treating floating endpoints as valid would make every discrete support
    certificate unsound (and permit models to stop in mid-air).
    """
    z = model.pose.position.z
    if z == 0.0:
        return True
    return any(
        z == surface.z_inches
        and shapely_backend.base_footprint_intersects_polygon(
            model.base, model.pose, surface.footprint_polygon()
        )
        for feature in features
        for surface in feature.support_surfaces(no_overhang_required=False)
    ) or any(
        z == volume.top_z_inches()
        and shapely_backend.footprint_for_base(model.base, model.pose).intersects(
            shapely_backend.footprint_for_terrain(volume)
        )
        for volume in terrain
    )
