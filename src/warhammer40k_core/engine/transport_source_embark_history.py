"""Bind no-movement embark records without manufacturing movement history."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.transport_embark_context import (
    NoMovementEmbarkContext,
    NoMovementEmbarkContextPayload,
)
from warhammer40k_core.engine.transports import EmbarkSelection, EmbarkSelectionPayload


def validate_source_embark_request(request: DecisionRequest) -> NoMovementEmbarkContext:
    payload = request.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("source_context"), dict):
        raise GameLifecycleError("Source Embark request context is invalid.")
    context = NoMovementEmbarkContext.from_payload(
        cast(NoMovementEmbarkContextPayload, payload["source_context"])
    )
    if (
        "movement_context" in payload
        or context.unit_instance_id != payload.get("unit_instance_id")
        or context.battle_round != payload.get("battle_round")
        or context.turn_player_id != payload.get("active_player_id")
        or context.phase.value != payload.get("phase")
    ):
        raise GameLifecycleError("Source Embark request occurrence drift.")
    for option in request.options:
        if option.option_id == "decline_embark":
            continue
        if not isinstance(option.payload, dict):
            raise GameLifecycleError("Source Embark option must be an object.")
        selection = EmbarkSelection.from_payload(cast(EmbarkSelectionPayload, option.payload))
        if (
            selection.source_context != context
            or selection.player_id != request.actor_id
            or selection.transport_unit_instance_id != option.option_id
        ):
            raise GameLifecycleError("Source Embark option authority drift.")
    return context


def validate_source_embark_event(record: DecisionRecord, payload: dict[str, JsonValue]) -> None:
    context = validate_source_embark_request(record.request)
    selection_payload = payload.get("embark_selection")
    if not isinstance(selection_payload, dict) or not isinstance(record.result.payload, dict):
        raise GameLifecycleError("Source Embark event selection is invalid.")
    selection = EmbarkSelection.from_payload(cast(EmbarkSelectionPayload, selection_payload))
    submitted = EmbarkSelection.from_payload(cast(EmbarkSelectionPayload, record.result.payload))
    if (
        selection != submitted
        or selection.source_context != context
        or selection.player_id != record.request.actor_id
        or selection.transport_unit_instance_id != payload.get("transport_unit_instance_id")
        or selection.unit_instance_id != payload.get("unit_instance_id")
    ):
        raise GameLifecycleError("Source Embark mutation selection drift.")
