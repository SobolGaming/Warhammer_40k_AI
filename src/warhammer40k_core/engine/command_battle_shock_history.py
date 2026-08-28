from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import (
    DiceError,
    DiceRollState,
    DiceRollStatePayload,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
    BattleShockTestReason,
    BattleShockTestRequest,
    BattleShockTestRequestPayload,
)
from warhammer40k_core.engine.battle_shock_state_history import (
    validate_battle_shock_state_history,
)
from warhammer40k_core.engine.command_battle_shock_candidates import (
    CommandBattleShockCandidate,
    CommandBattleShockCandidatePayload,
    command_battle_shock_request_id,
    validate_command_battle_shock_candidate_inventory,
)
from warhammer40k_core.engine.command_battle_shock_history_helpers import (
    candidate_by_id,
    ordered_candidates_by_request_id,
    payload_int,
    payload_object,
    payload_string,
    raw_result_request_id,
    sequencing_request_conflict_id,
    validate_historical_candidate_order,
    validate_historical_request_context,
    validate_historical_sequencing_request,
    validate_pending_order_restore_authority,
    validate_request_against_candidate,
)
from warhammer40k_core.engine.command_battle_shock_runtime_authority import (
    validate_historical_command_candidate_inventory,
)
from warhammer40k_core.engine.command_core_cp_history import (
    expected_restored_core_command_occurrence_keys,
    validate_core_command_point_anchor,
)
from warhammer40k_core.engine.command_insane_bravery_authority import (
    validate_command_auto_pass_history,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecord,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    rules_unit_identity_ids,
    rules_unit_views_from_armies,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_candidate_by_id = candidate_by_id
_ordered_candidates_by_request_id = ordered_candidates_by_request_id
_payload_int = payload_int
_payload_object = payload_object
_payload_string = payload_string
_raw_result_request_id = raw_result_request_id
_sequencing_request_conflict_id = sequencing_request_conflict_id
_validate_historical_candidate_order = validate_historical_candidate_order
_validate_historical_request_context = validate_historical_request_context
_validate_historical_sequencing_request = validate_historical_sequencing_request
_validate_pending_candidate_order_restore_authority = validate_pending_order_restore_authority
_validate_request_against_candidate = validate_request_against_candidate

__all__ = (
    "_sequencing_request_conflict_id",
    "_validate_historical_sequencing_request",
)

COMMAND_BATTLE_SHOCK_RESOLVED_EVENT_TYPE = "battle_shock_test_resolved"
COMMAND_BATTLE_SHOCK_SNAPSHOT_EVENT_TYPE = "battle_shock_step_snapshot_created"
COMMAND_BATTLE_SHOCK_COMPLETED_EVENT_TYPE = "battle_shock_step_completed"
COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND = "command_battle_shock"
_COMMAND_SNAPSHOT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "battle_shock_phase_start_unit_ids",
        "battle_shock_candidate_inventory",
    }
)
_COMMAND_STEP_ANCHOR_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "command_point_gains",
    }
)
_COMMAND_RESULT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "source_kind",
        "battle_shock_result",
        "auto_passed",
        "state_update",
        "cleared_battle_shocked_unit_ids",
    }
)
_COMMAND_COMPLETION_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "battle_shock_test_count",
        "battle_shock_results",
        "completed_battle_shock_test_request_ids",
    }
)


def requires_command_prevalidation(*, state: GameState, request: DecisionRequest) -> bool:
    payload = request.payload
    if (
        state.current_battle_phase is not BattlePhase.COMMAND
        or request.decision_type != DICE_REROLL_DECISION_TYPE
        or not isinstance(payload, dict)
        or not isinstance(payload.get("battle_shock_context"), dict)
        or state.command_step_state is None
    ):
        return False
    context = cast(dict[str, JsonValue], payload["battle_shock_context"])
    retained_request = context.get("battle_shock_test_request")
    in_flight = state.command_step_state.battle_shock_in_flight_test_request
    return context.get("source_kind") == COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND or (
        in_flight is not None and retained_request == in_flight.to_payload()
    )


def validate_command_battle_shock_state_snapshot(*, state: GameState) -> None:
    command_state = state.command_step_state
    if command_state is None or command_state.current_step.value != "battle_shock":
        return
    current_canonical_ids = {
        rules_unit.unit_instance_id
        for rules_unit in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if rules_unit.owner_player_id == command_state.active_player_id
    }
    historical_canonical_ids = {
        record.attached_unit_instance_id
        for record in state.starting_attached_unit_records
        if record.player_id == command_state.active_player_id
    }
    allowed_canonical_ids = current_canonical_ids | historical_canonical_ids
    request = command_state.battle_shock_in_flight_test_request
    if request is not None:
        if request.game_id != state.game_id:
            raise GameLifecycleError("Command Battle-shock in-flight test game_id drift.")
        if request.reason not in {
            BattleShockTestReason.COMMAND_PHASE_REQUIRED,
            BattleShockTestReason.BELOW_STARTING_STRENGTH_FORCED,
        }:
            raise GameLifecycleError("Command Battle-shock in-flight test reason drift.")
        expected_request_id = command_battle_shock_request_id(
            battle_round=command_state.battle_round,
            active_player_id=command_state.active_player_id,
            unit_instance_id=request.unit_instance_id,
            reason=request.reason,
        )
        if request.request_id != expected_request_id:
            raise GameLifecycleError("Command Battle-shock in-flight test request_id drift.")
        if request.unit_instance_id not in allowed_canonical_ids:
            raise GameLifecycleError("Command Battle-shock in-flight test unit is not canonical.")
        _validate_request_against_candidate(
            request=request,
            candidate=_candidate_by_id(
                command_state.battle_shock_candidate_inventory,
                request.unit_instance_id,
            ),
        )
    if not set(command_state.battle_shock_phase_start_unit_ids) <= allowed_canonical_ids:
        raise GameLifecycleError("Command Battle-shock phase-start unit is not canonical.")
    if (
        not {
            candidate.unit_instance_id
            for candidate in command_state.battle_shock_candidate_inventory
        }
        <= allowed_canonical_ids
    ):
        raise GameLifecycleError("Command Battle-shock candidate unit is not canonical.")


