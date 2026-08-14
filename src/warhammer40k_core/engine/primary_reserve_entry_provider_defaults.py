from __future__ import annotations

from importlib import import_module
from typing import cast

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryAbilityProviderDefinition,
    PrimaryReserveEntryOccurrenceValidator,
)

_PROVIDER_MODULE_NAMES = (
    "warhammer40k_core.engine.catalog_turn_end_reserves",
    (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "aeldari.detachments.corsair_coterie.enhancements"
    ),
    (
        "warhammer40k_core.engine.faction_content.warhammer_40000_11th."
        "chaos_daemons.detachments.shadow_legion.enhancements"
    ),
    ("warhammer40k_core.engine.faction_content.warhammer_40000_11th.grey_knights.army_rule"),
)
_OCCURRENCE_VALIDATOR_MODULE_NAMES = (
    "warhammer40k_core.engine.cult_ambush_reserve_entry_integrity",
)


def default_primary_reserve_entry_ability_provider_definitions() -> tuple[
    PrimaryReserveEntryAbilityProviderDefinition, ...
]:
    """Compose the source-backed during-battle reserve ability providers."""
    definitions: list[PrimaryReserveEntryAbilityProviderDefinition] = []
    for module_name in _PROVIDER_MODULE_NAMES:
        module = import_module(module_name)
        definition = module.PRIMARY_RESERVE_ENTRY_PROVIDER_DEFINITION
        if type(definition) is not PrimaryReserveEntryAbilityProviderDefinition:
            raise GameLifecycleError("Reserve-entry provider module definition is invalid.")
        definitions.append(definition)
    return tuple(definitions)


def default_primary_reserve_entry_occurrence_validators() -> tuple[
    PrimaryReserveEntryOccurrenceValidator, ...
]:
    """Compose bespoke occurrence validators outside generic lifecycle code."""
    validators: list[PrimaryReserveEntryOccurrenceValidator] = []
    for module_name in _OCCURRENCE_VALIDATOR_MODULE_NAMES:
        module = import_module(module_name)
        validator = module.validated_primary_reserve_entry_occurrences
        if not callable(validator):
            raise GameLifecycleError("Reserve-entry occurrence validator is invalid.")
        validators.append(cast(PrimaryReserveEntryOccurrenceValidator, validator))
    return tuple(validators)


__all__ = (
    "default_primary_reserve_entry_ability_provider_definitions",
    "default_primary_reserve_entry_occurrence_validators",
)
