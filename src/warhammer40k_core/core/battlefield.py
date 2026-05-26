from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Self, TypedDict

from warhammer40k_core.core.deployment_zones import DeploymentZone, DeploymentZonePayload
from warhammer40k_core.core.objectives import (
    Objective,
    ObjectiveAnchorKind,
    ObjectivePayload,
    PointObjectiveAnchor,
    TerrainObjectiveAnchor,
)
from warhammer40k_core.core.ruleset import RulesetId, RulesetIdPayload


class BattlefieldError(ValueError):
    """Raised when battlefield state violates CORE V2 invariants."""


class SpatialModelStatePayload(TypedDict):
    model_id: str
    player_id: str
    x: float
    y: float
    z: float
    objective_control: int
    is_alive: bool


class SpatialStatePayload(TypedDict):
    model_states: list[SpatialModelStatePayload]
    generation: int


class TerrainLayoutPayload(TypedDict):
    terrain_ids: list[str]
    generation: int


class ObjectiveControlPayload(TypedDict):
    objective_id: str
    controlled_by_player_id: str | None
    scores: list[ObjectiveControlScorePayload]


class ObjectiveControlScorePayload(TypedDict):
    player_id: str
    score: int


class BattlefieldPayload(TypedDict):
    battlefield_id: str
    ruleset_id: RulesetIdPayload
    width: float
    depth: float
    terrain_layout: TerrainLayoutPayload
    objectives: list[ObjectivePayload]
    deployment_zones: list[DeploymentZonePayload]
    spatial_state: SpatialStatePayload


@dataclass(frozen=True, slots=True)
class SpatialModelState:
    model_id: str
    player_id: str
    x: float
    y: float
    z: float = 0.0
    objective_control: int = 1
    is_alive: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _validate_model_id(self.model_id))
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(self, "x", _validate_finite_number("SpatialModelState x", self.x))
        object.__setattr__(self, "y", _validate_finite_number("SpatialModelState y", self.y))
        object.__setattr__(self, "z", _validate_finite_number("SpatialModelState z", self.z))
        object.__setattr__(
            self,
            "objective_control",
            _validate_non_negative_int(
                "SpatialModelState objective_control",
                self.objective_control,
            ),
        )
        if type(self.is_alive) is not bool:
            raise BattlefieldError("SpatialModelState is_alive must be a bool.")

    def stable_identity(self) -> str:
        return f"model:{self.model_id}"

    def with_position(self, x: float, y: float, z: float | None = None) -> Self:
        return type(self)(
            model_id=self.model_id,
            player_id=self.player_id,
            x=x,
            y=y,
            z=self.z if z is None else z,
            objective_control=self.objective_control,
            is_alive=self.is_alive,
        )

    def with_alive_status(self, is_alive: bool) -> Self:
        return type(self)(
            model_id=self.model_id,
            player_id=self.player_id,
            x=self.x,
            y=self.y,
            z=self.z,
            objective_control=self.objective_control,
            is_alive=is_alive,
        )

    def to_payload(self) -> SpatialModelStatePayload:
        return {
            "model_id": self.model_id,
            "player_id": self.player_id,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "objective_control": self.objective_control,
            "is_alive": self.is_alive,
        }

    @classmethod
    def from_payload(cls, payload: SpatialModelStatePayload) -> Self:
        return cls(
            model_id=payload["model_id"],
            player_id=payload["player_id"],
            x=payload["x"],
            y=payload["y"],
            z=payload["z"],
            objective_control=payload["objective_control"],
            is_alive=payload["is_alive"],
        )


