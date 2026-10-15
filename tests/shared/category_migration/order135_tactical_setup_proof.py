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


__all__: list[str] = []
__all__ += ["CircularBase", "DistanceMeasurementContext", "GeometryError", "Model", "ModelVolume"]
__all__ += ["OvalBase", "Pose", "TacticalSetupProofQuery", "TacticalSupportRegion"]
__all__ += ["TacticalSupportSurface", "pytest", "query_for", "replace"]
__all__ += ["tactical_setup_is_excluded"]
