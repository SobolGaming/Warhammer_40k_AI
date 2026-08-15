from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
)


class MissionActionBattlefieldBoundaryEvidencePayload(TypedDict):
    battlefield_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    terrain_features: list[TerrainFeatureDefinitionPayload]


@dataclass(frozen=True, slots=True)
class MissionActionBattlefieldBoundaryEvidence:
    """Minimal immutable battlefield context needed to rederive start visibility."""

    battlefield_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    terrain_features: tuple[TerrainFeatureDefinition, ...]

    def __post_init__(self) -> None:
        boundary = BattlefieldRuntimeState(
            battlefield_id=self.battlefield_id,
            battlefield_width_inches=self.battlefield_width_inches,
            battlefield_depth_inches=self.battlefield_depth_inches,
            placed_armies=(),
            terrain_features=self.terrain_features,
        )
        object.__setattr__(self, "battlefield_id", boundary.battlefield_id)
        object.__setattr__(
            self,
            "battlefield_width_inches",
            boundary.battlefield_width_inches,
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            boundary.battlefield_depth_inches,
        )
        object.__setattr__(self, "terrain_features", boundary.terrain_features)

    @classmethod
    def from_battlefield_state(cls, state: BattlefieldRuntimeState) -> Self:
        if type(state) is not BattlefieldRuntimeState:
            raise GameLifecycleError(
                "Primary Mission Action battlefield boundary requires typed state."
            )
        return cls(
            battlefield_id=state.battlefield_id,
            battlefield_width_inches=state.battlefield_width_inches,
            battlefield_depth_inches=state.battlefield_depth_inches,
            terrain_features=state.terrain_features,
        )

    def to_payload(self) -> MissionActionBattlefieldBoundaryEvidencePayload:
        return {
            "battlefield_id": self.battlefield_id,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise GameLifecycleError(
                "Primary Mission Action battlefield boundary payload must be an object."
            )
        raw = cast(dict[object, object], payload)
        expected_keys = {
            "battlefield_id",
            "battlefield_width_inches",
            "battlefield_depth_inches",
            "terrain_features",
        }
        if set(raw) != expected_keys:
            raise GameLifecycleError(
                "Primary Mission Action battlefield boundary payload keys drifted."
            )
        battlefield_id = raw["battlefield_id"]
        width = raw["battlefield_width_inches"]
        depth = raw["battlefield_depth_inches"]
        terrain = raw["terrain_features"]
        if (
            type(battlefield_id) is not str
            or type(width) not in {int, float}
            or type(depth) not in {int, float}
            or type(terrain) is not list
        ):
            raise GameLifecycleError(
                "Primary Mission Action battlefield boundary payload is invalid."
            )
        validated_width = cast(int | float, width)
        validated_depth = cast(int | float, depth)
        terrain_payloads = cast(list[object], terrain)
        return cls(
            battlefield_id=battlefield_id,
            battlefield_width_inches=float(validated_width),
            battlefield_depth_inches=float(validated_depth),
            terrain_features=tuple(
                TerrainFeatureDefinition.from_payload(item) for item in terrain_payloads
            ),
        )


__all__ = (
    "MissionActionBattlefieldBoundaryEvidence",
    "MissionActionBattlefieldBoundaryEvidencePayload",
)
