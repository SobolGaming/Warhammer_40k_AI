from __future__ import annotations

from warhammer40k_core.engine import command_battle_shock_candidates as _cbsc
from warhammer40k_core.engine.battle_shock_model_authority import battle_shock_model_ids
from warhammer40k_core.engine.command_battle_shock_history import (
    COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
)
from warhammer40k_core.engine.command_points import CommandPhaseStep
from warhammer40k_core.engine.command_step_authority import (
    command_step_state as _command_step_state,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
)
from warhammer40k_core.engine.timing_batch_runtime import (
    select_timing_participant,
    timing_batches_for_context,
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
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=candidate.unit_instance_id)
        try:
            battle_shock_model_ids(
                rules_unit=rules_unit,
                battlefield=battlefield,
                state=state,
                allow_off_battlefield=True,
            )
        except GameLifecycleError as exc:
            return LifecycleStatus.unsupported(
                stage=GameLifecycleStage.BATTLE,
                message=f"Command Battle-shock model presence is not supported: {exc}",
                payload={
                    "source_rule_id": COMMAND_BATTLE_SHOCK_SOURCE_RULE_ID,
                    "section_id": "08.03",
                    "unit_instance_id": candidate.unit_instance_id,
                    "component_unit_instance_ids": list(candidate.component_unit_instance_ids),
                    "candidate_reasons": [reason.value for reason in candidate.eligibility_reasons],
                    "unsupported_scope": "battle_shock_model_presence",
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
    context = command_battle_shock_sequencing_context(
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=command_state.active_player_id,
        player_ids=state.player_ids,
    )
    participants = command_battle_shock_sequencing_participants(
        active_player_id=command_state.active_player_id,
        candidates=candidates,
    )
    history = timing_batches_for_context(decisions, context)
    current_order = command_state.battle_shock_candidate_order_unit_ids
    completed_count = len(command_state.completed_battle_shock_test_request_ids)
    completed_ids = tuple(
        f"command-battle-shock-test:{unit_id}" for unit_id in current_order[:completed_count]
    )
    completion = None
    if history:
        batch = history[-1]
        if len(history) != 1 or batch.participants != participants or batch.deferred_participants:
            raise GameLifecycleError("Battle-shock timing population drifted from its snapshot.")
        retained_ids = batch.completed_participant_ids
        if batch.selected_participant_id in completed_ids:
            completion = batch.selected_participant_id
            retained_ids = (*retained_ids, completion)
        if retained_ids != completed_ids:
            raise GameLifecycleError("Battle-shock timing completion prefix drifted.")
    elif completed_ids or current_order:
        raise GameLifecycleError("Battle-shock ordering lacks its original timing batch.")
    pending = decisions.queue.pending_requests
    if len(pending) > 1:
        raise GameLifecycleError("Battle-shock sequencing pending queue is ambiguous.")
    selection = select_timing_participant(
        decisions=decisions,
        context=context,
        unresolved_participants=participants,
        next_request_id=(lambda: pending[0].request_id)
        if pending
        else state.next_decision_request_id,
        completed_participant_id=completion,
    )
    if selection.request is not None:
        if pending:
            if pending != (selection.request,):
                raise GameLifecycleError("Battle-shock sequencing pending request drifted.")
        else:
            decisions.request_decision(selection.request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=selection.request,
            payload={
                "phase": BattlePhase.COMMAND.value,
                "phase_body_status": "battle_shock_next_test_selection_pending",
                "pending_request_id": selection.request.request_id,
                "selected_candidate_count": len(current_order),
                "remaining_candidate_count": len(candidates) - len(current_order),
            },
        )
    if selection.participant_id is not None:
        unit_id_by_participant = {
            _command_battle_shock_participant_id(candidate): candidate.unit_instance_id
            for candidate in candidates
        }
        expected_order = (
            *current_order[:completed_count],
            unit_id_by_participant[selection.participant_id],
        )
        if current_order == expected_order[:-1]:
            state.replace_command_step_state(
                command_state.with_battle_shock_candidate_order(expected_order)
            )
        elif current_order != expected_order:
            raise GameLifecycleError("Battle-shock sequencing state prefix drifted.")
    elif completed_count != len(candidates):
        raise GameLifecycleError("Battle-shock timing batch completed before its required tests.")
    return None


def command_battle_shock_sequencing_context(
    *,
    game_id: str,
    battle_round: int,
    active_player_id: str,
    player_ids: tuple[str, ...],
) -> SequencingConflictContext:
    conflict_id = (
        f"command-battle-shock-order:{game_id}:round-{battle_round:02d}:{active_player_id}"
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
        game_id=game_id,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase=BattlePhase.COMMAND,
    )
    return SequencingConflictContext(
        conflict_id=conflict_id,
        game_id=game_id,
        timing_window=timing_window,
        player_ids=player_ids,
        active_player_id=active_player_id,
    )


def command_battle_shock_sequencing_participants(
    *,
    active_player_id: str,
    candidates: tuple[_cbsc.CommandBattleShockCandidate, ...],
) -> tuple[SequencingParticipant, ...]:
    return tuple(
        SequencingParticipant(
            participant_id=_command_battle_shock_participant_id(candidate),
            player_id=active_player_id,
            source_rule_id=COMMAND_BATTLE_SHOCK_SOURCE_RULE_ID,
            requirement=SequencingRequirement.MANDATORY,
            payload=validate_json_value(candidate.to_payload()),
        )
        for candidate in candidates
    )


def _command_battle_shock_participant_id(
    candidate: _cbsc.CommandBattleShockCandidate,
) -> str:
    return f"command-battle-shock-test:{candidate.unit_instance_id}"
