from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_RESERVE_ENTRY_MUTATION_EVENT,
    reserve_entry_evidence_payload,
)
from warhammer40k_core.engine.reserve_restriction_integrity import (
    reserve_arrival_restriction_expiry_is_proven,
)
from warhammer40k_core.engine.reserve_state_attached_split import (
    RESERVE_STATE_ATTACHED_SPLIT_EVENT,
    arrived_reserve_state_split_successors,
)
from warhammer40k_core.engine.reserves import (
    ReserveOrigin,
    ReserveState,
    ReserveStatePayload,
    ReserveStatus,
)
from warhammer40k_core.engine.rules_units import (
    reconcile_rules_unit_identity,
    rules_unit_identities_share_lineage,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_SPLIT_EVENT_KEYS: frozenset[str] = frozenset(
    (
        "game_id",
        "battle_round",
        "active_player_id",
        "phase",
        "player_id",
        "historical_unit_instance_id",
        "source_reserve_state",
        "successor_reserve_states",
    )
)


@dataclass(frozen=True, slots=True)
class PrimaryReserveEntryStateOccurrence:
    mutation_order: int
    historical_unit_instance_id: str
    reserve_entry: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class _AttachedSplitTransfer:
    event_order: int
    historical_unit_instance_id: str
    source_state: ReserveState
    successor_states: tuple[ReserveState, ...]


def validate_latest_primary_reserve_entry_states(
    *,
    state: GameState,
    occurrences: tuple[PrimaryReserveEntryStateOccurrence, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    """Bind current ReserveState rows to entry evidence across attached splits."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary reserve state integrity requires GameState.")
    if type(occurrences) is not tuple or any(
        type(occurrence) is not PrimaryReserveEntryStateOccurrence for occurrence in occurrences
    ):
        raise GameLifecycleError("Primary reserve state occurrences are malformed.")
    event_order_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    transfers = _attached_split_transfers(
        state=state,
        event_records=event_records,
        event_order_by_id=event_order_by_id,
    )
    _validate_transfer_source_occurrences(
        occurrences=occurrences,
        transfers=transfers,
    )
    reserve_state_by_unit_id = {value.unit_instance_id: value for value in state.reserve_states}
    if len(reserve_state_by_unit_id) != len(state.reserve_states):
        raise GameLifecycleError("Current ReserveState identity is duplicated.")
    latest_by_current_unit_id: dict[str, tuple[int, dict[str, JsonValue]]] = {}
    for occurrence in occurrences:
        transfer = transfers.get(occurrence.historical_unit_instance_id)
        if transfer is not None:
            if occurrence.mutation_order >= transfer.event_order:
                raise GameLifecycleError(
                    "Reserve entry occurred after its attached split transfer."
                )
            mapped_entries = _split_reserve_entry_payloads(
                reserve_entry=occurrence.reserve_entry,
                successor_unit_instance_ids=tuple(
                    successor.unit_instance_id for successor in transfer.successor_states
                ),
            )
        else:
            mapped_unit_id = _unsplit_current_unit_id(
                historical_unit_instance_id=occurrence.historical_unit_instance_id,
                reserve_state_by_unit_id=reserve_state_by_unit_id,
            )
            mapped_entry = dict(occurrence.reserve_entry)
            mapped_entry["unit_instance_id"] = mapped_unit_id
            mapped_entries = (mapped_entry,)
        for mapped_entry in mapped_entries:
            current_unit_id = _required_string(
                mapped_entry.get("unit_instance_id"),
                field_name="mapped reserve unit_instance_id",
            )
            previous = latest_by_current_unit_id.get(current_unit_id)
            if previous is None or occurrence.mutation_order > previous[0]:
                latest_by_current_unit_id[current_unit_id] = (
                    occurrence.mutation_order,
                    mapped_entry,
                )
    for unit_id, (_order, expected_entry) in latest_by_current_unit_id.items():
        reserve_state = reserve_state_by_unit_id.get(unit_id)
        if reserve_state is None or reserve_entry_evidence_payload(reserve_state) != expected_entry:
            raise GameLifecycleError(
                "Primary reserve-entry mutation lacks its persisted ReserveState."
            )


def validate_reserve_state_attached_split_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    """Close every attached-unit ReserveState transfer against final authoritative state."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Attached split reserve integrity requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Attached split reserve integrity requires typed events.")
    event_order_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_order_by_id) != len(event_records):
        raise GameLifecycleError("Attached split reserve event IDs must be unique.")
    transfers = _attached_split_transfers(
        state=state,
        event_records=event_records,
        event_order_by_id=event_order_by_id,
    )
    _validate_missing_prebattle_transfers(
        state=state,
        transfers=transfers,
        event_records=event_records,
    )


def validated_attached_split_reserve_source_by_successor_id(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> dict[str, ReserveState]:
    """Return each current component ID to its authenticated historical source row."""
    from warhammer40k_core.engine.game_state import GameState

    if (
        type(state) is not GameState
        or type(event_records) is not tuple
        or any(type(record) is not EventRecord for record in event_records)
    ):
        raise GameLifecycleError("Attached split reserve ancestry requires typed lifecycle state.")
    event_order_by_id = {event.event_id: index for index, event in enumerate(event_records)}
    if len(event_order_by_id) != len(event_records):
        raise GameLifecycleError("Attached split reserve event IDs must be unique.")
    transfers = _attached_split_transfers(
        state=state,
        event_records=event_records,
        event_order_by_id=event_order_by_id,
    )
    source_by_successor: dict[str, ReserveState] = {}
    for transfer in transfers.values():
        for successor in transfer.successor_states:
            if successor.unit_instance_id in source_by_successor:
                raise GameLifecycleError(
                    "ReserveState split successor has ambiguous historical ancestry."
                )
            source_by_successor[successor.unit_instance_id] = transfer.source_state
    return source_by_successor


def _attached_split_transfers(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    event_order_by_id: dict[str, int],
) -> dict[str, _AttachedSplitTransfer]:
    transfers: dict[str, _AttachedSplitTransfer] = {}
    for event in event_records:
        if event.event_type != RESERVE_STATE_ATTACHED_SPLIT_EVENT:
            continue
        payload = _closed_object(event.payload, field_name="Attached split reserve event")
        historical_id = _required_string(
            payload.get("historical_unit_instance_id"),
            field_name="historical_unit_instance_id",
        )
        if historical_id in transfers:
            raise GameLifecycleError("Attached split reserve transfer is duplicated.")
        source_state = _reserve_state(
            payload.get("source_reserve_state"),
            field_name="attached split source ReserveState",
        )
        raw_successors = payload.get("successor_reserve_states")
        if not isinstance(raw_successors, list) or not raw_successors:
            raise GameLifecycleError("Attached split reserve successors are malformed.")
        successor_states = tuple(
            _reserve_state(value, field_name="attached split successor ReserveState")
            for value in raw_successors
        )
        successor_ids = tuple(successor.unit_instance_id for successor in successor_states)
        expected_successors = arrived_reserve_state_split_successors(
            source_state=source_state,
            component_unit_instance_ids=successor_ids,
        )
        raw_phase = payload.get("phase")
        if type(raw_phase) is not str:
            raise GameLifecycleError("Attached split reserve transfer identity drift.")
        try:
            split_phase = BattlePhase(raw_phase)
        except (TypeError, ValueError) as exc:
            raise GameLifecycleError("Attached split reserve transfer identity drift.") from exc
        split_round = payload.get("battle_round")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("player_id") != source_state.player_id
            or source_state.unit_instance_id != historical_id
            or source_state.status is not ReserveStatus.ARRIVED
            or [value.to_payload() for value in successor_states]
            != [value.to_payload() for value in expected_successors]
            or type(split_round) is not int
            or split_round <= 0
            or split_round > state.battle_round
            or payload.get("active_player_id") not in state.player_ids
            or split_phase not in state.battle_phase_sequence
        ):
            raise GameLifecycleError("Attached split reserve transfer identity drift.")
        _validate_transfer_causal_timing(
            state=state,
            source_state=source_state,
            split_battle_round=split_round,
            split_phase=split_phase,
        )
        if any(
            not rules_unit_identities_share_lineage(
                state=state,
                first_unit_instance_id=historical_id,
                second_unit_instance_id=successor_id,
            )
            for successor_id in successor_ids
        ):
            raise GameLifecycleError("Attached split reserve successor lineage drift.")
        reconciliation = reconcile_rules_unit_identity(
            state=state,
            unit_instance_id=historical_id,
        )
        if not reconciliation.is_split or successor_ids != reconciliation.current_unit_instance_ids:
            raise GameLifecycleError("Attached split reserve successor set drift.")
        current_reserve_by_id = {value.unit_instance_id: value for value in state.reserve_states}
        current_reserve_ids = set(current_reserve_by_id)
        if historical_id in current_reserve_ids or not set(successor_ids) <= current_reserve_ids:
            raise GameLifecycleError(
                "Attached split reserve transfer is not reflected in current ReserveState rows."
            )
        transfer_order = event_order_by_id[event.event_id]
        later_entry_unit_ids = _later_reserve_entry_unit_ids(
            event_records=event_records,
            event_order_by_id=event_order_by_id,
            transfer_order=transfer_order,
        )
        arrival_active_player_id = _arrival_active_player_id_for_transfer(
            state=state,
            event_records=event_records,
            event_order_by_id=event_order_by_id,
            transfer_order=transfer_order,
            historical_unit_instance_id=historical_id,
            source_state=source_state,
        )
        for successor in successor_states:
            if successor.unit_instance_id in later_entry_unit_ids:
                continue
            _validate_persisted_successor(
                recorded=successor,
                current=current_reserve_by_id[successor.unit_instance_id],
                state=state,
                arrival_active_player_id=arrival_active_player_id,
            )
        transfers[historical_id] = _AttachedSplitTransfer(
            event_order=transfer_order,
            historical_unit_instance_id=historical_id,
            source_state=source_state,
            successor_states=successor_states,
        )
    return transfers


def _validate_missing_prebattle_transfers(
    *,
    state: GameState,
    transfers: dict[str, _AttachedSplitTransfer],
    event_records: tuple[EventRecord, ...],
) -> None:
    reserve_state_by_unit_id = {
        reserve_state.unit_instance_id: reserve_state for reserve_state in state.reserve_states
    }
    declared_unit_ids: set[str] = set()
    for event in event_records:
        if event.event_type != "reserve_unit_declared":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Reserve declaration event payload is malformed.")
        declared_unit_ids.add(
            _required_string(
                event.payload.get("unit_instance_id"),
                field_name="reserve declaration unit_instance_id",
            )
        )
    for starting_record in state.starting_attached_unit_records:
        historical_id = starting_record.attached_unit_instance_id
        reconciliation = reconcile_rules_unit_identity(
            state=state,
            unit_instance_id=historical_id,
        )
        if not reconciliation.is_split or historical_id in transfers:
            continue
        component_states = tuple(
            reserve_state_by_unit_id[component_id]
            for component_id in starting_record.component_unit_instance_ids
            if component_id in reserve_state_by_unit_id
        )
        component_ids = set(starting_record.component_unit_instance_ids)
        has_unattributed_prebattle_successor_set = (
            len(component_states) == len(component_ids)
            and not component_ids.intersection(declared_unit_ids)
            and all(
                reserve_state.reserve_origin is ReserveOrigin.DECLARE_BATTLE_FORMATIONS
                for reserve_state in component_states
            )
        )
        if historical_id in declared_unit_ids or has_unattributed_prebattle_successor_set:
            raise GameLifecycleError(
                "Split prebattle ARRIVED ReserveState requires its transfer event."
            )


def _validate_transfer_causal_timing(
    *,
    state: GameState,
    source_state: ReserveState,
    split_battle_round: int,
    split_phase: BattlePhase,
) -> None:
    if source_state.arrived_battle_round is None or source_state.arrived_phase is None:
        raise GameLifecycleError("Attached split reserve transfer source arrival is missing.")
    try:
        arrival_phase = BattlePhase(source_state.arrived_phase)
    except ValueError as exc:
        raise GameLifecycleError(
            "Attached split reserve transfer source arrival phase is invalid."
        ) from exc
    if arrival_phase not in state.battle_phase_sequence:
        raise GameLifecycleError("Attached split reserve transfer source arrival phase is invalid.")
    if split_battle_round < source_state.arrived_battle_round or (
        split_battle_round == source_state.arrived_battle_round
        and state.battle_phase_sequence.index(split_phase)
        < state.battle_phase_sequence.index(arrival_phase)
    ):
        raise GameLifecycleError("Attached split reserve transfer predates its source arrival.")


def _later_reserve_entry_unit_ids(
    *,
    event_records: tuple[EventRecord, ...],
    event_order_by_id: dict[str, int],
    transfer_order: int,
) -> frozenset[str]:
    unit_ids: set[str] = set()
    for event in event_records:
        if (
            event.event_type != PRIMARY_RESERVE_ENTRY_MUTATION_EVENT
            or event_order_by_id[event.event_id] <= transfer_order
            or not isinstance(event.payload, dict)
        ):
            continue
        reserve_entry = event.payload.get("reserve_entry_state")
        if not isinstance(reserve_entry, dict):
            continue
        unit_id = reserve_entry.get("unit_instance_id")
        if type(unit_id) is str:
            unit_ids.add(unit_id)
    return frozenset(unit_ids)


def _validate_persisted_successor(
    *,
    recorded: ReserveState,
    current: ReserveState,
    state: GameState,
    arrival_active_player_id: str,
) -> None:
    recorded_payload = dict(cast(dict[str, JsonValue], recorded.to_payload()))
    current_payload = dict(cast(dict[str, JsonValue], current.to_payload()))
    recorded_restrictions = recorded_payload.pop("post_arrival_restrictions")
    recorded_restriction_round = recorded_payload.pop("restriction_battle_round")
    current_restrictions = current_payload.pop("post_arrival_restrictions")
    current_restriction_round = current_payload.pop("restriction_battle_round")
    restrictions_match = (
        current_restrictions == recorded_restrictions
        and current_restriction_round == recorded_restriction_round
    ) or (
        bool(recorded_restrictions)
        and recorded.restriction_battle_round is not None
        and current_restrictions == []
        and current_restriction_round is None
        and reserve_arrival_restriction_expiry_is_proven(
            state=state,
            arrival_active_player_id=arrival_active_player_id,
            restriction_battle_round=recorded.restriction_battle_round,
        )
    )
    if current_payload != recorded_payload or not restrictions_match:
        raise GameLifecycleError("Attached split ReserveState successor persistence drift.")


def _arrival_active_player_id_for_transfer(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    event_order_by_id: dict[str, int],
    transfer_order: int,
    historical_unit_instance_id: str,
    source_state: ReserveState,
) -> str:
    if not source_state.post_arrival_restrictions:
        return source_state.player_id
    matching_events = tuple(
        event
        for event in event_records
        if event.event_type == "reinforcement_unit_arrived"
        and event_order_by_id[event.event_id] < transfer_order
        and isinstance(event.payload, dict)
        and event.payload.get("unit_instance_id") == historical_unit_instance_id
        and event.payload.get("battle_round") == source_state.arrived_battle_round
        and event.payload.get("phase") == source_state.arrived_phase
    )
    if matching_events:
        latest = max(matching_events, key=lambda event: event_order_by_id[event.event_id])
        if not isinstance(latest.payload, dict):
            raise GameLifecycleError(
                "Attached split reserve arrival active-player evidence is invalid."
            )
        active_player_id = latest.payload.get("active_player_id")
        if type(active_player_id) is not str or active_player_id not in state.player_ids:
            raise GameLifecycleError(
                "Attached split reserve arrival active-player evidence is invalid."
            )
        return active_player_id
    if source_state.reserve_origin is ReserveOrigin.DECLARE_BATTLE_FORMATIONS:
        return source_state.player_id
    raise GameLifecycleError(
        "Attached split reserve restrictions lack arrival active-player evidence."
    )


def _validate_transfer_source_occurrences(
    *,
    occurrences: tuple[PrimaryReserveEntryStateOccurrence, ...],
    transfers: dict[str, _AttachedSplitTransfer],
) -> None:
    for historical_id, transfer in transfers.items():
        earlier = tuple(
            occurrence
            for occurrence in occurrences
            if occurrence.historical_unit_instance_id == historical_id
            and occurrence.mutation_order < transfer.event_order
        )
        if not earlier:
            if (
                transfer.source_state.entered_reserves_battle_round is not None
                or transfer.source_state.entered_reserves_phase is not None
            ):
                raise GameLifecycleError(
                    "Attached split reserve transfer lacks an authoritative entry occurrence."
                )
            continue
        latest = max(earlier, key=lambda occurrence: occurrence.mutation_order)
        if latest.reserve_entry != reserve_entry_evidence_payload(transfer.source_state):
            raise GameLifecycleError("Attached split reserve transfer source occurrence drift.")


def _unsplit_current_unit_id(
    *,
    historical_unit_instance_id: str,
    reserve_state_by_unit_id: dict[str, ReserveState],
) -> str:
    if historical_unit_instance_id in reserve_state_by_unit_id:
        return historical_unit_instance_id
    raise GameLifecycleError("Historical reserve identity requires an attached split transfer.")


def _split_reserve_entry_payloads(
    *,
    reserve_entry: dict[str, JsonValue],
    successor_unit_instance_ids: tuple[str, ...],
) -> tuple[dict[str, JsonValue], ...]:
    points = reserve_entry.get("points_contribution")
    embarked_ids = reserve_entry.get("embarked_unit_instance_ids")
    if type(points) is not int or not isinstance(embarked_ids, list):
        raise GameLifecycleError("Reserve entry split aggregate fields are malformed.")
    first_successor_id = successor_unit_instance_ids[0]
    mapped: list[dict[str, JsonValue]] = []
    for successor_id in successor_unit_instance_ids:
        payload = dict(reserve_entry)
        payload["unit_instance_id"] = successor_id
        payload["points_contribution"] = points if successor_id == first_successor_id else 0
        payload["embarked_unit_instance_ids"] = (
            list(embarked_ids) if successor_id == first_successor_id else []
        )
        mapped.append(payload)
    return tuple(mapped)


def _closed_object(value: JsonValue, *, field_name: str) -> dict[str, JsonValue]:
    if (
        not isinstance(value, dict)
        or len(value) != len(_SPLIT_EVENT_KEYS)
        or any(key not in value for key in _SPLIT_EVENT_KEYS)
    ):
        raise GameLifecycleError(f"{field_name} fields are malformed.")
    return value


def _reserve_state(value: JsonValue, *, field_name: str) -> ReserveState:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    try:
        return ReserveState.from_payload(cast(ReserveStatePayload, value))
    except (KeyError, TypeError, ValueError, GameLifecycleError) as exc:
        raise GameLifecycleError(f"{field_name} is invalid.") from exc


def _required_string(value: JsonValue, *, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{field_name} must be an identifier.")
    return value


__all__ = (
    "PrimaryReserveEntryStateOccurrence",
    "validate_latest_primary_reserve_entry_states",
    "validate_reserve_state_attached_split_integrity",
    "validated_attached_split_reserve_source_by_successor_id",
)
