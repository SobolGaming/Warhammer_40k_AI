from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness, PathWitnessPayload
from warhammer40k_core.geometry.pose import Pose, PosePayload
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
)


class PlacementError(ValueError):
    """Raised when battlefield placement violates CORE V2 invariants."""


class ModelDisplacementKind(StrEnum):
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"
    CHARGE_MOVE = "charge_move"
    PILE_IN = "pile_in"
    CONSOLIDATE = "consolidate"
    SURGE_MOVE = "surge_move"
    TRIGGERED_MOVE = "triggered_move"
    SCOUT_MOVE = "scout_move"


class BattlefieldPlacementKind(StrEnum):
    DEPLOYMENT = "deployment"
    REDEPLOY = "redeploy"
    STRATEGIC_RESERVES = "strategic_reserves"
    DEEP_STRIKE = "deep_strike"
    DISEMBARK = "disembark"
    RETURN_TO_BATTLEFIELD = "return_to_battlefield"
    SPLIT_UNIT = "split_unit"


class BattlefieldRemovalKind(StrEnum):
    DESTROYED = "destroyed"
    EMBARK = "embark"
    INTO_RESERVES = "into_reserves"
    TEMPORARILY_REMOVED = "temporarily_removed"


class ModelPlacementRecordPayload(TypedDict):
    model_instance_id: str
    placement_kind: str
    pose: PosePayload
    source_phase: str | None
    source_step: str | None
    source_rule_id: str | None
    source_event_id: str | None


class ModelRemovalRecordPayload(TypedDict):
    model_instance_id: str
    removal_kind: str
    source_phase: str | None
    source_step: str | None
    source_rule_id: str | None
    source_event_id: str | None
    destination_id: str | None


class ModelDisplacementRecordPayload(TypedDict):
    model_instance_id: str
    displacement_kind: str
    start_pose: PosePayload
    end_pose: PosePayload
    path_witness: PathWitnessPayload | None
    source_phase: str | None
    source_step: str | None
    source_rule_id: str | None
    source_event_id: str | None


class BattlefieldTransitionBatchPayload(TypedDict):
    placements: list[ModelPlacementRecordPayload]
    removals: list[ModelRemovalRecordPayload]
    displacements: list[ModelDisplacementRecordPayload]


class SpatialIndexStatePayload(TypedDict):
    terrain_revision: int
    model_blocker_revision: int
    terrain_feature_ids: list[str]
    terrain_volume_ids: list[str]
    los_cache_key: str
    pathing_cache_key: str


class ModelPlacementPayload(TypedDict):
    army_id: str
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    pose: PosePayload


class UnitPlacementPayload(TypedDict):
    army_id: str
    player_id: str
    unit_instance_id: str
    model_placements: list[ModelPlacementPayload]


class PlacedArmyPayload(TypedDict):
    army_id: str
    player_id: str
    unit_placements: list[UnitPlacementPayload]


class BattlefieldRuntimeStatePayload(TypedDict):
    battlefield_id: str
    placed_armies: list[PlacedArmyPayload]


class BattlefieldScenarioPayload(TypedDict):
    armies: list[ArmyDefinitionPayload]
    battlefield_state: BattlefieldRuntimeStatePayload


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