def record_command_battle_shock_snapshot(*, state: GameState, event_log: EventLog) -> None:
    validate_command_battle_shock_state_snapshot(state=state)
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Command Battle-shock snapshot requires EventLog.")
    event_log.append(
        COMMAND_BATTLE_SHOCK_SNAPSHOT_EVENT_TYPE,
        _command_battle_shock_snapshot_payload(state=state),
    )


def validate_command_battle_shock_snapshot_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> int:
    validate_command_battle_shock_state_snapshot(state=state)
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Command Battle-shock snapshot authority requires event records.")
    command_state = state.command_step_state
    if command_state is None or command_state.current_step.value != "battle_shock":
        raise GameLifecycleError(
            "Command Battle-shock snapshot authority requires Battle-shock step."
        )
    expected = _command_battle_shock_snapshot_payload(state=state)
    matching: list[tuple[int, dict[str, JsonValue]]] = []
    for event_index, event in enumerate(event_records):
        if event.event_type != COMMAND_BATTLE_SHOCK_SNAPSHOT_EVENT_TYPE:
            continue
        payload = _payload_object(event.payload)
        if _payload_string(payload, "game_id") != state.game_id:
            continue
        if _payload_int(payload, "battle_round") != state.battle_round:
            continue
        if _payload_string(payload, "active_player_id") != command_state.active_player_id:
            continue
        if frozenset(payload) != _COMMAND_SNAPSHOT_PAYLOAD_KEYS:
            raise GameLifecycleError("Command Battle-shock snapshot event payload shape drift.")
        if _payload_string(payload, "phase") != BattlePhase.COMMAND.value:
            raise GameLifecycleError("Command Battle-shock snapshot event phase drift.")
        matching.append((event_index, payload))
    if len(matching) != 1:
        raise GameLifecycleError(
            "Command Battle-shock step requires exactly one snapshot authority event."
        )
    if matching[0][1] != expected:
        raise GameLifecycleError("Command Battle-shock snapshot authority drift.")
    return matching[0][0]


def _command_battle_shock_snapshot_payload(*, state: GameState) -> dict[str, JsonValue]:
    command_state = state.command_step_state
    if command_state is None or command_state.current_step.value != "battle_shock":
        raise GameLifecycleError("Command Battle-shock snapshot requires Battle-shock step.")
    return cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": command_state.active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "battle_shock_phase_start_unit_ids": list(
                    command_state.battle_shock_phase_start_unit_ids
                ),
                "battle_shock_candidate_inventory": [
                    candidate.to_payload()
                    for candidate in command_state.battle_shock_candidate_inventory
                ],
            }
        ),
    )


