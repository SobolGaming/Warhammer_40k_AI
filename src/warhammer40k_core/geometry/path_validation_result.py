"""Typed path validation results shared by physical movement owners."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.geometry.movement_envelope import (
    MovementDistanceWitness,
    MovementDistanceWitnessPayload,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.validation import IdentifierValidator

if TYPE_CHECKING:
    from warhammer40k_core.geometry.base_contact import DeemedBaseContact, DeemedBaseContactPayload
    from warhammer40k_core.geometry.movement_query_payloads import MovementQueryPayload
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery

_validate_identifier = IdentifierValidator(GeometryError)


class PathConstraintViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_id: str | None
    blocker_id: str | None


class PathValidationResultPayload(TypedDict):
    deemed_base_contacts: NotRequired[list[DeemedBaseContactPayload]]
    base_contact_query: NotRequired[MovementQueryPayload]
    is_valid: bool
    violations: list[PathConstraintViolationPayload]
    sampled_pose_count: int
    model_collision_check_count: int
    terrain_collision_check_count: int
    engagement_check_count: int
    movement_distance_witness: MovementDistanceWitnessPayload | None


@dataclass(frozen=True, slots=True)
class PathConstraintViolation:
    violation_code: str
    message: str
    model_id: str | None = None
    blocker_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            _validate_identifier("PathConstraintViolation violation_code", self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("PathConstraintViolation message", self.message),
        )
        object.__setattr__(
            self,
            "model_id",
            _validate_optional_identifier("PathConstraintViolation model_id", self.model_id),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier("PathConstraintViolation blocker_id", self.blocker_id),
        )

    def to_payload(self) -> PathConstraintViolationPayload:
        return {
            "violation_code": self.violation_code,
            "message": self.message,
            "model_id": self.model_id,
            "blocker_id": self.blocker_id,
        }

    @classmethod
    def from_payload(cls, payload: PathConstraintViolationPayload) -> Self:
        return cls(
            violation_code=payload["violation_code"],
            message=payload["message"],
            model_id=payload["model_id"],
            blocker_id=payload["blocker_id"],
        )


@dataclass(frozen=True, slots=True)
class PathValidationResult:
    deemed_base_contacts: tuple[DeemedBaseContact, ...] = ()
    base_contact_query: MovementReachabilityQuery | None = None
    violations: tuple[PathConstraintViolation, ...] = ()
    sampled_pose_count: int = 0
    model_collision_check_count: int = 0
    terrain_collision_check_count: int = 0
    engagement_check_count: int = 0
    movement_distance_witness: MovementDistanceWitness | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.geometry.base_contact import DeemedBaseContact

        if type(self.deemed_base_contacts) is not tuple or any(
            type(c) is not DeemedBaseContact for c in self.deemed_base_contacts
        ):
            raise GeometryError("Path results require typed deemed base contact witnesses.")
        if any(c.movement_query != self.base_contact_query for c in self.deemed_base_contacts):
            raise GeometryError("Contact evidence differs from its accepted movement query.")
        if self.deemed_base_contacts and (
            self.violations
            or len({c.enemy_model_id for c in self.deemed_base_contacts})
            != len(self.deemed_base_contacts)
        ):
            raise GeometryError("Invalid or duplicate path contact authority.")
        object.__setattr__(
            self,
            "violations",
            _validate_path_constraint_violations(self.violations),
        )
        object.__setattr__(
            self,
            "sampled_pose_count",
            _validate_non_negative_int(
                "PathValidationResult sampled_pose_count",
                self.sampled_pose_count,
            ),
        )
        object.__setattr__(
            self,
            "model_collision_check_count",
            _validate_non_negative_int(
                "PathValidationResult model_collision_check_count",
                self.model_collision_check_count,
            ),
        )
        object.__setattr__(
            self,
            "terrain_collision_check_count",
            _validate_non_negative_int(
                "PathValidationResult terrain_collision_check_count",
                self.terrain_collision_check_count,
            ),
        )
        object.__setattr__(
            self,
            "engagement_check_count",
            _validate_non_negative_int(
                "PathValidationResult engagement_check_count",
                self.engagement_check_count,
            ),
        )
        if (
            self.movement_distance_witness is not None
            and type(self.movement_distance_witness) is not MovementDistanceWitness
        ):
            raise GeometryError(
                "PathValidationResult movement_distance_witness must be a MovementDistanceWitness."
            )

    @classmethod
    def valid(
        cls,
        *,
        sampled_pose_count: int,
        model_collision_check_count: int,
        terrain_collision_check_count: int,
        engagement_check_count: int,
        movement_distance_witness: MovementDistanceWitness | None = None,
    ) -> Self:
        return cls(
            sampled_pose_count=sampled_pose_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_check_count=engagement_check_count,
            movement_distance_witness=movement_distance_witness,
        )

    @classmethod
    def invalid(
        cls,
        violation: PathConstraintViolation,
        *,
        sampled_pose_count: int,
        model_collision_check_count: int,
        terrain_collision_check_count: int,
        engagement_check_count: int,
        movement_distance_witness: MovementDistanceWitness | None = None,
    ) -> Self:
        return cls(
            violations=(violation,),
            sampled_pose_count=sampled_pose_count,
            model_collision_check_count=model_collision_check_count,
            terrain_collision_check_count=terrain_collision_check_count,
            engagement_check_count=engagement_check_count,
            movement_distance_witness=movement_distance_witness,
        )

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> PathValidationResultPayload:
        payload: PathValidationResultPayload = {
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "sampled_pose_count": self.sampled_pose_count,
            "model_collision_check_count": self.model_collision_check_count,
            "terrain_collision_check_count": self.terrain_collision_check_count,
            "engagement_check_count": self.engagement_check_count,
            "movement_distance_witness": (
                None
                if self.movement_distance_witness is None
                else self.movement_distance_witness.to_payload()
            ),
        }
        if self.base_contact_query is not None:
            from warhammer40k_core.geometry.movement_query_payloads import query_payload

            payload["base_contact_query"] = query_payload(self.base_contact_query)
        if self.deemed_base_contacts:
            payload["deemed_base_contacts"] = [c.to_payload() for c in self.deemed_base_contacts]
        return payload

    @classmethod
    def from_payload(cls, payload: PathValidationResultPayload) -> Self:
        from warhammer40k_core.geometry.base_contact import DeemedBaseContact
        from warhammer40k_core.geometry.movement_query_payloads import query_from_payload

        result = cls(
            base_contact_query=None
            if "base_contact_query" not in payload
            else query_from_payload(payload["base_contact_query"]),
            deemed_base_contacts=tuple(
                DeemedBaseContact.from_payload(c) for c in payload.get("deemed_base_contacts", [])
            ),
            violations=tuple(
                PathConstraintViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            sampled_pose_count=payload["sampled_pose_count"],
            model_collision_check_count=payload["model_collision_check_count"],
            terrain_collision_check_count=payload["terrain_collision_check_count"],
            engagement_check_count=payload["engagement_check_count"],
            movement_distance_witness=(
                None
                if payload["movement_distance_witness"] is None
                else MovementDistanceWitness.from_payload(payload["movement_distance_witness"])
            ),
        )
        if result.is_valid != payload["is_valid"]:
            raise GeometryError("PathValidationResult payload validity does not match violations.")
        return result


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 0:
        raise GeometryError(f"{field_name} must not be negative.")
    return value


def _validate_path_constraint_violations(
    values: object,
) -> tuple[PathConstraintViolation, ...]:
    if type(values) is not tuple:
        raise GeometryError("PathValidationResult violations must be a tuple.")
    return tuple(
        _validate_path_constraint_violation("PathValidationResult violation", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_path_constraint_violation(
    field_name: str,
    value: object,
) -> PathConstraintViolation:
    if type(value) is not PathConstraintViolation:
        raise GeometryError(f"{field_name} must be a PathConstraintViolation.")
    return value
