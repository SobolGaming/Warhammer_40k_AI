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


def start_turn_context(state: GameState) -> SequencingConflictContext:
    active = state.active_player_id
    if active is None:
        raise GameLifecycleError("Turn-start source authority requires a player turn.")
    identifier = f"timing-window:{state.game_id}:round-{state.battle_round:02d}:turn:{active}:start"
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=active,
        timing_window=TimingWindow(
            window_id=identifier,
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=active,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{identifier}:descriptor",
                trigger_kind=TimingTriggerKind.START_TURN,
                source_rule_id="core-rules-lifecycle-timing",
                source_step="player_turn",
            ),
        ),
    )


def boundary_context(
    state: GameState, trigger_kind: TimingTriggerKind
) -> SequencingConflictContext:
    phase = state.current_battle_phase
    active = state.active_player_id
    if phase is None or active is None:
        raise GameLifecycleError("End rules require a current phase and player turn.")
    prefix = f"timing-window:{state.game_id}:round-{state.battle_round:02d}"
    if trigger_kind is TimingTriggerKind.END_PHASE:
        identifier = f"{prefix}:turn:{active}:phase:{phase.value}:end"
    elif trigger_kind is TimingTriggerKind.END_TURN:
        identifier = f"{prefix}:turn:{active}:end"
        phase = None
    elif trigger_kind is TimingTriggerKind.END_BATTLE_ROUND:
        identifier = f"{prefix}:battle-round:end"
        active = state.turn_order[0]
        phase = None
    else:
        raise GameLifecycleError("End rules require an end-boundary timing trigger.")
    window = TimingWindow(
        window_id=identifier,
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=active,
        phase=phase,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{identifier}:descriptor",
            trigger_kind=trigger_kind,
            phase=phase,
            source_rule_id="core-rules-lifecycle-timing",
            source_step=(
                phase.value
                if phase is not None
                else "player_turn"
                if trigger_kind is TimingTriggerKind.END_TURN
                else "battle_round"
            ),
        ),
    )
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=active,
        timing_window=window,
    )


def resolve_boundary_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger_kind: TimingTriggerKind,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> DecisionRequest | LifecycleStatus | None:
    context = boundary_context(state, trigger_kind)
    if timing_window_boundary_state(
        decisions=decisions,
        window=context.timing_window,
        resolution_order=("non_mission_rules", "mission_rules"),
    )[1]:
        return None
    record_timing_window_boundary(
        decisions=decisions,
        window=context.timing_window,
        completed=False,
        resolution_order=("non_mission_rules", "mission_rules"),
    )
    return resolve_timing_rule_candidates(
        decisions=decisions,
        context=context,
        discover=discover,
        next_request_id=state.next_decision_request_id,
    )
