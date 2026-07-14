from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.engine.phase import GameLifecycleError


@dataclass(frozen=True, slots=True)
class CatalogDescriptorConsumptionRecord:
    ability_id: str
    source_kind: CatalogAbilitySourceKind
    semantic_categories: tuple[str, ...]
    runtime_consumer_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.ability_id) is not str or not self.ability_id.strip():
            raise GameLifecycleError("Descriptor consumption ability_id must be a string.")
        if type(self.source_kind) is not CatalogAbilitySourceKind:
            raise GameLifecycleError("Descriptor consumption source_kind must be catalog data.")
        object.__setattr__(
            self,
            "semantic_categories",
            _validated_text_tuple("semantic_categories", self.semantic_categories),
        )
        object.__setattr__(
            self,
            "runtime_consumer_ids",
            _validated_text_tuple("runtime_consumer_ids", self.runtime_consumer_ids),
        )

    @property
    def identity(self) -> tuple[CatalogAbilitySourceKind, str]:
        return self.source_kind, self.ability_id


def catalog_descriptor_consumption_for(
    descriptor: DatasheetAbilityDescriptor,
) -> CatalogDescriptorConsumptionRecord | None:
    if type(descriptor) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Descriptor consumption lookup requires catalog data.")
    records = _default_records()
    matches = tuple(
        record
        for record in records
        if record.identity == (descriptor.source_kind, descriptor.ability_id)
    )
    if len(matches) > 1:
        raise GameLifecycleError("Descriptor consumption registry contains duplicate identities.")
    return None if not matches else matches[0]


def _default_records() -> tuple[CatalogDescriptorConsumptionRecord, ...]:
    from warhammer40k_core.engine.core_descriptor_consumption import (
        core_descriptor_consumption_records,
    )
    from warhammer40k_core.engine.faction_content.descriptor_consumption import (
        faction_descriptor_consumption_records,
    )

    records = (*core_descriptor_consumption_records(), *faction_descriptor_consumption_records())
    identities = tuple(record.identity for record in records)
    if len(identities) != len(set(identities)):
        raise GameLifecycleError("Descriptor consumption registry identities must be unique.")
    return tuple(sorted(records, key=lambda record: (record.source_kind.value, record.ability_id)))


def _validated_text_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise GameLifecycleError(f"Descriptor consumption {field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        if type(value) is not str or not value.strip():
            raise GameLifecycleError(f"Descriptor consumption {field_name} values must be strings.")
        if value in seen:
            raise GameLifecycleError(
                f"Descriptor consumption {field_name} must not contain duplicates."
            )
        seen.add(value)
        validated.append(value)
    return tuple(validated)
