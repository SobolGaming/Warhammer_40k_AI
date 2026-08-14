from __future__ import annotations

from dataclasses import dataclass
from typing import Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.game_state_payloads import StartingAttachedUnitRecordPayload
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_state import StartingStrengthRecord


@dataclass(frozen=True, slots=True)
class StartingAttachedUnitRecord:
    """Frozen battle-start identity for one Attached Unit.

    Core Rules 19.02 makes the models that started the battle in the Attached
    Unit authoritative for its later unit-destroyed trigger.  The exact model
    mapping therefore survives splits, revivals, and runtime materialization.
    """

    player_id: str
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: tuple[str, ...]
    support_unit_instance_ids: tuple[str, ...]
    component_unit_instance_ids: tuple[str, ...]
    starting_model_instance_ids_by_component: tuple[tuple[str, tuple[str, ...]], ...]
    starting_model_count: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StartingAttachedUnitRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "attached_unit_instance_id",
            _validate_identifier(
                "StartingAttachedUnitRecord attached_unit_instance_id",
                self.attached_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_unit_instance_id",
            _validate_identifier(
                "StartingAttachedUnitRecord bodyguard_unit_instance_id",
                self.bodyguard_unit_instance_id,
            ),
        )
        leader_ids = _validate_identifier_tuple(
            "StartingAttachedUnitRecord leader_unit_instance_ids",
            self.leader_unit_instance_ids,
            min_length=0,
        )
        support_ids = _validate_identifier_tuple(
            "StartingAttachedUnitRecord support_unit_instance_ids",
            self.support_unit_instance_ids,
            min_length=0,
        )
        if not leader_ids and not support_ids:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord requires a leader or support unit."
            )
        component_ids = _validate_identifier_tuple(
            "StartingAttachedUnitRecord component_unit_instance_ids",
            self.component_unit_instance_ids,
            min_length=2,
        )
        expected_component_ids = tuple(
            sorted((self.bodyguard_unit_instance_id, *leader_ids, *support_ids))
        )
        if component_ids != expected_component_ids:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord component_unit_instance_ids must match components."
            )
        starting_models_by_component = _validate_starting_attached_model_ids(
            self.starting_model_instance_ids_by_component,
            component_unit_instance_ids=component_ids,
        )
        starting_model_count = _validate_positive_int(
            "StartingAttachedUnitRecord starting_model_count",
            self.starting_model_count,
        )
        if starting_model_count != sum(
            len(model_ids) for _component_id, model_ids in starting_models_by_component
        ):
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model count does not match its frozen mapping."
            )
        object.__setattr__(self, "leader_unit_instance_ids", leader_ids)
        object.__setattr__(self, "support_unit_instance_ids", support_ids)
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(
            self,
            "starting_model_instance_ids_by_component",
            starting_models_by_component,
        )
        object.__setattr__(self, "starting_model_count", starting_model_count)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StartingAttachedUnitRecord source_id", self.source_id),
        )

    @classmethod
    def from_formation(
        cls,
        *,
        player_id: str,
        attached_unit: AttachedUnitFormation,
        unit_by_id: dict[str, UnitInstance],
    ) -> Self:
        if type(attached_unit) is not AttachedUnitFormation:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord derivation requires an AttachedUnitFormation."
            )
        component_ids = tuple(sorted(attached_unit.component_unit_instance_ids))
        starting_models_by_component: list[tuple[str, tuple[str, ...]]] = []
        for component_id in component_ids:
            unit = unit_by_id.get(component_id)
            if unit is None:
                raise GameLifecycleError("StartingAttachedUnitRecord component unit is unknown.")
            starting_models_by_component.append((component_id, tuple(sorted(unit.own_model_ids()))))
        return cls(
            player_id=player_id,
            attached_unit_instance_id=attached_unit.attached_unit_instance_id,
            bodyguard_unit_instance_id=attached_unit.bodyguard_unit_instance_id,
            leader_unit_instance_ids=attached_unit.leader_unit_instance_ids,
            support_unit_instance_ids=attached_unit.support_unit_instance_ids,
            component_unit_instance_ids=component_ids,
            starting_model_instance_ids_by_component=tuple(starting_models_by_component),
            starting_model_count=sum(
                len(model_ids) for _component_id, model_ids in starting_models_by_component
            ),
            source_id=attached_unit.source_id,
        )

    def leader_or_support_unit_instance_ids(self) -> tuple[str, ...]:
        return tuple(sorted((*self.leader_unit_instance_ids, *self.support_unit_instance_ids)))

    def starting_model_instance_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                model_id
                for _component_id, model_ids in self.starting_model_instance_ids_by_component
                for model_id in model_ids
            )
        )

    def starting_model_instance_ids_for_component(
        self,
        component_unit_instance_id: str,
    ) -> tuple[str, ...]:
        requested_component_id = _validate_identifier(
            "component_unit_instance_id",
            component_unit_instance_id,
        )
        matches = tuple(
            model_ids
            for component_id, model_ids in self.starting_model_instance_ids_by_component
            if component_id == requested_component_id
        )
        if len(matches) != 1:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting-model component lookup failed."
            )
        return matches[0]

    def to_payload(self) -> StartingAttachedUnitRecordPayload:
        return {
            "player_id": self.player_id,
            "attached_unit_instance_id": self.attached_unit_instance_id,
            "bodyguard_unit_instance_id": self.bodyguard_unit_instance_id,
            "leader_unit_instance_ids": list(self.leader_unit_instance_ids),
            "support_unit_instance_ids": list(self.support_unit_instance_ids),
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "starting_model_instance_ids_by_component": {
                component_id: list(model_ids)
                for component_id, model_ids in self.starting_model_instance_ids_by_component
            },
            "starting_model_count": self.starting_model_count,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        expected_fields = {
            "player_id",
            "attached_unit_instance_id",
            "bodyguard_unit_instance_id",
            "leader_unit_instance_ids",
            "support_unit_instance_ids",
            "component_unit_instance_ids",
            "starting_model_instance_ids_by_component",
            "starting_model_count",
            "source_id",
        }
        if not isinstance(payload, dict):
            raise GameLifecycleError("StartingAttachedUnitRecord payload must be an object.")
        raw_untyped = cast(dict[object, object], payload)
        if any(type(key) is not str for key in raw_untyped) or set(raw_untyped) != expected_fields:
            raise GameLifecycleError("StartingAttachedUnitRecord payload fields are invalid.")
        raw = cast(dict[str, object], payload)
        leader_ids = _payload_identifier_tuple(
            "StartingAttachedUnitRecord leader_unit_instance_ids",
            raw["leader_unit_instance_ids"],
            min_length=0,
        )
        support_ids = _payload_identifier_tuple(
            "StartingAttachedUnitRecord support_unit_instance_ids",
            raw["support_unit_instance_ids"],
            min_length=0,
        )
        component_ids = _payload_identifier_tuple(
            "StartingAttachedUnitRecord component_unit_instance_ids",
            raw["component_unit_instance_ids"],
            min_length=2,
        )
        raw_models_by_component = raw["starting_model_instance_ids_by_component"]
        if type(raw_models_by_component) is not dict:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model mapping must be an object."
            )
        models_mapping = cast(dict[object, object], raw_models_by_component)
        if any(type(component_id) is not str for component_id in models_mapping):
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model mapping entries are invalid."
            )
        starting_models_by_component = tuple(
            (
                cast(str, component_id),
                _payload_identifier_tuple(
                    "StartingAttachedUnitRecord starting model IDs",
                    model_ids,
                    min_length=1,
                ),
            )
            for component_id, model_ids in models_mapping.items()
        )
        return cls(
            player_id=_validate_identifier(
                "StartingAttachedUnitRecord player_id",
                raw["player_id"],
            ),
            attached_unit_instance_id=_validate_identifier(
                "StartingAttachedUnitRecord attached_unit_instance_id",
                raw["attached_unit_instance_id"],
            ),
            bodyguard_unit_instance_id=_validate_identifier(
                "StartingAttachedUnitRecord bodyguard_unit_instance_id",
                raw["bodyguard_unit_instance_id"],
            ),
            leader_unit_instance_ids=leader_ids,
            support_unit_instance_ids=support_ids,
            component_unit_instance_ids=component_ids,
            starting_model_instance_ids_by_component=starting_models_by_component,
            starting_model_count=_validate_positive_int(
                "StartingAttachedUnitRecord starting_model_count",
                raw["starting_model_count"],
            ),
            source_id=_validate_identifier(
                "StartingAttachedUnitRecord source_id",
                raw["source_id"],
            ),
        )


