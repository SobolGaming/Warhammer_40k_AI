from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    PlacementError,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pose import GeometryError

if TYPE_CHECKING:
    from warhammer40k_core.engine.event_log import EventRecord


AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES = frozenset(
    {
        "battlefield_models_placed",
        "catalog_models_materialized",
        "catalog_setup_reactive_charge_move_completed",
        "charge_move_completed",
        "fight_movement_completed",
        "heroic_intervention_charge_move_completed",
        "movement_activation_completed",
        "reinforcement_unit_arrived",
        "triggered_movement_resolved",
        "unit_disembarked",
    }
)


def authoritative_battlefield_transition_batch_or_none(
    *,
    event: EventRecord,
) -> BattlefieldTransitionBatch | None:
    """Parse only event families that authoritatively mutate battlefield placement."""

    if event.event_type not in AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES:
        return None
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Battlefield transition event payload is invalid.")
    raw_transition = event.payload.get("transition_batch")
    if raw_transition is None:
        return None
    if not isinstance(raw_transition, dict):
        raise GameLifecycleError("Battlefield transition batch is invalid.")
    try:
        return BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, raw_transition)
        )
    except (GeometryError, KeyError, PlacementError, TypeError) as exc:
        raise GameLifecycleError("Battlefield transition batch is invalid.") from exc


def prior_fall_back_applied_transition_or_none(
    *,
    event_records: tuple[EventRecord, ...],
    event_index: int,
    event: EventRecord,
) -> BattlefieldTransitionBatch | None:
    """Authenticate a delayed Fall Back terminal event against its applied move."""

    if event.event_type != "movement_activation_completed":
        return None
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Fall Back terminal event payload is invalid.")
    applied_event_id = event.payload.get("fall_back_applied_event_id")
    if applied_event_id is None:
        return None
    if type(applied_event_id) is not str or not applied_event_id:
        raise GameLifecycleError("Fall Back applied event identity is invalid.")
    if event_index < 0 or event_index >= len(event_records) or event_records[event_index] != event:
        raise GameLifecycleError("Fall Back terminal event index is invalid.")
    matches = tuple(
        candidate
        for candidate in event_records[:event_index]
        if candidate.event_id == applied_event_id
    )
    if len(matches) != 1 or matches[0].event_type != "fall_back_move_applied":
        raise GameLifecycleError("Fall Back applied event authority is missing.")
    applied_payload = matches[0].payload
    if not isinstance(applied_payload, dict):
        raise GameLifecycleError("Fall Back applied event payload is invalid.")
    terminal_transition = authoritative_battlefield_transition_batch_or_none(event=event)
    raw_applied_transition = applied_payload.get("transition_batch")
    if terminal_transition is None or not isinstance(raw_applied_transition, dict):
        raise GameLifecycleError("Fall Back applied transition authority is missing.")
    try:
        applied_transition = BattlefieldTransitionBatch.from_payload(
            cast(BattlefieldTransitionBatchPayload, raw_applied_transition)
        )
    except (GeometryError, KeyError, PlacementError, TypeError) as exc:
        raise GameLifecycleError("Fall Back applied transition authority is invalid.") from exc
    if (
        event.payload.get("movement_phase_action") != "fall_back"
        or applied_payload.get("movement_phase_action") != "fall_back"
        or applied_payload.get("request_id") != event.payload.get("request_id")
        or applied_payload.get("result_id") != event.payload.get("result_id")
        or applied_payload.get("unit_instance_id") != event.payload.get("unit_instance_id")
        or applied_transition != terminal_transition
    ):
        raise GameLifecycleError("Fall Back applied event authority drifted.")
    return applied_transition


__all__ = (
    "AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES",
    "authoritative_battlefield_transition_batch_or_none",
    "prior_fall_back_applied_transition_or_none",
)
