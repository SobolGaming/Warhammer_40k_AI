"""Shared source-backed oversized setup geometry and restriction authority."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZoneCircleCutout,
    DeploymentZonePolygonCutout,
    DeploymentZoneShape,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.setup_fit import Region, base_fits_region, base_fits_regions
from warhammer40k_core.geometry.visibility_algebra import VisibilityComputationError
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_large_model_setup_2026_09 as large_model_source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.mission_setup import MissionSetup


def base_fits_zone(base: BaseShape, shape: DeploymentZoneShape) -> bool:
    return base_fits_regions(base, (_zone_region(shape),))


def _zone_region(shape: DeploymentZoneShape) -> Region:
    return (
        tuple(tuple((v.x, v.y) for v in p.vertices) for p in shape.polygons),
        tuple(
            tuple((v.x, v.y) for v in p.vertices)
            for p in shape.cutouts
            if isinstance(p, DeploymentZonePolygonCutout)
        ),
        tuple(
            (p.center_x, p.center_y, p.radius)
            for p in shape.cutouts
            if isinstance(p, DeploymentZoneCircleCutout)
        ),
    )


def model_bounds(model: Model) -> tuple[float, float, float, float]:
    base, pose = model.base, model.pose
    c, s = math.cos(math.radians(pose.facing.degrees)), math.sin(math.radians(pose.facing.degrees))
    if isinstance(base, CircularBase):
        dx = dy = base.radius
    elif isinstance(base, OvalBase):
        dx = math.hypot(base.length * c, base.width * s) / 2
        dy = math.hypot(base.length * s, base.width * c) / 2
    elif isinstance(base, RectangularBase):
        dx = (base.length * abs(c) + base.width * abs(s)) / 2
        dy = (base.length * abs(s) + base.width * abs(c)) / 2
    else:
        raise GameLifecycleError("Unsupported oversized setup base.")
    return pose.position.x - dx, pose.position.y - dy, pose.position.x + dx, pose.position.y + dy


def oversized_deployment_violation(
    *, model: Model, zones: tuple[DeploymentZone, ...], mission: MissionSetup, player_id: str
) -> str | None:
    if (
        not large_model_source.SETUP_POLICY.deployment_requires_impossible_fit
        or not large_model_source.SETUP_POLICY.deployment_requires_own_edge
    ):
        raise GameLifecycleError("Oversized setup source policy drifted.")
    try:
        fits = base_fits_regions(model.base, tuple(_zone_region(zone.shape) for zone in zones))
    except VisibilityComputationError as exc:
        raise GameLifecycleError("Oversized setup fit computation is unresolved.") from exc
    if fits:
        return "deployment_zone_violation"
    edge = (
        mission.attacker_battlefield_edge
        if player_id == mission.attacker_player_id
        else mission.defender_battlefield_edge
    )
    if edge is None:
        return "large_model_player_edge_unsupported"
    left, bottom, right, top = model_bounds(model)
    contacts = {
        "west": left,
        "east": right - mission.battlefield_width_inches,
        "south": bottom,
        "north": top - mission.battlefield_depth_inches,
    }
    edge_components = {
        "north": ("north",),
        "south": ("south",),
        "east": ("east",),
        "west": ("west",),
        "north_west_corner": ("north", "west"),
        "north_east_corner": ("north", "east"),
        "south_west_corner": ("south", "west"),
        "south_east_corner": ("south", "east"),
    }[edge]
    if not any(math.isclose(contacts[e], 0, rel_tol=0, abs_tol=1e-9) for e in edge_components):
        return "large_model_edge_contact_missing"
    return None


def base_fits_edge_band(
    model: Model,
    *,
    edge: object,
    distance_inches: float,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    from warhammer40k_core.engine.reserves import BattlefieldEdge

    if edge in (BattlefieldEdge.NORTH, BattlefieldEdge.SOUTH):
        width, depth = battlefield_width_inches, min(distance_inches, battlefield_depth_inches)
    elif edge in (BattlefieldEdge.WEST, BattlefieldEdge.EAST):
        width, depth = min(distance_inches, battlefield_width_inches), battlefield_depth_inches
    else:
        raise GameLifecycleError("Unsupported oversized setup battlefield edge.")
    return base_fits_region(model.base, (((0.0, 0.0), (width, 0.0), (width, depth), (0.0, depth)),))
