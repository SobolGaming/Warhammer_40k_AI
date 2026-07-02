from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, SetupStep

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameConfig, GameState


SELECT_FACTION_RULE_SETUP_OPTION_DECISION_TYPE = "select_faction_rule_setup_option"


type BattleFormationRequestHandler = Callable[
    ["BattleFormationRequestContext"],
    DecisionRequest | None,
]
type BattleFormationResultHandler = Callable[
    ["BattleFormationResultContext"],
    bool,
]


@dataclass(frozen=True, slots=True)
class BattleFormationRequestContext:
    state: GameState
    decisions: DecisionController
    config: GameConfig

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameConfig, GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleFormationRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleFormationRequestContext decisions must be DecisionController."
            )
        if type(self.config) is not GameConfig:
            raise GameLifecycleError("BattleFormationRequestContext config must be GameConfig.")
        _validate_declare_battle_formations_step(self.state)


@dataclass(frozen=True, slots=True)
class BattleFormationResultContext:
    state: GameState
    decisions: DecisionController
    config: GameConfig
    request: DecisionRequest
    result: DecisionResult

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameConfig, GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleFormationResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleFormationResultContext decisions must be DecisionController."
            )
        if type(self.config) is not GameConfig:
            raise GameLifecycleError("BattleFormationResultContext config must be GameConfig.")
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "BattleFormationResultContext request must be DecisionRequest."
            )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("BattleFormationResultContext result must be DecisionResult.")
        _validate_declare_battle_formations_step(self.state)


@dataclass(frozen=True, slots=True)
class BattleFormationHookBinding:
    hook_id: str
    source_id: str
    request_handler: BattleFormationRequestHandler | None = None
    result_handler: BattleFormationResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("BattleFormationHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError("BattleFormationHookBinding request_handler must be callable.")
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("BattleFormationHookBinding result_handler must be callable.")


@dataclass(frozen=True, slots=True)
class BattleFormationHookRegistry:
    bindings: tuple[BattleFormationHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[BattleFormationHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[BattleFormationHookBinding, ...]:
        return self.bindings

    def next_request_for(
        self,
        context: BattleFormationRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not BattleFormationRequestContext:
            raise GameLifecycleError("Battle formation request hooks require a context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Battle formation request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            raise GameLifecycleError(
                "Battle formation hooks produced multiple simultaneous requests."
            )
        if not requests:
            return None
        return requests[0]

    def apply_result(
        self,
        context: BattleFormationResultContext,
    ) -> bool:
        if type(context) is not BattleFormationResultContext:
            raise GameLifecycleError("Battle formation result hooks require a context.")
        handled_ids: list[str] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Battle formation result handlers must return bool.")
            if handled:
                handled_ids.append(binding.hook_id)
        if len(handled_ids) > 1:
            raise GameLifecycleError("Battle formation result was handled by multiple hooks.")
        return bool(handled_ids)


def _validate_hook_bindings(value: object) -> tuple[BattleFormationHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("BattleFormationHookRegistry bindings must be a tuple.")
    bindings: list[BattleFormationHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not BattleFormationHookBinding:
            raise GameLifecycleError(
                "BattleFormationHookRegistry bindings must contain BattleFormationHookBinding."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("BattleFormationHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_declare_battle_formations_step(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.SETUP:
        raise GameLifecycleError("Battle formation hooks require setup stage.")
    if state.current_setup_step is not SetupStep.DECLARE_BATTLE_FORMATIONS:
        raise GameLifecycleError("Battle formation hooks require DECLARE_BATTLE_FORMATIONS.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
