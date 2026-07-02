from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type UnitDestroyedHandler = Callable[["UnitDestroyedContext"], None]


@dataclass(frozen=True, slots=True)
class UnitDestroyedContext:
    state: GameState
    decisions: DecisionController
    completed_phase: BattlePhase
    model_destroyed_event_id: str
    model_destroyed_payload: dict[str, JsonValue]
    destroying_player_id: str
    destroyed_unit_instance_id: str
    destroyed_player_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("UnitDestroyedContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("UnitDestroyedContext decisions must be DecisionController.")
        object.__setattr__(self, "completed_phase", _battle_phase_from_token(self.completed_phase))
        object.__setattr__(
            self,
            "model_destroyed_event_id",
            _validate_identifier("model_destroyed_event_id", self.model_destroyed_event_id),
        )
        payload = validate_json_value(self.model_destroyed_payload)
        if not isinstance(payload, dict):
            raise GameLifecycleError("UnitDestroyedContext model_destroyed_payload must be object.")
        object.__setattr__(self, "model_destroyed_payload", payload)
        object.__setattr__(
            self,
            "destroying_player_id",
            _validate_identifier("destroying_player_id", self.destroying_player_id),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_id",
            _validate_identifier("destroyed_unit_instance_id", self.destroyed_unit_instance_id),
        )
        object.__setattr__(
            self,
            "destroyed_player_id",
            _validate_identifier("destroyed_player_id", self.destroyed_player_id),
        )
        if self.destroying_player_id == self.destroyed_player_id:
            raise GameLifecycleError("UnitDestroyedContext requires enemy destruction.")


@dataclass(frozen=True, slots=True)
class UnitDestroyedHookBinding:
    hook_id: str
    source_id: str
    handler: UnitDestroyedHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("UnitDestroyedHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class UnitDestroyedHookRegistry:
    bindings: tuple[UnitDestroyedHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[UnitDestroyedHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[UnitDestroyedHookBinding, ...]:
        return self.bindings

    def resolve(self, context: UnitDestroyedContext) -> None:
        if type(context) is not UnitDestroyedContext:
            raise GameLifecycleError("Unit-destroyed hooks require context.")
        for binding in self.bindings:
            binding.handler(context)


def _validate_bindings(value: object) -> tuple[UnitDestroyedHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("UnitDestroyedHookRegistry bindings must be a tuple.")
    bindings: list[UnitDestroyedHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not UnitDestroyedHookBinding:
            raise GameLifecycleError("UnitDestroyedHookRegistry requires hook bindings.")
        if binding.hook_id in seen:
            raise GameLifecycleError("UnitDestroyedHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda item: item.hook_id))


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Unit-destroyed hook phase must be BattlePhase.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported unit-destroyed hook phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
