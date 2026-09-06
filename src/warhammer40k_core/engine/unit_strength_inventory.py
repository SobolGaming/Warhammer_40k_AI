"""Canonical original and successor Starting Strength inventory."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


def validate_starting_strength_records(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    player_ids: tuple[str, ...],
) -> list[StartingStrengthRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState starting_strength_records must be a list.")
    if not values and army_definitions:
        derived: list[StartingStrengthRecord] = []
        for army_definition in army_definitions:
            derived.extend(starting_strength_records_for_army(army_definition))
        return sorted(derived, key=lambda record: record.unit_instance_id)

    expected_record_owner_by_id = _starting_strength_record_owner_by_id(army_definitions)
    validated: list[StartingStrengthRecord] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StartingStrengthRecord:
            raise GameLifecycleError(
                "GameState starting_strength_records must contain StartingStrengthRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StartingStrengthRecord player_id is not in this game.")
        owner = expected_record_owner_by_id.get(value.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("StartingStrengthRecord unit is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("StartingStrengthRecord player_id drift.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState starting_strength_records must be unique.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    if set(expected_record_owner_by_id) != seen:
        raise GameLifecycleError("GameState starting_strength_records must include every unit.")
    return sorted(validated, key=lambda record: record.unit_instance_id)


def starting_strength_records_for_army(
    army_definition: ArmyDefinition,
) -> tuple[StartingStrengthRecord, ...]:
    if type(army_definition) is not ArmyDefinition:
        raise GameLifecycleError("StartingStrengthRecord derivation requires an ArmyDefinition.")
    attached_component_ids = {
        component_id
        for attached_unit in army_definition.attached_units
        for component_id in attached_unit.component_unit_instance_ids
    }
    records = [
        StartingStrengthRecord.from_unit(player_id=army_definition.player_id, unit=unit)
        for unit in army_definition.source_units()
        if unit.unit_instance_id not in attached_component_ids
    ]
    unit_by_id = {unit.unit_instance_id: unit for unit in army_definition.source_units()}
    for attached_unit in army_definition.attached_units:
        records.append(
            _starting_strength_record_for_attached_unit(
                player_id=army_definition.player_id,
                attached_unit=attached_unit,
                unit_by_id=unit_by_id,
            )
        )
    for split in army_definition.unit_splits:
        for index in (0, 1):
            model_ids = split.model_ids(index)
            models = tuple(
                model
                for unit in split.source_units
                for model in unit.own_models
                if model.model_instance_id in model_ids
            )
            records.append(
                StartingStrengthRecord(
                    player_id=army_definition.player_id,
                    unit_instance_id=split.successor_id(index),
                    starting_model_count=len(models),
                    single_model_starting_wounds=models[0].starting_wounds
                    if len(models) == 1
                    else None,
                    source_id=split.source_id,
                )
            )
    return tuple(sorted(records, key=lambda record: record.unit_instance_id))


def _starting_strength_record_for_attached_unit(
    *,
    player_id: str,
    attached_unit: AttachedUnitFormation,
    unit_by_id: dict[str, UnitInstance],
) -> StartingStrengthRecord:
    if type(attached_unit) is not AttachedUnitFormation:
        raise GameLifecycleError("Attached starting strength requires an AttachedUnitFormation.")
    starting_model_count = 0
    for unit_id in attached_unit.component_unit_instance_ids:
        unit = unit_by_id.get(unit_id)
        if unit is None:
            raise GameLifecycleError("Attached starting strength component unit is unknown.")
        starting_model_count += len(unit.own_models)
    return StartingStrengthRecord(
        player_id=player_id,
        unit_instance_id=attached_unit.attached_unit_instance_id,
        starting_model_count=starting_model_count,
        single_model_starting_wounds=None,
        source_id=attached_unit.source_id,
    )


def _starting_strength_record_owner_by_id(
    army_definitions: list[ArmyDefinition],
) -> dict[str, str]:
    return {
        record.unit_instance_id: record.player_id
        for army in army_definitions
        for record in starting_strength_records_for_army(army)
    }