@dataclass(frozen=True, slots=True)
class ModelPlacementRecord:
    model_instance_id: str
    placement_kind: BattlefieldPlacementKind
    pose: Pose
    source_phase: str | None = None
    source_step: str | None = None
    source_rule_id: str | None = None
    source_event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_unprefixed_identifier(
                "ModelPlacementRecord model_instance_id",
                self.model_instance_id,
                "model:",
            ),
        )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        if type(self.pose) is not Pose:
            raise PlacementError("ModelPlacementRecord pose must be a Pose.")
        object.__setattr__(
            self,
            "source_phase",
            _validate_optional_identifier("ModelPlacementRecord source_phase", self.source_phase),
        )
        object.__setattr__(
            self,
            "source_step",
            _validate_optional_identifier("ModelPlacementRecord source_step", self.source_step),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_optional_identifier(
                "ModelPlacementRecord source_rule_id",
                self.source_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "source_event_id",
            _validate_optional_identifier(
                "ModelPlacementRecord source_event_id",
                self.source_event_id,
            ),
        )

    def to_payload(self) -> ModelPlacementRecordPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "placement_kind": self.placement_kind.value,
            "pose": self.pose.to_payload(),
            "source_phase": self.source_phase,
            "source_step": self.source_step,
            "source_rule_id": self.source_rule_id,
            "source_event_id": self.source_event_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelPlacementRecordPayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            placement_kind=battlefield_placement_kind_from_token(payload["placement_kind"]),
            pose=Pose.from_payload(payload["pose"]),
            source_phase=payload["source_phase"],
            source_step=payload["source_step"],
            source_rule_id=payload["source_rule_id"],
            source_event_id=payload["source_event_id"],
        )


@dataclass(frozen=True, slots=True)
class ModelRemovalRecord:
    model_instance_id: str
    removal_kind: BattlefieldRemovalKind
    source_phase: str | None = None
    source_step: str | None = None
    source_rule_id: str | None = None
    source_event_id: str | None = None
    destination_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_unprefixed_identifier(
                "ModelRemovalRecord model_instance_id",
                self.model_instance_id,
                "model:",
            ),
        )
        object.__setattr__(
            self,
            "removal_kind",
            battlefield_removal_kind_from_token(self.removal_kind),
        )
        object.__setattr__(
            self,
            "source_phase",
            _validate_optional_identifier("ModelRemovalRecord source_phase", self.source_phase),
        )
        object.__setattr__(
            self,
            "source_step",
            _validate_optional_identifier("ModelRemovalRecord source_step", self.source_step),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_optional_identifier(
                "ModelRemovalRecord source_rule_id",
                self.source_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "source_event_id",
            _validate_optional_identifier(
                "ModelRemovalRecord source_event_id",
                self.source_event_id,
            ),
        )
        object.__setattr__(
            self,
            "destination_id",
            _validate_optional_identifier("ModelRemovalRecord destination_id", self.destination_id),
        )

    def to_payload(self) -> ModelRemovalRecordPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "removal_kind": self.removal_kind.value,
            "source_phase": self.source_phase,
            "source_step": self.source_step,
            "source_rule_id": self.source_rule_id,
            "source_event_id": self.source_event_id,
            "destination_id": self.destination_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelRemovalRecordPayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            removal_kind=battlefield_removal_kind_from_token(payload["removal_kind"]),
            source_phase=payload["source_phase"],
            source_step=payload["source_step"],
            source_rule_id=payload["source_rule_id"],
            source_event_id=payload["source_event_id"],
            destination_id=payload["destination_id"],
        )