def ordered_completed_command_battle_shock_results(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> tuple[BattleShockResult, ...]:
    """Rebuild the exact ordered Command-step result set from authoritative events."""
    snapshot_index = validate_command_battle_shock_snapshot_authority(
        state=state,
        event_records=event_records,
    )
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Command Battle-shock history requires decision records.")
    command_state = state.command_step_state
    if command_state is None:
        raise GameLifecycleError("Command Battle-shock history requires command state.")
    game_id = state.game_id
    battle_round = state.battle_round
    active_player_id = command_state.active_player_id
    completed_test_request_ids = command_state.completed_battle_shock_test_request_ids
    candidates_by_request_id = _ordered_candidates_by_request_id(command_state)
    if len(set(completed_test_request_ids)) != len(completed_test_request_ids):
        raise GameLifecycleError(
            "Command Battle-shock history completed request IDs must be unique."
        )
    completed_ids = set(completed_test_request_ids)
    if not completed_ids <= set(candidates_by_request_id):
        raise GameLifecycleError("Command Battle-shock history completed request is not required.")

    result_by_request_id: dict[
        str,
        tuple[BattleShockResult, int, dict[str, JsonValue]],
    ] = {}
    for event_index, event in enumerate(
        event_records[snapshot_index + 1 :],
        start=snapshot_index + 1,
    ):
        if event.event_type != COMMAND_BATTLE_SHOCK_RESOLVED_EVENT_TYPE:
            continue
        payload = _payload_object(event.payload)
        raw_result_payload = payload.get("battle_shock_result")
        if not isinstance(raw_result_payload, dict):
            continue
        raw_request_payload = raw_result_payload.get("request")
        if not isinstance(raw_request_payload, dict):
            continue
        raw_request_id = raw_request_payload.get("request_id")
        if type(raw_request_id) is not str or raw_request_id not in candidates_by_request_id:
            continue
        if _payload_string(payload, "phase") != BattlePhase.COMMAND.value:
            raise GameLifecycleError("Command Battle-shock resolved event phase drift.")
        if _payload_string(payload, "game_id") != game_id:
            raise GameLifecycleError("Command Battle-shock resolved event game_id drift.")
        if _payload_int(payload, "battle_round") != battle_round:
            raise GameLifecycleError("Command Battle-shock resolved event round drift.")
        if _payload_string(payload, "active_player_id") != active_player_id:
            raise GameLifecycleError("Command Battle-shock resolved event active player drift.")
        if frozenset(payload) != _COMMAND_RESULT_PAYLOAD_KEYS:
            raise GameLifecycleError("Command Battle-shock resolved event payload shape drift.")
        if type(payload["auto_passed"]) is not bool:
            raise GameLifecycleError(
                "Command Battle-shock resolved event auto_passed must be a bool."
            )
        _payload_string(payload, "state_update")
        cleared_ids = payload["cleared_battle_shocked_unit_ids"]
        if not isinstance(cleared_ids, list) or any(
            type(unit_id) is not str or not unit_id.strip() for unit_id in cleared_ids
        ):
            raise GameLifecycleError("Command Battle-shock resolved event cleared unit IDs drift.")
        if len(cleared_ids) != len(set(cast(list[str], cleared_ids))):
            raise GameLifecycleError(
                "Command Battle-shock resolved event cleared unit IDs are duplicated."
            )
        result_payload = _payload_object(raw_result_payload)
        result = BattleShockResult.from_payload(cast(BattleShockResultPayload, result_payload))
        if result_payload != validate_json_value(result.to_payload()):
            raise GameLifecycleError(
                "Command Battle-shock resolved event result payload shape drift."
            )
        request_id = result.request.request_id
        _validate_request_against_candidate(
            request=result.request,
            candidate=candidates_by_request_id[request_id],
        )
        if request_id not in completed_ids:
            raise GameLifecycleError(
                "Command Battle-shock resolved event request is not completed."
            )
        if request_id in result_by_request_id:
            raise GameLifecycleError("Command Battle-shock resolved event is duplicated.")
        _validate_result_state_update(
            state=state,
            command_state_phase_start_ids=set(command_state.battle_shock_phase_start_unit_ids),
            result=result,
            payload=payload,
            cleared_ids=tuple(cast(list[str], cleared_ids)),
        )
        result_by_request_id[request_id] = (result, event_index, payload)

    result_request_ids = tuple(result_by_request_id)
    if result_request_ids != completed_test_request_ids:
        raise GameLifecycleError(
            "Command Battle-shock resolved events must equal the completed request prefix."
        )
    ordered_rows = tuple(
        result_by_request_id[request_id] for request_id in completed_test_request_ids
    )
    _validate_ordered_result_event_prefix(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        snapshot_index=snapshot_index,
        ordered_rows=ordered_rows,
        battle_round=battle_round,
        active_player_id=active_player_id,
        phase_start_battle_shocked_unit_ids=(command_state.battle_shock_phase_start_unit_ids),
    )
    return tuple(result for result, _event_index, _payload in ordered_rows)


def _validate_result_state_update(
    *,
    state: GameState,
    command_state_phase_start_ids: set[str],
    result: BattleShockResult,
    payload: dict[str, JsonValue],
    cleared_ids: tuple[str, ...],
) -> None:
    state_update = _payload_string(payload, "state_update")
    auto_passed = payload["auto_passed"]
    if auto_passed is True and not result.passed:
        raise GameLifecycleError("Command Battle-shock auto-pass result must pass.")
    shocked_at_start = result.request.unit_instance_id in command_state_phase_start_ids
    if result.passed and shocked_at_start:
        if state_update != "cleared_battle_shocked" or not cleared_ids:
            raise GameLifecycleError("Command Battle-shock successful clear state drift.")
        if not set(cleared_ids) <= set(
            rules_unit_identity_ids(
                state=state,
                unit_instance_id=result.request.unit_instance_id,
            )
        ):
            raise GameLifecycleError("Command Battle-shock cleared identity drift.")
        return
    if result.passed:
        if state_update != "not_required" or cleared_ids:
            raise GameLifecycleError("Command Battle-shock successful state update drift.")
        return
    if cleared_ids:
        raise GameLifecycleError("Failed Command Battle-shock result cannot clear state.")
    allowed_updates = (
        {"already_battle_shocked"}
        if shocked_at_start
        else {
            "recorded_battle_shocked",
            "recorded_missing_battle_shocked_descendants",
            "already_battle_shocked",
        }
    )
    if state_update not in allowed_updates:
        raise GameLifecycleError("Command Battle-shock failed state update drift.")


def _validate_ordered_result_event_prefix(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    snapshot_index: int,
    ordered_rows: tuple[
        tuple[BattleShockResult, int, dict[str, JsonValue]],
        ...,
    ],
    battle_round: int,
    active_player_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
) -> None:
    previous_result_index = snapshot_index
    for result, resolved_index, resolved_payload in ordered_rows:
        segment = event_records[previous_result_index + 1 : resolved_index]
        expected_request_payload = validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
                "battle_shock_test_request": result.request.to_payload(),
            }
        )
        request_matches = tuple(
            (index, event)
            for index, event in enumerate(
                segment,
                start=previous_result_index + 1,
            )
            if event.event_type == "battle_shock_test_requested"
            and event.payload == expected_request_payload
        )
        if len(request_matches) != 1:
            raise GameLifecycleError("Command Battle-shock result lacks one exact request event.")
        request_index = request_matches[0][0]
        original_roll_payload = result.roll_state.original_result.to_payload()
        original_roll_matches = tuple(
            index
            for index, event in enumerate(segment, start=previous_result_index + 1)
            if event.event_type == "dice_rolled" and event.payload == original_roll_payload
        )
        if len(original_roll_matches) != 1 or original_roll_matches[0] <= request_index:
            raise GameLifecycleError(
                "Command Battle-shock result lacks one exact original dice event."
            )
        rolling_state = _validated_reroll_decision_history(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            segment_start_index=request_index + 1,
            resolved_index=resolved_index,
            original_roll_index=original_roll_matches[0],
            result=result,
            battle_round=battle_round,
            active_player_id=active_player_id,
            phase_start_battle_shocked_unit_ids=(phase_start_battle_shocked_unit_ids),
        )
        if rolling_state != result.roll_state:
            raise GameLifecycleError("Command Battle-shock reroll history drift.")
        validate_command_auto_pass_history(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            segment_start_index=previous_result_index + 1,
            resolved_index=resolved_index,
            result=result,
            auto_passed=cast(bool, resolved_payload["auto_passed"]),
            battle_round=battle_round,
            active_player_id=active_player_id,
        )
        previous_result_index = resolved_index


