from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    UnitPlacement,
    battlefield_placement_kind_from_token,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class ReserveArrivalDistanceGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    enemy_horizontal_distance_inches: float
    replay_payload: JsonValue


type ReserveArrivalDistanceHandler = Callable[
    ["ReserveArrivalDistanceContext"],
    tuple["ReserveArrivalDistanceGrant", ...],
]


@dataclass(frozen=True, slots=True)
class ReserveArrivalDistanceContext:
    state: GameState
    scenario: BattlefieldScenario
    ruleset_descriptor: RulesetDescriptor
    reserve_state: ReserveState
    unit: UnitInstance
    attempted_placement: UnitPlacement
    placement_kind: BattlefieldPlacementKind
    battle_round: int
    battlefield_width_inches: float
    battlefield_depth_inches: float
    terrain_features: tuple[TerrainFeatureDefinition, ...]
    objective_markers: tuple[ObjectiveMarker, ...]
    enemy_deployment_zones: tuple[DeploymentZone, ...]
    base_enemy_horizontal_distance_inches: float

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("ReserveArrivalDistanceContext state must be a GameState.")
        if type(self.scenario) is not BattlefieldScenario:
            raise GameLifecycleError("ReserveArrivalDistanceContext scenario must be a scenario.")
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError(
                "ReserveArrivalDistanceContext ruleset_descriptor must be a RulesetDescriptor."
            )
        if type(self.reserve_state) is not ReserveState:
            raise GameLifecycleError(
                "ReserveArrivalDistanceContext reserve_state must be a ReserveState."
            )
        if type(self.unit) is not UnitInstance:
            raise GameLifecycleError("ReserveArrivalDistanceContext unit must be a UnitInstance.")
        if self.unit.unit_instance_id != self.reserve_state.unit_instance_id:
            raise GameLifecycleError("ReserveArrivalDistanceContext unit drift.")
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "ReserveArrivalDistanceContext attempted_placement must be a UnitPlacement."
            )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "terrain_features",
            _validate_tuple(
                "terrain_features",
                self.terrain_features,
                TerrainFeatureDefinition,
            ),
        )
        object.__setattr__(
            self,
            "objective_markers",
            _validate_tuple("objective_markers", self.objective_markers, ObjectiveMarker),
        )
        object.__setattr__(
            self,
            "enemy_deployment_zones",
            _validate_tuple(
                "enemy_deployment_zones",
                self.enemy_deployment_zones,
                DeploymentZone,
            ),
        )
        object.__setattr__(
            self,
            "base_enemy_horizontal_distance_inches",
            _validate_positive_number(
                "base_enemy_horizontal_distance_inches",
                self.base_enemy_horizontal_distance_inches,
            ),
        )


@dataclass(frozen=True, slots=True)
class ReserveArrivalDistanceGrant:
    hook_id: str
    source_id: str
    enemy_horizontal_distance_inches: float
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "enemy_horizontal_distance_inches",
            _validate_positive_number(
                "enemy_horizontal_distance_inches",
                self.enemy_horizontal_distance_inches,
            ),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> ReserveArrivalDistanceGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "enemy_horizontal_distance_inches": self.enemy_horizontal_distance_inches,
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class ReserveArrivalDistanceHookBinding:
    hook_id: str
    source_id: str
    handler: ReserveArrivalDistanceHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("ReserveArrivalDistanceHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class ReserveArrivalDistanceHookRegistry:
    bindings: tuple[ReserveArrivalDistanceHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(
        cls,
        bindings: tuple[ReserveArrivalDistanceHookBinding, ...],
    ) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[ReserveArrivalDistanceHookBinding, ...]:
        return self.bindings

    def grants_for(
        self,
        context: ReserveArrivalDistanceContext,
    ) -> tuple[ReserveArrivalDistanceGrant, ...]:
        if type(context) is not ReserveArrivalDistanceContext:
            raise GameLifecycleError("Reserve arrival distance hooks require a context.")
        grants: list[ReserveArrivalDistanceGrant] = []
        for binding in self.bindings:
            returned_grants = binding.handler(context)
            if type(returned_grants) is not tuple:
                raise GameLifecycleError(
                    "Reserve arrival distance handlers must return a tuple of grants."
                )
            for grant in returned_grants:
                if type(grant) is not ReserveArrivalDistanceGrant:
                    raise GameLifecycleError(
                        "Reserve arrival distance handlers must return distance grants."
                    )
                if grant.hook_id != binding.hook_id:
                    raise GameLifecycleError(
                        "Reserve arrival distance handler returned hook_id drift."
                    )
                if grant.source_id != binding.source_id:
                    raise GameLifecycleError(
                        "Reserve arrival distance handler returned source_id drift."
                    )
                if (
                    grant.enemy_horizontal_distance_inches
                    > context.base_enemy_horizontal_distance_inches
                ):
                    raise GameLifecycleError(
                        "Reserve arrival distance grants must not increase the base distance."
                    )
                grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: grant.hook_id))

    def effective_enemy_horizontal_distance_inches(
        self,
        context: ReserveArrivalDistanceContext,
    ) -> float:
        distances = [
            context.base_enemy_horizontal_distance_inches,
            *(grant.enemy_horizontal_distance_inches for grant in self.grants_for(context)),
        ]
        return min(distances)


def _validate_hook_bindings(
    value: object,
) -> tuple[ReserveArrivalDistanceHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("ReserveArrivalDistanceHookRegistry bindings must be a tuple.")
    bindings: list[ReserveArrivalDistanceHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not ReserveArrivalDistanceHookBinding:
            raise GameLifecycleError(
                "ReserveArrivalDistanceHookRegistry bindings must contain "
                "ReserveArrivalDistanceHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("ReserveArrivalDistanceHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_tuple[T](
    field_name: str,
    value: object,
    expected_type: type[T],
) -> tuple[T, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"Reserve arrival distance hook {field_name} must be a tuple.")
    validated: list[T] = []
    for item in cast(tuple[object, ...], value):
        if type(item) is not expected_type:
            raise GameLifecycleError(
                f"Reserve arrival distance hook {field_name} contains invalid values."
            )
        validated.append(item)
    return tuple(validated)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Reserve arrival distance hook {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(
            f"Reserve arrival distance hook {field_name} must be greater than zero."
        )
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"Reserve arrival distance hook {field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise GameLifecycleError(
            f"Reserve arrival distance hook {field_name} must be greater than zero."
        )
    return number


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Reserve arrival distance hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Reserve arrival distance hook {field_name} must not be empty.")
    return stripped