@dataclass(frozen=True, slots=True)
class ModelDisplacementRecord:
    model_instance_id: str
    displacement_kind: ModelDisplacementKind
    start_pose: Pose
    end_pose: Pose
    path_witness: PathWitness | None = None
    source_phase: str | None = None
    source_step: str | None = None
    source_rule_id: str | None = None
    source_event_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_unprefixed_identifier(
                "ModelDisplacementRecord model_instance_id",
                self.model_instance_id,
                "model:",
            ),
        )
        object.__setattr__(
            self,
            "displacement_kind",
            model_displacement_kind_from_token(self.displacement_kind),
        )
        if type(self.start_pose) is not Pose:
            raise PlacementError("ModelDisplacementRecord start_pose must be a Pose.")
        if type(self.end_pose) is not Pose:
            raise PlacementError("ModelDisplacementRecord end_pose must be a Pose.")
        if self.start_pose == self.end_pose:
            raise PlacementError("ModelDisplacementRecord start_pose and end_pose must differ.")
        if self.path_witness is not None and type(self.path_witness) is not PathWitness:
            raise PlacementError("ModelDisplacementRecord path_witness must be a PathWitness.")
        object.__setattr__(
            self,
            "source_phase",
            _validate_optional_identifier(
                "ModelDisplacementRecord source_phase",
                self.source_phase,
            ),
        )
        object.__setattr__(
            self,
            "source_step",
            _validate_optional_identifier("ModelDisplacementRecord source_step", self.source_step),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_optional_identifier(
                "ModelDisplacementRecord source_rule_id",
                self.source_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "source_event_id",
            _validate_optional_identifier(
                "ModelDisplacementRecord source_event_id",
                self.source_event_id,
            ),
        )

    def to_payload(self) -> ModelDisplacementRecordPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "displacement_kind": self.displacement_kind.value,
            "start_pose": self.start_pose.to_payload(),
            "end_pose": self.end_pose.to_payload(),
            "path_witness": None if self.path_witness is None else self.path_witness.to_payload(),
            "source_phase": self.source_phase,
            "source_step": self.source_step,
            "source_rule_id": self.source_rule_id,
            "source_event_id": self.source_event_id,
        }

    @classmethod
    def from_payload(cls, payload: ModelDisplacementRecordPayload) -> Self:
        witness_payload = payload["path_witness"]
        return cls(
            model_instance_id=payload["model_instance_id"],
            displacement_kind=model_displacement_kind_from_token(payload["displacement_kind"]),
            start_pose=Pose.from_payload(payload["start_pose"]),
            end_pose=Pose.from_payload(payload["end_pose"]),
            path_witness=(
                None if witness_payload is None else PathWitness.from_payload(witness_payload)
            ),
            source_phase=payload["source_phase"],
            source_step=payload["source_step"],
            source_rule_id=payload["source_rule_id"],
            source_event_id=payload["source_event_id"],
        )


