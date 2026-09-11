from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.retained_destruction_cleanup import start_retained_cleanup
from warhammer40k_core.engine.retained_destruction_state import (
    RetainedDestructionStage,
    retained_destructions,
)
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext


def retained_phase_end_binding() -> TurnEndHookBinding:
    return TurnEndHookBinding(
        hook_id="core-rules:retained-destruction-phase-end",
        source_id="gw-11e-core-fight-on-death:fight-on-death",
        trigger_kind=TimingTriggerKind.END_PHASE,
        candidate_handler=retained_phase_end_candidates,
    )


def retained_phase_end_candidates(
    context: TurnEndRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    candidates: list[TimingRuleCandidate] = []
    for record in retained_destructions(state=context.state):
        if record.stage is not RetainedDestructionStage.WAITING:
            continue
        source = next(
            source
            for source in record.eligible_sources
            if source.source_id == record.selected_source_id
        )
        candidates.append(
            TimingRuleCandidate(
                participant=SequencingParticipant(
                    participant_id=f"retained-phase-end:{record.cause_id}",
                    player_id=record.placement.player_id,
                    source_rule_id=source.source_rule_id,
                    requirement=SequencingRequirement.MANDATORY,
                    payload={
                        "cause_id": record.cause_id,
                        "model_instance_id": record.model_instance_id,
                        "source_id": source.source_id,
                        "timing_source_rule_id": "gw-11e-core-fight-on-death:fight-on-death",
                    },
                ),
                activate=partial(
                    start_retained_cleanup,
                    state=context.state,
                    decisions=context.decisions,
                    record=record,
                ),
            )
        )
    return tuple(candidates)
