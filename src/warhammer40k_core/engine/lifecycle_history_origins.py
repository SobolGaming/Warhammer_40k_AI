"""Lifecycle wiring for independently replayable historical roots."""

# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine import ingress_placement_history as ingress
from warhammer40k_core.engine import psychic_modifier_history_origin as psychic

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload


def capture(
    lifecycle: GameLifecycle, request: DecisionRequest | None
) -> tuple[
    psychic.PsychicModifierHistoryOrigin | None,
    ingress.IngressPlacementHistoryOrigin | None,
]:
    return (
        psychic.capture_psychic_history_origin(
            lifecycle=lifecycle,
            request=request,
            existing=lifecycle._psychic_modifier_history_origin,
        ),
        ingress.capture_ingress_history_origin(
            lifecycle=lifecycle,
            request=request,
            existing=lifecycle._ingress_placement_history_origin,
        ),
    )


def serialize(lifecycle: GameLifecycle, payload: GameLifecyclePayload) -> None:
    if lifecycle._psychic_modifier_history_origin is not None:
        payload["psychic_modifier_history_origin"] = (
            lifecycle._psychic_modifier_history_origin.to_payload()
        )
    if lifecycle._ingress_placement_history_origin is not None:
        payload["ingress_placement_history_origin"] = (
            lifecycle._ingress_placement_history_origin.to_payload()
        )


def restore(lifecycle: GameLifecycle, payload: GameLifecyclePayload) -> None:
    lifecycle._psychic_modifier_history_origin = (
        psychic.PsychicModifierHistoryOrigin.from_payload(
            payload["psychic_modifier_history_origin"]
        )
        if "psychic_modifier_history_origin" in payload
        else None
    )
    lifecycle._ingress_placement_history_origin = (
        ingress.IngressPlacementHistoryOrigin.from_payload(
            payload["ingress_placement_history_origin"]
        )
        if "ingress_placement_history_origin" in payload
        else None
    )


def validate(lifecycle: GameLifecycle) -> None:
    psychic.validate_psychic_history_origin(
        lifecycle=lifecycle, origin=lifecycle._psychic_modifier_history_origin
    )
    ingress.validate_ingress_history_origin(
        lifecycle=lifecycle, origin=lifecycle._ingress_placement_history_origin
    )