@dataclass(frozen=True, slots=True)
class BattlefieldTransitionBatch:
    placements: tuple[ModelPlacementRecord, ...] = ()
    removals: tuple[ModelRemovalRecord, ...] = ()
    displacements: tuple[ModelDisplacementRecord, ...] = ()

    def __post_init__(self) -> None:
        placements = _validate_placement_records(
            "BattlefieldTransitionBatch placements",
            self.placements,
        )
        removals = _validate_removal_records(
            "BattlefieldTransitionBatch removals",
            self.removals,
        )
        displacements = _validate_displacement_records(
            "BattlefieldTransitionBatch displacements",
            self.displacements,
        )
        placement_ids = {record.model_instance_id for record in placements}
        removal_ids = {record.model_instance_id for record in removals}
        displacement_ids = {record.model_instance_id for record in displacements}
        if placement_ids & removal_ids:
            raise PlacementError(
                "BattlefieldTransitionBatch models must not be both placed and removed."
            )
        if placement_ids & displacement_ids:
            raise PlacementError(
                "BattlefieldTransitionBatch models must not be both placed and displaced."
            )
        if removal_ids & displacement_ids:
            raise PlacementError(
                "BattlefieldTransitionBatch models must not be both removed and displaced."
            )
        object.__setattr__(self, "placements", placements)
        object.__setattr__(self, "removals", removals)
        object.__setattr__(self, "displacements", displacements)

    def to_payload(self) -> BattlefieldTransitionBatchPayload:
        return {
            "placements": [record.to_payload() for record in self.placements],
            "removals": [record.to_payload() for record in self.removals],
            "displacements": [record.to_payload() for record in self.displacements],
        }

    @classmethod
    def from_payload(cls, payload: BattlefieldTransitionBatchPayload) -> Self:
        return cls(
            placements=tuple(
                ModelPlacementRecord.from_payload(record) for record in payload["placements"]
            ),
            removals=tuple(
                ModelRemovalRecord.from_payload(record) for record in payload["removals"]
            ),
            displacements=tuple(
                ModelDisplacementRecord.from_payload(record) for record in payload["displacements"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ModelPlacement:
    army_id: str
    player_id: str
    unit_instance_id: str
    model_instance_id: str
    pose: Pose

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("ModelPlacement army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ModelPlacement player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_unprefixed_identifier(
                "ModelPlacement unit_instance_id",
                self.unit_instance_id,
                "unit:",
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_unprefixed_identifier(
                "ModelPlacement model_instance_id",
                self.model_instance_id,
                "model:",
            ),
        )
        if not self.unit_instance_id.startswith(f"{self.army_id}:"):
            raise PlacementError("ModelPlacement unit_instance_id must be scoped to army_id.")
        if not self.model_instance_id.startswith(f"{self.unit_instance_id}:"):
            raise PlacementError(
                "ModelPlacement model_instance_id must be scoped to unit_instance_id."
            )
        if type(self.pose) is not Pose:
            raise PlacementError("ModelPlacement pose must be a Pose.")

    def to_payload(self) -> ModelPlacementPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "pose": self.pose.to_payload(),
        }

    def with_pose(self, pose: Pose) -> Self:
        return type(self)(
            army_id=self.army_id,
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            model_instance_id=self.model_instance_id,
            pose=pose,
        )

    @classmethod
    def from_payload(cls, payload: ModelPlacementPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            pose=Pose.from_payload(payload["pose"]),
        )


@dataclass(frozen=True, slots=True)
class UnitPlacement:
    army_id: str
    player_id: str
    unit_instance_id: str
    model_placements: tuple[ModelPlacement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("UnitPlacement army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("UnitPlacement player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_unprefixed_identifier(
                "UnitPlacement unit_instance_id",
                self.unit_instance_id,
                "unit:",
            ),
        )
        if not self.unit_instance_id.startswith(f"{self.army_id}:"):
            raise PlacementError("UnitPlacement unit_instance_id must be scoped to army_id.")
        model_placements = _validate_model_placements(
            "UnitPlacement model_placements",
            self.model_placements,
        )
        for model_placement in model_placements:
            if model_placement.army_id != self.army_id:
                raise PlacementError("UnitPlacement model_placements must match army_id.")
            if model_placement.player_id != self.player_id:
                raise PlacementError("UnitPlacement model_placements must match player_id.")
            if model_placement.unit_instance_id != self.unit_instance_id:
                raise PlacementError("UnitPlacement model_placements must match unit_instance_id.")
        object.__setattr__(self, "model_placements", model_placements)

    def to_payload(self) -> UnitPlacementPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "model_placements": [placement.to_payload() for placement in self.model_placements],
        }

    def with_model_placements(self, model_placements: tuple[ModelPlacement, ...]) -> Self:
        return type(self)(
            army_id=self.army_id,
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            model_placements=model_placements,
        )

    @classmethod
    def from_payload(cls, payload: UnitPlacementPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            model_placements=tuple(
                ModelPlacement.from_payload(placement) for placement in payload["model_placements"]
            ),
        )


@dataclass(frozen=True, slots=True)
class PlacedArmy:
    army_id: str
    player_id: str
    unit_placements: tuple[UnitPlacement, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("PlacedArmy army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("PlacedArmy player_id", self.player_id),
        )
        unit_placements = _validate_unit_placements(
            "PlacedArmy unit_placements",
            self.unit_placements,
        )
        for unit_placement in unit_placements:
            if unit_placement.army_id != self.army_id:
                raise PlacementError("PlacedArmy unit_placements must match army_id.")
            if unit_placement.player_id != self.player_id:
                raise PlacementError("PlacedArmy unit_placements must match player_id.")
        object.__setattr__(self, "unit_placements", unit_placements)

    def placed_model_ids(self) -> tuple[str, ...]:
        return tuple(
            model_placement.model_instance_id
            for unit_placement in self.unit_placements
            for model_placement in unit_placement.model_placements
        )

    def to_payload(self) -> PlacedArmyPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "unit_placements": [placement.to_payload() for placement in self.unit_placements],
        }

    @classmethod
    def from_payload(cls, payload: PlacedArmyPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            unit_placements=tuple(
                UnitPlacement.from_payload(placement) for placement in payload["unit_placements"]
            ),
        )


@dataclass(frozen=True, slots=True)
class BattlefieldRuntimeState:
    battlefield_id: str
    placed_armies: tuple[PlacedArmy, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battlefield_id",
            _validate_unprefixed_identifier(
                "BattlefieldRuntimeState battlefield_id",
                self.battlefield_id,
                "battlefield:",
            ),
        )
        placed_armies = _validate_placed_armies(
            "BattlefieldRuntimeState placed_armies",
            self.placed_armies,
        )
        _validate_unique_placed_armies(placed_armies)
        _validate_no_duplicate_placed_models(placed_armies)
        object.__setattr__(self, "placed_armies", placed_armies)

    def placed_model_ids(self) -> tuple[str, ...]:
        return tuple(
            model_id
            for placed_army in self.placed_armies
            for model_id in placed_army.placed_model_ids()
        )

    def placed_army_for_player(self, player_id: str) -> PlacedArmy:
        requested_player_id = _validate_identifier("player_id", player_id)
        for placed_army in self.placed_armies:
            if placed_army.player_id == requested_player_id:
                return placed_army
        raise PlacementError("BattlefieldRuntimeState player_id is not placed.")

    def unit_placement_by_id(self, unit_instance_id: str) -> UnitPlacement:
        requested_unit_id = _validate_unprefixed_identifier(
            "unit_instance_id",
            unit_instance_id,
            "unit:",
        )
        for placed_army in self.placed_armies:
            for unit_placement in placed_army.unit_placements:
                if unit_placement.unit_instance_id == requested_unit_id:
                    return unit_placement
        raise PlacementError("BattlefieldRuntimeState unit_instance_id is not placed.")

    def model_placement_by_id(self, model_instance_id: str) -> ModelPlacement:
        requested_model_id = _validate_unprefixed_identifier(
            "model_instance_id",
            model_instance_id,
            "model:",
        )
        for placed_army in self.placed_armies:
            for unit_placement in placed_army.unit_placements:
                for model_placement in unit_placement.model_placements:
                    if model_placement.model_instance_id == requested_model_id:
                        return model_placement
        raise PlacementError("BattlefieldRuntimeState model_instance_id is not placed.")

    def with_unit_placement(self, updated_unit_placement: UnitPlacement) -> Self:
        if type(updated_unit_placement) is not UnitPlacement:
            raise PlacementError("updated_unit_placement must be a UnitPlacement.")
        placed_armies: list[PlacedArmy] = []
        did_update = False
        for placed_army in self.placed_armies:
            if placed_army.army_id != updated_unit_placement.army_id:
                placed_armies.append(placed_army)
                continue
            unit_placements: list[UnitPlacement] = []
            for unit_placement in placed_army.unit_placements:
                if unit_placement.unit_instance_id == updated_unit_placement.unit_instance_id:
                    unit_placements.append(updated_unit_placement)
                    did_update = True
                else:
                    unit_placements.append(unit_placement)
            placed_armies.append(
                PlacedArmy(
                    army_id=placed_army.army_id,
                    player_id=placed_army.player_id,
                    unit_placements=tuple(unit_placements),
                )
            )
        if not did_update:
            raise PlacementError("BattlefieldRuntimeState updated unit is not placed.")
        return type(self)(
            battlefield_id=self.battlefield_id,
            placed_armies=tuple(placed_armies),
        )

    def to_payload(self) -> BattlefieldRuntimeStatePayload:
        return {
            "battlefield_id": self.battlefield_id,
            "placed_armies": [placed_army.to_payload() for placed_army in self.placed_armies],
        }

    @classmethod
    def from_payload(cls, payload: BattlefieldRuntimeStatePayload) -> Self:
        return cls(
            battlefield_id=payload["battlefield_id"],
            placed_armies=tuple(
                PlacedArmy.from_payload(placed_army) for placed_army in payload["placed_armies"]
            ),
        )


@dataclass(frozen=True, slots=True)
class BattlefieldScenario:
    armies: tuple[ArmyDefinition, ...]
    battlefield_state: BattlefieldRuntimeState

    def __post_init__(self) -> None:
        armies = _validate_army_definitions("BattlefieldScenario armies", self.armies)
        if type(self.battlefield_state) is not BattlefieldRuntimeState:
            raise PlacementError(
                "BattlefieldScenario battlefield_state must be a BattlefieldRuntimeState."
            )
        _validate_battlefield_state_references_armies(
            battlefield_state=self.battlefield_state,
            armies=armies,
        )
        object.__setattr__(self, "armies", armies)

    def army_by_id(self, army_id: str) -> ArmyDefinition:
        requested_id = _validate_unprefixed_identifier("army_id", army_id, "army:")
        for army in self.armies:
            if army.army_id == requested_id:
                return army
        raise PlacementError("BattlefieldScenario army_id was not found.")

    def unit_instance_for_placement(self, placement: UnitPlacement) -> UnitInstance:
        if type(placement) is not UnitPlacement:
            raise PlacementError("placement must be a UnitPlacement.")
        try:
            return self.army_by_id(placement.army_id).unit_by_id(placement.unit_instance_id)
        except ArmyMusteringError as exc:
            raise PlacementError("UnitPlacement must reference an existing UnitInstance.") from exc

    def model_instance_for_placement(self, placement: ModelPlacement) -> ModelInstance:
        if type(placement) is not ModelPlacement:
            raise PlacementError("placement must be a ModelPlacement.")
        try:
            unit = self.army_by_id(placement.army_id).unit_by_id(placement.unit_instance_id)
        except ArmyMusteringError as exc:
            raise PlacementError("UnitPlacement must reference an existing UnitInstance.") from exc
        for model in unit.own_models:
            if model.model_instance_id == placement.model_instance_id:
                return model
        raise PlacementError("BattlefieldScenario model_instance_id was not found.")

    def unplaced_model_ids(self) -> tuple[str, ...]:
        placed_model_ids = set(self.battlefield_state.placed_model_ids())
        return tuple(
            model.model_instance_id
            for army in self.armies
            for unit in army.units
            for model in unit.own_models
            if model.model_instance_id not in placed_model_ids
        )

    def assert_all_mustered_models_placed(self) -> None:
        unplaced_model_ids = self.unplaced_model_ids()
        if unplaced_model_ids:
            raise PlacementError(
                f"BattlefieldScenario has unplaced model IDs: {', '.join(unplaced_model_ids)}"
            )

    def to_payload(self) -> BattlefieldScenarioPayload:
        return {
            "armies": [army.to_payload() for army in self.armies],
            "battlefield_state": self.battlefield_state.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: BattlefieldScenarioPayload) -> Self:
        return cls(
            armies=tuple(_army_definition_from_payload(army) for army in payload["armies"]),
            battlefield_state=BattlefieldRuntimeState.from_payload(payload["battlefield_state"]),
        )


def battlefield_placement_kind_from_token(token: object) -> BattlefieldPlacementKind:
    if type(token) is BattlefieldPlacementKind:
        return token
    if type(token) is not str:
        raise PlacementError("BattlefieldPlacementKind token must be a string.")
    try:
        return BattlefieldPlacementKind(token)
    except ValueError as exc:
        raise PlacementError(f"Unsupported BattlefieldPlacementKind token: {token}.") from exc


def battlefield_removal_kind_from_token(token: object) -> BattlefieldRemovalKind:
    if type(token) is BattlefieldRemovalKind:
        return token
    if type(token) is not str:
        raise PlacementError("BattlefieldRemovalKind token must be a string.")
    try:
        return BattlefieldRemovalKind(token)
    except ValueError as exc:
        raise PlacementError(f"Unsupported BattlefieldRemovalKind token: {token}.") from exc


def model_displacement_kind_from_token(token: object) -> ModelDisplacementKind:
    if type(token) is ModelDisplacementKind:
        return token
    if type(token) is not str:
        raise PlacementError("ModelDisplacementKind token must be a string.")
    try:
        return ModelDisplacementKind(token)
    except ValueError as exc:
        raise PlacementError(f"Unsupported ModelDisplacementKind token: {token}.") from exc


def _validate_battlefield_state_references_armies(
    *,
    battlefield_state: BattlefieldRuntimeState,
    armies: tuple[ArmyDefinition, ...],
) -> None:
    army_by_id = {army.army_id: army for army in armies}
    for placed_army in battlefield_state.placed_armies:
        army = army_by_id.get(placed_army.army_id)
        if army is None:
            raise PlacementError("PlacedArmy must reference an existing ArmyDefinition.")
        if placed_army.player_id != army.player_id:
            raise PlacementError("PlacedArmy belongs to the wrong player.")
        for unit_placement in placed_army.unit_placements:
            unit = _unit_for_placement(army=army, placement=unit_placement)
            for model_placement in unit_placement.model_placements:
                _model_for_placement(unit=unit, placement=model_placement)


def _unit_for_placement(*, army: ArmyDefinition, placement: UnitPlacement) -> UnitInstance:
    try:
        return army.unit_by_id(placement.unit_instance_id)
    except ArmyMusteringError as exc:
        raise PlacementError("UnitPlacement must reference an existing UnitInstance.") from exc


def _model_for_placement(*, unit: UnitInstance, placement: ModelPlacement) -> ModelInstance:
    for model in unit.own_models:
        if model.model_instance_id == placement.model_instance_id:
            return model
    raise PlacementError("ModelPlacement must reference an existing ModelInstance.")


def _army_definition_from_payload(payload: ArmyDefinitionPayload) -> ArmyDefinition:
    try:
        return ArmyDefinition.from_payload(payload)
    except ArmyMusteringError as exc:
        raise PlacementError("BattlefieldScenario army payload is invalid.") from exc


def _validate_placement_records(
    field_name: str,
    values: object,
) -> tuple[ModelPlacementRecord, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    records: list[ModelPlacementRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ModelPlacementRecord:
            raise PlacementError(f"{field_name} must contain ModelPlacementRecord values.")
        if value.model_instance_id in seen:
            raise PlacementError("ModelPlacementRecord model_instance_id must not be duplicated.")
        seen.add(value.model_instance_id)
        records.append(value)
    return tuple(records)


def _validate_removal_records(
    field_name: str,
    values: object,
) -> tuple[ModelRemovalRecord, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    records: list[ModelRemovalRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ModelRemovalRecord:
            raise PlacementError(f"{field_name} must contain ModelRemovalRecord values.")
        if value.model_instance_id in seen:
            raise PlacementError("ModelRemovalRecord model_instance_id must not be duplicated.")
        seen.add(value.model_instance_id)
        records.append(value)
    return tuple(records)


def _validate_displacement_records(
    field_name: str,
    values: object,
) -> tuple[ModelDisplacementRecord, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    records: list[ModelDisplacementRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ModelDisplacementRecord:
            raise PlacementError(f"{field_name} must contain ModelDisplacementRecord values.")
        if value.model_instance_id in seen:
            raise PlacementError(
                "ModelDisplacementRecord model_instance_id must not be duplicated."
            )
        seen.add(value.model_instance_id)
        records.append(value)
    return tuple(records)


def _validate_model_placements(
    field_name: str,
    values: object,
) -> tuple[ModelPlacement, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise PlacementError(f"{field_name} must not be empty.")
    placements: list[ModelPlacement] = []
    seen: set[str] = set()
    for value in raw_values:
        if type(value) is not ModelPlacement:
            raise PlacementError(f"{field_name} must contain ModelPlacement values.")
        if value.model_instance_id in seen:
            raise PlacementError("ModelPlacement model_instance_id must not be placed twice.")
        seen.add(value.model_instance_id)
        placements.append(value)
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def _validate_unit_placements(
    field_name: str,
    values: object,
) -> tuple[UnitPlacement, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise PlacementError(f"{field_name} must not be empty.")
    placements: list[UnitPlacement] = []
    seen_units: set[str] = set()
    seen_models: set[str] = set()
    for value in raw_values:
        if type(value) is not UnitPlacement:
            raise PlacementError(f"{field_name} must contain UnitPlacement values.")
        if value.unit_instance_id in seen_units:
            raise PlacementError("UnitPlacement unit_instance_id must not be placed twice.")
        seen_units.add(value.unit_instance_id)
        for model_id in (placement.model_instance_id for placement in value.model_placements):
            if model_id in seen_models:
                raise PlacementError("ModelPlacement model_instance_id must not be placed twice.")
            seen_models.add(model_id)
        placements.append(value)
    return tuple(sorted(placements, key=lambda placement: placement.unit_instance_id))


def _validate_placed_armies(
    field_name: str,
    values: object,
) -> tuple[PlacedArmy, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise PlacementError(f"{field_name} must not be empty.")
    placed_armies: list[PlacedArmy] = []
    for value in raw_values:
        if type(value) is not PlacedArmy:
            raise PlacementError(f"{field_name} must contain PlacedArmy values.")
        placed_armies.append(value)
    return tuple(sorted(placed_armies, key=lambda placed_army: placed_army.player_id))


def _validate_army_definitions(
    field_name: str,
    values: object,
) -> tuple[ArmyDefinition, ...]:
    if type(values) is not tuple:
        raise PlacementError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    if not raw_values:
        raise PlacementError(f"{field_name} must not be empty.")
    armies: list[ArmyDefinition] = []
    army_ids: set[str] = set()
    player_ids: set[str] = set()
    for value in raw_values:
        if type(value) is not ArmyDefinition:
            raise PlacementError(f"{field_name} must contain ArmyDefinition values.")
        if value.army_id in army_ids:
            raise PlacementError("BattlefieldScenario armies must have unique army IDs.")
        if value.player_id in player_ids:
            raise PlacementError("BattlefieldScenario armies must have unique player IDs.")
        army_ids.add(value.army_id)
        player_ids.add(value.player_id)
        armies.append(value)
    return tuple(sorted(armies, key=lambda army: army.player_id))


def _validate_unique_placed_armies(placed_armies: tuple[PlacedArmy, ...]) -> None:
    army_ids: set[str] = set()
    player_ids: set[str] = set()
    for placed_army in placed_armies:
        if placed_army.army_id in army_ids:
            raise PlacementError("BattlefieldRuntimeState army_id must not be placed twice.")
        if placed_army.player_id in player_ids:
            raise PlacementError("BattlefieldRuntimeState player_id must not be placed twice.")
        army_ids.add(placed_army.army_id)
        player_ids.add(placed_army.player_id)


def _validate_no_duplicate_placed_models(placed_armies: tuple[PlacedArmy, ...]) -> None:
    seen: set[str] = set()
    for placed_army in placed_armies:
        for model_id in placed_army.placed_model_ids():
            if model_id in seen:
                raise PlacementError("ModelPlacement model_instance_id must not be placed twice.")
            seen.add(model_id)


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
    payloads: list[TerrainFeatureDefinitionPayload] = [
        feature.to_payload()
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


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise PlacementError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise PlacementError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise PlacementError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
