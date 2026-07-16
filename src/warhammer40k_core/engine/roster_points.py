from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator


class RosterPointError(ValueError):
    """Raised when a source-backed roster point record is invalid."""


class RosterUnitPointValuePayload(TypedDict):
    unit_selection_id: str
    points: int
    source_id: str


class RosterEnhancementPointValuePayload(TypedDict):
    enhancement_id: str
    target_unit_selection_id: str
    points: int
    source_id: str


@dataclass(frozen=True, slots=True)
class RosterUnitPointValue:
    unit_selection_id: str
    points: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_selection_id",
            _validate_unprefixed_identifier(
                "RosterUnitPointValue unit_selection_id",
                self.unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "points",
            _validate_non_negative_int("RosterUnitPointValue points", self.points),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("RosterUnitPointValue source_id", self.source_id),
        )

    def to_payload(self) -> RosterUnitPointValuePayload:
        return {
            "unit_selection_id": self.unit_selection_id,
            "points": self.points,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: RosterUnitPointValuePayload) -> Self:
        return cls(
            unit_selection_id=payload["unit_selection_id"],
            points=payload["points"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class RosterEnhancementPointValue:
    enhancement_id: str
    target_unit_selection_id: str
    points: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "enhancement_id",
            _validate_unprefixed_identifier(
                "RosterEnhancementPointValue enhancement_id",
                self.enhancement_id,
                "enhancement:",
            ),
        )
        object.__setattr__(
            self,
            "target_unit_selection_id",
            _validate_unprefixed_identifier(
                "RosterEnhancementPointValue target_unit_selection_id",
                self.target_unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "points",
            _validate_non_negative_int("RosterEnhancementPointValue points", self.points),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("RosterEnhancementPointValue source_id", self.source_id),
        )

    def to_payload(self) -> RosterEnhancementPointValuePayload:
        return {
            "enhancement_id": self.enhancement_id,
            "target_unit_selection_id": self.target_unit_selection_id,
            "points": self.points,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: RosterEnhancementPointValuePayload) -> Self:
        return cls(
            enhancement_id=payload["enhancement_id"],
            target_unit_selection_id=payload["target_unit_selection_id"],
            points=payload["points"],
            source_id=payload["source_id"],
        )


def validate_roster_unit_point_tuple(
    field_name: str,
    values: object,
    *,
    error_type: type[ValueError],
) -> tuple[RosterUnitPointValue, ...]:
    if type(values) is not tuple:
        raise error_type(f"{field_name} must be a tuple.")
    validated: list[RosterUnitPointValue] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not RosterUnitPointValue:
            raise error_type(f"{field_name} must contain RosterUnitPointValue values.")
        if value.unit_selection_id in seen:
            raise error_type("RosterUnitPointValue values must be unique by unit.")
        seen.add(value.unit_selection_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda point: point.unit_selection_id))


def validate_roster_enhancement_point_tuple(
    field_name: str,
    values: object,
    *,
    error_type: type[ValueError],
) -> tuple[RosterEnhancementPointValue, ...]:
    if type(values) is not tuple:
        raise error_type(f"{field_name} must be a tuple.")
    validated: list[RosterEnhancementPointValue] = []
    seen: set[tuple[str, str]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not RosterEnhancementPointValue:
            raise error_type(f"{field_name} must contain RosterEnhancementPointValue values.")
        key = (value.target_unit_selection_id, value.enhancement_id)
        if key in seen:
            raise error_type(
                "RosterEnhancementPointValue values must be unique by target and Enhancement."
            )
        seen.add(key)
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda point: (
                point.target_unit_selection_id,
                point.enhancement_id,
            ),
        )
    )


def validate_source_backed_point_ledger(
    *,
    owner: str,
    points_source_package_id: str | None,
    unit_selection_ids: tuple[str, ...],
    unit_points: tuple[RosterUnitPointValue, ...],
    enhancement_assignments: tuple[tuple[str, str, str], ...],
    enhancement_point_values: tuple[RosterEnhancementPointValue, ...],
    error_type: type[ValueError],
) -> None:
    if points_source_package_id is None:
        if enhancement_point_values:
            raise error_type(f"{owner} enhancement_point_values require points_source_package_id.")
        return
    if set(unit_selection_ids) != {point.unit_selection_id for point in unit_points}:
        raise error_type(
            f"{owner} source-backed unit point records must cover exactly the selected units."
        )
    assignment_by_key = {
        (target_unit_selection_id, enhancement_id): source_id
        for target_unit_selection_id, enhancement_id, source_id in enhancement_assignments
    }
    points_by_key = {
        (point.target_unit_selection_id, point.enhancement_id): point
        for point in enhancement_point_values
    }
    if assignment_by_key.keys() != points_by_key.keys():
        raise error_type(
            f"{owner} source-backed Enhancement point records must cover every assignment."
        )
    for key, source_id in assignment_by_key.items():
        if source_id != points_by_key[key].source_id:
            raise error_type(f"{owner} Enhancement assignment source must match its point record.")
    source_prefix = f"{points_source_package_id}:"
    point_source_ids = (
        *(point.source_id for point in unit_points),
        *(point.source_id for point in enhancement_point_values),
    )
    if any(not source_id.startswith(source_prefix) for source_id in point_source_ids):
        raise error_type(
            f"{owner} point record source IDs must belong to points_source_package_id."
        )


def mismatched_catalog_enhancement_point_values(
    *,
    catalog_points_by_id: dict[str, int | None],
    point_values: tuple[RosterEnhancementPointValue, ...],
) -> tuple[RosterEnhancementPointValue, ...]:
    return tuple(
        point
        for point in point_values
        if point.enhancement_id in catalog_points_by_id
        and catalog_points_by_id[point.enhancement_id] != point.points
    )


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise RosterPointError(f"{field_name} must not include the stable identity prefix.")
    return identifier


_validate_identifier = IdentifierValidator(RosterPointError)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise RosterPointError(f"{field_name} must be an integer.")
    if value < 0:
        raise RosterPointError(f"{field_name} must not be negative.")
    return value
