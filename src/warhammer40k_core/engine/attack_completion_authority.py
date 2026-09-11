"""Immutable executor evidence for rules that resolve after all attacks."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.attack_sequence_model import AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError

ATTACK_COMPLETION_STATE_EVENT = "attack_sequence_completion_state_recorded"


def attack_completion_continuation(
    *,
    previous: AttackSequence | None,
    updated: AttackSequence | None,
    pending: AttackSequence | None,
) -> AttackSequence | None:
    """Every terminal executor result preserves the phase owner's completion work."""
    if previous is not None and updated is None:
        if pending is not None:
            raise GameLifecycleError("Attack completion continuation is already occupied.")
        return previous
    return pending


def completed_attack_sequence(
    *, event_records: tuple[EventRecord, ...], sequence_id: str
) -> AttackSequence:
    matches = tuple(
        (index, event)
        for index, event in enumerate(event_records)
        if event.event_type == ATTACK_COMPLETION_STATE_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Attack completion requires unique executor state evidence.")
    index, event = matches[0]
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Attack completion executor state must be an object.")
    sequence = AttackSequence.from_payload(cast(AttackSequencePayload, event.payload))
    if (
        not sequence.is_complete
        or sequence.pending_attack_destructions
        or sequence.pending_destroyed_transport_disembark is not None
        or sequence.deferred_mortal_wounds
        or index == 0
        or event_records[index - 1].event_type != "attack_sequence_completed"
        or event_records[index - 1].payload
        != {
            "sequence_id": sequence.sequence_id,
            "attacker_player_id": sequence.attacker_player_id,
            "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
        }
    ):
        raise GameLifecycleError("Attack completion executor boundary drift.")
    return sequence
