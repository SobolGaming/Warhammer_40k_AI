from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
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


def phase_start_context(state: GameState) -> SequencingConflictContext:
    phase = state.current_battle_phase
    if phase is None or state.active_player_id is None:
        raise GameLifecycleError("Phase-start timing requires a current player turn and phase.")
    identifier = (
        f"timing-window:{state.game_id}:round-{state.battle_round:02d}:"
        f"turn:{state.active_player_id}:phase:{phase.value}:start"
    )
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=state.effective_active_player_id(),
        timing_window=TimingWindow(
            window_id=identifier,
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=state.effective_active_player_id(),
            phase=phase,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{identifier}:descriptor",
                trigger_kind=TimingTriggerKind.START_PHASE,
                phase=phase,
                source_rule_id="core-rules-lifecycle-timing",
                source_step=phase.value,
            ),
        ),
    )


def resolve_phase_start_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> DecisionRequest | LifecycleStatus | None:
    context = phase_start_context(state)
    if timing_window_boundary_state(decisions=decisions, window=context.timing_window)[1]:
        return None
    record_timing_window_boundary(
        decisions=decisions, window=context.timing_window, completed=False
    )
    outcome = resolve_timing_rule_candidates(
        decisions=decisions,
        context=context,
        discover=discover,
        next_request_id=state.next_decision_request_id,
    )
    if outcome is None:
        record_timing_window_boundary(
            decisions=decisions, window=context.timing_window, completed=True
        )
    return outcome


def selected_request_is_current(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    candidates: tuple[TimingRuleCandidate, ...],
) -> bool:
    from warhammer40k_core.engine.timing_request_candidates import (
        selected_timing_request_is_current,
    )

    return selected_timing_request_is_current(
        decisions=decisions,
        context=phase_start_context(state),
        request=request,
        candidates=candidates,
    )
