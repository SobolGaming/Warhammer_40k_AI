from __future__ import annotations

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PRIMARY_SCORING_PENDING_WINDOW_TURN_END_FACTION_RULE,
    mark_pending_primary_scoring_boundaries,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sticky_objective_control import (
    PhaseEndObjectiveControlHookRegistry,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.turn_end_hooks import TurnEndHookRegistry, TurnEndRequestContext


def compose_core_end_rule_registry(
    registry: TurnEndHookRegistry,
    objective_control_hooks: PhaseEndObjectiveControlHookRegistry,
) -> TurnEndHookRegistry:
    """Use the same Core providers for boundary execution and submission authority."""
    from warhammer40k_core.engine.retained_phase_end_sequencing import retained_phase_end_binding
    from warhammer40k_core.engine.return_on_death_sequencing import return_phase_end_binding
    from warhammer40k_core.engine.sticky_objective_sequencing import sticky_boundary_binding

    return TurnEndHookRegistry.from_bindings(
        (
            *registry.bindings,
            sticky_boundary_binding(objective_control_hooks),
            retained_phase_end_binding(),
            return_phase_end_binding(),
        )
    )


def request_end_rules(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: TurnEndHookRegistry,
    trigger_kind: TimingTriggerKind,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
    reaction_queue: ReactionQueue | None = None,
) -> LifecycleStatus | None:
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("End rules require a current phase.")
    outcome = registry.next_request_for(
        TurnEndRequestContext(
            state=state,
            decisions=decisions,
            completed_phase=phase,
            trigger_kind=trigger_kind,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            runtime_modifier_registry=runtime_modifier_registry,
            reaction_queue=reaction_queue,
        )
    )
    if isinstance(outcome, LifecycleStatus):
        return outcome
    if outcome is None:
        return None
    decisions.request_decision(outcome)
    decisions.event_log.append(
        "turn_end_faction_rule_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": phase.value,
            "request_id": outcome.request_id,
            "decision_type": outcome.decision_type,
            "actor_id": outcome.actor_id,
        },
    )
    mark_pending_primary_scoring_boundaries(
        state=state,
        pending_window=PRIMARY_SCORING_PENDING_WINDOW_TURN_END_FACTION_RULE,
        pending_decision_request_id=outcome.request_id,
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=outcome,
        payload={
            "battle_round": state.battle_round,
            "phase": phase.value,
            "phase_body_status": PRIMARY_SCORING_PENDING_WINDOW_TURN_END_FACTION_RULE,
            "request_id": outcome.request_id,
        },
    )


def prepare_phase_end_boundary(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    """Determine control before any rule at this boundary, retaining its authority."""
    phase = state.current_battle_phase
    if phase is None:
        raise GameLifecycleError("Phase-end preparation requires a current phase.")
    phase_end_objective_control_record = state.determine_current_phase_end_objective_control(
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if not any(
        event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload.get("record_ids") == [phase_end_objective_control_record.record_id]
        for event in decisions.event_log.records
    ):
        decisions.event_log.append(
            "end_boundary_objective_control_determined",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": phase.value,
                "record_ids": [phase_end_objective_control_record.record_id],
                "source_rule_id": (
                    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:"
                    "14.02.01-control-first"
                ),
            },
        )
