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
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingDecision,
    SequencingDecisionPayload,
    SequencingParticipant,
    apply_sequencing_decision_from_request,
    create_sequencing_decision_request,
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
    placed_model_ids = set(battlefield.placed_model_ids())
    for candidate in command_state.battle_shock_candidate_inventory:
        if candidate.test_reason is None:
            continue
        rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=candidate.unit_instance_id,
        )
        alive_model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
        if alive_model_ids and alive_model_ids <= placed_model_ids:
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
    if command_state.battle_shock_candidate_order_unit_ids:
        return None
    candidates = tuple(
        candidate
        for candidate in command_state.battle_shock_candidate_inventory
        if candidate.test_reason is not None
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        raise GameLifecycleError("Battle-shock trivial candidate order was not fixed at entry.")
    context = _command_battle_shock_sequencing_context(state=state)
    participants = _command_battle_shock_sequencing_participants(
        active_player_id=command_state.active_player_id,
        candidates=candidates,
    )
    matching_events: list[tuple[int, SequencingDecision]] = []
    for event_index, event in enumerate(decisions.event_log.records):
        if event.event_type != "sequencing_order_resolved":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Battle-shock sequencing event payload is malformed.")
        if event.payload.get("conflict_id") != context.conflict_id:
            continue
        matching_events.append(
            (
                event_index,
                SequencingDecision.from_payload(cast(SequencingDecisionPayload, event.payload)),
            )
        )
    if not matching_events:
        pending_requests = decisions.queue.pending_requests
        if pending_requests:
            if len(pending_requests) != 1:
                raise GameLifecycleError("Battle-shock sequencing pending queue is ambiguous.")
            request = pending_requests[0]
            expected = create_sequencing_decision_request(
                request_id=request.request_id,
                context=context,
                participants=participants,
            )
            if request != expected:
                raise GameLifecycleError("Battle-shock sequencing pending request drifted.")
        else:
            request = create_sequencing_decision_request(
                request_id=state.next_decision_request_id(),
                context=context,
                participants=participants,
            )
            decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "phase_body_status": "battle_shock_test_order_pending",
                "pending_request_id": request.request_id,
            },
        )
    if len(matching_events) != 1:
        raise GameLifecycleError("Battle-shock sequencing decision is duplicated.")
    event_index, sequencing_decision = matching_events[0]
    snapshot_indices = tuple(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "battle_shock_step_snapshot_created"
        and isinstance(event.payload, dict)
        and event.payload.get("game_id") == state.game_id
        and event.payload.get("battle_round") == state.battle_round
        and event.payload.get("active_player_id") == command_state.active_player_id
    )
    if len(snapshot_indices) != 1 or event_index <= snapshot_indices[0]:
        raise GameLifecycleError("Battle-shock sequencing event escaped its snapshot boundary.")
    matching_records = tuple(
        record
        for record in decisions.records
        if record.request.request_id == sequencing_decision.request_id
        and record.result.result_id == sequencing_decision.result_id
    )
    if len(matching_records) != 1:
        raise GameLifecycleError("Battle-shock sequencing lacks one decision record.")
    record = matching_records[0]
    expected_request = create_sequencing_decision_request(
        request_id=record.request.request_id,
        context=context,
        participants=participants,
    )
    if (
        record.request != expected_request
        or apply_sequencing_decision_from_request(
            request=record.request,
            result=record.result,
        )
        != sequencing_decision
    ):
        raise GameLifecycleError("Battle-shock sequencing authority drifted.")
    unit_id_by_participant_id = {
        _command_battle_shock_participant_id(candidate): candidate.unit_instance_id
        for candidate in candidates
    }
    if set(sequencing_decision.ordered_participant_ids) != set(unit_id_by_participant_id):
        raise GameLifecycleError("Battle-shock sequencing participant inventory drifted.")
    state.replace_command_step_state(
        command_state.with_battle_shock_candidate_order(
            tuple(
                unit_id_by_participant_id[participant_id]
                for participant_id in sequencing_decision.ordered_participant_ids
            )
        )
    )
    return None


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
