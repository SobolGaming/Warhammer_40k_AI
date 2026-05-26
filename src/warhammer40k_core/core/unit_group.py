from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.attached_unit import AttachedUnit, AttachedUnitPayload
from warhammer40k_core.core.unit import (
    MovementStatus,
    Unit,
    UnitMember,
    UnitPayload,
    movement_status_from_token,
)


class UnitGroupError(ValueError):
    """Raised when a group-aware unit operation is invalid."""


class UnitGroupKind(StrEnum):
    SINGLE = "single"
    ATTACHED = "attached"


class UnitGroupEventPayload(TypedDict):
    unit_group_id: str
    unit_ids: list[str]
    model_ids: list[str]
    alive_model_ids: list[str]
    movement_status: str


class UnitGroupPayload(TypedDict):
    kind: str
    unit: UnitPayload | None
    attached_unit: AttachedUnitPayload | None


@dataclass(frozen=True, slots=True)
class UnitGroup:
    unit: Unit | None = None
    attached_unit: AttachedUnit | None = None

    def __post_init__(self) -> None:
        if (self.unit is None) == (self.attached_unit is None):
            raise UnitGroupError("UnitGroup must contain exactly one unit source.")
        if self.unit is not None and type(self.unit) is not Unit:
            raise UnitGroupError("UnitGroup unit must be a Unit.")
        if self.attached_unit is not None and type(self.attached_unit) is not AttachedUnit:
            raise UnitGroupError("UnitGroup attached_unit must be an AttachedUnit.")

    @classmethod
    def single(cls, unit: Unit) -> Self:
        if type(unit) is not Unit:
            raise UnitGroupError("UnitGroup single unit must be a Unit.")
        return cls(unit=unit)

    @classmethod
    def attached(cls, attached_unit: AttachedUnit) -> Self:
        if type(attached_unit) is not AttachedUnit:
            raise UnitGroupError("UnitGroup attached_unit must be an AttachedUnit.")
        return cls(attached_unit=attached_unit)

    @property
    def kind(self) -> UnitGroupKind:
        if self.unit is not None:
            return UnitGroupKind.SINGLE
        return UnitGroupKind.ATTACHED

    @property
    def movement_status(self) -> MovementStatus:
        if self.unit is not None:
            return self.unit.movement_status
        if self.attached_unit is None:
            raise UnitGroupError("UnitGroup has no unit source.")
        return self.attached_unit.movement_status

    def stable_identity(self) -> str:
        if self.unit is not None:
            return f"unit-group:single:{self.unit.unit_id}"
        if self.attached_unit is None:
            raise UnitGroupError("UnitGroup has no unit source.")
        return f"unit-group:attached:{self.attached_unit.attached_unit_id}"

    def units(self) -> tuple[Unit, ...]:
        if self.unit is not None:
            return (self.unit,)
        if self.attached_unit is None:
            raise UnitGroupError("UnitGroup has no unit source.")
        return self.attached_unit.units()

    def unit_ids(self) -> tuple[str, ...]:
        return tuple(unit.unit_id for unit in self.units())

    def all_models(self) -> tuple[UnitMember, ...]:
        return tuple(member for unit in self.units() for member in unit.own_models)

    def alive_models(self) -> tuple[UnitMember, ...]:
        return tuple(member for unit in self.units() for member in unit.alive_own_models())

    def all_model_ids(self) -> tuple[str, ...]:
        return tuple(member.model_id for member in self.all_models())

    def alive_model_ids(self) -> tuple[str, ...]:
        return tuple(member.model_id for member in self.alive_models())

    def model_ids_for_movement(self) -> tuple[str, ...]:
        return self.alive_model_ids()

    def model_ids_for_damage_allocation(self) -> tuple[str, ...]:
        return self.alive_model_ids()

    def model_ids_for_event_logging(self) -> tuple[str, ...]:
        return self.all_model_ids()

    def model_ids_for_line_of_sight(self) -> tuple[str, ...]:
        return self.alive_model_ids()

    def targetable_model_ids(self) -> tuple[str, ...]:
        return self.alive_model_ids()

    def event_subject_payload(self) -> UnitGroupEventPayload:
        return {
            "unit_group_id": self.stable_identity(),
            "unit_ids": list(self.unit_ids()),
            "model_ids": list(self.model_ids_for_event_logging()),
            "alive_model_ids": list(self.alive_model_ids()),
            "movement_status": self.movement_status.value,
        }

    def with_movement_status(self, movement_status: MovementStatus) -> Self:
        status = movement_status_from_token(movement_status)
        if self.unit is not None:
            return type(self).single(self.unit.with_movement_status(status))
        if self.attached_unit is None:
            raise UnitGroupError("UnitGroup has no unit source.")
        return type(self).attached(self.attached_unit.with_movement_status(status))

    def to_payload(self) -> UnitGroupPayload:
        if self.unit is not None:
            return {
                "kind": UnitGroupKind.SINGLE.value,
                "unit": self.unit.to_payload(),
                "attached_unit": None,
            }
        if self.attached_unit is None:
            raise UnitGroupError("UnitGroup has no unit source.")
        return {
            "kind": UnitGroupKind.ATTACHED.value,
            "unit": None,
            "attached_unit": self.attached_unit.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: UnitGroupPayload) -> Self:
        kind = unit_group_kind_from_token(payload["kind"])
        if kind is UnitGroupKind.SINGLE:
            unit_payload = payload["unit"]
            if unit_payload is None:
                raise UnitGroupError("Single UnitGroup payload must include unit.")
            if payload["attached_unit"] is not None:
                raise UnitGroupError("Single UnitGroup payload must not include attached_unit.")
            return cls.single(Unit.from_payload(unit_payload))

        attached_unit_payload = payload["attached_unit"]
        if attached_unit_payload is None:
            raise UnitGroupError("Attached UnitGroup payload must include attached_unit.")
        if payload["unit"] is not None:
            raise UnitGroupError("Attached UnitGroup payload must not include unit.")
        return cls.attached(AttachedUnit.from_payload(attached_unit_payload))


def unit_group_kind_from_token(token: object) -> UnitGroupKind:
    if type(token) is not str:
        raise UnitGroupError("UnitGroup kind token must be a string.")
    try:
        return UnitGroupKind(token)
    except ValueError as exc:
        raise UnitGroupError(f"Unsupported UnitGroup kind token: {token}.") from exc
