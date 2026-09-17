"""Active core instances retain the complete catalog occurrence inventory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict

from warhammer40k_core.core.ability_sources import (
    AbilitySourceInstance,
    AbilitySourceInstancePayload,
)
from warhammer40k_core.core.core_ability_family import CoreAbilityFamily
from warhammer40k_core.core.datasheet import DatasheetAbilityDescriptor
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.unit_factory import UnitInstance


class CoreAbilitySelectionPayload(TypedDict):
    family: str
    instance_id: str
    decision_result_id: str
    opportunity_id: str
    runtime_source: NotRequired[AbilitySourceInstancePayload]


@dataclass(frozen=True, slots=True)
class CoreAbilitySelection:
    family: CoreAbilityFamily
    instance_id: str
    decision_result_id: str
    opportunity_id: str
    runtime_source: AbilitySourceInstance | None = None

    def __post_init__(self) -> None:
        if type(self.family) is not CoreAbilityFamily:
            raise GameLifecycleError("Core ability selection requires a canonical family.")
        if self.runtime_source is not None and (
            type(self.runtime_source) is not AbilitySourceInstance
            or self.runtime_source.instance_id != self.instance_id
        ):
            raise GameLifecycleError("Core runtime source instance identity drift.")
        for value in (self.instance_id, self.decision_result_id, self.opportunity_id):
            if type(value) is not str or not value or value.strip() != value:
                raise GameLifecycleError("Core ability selection requires nonempty identifiers.")

    def to_payload(self) -> CoreAbilitySelectionPayload:
        payload: CoreAbilitySelectionPayload = {
            "family": self.family.value,
            "instance_id": self.instance_id,
            "decision_result_id": self.decision_result_id,
            "opportunity_id": self.opportunity_id,
        }
        if self.runtime_source is not None:
            payload["runtime_source"] = self.runtime_source.to_payload()
        return payload

    @classmethod
    def from_payload(cls, payload: CoreAbilitySelectionPayload) -> Self:
        try:
            family = CoreAbilityFamily(payload["family"])
        except ValueError as exc:
            raise GameLifecycleError("Core ability selection family is unsupported.") from exc
        return cls(
            family=family,
            instance_id=payload["instance_id"],
            decision_result_id=payload["decision_result_id"],
            opportunity_id=payload["opportunity_id"],
            runtime_source=AbilitySourceInstance.from_payload(payload["runtime_source"])
            if "runtime_source" in payload
            else None,
        )


def core_instance_groups(
    unit: UnitInstance,
) -> tuple[tuple[CoreAbilityFamily, tuple[AbilitySourceInstance, ...]], ...]:
    descriptors = {
        (ability.source_id, ability.ability_id): ability for ability in unit.datasheet_abilities
    }
    groups: dict[CoreAbilityFamily, list[AbilitySourceInstance]] = {}
    for source in unit.ability_source_instances():
        family = descriptors[(source.source_id, source.ability_id)].core_family
        if family is not None:
            groups.setdefault(family, []).append(source)
    for source in unit.core_keyword_sources:
        groups.setdefault(CoreAbilityFamily.DEEP_STRIKE, []).append(source)
    return tuple(
        (family, tuple(sorted(sources, key=lambda source: source.instance_id)))
        for family, sources in sorted(groups.items())
    )


def validate_unit_core_selections(unit: UnitInstance) -> tuple[CoreAbilitySelection, ...]:
    choices = unit.core_ability_selections
    if type(choices) is not tuple or any(
        type(choice) is not CoreAbilitySelection for choice in choices
    ):
        raise GameLifecycleError("Unit core ability selections must be typed choices.")
    groups = dict(core_instance_groups(unit))
    seen: set[CoreAbilityFamily] = set()
    for choice in choices:
        sources = groups.get(choice.family, ())
        if choice.family in seen:
            raise GameLifecycleError("Unit core ability selection source inventory drift.")
        if choice.runtime_source is not None:
            if choice.runtime_source.owner_id != unit.unit_instance_id:
                raise GameLifecycleError("Unit core runtime source owner drift.")
        elif len(sources) < 2 or choice.instance_id not in {
            source.instance_id for source in sources
        }:
            raise GameLifecycleError("Unit core ability selection source inventory drift.")
        seen.add(choice.family)
    return tuple(sorted(choices, key=lambda choice: choice.family.value))


def active_core_descriptors(
    unit: UnitInstance,
    family: CoreAbilityFamily,
) -> tuple[DatasheetAbilityDescriptor, ...]:
    descriptors = tuple(
        ability for ability in unit.datasheet_abilities if ability.core_family is family
    )
    choices = tuple(choice for choice in unit.core_ability_selections if choice.family is family)
    if (
        choices
        and choices[0].runtime_source is not None
        and choices[0].instance_id
        not in {source.instance_id for source in unit.ability_source_instances()}
    ):
        return ()
    if len(descriptors) < 2:
        return descriptors
    if len(choices) != 1:
        raise GameLifecycleError("Duplicated core ability requires controlling-player selection.")
    sources = dict(core_instance_groups(unit))[family]
    source = next(source for source in sources if source.instance_id == choices[0].instance_id)
    return tuple(
        ability
        for ability in descriptors
        if (ability.source_id, ability.ability_id) == (source.source_id, source.ability_id)
    )


def validate_core_keyword_sources(unit: UnitInstance) -> tuple[AbilitySourceInstance, ...]:
    sources = unit.core_keyword_sources
    if type(sources) is not tuple or any(
        type(source) is not AbilitySourceInstance for source in sources
    ):
        raise GameLifecycleError("Core keyword occurrences require typed sources.")
    if len({source.instance_id for source in sources}) != len(sources):
        raise GameLifecycleError("Core keyword occurrences must be unique.")
    for source in sources:
        if source.owner_id != unit.unit_instance_id or source.ability_id != "core-deep-strike":
            raise GameLifecycleError("Core keyword occurrence owner or family drift.")
    return tuple(sorted(sources, key=lambda source: source.instance_id))


def core_keyword_sources_after_grant(
    unit: UnitInstance,
    *,
    keywords: tuple[str, ...],
    source_id: str,
    source_instance_id: str,
) -> tuple[AbilitySourceInstance, ...]:
    # Deep Strike has real keyword-grant consumers (roster rules and Enhancements).
    # Preserve their occurrences even when the canonical keyword is already present.
    if "DEEP STRIKE" not in keywords:
        return unit.core_keyword_sources
    sources = list(unit.core_keyword_sources)
    has_native_descriptor = any(
        ability.core_family is CoreAbilityFamily.DEEP_STRIKE for ability in unit.datasheet_abilities
    )
    if not sources and not has_native_descriptor and "DEEP STRIKE" in unit.keywords:
        sources.append(
            AbilitySourceInstance(
                owner_id=unit.unit_instance_id,
                source_id=f"datasheet:{unit.datasheet_id}",
                source_instance_id=f"datasheet:{unit.datasheet_id}",
                slot_id="keyword:DEEP STRIKE",
                ability_id="core-deep-strike",
            )
        )
    source = AbilitySourceInstance(
        owner_id=unit.unit_instance_id,
        source_id=source_id,
        source_instance_id=source_instance_id,
        slot_id="keyword:DEEP STRIKE",
        ability_id="core-deep-strike",
    )
    if source not in sources:
        sources.append(source)
    return tuple(sorted(sources, key=lambda source: source.instance_id))
