from __future__ import annotations

from typing import cast

from warhammer40k_core.engine import command_battle_shock_candidates as _cbsc
from warhammer40k_core.engine.command_battle_shock_history import (
    COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
)
from warhammer40k_core.engine.command_points import CommandPhaseStep, CommandStepState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import reconcile_rules_unit_identity
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingNextParticipantDecision,
    SequencingNextParticipantDecisionPayload,
    SequencingParticipant,
    apply_select_next_sequencing_participant_from_request,
    create_select_next_sequencing_participant_request,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

COMMAND_BATTLE_SHOCK_SOURCE_RULE_ID = "gw-11e-core-rules:command-phase:battle-shock"
_COMMAND_BATTLE_SHOCK_SEQUENCING_DESCRIPTOR_ID = "command-battle-shock-test-order"


def battle_shock_result_base_payload(
    *,
    state: GameState,
    active_player_id: str,
) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": BattlePhase.COMMAND.value,
        "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
    }


def unsupported_candidate_status(
    *,
    state: GameState,
) -> LifecycleStatus | None:
    command_state = _command_step_state(state)
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Battle-shock candidate support requires battlefield state.")
    completed_count = len(command_state.completed_battle_shock_test_request_ids)
    completed_unit_ids = set(command_state.battle_shock_candidate_order_unit_ids[:completed_count])
    for candidate in command_state.battle_shock_candidate_inventory:
        if candidate.test_reason is None:
            continue
        if candidate.unit_instance_id in completed_unit_ids:
            continue
        reconciliation = reconcile_rules_unit_identity(
            state=state,
            unit_instance_id=candidate.unit_instance_id,
        )
        if (
            reconciliation.surviving_unit_instance_ids
            and reconciliation.placed_surviving_unit_instance_ids
            == reconciliation.surviving_unit_instance_ids
        ):
            continue
        return LifecycleStatus.unsupported(
            stage=GameLifecycleStage.BATTLE,
            message=(
                "Command Battle-shock testing for an eligible off-battlefield rules unit "
                "is not supported."
            ),
            payload={
                "source_rule_id": COMMAND_BATTLE_SHOCK_SOURCE_RULE_ID,
                "section_id": "08.03",
                "unit_instance_id": candidate.unit_instance_id,
                "component_unit_instance_ids": list(candidate.component_unit_instance_ids),
                "candidate_reasons": [reason.value for reason in candidate.eligibility_reasons],
                "unsupported_scope": "off_battlefield_battle_shock_test",
            },
        )
    return None


