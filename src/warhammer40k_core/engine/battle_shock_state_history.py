from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attached_unit_split_history import (
    ATTACHED_RULES_UNIT_SPLIT_EVENT,
)
from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockedUnitStatePayload,
    BattleShockResult,
    BattleShockResultPayload,
)
from warhammer40k_core.engine.battle_shock_state import (
    BATTLE_SHOCK_ATTACHED_SPLIT_TRANSFER_EVENT,
    BATTLE_SHOCK_STATE_ALREADY,
    BATTLE_SHOCK_STATE_RECORDED,
    BATTLE_SHOCK_STATE_RECORDED_MISSING_DESCENDANTS,
)
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    physical_model_authority_before_event,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord


_BATTLE_SHOCK_RESOLVED_EVENT = "battle_shock_test_resolved"
_RULES_UNIT_SPLIT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "player_id",
        "attached_unit_instance_id",
        "component_unit_instance_ids",
        "surviving_unit_instance_ids",
        "starting_attached_unit_record",
    }
)
_SPLIT_PAYLOAD_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "player_id",
        "attached_unit_instance_id",
        "surviving_unit_instance_ids",
        "source_battle_shocked_unit_state",
        "successor_battle_shocked_unit_states",
    }
)
type _PendingShockedSplit = tuple[str, tuple[str, ...], dict[str, JsonValue]]


@dataclass(frozen=True, slots=True)
class BattleShockStateAuthorityBeforeEvent:
    active_attached_unit_ids: tuple[str, ...]
    battle_shocked_unit_ids: tuple[str, ...]


def validate_battle_shock_state_history(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Replay every authoritative Battle-shock mutation and bind current state to it."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Battle-shock state history requires GameState.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Battle-shock state history requires event records.")
    if type(decision_records) is not tuple or any(
        type(record) is not DecisionRecord for record in decision_records
    ):
        raise GameLifecycleError("Battle-shock state history requires decision records.")
    if (
        not state.battle_shocked_unit_ids
        and not state.battle_shocked_unit_states
        and not any(event.event_type == _BATTLE_SHOCK_RESOLVED_EVENT for event in event_records)
    ):
        return

    replayed_states, active_attached_ids = _replay_battle_shock_state_until(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        stop_index=len(event_records),
    )
    final_active_attached_ids = {
        attached.attached_unit_instance_id
        for army in state.army_definitions
        for attached in army.attached_units
    }
    if active_attached_ids != final_active_attached_ids:
        raise GameLifecycleError("Attached rules-unit split history drifted.")

    expected_states = tuple(
        sorted(replayed_states.values(), key=lambda value: value.unit_instance_id)
    )
    expected_ids = tuple(value.unit_instance_id for value in expected_states)
    if tuple(state.battle_shocked_unit_ids) != expected_ids:
        raise GameLifecycleError("Battle-shock unit inventory lacks exact event authority.")
    if tuple(state.battle_shocked_unit_states) != expected_states:
        raise GameLifecycleError("Battle-shock state rows lack exact event authority.")


def battle_shock_state_authority_before_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
) -> BattleShockStateAuthorityBeforeEvent:
    """Return exact attached and Battle-shocked identities before one event."""
    if type(event_index) is not int or not 0 <= event_index <= len(event_records):
        raise GameLifecycleError("Battle-shock history boundary index is invalid.")
    replayed_states, active_attached_ids = _replay_battle_shock_state_until(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        stop_index=event_index,
    )
    return BattleShockStateAuthorityBeforeEvent(
        active_attached_unit_ids=tuple(sorted(active_attached_ids)),
        battle_shocked_unit_ids=tuple(sorted(replayed_states)),
    )