def _validated_reroll_decision_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    segment_start_index: int,
    resolved_index: int,
    original_roll_index: int,
    result: BattleShockResult,
    battle_round: int,
    active_player_id: str,
    phase_start_battle_shocked_unit_ids: tuple[str, ...],
) -> DiceRollState:
    initial_state = DiceRollState.from_result(result.roll_state.original_result)
    segment = event_records[segment_start_index:resolved_index]
    relevant_records = tuple(
        record
        for record in decision_records
        if _record_targets_battle_shock_request(record=record, result=result)
        or any(
            (
                event.event_type == "decision_requested"
                and event.payload == record.request.to_payload()
            )
            or (event.event_type == "decision_recorded" and event.payload == record.to_payload())
            for event in segment
        )
    )
    if len(result.roll_state.rerolls) > 1 or len(relevant_records) > 1:
        raise GameLifecycleError("Command Battle-shock permits at most one reroll decision.")
    if not relevant_records:
        if result.roll_state.rerolls or any(
            event.event_type in {"decision_requested", "decision_recorded"} for event in segment
        ):
            raise GameLifecycleError("Command Battle-shock reroll decision authority is missing.")
        return initial_state

    record = relevant_records[0]
    expected_context = {
        "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
        "game_id": state.game_id,
        "battle_round": battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": active_player_id,
        "battle_shock_test_request": validate_json_value(result.request.to_payload()),
        "battle_shock_roll_state": validate_json_value(initial_state.to_payload()),
        "phase_start_battle_shocked_unit_ids": list(phase_start_battle_shocked_unit_ids),
        "passed_state_policy": "clear_if_step_start_shocked",
        "base_payload": {
            "game_id": state.game_id,
            "battle_round": battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
        },
        "resolved_event_types": [COMMAND_BATTLE_SHOCK_RESOLVED_EVENT_TYPE],
        "additional_modifier_applications": [],
    }
    request_payload = _payload_object(record.request.payload)
    if (
        record.request.decision_type != DICE_REROLL_DECISION_TYPE
        or record.result.decision_type != DICE_REROLL_DECISION_TYPE
        or record.request.actor_id != result.request.player_id
        or record.result.actor_id != result.request.player_id
        or request_payload.get("battle_shock_context") != expected_context
        or request_payload.get("roll_id") != result.roll_state.original_result.roll_id
        or request_payload.get("roll_type") != result.roll_state.original_result.spec.roll_type
        or request_payload.get("current_values") != list(result.roll_state.original_result.values)
    ):
        raise GameLifecycleError("Command Battle-shock reroll decision context drift.")
    permission_payload = _payload_object(request_payload.get("permission"))
    permission = RerollPermission.from_payload(cast(RerollPermissionPayload, permission_payload))
    expected_reroll_request = DiceRollManager(state.game_id).build_reroll_request(
        initial_state,
        request_id=record.request.request_id,
        actor_id=result.request.player_id,
        permission=permission,
        extra_payload={"battle_shock_context": cast(JsonValue, expected_context)},
    )
    if record.request != expected_reroll_request:
        raise GameLifecycleError("Command Battle-shock reroll request structure drift.")
    requested_indices = tuple(
        index
        for index, event in enumerate(
            event_records[segment_start_index:resolved_index],
            start=segment_start_index,
        )
        if event.event_type == "decision_requested" and event.payload == record.request.to_payload()
    )
    recorded_indices = tuple(
        index
        for index, event in enumerate(
            event_records[segment_start_index:resolved_index],
            start=segment_start_index,
        )
        if event.event_type == "decision_recorded" and event.payload == record.to_payload()
    )
    if (
        len(requested_indices) != 1
        or len(recorded_indices) != 1
        or not original_roll_index < requested_indices[0] < recorded_indices[0] < resolved_index
    ):
        raise GameLifecycleError("Command Battle-shock reroll decision closure drift.")
    if (
        sum(event.event_type in {"decision_requested", "decision_recorded"} for event in segment)
        != 2
    ):
        raise GameLifecycleError("Command Battle-shock reroll decision events are ambiguous.")
    selected_indices = _selected_reroll_indices(record)
    if result.roll_state.rerolls:
        reroll = result.roll_state.rerolls[0]
        if (
            not selected_indices
            or record.request.request_id != reroll.request_id
            or record.result.result_id != reroll.decision_id
            or selected_indices != reroll.selected_indices
        ):
            raise GameLifecycleError("Command Battle-shock accepted reroll authority drift.")
        replacement_indices = tuple(
            index
            for index, event in enumerate(event_records, start=0)
            if segment_start_index <= index < resolved_index
            and event.event_type == "dice_rolled"
            and event.payload == reroll.replacement_result.to_payload()
        )
        updated_state = initial_state.with_reroll(
            decision_id=reroll.decision_id,
            request_id=reroll.request_id,
            selected_indices=reroll.selected_indices,
            replacement_result=reroll.replacement_result,
        )
        reroll_resolved_indices = tuple(
            index
            for index, event in enumerate(event_records, start=0)
            if segment_start_index <= index < resolved_index
            and event.event_type == "dice_reroll_resolved"
            and event.payload == updated_state.to_payload()
        )
        if (
            len(replacement_indices) != 1
            or len(reroll_resolved_indices) != 1
            or not recorded_indices[0]
            < replacement_indices[0]
            < reroll_resolved_indices[0]
            < resolved_index
        ):
            raise GameLifecycleError("Command Battle-shock accepted reroll event order drift.")
        return updated_state

    if selected_indices:
        raise GameLifecycleError("Command Battle-shock declined reroll selected dice.")
    expected_decline = {
        "roll_id": result.roll_state.original_result.roll_id,
        "decision_id": record.result.result_id,
        "request_id": record.request.request_id,
    }
    decline_indices = tuple(
        index
        for index, event in enumerate(event_records, start=0)
        if segment_start_index <= index < resolved_index
        and event.event_type == "dice_reroll_declined"
        and event.payload == expected_decline
    )
    if len(decline_indices) != 1 or not recorded_indices[0] < decline_indices[0] < resolved_index:
        raise GameLifecycleError("Command Battle-shock reroll decline authority drift.")
    return initial_state


