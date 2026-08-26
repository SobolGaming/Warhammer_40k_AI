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


__all__ = (
    "AUTHORITATIVE_BATTLEFIELD_TRANSITION_EVENT_TYPES",
    "authoritative_battlefield_transition_batch_or_none",
)
