"""Source-selected 03.02.01 rollback of an unsuccessful move-type setup.

The complete immutable observation is retained in Order 97 selected-sources.json.
These are audit identities, not a newly claimed runtime source package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement_state import MovementPhaseState

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState

SOURCE_ROW_ID: Final = "rule:03:03.02.01:1"
SOURCE_SHA256: Final = "28bc62101a93e202a54e55347fd55736350d1afd0fb33eec725ee818b01d48e8"
_FAILED_EVENTS: Final = frozenset(
    {
        "disembark_placement_invalid",
        "combat_disembark_placement_invalid",
        "reinforcement_placement_invalid",
    }
)


def restore_failed_setup_selection(
    *, state: GameState, decisions: DecisionController, result: DecisionResult
) -> None:
    from warhammer40k_core.engine.phases.movement_handler import request_movement_unit_selection

    before = state.movement_phase_state
    if before is None or before.active_selection is None:
        raise GameLifecycleError("Failed setup requires active movement authority.")
    invalid_event = decisions.event_log.records[-1]
    if invalid_event.event_type not in _FAILED_EVENTS:
        raise GameLifecycleError("Failed setup requires a recorded invalid placement.")
    selection = before.active_selection
    after = before.without_failed_setup_selection(selection.unit_instance_id)
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": selection.unit_instance_id,
        "selection_request_id": selection.request_id,
        "selection_result_id": selection.result_id,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "invalid_event_id": invalid_event.event_id,
        "source_observation_row_id": SOURCE_ROW_ID,
        "source_observation_sha256": SOURCE_SHA256,
        "movement_phase_state_before": validate_json_value(before.to_payload()),
        "movement_phase_state_after": validate_json_value(after.to_payload()),
    }
    state.replace_movement_phase_state(after)
    decisions.event_log.append("movement_setup_failed", payload)
    request_movement_unit_selection(state=state, decisions=decisions)


def validate_failed_setup_history(
    *, state: GameState, events: tuple[EventRecord, ...], records: tuple[DecisionRecord, ...]
) -> None:
    """Authenticate rollback receipts and the subsequent selection rights."""
    if not any(
        event.event_type in _FAILED_EVENTS or event.event_type == "movement_setup_failed"
        for event in events
    ):
        return
    from warhammer40k_core.engine.fight_model_authority_history import (
        build_model_authority_timeline,
    )
    from warhammer40k_core.engine.movement_failed_setup_authority import (
        validate_failed_placement_authority,
    )
    from warhammer40k_core.engine.movement_proposals import (
        MovementProposalRequest,
        PlacementProposalPayload,
        PlacementProposalPayloadPayload,
        ProposalKind,
    )
    from warhammer40k_core.engine.movement_selection_history import MovementSelectionHistory
    from warhammer40k_core.engine.phases.movement_model import MovementPhaseStatePayload

    by_result = {record.result.result_id: record for record in records}
    by_event = {event.event_id: index for index, event in enumerate(events)}
    history = MovementSelectionHistory(records=records, events=events, game_id=state.game_id)
    model_history = (
        build_model_authority_timeline(state=state, event_records=events, decision_records=records)
        if any(event.event_type == "movement_setup_failed" for event in events)
        else None
    )
    affected: dict[tuple[int, str, str], bool] = {}
    for index, event in enumerate(events):
        payload = event.payload
        history.observe(event=event, prior_event=None if index == 0 else events[index - 1])
        if event.event_type in _FAILED_EVENTS and (
            index + 1 >= len(events) or events[index + 1].event_type != "movement_setup_failed"
        ):
            raise GameLifecycleError("Failed move-type setup has no selection rollback receipt.")
        if event.event_type == "movement_setup_failed":
            if not isinstance(payload, dict):
                raise GameLifecycleError("Failed setup receipt requires an object.")
            before_raw = payload.get("movement_phase_state_before")
            if not isinstance(before_raw, dict):
                raise GameLifecycleError("Failed setup receipt requires its prior selection.")
            before = MovementPhaseState.from_payload(cast(MovementPhaseStatePayload, before_raw))
            history.assert_projection(before)
            selection = before.active_selection
            if selection is None:
                raise GameLifecycleError("Failed setup receipt lost its active selection.")
            unit_id = selection.unit_instance_id
            after = before.without_failed_setup_selection(unit_id)
            selected = by_result.get(selection.result_id)
            rejected = by_result.get(_string(payload, "result_id"))
            index = by_event[event.event_id]
            if index < 2 or rejected is None or selected is None:
                raise GameLifecycleError("Failed setup receipt has no decision authority.")
            invalid_event = events[index - 1]
            recorded_event = events[index - 2]
            if (
                recorded_event.event_type != "decision_recorded"
                or recorded_event.payload != validate_json_value(rejected.to_payload())
            ):
                raise GameLifecycleError("Failed setup rejected decision closure drift.")
            expected = {
                "game_id": state.game_id,
                "battle_round": before.battle_round,
                "active_player_id": before.active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": unit_id,
                "selection_request_id": selection.request_id,
                "selection_result_id": selection.result_id,
                "request_id": rejected.request.request_id,
                "result_id": rejected.result.result_id,
                "invalid_event_id": invalid_event.event_id,
                "source_observation_row_id": SOURCE_ROW_ID,
                "source_observation_sha256": SOURCE_SHA256,
                "movement_phase_state_before": validate_json_value(before.to_payload()),
                "movement_phase_state_after": validate_json_value(after.to_payload()),
            }
            if payload != expected or invalid_event.event_type not in _FAILED_EVENTS:
                raise GameLifecycleError("Failed setup receipt source or rollback drift.")
            invalid = invalid_event.payload
            if (
                not isinstance(invalid, dict)
                or invalid.get("request_id") != rejected.request.request_id
                or invalid.get("result_id") != rejected.result.result_id
                or invalid.get("unit_instance_id") != unit_id
                or selected.request.decision_type != "select_movement_unit"
                or selected.request.request_id != selection.request_id
                or selected.request.actor_id != before.active_player_id
                or not isinstance(selected.result.payload, dict)
                or selected.result.payload.get("unit_instance_id") != unit_id
                or rejected.request.decision_type != "submit_placement_proposal"
            ):
                raise GameLifecycleError("Failed setup receipt decision or diagnostic drift.")
            proposal = MovementProposalRequest.from_decision_request_payload(
                rejected.request.payload
            )
            submission = PlacementProposalPayload.from_payload(
                cast(PlacementProposalPayloadPayload, rejected.result.payload)
            )
            action_record = by_result.get(proposal.source_decision_result_id)
            history.assert_action_order(
                selection=selection, action=action_record, rejected=rejected, mutation_index=index
            )
            if (
                proposal.unit_instance_id != unit_id
                or proposal.game_id != state.game_id
                or proposal.battle_round != before.battle_round
                or proposal.actor_id != before.active_player_id
                or proposal.phase != BattlePhase.MOVEMENT.value
                or proposal.proposal_kind
                not in {
                    ProposalKind.DISEMBARK,
                    ProposalKind.REINFORCEMENT,
                    ProposalKind.DEEP_STRIKE,
                    ProposalKind.STRATEGIC_RESERVES,
                }
                or not submission.validation_result_for_request(proposal).is_valid
                or action_record is None
                or action_record.request.request_id != proposal.source_decision_request_id
                or action_record.request.decision_type != "select_movement_action"
                or not isinstance(action_record.result.payload, dict)
                or action_record.result.payload.get("unit_instance_id") != unit_id
                or action_record.result.payload.get("movement_phase_action")
                != ("disembark" if proposal.proposal_kind is ProposalKind.DISEMBARK else "ingress")
            ):
                raise GameLifecycleError("Failed setup receipt placement context drift.")
            validate_failed_placement_authority(
                state=state,
                proposal=proposal,
                submitted=submission,
                rejected=rejected,
                action=action_record,
                invalid=invalid_event,
                events=events,
                records=records,
                event_index=by_event,
                rollback_order=index,
                model_history=model_history,
            )
            affected[(before.battle_round, before.active_player_id, unit_id)] = False
            history.rollback(before)
        elif event.event_type == "movement_unit_selected" and isinstance(payload, dict):
            round_number = payload.get("battle_round")
            if type(round_number) is not int:
                raise GameLifecycleError("Failed setup reselection requires a round number.")
            key = (
                round_number,
                _string(payload, "active_player_id"),
                _string(payload, "unit_instance_id"),
            )
            if key in affected:
                selected = by_result.get(_string(payload, "result_id"))
                if (
                    selected is None
                    or selected.request.decision_type != "select_movement_unit"
                    or selected.request.request_id != payload.get("request_id")
                    or selected.request.actor_id != key[1]
                    or not isinstance(selected.result.payload, dict)
                    or selected.result.payload.get("unit_instance_id") != key[2]
                    or affected[key]
                ):
                    raise GameLifecycleError("Failed setup reselection decision drift.")
                affected[key] = True
    current = state.movement_phase_state
    if current is not None:
        if any(
            round_number == current.battle_round and player_id == current.active_player_id
            for round_number, player_id, _ in affected
        ):
            history.assert_projection(current)
        for (round_number, player_id, unit_id), selected_after in affected.items():
            if (
                round_number == current.battle_round
                and player_id == current.active_player_id
                and (unit_id in current.selected_unit_ids) is not selected_after
            ):
                raise GameLifecycleError("Failed setup current selection history drift.")


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Failed setup receipt requires string {key}.")
    return value
