from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.shooting_types import ShootingType, shooting_type_from_token

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class TargetRestrictionPayload(TypedDict):
    hook_id: str
    source_id: str
    violation_code: str
    message: str
    replay_payload: JsonValue


@dataclass(frozen=True, slots=True)
class ShootingTargetRestrictionContext:
    state: GameState
    player_id: str
    battle_round: int
    attacking_unit_instance_id: str
    target_unit_instance_id: str
    attacker_model_instance_id: str | None = None
    shooting_type: ShootingType | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("ShootingTargetRestrictionContext state must be GameState.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_optional_identifier(
                "attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "shooting_type",
            _validate_optional_shooting_type(self.shooting_type),
        )


@dataclass(frozen=True, slots=True)
class ChargeTargetRestrictionContext:
    state: GameState
    player_id: str
    battle_round: int
    charging_unit_instance_id: str
    target_unit_instance_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("ChargeTargetRestrictionContext state must be GameState.")
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "charging_unit_instance_id",
            _validate_identifier("charging_unit_instance_id", self.charging_unit_instance_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier("target_unit_instance_id", self.target_unit_instance_id),
        )


@dataclass(frozen=True, slots=True)
class TargetRestriction:
    hook_id: str
    source_id: str
    violation_code: str
    message: str
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("violation_code", self.violation_code),
        )
        object.__setattr__(self, "message", _validate_message(self.message))
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> TargetRestrictionPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "violation_code": self.violation_code,
            "message": self.message,
            "replay_payload": self.replay_payload,
        }


type ShootingTargetRestrictionHandler = Callable[
    [ShootingTargetRestrictionContext],
    TargetRestriction | None,
]
type ChargeTargetRestrictionHandler = Callable[
    [ChargeTargetRestrictionContext],
    TargetRestriction | None,
]


@dataclass(frozen=True, slots=True)
class ShootingTargetRestrictionHookBinding:
    hook_id: str
    source_id: str
    handler: ShootingTargetRestrictionHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError(
                "ShootingTargetRestrictionHookBinding handler must be callable."
            )


@dataclass(frozen=True, slots=True)
class ChargeTargetRestrictionHookBinding:
    hook_id: str
    source_id: str
    handler: ChargeTargetRestrictionHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("ChargeTargetRestrictionHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class ShootingTargetRestrictionHookRegistry:
    bindings: tuple[ShootingTargetRestrictionHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "bindings",
            _validate_shooting_target_restriction_bindings(self.bindings),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(
        cls,
        bindings: tuple[ShootingTargetRestrictionHookBinding, ...],
    ) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[ShootingTargetRestrictionHookBinding, ...]:
        return self.bindings

    def restrictions_for(
        self,
        context: ShootingTargetRestrictionContext,
    ) -> tuple[TargetRestriction, ...]:
        if type(context) is not ShootingTargetRestrictionContext:
            raise GameLifecycleError("Shooting target restriction hooks require a context.")
        restrictions: list[TargetRestriction] = []
        for binding in self.bindings:
            restriction = binding.handler(context)
            if restriction is None:
                continue
            _validate_restriction_for_binding(
                restriction=restriction,
                hook_id=binding.hook_id,
                source_id=binding.source_id,
                context_name="Shooting target restriction",
            )
            restrictions.append(restriction)
        return tuple(sorted(restrictions, key=lambda restriction: restriction.hook_id))


@dataclass(frozen=True, slots=True)
class ChargeTargetRestrictionHookRegistry:
    bindings: tuple[ChargeTargetRestrictionHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "bindings",
            _validate_charge_target_restriction_bindings(self.bindings),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[ChargeTargetRestrictionHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[ChargeTargetRestrictionHookBinding, ...]:
        return self.bindings

    def restrictions_for(
        self,
        context: ChargeTargetRestrictionContext,
    ) -> tuple[TargetRestriction, ...]:
        if type(context) is not ChargeTargetRestrictionContext:
            raise GameLifecycleError("Charge target restriction hooks require a context.")
        restrictions: list[TargetRestriction] = []
        for binding in self.bindings:
            restriction = binding.handler(context)
            if restriction is None:
                continue
            _validate_restriction_for_binding(
                restriction=restriction,
                hook_id=binding.hook_id,
                source_id=binding.source_id,
                context_name="Charge target restriction",
            )
            restrictions.append(restriction)
        return tuple(sorted(restrictions, key=lambda restriction: restriction.hook_id))


def _validate_restriction_for_binding(
    *,
    restriction: object,
    hook_id: str,
    source_id: str,
    context_name: str,
) -> None:
    if type(restriction) is not TargetRestriction:
        raise GameLifecycleError(f"{context_name} handlers must return restrictions or None.")
    if restriction.hook_id != hook_id:
        raise GameLifecycleError(f"{context_name} handler returned hook_id drift.")
    if restriction.source_id != source_id:
        raise GameLifecycleError(f"{context_name} handler returned source_id drift.")


def _validate_shooting_target_restriction_bindings(
    value: object,
) -> tuple[ShootingTargetRestrictionHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("ShootingTargetRestrictionHookRegistry bindings must be a tuple.")
    bindings: list[ShootingTargetRestrictionHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not ShootingTargetRestrictionHookBinding:
            raise GameLifecycleError(
                "ShootingTargetRestrictionHookRegistry bindings contain invalid values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError(
                "ShootingTargetRestrictionHookRegistry hook IDs must be unique."
            )
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_charge_target_restriction_bindings(
    value: object,
) -> tuple[ChargeTargetRestrictionHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("ChargeTargetRestrictionHookRegistry bindings must be a tuple.")
    bindings: list[ChargeTargetRestrictionHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not ChargeTargetRestrictionHookBinding:
            raise GameLifecycleError(
                "ChargeTargetRestrictionHookRegistry bindings contain invalid values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("ChargeTargetRestrictionHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Target restriction hook {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"Target restriction hook {field_name} must be greater than zero.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Target restriction hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Target restriction hook {field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_optional_shooting_type(value: object) -> ShootingType | None:
    if value is None:
        return None
    return shooting_type_from_token(value)


def _validate_message(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Target restriction hook message must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("Target restriction hook message must not be empty.")
    return stripped