def _replay_battle_shock_state_until(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    stop_index: int,
) -> tuple[dict[str, BattleShockedUnitState], set[str]]:
    owner_by_unit_id, model_ids_by_unit_id = _historical_unit_inventory(state=state)
    attached_by_identity = _starting_attached_records_by_identity(state=state)
    active_attached_ids = {
        record.attached_unit_instance_id for record in state.starting_attached_unit_records
    }
    final_active_attached_ids = {
        attached.attached_unit_instance_id
        for army in state.army_definitions
        for attached in army.attached_units
    }
    replayed_states: dict[str, BattleShockedUnitState] = {}
    seen_result_ids: set[str] = set()
    seen_request_ids: set[str] = set()
    pending_shocked_split: _PendingShockedSplit | None = None
    for event_index, event in enumerate(event_records[:stop_index]):
        if (
            pending_shocked_split is not None
            and event.event_type != BATTLE_SHOCK_ATTACHED_SPLIT_TRANSFER_EVENT
        ):
            raise GameLifecycleError(
                "Battle-shocked attached split lacks its immediate state transfer."
            )
        if event.event_type == _BATTLE_SHOCK_RESOLVED_EVENT:
            _apply_resolved_event(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                event_index=event_index,
                payload=_event_payload(event),
                replayed_states=replayed_states,
                seen_result_ids=seen_result_ids,
                seen_request_ids=seen_request_ids,
                owner_by_unit_id=owner_by_unit_id,
                model_ids_by_unit_id=model_ids_by_unit_id,
                attached_by_identity=attached_by_identity,
                active_attached_ids=active_attached_ids,
            )
            continue
        if event.event_type == ATTACHED_RULES_UNIT_SPLIT_EVENT:
            physical_rows = physical_model_authority_before_event(
                state=state,
                event_records=event_records,
                decision_records=decision_records,
                event_index=event_index,
            )
            attached_id, survivor_ids = _apply_rules_unit_split_event(
                state=state,
                payload=_event_payload(event),
                active_attached_ids=active_attached_ids,
                final_active_attached_ids=final_active_attached_ids,
                alive_model_ids={
                    row.model_instance_id for row in physical_rows if row.wounds_remaining > 0
                },
            )
            if attached_id in replayed_states:
                pending_shocked_split = (attached_id, survivor_ids, _event_payload(event))
            continue
        if event.event_type == BATTLE_SHOCK_ATTACHED_SPLIT_TRANSFER_EVENT:
            if pending_shocked_split is None:
                raise GameLifecycleError(
                    "Battle-shock attached split lacks rules-unit split authority."
                )
            _apply_split_transfer_event(
                state=state,
                payload=_event_payload(event),
                replayed_states=replayed_states,
                owner_by_unit_id=owner_by_unit_id,
                model_ids_by_unit_id=model_ids_by_unit_id,
                expected_split=pending_shocked_split,
            )
            pending_shocked_split = None
    if pending_shocked_split is not None:
        raise GameLifecycleError("Battle-shocked attached split transfer is missing.")
    return replayed_states, active_attached_ids


