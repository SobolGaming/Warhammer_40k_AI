"""Read evaluated model profiles at an authenticated historical event boundary."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    RandomProfileValuePayload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError


def armies_with_historical_random_profiles(
    *,
    armies: tuple[ArmyDefinition, ...],
    prior_events: tuple[EventRecord, ...],
    characteristics: tuple[Characteristic, ...],
) -> tuple[ArmyDefinition, ...]:
    needed = {
        (model.model_instance_id, value.characteristic)
        for army in armies
        for unit in army.units
        for model in unit.own_models
        for value in model.characteristics
        if isinstance(value, RandomProfileValue) and value.characteristic in characteristics
    }
    if not needed:
        return armies
    latest: dict[tuple[str, Characteristic], RandomProfileValue] = {}
    for event in prior_events:
        if event.event_type != "random_profile_values_evaluated":
            continue
        if not isinstance(event.payload, dict) or not isinstance(
            event.payload.get("entries"), list
        ):
            raise GameLifecycleError("Random profile history inventory is invalid.")
        entries = event.payload["entries"]
        if not isinstance(entries, list):
            raise GameLifecycleError("Random profile history entries are invalid.")
        for entry in entries:
            if not isinstance(entry, dict):
                raise GameLifecycleError("Random profile history entry is invalid.")
            model_id, raw = entry.get("model_instance_id"), entry.get("profile_value")
            if type(model_id) is not str or not isinstance(raw, dict):
                raise GameLifecycleError("Random profile history model or value is invalid.")
            value = RandomProfileValue.from_payload(cast(RandomProfileValuePayload, raw))
            key = model_id, value.characteristic
            if key in needed:
                latest[key] = value
    return tuple(
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(
                            model,
                            characteristics=tuple(
                                latest.get(
                                    (model.model_instance_id, value.characteristic),
                                    replace(value, evaluation=None, evaluation_id=None),
                                )
                                if isinstance(value, RandomProfileValue)
                                and value.characteristic in characteristics
                                else value
                                for value in model.characteristics
                            ),
                        )
                        if any((model.model_instance_id, c) in needed for c in characteristics)
                        else model
                        for model in unit.own_models
                    ),
                )
                for unit in army.units
            ),
        )
        for army in armies
    )
