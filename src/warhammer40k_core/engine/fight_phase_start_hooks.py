from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE = (
    "select_faction_rule_fight_phase_start_option"
)

type FightPhaseStartRequestHandler = Callable[
    ["FightPhaseStartRequestContext"],
    DecisionRequest | None,
]
type FightPhaseStartResultHandler = Callable[
    ["FightPhaseStartResultContext"],
    bool | LifecycleStatus,
]


@dataclass(frozen=True, slots=True)
class FightPhaseStartRequestContext:
    state: GameState
    decisions: DecisionController

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FightPhaseStartRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "FightPhaseStartRequestContext decisions must be DecisionController."
            )
        _validate_fight_phase_start_state(self.state)


@dataclass(frozen=True, slots=True)
class FightPhaseStartResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("FightPhaseStartResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "FightPhaseStartResultContext decisions must be DecisionController."
            )
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "FightPhaseStartResultContext request must be DecisionRequest."
            )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("FightPhaseStartResultContext result must be DecisionResult.")
        if self.request.decision_type != SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE:
            raise GameLifecycleError("FightPhaseStartResultContext request decision_type drift.")
        _validate_fight_phase_start_state(self.state)


@dataclass(frozen=True, slots=True)
class FightPhaseStartHookBinding:
    hook_id: str
    source_id: str
    request_handler: FightPhaseStartRequestHandler | None = None
    result_handler: FightPhaseStartResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("FightPhaseStartHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError("FightPhaseStartHookBinding request_handler must be callable.")
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("FightPhaseStartHookBinding result_handler must be callable.")


@dataclass(frozen=True, slots=True)
class FightPhaseStartHookRegistry:
    bindings: tuple[FightPhaseStartHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[FightPhaseStartHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[FightPhaseStartHookBinding, ...]:
        return self.bindings

    def next_request_for(
        self,
        context: FightPhaseStartRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not FightPhaseStartRequestContext:
            raise GameLifecycleError("Fight-phase start request hooks require context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Fight-phase start request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            raise GameLifecycleError(
                "Fight-phase start hooks produced multiple simultaneous requests."
            )
        if not requests:
            return None
        return requests[0]

    def apply_result(self, context: FightPhaseStartResultContext) -> bool | LifecycleStatus:
        if type(context) is not FightPhaseStartResultContext:
            raise GameLifecycleError("Fight-phase start result hooks require context.")
        handled_results: list[bool | LifecycleStatus] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool and type(handled) is not LifecycleStatus:
                raise GameLifecycleError(
                    "Fight-phase start result handlers must return bool or status."
                )
            if handled:
                handled_results.append(handled)
        if len(handled_results) > 1:
            raise GameLifecycleError("Fight-phase start result was handled by multiple hooks.")
        if not handled_results:
            return False
        return handled_results[0]


def _validate_hook_bindings(value: object) -> tuple[FightPhaseStartHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("FightPhaseStartHookRegistry bindings must be a tuple.")
    bindings: list[FightPhaseStartHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not FightPhaseStartHookBinding:
            raise GameLifecycleError("FightPhaseStartHookRegistry requires hook bindings.")
        if binding.hook_id in seen:
            raise GameLifecycleError("FightPhaseStartHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_fight_phase_start_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Fight-phase start hooks require battle stage.")
    if state.current_battle_phase is not BattlePhase.FIGHT:
        raise GameLifecycleError("Fight-phase start hooks require Fight phase.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Fight-phase start hook {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Fight-phase start hook {field_name} must not be empty.")
    return stripped
