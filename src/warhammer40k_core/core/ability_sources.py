"""Source occurrence identity, independent of ability family or parameter values."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator

if TYPE_CHECKING:
    from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor


class AbilitySourceError(ValueError):
    """An ability occurrence has missing, conflicting or stale source identity."""


class AbilitySourceInstancePayload(TypedDict):
    instance_id: str
    owner_id: str
    source_id: str
    source_instance_id: str
    slot_id: str
    ability_id: str


@dataclass(frozen=True, slots=True)
class AbilitySourceInstance:
    owner_id: str
    source_id: str
    source_instance_id: str
    slot_id: str
    ability_id: str

    def __post_init__(self) -> None:
        validate = IdentifierValidator(AbilitySourceError)
        for name in ("owner_id", "source_id", "source_instance_id", "slot_id", "ability_id"):
            value = getattr(self, name)
            if validate(f"Ability source {name}", value) != value:
                raise AbilitySourceError("Ability source identifiers must be canonical.")

    @property
    def instance_id(self) -> str:
        identity = (self.owner_id, self.source_id, self.source_instance_id, self.slot_id)
        encoded = json.dumps(identity, ensure_ascii=True, separators=(",", ":")).encode()
        return "ability-instance:" + hashlib.sha256(encoded).hexdigest()

    def to_payload(self) -> AbilitySourceInstancePayload:
        return {
            "instance_id": self.instance_id,
            "owner_id": self.owner_id,
            "source_id": self.source_id,
            "source_instance_id": self.source_instance_id,
            "slot_id": self.slot_id,
            "ability_id": self.ability_id,
        }

    @classmethod
    def from_payload(cls, payload: AbilitySourceInstancePayload) -> Self:
        if type(cast(object, payload)) is not dict or set(payload) != set(
            AbilitySourceInstancePayload.__annotations__
        ):
            raise AbilitySourceError("Ability source payload has invalid fields.")
        result = cls(
            owner_id=payload["owner_id"],
            source_id=payload["source_id"],
            source_instance_id=payload["source_instance_id"],
            slot_id=payload["slot_id"],
            ability_id=payload["ability_id"],
        )
        if result.instance_id != payload["instance_id"]:
            raise AbilitySourceError("Ability source instance identity drifted.")
        return result


def validate_datasheet_ability_sources(
    values: tuple[DatasheetAbilityDescriptor, ...],
) -> tuple[DatasheetAbilityDescriptor, ...]:
    from warhammer40k_core.core.datasheet import (
        CatalogAbilitySourceKind,
        DatasheetAbilityDescriptor,
    )

    if type(values) is not tuple:
        raise AbilitySourceError("Datasheet ability sources must be a tuple.")
    seen: set[tuple[str, str]] = set()
    for value in values:
        if type(value) is not DatasheetAbilityDescriptor:
            raise AbilitySourceError("Datasheet ability sources must contain ability descriptors.")
        # CORE duplicates have independent source rows. Other catalog families retain
        # their existing definition-ID uniqueness contract.
        source = value.source_id if value.source_kind is CatalogAbilitySourceKind.CORE else ""
        key = (value.ability_id, source)
        if key in seen:
            raise AbilitySourceError(
                "Datasheet abilities must not contain duplicate ability IDs from the same source."
            )
        seen.add(key)
    return values


def datasheet_ability_sources(
    values: tuple[DatasheetAbilityDescriptor, ...],
    *,
    owner_id: str,
) -> tuple[AbilitySourceInstance, ...]:
    return tuple(
        sorted(
            (
                AbilitySourceInstance(
                    owner_id=owner_id,
                    source_id=value.source_id,
                    source_instance_id=value.source_id,
                    slot_id=value.ability_id,
                    ability_id=value.ability_id,
                )
                for value in validate_datasheet_ability_sources(values)
            ),
            key=lambda source: source.instance_id,
        )
    )


def merge_datasheet_ability_source(
    values: tuple[DatasheetAbilityDescriptor, ...],
    ability: DatasheetAbilityDescriptor,
) -> tuple[DatasheetAbilityDescriptor, ...]:
    validate_datasheet_ability_sources(values)
    for existing in values:
        if (existing.ability_id, existing.source_id) == (ability.ability_id, ability.source_id):
            if existing != ability:
                raise AbilitySourceError("Datasheet ability source has conflicting semantics.")
            return values
    return validate_datasheet_ability_sources((*values, ability))
