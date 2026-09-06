"""Reconstruct ordinary Consolidate progress from its preceding Fight boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import FightPhaseStepKind
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.fight_continuation_checkpoint import (
    FightContinuationEffects,
    reconstruct_fight_continuation_checkpoint,
)
from warhammer40k_core.engine.fight_order import (
    FightActivationSelection,
    FightActivationSelectionPayload,
    FightMovementStepState,
    FightPhaseState,
    FightPhaseStatePayload,
    current_fight_activation_selection_from_payload,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import GameLifecycleError


def consolidation_continuation_before_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    battle_round: int,
    active_player_id: str,
) -> FightPhaseState:
    boundaries = tuple(
        (index, event)
        for index, event in enumerate(event_records[:event_index])
        if event.event_type == "fight_step_completed"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_round") == battle_round
        and event.payload.get("active_player_id") == active_player_id
    )
    if len(boundaries) != 1:
        raise GameLifecycleError(
            "Consolidation continuation requires one preceding Fight boundary."
        )
    boundary_index, boundary = boundaries[0]
    ordinary: FightPhaseState = FightPhaseState.from_payload(
        cast(FightPhaseStatePayload, _object(_object(boundary.payload).get("fight_phase_state")))
    )
    _validate_entry(state, ordinary, battle_round=battle_round, active_player_id=active_player_id)
    canonical_entry = reconstruct_fight_continuation_checkpoint(
        state=state,
        events=event_records,
        records=decision_records,
        boundary_index=boundary_index,
        battle_round=battle_round,
        active_player_id=active_player_id,
    )
    if ordinary != canonical_entry:
        raise GameLifecycleError("Consolidation entry differs from preceding Fight decisions.")
    ordinary = canonical_entry
    records = {record.request.request_id: record for record in decision_records}
    response: list[FightActivationSelection] | None = None
    completed_response_ids: set[str] = set()
    effects = FightContinuationEffects(ordinary.allocated_model_ids_this_phase)
    melee_sequences: set[str] = set()
    for event in event_records[boundary_index + 1 : event_index]:
        if not isinstance(event.payload, dict):
            continue
        payload = event.payload
        if event.event_type == "melee_declaration_accepted":
            sequence_id = payload.get("attack_sequence_id")
            if not isinstance(sequence_id, str) or response is None:
                raise GameLifecycleError("Consolidation response melee sequence context drift.")
            melee_sequences.add(sequence_id)
        effects.consume(event, sequences=melee_sequences)
        if event.event_type == "forced_fight_activation_queue_started":
            if response is not None:
                raise GameLifecycleError("Consolidation continuation cannot nest response queues.")
            if payload.get("suspended_state") != ordinary.to_payload():
                raise GameLifecycleError(
                    "Consolidation suspended continuation differs from prior history."
                )
            response = []
            completed_response_ids = set()
        elif event.event_type == "fight_activation_selected" and response is not None:
            selected = FightActivationSelection.from_payload(
                cast(FightActivationSelectionPayload, _object(payload.get("activation_selection")))
            )
            record = _record(records, selected.request_id)
            canonical = current_fight_activation_selection_from_payload(
                result_payload=record.result.payload,
                request_id=record.request.request_id,
                result_id=record.result.result_id,
            )
            if canonical != selected:
                raise GameLifecycleError(
                    "Consolidation response selection differs from its decision."
                )
            response.append(canonical)
        elif event.event_type == "unit_has_fought" and response is not None:
            selected = FightActivationSelection.from_payload(
                cast(FightActivationSelectionPayload, _object(payload.get("activation_selection")))
            )
            if selected not in response or selected.result_id in completed_response_ids:
                raise GameLifecycleError("Consolidation response activation completion drift.")
            completed_response_ids.add(selected.result_id)
        elif event.event_type == "forced_fight_activation_queue_completed":
            if response is None or completed_response_ids != {item.result_id for item in response}:
                raise GameLifecycleError(
                    "Consolidation resumed with an unfinished response activation."
                )
            order = ordinary.fight_order_state
            ordinary = replace(
                ordinary,
                fight_order_state=replace(
                    order,
                    selected_to_fight_unit_ids=(
                        *order.selected_to_fight_unit_ids,
                        *(item.unit_instance_id for item in response),
                    ),
                    activation_selections=(*order.activation_selections, *response),
                ),
                allocated_model_ids_this_phase=tuple(sorted(effects.allocated_ids)),
                overrun_pile_in_completed_activation_result_ids=tuple(
                    sorted(ordinary.overrun_pile_in_completed_activation_result_ids)
                ),
            )
            if payload.get("resumed_state") != ordinary.to_payload():
                raise GameLifecycleError(
                    "Consolidation resumed continuation differs from authenticated effects."
                )
            response = None
        elif event.event_type == "overrun_pile_in_not_available" and response is not None:
            selection = FightActivationSelection.from_payload(
                cast(FightActivationSelectionPayload, _object(payload.get("activation_selection")))
            )
            if selection not in response:
                raise GameLifecycleError("Consolidation overrun completion lacks its activation.")
            ordinary = ordinary.with_overrun_pile_in_completed(
                activation_result_id=selection.result_id
            )
        elif event.event_type == "fight_movement_completed":
            record = _record(records, payload.get("request_id"))
            request = MovementProposalRequest.from_decision_request_payload(record.request.payload)
            if payload.get("result_id") != record.result.result_id:
                raise GameLifecycleError("Consolidation movement history decision identity drift.")
            if (
                request.context is not None
                and request.context.get("fight_movement_timing") == "overrun"
            ):
                if response is None or request.source_decision_result_id not in {
                    item.result_id for item in response
                }:
                    raise GameLifecycleError("Consolidation overrun movement lacks its activation.")
                ordinary = ordinary.with_overrun_pile_in_completed(
                    activation_result_id=request.source_decision_result_id
                )
                continue
            if response is not None or request.proposal_kind is not ProposalKind.CONSOLIDATE:
                raise GameLifecycleError("Consolidation continuation has an out-of-step movement.")
            movement = ordinary.consolidate_state
            if movement is None:
                raise GameLifecycleError("Consolidation continuation has no movement state.")
            for _ in state.player_ids:
                if movement.next_player_id == request.actor_id:
                    break
                next_player = state.player_ids[
                    (state.player_ids.index(movement.next_player_id) + 1) % len(state.player_ids)
                ]
                movement = movement.with_completed_player(next_player_id=next_player)
            if movement.next_player_id != request.actor_id:
                raise GameLifecycleError("Consolidation movement actor is not in this game.")
            ordinary = ordinary.with_consolidate_state(
                movement.with_completed_unit(unit_instance_id=request.unit_instance_id)
            )
    if response is not None:
        raise GameLifecycleError("Consolidation continuation is still inside a response queue.")
    return ordinary


def _validate_entry(
    state: GameState, entry: FightPhaseState, *, battle_round: int, active_player_id: str
) -> None:
    if (
        entry.battle_round != battle_round
        or entry.active_player_id != active_player_id
        or entry.current_step is not FightPhaseStepKind.CONSOLIDATE
        or entry.forced_activation_context is not None
        or entry.suspended_state is not None
        or entry.active_activation is not None
        or entry.attack_sequence is not None
        or entry.pending_completed_attack_sequence is not None
        or entry.phase_complete
        or entry.consolidate_state
        != FightMovementStepState.start(
            step=FightPhaseStepKind.CONSOLIDATE, next_player_id=active_player_id
        )
        or entry.with_current_step(
            current_step=FightPhaseStepKind.CONSOLIDATE,
            policy=state.runtime_ruleset_descriptor().fight_policy,
        )
        != entry
    ):
        raise GameLifecycleError("Consolidation preceding Fight boundary is not a valid entry.")


def _record(records: dict[str, DecisionRecord], request_id: object) -> DecisionRecord:
    if not isinstance(request_id, str) or request_id not in records:
        raise GameLifecycleError("Consolidation continuation is missing an accepted decision.")
    return records[request_id]


def _object(value: object) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError("Consolidation continuation history requires object payloads.")
    return cast(dict[str, JsonValue], value)
