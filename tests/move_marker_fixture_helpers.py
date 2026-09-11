from __future__ import annotations

from collections.abc import Callable
from functools import partial

from warhammer40k_core.engine.cult_ambush_marker_removal import (
    cult_ambush_marker_removal_candidates,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.primary_mission_state_runtime import surveil_move_marker_candidates
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    RULES_SEQUENCING_SOURCE_ID,
)


def resolve_cult_markers_for_fixture(
    *, state: GameState, decisions: DecisionController, completed_phase: BattlePhase
) -> None:
    _resolve_marker_rules(
        state=state,
        decisions=decisions,
        completed_phase=completed_phase,
        discover=partial(
            cult_ambush_marker_removal_candidates,
            state=state,
            decisions=decisions,
            completed_phase=completed_phase,
        ),
    )


def resolve_surveil_markers_for_fixture(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    _resolve_marker_rules(
        state=state,
        decisions=decisions,
        completed_phase=completed_phase,
        discover=partial(
            surveil_move_marker_candidates,
            state=state,
            decisions=decisions,
            completed_phase=completed_phase,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
    )


def _resolve_marker_rules(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    discover: Callable[..., tuple[TimingRuleCandidate, ...]],
) -> None:
    """Exercise isolated marker providers through the real timing-batch executor."""
    assert state.active_player_id is not None
    for event in tuple(decisions.event_log.records):
        identity = f"fixture-move-marker:{event.event_id}"
        context = SequencingConflictContext(
            conflict_id=identity,
            game_id=state.game_id,
            player_ids=state.player_ids,
            active_player_id=state.active_player_id,
            timing_window=TimingWindow(
                window_id=identity,
                game_id=state.game_id,
                battle_round=state.battle_round,
                active_player_id=state.active_player_id,
                phase=completed_phase,
                trigger_event_id=event.event_id,
                descriptor=TimingWindowDescriptor(
                    descriptor_id=f"{identity}:descriptor",
                    source_rule_id=RULES_SEQUENCING_SOURCE_ID,
                    trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_MOVE,
                    phase=completed_phase,
                    source_step="unit_move_completed",
                ),
            ),
        )
        assert (
            resolve_timing_rule_candidates(
                decisions=decisions,
                context=context,
                discover=partial(discover, trigger_event_id=event.event_id),
                next_request_id=state.next_decision_request_id,
            )
            is None
        )