def resolve_candidate_order(
    *,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    command_state = _command_step_state(state)
    candidates = tuple(
        candidate
        for candidate in command_state.battle_shock_candidate_inventory
        if candidate.test_reason is not None
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        expected_order = (candidates[0].unit_instance_id,)
        if not command_state.battle_shock_candidate_order_unit_ids:
            state.replace_command_step_state(
                command_state.with_battle_shock_candidate_order(expected_order)
            )
        elif command_state.battle_shock_candidate_order_unit_ids != expected_order:
            raise GameLifecycleError("Battle-shock trivial candidate order drifted.")
        return None
    context = _command_battle_shock_sequencing_context(state=state)
    all_participants = _command_battle_shock_sequencing_participants(
        active_player_id=command_state.active_player_id,
        candidates=candidates,
    )
    participant_by_id = {
        participant.participant_id: participant for participant in all_participants
    }
    unit_id_by_participant_id = {
        _command_battle_shock_participant_id(candidate): candidate.unit_instance_id
        for candidate in candidates
    }
    matching_events: list[tuple[int, SequencingNextParticipantDecision]] = []
    for event_index, event in enumerate(decisions.event_log.records):
        if event.event_type != "sequencing_next_participant_selected":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Battle-shock sequencing event payload is malformed.")
        if event.payload.get("conflict_id") != context.conflict_id:
            continue
        matching_events.append(
            (
                event_index,
                SequencingNextParticipantDecision.from_payload(
                    cast(SequencingNextParticipantDecisionPayload, event.payload)
                ),
            )
        )
    snapshot_indices = tuple(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "battle_shock_step_snapshot_created"
        and isinstance(event.payload, dict)
        and event.payload.get("game_id") == state.game_id
        and event.payload.get("battle_round") == state.battle_round
        and event.payload.get("active_player_id") == command_state.active_player_id
    )
    if len(snapshot_indices) != 1:
        raise GameLifecycleError("Battle-shock sequencing snapshot authority is ambiguous.")
    selected_participant_ids: list[str] = []
    remaining_participant_ids = list(participant_by_id)
    for event_index, sequencing_decision in matching_events:
        if event_index <= snapshot_indices[0]:
            raise GameLifecycleError("Battle-shock sequencing event escaped its snapshot boundary.")
        if sequencing_decision.previously_selected_participant_ids != tuple(
            selected_participant_ids
        ) or sequencing_decision.remaining_participant_ids != tuple(remaining_participant_ids):
            raise GameLifecycleError("Battle-shock sequencing selection prefix drifted.")
        matching_records = tuple(
            record
            for record in decisions.records
            if record.request.request_id == sequencing_decision.request_id
            and record.result.result_id == sequencing_decision.result_id
        )
        if len(matching_records) != 1:
            raise GameLifecycleError("Battle-shock sequencing lacks one decision record.")
        record = matching_records[0]
        remaining_participants = tuple(
            participant_by_id[participant_id] for participant_id in remaining_participant_ids
        )
        expected_request = create_select_next_sequencing_participant_request(
            request_id=record.request.request_id,
            context=context,
            previously_selected_participant_ids=tuple(selected_participant_ids),
            remaining_participants=remaining_participants,
        )
        if (
            record.request != expected_request
            or apply_select_next_sequencing_participant_from_request(
                request=record.request,
                result=record.result,
            )
            != sequencing_decision
        ):
            raise GameLifecycleError("Battle-shock sequencing authority drifted.")
        selected_participant_ids.append(sequencing_decision.selected_participant_id)
        remaining_participant_ids.remove(sequencing_decision.selected_participant_id)

    selected_unit_ids = tuple(
        unit_id_by_participant_id[participant_id] for participant_id in selected_participant_ids
    )
    current_order = command_state.battle_shock_candidate_order_unit_ids
    if current_order == selected_unit_ids[:-1] and selected_unit_ids:
        command_state = command_state.with_battle_shock_candidate_order(selected_unit_ids)
        state.replace_command_step_state(command_state)
        current_order = command_state.battle_shock_candidate_order_unit_ids
    elif current_order != selected_unit_ids:
        auto_completed_order = (
            (*selected_unit_ids, unit_id_by_participant_id[remaining_participant_ids[0]])
            if len(remaining_participant_ids) == 1
            else selected_unit_ids
        )
        if current_order != auto_completed_order:
            raise GameLifecycleError("Battle-shock sequencing state prefix drifted.")

    if len(command_state.completed_battle_shock_test_request_ids) < len(current_order):
        return None
    if len(command_state.completed_battle_shock_test_request_ids) != len(current_order):
        raise GameLifecycleError("Battle-shock sequencing completion prefix drifted.")
    if len(remaining_participant_ids) == 1:
        if current_order == selected_unit_ids:
            command_state = command_state.with_battle_shock_candidate_order(
                (*current_order, unit_id_by_participant_id[remaining_participant_ids[0]])
            )
            state.replace_command_step_state(command_state)
        return None
    if not remaining_participant_ids:
        return None

    remaining_participants = tuple(
        participant_by_id[participant_id] for participant_id in remaining_participant_ids
    )
    pending_requests = decisions.queue.pending_requests
    if pending_requests:
        if len(pending_requests) != 1:
            raise GameLifecycleError("Battle-shock sequencing pending queue is ambiguous.")
        request = pending_requests[0]
        expected = create_select_next_sequencing_participant_request(
            request_id=request.request_id,
            context=context,
            previously_selected_participant_ids=tuple(selected_participant_ids),
            remaining_participants=remaining_participants,
        )
        if request != expected:
            raise GameLifecycleError("Battle-shock sequencing pending request drifted.")
    else:
        request = create_select_next_sequencing_participant_request(
            request_id=state.next_decision_request_id(),
            context=context,
            previously_selected_participant_ids=tuple(selected_participant_ids),
            remaining_participants=remaining_participants,
        )
        decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.COMMAND.value,
            "phase_body_status": "battle_shock_next_test_selection_pending",
            "pending_request_id": request.request_id,
            "selected_candidate_count": len(selected_participant_ids),
            "remaining_candidate_count": len(remaining_participant_ids),
        },
    )


def _command_battle_shock_sequencing_context(
    *,
    state: GameState,
) -> SequencingConflictContext:
    active_player_id = _active_player_id(state)
    conflict_id = (
        f"command-battle-shock-order:{state.game_id}:"
        f"round-{state.battle_round:02d}:{active_player_id}"
    )
    timing_window = TimingWindow(
        window_id=f"timing-window:{conflict_id}",
        descriptor=TimingWindowDescriptor(
            descriptor_id=_COMMAND_BATTLE_SHOCK_SEQUENCING_DESCRIPTOR_ID,
            trigger_kind=TimingTriggerKind.DURING_PHASE,
            source_rule_id=COMMAND_BATTLE_SHOCK_SOURCE_RULE_ID,
            phase=BattlePhase.COMMAND,
            source_step=CommandPhaseStep.BATTLE_SHOCK.value,
            metadata={"candidate_scope": "required_command_battle_shock_tests"},
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
    )
    return SequencingConflictContext(
        conflict_id=conflict_id,
        game_id=state.game_id,
        timing_window=timing_window,
        player_ids=state.player_ids,
        active_player_id=active_player_id,
    )


def _command_battle_shock_sequencing_participants(
    *,
    active_player_id: str,
    candidates: tuple[_cbsc.CommandBattleShockCandidate, ...],
) -> tuple[SequencingParticipant, ...]:
    return tuple(
        SequencingParticipant(
            participant_id=_command_battle_shock_participant_id(candidate),
            player_id=active_player_id,
            source_rule_id=COMMAND_BATTLE_SHOCK_SOURCE_RULE_ID,
            payload=validate_json_value(candidate.to_payload()),
        )
        for candidate in candidates
    )


def _command_battle_shock_participant_id(
    candidate: _cbsc.CommandBattleShockCandidate,
) -> str:
    return f"command-battle-shock-test:{candidate.unit_instance_id}"


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle state requires an active player.")
    return state.active_player_id


def _command_step_state(state: GameState) -> CommandStepState:
    if state.command_step_state is None:
        raise GameLifecycleError("Command phase requires CommandStepState.")
    return state.command_step_state
