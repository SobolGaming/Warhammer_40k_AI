"""Canonical model-preserving partition; lifecycle decisions own its application."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_split_records import UnitSplitRecord
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_unit_splitting_2026_09,
)

UNIT_SPLITTING_SOURCE_ID = core_unit_splitting_2026_09.UNIT_SPLITTING_SOURCE_ID
BALANCED_UNIT_SPLITTING_SOURCE_ID = core_unit_splitting_2026_09.BALANCED_UNIT_SPLITTING_SOURCE_ID


def build_split_army(
    *,
    army: ArmyDefinition,
    unit_instance_id: str,
    first_model_ids: tuple[str, ...],
    request_id: str,
    source_id: str,
    specified_strengths: tuple[int, int] | None,
) -> ArmyDefinition:
    """Validate and build a complete replacement before the engine mutates state.

    The caller must authenticate the authorizing rule and its timing. This pure
    transformation grants no split opportunity and never mutates a game.
    """
    if type(army) is not ArmyDefinition:
        raise GameLifecycleError("Unit splitting requires an ArmyDefinition.")
    for previous in army.unit_splits:
        if unit_instance_id in {
            previous.source_unit_instance_id,
            previous.successor_id(0),
            previous.successor_id(1),
            *(
                origin.unit_instance_id
                for index in (0, 1)
                for origin in previous.component_origins(index)
            ),
        }:
            raise GameLifecycleError("These models have already been split.")
    formation = next(
        (row for row in army.attached_units if row.attached_unit_instance_id == unit_instance_id),
        None,
    )
    source_units: tuple[UnitInstance, ...]
    if formation is None:
        if any(unit_instance_id in row.component_unit_instance_ids for row in army.attached_units):
            raise GameLifecycleError("Unit splitting requires canonical rules-unit identity.")
        source_units = (army.unit_by_id(unit_instance_id),)
    else:
        source_units = tuple(
            army.unit_by_id(value) for value in formation.component_unit_instance_ids
        )
    record = UnitSplitRecord(
        request_id=request_id,
        source_id=source_id,
        source_unit_instance_id=unit_instance_id,
        source_units=source_units,
        source_formation=formation,
        first_model_ids=first_model_ids,
        specified_strengths=specified_strengths,
    )
    retired = {unit.unit_instance_id for unit in source_units}
    units = [unit for unit in army.units if unit.unit_instance_id not in retired]
    for index in (0, 1):
        chosen = set(record.model_ids(index))
        for origin in record.component_origins(index):
            source = next(
                unit
                for unit in source_units
                if unit.unit_instance_id == origin.source_unit_instance_id
            )
            units.append(
                replace(
                    source,
                    unit_instance_id=origin.unit_instance_id,
                    split_origin=origin,
                    own_models=tuple(
                        model for model in source.own_models if model.model_instance_id in chosen
                    ),
                )
            )
    return replace(
        army,
        units=tuple(sorted(units, key=lambda u: u.unit_instance_id)),
        unit_splits=(*army.unit_splits, record),
    )
