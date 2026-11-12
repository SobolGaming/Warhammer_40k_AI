"""Validation-local footprint preparation; no legality or prefix results are cached."""

from __future__ import annotations

from dataclasses import dataclass, field

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import BaseShape
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainVolume

type Bounds = tuple[float, float, float, float]
type PreparedSample = tuple[Pose, shapely_backend.FootprintGeometry, Bounds]


@dataclass(frozen=True, slots=True)
class TerrainPathFootprints:
    """Own immutable inputs for exactly one complete terrain validation call.

    Lazy preparation preserves the no-terrain and beneath-lintel fast paths.
    Its storage is bounded by the current sampled path and discarded with the
    validation, so new paths, models, terrain and games cannot inherit results.
    """

    base: BaseShape
    sampled_path: tuple[Pose, ...]
    _samples: tuple[PreparedSample, ...] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def touching_poses(self, terrain: TerrainVolume) -> tuple[Pose, ...]:
        samples = self._samples
        if samples is None:
            footprints = tuple(
                (pose, shapely_backend.footprint_for_base(self.base, pose))
                for pose in self.sampled_path
            )
            samples = tuple((pose, footprint, footprint.bounds) for pose, footprint in footprints)
            object.__setattr__(self, "_samples", samples)
        footprint = shapely_backend.footprint_for_terrain(terrain)
        bounds = footprint.bounds
        # Bounds come from the same exact geometries as the narrow phase. Strict
        # separation alone rejects; touching bounds still execute intersects.
        return tuple(
            pose
            for pose, sample, sample_bounds in samples
            if not (
                sample_bounds[2] < bounds[0]
                or bounds[2] < sample_bounds[0]
                or sample_bounds[3] < bounds[1]
                or bounds[3] < sample_bounds[1]
            )
            and footprint.intersects(sample)
        )
