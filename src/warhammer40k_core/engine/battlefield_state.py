from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.pose import Pose, PosePayload


class PlacementError(ValueError):
    """Raised when battlefield placement violates CORE V2 invariants."""


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
