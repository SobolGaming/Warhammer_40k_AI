from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlContext,
    PhaseEndObjectiveControlHookRegistry,
    StickyObjectiveControlState,
)
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    rule_discovery_snapshot,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookBinding, TurnEndRequestContext


def sticky_boundary_binding(registry: PhaseEndObjectiveControlHookRegistry) -> TurnEndHookBinding:
    return TurnEndHookBinding(
        hook_id="core-rules:sticky-objective-boundary-providers",
        source_id="core-rules-lifecycle-timing",
        trigger_kind=TimingTriggerKind.END_PHASE,
        candidate_handler=partial(sticky_boundary_candidates, registry),
    )


def sticky_boundary_candidates(
    registry: PhaseEndObjectiveControlHookRegistry,
    context: TurnEndRequestContext,
) -> tuple[TimingRuleCandidate, ...]:
    if not registry.bindings:
        return ()
    before = rule_discovery_snapshot(context.state, context.decisions)
    states = registry.states_for(
        PhaseEndObjectiveControlContext(
            state=context.state,
            event_log=context.decisions.event_log,
            completed_phase=context.completed_phase,
            runtime_modifier_registry=context.runtime_modifier_registry,
        )
    )
    if before != rule_discovery_snapshot(context.state, context.decisions):
        raise GameLifecycleError("Sticky objective discovery mutated engine state.")
    existing = {item.state_id: item for item in context.state.sticky_objective_control_states}
    groups: dict[tuple[str, str, str, str], list[StickyObjectiveControlState]] = {}
    for item in states:
        if item.state_id in existing:
            prior = existing[item.state_id]
            # Some source rules identify a once-per-round state across phase boundaries.
            # Its first recorded boundary remains authoritative on later rediscovery.
            if (
                item.game_id,
                item.player_id,
                item.source_rule_id,
                item.objective_id,
                item.originating_unit_instance_id,
                item.destroyed_unit_instance_id,
            ) != (
                prior.game_id,
                prior.player_id,
                prior.source_rule_id,
                prior.objective_id,
                prior.originating_unit_instance_id,
                prior.destroyed_unit_instance_id,
            ):
                raise GameLifecycleError("Sticky objective source occurrence drift.")
            continue
        key = (
            item.player_id,
            item.source_rule_id,
            item.originating_unit_instance_id,
            item.source_event_id,
        )
        groups.setdefault(key, []).append(item)
    return tuple(
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id="sticky-objective:" + ":".join(key),
                source_rule_id=key[1],
                player_id=key[0],
                requirement=SequencingRequirement.MANDATORY,
                payload={"state_ids": [item.state_id for item in items]},
            ),
            activate=partial(_record_states, context, tuple(items)),
        )
        for key, items in sorted(groups.items())
    )


def _record_states(
    context: TurnEndRequestContext, states: tuple[StickyObjectiveControlState, ...]
) -> None:
    for item in states:
        context.state.record_sticky_objective_control_state(item)
        context.decisions.event_log.append(
            "sticky_objective_control_state_recorded",
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "active_player_id": context.state.active_player_id,
                "phase": context.completed_phase.value,
                "sticky_objective_control_state": item.to_payload(),
            },
        )
