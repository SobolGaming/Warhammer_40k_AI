"""Reconstruct modifier choices from independent inputs, including expired sources."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.modifier_evaluation import SELECT_MODIFIER_IGNORES_DECISION_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload

ORIGIN_KEY = "modifier_evaluation_history_origin"
_RECONSTRUCTING: ContextVar[bool] = ContextVar("modifier_evaluation_reconstructing", default=False)


@dataclass(frozen=True, slots=True)
class ModifierEvaluationHistoryOrigin:
    initial_lifecycle_json: str

    def to_payload(self) -> dict[str, JsonValue]:
        import json

        value = validate_json_value(json.loads(self.initial_lifecycle_json))
        if not isinstance(value, dict):
            raise GameLifecycleError("Modifier evaluation origin requires a lifecycle object.")
        return value

    @classmethod
    def from_payload(cls, payload: JsonValue) -> ModifierEvaluationHistoryOrigin:
        from warhammer40k_core.engine.decision_controller import (
            DecisionController,
            DecisionControllerPayload,
        )

        if not isinstance(payload, dict) or ORIGIN_KEY in payload:
            raise GameLifecycleError("Modifier evaluation origin must not contain itself.")
        raw = payload.get("decisions")
        if not isinstance(raw, dict):
            raise GameLifecycleError("Modifier evaluation origin lacks decision authority.")
        decisions = DecisionController.from_payload(cast(DecisionControllerPayload, raw))
        if any(
            record.request.decision_type == SELECT_MODIFIER_IGNORES_DECISION_TYPE
            for record in decisions.records
        ) or any(
            request.decision_type == SELECT_MODIFIER_IGNORES_DECISION_TYPE
            for request in decisions.queue.pending_requests
        ):
            raise GameLifecycleError("Modifier origin must precede source evaluation choices.")
        return cls(canonical_json(payload))


def capture_modifier_origin(
    lifecycle: GameLifecycle,
    existing: ModifierEvaluationHistoryOrigin | None,
) -> ModifierEvaluationHistoryOrigin | None:
    if existing is not None:
        return existing
    return ModifierEvaluationHistoryOrigin.from_payload(validate_json_value(lifecycle.to_payload()))


def validate_modifier_origin(
    lifecycle: GameLifecycle,
    origin: ModifierEvaluationHistoryOrigin | None,
) -> None:
    if _RECONSTRUCTING.get():
        return
    decisions = lifecycle.decision_controller
    has_evaluation_events = any(
        event.event_type
        in {
            "attack_save_modifiers_prepared",
            "failed_save_damage_replacement_ignored",
            "modifier_ignores_selected",
        }
        for event in decisions.event_log.records
    )
    if (
        not has_evaluation_events
        and not any(
            record.request.decision_type == SELECT_MODIFIER_IGNORES_DECISION_TYPE
            for record in decisions.records
        )
        and not any(
            request.decision_type == SELECT_MODIFIER_IGNORES_DECISION_TYPE
            for request in decisions.queue.pending_requests
        )
    ):
        return
    if origin is None:
        raise GameLifecycleError(
            "Modifier evaluation lacks independent historical source authority."
        )
    token = _RECONSTRUCTING.set(True)
    try:
        _reconstruct(lifecycle, origin)
    finally:
        _RECONSTRUCTING.reset(token)


def _reconstruct(lifecycle: GameLifecycle, origin: ModifierEvaluationHistoryOrigin) -> None:
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.replay_continuation import advance_recorded_automatic_progress

    initial = origin.to_payload()
    if canonical_json(initial.get("config")) != canonical_json(lifecycle.to_payload()["config"]):
        raise GameLifecycleError("Modifier origin catalog/config authority drift.")
    reproduced = GameLifecycle.from_payload(cast("GameLifecyclePayload", initial))
    expected = lifecycle.decision_controller
    actual = reproduced.decision_controller
    prefix_records = len(actual.records)
    prefix_events = len(actual.event_log.records)
    if (
        actual.records != expected.records[:prefix_records]
        or actual.event_log.records != expected.event_log.records[:prefix_events]
    ):
        raise GameLifecycleError("Modifier origin historical prefix drift.")
    events = expected.event_log.records[prefix_events:]
    for index in range(prefix_records, len(expected.records)):
        if len(actual.records) <= index:
            advance_recorded_automatic_progress(
                lifecycle=reproduced,
                expected_events=events,
                initial_event_count=prefix_events,
                stop_at_record_count=index + 1,
            )
        if len(actual.records) <= index:
            record = expected.records[index]
            pending = actual.queue.pending_requests
            if not pending or pending[0] != record.request:
                raise GameLifecycleError("Modifier historical source request reconstruction drift.")
            status = reproduced.submit_decision(record.result)
            if status.status_kind in {LifecycleStatusKind.INVALID, LifecycleStatusKind.UNSUPPORTED}:
                raise GameLifecycleError("Modifier historical source choice reconstruction failed.")
        if actual.records[index] != expected.records[index]:
            raise GameLifecycleError("Modifier historical decision reconstruction drift.")
    advance_recorded_automatic_progress(
        lifecycle=reproduced,
        expected_events=events,
        initial_event_count=prefix_events,
    )
    if actual.to_payload() != expected.to_payload():
        raise GameLifecycleError("Modifier source events or pending request reconstruction drift.")
    if (
        reproduced.state is None
        or lifecycle.state is None
        or reproduced.state.to_payload() != lifecycle.state.to_payload()
    ):
        raise GameLifecycleError("Modifier historical state reconstruction drift.")
