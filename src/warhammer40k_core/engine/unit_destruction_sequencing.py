from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import resolve_timing_rule_candidates
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    UnitDestroyedContext,
    UnitDestroyedHookRegistry,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    RULES_SEQUENCING_SOURCE_ID,
)


def unit_destruction_timing_context(context: UnitDestroyedContext) -> SequencingConflictContext:
    state = context.state
    identifier = f"model-destruction:{context.model_destroyed_event_id}"
    active = context.sequencing_active_player_id
    phase = context.completed_phase
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
            phase=phase,
            trigger_event_id=context.model_destroyed_event_id,
            descriptor=TimingWindowDescriptor(
                descriptor_id="unit-destruction-sequencing",
                trigger_kind=TimingTriggerKind.AFTER_UNIT_DESTROYED,
                phase=phase,
                source_rule_id=RULES_SEQUENCING_SOURCE_ID,
                source_step="model_destroyed",
            ),
        ),
    )


def resolve_unit_destroyed_candidates(
    *, context: UnitDestroyedContext, registry: UnitDestroyedHookRegistry
) -> LifecycleStatus | None:
    if context.decisions.queue.pending_requests:
        raise GameLifecycleError(
            "Unit-destroyed resolution requires the pending decision to finish."
        )
    outcome = resolve_timing_rule_candidates(
        decisions=context.decisions,
        context=unit_destruction_timing_context(context),
        discover=partial(registry.candidates_for, context),
        next_request_id=context.state.next_decision_request_id,
    )
    if isinstance(outcome, DecisionRequest):
        context.decisions.request_decision(outcome)
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage,
            decision_request=outcome,
            payload={"phase_body_status": "unit_destroyed_rule_pending"},
        )
    return outcome
