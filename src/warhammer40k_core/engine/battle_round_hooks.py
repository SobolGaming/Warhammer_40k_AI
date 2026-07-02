from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_FACTION_RULE_BATTLE_ROUND_OPTION_DECISION_TYPE = "select_faction_rule_battle_round_option"


type BattleRoundStartRequestHandler = Callable[
    ["BattleRoundStartRequestContext"],
    DecisionRequest | None,
]
type BattleRoundStartResultHandler = Callable[
    ["BattleRoundStartResultContext"],
    bool,
]


@dataclass(frozen=True, slots=True)
class BattleRoundStartRequestContext:
    state: GameState
    decisions: DecisionController

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleRoundStartRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleRoundStartRequestContext decisions must be DecisionController."
            )
        _validate_start_battle_round(self.state)


@dataclass(frozen=True, slots=True)
class BattleRoundStartResultContext:
    state: GameState
    decisions: DecisionController
    request: DecisionRequest
    result: DecisionResult

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleRoundStartResultContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleRoundStartResultContext decisions must be DecisionController."
            )
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError(
                "BattleRoundStartResultContext request must be DecisionRequest."
            )
        if type(self.result) is not DecisionResult:
            raise GameLifecycleError("BattleRoundStartResultContext result must be DecisionResult.")
        _validate_start_battle_round(self.state)


@dataclass(frozen=True, slots=True)
class BattleRoundStartHookBinding:
    hook_id: str
    source_id: str
    request_handler: BattleRoundStartRequestHandler | None = None
    result_handler: BattleRoundStartResultHandler | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "hook_id", _validate_identifier("hook_id", self.hook_id))
        object.__setattr__(self, "source_id", _validate_identifier("source_id", self.source_id))
        if self.request_handler is None and self.result_handler is None:
            raise GameLifecycleError("BattleRoundStartHookBinding requires a handler.")
        if self.request_handler is not None and not callable(self.request_handler):
            raise GameLifecycleError(
                "BattleRoundStartHookBinding request_handler must be callable."
            )
        if self.result_handler is not None and not callable(self.result_handler):
            raise GameLifecycleError("BattleRoundStartHookBinding result_handler must be callable.")


@dataclass(frozen=True, slots=True)
class BattleRoundStartHookRegistry:
    bindings: tuple[BattleRoundStartHookBinding, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "bindings", _validate_hook_bindings(self.bindings))

    @classmethod
    def empty(cls) -> Self:
        return cls(bindings=())

    @classmethod
    def from_bindings(cls, bindings: tuple[BattleRoundStartHookBinding, ...]) -> Self:
        return cls(bindings=bindings)

    def all_bindings(self) -> tuple[BattleRoundStartHookBinding, ...]:
        return self.bindings

    def next_request_for(
        self,
        context: BattleRoundStartRequestContext,
    ) -> DecisionRequest | None:
        if type(context) is not BattleRoundStartRequestContext:
            raise GameLifecycleError("Battle-round start request hooks require a context.")
        requests: list[DecisionRequest] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            request = binding.request_handler(context)
            if request is None:
                continue
            if type(request) is not DecisionRequest:
                raise GameLifecycleError(
                    "Battle-round start request handlers must return DecisionRequest or None."
                )
            requests.append(request)
        if len(requests) > 1:
            raise GameLifecycleError(
                "Battle-round start hooks produced multiple simultaneous requests."
            )
        if not requests:
            return None
        return requests[0]

    def apply_result(
        self,
        context: BattleRoundStartResultContext,
    ) -> bool:
        if type(context) is not BattleRoundStartResultContext:
            raise GameLifecycleError("Battle-round start result hooks require a context.")
        handled_ids: list[str] = []
        for binding in self.bindings:
            if binding.result_handler is None:
                continue
            handled = binding.result_handler(context)
            if type(handled) is not bool:
                raise GameLifecycleError("Battle-round start result handlers must return bool.")
            if handled:
                handled_ids.append(binding.hook_id)
        if len(handled_ids) > 1:
            raise GameLifecycleError("Battle-round start result was handled by multiple hooks.")
        return bool(handled_ids)


def _validate_hook_bindings(value: object) -> tuple[BattleRoundStartHookBinding, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError("BattleRoundStartHookRegistry bindings must be a tuple.")
    bindings: list[BattleRoundStartHookBinding] = []
    seen: set[str] = set()
    for binding in cast(tuple[object, ...], value):
        if type(binding) is not BattleRoundStartHookBinding:
            raise GameLifecycleError(
                "BattleRoundStartHookRegistry bindings must contain BattleRoundStartHookBinding."
            )
        if binding.hook_id in seen:
            raise GameLifecycleError("BattleRoundStartHookRegistry hook IDs must be unique.")
        seen.add(binding.hook_id)
        bindings.append(binding)
    return tuple(sorted(bindings, key=lambda binding: binding.hook_id))


def _validate_start_battle_round(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Battle-round start hooks require battle stage.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        raise GameLifecycleError("Battle-round start hooks require Command phase.")
    if state.battle_phase_index != 0:
        raise GameLifecycleError("Battle-round start hooks require first battle phase.")
    if not state.turn_order:
        raise GameLifecycleError("Battle-round start hooks require turn order.")
    if state.active_player_id != state.turn_order[0]:
        raise GameLifecycleError("Battle-round start hooks require first player turn.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
