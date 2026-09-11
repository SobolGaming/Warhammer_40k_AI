from __future__ import annotations

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.primary_mission_choices import punishment_timing_candidates
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind, TimingWindow


def mission_timing_candidates(
    *, state: GameState, decisions: DecisionController, window: TimingWindow
) -> tuple[TimingRuleCandidate, ...]:
    """Mission-owned providers join the same boundary as loaded army rules."""
    if state.mission_setup is None:
        return ()
    if window.descriptor.trigger_kind is TimingTriggerKind.START_TURN:
        return punishment_timing_candidates(state=state, decisions=decisions)
    return ()