def _apply_resolved_event(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index: int,
    payload: dict[str, JsonValue],
    replayed_states: dict[str, BattleShockedUnitState],
    seen_result_ids: set[str],
    seen_request_ids: set[str],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    attached_by_identity: dict[str, StartingAttachedUnitRecord],
    active_attached_ids: set[str],
) -> None:
    from warhammer40k_core.engine.battle_shock_event_authority import (
        validate_battle_shock_resolution_event_authority,
    )

    raw_result = payload.get("battle_shock_result")
    if not isinstance(raw_result, dict):
        raise GameLifecycleError("Battle-shock resolved event result is invalid.")
    result = BattleShockResult.from_payload(cast(BattleShockResultPayload, raw_result))
    validate_battle_shock_resolution_event_authority(
        event_records=event_records,
        decision_records=decision_records,
        resolved_index=event_index,
        resolved_payload=payload,
        result=result,
    )
    request = result.request
    if (
        result.result_id != f"{request.request_id}:result"
        or result.result_id in seen_result_ids
        or request.request_id in seen_request_ids
    ):
        raise GameLifecycleError("Battle-shock result event identity is duplicated.")
    seen_result_ids.add(result.result_id)
    seen_request_ids.add(request.request_id)
    if (
        request.game_id != state.game_id
        or payload.get("game_id") != state.game_id
        or payload.get("battle_round") != request.battle_round
        or request.battle_round > state.battle_round
    ):
        raise GameLifecycleError("Battle-shock resolved event occurrence drifted.")
    phase = payload.get("phase")
    if type(phase) is not str or phase not in {value.value for value in BattlePhase}:
        raise GameLifecycleError("Battle-shock resolved event phase is invalid.")
    active_player_id = payload.get("active_player_id")
    if type(active_player_id) is not str or active_player_id not in state.player_ids:
        raise GameLifecycleError("Battle-shock resolved event active player is invalid.")
    if owner_by_unit_id.get(request.unit_instance_id) != request.player_id:
        raise GameLifecycleError("Battle-shock resolved event unit owner drifted.")
    attached_record = attached_by_identity.get(request.unit_instance_id)
    if (
        attached_record is not None
        and attached_record.attached_unit_instance_id in active_attached_ids
        and request.unit_instance_id != attached_record.attached_unit_instance_id
    ):
        raise GameLifecycleError("Battle-shock event must target the canonical attached-unit ID.")
    auto_passed = payload.get("auto_passed")
    if type(auto_passed) is not bool or (auto_passed and not result.passed):
        raise GameLifecycleError("Battle-shock resolved event auto-pass state drifted.")
    state_update = payload.get("state_update")
    if type(state_update) is not str:
        raise GameLifecycleError("Battle-shock resolved event state update is invalid.")
    cleared_ids = _cleared_unit_ids(payload)
    active_ids = _active_state_ids_for_request(
        unit_instance_id=request.unit_instance_id,
        replayed_states=replayed_states,
        attached_by_identity=attached_by_identity,
        active_attached_ids=active_attached_ids,
    )

    if result.passed:
        if state_update == "not_required":
            if cleared_ids:
                raise GameLifecycleError("Battle-shock no-op result cannot clear state.")
            return
        if (
            state_update != "cleared_battle_shocked"
            or phase != BattlePhase.COMMAND.value
            or not _has_command_required_clear_authority(
                event_records=event_records,
                resolved_index=event_index,
                result=result,
            )
            or not active_ids
            or set(cleared_ids) != active_ids
        ):
            raise GameLifecycleError("Battle-shock clear identity drifted.")
        for unit_id in cleared_ids:
            del replayed_states[unit_id]
        return

    if cleared_ids:
        raise GameLifecycleError("Failed Battle-shock result cannot clear state.")
    physical_rows = physical_model_authority_before_event(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
        event_index=event_index,
    )
    target_unit_ids = _current_state_target_ids_for_request(
        unit_instance_id=request.unit_instance_id,
        attached_by_identity=attached_by_identity,
        active_attached_ids=active_attached_ids,
        model_ids_by_unit_id=model_ids_by_unit_id,
        alive_model_ids={
            row.model_instance_id for row in physical_rows if row.wounds_remaining > 0
        },
    )
    if not target_unit_ids:
        raise GameLifecycleError("Battle-shock result unit model inventory is unknown.")
    already_target_ids = set(target_unit_ids).intersection(active_ids)
    missing_target_ids = tuple(
        unit_id for unit_id in target_unit_ids if unit_id not in already_target_ids
    )
    expected_state_update = (
        BATTLE_SHOCK_STATE_ALREADY
        if not missing_target_ids
        else (
            BATTLE_SHOCK_STATE_RECORDED_MISSING_DESCENDANTS
            if already_target_ids
            else BATTLE_SHOCK_STATE_RECORDED
        )
    )
    if state_update != expected_state_update:
        raise GameLifecycleError("Battle-shock failure mutation token drifted.")
    for target_unit_id in missing_target_ids:
        replayed_states[target_unit_id] = BattleShockedUnitState(
            player_id=request.player_id,
            unit_instance_id=target_unit_id,
            model_instance_ids=model_ids_by_unit_id[target_unit_id],
            source_result_id=result.result_id,
            battle_round_started=request.battle_round,
        )


def _apply_rules_unit_split_event(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    active_attached_ids: set[str],
    final_active_attached_ids: set[str],
    alive_model_ids: set[str],
) -> tuple[str, tuple[str, ...]]:
    if (
        frozenset(payload) != _RULES_UNIT_SPLIT_PAYLOAD_KEYS
        or payload.get("game_id") != state.game_id
    ):
        raise GameLifecycleError("Attached rules-unit split payload drifted.")
    attached_id = _payload_string(payload, "attached_unit_instance_id")
    player_id = _payload_string(payload, "player_id")
    matching = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == attached_id
    )
    raw_components = payload.get("component_unit_instance_ids")
    raw_survivors = payload.get("surviving_unit_instance_ids")
    if (
        len(matching) != 1
        or attached_id not in active_attached_ids
        or attached_id in final_active_attached_ids
        or player_id != matching[0].player_id
        or payload.get("starting_attached_unit_record") != matching[0].to_payload()
        or not isinstance(raw_components, list)
        or any(type(value) is not str for value in raw_components)
        or tuple(raw_components) != matching[0].component_unit_instance_ids
        or not isinstance(raw_survivors, list)
        or any(type(value) is not str for value in raw_survivors)
    ):
        raise GameLifecycleError("Attached rules-unit split identity drifted.")
    survivors = tuple(cast(list[str], raw_survivors))
    expected_survivors = tuple(
        component_id
        for component_id, model_ids in matching[0].starting_model_instance_ids_by_component
        if set(model_ids).intersection(alive_model_ids)
    )
    if (
        survivors != tuple(sorted(set(survivors)))
        or not survivors
        or survivors != expected_survivors
    ):
        raise GameLifecycleError("Attached rules-unit split survivors drifted.")
    _validate_split_occurrence(state=state, payload=payload)
    active_attached_ids.remove(attached_id)
    return attached_id, survivors


