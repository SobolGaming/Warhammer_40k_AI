from __future__ import annotations

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.mission_action_policies import primary_mission_state_rule_for_id
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionMarkerState


def primary_marker_removal_event_index(
    *, marker: PrimaryMissionMarkerState, event_records: tuple[EventRecord, ...]
) -> int | None:
    """Resolve a marker's mutation boundary, which can follow its deferred trigger."""
    if marker.removal_event_id is None:
        return None
    source_id = primary_mission_state_rule_for_id(
        "surveil-remove-operation-markers-after-move"
    ).source_id
    if marker.removal_source_id == source_id:
        indices = tuple(
            index
            for index, event in enumerate(event_records)
            if event.event_type == "primary_surveil_move_marker_removal_resolved"
            and isinstance(event.payload, dict)
            and event.payload.get("trigger_event_id") == marker.removal_event_id
            and isinstance(rows := event.payload.get("removed_primary_mission_markers"), list)
            and any(
                isinstance(row, dict) and row.get("marker_id") == marker.marker_id for row in rows
            )
        )
    else:
        indices = tuple(
            index
            for index, event in enumerate(event_records)
            if event.event_id == marker.removal_event_id
        )
    if len(indices) != 1:
        raise GameLifecycleError("Primary marker requires its unique removal mutation event.")
    return indices[0]


def primary_marker_was_active_at_event(
    *,
    marker: PrimaryMissionMarkerState,
    event_id: str,
    event_records: tuple[EventRecord, ...],
) -> bool:
    indices = {event.event_id: index for index, event in enumerate(event_records)}
    if marker.source_event_id not in indices or event_id not in indices:
        raise GameLifecycleError("Primary marker history requires its creation and observation.")
    removal_index = primary_marker_removal_event_index(marker=marker, event_records=event_records)
    return indices[marker.source_event_id] < indices[event_id] and (
        removal_index is None or removal_index >= indices[event_id]
    )
