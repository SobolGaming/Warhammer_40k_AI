from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.placement_errors import PlacementError
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureRulesGeometryPayload,
)


class SpatialIndexStatePayload(TypedDict):
    terrain_revision: int
    model_blocker_revision: int
    terrain_feature_ids: list[str]
    terrain_volume_ids: list[str]
    los_cache_key: str
    pathing_cache_key: str


@dataclass(frozen=True, slots=True)
class SpatialIndexState:
    terrain_revision: int = 0
    model_blocker_revision: int = 0
    terrain_feature_ids: tuple[str, ...] = ()
    terrain_volume_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_revision",
            _validate_non_negative_int(
                "SpatialIndexState terrain_revision",
                self.terrain_revision,
            ),
        )
        object.__setattr__(
            self,
            "model_blocker_revision",
            _validate_non_negative_int(
                "SpatialIndexState model_blocker_revision",
                self.model_blocker_revision,
            ),
        )
        object.__setattr__(
            self,
            "terrain_feature_ids",
            _validate_identifier_tuple(
                "SpatialIndexState terrain_feature_ids",
                self.terrain_feature_ids,
            ),
        )
        object.__setattr__(
            self,
            "terrain_volume_ids",
            _validate_identifier_tuple(
                "SpatialIndexState terrain_volume_ids",
                self.terrain_volume_ids,
            ),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls()

    @classmethod
    def from_terrain_features(
        cls,
        features: tuple[TerrainFeatureDefinition, ...],
        *,
        model_blocker_revision: int = 0,
    ) -> Self:
        terrain_features = _validate_terrain_feature_tuple(
            "SpatialIndexState features",
            features,
        )
        return cls(
            terrain_revision=_terrain_revision_for_features(terrain_features),
            model_blocker_revision=model_blocker_revision,
            terrain_feature_ids=tuple(feature.feature_id for feature in terrain_features),
            terrain_volume_ids=tuple(
                volume.terrain_id
                for feature in terrain_features
                for volume in feature.terrain_volumes()
            ),
        )

    def los_cache_key(self) -> str:
        return _spatial_cache_key(
            "los",
            terrain_revision=self.terrain_revision,
            model_blocker_revision=self.model_blocker_revision,
            terrain_feature_ids=self.terrain_feature_ids,
            terrain_volume_ids=self.terrain_volume_ids,
        )

    def pathing_cache_key(self) -> str:
        return _spatial_cache_key(
            "pathing",
            terrain_revision=self.terrain_revision,
            model_blocker_revision=self.model_blocker_revision,
            terrain_feature_ids=self.terrain_feature_ids,
            terrain_volume_ids=self.terrain_volume_ids,
        )

    def rebuild_spatial_index(
        self,
        features: tuple[TerrainFeatureDefinition, ...],
    ) -> SpatialIndex:
        expected_state = type(self).from_terrain_features(
            features,
            model_blocker_revision=self.model_blocker_revision,
        )
        if expected_state != self:
            raise PlacementError("SpatialIndexState does not match the supplied terrain features.")
        return SpatialIndex(
            terrain=tuple(
                volume
                for feature in _validate_terrain_feature_tuple(
                    "SpatialIndexState features",
                    features,
                )
                for volume in feature.terrain_volumes()
            ),
            generation=self.terrain_revision,
        )

    def to_payload(self) -> SpatialIndexStatePayload:
        return {
            "terrain_revision": self.terrain_revision,
            "model_blocker_revision": self.model_blocker_revision,
            "terrain_feature_ids": list(self.terrain_feature_ids),
            "terrain_volume_ids": list(self.terrain_volume_ids),
            "los_cache_key": self.los_cache_key(),
            "pathing_cache_key": self.pathing_cache_key(),
        }

    @classmethod
    def from_payload(cls, payload: SpatialIndexStatePayload) -> Self:
        state = cls(
            terrain_revision=payload["terrain_revision"],
            model_blocker_revision=payload["model_blocker_revision"],
            terrain_feature_ids=tuple(payload["terrain_feature_ids"]),
            terrain_volume_ids=tuple(payload["terrain_volume_ids"]),
        )
        if payload["los_cache_key"] != state.los_cache_key():
            raise PlacementError("SpatialIndexState los_cache_key does not match payload state.")
        if payload["pathing_cache_key"] != state.pathing_cache_key():
            raise PlacementError(
                "SpatialIndexState pathing_cache_key does not match payload state."
            )
        return state


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise PlacementError(f"{field_name} must be an integer.")
    if value < 0:
        raise PlacementError(f"{field_name} must not be negative.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} entry", value)
        if identifier in seen:
            raise PlacementError(f"{field_name} entries must be unique.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise PlacementError(f"{field_name} must contain TerrainFeatureDefinition values.")
        if value.feature_id in seen:
            raise PlacementError("TerrainFeatureDefinition feature_id must not be duplicated.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _terrain_revision_for_features(features: tuple[TerrainFeatureDefinition, ...]) -> int:
    if not features:
        return 0
    payloads: list[TerrainFeatureRulesGeometryPayload] = [
        feature.to_rules_geometry_payload()
        for feature in _validate_terrain_feature_tuple(
            "SpatialIndexState features",
            features,
        )
    ]
    encoded = json.dumps(
        payloads,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return int(hashlib.sha256(encoded).hexdigest()[:16], 16)


def _spatial_cache_key(
    namespace: str,
    *,
    terrain_revision: int,
    model_blocker_revision: int,
    terrain_feature_ids: tuple[str, ...],
    terrain_volume_ids: tuple[str, ...],
) -> str:
    cache_payload = {
        "namespace": namespace,
        "terrain_revision": terrain_revision,
        "model_blocker_revision": model_blocker_revision,
        "terrain_feature_ids": list(terrain_feature_ids),
        "terrain_volume_ids": list(terrain_volume_ids),
    }
    encoded = json.dumps(
        cache_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return f"{namespace}:{hashlib.sha256(encoded).hexdigest()[:16]}"


_validate_identifier = IdentifierValidator(PlacementError)
