from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.unit import (
    MovementStatus,
    Unit,
    UnitMember,
    UnitPayload,
    movement_status_from_token,
)


class AttachedUnitError(ValueError):
    """Raised when attached-unit data violates CORE V2 invariants."""


class AttachedUnitPayload(TypedDict):
    attached_unit_id: str
    bodyguard: UnitPayload
    leaders: list[UnitPayload]
    support_units: list[UnitPayload]


@dataclass(frozen=True, slots=True)
class AttachedUnit:
    attached_unit_id: str
    bodyguard: Unit
    leaders: tuple[Unit, ...]
    support_units: tuple[Unit, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attached_unit_id",
            _validate_attached_unit_id(self.attached_unit_id),
        )
        bodyguard = _validate_unit("AttachedUnit bodyguard", self.bodyguard)
        if type(self.leaders) is not tuple:
            raise AttachedUnitError("AttachedUnit leaders must be a tuple.")
        if type(self.support_units) is not tuple:
            raise AttachedUnitError("AttachedUnit support_units must be a tuple.")
        leaders = tuple(_validate_unit("AttachedUnit leader", unit) for unit in self.leaders)
        if not leaders:
            raise AttachedUnitError("AttachedUnit leaders must not be empty.")
        support_units = tuple(
            _validate_unit("AttachedUnit support unit", unit) for unit in self.support_units
        )

        leaders = tuple(sorted(leaders, key=lambda unit: unit.unit_id))
        support_units = tuple(sorted(support_units, key=lambda unit: unit.unit_id))
        units = (bodyguard, *leaders, *support_units)
        _validate_unique_unit_ids(units)
        _validate_unique_model_ids(units)
        _validate_shared_movement_status(units)

        object.__setattr__(self, "bodyguard", bodyguard)
        object.__setattr__(self, "leaders", leaders)
        object.__setattr__(self, "support_units", support_units)

    def stable_identity(self) -> str:
        return f"attached-unit:{self.attached_unit_id}"

    def units(self) -> tuple[Unit, ...]:
        return (self.bodyguard, *self.leaders, *self.support_units)

    def unit_ids(self) -> tuple[str, ...]:
        return tuple(unit.unit_id for unit in self.units())

    def all_models(self) -> tuple[UnitMember, ...]:
        return tuple(member for unit in self.units() for member in unit.own_models)

    def alive_models(self) -> tuple[UnitMember, ...]:
        return tuple(member for unit in self.units() for member in unit.alive_own_models())

    @property
    def movement_status(self) -> MovementStatus:
        return self.bodyguard.movement_status

    def with_movement_status(self, movement_status: MovementStatus) -> Self:
        status = movement_status_from_token(movement_status)
        return type(self)(
            attached_unit_id=self.attached_unit_id,
            bodyguard=self.bodyguard.with_movement_status(status),
            leaders=tuple(unit.with_movement_status(status) for unit in self.leaders),
            support_units=tuple(unit.with_movement_status(status) for unit in self.support_units),
        )

    def to_payload(self) -> AttachedUnitPayload:
        return {
            "attached_unit_id": self.attached_unit_id,
            "bodyguard": self.bodyguard.to_payload(),
            "leaders": [unit.to_payload() for unit in self.leaders],
            "support_units": [unit.to_payload() for unit in self.support_units],
        }

    @classmethod
    def from_payload(cls, payload: AttachedUnitPayload) -> Self:
        return cls(
            attached_unit_id=payload["attached_unit_id"],
            bodyguard=Unit.from_payload(payload["bodyguard"]),
            leaders=tuple(Unit.from_payload(unit) for unit in payload["leaders"]),
            support_units=tuple(Unit.from_payload(unit) for unit in payload["support_units"]),
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise AttachedUnitError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise AttachedUnitError(f"{field_name} must not be empty.")
    return stripped


def _validate_attached_unit_id(value: object) -> str:
    identifier = _validate_identifier("AttachedUnit attached_unit_id", value)
    if identifier.startswith("attached-unit:"):
        raise AttachedUnitError(
            "AttachedUnit attached_unit_id must not include the stable identity prefix."
        )
    return identifier


def _validate_unit(field_name: str, value: object) -> Unit:
    if type(value) is not Unit:
        raise AttachedUnitError(f"{field_name} must be a Unit.")
    return value


def _validate_unique_unit_ids(units: tuple[Unit, ...]) -> None:
    seen: set[str] = set()
    for unit in units:
        if unit.unit_id in seen:
            raise AttachedUnitError("AttachedUnit units must not contain duplicate unit_ids.")
        seen.add(unit.unit_id)


def _validate_unique_model_ids(units: tuple[Unit, ...]) -> None:
    seen: set[str] = set()
    for unit in units:
        for member in unit.own_models:
            if member.model_id in seen:
                raise AttachedUnitError("AttachedUnit units must not contain duplicate model_ids.")
            seen.add(member.model_id)


def _validate_shared_movement_status(units: tuple[Unit, ...]) -> None:
    statuses = {unit.movement_status for unit in units}
    if len(statuses) != 1:
        raise AttachedUnitError("AttachedUnit units must share one movement_status.")
