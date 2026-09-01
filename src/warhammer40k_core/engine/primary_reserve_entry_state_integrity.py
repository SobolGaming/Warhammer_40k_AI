from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import reserve_entry_evidence_payload

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


@dataclass(frozen=True, slots=True)
class PrimaryReserveEntryStateOccurrence:
    mutation_order: int
    historical_unit_instance_id: str
    reserve_entry: dict[str, JsonValue]


def validate_latest_primary_reserve_entry_states(
    *,
    state: GameState,
    occurrences: tuple[PrimaryReserveEntryStateOccurrence, ...],
    event_records: tuple[EventRecord, ...],
) -> None:
    """Bind current ReserveState rows directly to canonical entry evidence."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary reserve state integrity requires GameState.")
    if type(occurrences) is not tuple or any(
        type(occurrence) is not PrimaryReserveEntryStateOccurrence for occurrence in occurrences
    ):
        raise GameLifecycleError("Primary reserve state occurrences are malformed.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Primary reserve state integrity requires typed events.")
    if any(
        event.event_type == "reserve_state_transferred_after_attached_unit_split"
        for event in event_records
    ):
        raise GameLifecycleError(
            "Attached rules-unit reserve split events are invalid under retained identity."
        )

    reserve_state_by_unit_id = {value.unit_instance_id: value for value in state.reserve_states}
    if len(reserve_state_by_unit_id) != len(state.reserve_states):
        raise GameLifecycleError("Current ReserveState identity is duplicated.")
    latest_by_unit_id: dict[str, tuple[int, dict[str, JsonValue]]] = {}
    for occurrence in occurrences:
        unit_id = occurrence.historical_unit_instance_id
        if unit_id not in reserve_state_by_unit_id:
            raise GameLifecycleError(
                "Authoritative reserve-entry identity lacks its canonical ReserveState."
            )
        previous = latest_by_unit_id.get(unit_id)
        if previous is None or occurrence.mutation_order > previous[0]:
            expected_entry = dict(occurrence.reserve_entry)
            expected_entry["unit_instance_id"] = unit_id
            latest_by_unit_id[unit_id] = (occurrence.mutation_order, expected_entry)
    for unit_id, (_order, expected_entry) in latest_by_unit_id.items():
        reserve_state = reserve_state_by_unit_id[unit_id]
        if reserve_entry_evidence_payload(reserve_state) != expected_entry:
            raise GameLifecycleError(
                "Primary reserve-entry mutation lacks its persisted ReserveState."
            )


__all__ = (
    "PrimaryReserveEntryStateOccurrence",
    "validate_latest_primary_reserve_entry_states",
)
