"""Random-profile attack occurrences share the owning hit and retargeting history."""

from __future__ import annotations

from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_generated_profile_attack(
    *,
    sequence_id: str,
    pool_index: int,
    attack_index: int,
    generated_hit_number: int | None,
    events: tuple[EventRecord, ...],
) -> None:
    if generated_hit_number is None:
        return
    if generated_hit_number < 2:
        raise GameLifecycleError("Random profile generated hit identity is invalid.")
    hits = [
        event.payload
        for event in events
        if event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "hit"
        and event.payload.get("sequence_id") == sequence_id
        and event.payload.get("pool_index") == pool_index
        and event.payload.get("attack_index") == attack_index
    ]
    if len(hits) != 1:
        raise GameLifecycleError("Random profile generated hit lacks its owning hit.")
    hit = hits[0].get("payload")
    count = hit.get("generated_hits") if isinstance(hit, dict) else None
    if type(count) is not int or count < generated_hit_number:
        raise GameLifecycleError("Random profile generated hit exceeds its owning hit count.")
