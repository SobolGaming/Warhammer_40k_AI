from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.datasheet import CatalogAbilitySupport, DatasheetAbilityDescriptor
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance


@dataclass(frozen=True, slots=True)
class CoreKeywordAbilitySpec:
    keyword: str
    ability_ids: frozenset[str]
    name_words: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeadlyDemiseAbilityProfile:
    source_id: str
    mortal_wounds_token: str


DEEP_STRIKE_ABILITY_IDS = frozenset({"000008343", "core-deep-strike", "deep-strike"})
INFILTRATORS_ABILITY_IDS = frozenset({"core-infiltrators", "infiltrators"})
LEADER_ABILITY_IDS = frozenset({"core-leader", "leader"})
SUPPORT_ABILITY_IDS = frozenset({"core-support", "support"})
SCOUTS_ABILITY_IDS = frozenset({"core-scouts", "scouts"})
FIRING_DECK_ABILITY_IDS = frozenset({"core-firing-deck", "firing-deck"})
DEADLY_DEMISE_ABILITY_IDS = frozenset({"core-deadly-demise", "deadly-demise"})

_DEEP_STRIKE_SPEC = CoreKeywordAbilitySpec(
    keyword="DEEP_STRIKE",
    ability_ids=DEEP_STRIKE_ABILITY_IDS,
    name_words=("DEEP", "STRIKE"),
)
_INFILTRATORS_SPEC = CoreKeywordAbilitySpec(
    keyword="INFILTRATORS",
    ability_ids=INFILTRATORS_ABILITY_IDS,
    name_words=("INFILTRATORS",),
)
_LEADER_SPEC = CoreKeywordAbilitySpec(
    keyword="LEADER",
    ability_ids=LEADER_ABILITY_IDS,
    name_words=("LEADER",),
)
_SUPPORT_SPEC = CoreKeywordAbilitySpec(
    keyword="SUPPORT",
    ability_ids=SUPPORT_ABILITY_IDS,
    name_words=("SUPPORT",),
)
_SCOUTS_SPEC = CoreKeywordAbilitySpec(
    keyword="SCOUTS",
    ability_ids=SCOUTS_ABILITY_IDS,
    name_words=("SCOUTS",),
)
_FIRING_DECK_SPEC = CoreKeywordAbilitySpec(
    keyword="FIRING_DECK",
    ability_ids=FIRING_DECK_ABILITY_IDS,
    name_words=("FIRING", "DECK"),
)
_DEADLY_DEMISE_SPEC = CoreKeywordAbilitySpec(
    keyword="DEADLY_DEMISE",
    ability_ids=DEADLY_DEMISE_ABILITY_IDS,
    name_words=("DEADLY", "DEMISE"),
)


def unit_has_deep_strike(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_DEEP_STRIKE_SPEC)


def descriptor_is_deep_strike(descriptor: DatasheetAbilityDescriptor) -> bool:
    return _descriptor_matches_spec(descriptor, _DEEP_STRIKE_SPEC)


def unit_has_infiltrators(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_INFILTRATORS_SPEC)


def unit_has_leader(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_LEADER_SPEC)


def unit_has_support(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_SUPPORT_SPEC)


def unit_has_scouts(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_SCOUTS_SPEC)


def unit_has_firing_deck(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_FIRING_DECK_SPEC)


def unit_has_deadly_demise(unit: UnitInstance) -> bool:
    return _unit_has_core_keyword_ability(unit=unit, spec=_DEADLY_DEMISE_SPEC)


def scouts_ability_descriptors_for_unit(
    unit: UnitInstance,
) -> tuple[DatasheetAbilityDescriptor, ...]:
    return _ability_descriptors_for_unit(unit=unit, spec=_SCOUTS_SPEC)


def scouts_distance_inches_from_descriptor(
    descriptor: DatasheetAbilityDescriptor,
) -> float:
    _require_descriptor_only(descriptor=descriptor, ability_name="Scouts")
    if not _descriptor_matches_spec(descriptor, _SCOUTS_SPEC):
        raise GameLifecycleError("Scouts distance requires a Scouts datasheet ability descriptor.")
    token = _single_parameter_token(descriptor=descriptor, ability_name="Scouts")
    return _positive_float_token(token=token, field_name="Scouts descriptor distance_inches")


def firing_deck_value_for_unit(unit: UnitInstance) -> int | None:
    descriptors = _ability_descriptors_for_unit(unit=unit, spec=_FIRING_DECK_SPEC)
    if not descriptors:
        if unit_has_keyword(unit, _FIRING_DECK_SPEC.keyword):
            raise GameLifecycleError(
                "Firing Deck keyword requires a structured datasheet ability descriptor."
            )
        return None
    if len(descriptors) > 1:
        raise GameLifecycleError("Datasheet must not contain duplicate Firing Deck descriptors.")
    descriptor = next(iter(descriptors))
    _require_descriptor_only(descriptor=descriptor, ability_name="Firing Deck")
    token = _single_parameter_token(descriptor=descriptor, ability_name="Firing Deck")
    return _positive_int_token(token=token, field_name="Firing Deck descriptor value")


