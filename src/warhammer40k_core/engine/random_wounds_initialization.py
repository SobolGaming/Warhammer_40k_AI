"""Initialize random Wounds only when the engine materializes a live army."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import (
    RandomProfileValue,
    RandomProfileValuePayload,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_profile_evaluation import evaluate_model_profile_inventory
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance


def initialize_army_random_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    army: ArmyDefinition,
) -> ArmyDefinition:
    return replace(
        army,
        units=tuple(
            replace(
                unit,
                own_models=evaluate_model_profile_inventory(
                    state=state,
                    decisions=decisions,
                    models=unit.own_models,
                    unit_instance_id=unit.unit_instance_id,
                    player_id=army.player_id,
                    scope_id=f"muster-wounds:{army.army_id}",
                    characteristics=(Characteristic.WOUNDS,),
                    initialize_wounds=True,
                ),
            )
            for unit in army.units
        ),
    )


def restore_muster_random_wounds(
    *,
    armies: tuple[ArmyDefinition, ...],
    event_records: tuple[EventRecord, ...],
) -> tuple[ArmyDefinition, ...]:
    """Reconstruct initial health from recorded evaluation, never from current health."""
    restored: list[ArmyDefinition] = []
    for army in armies:
        scope = f"muster-wounds:{army.army_id}"
        values: dict[str, RandomProfileValue] = {}
        for event in event_records:
            payload = event.payload
            if (
                event.event_type != "random_profile_values_evaluated"
                or not isinstance(payload, dict)
                or payload.get("scope_id") != scope
            ):
                continue
            if payload.get("player_id") != army.player_id or payload.get("phase") is not None:
                raise GameLifecycleError("Random Wounds initialization scope drifted.")
            entries = payload.get("entries")
            if not isinstance(entries, list):
                raise GameLifecycleError("Random Wounds initialization inventory is invalid.")
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("profile_value"), dict):
                    raise GameLifecycleError("Random Wounds initialization entry is invalid.")
                model_id = entry.get("model_instance_id")
                if type(model_id) is not str or model_id in values:
                    raise GameLifecycleError(
                        "Random Wounds initialization model is invalid or duplicated."
                    )
                values[model_id] = RandomProfileValue.from_payload(
                    cast(RandomProfileValuePayload, entry["profile_value"])
                )
        units: list[UnitInstance] = []
        for unit in army.units:
            models: list[ModelInstance] = []
            for model in unit.own_models:
                descriptor = model.characteristic(Characteristic.WOUNDS)
                if not isinstance(descriptor, RandomProfileValue):
                    models.append(model)
                    continue
                value = values.pop(model.model_instance_id, None)
                if (
                    value is None
                    or replace(value, evaluation=None, evaluation_id=None) != descriptor
                    or value.evaluation_id
                    != f"{scope}:{unit.unit_instance_id}:{model.model_instance_id}:wounds"
                ):
                    raise GameLifecycleError(
                        "Random Wounds initialization lacks its catalog-linked evaluation."
                    )
                models.append(
                    replace(model, starting_wounds=value.final, wounds_remaining=value.final)
                )
            units.append(replace(unit, own_models=tuple(models)))
        if values:
            raise GameLifecycleError("Random Wounds initialization contains unknown models.")
        restored.append(replace(army, units=tuple(units)))
    return tuple(restored)


def restore_initialized_model_wounds(
    *,
    models: tuple[ModelInstance, ...],
    unit_instance_id: str,
    player_id: str,
    scope_id: str,
    event_records: tuple[EventRecord, ...],
) -> tuple[ModelInstance, ...]:
    """Authenticate creation-time Wounds without rolling during request validation."""
    from warhammer40k_core.core.dice import (
        RandomCharacteristicRoll,
        RandomCharacteristicRollPayload,
        RandomCharacteristicTiming,
    )
    from warhammer40k_core.engine.event_log import JsonValue, canonical_json
    from warhammer40k_core.engine.random_profile_roll_authority import validate_profile_roll
    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        core_random_profiles_2026_09 as random_source,
    )

    values: dict[str, RandomProfileValue] = {}
    physical: dict[str, JsonValue] = {}
    random_rolls: set[str] = set()
    by_id = {model.model_instance_id: model for model in models}
    for event in event_records:
        payload = event.payload
        if not isinstance(payload, dict):
            continue
        if event.event_type == "dice_rolled" and type(payload.get("roll_id")) is str:
            physical[cast(str, payload["roll_id"])] = payload
        elif event.event_type == "random_characteristic_rolled":
            random_rolls.add(canonical_json(payload))
        elif (
            event.event_type == "random_profile_values_evaluated"
            and payload.get("scope_id") == scope_id
        ):
            if (
                payload.get("unit_instance_id") != unit_instance_id
                or payload.get("player_id") != player_id
                or payload.get("source_rule_id") != random_source.RANDOM_PROFILES_SOURCE_ID
            ):
                raise GameLifecycleError("Created model Wounds owner or source drifted.")
            entries = payload.get("entries")
            if not isinstance(entries, list):
                raise GameLifecycleError("Created model Wounds inventory is invalid.")
            for entry in entries:
                if not isinstance(entry, dict) or set(entry) != {
                    "model_instance_id",
                    "profile_value",
                    "roll",
                    "reused",
                }:
                    raise GameLifecycleError("Created model Wounds entry is invalid.")
                model_id = entry["model_instance_id"]
                if (
                    type(model_id) is not str
                    or model_id not in by_id
                    or model_id in values
                    or entry["reused"] is not False
                    or not isinstance(entry["profile_value"], dict)
                    or not isinstance(entry["roll"], dict)
                ):
                    raise GameLifecycleError("Created model Wounds occurrence drifted.")
                value = RandomProfileValue.from_payload(
                    cast(RandomProfileValuePayload, entry["profile_value"])
                )
                source = by_id[model_id].characteristic(Characteristic.WOUNDS)
                identity = f"{scope_id}:{unit_instance_id}:{model_id}:wounds"
                if (
                    replace(value, evaluation=None, evaluation_id=None) != source
                    or value.evaluation_id != identity
                ):
                    raise GameLifecycleError("Created model Wounds descriptor drifted.")
                roll = RandomCharacteristicRoll.from_payload(
                    cast(RandomCharacteristicRollPayload, entry["roll"])
                )
                validate_profile_roll(
                    roll=roll,
                    value=value,
                    scope_id=identity,
                    timing=RandomCharacteristicTiming.PER_MODEL,
                    actor_id=player_id,
                    reason=f"Source profile wounds for {unit_instance_id}",
                    physical_rolls=physical,
                    random_rolls=random_rolls,
                )
                if (
                    value.evaluate(raw=roll.value, evaluation_id=identity, target_id=model_id)
                    != value
                ):
                    raise GameLifecycleError("Created model Wounds result drifted.")
                values[model_id] = value
    result: list[ModelInstance] = []
    for model in models:
        if not isinstance(model.characteristic(Characteristic.WOUNDS), RandomProfileValue):
            result.append(model)
            continue
        initialized = values.get(model.model_instance_id)
        if initialized is None:
            raise GameLifecycleError("Created model Wounds evaluation is missing.")
        result.append(
            replace(
                model,
                characteristics=tuple(
                    initialized if item.characteristic is Characteristic.WOUNDS else item
                    for item in model.characteristics
                ),
                starting_wounds=initialized.final,
                wounds_remaining=initialized.final,
            )
        )
    return tuple(result)
