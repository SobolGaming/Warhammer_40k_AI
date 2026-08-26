from __future__ import annotations

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    DatasheetAbilityDescriptor,
    DatasheetDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.validation import canonical_keyword_token
from warhammer40k_core.engine.datasheet_faction_access import (
    DatasheetFactionAccessBinding,
)
from warhammer40k_core.engine.list_validation_errors import ListValidationError

BATTLE_FOCUS_CATALOG_ABILITY_ID = "000009894"
DISPARATE_PATHS_CATALOG_ABILITY_ID = "000009896"
DISPARATE_PATHS_MUSTERING_CONSUMER_ID = "army-mustering:aeldari-disparate-paths"
DISPARATE_PATHS_FACTION_ACCESS_BINDING_ID = "datasheet-faction-access:aeldari-disparate-paths"
ASURYANI_FACTION_KEYWORD = "ASURYANI"
HARLEQUINS_FACTION_KEYWORD = "HARLEQUINS"


def disparate_paths_descriptor(descriptor: DatasheetAbilityDescriptor) -> bool:
    if type(descriptor) is not DatasheetAbilityDescriptor:
        raise ListValidationError("Disparate Paths descriptor must be catalog data.")
    return (
        descriptor.source_kind is CatalogAbilitySourceKind.FACTION
        and descriptor.ability_id == DISPARATE_PATHS_CATALOG_ABILITY_ID
    )


def aeldari_disparate_paths_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Disparate Paths datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Disparate Paths faction must be a FactionDefinition.")
    faction_keywords = {canonical_keyword_token(keyword) for keyword in faction.faction_keywords}
    datasheet_faction_keywords = {
        canonical_keyword_token(keyword) for keyword in datasheet.keywords.faction_keywords
    }
    if ASURYANI_FACTION_KEYWORD not in faction_keywords:
        return False
    if BATTLE_FOCUS_CATALOG_ABILITY_ID not in faction.army_rule_ids:
        return False
    if HARLEQUINS_FACTION_KEYWORD not in datasheet_faction_keywords:
        return False
    return any(disparate_paths_descriptor(ability) for ability in datasheet.abilities)


def datasheet_faction_access_bindings() -> tuple[DatasheetFactionAccessBinding, ...]:
    return (
        DatasheetFactionAccessBinding(
            binding_id=DISPARATE_PATHS_FACTION_ACCESS_BINDING_ID,
            source_ability_id=DISPARATE_PATHS_CATALOG_ABILITY_ID,
            runtime_consumer_id=DISPARATE_PATHS_MUSTERING_CONSUMER_ID,
            predicate=aeldari_disparate_paths_datasheet_allowed_for_faction,
        ),
    )
