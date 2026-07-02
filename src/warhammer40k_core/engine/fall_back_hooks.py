from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class FallBackEligibilityGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    can_shoot: bool
    can_declare_charge: bool
    replay_payload: JsonValue


type FallBackEligibilityHandler = Callable[
    ["FallBackEligibilityContext"],
    "FallBackEligibilityGrant | None",
]


@dataclass(frozen=True, slots=True)
class FallBackEligibilityContext:
    state: GameState
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_request_id: str
    movement_result_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FallBackEligibilityContext state must be a GameState.")
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "movement_request_id",
            _validate_identifier("movement_request_id", self.movement_request_id),
        )
        object.__setattr__(
            self,
            "movement_result_id",
            _validate_identifier("movement_result_id", self.movement_result_id),
        )


@dataclass(frozen=True, slots=True)
class FallBackEligibilityGrant:
    hook_id: str
    source_id: str
    can_shoot: bool
    can_declare_charge: bool
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(
            self,
            "can_shoot",
            _validate_bool("can_shoot", self.can_shoot),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("can_declare_charge", self.can_declare_charge),
        )
        if not self.can_shoot and not self.can_declare_charge:
            raise GameLifecycleError("FallBackEligibilityGrant must grant at least one permission.")
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> FallBackEligibilityGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "can_shoot": self.can_shoot,
            "can_declare_charge": self.can_declare_charge,
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class FallBackEligibilityHookBinding:
    hook_id: str
    source_id: str
    handler: FallBackEligibilityHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("FallBackEligibilityHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class FallBackEligibilityHookRegistry:
    bindings: tuple[FallBackEligibilityHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[FallBackEligibilityHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[FallBackEligibilityHookBinding, ...]:
        return self.bindings

    def grants_for(
        self,
        context: FallBackEligibilityContext,
    ) -> tuple[FallBackEligibilityGrant, ...]:
        if type(context) is not FallBackEligibilityContext:
            raise GameLifecycleError("Fall Back eligibility hooks require a context.")
        grants: list[FallBackEligibilityGrant] = []
        for binding in self.bindings:
            grant = binding.handler(context)
            if grant is None:
                continue
            if type(grant) is not FallBackEligibilityGrant:
                raise GameLifecycleError(
                    "Fall Back eligibility handlers must return grants or None."
                )
            if grant.hook_id != binding.hook_id:
                raise GameLifecycleError("Fall Back eligibility handler returned hook_id drift.")
            if grant.source_id != binding.source_id:
                raise GameLifecycleError("Fall Back eligibility handler returned source_id drift.")
            grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_hook_bindings(value: object) -> tuple[FallBackEligibilityHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("FallBackEligibilityHookRegistry bindings must be a tuple.")
    bindings: list[FallBackEligibilityHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not FallBackEligibilityHookBinding:
            raise GameLifecycleError(
                "FallBackEligibilityHookRegistry bindings must contain "
                "FallBackEligibilityHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("FallBackEligibilityHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"Fall Back eligibility hook {field_name} must be a bool.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Fall Back eligibility hook {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(
            f"Fall Back eligibility hook {field_name} must be greater than zero."
        )
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)
