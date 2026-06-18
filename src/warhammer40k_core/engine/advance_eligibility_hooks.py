from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


class AdvanceEligibilityGrantPayload(TypedDict):
    hook_id: str
    source_id: str
    can_shoot: bool
    can_declare_charge: bool
    replay_payload: JsonValue


type AdvanceEligibilityHandler = Callable[
    ["AdvanceEligibilityContext"],
    "AdvanceEligibilityGrant | None",
]


@dataclass(frozen=True, slots=True)
class AdvanceEligibilityContext:
    state: GameState
    player_id: str
    battle_round: int
    unit_instance_id: str
    movement_request_id: str
    movement_result_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("AdvanceEligibilityContext state must be a GameState.")
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
class AdvanceEligibilityGrant:
    hook_id: str
    source_id: str
    can_shoot: bool
    can_declare_charge: bool
    replay_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        object.__setattr__(self, "can_shoot", _validate_bool("can_shoot", self.can_shoot))
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("can_declare_charge", self.can_declare_charge),
        )
        if not self.can_shoot and not self.can_declare_charge:
            raise GameLifecycleError("AdvanceEligibilityGrant must grant at least one permission.")
        object.__setattr__(self, "replay_payload", validate_json_value(self.replay_payload))

    def to_payload(self) -> AdvanceEligibilityGrantPayload:
        return {
            "hook_id": self.hook_id,
            "source_id": self.source_id,
            "can_shoot": self.can_shoot,
            "can_declare_charge": self.can_declare_charge,
            "replay_payload": self.replay_payload,
        }


@dataclass(frozen=True, slots=True)
class AdvanceEligibilityHookBinding:
    hook_id: str
    source_id: str
    handler: AdvanceEligibilityHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("AdvanceEligibilityHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class AdvanceEligibilityHookRegistry:
    bindings: tuple[AdvanceEligibilityHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[AdvanceEligibilityHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[AdvanceEligibilityHookBinding, ...]:
        return self.bindings

    def grants_for(
        self,
        context: AdvanceEligibilityContext,
    ) -> tuple[AdvanceEligibilityGrant, ...]:
        if type(context) is not AdvanceEligibilityContext:
            raise GameLifecycleError("Advance eligibility hooks require a context.")
        grants: list[AdvanceEligibilityGrant] = []
        for binding in self.bindings:
            grant = binding.handler(context)
            if grant is None:
                continue
            if type(grant) is not AdvanceEligibilityGrant:
                raise GameLifecycleError("Advance eligibility handlers must return grants or None.")
            if grant.hook_id != binding.hook_id:
                raise GameLifecycleError("Advance eligibility handler returned hook_id drift.")
            if grant.source_id != binding.source_id:
                raise GameLifecycleError("Advance eligibility handler returned source_id drift.")
            grants.append(grant)
        return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_hook_bindings(value: object) -> tuple[AdvanceEligibilityHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("AdvanceEligibilityHookRegistry bindings must be a tuple.")
    bindings: list[AdvanceEligibilityHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not AdvanceEligibilityHookBinding:
            raise GameLifecycleError(
                "AdvanceEligibilityHookRegistry bindings must contain "
                "AdvanceEligibilityHookBinding values."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("AdvanceEligibilityHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"Advance eligibility hook {field_name} must be a bool.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"Advance eligibility hook {field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(
            f"Advance eligibility hook {field_name} must be greater than zero."
        )
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Advance eligibility hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Advance eligibility hook {field_name} must not be empty.")
    return stripped
