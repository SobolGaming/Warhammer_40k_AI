from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE = "select_faction_rule_turn_end_option"

type TurnEndRequestHandler = Callable[["TurnEndRequestContext"], DecisionRequest | None]
type TurnEndResultHandler = Callable[["TurnEndResultContext"], bool]


@dataclass(frozen=True, slots=True)
class TurnEndRequestContext:
    state: GameState
    decisions: DecisionController
    completed_phase: BattlePhase

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("TurnEndRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("TurnEndRequestContext decisions must be DecisionController.")
        object.__setattr__(
            self,
            "completed_phase",
            _battle_phase_from_token(self.completed_phase),
        )
        _validate_turn_end_context(self.state, self.completed_phase)


@dataclass(frozen=True, slots=True)
class TurnEndResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("TurnEndResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError("TurnEndResultContext decisions must be DecisionController.")
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError("TurnEndResultContext request must be DecisionRequest.")
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("TurnEndResultContext result must be DecisionResult.")
        if self.request.decision_type != SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE:
            raise GameLifecycleError("TurnEndResultContext request decision_type drift.")
        current_phase = self.state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("TurnEndResultContext requires a current phase.")
        _validate_turn_end_context(self.state, current_phase)


@dataclass(frozen=True, slots=True)
class TurnEndHookBinding:
    hook_id: str
    source_id: str
    request_handler: TurnEndRequestHandler | None = None
    result_handler: TurnEndResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("TurnEndHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError("TurnEndHookBinding request_handler must be callable.")
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("TurnEndHookBinding result_handler must be callable.")


@dataclass(frozen=True, slots=True)
class TurnEndHookRegistry:
    bindings: tuple[TurnEndHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[TurnEndHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[TurnEndHookBinding, ...]:
        return self.bindings

    def next_request_for(self, context: TurnEndRequestContext) -> DecisionRequest | None:
        if type(context) is not TurnEndRequestContext:
            raise GameLifecycleError("Turn-end request hooks require a context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Turn-end request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            raise GameLifecycleError("Turn-end hooks produced multiple simultaneous requests.")
        if not requests:
            return None
        return requests[0]

    def apply_result(self, context: TurnEndResultContext) -> bool:
        if type(context) is not TurnEndResultContext:
            raise GameLifecycleError("Turn-end result hooks require a context.")
        handled_ids: list[str] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Turn-end result handlers must return bool.")
            if handled:
                handled_ids.append(binding.hook_id)
        if len(handled_ids) > 1:
            raise GameLifecycleError("Turn-end result was handled by multiple hooks.")
        return bool(handled_ids)


def _validate_hook_bindings(value: object) -> tuple[TurnEndHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.TURN_END,
        binding_type=TurnEndHookBinding,
        registry_name="TurnEndHookRegistry",
        invalid_binding_message="TurnEndHookRegistry requires hook bindings.",
    )


def _validate_turn_end_context(state: GameState, completed_phase: BattlePhase) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Turn-end hooks require battle stage.")
    if state.current_battle_phase is not completed_phase:
        raise GameLifecycleError("Turn-end hook phase drift.")


def _battle_phase_from_token(token: object) -> BattlePhase:
    if type(token) is BattlePhase:
        return token
    if type(token) is not str:
        raise GameLifecycleError("Turn-end hook phase must be a BattlePhase token.")
    try:
        return BattlePhase(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported turn-end hook phase: {token}.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