def _apply_split_transfer_event(
    *,
    state: GameState,
    payload: dict[str, JsonValue],
    replayed_states: dict[str, BattleShockedUnitState],
    owner_by_unit_id: dict[str, str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    expected_split: _PendingShockedSplit,
) -> None:
    if frozenset(payload) != _SPLIT_PAYLOAD_KEYS or payload.get("game_id") != state.game_id:
        raise GameLifecycleError("Battle-shock attached split payload drifted.")
    _validate_split_occurrence(state=state, payload=payload)
    battle_round = cast(int, payload["battle_round"])
    player_id = _payload_string(payload, "player_id")
    attached_id = _payload_string(payload, "attached_unit_instance_id")
    split_payload = expected_split[2]
    if (
        expected_split[0] != attached_id
        or owner_by_unit_id.get(attached_id) != player_id
        or any(
            payload.get(key) != split_payload.get(key)
            for key in (
                "game_id",
                "battle_round",
                "active_player_id",
                "phase",
                "player_id",
                "attached_unit_instance_id",
                "surviving_unit_instance_ids",
            )
        )
    ):
        raise GameLifecycleError("Battle-shock attached split identity drifted.")
    source_payload = payload.get("source_battle_shocked_unit_state")
    raw_successors = payload.get("successor_battle_shocked_unit_states")
    raw_survivor_ids = payload.get("surviving_unit_instance_ids")
    if (
        not isinstance(source_payload, dict)
        or not isinstance(raw_successors, list)
        or any(not isinstance(value, dict) for value in raw_successors)
        or not isinstance(raw_survivor_ids, list)
        or any(type(value) is not str for value in raw_survivor_ids)
    ):
        raise GameLifecycleError("Battle-shock attached split state is invalid.")
    source_state = BattleShockedUnitState.from_payload(
        cast(BattleShockedUnitStatePayload, source_payload)
    )
    survivor_ids = tuple(cast(list[str], raw_survivor_ids))
    starting_record = next(
        (
            record
            for record in state.starting_attached_unit_records
            if record.attached_unit_instance_id == attached_id
        ),
        None,
    )
    if (
        starting_record is None
        or survivor_ids != expected_split[1]
        or survivor_ids != tuple(sorted(set(survivor_ids)))
        or not survivor_ids
        or not set(survivor_ids).issubset(starting_record.component_unit_instance_ids)
        or replayed_states.get(attached_id) != source_state
        or source_state.player_id != player_id
        or source_state.battle_round_started > battle_round
    ):
        raise GameLifecycleError("Battle-shock attached split source authority drifted.")
    expected_successors = tuple(
        replace(
            source_state,
            unit_instance_id=unit_id,
            model_instance_ids=model_ids_by_unit_id[unit_id],
        )
        for unit_id in survivor_ids
    )
    successors = tuple(
        BattleShockedUnitState.from_payload(cast(BattleShockedUnitStatePayload, raw))
        for raw in raw_successors
        if isinstance(raw, dict)
    )
    if (
        successors != expected_successors
        or raw_successors != [value.to_payload() for value in expected_successors]
        or any(unit_id in replayed_states for unit_id in survivor_ids)
    ):
        raise GameLifecycleError("Battle-shock attached split successor authority drifted.")
    del replayed_states[attached_id]
    replayed_states.update({value.unit_instance_id: value for value in expected_successors})


def _historical_unit_inventory(
    *,
    state: GameState,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    owner_by_unit_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(model.model_instance_id for model in unit.own_models)
        for army in state.army_definitions
        for unit in army.units
    }
    for record in state.starting_attached_unit_records:
        if record.attached_unit_instance_id in owner_by_unit_id:
            raise GameLifecycleError("Battle-shock attached identity collides with a unit.")
        owner_by_unit_id[record.attached_unit_instance_id] = record.player_id
        model_ids_by_unit_id[record.attached_unit_instance_id] = tuple(
            model_id
            for component_id in record.component_unit_instance_ids
            for model_id in model_ids_by_unit_id[component_id]
        )
    return owner_by_unit_id, model_ids_by_unit_id


def _starting_attached_records_by_identity(
    *,
    state: GameState,
) -> dict[str, StartingAttachedUnitRecord]:
    records: dict[str, StartingAttachedUnitRecord] = {}
    for record in state.starting_attached_unit_records:
        for unit_id in (record.attached_unit_instance_id, *record.component_unit_instance_ids):
            if unit_id in records:
                raise GameLifecycleError("Battle-shock attached lineage is ambiguous.")
            records[unit_id] = record
    return records


def _active_state_ids_for_request(
    *,
    unit_instance_id: str,
    replayed_states: dict[str, BattleShockedUnitState],
    attached_by_identity: dict[str, StartingAttachedUnitRecord],
    active_attached_ids: set[str],
) -> set[str]:
    record = attached_by_identity.get(unit_instance_id)
    if record is None:
        return {unit_instance_id}.intersection(replayed_states)
    if record.attached_unit_instance_id not in active_attached_ids:
        if unit_instance_id == record.attached_unit_instance_id:
            return set(record.component_unit_instance_ids).intersection(replayed_states)
        return {unit_instance_id}.intersection(replayed_states)
    identity_ids = {record.attached_unit_instance_id, *record.component_unit_instance_ids}
    return identity_ids.intersection(replayed_states)


def _current_state_target_ids_for_request(
    *,
    unit_instance_id: str,
    attached_by_identity: dict[str, StartingAttachedUnitRecord],
    active_attached_ids: set[str],
    model_ids_by_unit_id: dict[str, tuple[str, ...]],
    alive_model_ids: set[str],
) -> tuple[str, ...]:
    record = attached_by_identity.get(unit_instance_id)
    if record is None or unit_instance_id != record.attached_unit_instance_id:
        model_ids = model_ids_by_unit_id.get(unit_instance_id)
        if model_ids is None or not set(model_ids).intersection(alive_model_ids):
            return ()
        return (unit_instance_id,)
    if record.attached_unit_instance_id in active_attached_ids:
        return (record.attached_unit_instance_id,)
    return tuple(
        component_id
        for component_id in record.component_unit_instance_ids
        if set(model_ids_by_unit_id[component_id]).intersection(alive_model_ids)
    )


def _validate_split_occurrence(*, state: GameState, payload: dict[str, JsonValue]) -> None:
    battle_round = payload.get("battle_round")
    if type(battle_round) is not int or battle_round < 0 or battle_round > state.battle_round:
        raise GameLifecycleError("Attached rules-unit split round drifted.")
    phase = payload.get("phase")
    if phase is not None and (
        type(phase) is not str or phase not in {value.value for value in BattlePhase}
    ):
        raise GameLifecycleError("Attached rules-unit split phase drifted.")
    active_player_id = payload.get("active_player_id")
    if active_player_id is not None and (
        type(active_player_id) is not str or active_player_id not in state.player_ids
    ):
        raise GameLifecycleError("Attached rules-unit split active player drifted.")


def _has_command_required_clear_authority(
    *,
    event_records: tuple[EventRecord, ...],
    resolved_index: int,
    result: BattleShockResult,
) -> bool:
    request_payload = result.request.to_payload()
    matching = 0
    for event in event_records[:resolved_index]:
        if event.event_type != "battle_shock_step_snapshot_created":
            continue
        payload = event.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Battle-shock Command snapshot payload is invalid.")
        if (
            payload.get("game_id") != result.request.game_id
            or payload.get("battle_round") != result.request.battle_round
            or payload.get("active_player_id") != result.request.player_id
            or payload.get("phase") != BattlePhase.COMMAND.value
        ):
            continue
        required = payload.get("battle_shock_required_test_requests")
        phase_start_ids = payload.get("battle_shock_phase_start_unit_ids")
        if not isinstance(required, list) or not isinstance(phase_start_ids, list):
            raise GameLifecycleError("Battle-shock Command snapshot clear authority is invalid.")
        if request_payload in required and result.request.unit_instance_id in phase_start_ids:
            matching += 1
    return matching == 1


def _cleared_unit_ids(payload: dict[str, JsonValue]) -> tuple[str, ...]:
    value = payload.get("cleared_battle_shocked_unit_ids")
    if not isinstance(value, list) or any(type(unit_id) is not str for unit_id in value):
        raise GameLifecycleError("Battle-shock resolved event cleared IDs are invalid.")
    cleared = tuple(cast(list[str], value))
    if cleared != tuple(sorted(set(cleared))):
        raise GameLifecycleError("Battle-shock resolved event cleared IDs drifted.")
    return cleared


def _event_payload(event: EventRecord) -> dict[str, JsonValue]:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Battle-shock mutation event payload is invalid.")
    return event.payload


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Battle-shock mutation event {key} is invalid.")
    return value


__all__ = (
    "BattleShockStateAuthorityBeforeEvent",
    "battle_shock_state_authority_before_event",
    "validate_battle_shock_state_history",
)
