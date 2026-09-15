"""Lifecycle ownership for a source-authorized Charge during another player's turn."""

from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from warhammer40k_core.engine.charge_phase_state import ChargeInterruption
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.reaction_queue import ReactionQueue

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler


def advance_interrupted_charge(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    handler: ChargePhaseHandler,
) -> LifecycleStatus | None:
    phase = state.charge_phase_state
    if phase is None or phase.interruption is None:
        return None
    if state.current_battle_phase is not BattlePhase.CHARGE:
        raise GameLifecycleError("Interrupted Charge cannot escape its phase.")
    if decisions.queue.pending_requests or state.out_of_phase_shooting_state is not None:
        return None
    return handler.begin_phase(state=state, decisions=decisions, reaction_queue=reaction_queue)


def finish_interrupted_charge_if_complete(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
) -> LifecycleStatus | None:
    phase = state.charge_phase_state
    if phase is None or phase.interruption is None:
        return None
    if not phase.phase_complete and (
        not phase.selected_unit_ids or phase.active_selection is not None
    ):
        return None
    if decisions.queue.pending_requests:
        raise GameLifecycleError("Cannot finish an interrupted Charge with pending choices.")
    source = phase.interruption
    if reaction_queue is not None and reaction_queue.frames:
        request_id = reaction_queue.frames[-1].request_id
        matches = tuple(
            record for record in decisions.records if record.request.request_id == request_id
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "Interrupted Charge completion requires its recorded reaction choice."
            )
        reaction_queue.resolve_reaction(result=matches[0].result, decisions=decisions)
    from warhammer40k_core.engine.active_player_scopes import charge_scope, pop_scope

    scope = charge_scope(state)
    if scope is None:
        raise GameLifecycleError("Charge completion lost its active-player scope.")
    pop_scope(state, scope)
    state.replace_charge_phase_state(source.suspended_phase)
    payload = {
        "source": source.to_payload(),
        "resolved_charge_phase": phase.to_payload(),
    }
    decisions.event_log.append("interrupted_charge_completed", payload)
    return LifecycleStatus.advanced(
        stage=state.stage, payload={"phase_body_status": "interrupted_charge_completed"}
    )


def continue_interrupted_charge_reaction(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue,
    result: DecisionResult,
) -> None:
    phase = state.charge_phase_state
    if phase is None or phase.interruption is None or not reaction_queue.frames:
        return
    if reaction_queue.frames[-1].request_id != result.request_id:
        return
    if not decisions.queue.pending_requests:
        raise GameLifecycleError("Interrupted Charge lost its next decision.")
    reaction_queue.continue_reaction(
        result=result, next_request_id=decisions.queue.peek_next().request_id, decisions=decisions
    )


def charge_turn_owner_at_event(
    *, event_records: tuple[EventRecord, ...], event_index: int, actor_id: str
) -> str:
    source: ChargeInterruption | None = None
    for event in event_records[:event_index]:
        if event.event_type == "interrupted_charge_started":
            if source is not None or not isinstance(event.payload, dict):
                raise GameLifecycleError("Interrupted Charge source nesting drift.")
            source = ChargeInterruption.from_payload(event.payload["source"])
        elif event.event_type == "interrupted_charge_completed":
            source = None
    return actor_id if source is None else source.suspended_phase.active_player_id
