from __future__ import annotations

from functools import partial

from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState
from warhammer40k_core.engine.fight_phase_end_hooks import (
    FightPhaseEndHookRegistry,
    FightPhaseEndRequestContext,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext


def fight_end_boundary_binding(registry: FightPhaseEndHookRegistry) -> TurnEndHookBinding:
    """Compose Fight-end providers into the same boundary as other phase-end rules."""
    return TurnEndHookBinding(
        hook_id="core-rules:fight-end-boundary-providers",
        source_id="core-rules-lifecycle-timing",
        trigger_kind=TimingTriggerKind.END_PHASE,
        candidate_handler=partial(_boundary_candidates, registry),
    )


def _boundary_candidates(
    registry: FightPhaseEndHookRegistry,
    context: TurnEndRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    if context.completed_phase is not BattlePhase.FIGHT:
        return ()
    return registry.candidates_for(
        FightPhaseEndRequestContext(state=context.state, decisions=context.decisions)
    )


def complete_fight_phase_boundary(*, state: GameState, decisions: DecisionController) -> None:
    if state.current_battle_phase is not BattlePhase.FIGHT:
        return
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.current_step is not FightPhaseStepKind.END:
        raise GameLifecycleError("Fight phase completion requires its completed body.")
    if fight_state.phase_complete:
        expected = fight_phase_status_payload(
            state=state, fight_state=fight_state, phase_body_status="fight_phase_complete"
        )
        prior = tuple(
            event
            for event in decisions.event_log.records
            if event.event_type == "fight_phase_completed" and event.payload == expected
        )
        if len(prior) != 1:
            raise GameLifecycleError("Fight phase completion event authority drift.")
        return
    state.replace_fight_phase_state(fight_state.with_phase_complete())
    decisions.event_log.append(
        "fight_phase_completed",
        fight_phase_status_payload(
            state=state,
            fight_state=fight_state.with_phase_complete(),
            phase_body_status="fight_phase_complete",
        ),
    )


def fight_phase_status_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    phase_body_status: str,
) -> JsonValue:
    return validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": phase_body_status,
            "fight_phase_state": fight_state.to_payload(),
        }
    )
