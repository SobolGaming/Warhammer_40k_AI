from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class ShootingEndSurgeGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    unit_instance_id: str
    max_distance_bonus_inches: int
    replay_payload: JsonValue
    decision_effect_payload: JsonValue


type ShootingEndSurgeHandler = Callable[
    ["ShootingEndSurgeContext"],
    tuple["ShootingEndSurgeGrant", ...],
]


@dataclass(frozen=True, slots=True)
class ShootingEndSurgeContext:
    state: GameState
    shooting_unit_instance_id: str
    shooting_player_id: str
    reacting_player_id: str
    trigger_event_id: str
    hit_target_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("ShootingEndSurgeContext state must be a GameState.")
        if self.state.current_battle_phase is not BattlePhase.SHOOTING:
            raise GameLifecycleError("ShootingEndSurgeContext requires the Shooting phase.")
        object.__setattr__(
            self,
            "shooting_unit_instance_id",
            _validate_identifier("shooting_unit_instance_id", self.shooting_unit_instance_id),
        )
        object.__setattr__(
            self,
            "shooting_player_id",
            _validate_identifier("shooting_player_id", self.shooting_player_id),
        )
        object.__setattr__(
            self,
            "reacting_player_id",
            _validate_identifier("reacting_player_id", self.reacting_player_id),
        )
        if self.shooting_player_id == self.reacting_player_id:
            raise GameLifecycleError("ShootingEndSurgeContext requires an opposing player.")
        object.__setattr__(
            self,
            "trigger_event_id",
            _validate_identifier("trigger_event_id", self.trigger_event_id),
        )
        object.__setattr__(
            self,
            "hit_target_unit_instance_ids",
            _validate_identifier_tuple(
                "hit_target_unit_instance_ids",
                self.hit_target_unit_instance_ids,
            ),
        )


@dataclass(frozen=True, slots=True)
class ShootingEndSurgeGrant:
    hook_id: str
    source_id: str
    unit_instance_id: str
    max_distance_bonus_inches: int = 0
    replay_payload: JsonValue = None
    decision_effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "max_distance_bonus_inches",
            _validate_non_negative_int(
                "max_distance_bonus_inches",
                self.max_distance_bonus_inches,
            ),
        )
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))
        object.__setattr__(
            self,
            "decision_effect_payload",
            validate_json_value(self.decision_effect_payload),
        )

    def to_payload(self) -> ShootingEndSurgeGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "unit_instance_id": self.unit_instance_id,
            "max_distance_bonus_inches": self.max_distance_bonus_inches,
            "replay_payload": self.replay_payload,
            "decision_effect_payload": self.decision_effect_payload,
        }


@dataclass(frozen=True, slots=True)
class ShootingEndSurgeHookBinding:
    hook_id: str
    source_id: str
    handler: ShootingEndSurgeHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("ShootingEndSurgeHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class ShootingEndSurgeHookRegistry:
    bindings: tuple[ShootingEndSurgeHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[ShootingEndSurgeHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[ShootingEndSurgeHookBinding, ...]:
        return self.bindings

    def grants_for(self, context: ShootingEndSurgeContext) -> tuple[ShootingEndSurgeGrant, ...]:
        if type(context) is not ShootingEndSurgeContext:
            raise GameLifecycleError("Shooting-end surge hooks require a context.")
        grants: list[ShootingEndSurgeGrant] = []
        for binding in self.bindings:
            handler_grants = binding.handler(context)
            if type(handler_grants) is not tuple:
                raise GameLifecycleError("Shooting-end surge handlers must return a tuple.")
            for grant in handler_grants:
                if type(grant) is not ShootingEndSurgeGrant:
                    raise GameLifecycleError(
                        "Shooting-end surge handlers must return ShootingEndSurgeGrant values."
                    )
                if grant.hook_id != binding.hook_id:
                    raise GameLifecycleError("Shooting-end surge handler returned hook_id drift.")
                if grant.source_id != binding.source_id:
                    raise GameLifecycleError("Shooting-end surge handler returned source_id drift.")
                grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: (grant.hook_id, grant.unit_instance_id)))


def _validate_hook_bindings(value: object) -> tuple[ShootingEndSurgeHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("ShootingEndSurgeHookRegistry bindings must be a tuple.")
    bindings: list[ShootingEndSurgeHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not ShootingEndSurgeHookBinding:
            raise GameLifecycleError(
                "ShootingEndSurgeHookRegistry bindings must contain "
                "ShootingEndSurgeHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("ShootingEndSurgeHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Shooting-end surge hook {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for raw_value in cast(tuple[object, ...], values):
        value = _validate_identifier(field_name, raw_value)
        if value in seen:
            raise GameLifecycleError(
                f"Shooting-end surge hook {field_name} must not contain duplicates."
            )
        seen.add(value)
        identifiers.append(value)
    return tuple(sorted(identifiers))


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Shooting-end surge hook {field_name} must be an int.")
    if value < 0:
        raise GameLifecycleError(f"Shooting-end surge hook {field_name} must not be negative.")
    return value
