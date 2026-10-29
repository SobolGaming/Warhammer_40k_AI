"""Section 13.06 endpoint policy for explicitly classified terrain features."""

from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import (
    TerrainEndpointSupportPolicy,
    TerrainFeatureMovementPolicy,
)
from warhammer40k_core.geometry.terrain_classification import (
    TerrainAreaClassification,
    terrain_area_classification_from_token,
)

RUINS_UPPER_FLOOR_KEYWORDS = (
    "BEAST",
    "BELISARIUS_CAWL",
    "FLY",
    "IMPERIUM_PRIMARCH",
    "INFANTRY",
    "MONSTER",
    "SWARM",
)
SURFACE_KEYWORDS = ("BEAST", "FLY", "INFANTRY", "MONSTER", "SWARM")


def classified_terrain_endpoint_policy(
    policy: TerrainFeatureMovementPolicy,
    classification: object,
) -> TerrainFeatureMovementPolicy:
    """Apply upper-surface eligibility independently of legacy feature kind.

    Eligibility is seeded in the descriptor before physical-model narrowing.
    Classification must retain that narrowed keyword list, including explicit
    move grants and existing exceptions. It changes support flags, never authority.
    """
    if terrain_area_classification_from_token(classification) not in (
        TerrainAreaClassification.EXPOSED,
        TerrainAreaClassification.LIGHT,
        TerrainAreaClassification.DENSE,
    ):
        return policy
    return replace(
        policy,
        endpoint_support_policy=TerrainEndpointSupportPolicy.ALLOWED_ON_ANY_FLOOR_WITH_NO_OVERHANG,
        no_overhang_required=True,
        ground_floor_only_unless_keyword=True,
    )
