from __future__ import annotations

from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartEffectContext,
    CommandPhaseStartRequestContext,
    CommandPhaseStartRequestHandler,
)
from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def command_request_context(
    context: CommandPhaseStartEffectContext,
) -> CommandPhaseStartRequestContext:
    return CommandPhaseStartRequestContext(
        state=context.state,
        decisions=context.decisions,
        active_player_id=context.active_player_id,
        authoritative_request_id="timing-request-template",
    )


def command_army_rule_candidate(
    context: CommandPhaseStartEffectContext,
    *,
    request_handler: CommandPhaseStartRequestHandler,
    source_rule_id: str,
    hook_id: str,
    requirement: SequencingRequirement,
) -> tuple[TimingRuleCandidate, ...]:
    """Discover one army-level state machine, retaining its internal resolution choices."""
    request = request_handler(command_request_context(context))
    if request is None:
        return ()
    return (
        timing_candidate_for_request(
            template=request,
            participant_id=f"{hook_id}:{request.actor_id}",
            source_rule_id=source_rule_id,
            requirement=requirement,
            next_request_id=context.state.next_decision_request_id,
        ),
    )
