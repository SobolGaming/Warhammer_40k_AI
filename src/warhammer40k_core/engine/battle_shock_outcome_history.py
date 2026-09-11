from __future__ import annotations

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_batch_runtime import (
    TIMING_BATCH_EVENT_TYPE,
    timing_batch_from_event,
)


def outcome_activation_index(
    *,
    events: tuple[EventRecord, ...],
    result_id: str,
    source_rule_id: str,
    owner_player_id: str,
    resolved_index: int,
    boundary_index: int,
) -> int:
    """Locate the source rule's own activation after its possibly deferred test outcome."""
    matching: list[int] = []
    for index, event in enumerate(events[:boundary_index]):
        if event.event_type != TIMING_BATCH_EVENT_TYPE:
            continue
        batch = timing_batch_from_event(event)
        if (
            batch.context.conflict_id != f"battle-shock-outcome:{result_id}"
            or not isinstance(event.payload, dict)
            or event.payload["transition"] != "selected"
        ):
            continue
        selected = tuple(
            participant
            for participant in batch.participants
            if participant.participant_id == batch.selected_participant_id
        )
        if len(selected) != 1:
            raise GameLifecycleError("Battle-shock outcome activation lacks its selected rule.")
        participant = selected[0]
        if (
            participant.source_rule_id == source_rule_id
            and participant.player_id == owner_player_id
            and participant.payload == {"battle_shock_result_id": result_id}
        ):
            matching.append(index)
    if len(matching) != 1 or not resolved_index < matching[0] < boundary_index:
        raise GameLifecycleError("Battle-shock outcome lacks its unique source activation.")
    return matching[0]
