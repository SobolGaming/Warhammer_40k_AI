"""Resume turn-start control before allowing new-turn rules or expiry."""

from __future__ import annotations

# This continuation shares GameState's phase-start expiry owner.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_turn_start_evidence_events,
)
from warhammer40k_core.engine.primary_turn_start_evidence import record_primary_turn_start_evidence

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def complete_turn_start_modifier_boundary(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    if state.active_player_id is None:
        raise GameLifecycleError("Turn-start control requires an active player.")
    if state.current_battle_phase is not BattlePhase.COMMAND:
        return None
    if state.mission_setup is None or state.battlefield_state is None:
        return None
    if any(
        snapshot.active_player_id == state.active_player_id
        and snapshot.battle_round == state.battle_round
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    ):
        return None
    from warhammer40k_core.engine.objective_control import (
        ObjectiveControlContext,
        ObjectiveControlTiming,
    )
    from warhammer40k_core.engine.random_objective_control import objective_control_boundary_scope

    boundary_id = objective_control_boundary_scope(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_START,
            phase=BattlePhase.COMMAND,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )
    requests = (
        *(record.request for record in decisions.records),
        *decisions.queue.pending_requests,
    )
    if not any(
        request.decision_type == "select_modifier_ignores"
        and isinstance(request.payload, dict)
        and isinstance(source := request.payload.get("source_context"), dict)
        and source.get("boundary_id") == boundary_id
        and source.get("timing") == ObjectiveControlTiming.TURN_START.value
        for request in requests
    ):
        return None
    objective_ids = tuple(value.state_id for value in state.primary_objective_turn_start_states)
    snapshot_ids = tuple(
        value.snapshot_id for value in state.primary_rules_unit_turn_start_snapshots
    )
    pending = record_primary_turn_start_evidence(
        state=state,
        decisions=decisions,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if pending is not None:
        return pending
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=objective_ids,
        snapshot_ids_before=snapshot_ids,
    )
    # This is the same engine-owned expiry used immediately after synchronous
    # turn-start control; a pending selection postpones it until this continuation.
    state._expire_persisting_effects_at_current_phase_start()
    return None