def starting_attached_unit_records_for_army(
    army_definition: ArmyDefinition,
) -> tuple[StartingAttachedUnitRecord, ...]:
    if type(army_definition) is not ArmyDefinition:
        raise GameLifecycleError(
            "StartingAttachedUnitRecord derivation requires an ArmyDefinition."
        )
    unit_by_id = {unit.unit_instance_id: unit for unit in army_definition.units}
    return tuple(
        sorted(
            (
                StartingAttachedUnitRecord.from_formation(
                    player_id=army_definition.player_id,
                    attached_unit=attached_unit,
                    unit_by_id=unit_by_id,
                )
                for attached_unit in army_definition.attached_units
            ),
            key=lambda record: record.attached_unit_instance_id,
        )
    )


def validate_starting_attached_unit_records(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    player_ids: tuple[str, ...],
    starting_strength_records: list[StartingStrengthRecord],
) -> list[StartingAttachedUnitRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState starting_attached_unit_records must be a list.")

    expected_by_id = {
        record.attached_unit_instance_id: record
        for army_definition in army_definitions
        for record in starting_attached_unit_records_for_army(army_definition)
    }
    physical_owner_by_id = {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }
    starting_strength_by_unit_id = {
        record.unit_instance_id: record.starting_model_count for record in starting_strength_records
    }
    validated: list[StartingAttachedUnitRecord] = []
    seen_attached_unit_ids: set[str] = set()
    seen_component_unit_ids: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StartingAttachedUnitRecord:
            raise GameLifecycleError(
                "GameState starting_attached_unit_records must contain "
                "StartingAttachedUnitRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StartingAttachedUnitRecord player_id is not in this game.")
        if value.attached_unit_instance_id in seen_attached_unit_ids:
            raise GameLifecycleError("GameState starting_attached_unit_records must be unique.")
        seen_attached_unit_ids.add(value.attached_unit_instance_id)
        for component_unit_id in value.component_unit_instance_ids:
            owner = physical_owner_by_id.get(component_unit_id)
            if owner is None:
                raise GameLifecycleError("StartingAttachedUnitRecord component unit is unknown.")
            if owner != value.player_id:
                raise GameLifecycleError("StartingAttachedUnitRecord component player_id drift.")
            if component_unit_id in seen_component_unit_ids:
                raise GameLifecycleError(
                    "StartingAttachedUnitRecord component units must not overlap."
                )
            seen_component_unit_ids.add(component_unit_id)
        authoritative_starting_count = starting_strength_by_unit_id.get(
            value.attached_unit_instance_id
        )
        if authoritative_starting_count is None:
            component_counts = tuple(
                starting_strength_by_unit_id.get(component_id)
                for component_id in value.component_unit_instance_ids
            )
            if any(count is None for count in component_counts):
                raise GameLifecycleError(
                    "StartingAttachedUnitRecord has no starting-strength lineage."
                )
            current_component_starting_count = sum(cast(tuple[int, ...], component_counts))
            if value.starting_model_count > current_component_starting_count:
                raise GameLifecycleError(
                    "StartingAttachedUnitRecord starting model count exceeds its descendants."
                )
        elif value.starting_model_count != authoritative_starting_count:
            raise GameLifecycleError("StartingAttachedUnitRecord starting model count drift.")
        validated.append(value)
    by_id = {record.attached_unit_instance_id: record for record in validated}
    for expected_id, expected_record in expected_by_id.items():
        record = by_id.get(expected_id)
        if record is None:
            raise GameLifecycleError(
                "GameState starting_attached_unit_records must include active attached units."
            )
        if _formation_identity(record) != _formation_identity(expected_record):
            raise GameLifecycleError("StartingAttachedUnitRecord active formation drift.")
    return sorted(validated, key=lambda record: record.attached_unit_instance_id)


def _formation_identity(record: StartingAttachedUnitRecord) -> tuple[object, ...]:
    return (
        record.player_id,
        record.attached_unit_instance_id,
        record.bodyguard_unit_instance_id,
        record.leader_unit_instance_ids,
        record.support_unit_instance_ids,
        record.component_unit_instance_ids,
        record.source_id,
    )


def _validate_starting_attached_model_ids(
    values: object,
    *,
    component_unit_instance_ids: tuple[str, ...],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "StartingAttachedUnitRecord starting model mapping must be a tuple."
        )
    validated: list[tuple[str, tuple[str, ...]]] = []
    seen_components: set[str] = set()
    seen_models: set[str] = set()
    for raw_entry in cast(tuple[object, ...], values):
        if type(raw_entry) is not tuple:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model mapping entry is invalid."
            )
        entry_values = cast(tuple[object, ...], raw_entry)
        if len(entry_values) != 2:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model mapping entry is invalid."
            )
        entry = entry_values
        component_id = _validate_identifier(
            "StartingAttachedUnitRecord starting model component",
            entry[0],
        )
        model_ids = _validate_identifier_tuple(
            "StartingAttachedUnitRecord starting model IDs",
            entry[1],
            min_length=1,
        )
        if component_id in seen_components:
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model components must be unique."
            )
        if seen_models.intersection(model_ids):
            raise GameLifecycleError(
                "StartingAttachedUnitRecord starting model IDs must not overlap."
            )
        seen_components.add(component_id)
        seen_models.update(model_ids)
        validated.append((component_id, model_ids))
    if seen_components != set(component_unit_instance_ids):
        raise GameLifecycleError(
            "StartingAttachedUnitRecord starting model components must match components."
        )
    return tuple(sorted(validated, key=lambda entry: entry[0]))


def _payload_identifier_tuple(
    field_name: str,
    value: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise GameLifecycleError(f"{field_name} must be a list.")
    return _validate_identifier_tuple(
        field_name,
        tuple(cast(list[object], value)),
        min_length=min_length,
    )


def _validate_identifier_tuple(
    field_name: str,
    value: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers = tuple(
        _validate_identifier(field_name, item) for item in cast(tuple[object, ...], value)
    )
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} value(s).")
    if len(set(identifiers)) != len(identifiers):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(identifiers))


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(f"{field_name} must be a positive integer.")
    return value


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "StartingAttachedUnitRecord",
    "starting_attached_unit_records_for_army",
    "validate_starting_attached_unit_records",
)
