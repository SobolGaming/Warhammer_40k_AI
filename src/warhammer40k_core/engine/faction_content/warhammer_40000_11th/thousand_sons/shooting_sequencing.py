from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.sequencing import SequencingRequirement
from warhammer40k_core.engine.shooting_phase_start_hooks import ShootingPhaseStartRequestContext
from warhammer40k_core.engine.timing_request_candidates import timing_candidate_for_request
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate

from .army_rule import HOOK_ID, SOURCE_RULE_ID, cabal_of_sorcerers_request


def candidates(context: ShootingPhaseStartRequestContext) -> tuple[TimingRuleCandidate, ...]:
    template = cabal_of_sorcerers_request(
        replace(context, authoritative_request_id=f"template:{HOOK_ID}")
    )
    if template is None:
        return ()
    return (
        timing_candidate_for_request(
            template=template,
            participant_id=f"{HOOK_ID}:{template.actor_id}",
            source_rule_id=SOURCE_RULE_ID,
            requirement=SequencingRequirement.OPTIONAL,
            next_request_id=context.state.next_decision_request_id,
        ),
    )
