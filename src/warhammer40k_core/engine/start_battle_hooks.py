from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameConfig, GameState


type StartBattleRequestHandler = Callable[["StartBattleRequestContext"], DecisionRequest | None]
type StartBattleResultHandler = Callable[["StartBattleResultContext"], bool]


@dataclass(frozen=True, slots=True)
class StartBattleRequestContext:
    state: GameState
    decisions: DecisionController
    config: GameConfig
    authoritative_request_id: str | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameConfig, GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("StartBattleRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "StartBattleRequestContext decisions must be DecisionController."
            )
        if type(self.config) is not GameConfig:
            raise GameLifecycleError("StartBattleRequestContext config must be GameConfig.")
        if self.authoritative_request_id is not None:
            object.__setattr__(
                self,
                "authoritative_request_id",
                _validate_identifier(
                    "authoritative_request_id",
                    self.authoritative_request_id,
                ),
            )
        _validate_start_battle_boundary(self.state)

    def issue_request_id(self) -> str:
        if self.authoritative_request_id is not None:
            return self.authoritative_request_id
        return self.state.next_decision_request_id()


@dataclass(frozen=True, slots=True)
class StartBattleResultContext:
    state: GameState
    decisions: DecisionController
    config: GameConfig
    request: DecisionRequest
    result: DecisionResult

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameConfig, GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("StartBattleResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "StartBattleResultContext decisions must be DecisionController."
            )
        if type(self.config) is not GameConfig:
            raise GameLifecycleError("StartBattleResultContext config must be GameConfig.")
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError("StartBattleResultContext request must be DecisionRequest.")
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("StartBattleResultContext result must be DecisionResult.")
        _validate_start_battle_boundary(self.state)


@dataclass(frozen=True, slots=True)
class StartBattleHookBinding:
    hook_id: str
    source_id: str
    request_handler: StartBattleRequestHandler | None = None
    result_handler: StartBattleResultHandler | None = None
    request_priority: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("StartBattleHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError("StartBattleHookBinding request_handler must be callable.")
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("StartBattleHookBinding result_handler must be callable.")
        if type(self.request_priority) is not int or self.request_priority < 0:
            raise GameLifecycleError(
                "StartBattleHookBinding request_priority must be a non-negative int."
            )


@dataclass(frozen=True, slots=True)
class StartBattleHookRegistry:
    bindings: tuple[StartBattleHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[StartBattleHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[StartBattleHookBinding, ...]:
        return self.bindings

    def next_request_for(self, context: StartBattleRequestContext) -> DecisionRequest | None:
        if type(context) is not StartBattleRequestContext:
            raise GameLifecycleError("Start-battle request hooks require a context.")
        requests: list[tuple[int, DecisionRequest]] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Start-battle request handlers must return DecisionRequest or None."
                )
            requests.append((binding.request_priority, request))
        if not requests:
            return None
        selected_priority = min(priority for priority, _request in requests)
        selected_requests = [
            request for priority, request in requests if priority == selected_priority
        ]
        if len(selected_requests) > 1:
            raise GameLifecycleError(
                "Start-battle hooks produced multiple simultaneous requests at the same priority."
            )
        return selected_requests[0]

    def validate_pending_request(
        self,
        *,
        context: StartBattleRequestContext,
        request: DecisionRequest,
    ) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(context) is not StartBattleRequestContext or type(request) is not DecisionRequest:
            raise GameLifecycleError(
                "Start-battle pending request validation requires typed inputs."
            )
        authoritative_request = self.next_request_for(
            StartBattleRequestContext(
                state=GameState.from_payload(context.state.to_payload()),
                decisions=DecisionController.from_payload(context.decisions.to_payload()),
                config=context.config,
                authoritative_request_id=request.request_id,
            )
        )
        if authoritative_request is None:
            raise GameLifecycleError("Start-battle pending request has no authoritative source.")
        if request != authoritative_request:
            raise GameLifecycleError("Start-battle pending request drifted.")

    def apply_result(self, context: StartBattleResultContext) -> bool:
        if type(context) is not StartBattleResultContext:
            raise GameLifecycleError("Start-battle result hooks require a context.")
        handled_ids: list[str] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Start-battle result handlers must return bool.")
            if handled:
                handled_ids.append(binding.hook_id)
        if len(handled_ids) > 1:
            raise GameLifecycleError("Start-battle result was handled by multiple hooks.")
        return bool(handled_ids)


def _validate_hook_bindings(value: object) -> tuple[StartBattleHookBinding, ...]:
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.START_BATTLE,
        binding_type=StartBattleHookBinding,
        registry_name="StartBattleHookRegistry",
        invalid_binding_message=(
            "StartBattleHookRegistry bindings must contain StartBattleHookBinding."
        ),
    )


def _validate_start_battle_boundary(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Start-battle hooks require setup stage.")
    if state.setup_step_index is None or state.setup_step_index + 1 != len(state.setup_sequence):
        raise GameLifecycleError("Start-battle hooks require the final setup boundary.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