def deadly_demise_profile_for_unit(unit: UnitInstance) -> DeadlyDemiseAbilityProfile | None:
    descriptors = _ability_descriptors_for_unit(unit=unit, spec=_DEADLY_DEMISE_SPEC)
    if not descriptors:
        if unit_has_keyword(unit, _DEADLY_DEMISE_SPEC.keyword):
            raise GameLifecycleError(
                "Deadly Demise keyword requires a structured datasheet ability descriptor."
            )
        return None
    if len(descriptors) > 1:
        raise GameLifecycleError("Datasheet must not contain duplicate Deadly Demise descriptors.")
    descriptor = next(iter(descriptors))
    _require_descriptor_only(descriptor=descriptor, ability_name="Deadly Demise")
    token = _single_parameter_token(descriptor=descriptor, ability_name="Deadly Demise")
    return DeadlyDemiseAbilityProfile(source_id=descriptor.source_id, mortal_wounds_token=token)


def _unit_has_core_keyword_ability(
    *,
    unit: UnitInstance,
    spec: CoreKeywordAbilitySpec,
) -> bool:
    _validate_unit(unit)
    return unit_has_keyword(unit, spec.keyword) or bool(
        _ability_descriptors_for_unit(unit=unit, spec=spec)
    )


def unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    _validate_unit(unit)
    requested_keyword = _canonical_token(keyword)
    return requested_keyword in {_canonical_token(stored) for stored in unit.keywords}


def _ability_descriptors_for_unit(
    *,
    unit: UnitInstance,
    spec: CoreKeywordAbilitySpec,
) -> tuple[DatasheetAbilityDescriptor, ...]:
    _validate_unit(unit)
    return tuple(
        sorted(
            (
                ability
                for ability in unit.datasheet_abilities
                if _descriptor_matches_spec(ability, spec)
            ),
            key=lambda ability: ability.ability_id,
        )
    )


def _descriptor_matches_spec(
    descriptor: DatasheetAbilityDescriptor,
    spec: CoreKeywordAbilitySpec,
) -> bool:
    if type(descriptor) is not DatasheetAbilityDescriptor:
        raise GameLifecycleError("Core keyword ability lookup requires ability descriptors.")
    if type(spec) is not CoreKeywordAbilitySpec:
        raise GameLifecycleError("Core keyword ability lookup requires an ability spec.")
    if descriptor.ability_id in spec.ability_ids:
        return True
    return _ability_name_matches_family(name=descriptor.name, family_words=spec.name_words)


def _ability_name_matches_family(
    *,
    name: str,
    family_words: tuple[str, ...],
) -> bool:
    words = _canonical_words(name)
    if words and words[0] == "CORE":
        words = words[1:]
    return len(words) >= len(family_words) and words[: len(family_words)] == family_words


def _require_descriptor_only(
    *,
    descriptor: DatasheetAbilityDescriptor,
    ability_name: str,
) -> None:
    if descriptor.support is not CatalogAbilitySupport.DESCRIPTOR_ONLY:
        raise GameLifecycleError(f"{ability_name} descriptor must be descriptor-only catalog data.")


def _single_parameter_token(
    *,
    descriptor: DatasheetAbilityDescriptor,
    ability_name: str,
) -> str:
    if len(descriptor.parameter_tokens) != 1:
        raise GameLifecycleError(f"{ability_name} descriptor requires exactly one value token.")
    return _normalize_parameter_token(descriptor.parameter_tokens[0])


def _positive_int_token(*, token: str, field_name: str) -> int:
    try:
        value = int(token)
    except ValueError as exc:
        raise GameLifecycleError(f"{field_name} token must be an int.") from exc
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value


def _positive_float_token(*, token: str, field_name: str) -> float:
    try:
        value = float(token)
    except ValueError as exc:
        raise GameLifecycleError(f"{field_name} token must be numeric.") from exc
    if value <= 0.0:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value


def _normalize_parameter_token(token: str) -> str:
    if type(token) is not str:
        raise GameLifecycleError("Ability parameter token must be a string.")
    stripped = token.strip().removesuffix('"').strip()
    if not stripped:
        raise GameLifecycleError("Ability parameter token must not be empty.")
    return stripped.upper()


def _canonical_token(value: str) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Ability or keyword token must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("Ability or keyword token must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _canonical_words(value: str) -> tuple[str, ...]:
    if type(value) is not str:
        raise GameLifecycleError("Ability name must be a string.")
    normalized = value.upper().replace("-", " ").replace("_", " ").replace('"', " ")
    return tuple(word for word in normalized.split() if word)


def _validate_unit(unit: UnitInstance) -> None:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Core keyword ability check requires a UnitInstance.")
