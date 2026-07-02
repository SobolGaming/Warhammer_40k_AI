from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator


class UnitError(ValueError):
    """Raised when unit data violates CORE V2 invariants."""


class MovementStatus(StrEnum):
    READY = "ready"
    REMAINED_STATIONARY = "remained_stationary"
    NORMAL_MOVE = "normal_move"
    ADVANCED = "advanced"
    FELL_BACK = "fell_back"


class UnitMemberPayload(TypedDict):
    model_id: str
    name: str
    starting_wounds: int
    wounds_remaining: int


class UnitPayload(TypedDict):
    unit_id: str
    name: str
    own_models: list[UnitMemberPayload]
    movement_status: str


@dataclass(frozen=True, slots=True)
class UnitMember:
    model_id: str
    name: str
    starting_wounds: int
    wounds_remaining: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _validate_model_id(self.model_id))
        object.__setattr__(self, "name", _validate_identifier("UnitMember name", self.name))
        starting_wounds = _validate_positive_int(
            "UnitMember starting_wounds",
            self.starting_wounds,
        )
        wounds_remaining = _validate_non_negative_int(
            "UnitMember wounds_remaining",
            self.wounds_remaining,
        )
        if wounds_remaining > starting_wounds:
            raise UnitError("UnitMember wounds_remaining must not exceed starting_wounds.")
        object.__setattr__(self, "starting_wounds", starting_wounds)
        object.__setattr__(self, "wounds_remaining", wounds_remaining)

    @classmethod
    def ready(cls, model_id: str, name: str, wounds: int = 1) -> Self:
        return cls(
            model_id=model_id,
            name=name,
            starting_wounds=wounds,
            wounds_remaining=wounds,
        )

    @property
    def is_alive(self) -> bool:
        return self.wounds_remaining > 0

    def with_wounds_remaining(self, wounds_remaining: int) -> Self:
        return type(self)(
            model_id=self.model_id,
            name=self.name,
            starting_wounds=self.starting_wounds,
            wounds_remaining=wounds_remaining,
        )

    def to_payload(self) -> UnitMemberPayload:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "starting_wounds": self.starting_wounds,
            "wounds_remaining": self.wounds_remaining,
        }

    @classmethod
    def from_payload(cls, payload: UnitMemberPayload) -> Self:
        return cls(
            model_id=payload["model_id"],
            name=payload["name"],
            starting_wounds=payload["starting_wounds"],
            wounds_remaining=payload["wounds_remaining"],
        )


@dataclass(frozen=True, slots=True)
class Unit:
    unit_id: str
    name: str
    own_models: tuple[UnitMember, ...]
    movement_status: MovementStatus = MovementStatus.READY

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit_id", _validate_unit_id(self.unit_id))
        object.__setattr__(self, "name", _validate_identifier("Unit name", self.name))
        if type(self.own_models) is not tuple:
            raise UnitError("Unit own_models must be a tuple.")
        own_models = tuple(_validate_unit_member(member) for member in self.own_models)
        if not own_models:
            raise UnitError("Unit own_models must not be empty.")
        _validate_unique_model_ids("Unit own_models", own_models)
        object.__setattr__(
            self,
            "own_models",
            tuple(sorted(own_models, key=lambda member: member.model_id)),
        )
        object.__setattr__(
            self,
            "movement_status",
            movement_status_from_token(self.movement_status),
        )

    def stable_identity(self) -> str:
        return f"unit:{self.unit_id}"

    def own_model_ids(self) -> tuple[str, ...]:
        return tuple(member.model_id for member in self.own_models)

    def alive_own_models(self) -> tuple[UnitMember, ...]:
        return tuple(member for member in self.own_models if member.is_alive)

    def alive_model_ids(self) -> tuple[str, ...]:
        return tuple(member.model_id for member in self.alive_own_models())

    def with_movement_status(self, movement_status: MovementStatus) -> Self:
        return type(self)(
            unit_id=self.unit_id,
            name=self.name,
            own_models=self.own_models,
            movement_status=movement_status,
        )

    def with_member_wounds(self, model_id: str, wounds_remaining: int) -> Self:
        requested_model_id = _validate_model_id(model_id)
        found = False
        members: list[UnitMember] = []
        for member in self.own_models:
            if member.model_id == requested_model_id:
                found = True
                members.append(member.with_wounds_remaining(wounds_remaining))
                continue
            members.append(member)
        if not found:
            raise UnitError("Unit own_models does not contain the requested model_id.")
        return type(self)(
            unit_id=self.unit_id,
            name=self.name,
            own_models=tuple(members),
            movement_status=self.movement_status,
        )

    def to_payload(self) -> UnitPayload:
        return {
            "unit_id": self.unit_id,
            "name": self.name,
            "own_models": [member.to_payload() for member in self.own_models],
            "movement_status": self.movement_status.value,
        }

    @classmethod
    def from_payload(cls, payload: UnitPayload) -> Self:
        return cls(
            unit_id=payload["unit_id"],
            name=payload["name"],
            own_models=tuple(UnitMember.from_payload(member) for member in payload["own_models"]),
            movement_status=movement_status_from_token(payload["movement_status"]),
        )


def movement_status_from_token(token: object) -> MovementStatus:
    if type(token) is MovementStatus:
        return token
    if type(token) is not str:
        raise UnitError("MovementStatus token must be a string.")
    try:
        return MovementStatus(token)
    except ValueError as exc:
        raise UnitError(f"Unsupported movement status token: {token}.") from exc


_validate_identifier = IdentifierValidator(UnitError)


def _validate_unit_id(value: object) -> str:
    identifier = _validate_identifier("Unit unit_id", value)
    if identifier.startswith("unit:"):
        raise UnitError("Unit unit_id must not include the stable identity prefix.")
    return identifier


def _validate_model_id(value: object) -> str:
    identifier = _validate_identifier("UnitMember model_id", value)
    if identifier.startswith("model:"):
        raise UnitError("UnitMember model_id must not include the stable identity prefix.")
    return identifier


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise UnitError(f"{field_name} must be an integer.")
    if value < 1:
        raise UnitError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise UnitError(f"{field_name} must be an integer.")
    if value < 0:
        raise UnitError(f"{field_name} must not be negative.")
    return value


def _validate_unit_member(value: object) -> UnitMember:
    if type(value) is not UnitMember:
        raise UnitError("Unit own_models must contain UnitMember values.")
    return value


def _validate_unique_model_ids(field_name: str, members: tuple[UnitMember, ...]) -> None:
    seen: set[str] = set()
    for member in members:
        if member.model_id in seen:
            raise UnitError(f"{field_name} must not contain duplicate model_ids.")
        seen.add(member.model_id)
