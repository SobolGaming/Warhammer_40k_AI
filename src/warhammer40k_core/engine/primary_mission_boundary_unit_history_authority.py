from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollState
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockResultPayload,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_event_decision_authority import (
    validate_primary_mission_movement_event_decision_authority,
    validate_primary_mission_mutation_decision_closure,
    validate_primary_mission_shooting_event_decision_authority,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_primary_mission_boundary_unit_history_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint_index: int,
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    prior_events = event_records[:checkpoint_index]
    advanced_ids, fell_back_ids = _movement_history_ids(
        event_records=prior_events,
        decision_records=decision_records,
        checkpoint=checkpoint,
    )
    checkpoint_advanced_ids = _unit_ids_from_state_jsons(checkpoint.advanced_unit_state_jsons)
    checkpoint_fell_back_ids = _unit_ids_from_state_jsons(checkpoint.fell_back_unit_state_jsons)
    if advanced_ids != checkpoint_advanced_ids:
        raise GameLifecycleError("Primary mission boundary Advance state lacks exact authority.")
    if fell_back_ids != checkpoint_fell_back_ids:
        raise GameLifecycleError("Primary mission boundary Fall Back state lacks exact authority.")
    _validate_battle_shock_authority(
        state=state,
        event_records=prior_events,
        decision_records=decision_records,
        checkpoint=checkpoint,
    )
    declared_shot_ids = _shooting_declaration_ids(
        event_records=prior_events,
        decision_records=decision_records,
        checkpoint=checkpoint,
    )
    if declared_shot_ids != set(checkpoint.shot_unit_instance_ids):
        raise GameLifecycleError("Primary mission boundary shooting state lacks exact authority.")


def _movement_history_ids(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> tuple[set[str], set[str]]:
    advanced: set[str] = set()
    fell_back: set[str] = set()
    for event_index, event in enumerate(event_records):
        if event.event_type != "movement_activation_completed":
            continue
        payload = _event_payload(event, context="movement activation")
        validate_primary_mission_movement_event_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            payload=payload,
        )
        if not _same_game(payload=payload, checkpoint=checkpoint):
            continue
        if payload.get("battle_round") != checkpoint.battle_round:
            continue
        if payload.get("active_player_id") != checkpoint.player_id:
            continue
        if payload.get("phase") != BattlePhase.MOVEMENT.value:
            raise GameLifecycleError("Primary mission movement history phase drifted.")
        unit_id = _payload_string(payload, key="unit_instance_id", context="movement activation")
        action = _payload_string(
            payload, key="movement_phase_action", context="movement activation"
        )
        if action == "advance":
            advanced.add(unit_id)
        elif action == "fall_back":
            fell_back.add(unit_id)
    return advanced, fell_back


def _validate_battle_shock_authority(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> None:
    active_results: dict[str, BattleShockResult] = {}
    for event_index, event in enumerate(event_records):
        if event.event_type == "command_step_started":
            payload = _event_payload(event, context="Command-step start")
            if not _same_game(payload=payload, checkpoint=checkpoint):
                continue
            battle_round = payload.get("battle_round")
            if type(battle_round) is not int or battle_round > checkpoint.battle_round:
                raise GameLifecycleError("Primary mission Command-step round drifted.")
            if payload.get("phase") != BattlePhase.COMMAND.value:
                raise GameLifecycleError("Primary mission Command-step phase drifted.")
            active_player_id = _payload_string(
                payload,
                key="active_player_id",
                context="Command-step start",
            )
            cleared = payload.get("cleared_battle_shocked_unit_ids")
            if not isinstance(cleared, list) or any(type(value) is not str for value in cleared):
                raise GameLifecycleError("Primary mission Battle-shock clear history is invalid.")
            active_results = {
                result_id: result
                for result_id, result in active_results.items()
                if result.request.player_id != active_player_id
            }
            continue
        if event.event_type != "battle_shock_test_resolved":
            continue
        payload = _event_payload(event, context="Battle-shock result")
        raw_result = payload.get("battle_shock_result")
        if not isinstance(raw_result, dict):
            raise GameLifecycleError("Primary mission Battle-shock result payload is invalid.")
        result = BattleShockResult.from_payload(cast(BattleShockResultPayload, raw_result))
        _validate_battle_shock_resolution_closure(
            event_records=event_records,
            decision_records=decision_records,
            resolved_index=event_index,
            resolved_payload=payload,
            result=result,
        )
        if result.request.game_id != checkpoint.game_id:
            raise GameLifecycleError("Primary mission Battle-shock history game drifted.")
        if result.request.battle_round > checkpoint.battle_round:
            raise GameLifecycleError("Primary mission Battle-shock history round drifted.")
        state_update = payload.get("state_update")
        if result.passed:
            if state_update not in (None, "not_required"):
                raise GameLifecycleError("Primary mission Battle-shock result state drifted.")
            continue
        if state_update == "already_battle_shocked":
            continue
        if state_update not in (None, "recorded_battle_shocked"):
            raise GameLifecycleError("Primary mission Battle-shock result state drifted.")
        if result.result_id in active_results:
            raise GameLifecycleError("Primary mission Battle-shock result identity is duplicated.")
        active_results[result.result_id] = result

    checkpoint_ids = set(checkpoint.battle_shocked_unit_instance_ids)
    authenticated_ids: set[str] = set()
    for result in active_results.values():
        matching_ids = checkpoint_ids.intersection(
            _battle_shock_result_unit_ids(state=state, result=result)
        )
        if not matching_ids:
            raise GameLifecycleError("Primary mission Battle-shock causal state was erased.")
        if authenticated_ids.intersection(matching_ids):
            raise GameLifecycleError("Primary mission Battle-shock authority is ambiguous.")
        authenticated_ids.update(matching_ids)
    if authenticated_ids != checkpoint_ids:
        raise GameLifecycleError("Primary mission Battle-shock state lacks result authority.")


def _validate_battle_shock_resolution_closure(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    resolved_index: int,
    resolved_payload: dict[str, JsonValue],
    result: BattleShockResult,
) -> None:
    prior_events = event_records[:resolved_index]
    request_payload = result.request.to_payload()
    requested = tuple(
        (index, event)
        for index, event in enumerate(prior_events)
        if event.event_type == "battle_shock_test_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_test_request") == request_payload
    )
    if len(requested) != 1:
        raise GameLifecycleError(
            "Primary mission Battle-shock result lacks exact request authority."
        )
    request_index, request_event = requested[0]
    request_context = cast(dict[str, JsonValue], request_event.payload)
    if (
        request_context.get("game_id") != result.request.game_id
        or request_context.get("battle_round") != result.request.battle_round
        or resolved_payload.get("game_id") != result.request.game_id
        or resolved_payload.get("battle_round") != result.request.battle_round
    ):
        raise GameLifecycleError("Primary mission Battle-shock request context drifted.")
    original_roll = result.roll_state.original_result
    original_rolls = tuple(
        (index, event)
        for index, event in enumerate(prior_events)
        if event.event_type == "dice_rolled" and event.payload == original_roll.to_payload()
    )
    if len(original_rolls) != 1 or original_rolls[0][0] <= request_index:
        raise GameLifecycleError("Primary mission Battle-shock result lacks exact dice authority.")
    reroll_decisions = tuple(
        record
        for record in decision_records
        if record.request.decision_type == DICE_REROLL_DECISION_TYPE
        and _battle_shock_reroll_request_payload(record) == request_payload
    )
    reroll_by_result_id = {record.result.result_id: record for record in reroll_decisions}
    if len(reroll_by_result_id) != len(reroll_decisions):
        raise GameLifecycleError("Primary mission Battle-shock reroll authority is duplicated.")
    accepted_ids = {row.decision_id for row in result.roll_state.rerolls}
    if not accepted_ids <= set(reroll_by_result_id):
        raise GameLifecycleError("Primary mission Battle-shock reroll state lacks authority.")
    rolling_state = DiceRollState.from_result(original_roll)
    for reroll in result.roll_state.rerolls:
        record = reroll_by_result_id[reroll.decision_id]
        validate_primary_mission_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=resolved_index,
            request_id=reroll.request_id,
            result_id=reroll.decision_id,
        )
        if (
            record.result.decision_type != DICE_REROLL_DECISION_TYPE
            or record.request.request_id != reroll.request_id
        ):
            raise GameLifecycleError("Primary mission Battle-shock reroll decision drifted.")
        replacement_rolls = tuple(
            event
            for event in prior_events
            if event.event_type == "dice_rolled"
            and event.payload == reroll.replacement_result.to_payload()
        )
        if len(replacement_rolls) != 1:
            raise GameLifecycleError(
                "Primary mission Battle-shock reroll lacks exact dice authority."
            )
        rolling_state = rolling_state.with_reroll(
            decision_id=reroll.decision_id,
            request_id=reroll.request_id,
            selected_indices=reroll.selected_indices,
            replacement_result=reroll.replacement_result,
        )
        resolved_rerolls = tuple(
            event
            for event in prior_events
            if event.event_type == "dice_reroll_resolved"
            and event.payload == rolling_state.to_payload()
        )
        if len(resolved_rerolls) != 1:
            raise GameLifecycleError(
                "Primary mission Battle-shock reroll lacks exact resolution authority."
            )
    for record in reroll_decisions:
        if record.result.result_id in accepted_ids:
            continue
        validate_primary_mission_mutation_decision_closure(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=resolved_index,
            request_id=record.request.request_id,
            result_id=record.result.result_id,
        )
        declined = tuple(
            event
            for event in prior_events
            if event.event_type == "dice_reroll_declined"
            and event.payload
            == {
                "roll_id": original_roll.roll_id,
                "decision_id": record.result.result_id,
                "request_id": record.request.request_id,
            }
        )
        if len(declined) != 1:
            raise GameLifecycleError(
                "Primary mission Battle-shock reroll decline lacks exact authority."
            )
    if rolling_state != result.roll_state:
        raise GameLifecycleError("Primary mission Battle-shock roll history drifted.")