def _record_targets_battle_shock_request(
    *,
    record: DecisionRecord,
    result: BattleShockResult,
) -> bool:
    if record.request.decision_type != DICE_REROLL_DECISION_TYPE:
        return False
    payload = record.request.payload
    if not isinstance(payload, dict):
        return False
    context = payload.get("battle_shock_context")
    if not isinstance(context, dict):
        return False
    request_payload = context.get("battle_shock_test_request")
    return isinstance(request_payload, dict) and (
        request_payload.get("request_id") == result.request.request_id
    )


def _selected_reroll_indices(record: DecisionRecord) -> tuple[int, ...]:
    payload = record.result.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Command Battle-shock reroll result payload drift.")
    selected = payload.get("selected_indices")
    if not isinstance(selected, list) or any(type(index) is not int for index in selected):
        raise GameLifecycleError("Command Battle-shock reroll selected indices drift.")
    return tuple(cast(list[int], selected))


def _validate_pending_reroll_restore_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    if type(pending_decision_requests) is not tuple or any(
        type(request) is not DecisionRequest for request in pending_decision_requests
    ):
        raise GameLifecycleError("Command Battle-shock restore requires pending decision requests.")
    pending_rerolls = tuple(
        request
        for request in pending_decision_requests
        if request.decision_type == DICE_REROLL_DECISION_TYPE
        and isinstance(request.payload, dict)
        and "battle_shock_context" in request.payload
    )
    command_state = state.command_step_state
    if command_state is None:
        return
    if command_state.battle_shock_step_resolved:
        if pending_rerolls:
            raise GameLifecycleError("Command Battle-shock resolved state has pending reroll.")
        return
    if len(pending_rerolls) > 1:
        raise GameLifecycleError("Command Battle-shock pending reroll is ambiguous.")
    in_flight_request = command_state.battle_shock_in_flight_test_request
    if in_flight_request is None:
        if pending_rerolls:
            raise GameLifecycleError("Command Battle-shock pending reroll has no in-flight test.")
        return
    expected_test_event = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": command_state.active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
            "battle_shock_test_request": in_flight_request.to_payload(),
        }
    )
    in_progress_test_events = tuple(
        event
        for event in event_records
        if event.event_type == "battle_shock_test_requested"
        and event.payload == expected_test_event
    )
    if not pending_rerolls:
        if in_progress_test_events:
            raise GameLifecycleError(
                "Command Battle-shock in-progress test requires pending reroll authority."
            )
        return
    pending_request = pending_rerolls[0]
    if not in_progress_test_events:
        raise GameLifecycleError("Command Battle-shock pending reroll state drift.")
    request_payload = _payload_object(pending_request.payload)
    context = _payload_object(request_payload.get("battle_shock_context"))
    raw_test_request = _payload_object(context.get("battle_shock_test_request"))
    test_request = BattleShockTestRequest.from_payload(
        cast(BattleShockTestRequestPayload, raw_test_request)
    )
    initial_roll = DiceRollState.from_payload(
        cast(DiceRollStatePayload, _payload_object(context.get("battle_shock_roll_state")))
    )
    if (
        test_request != in_flight_request
        or initial_roll != DiceRollState.from_result(initial_roll.original_result)
        or initial_roll.original_result.spec != test_request.spec
    ):
        raise GameLifecycleError("Command Battle-shock pending reroll snapshot drift.")
    expected_context = {
        "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": BattlePhase.COMMAND.value,
        "active_player_id": command_state.active_player_id,
        "battle_shock_test_request": validate_json_value(test_request.to_payload()),
        "battle_shock_roll_state": validate_json_value(initial_roll.to_payload()),
        "phase_start_battle_shocked_unit_ids": list(
            command_state.battle_shock_phase_start_unit_ids
        ),
        "passed_state_policy": "clear_if_step_start_shocked",
        "base_payload": {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": command_state.active_player_id,
            "phase": BattlePhase.COMMAND.value,
            "source_kind": COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND,
        },
        "resolved_event_types": [COMMAND_BATTLE_SHOCK_RESOLVED_EVENT_TYPE],
        "additional_modifier_applications": [],
    }
    permission = RerollPermission.from_payload(
        cast(RerollPermissionPayload, _payload_object(request_payload.get("permission")))
    )
    expected_request = DiceRollManager(state.game_id).build_reroll_request(
        initial_roll,
        request_id=pending_request.request_id,
        actor_id=test_request.player_id,
        permission=permission,
        extra_payload={"battle_shock_context": cast(JsonValue, expected_context)},
    )
    if pending_request != expected_request:
        raise GameLifecycleError("Command Battle-shock pending reroll request drift.")
    snapshot_index = validate_command_battle_shock_snapshot_authority(
        state=state,
        event_records=event_records,
    )
    test_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_shock_test_requested"
        and event.payload == expected_test_event
    )
    dice_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "dice_rolled"
        and event.payload == initial_roll.original_result.to_payload()
    )
    pending_indices = tuple(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "decision_requested"
        and event.payload == pending_request.to_payload()
    )
    if (
        len(test_indices) != 1
        or len(dice_indices) != 1
        or len(pending_indices) != 1
        or not snapshot_index < test_indices[0] < dice_indices[0] < pending_indices[0]
        or any(record.request == pending_request for record in decision_records)
    ):
        raise GameLifecycleError("Command Battle-shock pending reroll history drift.")


