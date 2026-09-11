from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.boundary_sequencing import resolve_boundary_candidates
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.return_on_death import resolve_return_on_death_occurrence
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext


def return_phase_end_binding() -> TurnEndHookBinding:
    return TurnEndHookBinding(
        hook_id="core-rules:return-on-death-phase-end",
        source_id="core-rules-lifecycle-timing",
        trigger_kind=TimingTriggerKind.END_PHASE,
        candidate_handler=return_phase_end_candidates,
    )


def return_phase_end_candidates(
    context: TurnEndRequestContext,
    *,
    dice_manager: DiceRollManager | None = None,
) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"return-on-death:{pending.pending_id}",
                source_rule_id=pending.source_rule_id,
                player_id=pending.owner_player_id,
                requirement=SequencingRequirement.MANDATORY,
                payload={"pending_id": pending.pending_id},
            ),
            activate=partial(
                resolve_return_on_death_occurrence,
                state=context.state,
                decisions=context.decisions,
                pending=pending,
                dice_manager=dice_manager,
            ),
        )
        for pending in context.state.pending_return_on_death
        if not pending.resolved
        and pending.resolution_timing == "phase_end"
        and pending.trigger_battle_round == context.state.battle_round
        and pending.trigger_phase == context.completed_phase.value
    )


def resolve_return_phase_end_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_manager: DiceRollManager | None = None,
) -> DecisionRequest | LifecycleStatus | None:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Return-on-death timing requires a phase.")
    context = TurnEndRequestContext(
        state=state,
        decisions=decisions,
        completed_phase=phase,
        trigger_kind=TimingTriggerKind.END_PHASE,
    )
    outcome = resolve_boundary_candidates(
        state=state,
        decisions=decisions,
        trigger_kind=TimingTriggerKind.END_PHASE,
        discover=lambda: return_phase_end_candidates(context, dice_manager=dice_manager),
    )
    if isinstance(outcome, DecisionRequest):
        decisions.request_decision(outcome)
    return outcome
