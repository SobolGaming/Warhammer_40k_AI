from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator


class AttachedUnitFormationError(ValueError):
    """Raised when a mustered attached-unit formation is invalid."""


class AttachedUnitFormationPayload(TypedDict):
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: list[str]
    support_unit_instance_ids: list[str]
    component_unit_instance_ids: list[str]
    source_id: str
    attachment_source_ids: list[str]


@dataclass(frozen=True, slots=True)
class AttachedUnitFormation:
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: tuple[str, ...] = ()
    support_unit_instance_ids: tuple[str, ...] = ()
    component_unit_instance_ids: tuple[str, ...] = ()
    source_id: str = ""
    attachment_source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attached_unit_instance_id",
            _validate_attached_unit_instance_id(
                "AttachedUnitFormation attached_unit_instance_id",
                self.attached_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_unit_instance_id",
            _validate_identifier(
                "AttachedUnitFormation bodyguard_unit_instance_id",
                self.bodyguard_unit_instance_id,
            ),
        )
        leader_ids = _validate_identifier_tuple(
            "AttachedUnitFormation leader_unit_instance_ids",
            self.leader_unit_instance_ids,
            min_length=0,
        )
        support_ids = _validate_identifier_tuple(
            "AttachedUnitFormation support_unit_instance_ids",
            self.support_unit_instance_ids,
            min_length=0,
        )
        if not leader_ids and not support_ids:
            raise AttachedUnitFormationError(
                "AttachedUnitFormation requires a leader or support unit."
            )
        component_ids = _validate_identifier_tuple(
            "AttachedUnitFormation component_unit_instance_ids",
            self.component_unit_instance_ids,
            min_length=2,
        )
        expected_component_ids = tuple(
            sorted((self.bodyguard_unit_instance_id, *leader_ids, *support_ids))
        )
        if component_ids != expected_component_ids:
            raise AttachedUnitFormationError(
                "AttachedUnitFormation component_unit_instance_ids must match components."
            )
        object.__setattr__(self, "leader_unit_instance_ids", leader_ids)
        object.__setattr__(self, "support_unit_instance_ids", support_ids)
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("AttachedUnitFormation source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "attachment_source_ids",
            _validate_identifier_tuple(
                "AttachedUnitFormation attachment_source_ids",
                self.attachment_source_ids,
                min_length=1,
            ),
        )

    def to_payload(self) -> AttachedUnitFormationPayload:
        return {
            "attached_unit_instance_id": self.attached_unit_instance_id,
            "bodyguard_unit_instance_id": self.bodyguard_unit_instance_id,
            "leader_unit_instance_ids": list(self.leader_unit_instance_ids),
            "support_unit_instance_ids": list(self.support_unit_instance_ids),
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "source_id": self.source_id,
            "attachment_source_ids": list(self.attachment_source_ids),
        }

    @classmethod
    def from_payload(cls, payload: AttachedUnitFormationPayload) -> Self:
        return cls(
            attached_unit_instance_id=payload["attached_unit_instance_id"],
            bodyguard_unit_instance_id=payload["bodyguard_unit_instance_id"],
            leader_unit_instance_ids=tuple(payload["leader_unit_instance_ids"]),
            support_unit_instance_ids=tuple(payload["support_unit_instance_ids"]),
            component_unit_instance_ids=tuple(payload["component_unit_instance_ids"]),
            source_id=payload["source_id"],
            attachment_source_ids=tuple(payload["attachment_source_ids"]),
        )


_validate_identifier = IdentifierValidator(AttachedUnitFormationError)


def _validate_attached_unit_instance_id(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    if not identifier.startswith("attached-unit:"):
        raise AttachedUnitFormationError(f"{field_name} must use attached-unit identity.")
    return identifier


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise AttachedUnitFormationError(f"{field_name} must be a tuple.")
    if len(values) < min_length:
        raise AttachedUnitFormationError(f"{field_name} must contain at least {min_length} values.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise AttachedUnitFormationError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))