def _validate_historical_snapshot_completion_pairs(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    anchors: dict[tuple[int, str], int] = {}
    snapshots: dict[
        tuple[int, str],
        tuple[
            int,
            dict[str, JsonValue],
            tuple[CommandBattleShockCandidate, ...],
            tuple[str, ...],
        ],
    ] = {}
    completions: dict[tuple[int, str], tuple[int, dict[str, JsonValue]]] = {}
    for event_index, event in enumerate(event_records):
        if event.event_type == "command_step_started":
            payload = _payload_object(event.payload)
            if frozenset(payload) != _COMMAND_STEP_ANCHOR_PAYLOAD_KEYS:
                raise GameLifecycleError("Command step anchor payload shape drift.")
            if _payload_string(payload, "game_id") != state.game_id:
                raise GameLifecycleError("Command step anchor game_id drift.")
            if _payload_string(payload, "phase") != BattlePhase.COMMAND.value:
                raise GameLifecycleError("Command step anchor phase drift.")
            key = (
                _payload_int(payload, "battle_round"),
                _payload_string(payload, "active_player_id"),
            )
            if key in anchors:
                raise GameLifecycleError("Command step anchor is duplicated.")
            validate_core_command_point_anchor(
                state=state,
                event_records=event_records,
                anchor_index=event_index,
                payload=payload,
            )
            anchors[key] = event_index
            continue
        if event.event_type == COMMAND_BATTLE_SHOCK_SNAPSHOT_EVENT_TYPE:
            payload = _payload_object(event.payload)
            if frozenset(payload) != _COMMAND_SNAPSHOT_PAYLOAD_KEYS:
                raise GameLifecycleError("Historical Command Battle-shock snapshot shape drift.")
            if _payload_string(payload, "game_id") != state.game_id:
                raise GameLifecycleError("Historical Command Battle-shock snapshot game drift.")
            if _payload_string(payload, "phase") != BattlePhase.COMMAND.value:
                raise GameLifecycleError("Historical Command Battle-shock snapshot phase drift.")
            key = (
                _payload_int(payload, "battle_round"),
                _payload_string(payload, "active_player_id"),
            )
            if key in snapshots:
                raise GameLifecycleError("Historical Command Battle-shock snapshot is duplicated.")
            raw_phase_start_ids = payload["battle_shock_phase_start_unit_ids"]
            if not isinstance(raw_phase_start_ids, list) or any(
                type(unit_id) is not str for unit_id in raw_phase_start_ids
            ):
                raise GameLifecycleError("Historical phase-start unit IDs drift.")
            phase_start_ids = tuple(cast(list[str], raw_phase_start_ids))
            if phase_start_ids != tuple(sorted(set(phase_start_ids))):
                raise GameLifecycleError("Historical phase-start unit IDs are not deterministic.")
            raw_candidates = payload["battle_shock_candidate_inventory"]
            if not isinstance(raw_candidates, list) or any(
                not isinstance(candidate_payload, dict) for candidate_payload in raw_candidates
            ):
                raise GameLifecycleError("Historical Command candidate inventory drift.")
            candidates = tuple(
                CommandBattleShockCandidate.from_payload(
                    cast(CommandBattleShockCandidatePayload, candidate_payload)
                )
                for candidate_payload in raw_candidates
                if isinstance(candidate_payload, dict)
            )
            if raw_candidates != [candidate.to_payload() for candidate in candidates]:
                raise GameLifecycleError("Historical Command candidate payload drift.")
            if not set(phase_start_ids) <= {
                candidate.unit_instance_id
                for candidate in candidates
                if candidate.test_reason is not None
            }:
                raise GameLifecycleError("Historical phase-start unit lacks required test.")
            validate_command_battle_shock_candidate_inventory(
                candidates,
                active_player_id=key[1],
                phase_start_battle_shocked_unit_ids=phase_start_ids,
            )
            validate_historical_command_candidate_inventory(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                snapshot_index=event_index,
                battle_round=key[0],
                active_player_id=key[1],
                phase_start_battle_shocked_unit_ids=phase_start_ids,
                candidates=candidates,
            )
            snapshots[key] = (event_index, payload, candidates, phase_start_ids)
            continue
        if event.event_type == COMMAND_BATTLE_SHOCK_COMPLETED_EVENT_TYPE:
            payload = _payload_object(event.payload)
            if frozenset(payload) != _COMMAND_COMPLETION_PAYLOAD_KEYS:
                raise GameLifecycleError("Historical Command Battle-shock completion shape drift.")
            if _payload_string(payload, "game_id") != state.game_id:
                raise GameLifecycleError("Historical Command Battle-shock completion game drift.")
            if _payload_string(payload, "phase") != BattlePhase.COMMAND.value:
                raise GameLifecycleError("Historical Command Battle-shock completion phase drift.")
            key = (
                _payload_int(payload, "battle_round"),
                _payload_string(payload, "active_player_id"),
            )
            if key in completions:
                raise GameLifecycleError(
                    "Historical Command Battle-shock completion is duplicated."
                )
            completions[key] = (event_index, payload)

    open_key: tuple[int, str] | None = None
    pre_snapshot_open_key: tuple[int, str] | None = None
    command_state = state.command_step_state
    if command_state is not None:
        current_key = (command_state.battle_round, command_state.active_player_id)
        if command_state.command_points_granted and current_key not in anchors:
            raise GameLifecycleError("Current Command step lacks its start anchor.")
        if not command_state.command_points_granted and current_key in anchors:
            raise GameLifecycleError("Command step start anchor precedes Core CP gain.")
    if tuple(anchors) != expected_restored_core_command_occurrence_keys(
        state,
        event_records=event_records,
    ):
        raise GameLifecycleError("Core CP Command occurrence inventory drifted.")
    if command_state is not None and not command_state.battle_shock_step_resolved:
        open_key = (command_state.battle_round, command_state.active_player_id)
        if command_state.current_step.value != "battle_shock":
            pre_snapshot_open_key = open_key
    expected_snapshot_keys = set(anchors)
    if pre_snapshot_open_key is not None:
        expected_snapshot_keys.discard(pre_snapshot_open_key)
    if set(snapshots) != expected_snapshot_keys:
        raise GameLifecycleError("Command step snapshot authority keys drifted.")
    expected_completion_keys = set(snapshots)
    if open_key is not None:
        expected_completion_keys.discard(open_key)
    if set(completions) != expected_completion_keys:
        raise GameLifecycleError("Command step completion authority keys drifted.")
    ordered_anchor_indices = tuple(sorted(anchors.values()))
    for key, anchor_index in anchors.items():
        snapshot = snapshots.get(key)
        if snapshot is None:
            if pre_snapshot_open_key == key:
                continue
            raise GameLifecycleError("Command step lacks Battle-shock snapshot authority.")
        snapshot_index, _snapshot_payload, candidates, phase_start_ids = snapshot
        if snapshot_index <= anchor_index:
            raise GameLifecycleError("Command Battle-shock snapshot precedes Command step anchor.")
        next_anchor_index = next(
            (index for index in ordered_anchor_indices if index > anchor_index),
            len(event_records),
        )
        if snapshot_index >= next_anchor_index:
            raise GameLifecycleError("Command Battle-shock snapshot escaped its Command step.")
        completion = completions.get(key)
        if open_key == key:
            if completion is not None:
                raise GameLifecycleError("Open Command Battle-shock history has completion event.")
            if command_state is None:
                raise GameLifecycleError("Open Command Battle-shock history lacks command state.")
            required_candidates = tuple(
                candidate for candidate in candidates if candidate.test_reason is not None
            )
            if command_state.battle_shock_candidate_order_unit_ids:
                _validate_historical_candidate_order(
                    state=state,
                    event_records=event_records,
                    decision_records=decision_records,
                    snapshot_index=snapshot_index,
                    completion_index=next_anchor_index,
                    battle_round=key[0],
                    active_player_id=key[1],
                    candidates=required_candidates,
                    ordered_unit_ids=(command_state.battle_shock_candidate_order_unit_ids),
                )
            elif len(required_candidates) == 1:
                raise GameLifecycleError("Open Command Battle-shock trivial order drifted.")
            continue
        if completion is None:
            raise GameLifecycleError("Historical Command Battle-shock completion is missing.")
        completion_index, completion_payload = completion
        if completion_index <= snapshot_index or completion_index >= next_anchor_index:
            raise GameLifecycleError("Historical Command Battle-shock completion order drift.")
        raw_results = completion_payload["battle_shock_results"]
        if not isinstance(raw_results, list) or any(
            not isinstance(result_payload, dict) for result_payload in raw_results
        ):
            raise GameLifecycleError("Historical Battle-shock completion results drift.")
        results = tuple(
            BattleShockResult.from_payload(cast(BattleShockResultPayload, result_payload))
            for result_payload in raw_results
            if isinstance(result_payload, dict)
        )
        if raw_results != [validate_json_value(result.to_payload()) for result in results]:
            raise GameLifecycleError("Historical Battle-shock completion result shape drift.")
        required_candidates = tuple(
            candidate for candidate in candidates if candidate.test_reason is not None
        )
        if len(results) != len(required_candidates):
            raise GameLifecycleError("Historical Battle-shock result inventory drift.")
        _candidate_by_id = {
            candidate.unit_instance_id: candidate for candidate in required_candidates
        }
        if len(_candidate_by_id) != len(required_candidates):
            raise GameLifecycleError("Historical Battle-shock candidates are duplicated.")
        result_unit_ids = tuple(result.request.unit_instance_id for result in results)
        if set(result_unit_ids) != set(_candidate_by_id) or len(set(result_unit_ids)) != len(
            result_unit_ids
        ):
            raise GameLifecycleError("Historical Battle-shock result candidate order drift.")
        for result in results:
            _validate_historical_request_context(
                state=state,
                request=result.request,
                battle_round=key[0],
                active_player_id=key[1],
                candidate=_candidate_by_id[result.request.unit_instance_id],
            )
        _validate_historical_candidate_order(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            snapshot_index=snapshot_index,
            completion_index=completion_index,
            battle_round=key[0],
            active_player_id=key[1],
            candidates=required_candidates,
            ordered_unit_ids=result_unit_ids,
        )
        required_ids = tuple(result.request.request_id for result in results)
        raw_completed_ids = completion_payload["completed_battle_shock_test_request_ids"]
        if raw_completed_ids != list(required_ids):
            raise GameLifecycleError("Historical completed request IDs drift.")
        if completion_payload["battle_shock_test_count"] != len(required_candidates):
            raise GameLifecycleError("Historical Battle-shock test count drift.")
        relevant_resolved = tuple(
            (event_index, _payload_object(event.payload))
            for event_index, event in enumerate(event_records)
            if snapshot_index < event_index < completion_index
            and event.event_type == COMMAND_BATTLE_SHOCK_RESOLVED_EVENT_TYPE
            and _raw_result_request_id(event.payload) in set(required_ids)
        )
        if len(relevant_resolved) != len(results):
            raise GameLifecycleError("Historical Battle-shock resolved event count drift.")
        for result, (_result_index, resolved_payload) in zip(
            results,
            relevant_resolved,
            strict=True,
        ):
            if (
                frozenset(resolved_payload) != _COMMAND_RESULT_PAYLOAD_KEYS
                or resolved_payload.get("game_id") != state.game_id
                or resolved_payload.get("battle_round") != key[0]
                or resolved_payload.get("active_player_id") != key[1]
                or resolved_payload.get("phase") != BattlePhase.COMMAND.value
                or resolved_payload.get("source_kind") != COMMAND_BATTLE_SHOCK_REROLL_SOURCE_KIND
                or type(resolved_payload.get("auto_passed")) is not bool
                or resolved_payload.get("battle_shock_result")
                != validate_json_value(result.to_payload())
            ):
                raise GameLifecycleError("Historical Battle-shock resolved payload drift.")
            cleared_ids = resolved_payload.get("cleared_battle_shocked_unit_ids")
            if (
                not isinstance(cleared_ids, list)
                or any(type(unit_id) is not str for unit_id in cleared_ids)
                or len(cleared_ids) != len(set(cast(list[str], cleared_ids)))
            ):
                raise GameLifecycleError("Historical Battle-shock cleared IDs drift.")
            _validate_result_state_update(
                state=state,
                command_state_phase_start_ids=set(phase_start_ids),
                result=result,
                payload=resolved_payload,
                cleared_ids=tuple(cast(list[str], cleared_ids)),
            )
        _validate_ordered_result_event_prefix(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            snapshot_index=snapshot_index,
            ordered_rows=tuple(
                (result, event_index, payload)
                for result, (event_index, payload) in zip(
                    results,
                    relevant_resolved,
                    strict=True,
                )
            ),
            battle_round=key[0],
            active_player_id=key[1],
            phase_start_battle_shocked_unit_ids=phase_start_ids,
        )


def validate_restore(
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    validate_battle_shock_state_history(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_historical_snapshot_completion_pairs(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    command_state = state.command_step_state
    if command_state is None or command_state.current_step.value != "battle_shock":
        return
    validate_command_battle_shock_completion_authority(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_pending_candidate_order_restore_authority(
        state=state,
        pending_decision_requests=pending_decision_requests,
    )
    try:
        _validate_pending_reroll_restore_authority(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            pending_decision_requests=pending_decision_requests,
        )
    except (DecisionError, DiceError) as exc:
        raise GameLifecycleError(
            "Command Battle-shock pending reroll restore authority drift."
        ) from exc


def validate_command_battle_shock_completion_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    results = ordered_completed_command_battle_shock_results(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    command_state = state.command_step_state
    if command_state is None:
        raise GameLifecycleError("Command Battle-shock completion requires command state.")
    snapshot_index = validate_command_battle_shock_snapshot_authority(
        state=state,
        event_records=event_records,
    )
    matching: list[tuple[int, dict[str, JsonValue]]] = []
    for event_index, event in enumerate(
        event_records[snapshot_index + 1 :],
        start=snapshot_index + 1,
    ):
        if event.event_type != COMMAND_BATTLE_SHOCK_COMPLETED_EVENT_TYPE:
            continue
        payload = _payload_object(event.payload)
        if _payload_string(payload, "game_id") != state.game_id:
            continue
        if _payload_int(payload, "battle_round") != state.battle_round:
            continue
        if _payload_string(payload, "active_player_id") != command_state.active_player_id:
            continue
        matching.append((event_index, payload))
    expected = cast(
        dict[str, JsonValue],
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": command_state.active_player_id,
                "phase": BattlePhase.COMMAND.value,
                "battle_shock_test_count": len(command_state.battle_shock_candidate_order_unit_ids),
                "battle_shock_results": [result.to_payload() for result in results],
                "completed_battle_shock_test_request_ids": list(
                    command_state.completed_battle_shock_test_request_ids
                ),
            }
        ),
    )
    if command_state.battle_shock_step_resolved:
        if len(matching) != 1:
            raise GameLifecycleError(
                "Resolved Command Battle-shock step requires one completion event."
            )
        result_request_ids = {result.request.request_id for result in results}
        result_indices = tuple(
            event_index
            for event_index, event in enumerate(event_records)
            if event.event_type == COMMAND_BATTLE_SHOCK_RESOLVED_EVENT_TYPE
            and _raw_result_request_id(event.payload) in result_request_ids
        )
        if (
            frozenset(matching[0][1]) != _COMMAND_COMPLETION_PAYLOAD_KEYS
            or matching[0][1] != expected
            or matching[0][0] <= max(result_indices, default=snapshot_index)
        ):
            raise GameLifecycleError("Command Battle-shock completion event drift.")
    elif matching:
        raise GameLifecycleError(
            "Unresolved Command Battle-shock step cannot have a completion event."
        )