@dataclass(frozen=True, slots=True)
class SpatialState:
    model_states: tuple[SpatialModelState, ...] = ()
    generation: int = 0

    def __post_init__(self) -> None:
        if type(self.model_states) is not tuple:
            raise BattlefieldError("SpatialState model_states must be a tuple.")
        model_states = tuple(
            _validate_spatial_model_state("SpatialState model_state", model_state)
            for model_state in self.model_states
        )
        _validate_unique_model_state_ids(model_states)
        object.__setattr__(
            self,
            "model_states",
            tuple(sorted(model_states, key=lambda model_state: model_state.model_id)),
        )
        object.__setattr__(self, "generation", _validate_generation(self.generation))

    @classmethod
    def empty(cls) -> Self:
        return cls()

    def model_ids(self) -> tuple[str, ...]:
        return tuple(model_state.model_id for model_state in self.model_states)

    def model_state(self, model_id: str) -> SpatialModelState:
        requested_model_id = _validate_model_id(model_id)
        for model_state in self.model_states:
            if model_state.model_id == requested_model_id:
                return model_state
        raise BattlefieldError("SpatialState does not contain the requested model_id.")

    def with_model_state(self, model_state: SpatialModelState) -> Self:
        valid_model_state = _validate_spatial_model_state("model_state", model_state)
        if any(existing.model_id == valid_model_state.model_id for existing in self.model_states):
            raise BattlefieldError("SpatialState model_ids must be unique.")
        return type(self)(
            model_states=(*self.model_states, valid_model_state),
            generation=self.generation + 1,
        )

    def with_replaced_model_state(self, model_state: SpatialModelState) -> Self:
        valid_model_state = _validate_spatial_model_state("model_state", model_state)
        found = False
        model_states: list[SpatialModelState] = []
        for existing in self.model_states:
            if existing.model_id == valid_model_state.model_id:
                found = True
                model_states.append(valid_model_state)
                continue
            model_states.append(existing)
        if not found:
            raise BattlefieldError("SpatialState cannot replace a missing model_id.")
        return type(self)(
            model_states=tuple(model_states),
            generation=self.generation + 1,
        )

    def with_model_position(
        self,
        model_id: str,
        x: float,
        y: float,
        z: float | None = None,
    ) -> Self:
        model_state = self.model_state(model_id)
        return self.with_replaced_model_state(model_state.with_position(x=x, y=y, z=z))

    def with_model_alive_status(self, model_id: str, is_alive: bool) -> Self:
        model_state = self.model_state(model_id)
        return self.with_replaced_model_state(model_state.with_alive_status(is_alive))

    def without_model(self, model_id: str) -> Self:
        requested_model_id = _validate_model_id(model_id)
        model_states = tuple(
            model_state
            for model_state in self.model_states
            if model_state.model_id != requested_model_id
        )
        if len(model_states) == len(self.model_states):
            raise BattlefieldError("SpatialState cannot remove a missing model_id.")
        return type(self)(model_states=model_states, generation=self.generation + 1)

    def to_payload(self) -> SpatialStatePayload:
        return {
            "model_states": [model_state.to_payload() for model_state in self.model_states],
            "generation": self.generation,
        }

    @classmethod
    def from_payload(cls, payload: SpatialStatePayload) -> Self:
        return cls(
            model_states=tuple(
                SpatialModelState.from_payload(model_state)
                for model_state in payload["model_states"]
            ),
            generation=payload["generation"],
        )


@dataclass(frozen=True, slots=True)
class TerrainLayout:
    terrain_ids: tuple[str, ...] = ()
    generation: int = 0

    def __post_init__(self) -> None:
        if type(self.terrain_ids) is not tuple:
            raise BattlefieldError("TerrainLayout terrain_ids must be a tuple.")
        terrain_ids = tuple(_validate_terrain_id(terrain_id) for terrain_id in self.terrain_ids)
        _validate_unique_identifiers("TerrainLayout terrain_ids", terrain_ids)
        object.__setattr__(self, "terrain_ids", tuple(sorted(terrain_ids)))
        object.__setattr__(self, "generation", _validate_generation(self.generation))

    @classmethod
    def empty(cls) -> Self:
        return cls()

    def with_terrain_id(self, terrain_id: str) -> Self:
        valid_terrain_id = _validate_terrain_id(terrain_id)
        if valid_terrain_id in self.terrain_ids:
            raise BattlefieldError("TerrainLayout terrain_ids must be unique.")
        return type(self)(
            terrain_ids=(*self.terrain_ids, valid_terrain_id),
            generation=self.generation + 1,
        )

    def without_terrain_id(self, terrain_id: str) -> Self:
        valid_terrain_id = _validate_terrain_id(terrain_id)
        terrain_ids = tuple(
            existing for existing in self.terrain_ids if existing != valid_terrain_id
        )
        if len(terrain_ids) == len(self.terrain_ids):
            raise BattlefieldError("TerrainLayout cannot remove a missing terrain_id.")
        return type(self)(terrain_ids=terrain_ids, generation=self.generation + 1)

    def to_payload(self) -> TerrainLayoutPayload:
        return {"terrain_ids": list(self.terrain_ids), "generation": self.generation}

    @classmethod
    def from_payload(cls, payload: TerrainLayoutPayload) -> Self:
        return cls(terrain_ids=tuple(payload["terrain_ids"]), generation=payload["generation"])


