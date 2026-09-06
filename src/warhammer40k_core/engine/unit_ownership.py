"""Immutable source identity for a physical component created by a unit split."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator


class UnitOwnershipError(ValueError):
    """Physical membership lacks a consistent source identity."""


class SplitUnitOriginPayload(TypedDict):
    source_unit_instance_id: str
    split_id: str
    successor_index: int


@dataclass(frozen=True, slots=True)
class SplitUnitOrigin:
    source_unit_instance_id: str
    split_id: str
    successor_index: int

    def __post_init__(self) -> None:
        validate = IdentifierValidator(UnitOwnershipError)
        validate("split source unit", self.source_unit_instance_id)
        validate("split identity", self.split_id)
        if type(self.successor_index) is not int or self.successor_index not in (0, 1):
            raise UnitOwnershipError("Split successor index must be 0 or 1.")

    @property
    def unit_instance_id(self) -> str:
        digest = hashlib.sha256(self.split_id.encode()).hexdigest()
        return f"{self.source_unit_instance_id}:split:{digest}:{self.successor_index}"

    def validate_membership(self, unit_instance_id: str, model_instance_id: str) -> None:
        if unit_instance_id != self.unit_instance_id:
            raise UnitOwnershipError("Split physical unit identity drifted from its origin.")
        if not model_instance_id.startswith(f"{self.source_unit_instance_id}:"):
            raise UnitOwnershipError("Split model identity drifted from its original source unit.")

    def to_payload(self) -> SplitUnitOriginPayload:
        return {
            "source_unit_instance_id": self.source_unit_instance_id,
            "split_id": self.split_id,
            "successor_index": self.successor_index,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict or set(cast(dict[str, object], payload)) != {
            "source_unit_instance_id",
            "split_id",
            "successor_index",
        }:
            raise UnitOwnershipError("Split origin requires its exact closed payload.")
        raw = cast(SplitUnitOriginPayload, payload)
        return cls(**raw)


def validate_physical_model_owner(
    *, unit_instance_id: str, model_instance_id: str, split_origin: SplitUnitOrigin | None
) -> None:
    if split_origin is None:
        if not model_instance_id.startswith(f"{unit_instance_id}:"):
            raise UnitOwnershipError("Model IDs must be scoped to unit_instance_id.")
        return
    if type(split_origin) is not SplitUnitOrigin:
        raise UnitOwnershipError("Physical split origin must be typed.")
    split_origin.validate_membership(unit_instance_id, model_instance_id)
