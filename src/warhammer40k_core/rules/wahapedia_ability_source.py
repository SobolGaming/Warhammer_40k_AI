from __future__ import annotations

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind


class WahapediaAbilitySourceError(ValueError):
    """Raised when a Wahapedia ability surface cannot be classified."""


def catalog_ability_source_kind_from_wahapedia_type(
    ability_type: object,
) -> CatalogAbilitySourceKind:
    source_kind = supported_catalog_ability_source_kind_from_wahapedia_type(ability_type)
    if source_kind is None:
        raise WahapediaAbilitySourceError("Unsupported datasheet ability type.")
    return source_kind


def supported_catalog_ability_source_kind_from_wahapedia_type(
    ability_type: object,
) -> CatalogAbilitySourceKind | None:
    if (
        type(ability_type) is not str
        or not ability_type.strip()
        or ability_type != ability_type.strip()
    ):
        raise WahapediaAbilitySourceError("Ability type must be non-empty stripped text.")
    normalized = ability_type.casefold()
    if normalized == "core":
        return CatalogAbilitySourceKind.CORE
    if normalized == "faction":
        return CatalogAbilitySourceKind.FACTION
    if normalized == "datasheet":
        return CatalogAbilitySourceKind.DATASHEET
    if normalized in {"wargear", "wargear profile"}:
        return CatalogAbilitySourceKind.WARGEAR
    if normalized == "primarch" or normalized.startswith(("special", "fortification")):
        return CatalogAbilitySourceKind.DATASHEET
    return None