def _battle_shock_reroll_request_payload(
    record: DecisionRecord,
) -> JsonValue:
    payload = record.request.payload
    if not isinstance(payload, dict):
        return None
    context = payload.get("battle_shock_context")
    if not isinstance(context, dict):
        return None
    return context.get("battle_shock_test_request")


def _battle_shock_result_unit_ids(*, state: GameState, result: BattleShockResult) -> set[str]:
    request = result.request
    allowed_unit_ids = {request.unit_instance_id}
    for attached in state.starting_attached_unit_records:
        if attached.attached_unit_instance_id == request.unit_instance_id:
            allowed_unit_ids.update(attached.component_unit_instance_ids)
    return allowed_unit_ids


def _shooting_declaration_ids(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> set[str]:
    if checkpoint.phase != BattlePhase.SHOOTING.value:
        return set()
    declared: set[str] = set()
    for event_index, event in enumerate(event_records):
        if event.event_type != "shooting_declaration_accepted":
            continue
        payload = _event_payload(event, context="shooting declaration")
        validate_primary_mission_shooting_event_decision_authority(
            event_records=event_records,
            decision_records=decision_records,
            mutation_index=event_index,
            payload=payload,
        )
        if not _same_game(payload=payload, checkpoint=checkpoint):
            continue
        if payload.get("battle_round") != checkpoint.battle_round:
            continue
        if payload.get("active_player_id") != checkpoint.player_id:
            continue
        if payload.get("phase") != BattlePhase.SHOOTING.value:
            raise GameLifecycleError("Primary mission shooting history phase drifted.")
        declared.add(
            _payload_string(payload, key="unit_instance_id", context="shooting declaration")
        )
        ineligible = payload.get("ineligible_unit_instance_ids")
        if not isinstance(ineligible, list) or any(type(value) is not str for value in ineligible):
            raise GameLifecycleError("Primary mission shooting causal inventory is invalid.")
        declared.update(cast(list[str], ineligible))
    return declared


def _same_game(
    *,
    payload: dict[str, JsonValue],
    checkpoint: PrimaryMissionBoundaryCheckpoint,
) -> bool:
    game_id = payload.get("game_id")
    if type(game_id) is not str:
        raise GameLifecycleError("Primary mission causal-history game identity is invalid.")
    if game_id != checkpoint.game_id:
        raise GameLifecycleError("Primary mission causal-history game identity drifted.")
    return True


def _event_payload(event: EventRecord, *, context: str) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError(f"Primary mission {context} event payload is invalid.")
    return event.payload


def _payload_string(
    payload: dict[str, JsonValue],
    *,
    key: str,
    context: str,
) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Primary mission {context} {key} is invalid.")
    return value


def _unit_ids_from_state_jsons(values: tuple[str, ...]) -> set[str]:
    unit_ids: set[str] = set()
    for value in values:
        try:
            decoded: object = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GameLifecycleError("Primary mission movement-state JSON is invalid.") from exc
        if not isinstance(decoded, dict):
            raise GameLifecycleError("Primary mission movement-state payload is invalid.")
        raw = cast(dict[object, object], decoded)
        unit_id = raw.get("unit_instance_id")
        if type(unit_id) is not str:
            raise GameLifecycleError("Primary mission movement-state unit identity is invalid.")
        unit_ids.add(unit_id)
    return unit_ids


__all__ = ("validate_primary_mission_boundary_unit_history_authority",)
