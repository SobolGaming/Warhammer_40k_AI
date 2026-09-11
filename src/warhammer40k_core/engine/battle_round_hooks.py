from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.active_player import effective_active_player_id
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.lifecycle_hooks import LifecycleHookEvent, validate_hook_bindings
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_window_events import (
    record_timing_window_boundary,
    timing_window_boundary_state,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

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
    authoritative_request_id: str | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.game_state import GameState

        if type(self.state) is not GameState:
            raise GameLifecycleError("BattleRoundStartRequestContext state must be GameState.")
        if type(self.decisions) is not DecisionController:
            raise GameLifecycleError(
                "BattleRoundStartRequestContext decisions must be DecisionController."
            )
        _validate_start_battle_round(self.state)

    def issue_request_id(self) -> str:
        if self.authoritative_request_id is not None:
            return _validate_identifier("authoritative_request_id", self.authoritative_request_id)
        return self.state.next_decision_request_id()


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
    candidate_handler: (
        Callable[[BattleRoundStartRequestContext], tuple[TimingRuleCandidate, ...]] | None
    ) = None

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
        timing = _battle_round_sequencing_context(context)
        if timing_window_boundary_state(decisions=context.decisions, window=timing.timing_window)[
            1
        ]:
            return None
        record_timing_window_boundary(
            decisions=context.decisions,
            window=timing.timing_window,
            completed=False,
        )
        outcome = resolve_timing_rule_candidates(
            decisions=context.decisions,
            context=timing,
            discover=lambda: self.candidates_for(context),
            next_request_id=context.state.next_decision_request_id,
        )
        if outcome is not None and type(outcome) is not DecisionRequest:
            raise GameLifecycleError("Battle-round activation must return a request or complete.")
        if outcome is None:
            record_timing_window_boundary(
                decisions=context.decisions,
                window=timing.timing_window,
                completed=True,
            )
        return outcome

    def candidates_for(
        self, context: BattleRoundStartRequestContext
    ) -> tuple[TimingRuleCandidate, ...]:
        candidates: list[TimingRuleCandidate] = []
        for binding in self.bindings:
            if binding.request_handler is None:
                continue
            if binding.candidate_handler is None:
                raise GameLifecycleError("Battle-round providers require pure candidate discovery.")
            before = (context.state.to_payload(), context.decisions.to_payload())
            discovered = binding.candidate_handler(context)
            if before != (context.state.to_payload(), context.decisions.to_payload()):
                raise GameLifecycleError("Battle-round candidate discovery mutated engine state.")
            if type(discovered) is not tuple or any(
                type(candidate) is not TimingRuleCandidate for candidate in discovered
            ):
                raise GameLifecycleError("Battle-round discovery requires typed candidates.")
            candidates.extend(discovered)
        return tuple(candidates)

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
    return validate_hook_bindings(
        value,
        lifecycle_event=LifecycleHookEvent.BATTLE_ROUND_START,
        binding_type=BattleRoundStartHookBinding,
        registry_name="BattleRoundStartHookRegistry",
        invalid_binding_message=(
            "BattleRoundStartHookRegistry bindings must contain BattleRoundStartHookBinding."
        ),
    )


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


def _battle_round_sequencing_context(
    context: BattleRoundStartRequestContext,
) -> SequencingConflictContext:
    state = context.state
    active = effective_active_player_id(state, trigger_kind=TimingTriggerKind.START_BATTLE_ROUND)
    identifier = f"battle-round-start:{state.game_id}:{state.battle_round}"
    window_id = f"timing-window:{state.game_id}:round-{state.battle_round:02d}:battle-round:start"
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=active,
        timing_window=TimingWindow(
            window_id=f"timing-window:{state.game_id}:round-{state.battle_round:02d}:battle-round:start",
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=active,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{window_id}:descriptor",
                trigger_kind=TimingTriggerKind.START_BATTLE_ROUND,
                source_rule_id="core-rules-lifecycle-timing",
                source_step="battle_round",
            ),
        ),
    )
