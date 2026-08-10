from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.tracked_target_state import attached_rules_unit_owner_ids


class StartingStrengthRecordLike(Protocol):
    @property
    def player_id(self) -> str: ...

    @property
    def unit_instance_id(self) -> str: ...


class StartingAttachedUnitRecordLike(Protocol):
    @property
    def player_id(self) -> str: ...

    @property
    def attached_unit_instance_id(self) -> str: ...

    @property
    def component_unit_instance_ids(self) -> tuple[str, ...]: ...


def ranged_attack_history_unit_owner_ids(
    *,
    army_definitions: Sequence[ArmyDefinition],
    starting_strength_records: Sequence[StartingStrengthRecordLike],
    starting_attached_unit_records: Sequence[StartingAttachedUnitRecordLike],
) -> dict[str, str]:
    owner_ids = {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }
    owner_ids.update(attached_rules_unit_owner_ids(tuple(army_definitions)))
    owner_ids.update(
        (record.unit_instance_id, record.player_id) for record in starting_strength_records
    )
    owner_ids.update(
        (record.attached_unit_instance_id, record.player_id)
        for record in starting_attached_unit_records
    )
    return owner_ids


def ranged_attack_history_source_unit_ids(
    *,
    unit_instance_id: str,
    starting_attached_unit_records: Sequence[StartingAttachedUnitRecordLike],
) -> set[str]:
    return {
        unit_instance_id,
        *(
            record.attached_unit_instance_id
            for record in starting_attached_unit_records
            if unit_instance_id in record.component_unit_instance_ids
        ),
    }


__all__ = (
    "ranged_attack_history_source_unit_ids",
    "ranged_attack_history_unit_owner_ids",
)
