"""Typed characteristic snapshots can retain an unevaluated source expression."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    ProfileCharacteristicValuePayload,
    RandomProfileValue,
    profile_characteristic_from_payload,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError


def profile_snapshot_from_json(value: str) -> ProfileCharacteristicValue:
    raw: JsonValue = json.loads(value)
    if not isinstance(raw, dict):
        raise GameLifecycleError("Characteristic snapshot requires an object.")
    return profile_characteristic_from_payload(cast(ProfileCharacteristicValuePayload, raw))


def same_profile_source(
    left: ProfileCharacteristicValue, right: ProfileCharacteristicValue
) -> bool:
    if isinstance(left, RandomProfileValue):
        return isinstance(right, RandomProfileValue) and replace(
            left, evaluation=None, evaluation_id=None
        ) == replace(right, evaluation=None, evaluation_id=None)
    return left == right


def snapshot_modifier_ids(value: str) -> tuple[str, ...]:
    return profile_snapshot_from_json(value).applied_modifier_ids


def validate_snapshot_profile_history(
    *,
    values: tuple[tuple[str, str], ...],
    prior_events: tuple[EventRecord, ...],
) -> None:
    """Bind each random snapshot to the last authenticated evaluation before it."""
    needed = {model_id: profile_snapshot_from_json(raw) for model_id, raw in values}
    random_models = {
        model_id: value
        for model_id, value in needed.items()
        if isinstance(value, RandomProfileValue)
    }
    if not random_models:
        return
    latest: dict[str, RandomProfileValue] = {}
    for event in prior_events:
        if event.event_type != "random_profile_values_evaluated" or not isinstance(
            event.payload, dict
        ):
            continue
        entries = event.payload.get("entries")
        if not isinstance(entries, list):
            raise GameLifecycleError("Random profile evaluation inventory is invalid.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise GameLifecycleError("Random profile evaluation entry is invalid.")
            model_id = entry.get("model_instance_id")
            if type(model_id) is not str or model_id not in random_models:
                continue
            raw = entry.get("profile_value")
            if not isinstance(raw, dict):
                raise GameLifecycleError("Random profile evaluation value is invalid.")
            value = profile_characteristic_from_payload(
                cast(ProfileCharacteristicValuePayload, raw)
            )
            if (
                isinstance(value, RandomProfileValue)
                and value.characteristic is random_models[model_id].characteristic
            ):
                latest[model_id] = value
    for model_id, value in random_models.items():
        expected = latest.get(model_id)
        if (expected is None and value.evaluation is not None) or (
            expected is not None and value != expected
        ):
            raise GameLifecycleError(
                "Random characteristic snapshot lacks its historical evaluation."
            )
