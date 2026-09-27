"""Authenticate off-battlefield returns from independent pre-return authority."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload

ORIGIN_KEY = "off_battlefield_revival_history_origin"


def _is_offboard_request(request: DecisionRequest) -> bool:
    return (
        request.decision_type == "select_healing_model"
        and isinstance(request.payload, dict)
        and "revival_location" in request.payload
    )


@dataclass(frozen=True, slots=True)
class OffBattlefieldRevivalHistoryOrigin:
    initial_lifecycle_json: str

    def to_payload(self) -> dict[str, JsonValue]:
        import json

        value = validate_json_value(json.loads(self.initial_lifecycle_json))
        if not isinstance(value, dict):
            raise GameLifecycleError(
                "Off-battlefield revival historical origin requires a lifecycle object."
            )
        return value

    @classmethod
    def from_payload(cls, payload: JsonValue) -> OffBattlefieldRevivalHistoryOrigin:
        from warhammer40k_core.engine.decision_controller import (
            DecisionController,
            DecisionControllerPayload,
        )

        if not isinstance(payload, dict) or ORIGIN_KEY in payload:
            raise GameLifecycleError(
                "Off-battlefield revival historical origin cannot contain another origin."
            )
        raw_decisions = payload.get("decisions")
        if not isinstance(raw_decisions, dict):
            raise GameLifecycleError(
                "Off-battlefield revival historical origin lacks decision authority."
            )
        decisions = DecisionController.from_payload(cast(DecisionControllerPayload, raw_decisions))
        if any(_is_offboard_request(record.request) for record in decisions.records):
            raise GameLifecycleError(
                "Revival historical origin must precede the first off-battlefield return."
            )
        if not decisions.queue.pending_requests or not _is_offboard_request(
            decisions.queue.pending_requests[0]
        ):
            raise GameLifecycleError(
                "Revival historical origin requires a pending off-battlefield return."
            )
        return cls(canonical_json(payload))


def capture_revival_history_origin(
    *,
    lifecycle: GameLifecycle,
    request: DecisionRequest | None,
    existing: OffBattlefieldRevivalHistoryOrigin | None,
) -> OffBattlefieldRevivalHistoryOrigin | None:
    if existing is not None or request is None or not _is_offboard_request(request):
        return existing
    return OffBattlefieldRevivalHistoryOrigin.from_payload(
        validate_json_value(lifecycle.to_payload())
    )


def validate_revival_history_origin(
    *,
    lifecycle: GameLifecycle,
    origin: OffBattlefieldRevivalHistoryOrigin | None,
) -> None:
    from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner

    decisions = lifecycle.decision_controller
    if not any(_is_offboard_request(record.request) for record in decisions.records):
        if origin is not None:
            raise GameLifecycleError("Off-battlefield revival history has an orphan origin.")
        return
    if origin is None:
        raise GameLifecycleError("Off-battlefield revival history lacks its pre-return authority.")
    payload = origin.to_payload()
    current = lifecycle.to_payload()
    if canonical_json(payload.get("config")) != canonical_json(current["config"]):
        raise GameLifecycleError(
            "Off-battlefield revival historical origin config/catalog authority drift."
        )
    original = payload["decisions"]
    present = validate_json_value(current["decisions"])
    if not isinstance(original, dict) or not isinstance(present, dict):
        raise GameLifecycleError(
            "Off-battlefield revival historical origin requires decision ledgers."
        )
    for key in ("records", "event_log"):
        prefix, actual = original[key], present[key]
        if (
            not isinstance(prefix, list)
            or not isinstance(actual, list)
            or canonical_json(prefix) != canonical_json(actual[: len(prefix)])
        ):
            raise GameLifecycleError(
                "Off-battlefield revival historical origin ledger prefix drift."
            )
    artifact = ReplayArtifact.capture(
        artifact_id="off-battlefield-revival-historical-authority",
        initial_lifecycle_payload=cast("GameLifecyclePayload", payload),
        final_lifecycle=lifecycle,
    )
    replay = ReplayRunner(artifact).run()
    if not replay.reproduced_exactly:
        raise GameLifecycleError(
            "Off-battlefield revival placement historical reconstruction drifted: "
            + ", ".join(row.diagnostic_code.value for row in replay.diagnostics)
        )