@dataclass(frozen=True, slots=True)
class Battlefield:
    battlefield_id: str
    width: float
    depth: float
    ruleset_id: RulesetId = field(default_factory=RulesetId.warhammer_40000_tenth)
    terrain_layout: TerrainLayout = field(default_factory=TerrainLayout)
    objectives: tuple[Objective, ...] = ()
    deployment_zones: tuple[DeploymentZone, ...] = ()
    spatial_state: SpatialState = field(default_factory=SpatialState)

    def __post_init__(self) -> None:
        object.__setattr__(self, "battlefield_id", _validate_battlefield_id(self.battlefield_id))
        object.__setattr__(
            self,
            "width",
            _validate_positive_number("Battlefield width", self.width),
        )
        object.__setattr__(
            self,
            "depth",
            _validate_positive_number("Battlefield depth", self.depth),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise BattlefieldError("Battlefield ruleset_id must be a RulesetId.")
        if type(self.terrain_layout) is not TerrainLayout:
            raise BattlefieldError("Battlefield terrain_layout must be a TerrainLayout.")
        if type(self.objectives) is not tuple:
            raise BattlefieldError("Battlefield objectives must be a tuple.")
        if type(self.deployment_zones) is not tuple:
            raise BattlefieldError("Battlefield deployment_zones must be a tuple.")
        objectives = tuple(_validate_objective(objective) for objective in self.objectives)
        deployment_zones = tuple(
            _validate_deployment_zone(deployment_zone) for deployment_zone in self.deployment_zones
        )
        _validate_unique_objective_ids(objectives)
        _validate_unique_deployment_zone_ids(deployment_zones)
        _validate_objectives_are_on_battlefield(self, objectives)
        _validate_deployment_zones_are_on_battlefield(self, deployment_zones)
        if type(self.spatial_state) is not SpatialState:
            raise BattlefieldError("Battlefield spatial_state must be a SpatialState.")
        _validate_points_are_on_battlefield(self, self.spatial_state.model_states)
        object.__setattr__(
            self,
            "objectives",
            tuple(sorted(objectives, key=lambda objective: objective.objective_id)),
        )
        object.__setattr__(
            self,
            "deployment_zones",
            tuple(
                sorted(
                    deployment_zones,
                    key=lambda deployment_zone: deployment_zone.deployment_zone_id,
                )
            ),
        )

    def stable_identity(self) -> str:
        return f"battlefield:{self.battlefield_id}"

    def objective(self, objective_id: str) -> Objective:
        requested_objective_id = _validate_objective_id(objective_id)
        for objective in self.objectives:
            if objective.objective_id == requested_objective_id:
                return objective
        raise BattlefieldError("Battlefield does not contain the requested objective_id.")

    def deployment_zone(self, deployment_zone_id: str) -> DeploymentZone:
        requested_deployment_zone_id = _validate_deployment_zone_id(deployment_zone_id)
        for deployment_zone in self.deployment_zones:
            if deployment_zone.deployment_zone_id == requested_deployment_zone_id:
                return deployment_zone
        raise BattlefieldError("Battlefield does not contain the requested deployment_zone_id.")

    def objective_control_scores(self, objective_id: str) -> tuple[tuple[str, int], ...]:
        objective = self.objective(objective_id)
        if objective.anchor.kind is ObjectiveAnchorKind.TERRAIN:
            raise BattlefieldError(
                "Terrain-anchored objective control requires a ruleset/geometry control policy."
            )
        scores: dict[str, int] = {}
        for model_state in self.spatial_state.model_states:
            if not model_state.is_alive:
                continue
            if model_state.objective_control == 0:
                continue
            if not objective.contains_point(model_state.x, model_state.y):
                continue
            scores[model_state.player_id] = (
                scores.get(model_state.player_id, 0) + model_state.objective_control
            )
        return tuple(sorted(scores.items(), key=lambda item: item[0]))

    def controlled_player_for_objective(self, objective_id: str) -> str | None:
        scores = self.objective_control_scores(objective_id)
        if not scores:
            return None
        highest_score = max(score for _player_id, score in scores)
        controlling_players = tuple(
            player_id for player_id, score in scores if score == highest_score
        )
        if len(controlling_players) != 1:
            return None
        return controlling_players[0]

    def objective_control_payloads(self) -> tuple[ObjectiveControlPayload, ...]:
        payloads: list[ObjectiveControlPayload] = []
        for objective in self.objectives:
            scores = self.objective_control_scores(objective.objective_id)
            payloads.append(
                {
                    "objective_id": objective.objective_id,
                    "controlled_by_player_id": self.controlled_player_for_objective(
                        objective.objective_id
                    ),
                    "scores": [
                        {"player_id": player_id, "score": score} for player_id, score in scores
                    ],
                }
            )
        return tuple(payloads)

    def with_spatial_state(self, spatial_state: SpatialState) -> Self:
        valid_spatial_state = _validate_spatial_state("spatial_state", spatial_state)
        if valid_spatial_state.generation <= self.spatial_state.generation:
            raise BattlefieldError("Battlefield spatial_state generation must increase.")
        return type(self)(
            battlefield_id=self.battlefield_id,
            width=self.width,
            depth=self.depth,
            ruleset_id=self.ruleset_id,
            terrain_layout=self.terrain_layout,
            objectives=self.objectives,
            deployment_zones=self.deployment_zones,
            spatial_state=valid_spatial_state,
        )

    def with_model_state(self, model_state: SpatialModelState) -> Self:
        return self.with_spatial_state(self.spatial_state.with_model_state(model_state))

    def with_model_position(
        self,
        model_id: str,
        x: float,
        y: float,
        z: float | None = None,
    ) -> Self:
        return self.with_spatial_state(self.spatial_state.with_model_position(model_id, x, y, z))

    def to_payload(self) -> BattlefieldPayload:
        return {
            "battlefield_id": self.battlefield_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "width": self.width,
            "depth": self.depth,
            "terrain_layout": self.terrain_layout.to_payload(),
            "objectives": [objective.to_payload() for objective in self.objectives],
            "deployment_zones": [
                deployment_zone.to_payload() for deployment_zone in self.deployment_zones
            ],
            "spatial_state": self.spatial_state.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: BattlefieldPayload) -> Self:
        return cls(
            battlefield_id=payload["battlefield_id"],
            ruleset_id=RulesetId.from_payload(payload["ruleset_id"]),
            width=payload["width"],
            depth=payload["depth"],
            terrain_layout=TerrainLayout.from_payload(payload["terrain_layout"]),
            objectives=tuple(
                Objective.from_payload(objective) for objective in payload["objectives"]
            ),
            deployment_zones=tuple(
                DeploymentZone.from_payload(deployment_zone)
                for deployment_zone in payload["deployment_zones"]
            ),
            spatial_state=SpatialState.from_payload(payload["spatial_state"]),
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise BattlefieldError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise BattlefieldError(f"{field_name} must not be empty.")
    return stripped


def _validate_battlefield_id(value: object) -> str:
    identifier = _validate_identifier("Battlefield battlefield_id", value)
    if identifier.startswith("battlefield:"):
        raise BattlefieldError(
            "Battlefield battlefield_id must not include the stable identity prefix."
        )
    return identifier


def _validate_model_id(value: object) -> str:
    identifier = _validate_identifier("model_id", value)
    if identifier.startswith("model:"):
        raise BattlefieldError("model_id must not include the stable identity prefix.")
    return identifier


def _validate_terrain_id(value: object) -> str:
    identifier = _validate_identifier("terrain_id", value)
    if identifier.startswith("terrain:"):
        raise BattlefieldError("terrain_id must not include the stable identity prefix.")
    return identifier


def _validate_objective_id(value: object) -> str:
    identifier = _validate_identifier("objective_id", value)
    if identifier.startswith("objective:"):
        raise BattlefieldError("objective_id must not include the stable identity prefix.")
    return identifier


def _validate_deployment_zone_id(value: object) -> str:
    identifier = _validate_identifier("deployment_zone_id", value)
    if identifier.startswith("deployment-zone:"):
        raise BattlefieldError("deployment_zone_id must not include the stable identity prefix.")
    return identifier


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise BattlefieldError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise BattlefieldError(f"{field_name} must be finite.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise BattlefieldError(f"{field_name} must be greater than 0.")
    return number


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise BattlefieldError(f"{field_name} must be an integer.")
    if value < 0:
        raise BattlefieldError(f"{field_name} must not be negative.")
    return value


def _validate_generation(value: object) -> int:
    return _validate_non_negative_int("generation", value)


def _validate_spatial_model_state(
    field_name: str,
    value: object,
) -> SpatialModelState:
    if type(value) is not SpatialModelState:
        raise BattlefieldError(f"{field_name} must be a SpatialModelState.")
    return value


def _validate_spatial_state(field_name: str, value: object) -> SpatialState:
    if type(value) is not SpatialState:
        raise BattlefieldError(f"{field_name} must be a SpatialState.")
    return value


def _validate_objective(value: object) -> Objective:
    if type(value) is not Objective:
        raise BattlefieldError("Battlefield objectives must contain Objective values.")
    return value


def _validate_deployment_zone(value: object) -> DeploymentZone:
    if type(value) is not DeploymentZone:
        raise BattlefieldError("Battlefield deployment_zones must contain DeploymentZone values.")
    return value


def _validate_objectives_are_on_battlefield(
    battlefield: Battlefield,
    objectives: tuple[Objective, ...],
) -> None:
    terrain_ids = set(battlefield.terrain_layout.terrain_ids)
    for objective in objectives:
        if type(objective.anchor) is PointObjectiveAnchor:
            if objective.anchor.x < 0.0 or objective.anchor.x > battlefield.width:
                raise BattlefieldError("Objective x must be within the battlefield.")
            if objective.anchor.y < 0.0 or objective.anchor.y > battlefield.depth:
                raise BattlefieldError("Objective y must be within the battlefield.")
            continue
        if type(objective.anchor) is TerrainObjectiveAnchor:
            if objective.anchor.terrain_id not in terrain_ids:
                raise BattlefieldError(
                    "Terrain-anchored objective must reference TerrainLayout terrain_ids."
                )
            continue
        raise BattlefieldError("Objective anchor must be supported by Battlefield.")


def _validate_deployment_zones_are_on_battlefield(
    battlefield: Battlefield,
    deployment_zones: tuple[DeploymentZone, ...],
) -> None:
    for deployment_zone in deployment_zones:
        if deployment_zone.min_x < 0.0 or deployment_zone.max_x > battlefield.width:
            raise BattlefieldError("DeploymentZone x bounds must be within the battlefield.")
        if deployment_zone.min_y < 0.0 or deployment_zone.max_y > battlefield.depth:
            raise BattlefieldError("DeploymentZone y bounds must be within the battlefield.")


def _validate_unique_model_state_ids(model_states: tuple[SpatialModelState, ...]) -> None:
    seen: set[str] = set()
    for model_state in model_states:
        if model_state.model_id in seen:
            raise BattlefieldError("SpatialState model_ids must be unique.")
        seen.add(model_state.model_id)


def _validate_unique_identifiers(field_name: str, identifiers: tuple[str, ...]) -> None:
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            raise BattlefieldError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)


def _validate_unique_objective_ids(objectives: tuple[Objective, ...]) -> None:
    _validate_unique_identifiers(
        "Battlefield objective_ids",
        tuple(objective.objective_id for objective in objectives),
    )


def _validate_unique_deployment_zone_ids(
    deployment_zones: tuple[DeploymentZone, ...],
) -> None:
    _validate_unique_identifiers(
        "Battlefield deployment_zone_ids",
        tuple(deployment_zone.deployment_zone_id for deployment_zone in deployment_zones),
    )


def _validate_points_are_on_battlefield(
    battlefield: Battlefield,
    model_states: tuple[SpatialModelState, ...],
) -> None:
    for model_state in model_states:
        if model_state.x < 0.0 or model_state.x > battlefield.width:
            raise BattlefieldError("SpatialModelState x must be within the battlefield.")
        if model_state.y < 0.0 or model_state.y > battlefield.depth:
            raise BattlefieldError("SpatialModelState y must be within the battlefield.")
