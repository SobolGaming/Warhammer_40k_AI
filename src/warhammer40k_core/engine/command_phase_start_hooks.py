from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


type CommandPhaseStartHandler = Callable[["CommandPhaseStartContext"], None]


@dataclass(frozen=True, slots=True)
class CommandPhaseStartContext:
    state: GameState
    decisions: DecisionController
    active_player_id: str

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("CommandPhaseStartContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "CommandPhaseStartContext decisions must be DecisionController."
            )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("active_player_id", self.active_player_id),
        )
        if self.state.current_battle_phase is not BattlePhase.COMMAND:
            raise GameLifecycleError("Command-phase start hooks require Command phase.")
        if self.state.active_player_id != self.active_player_id:
            raise GameLifecycleError("Command-phase start hook active player drift.")


@dataclass(frozen=True, slots=True)
class CommandPhaseStartHookBinding:
    hook_id: str
    source_id: str
    handler: CommandPhaseStartHandler

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if not callable(self.handler):
            raise GameLifecycleError("CommandPhaseStartHookBinding handler must be callable.")


@dataclass(frozen=True, slots=True)
class CommandPhaseStartHookRegistry:
    bindings: tuple[CommandPhaseStartHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[CommandPhaseStartHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[CommandPhaseStartHookBinding, ...]:
        return self.bindings

    def resolve(self, context: CommandPhaseStartContext) -> None:
        if type(context) is not CommandPhaseStartContext:
            raise GameLifecycleError("Command-phase start hooks require context.")
        for binding in self.bindings:
            binding.handler(context)


def _validate_bindings(value: object) -> tuple[CommandPhaseStartHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("CommandPhaseStartHookRegistry bindings must be a tuple.")
    bindings: list[CommandPhaseStartHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not CommandPhaseStartHookBinding:
            raise GameLifecycleError(
                "CommandPhaseStartHookRegistry bindings must contain hook bindings."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("CommandPhaseStartHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda item: item.hook_id))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Command-phase start hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Command-phase start hook {field_name} must not be empty.")
    return stripped
