"""Resolve source-declared weapon selectors against equipped catalog identities.

A weapon-family selector covers that Wargear's profiles. An exact profile selector
covers only that profile. Resolution happens at choice admission; downstream
modifiers consume the resulting stable IDs, never infer families from name suffixes.
"""

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance


def weapon_name_match_token(value: str) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Catalog named weapon name must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("Catalog named weapon name must not be empty.")
    return " ".join(stripped.casefold().replace("-", " ").split())


def equipped_named_weapon_profile_ids(
    *, army_catalog: ArmyCatalog, model: ModelInstance, weapon_names: tuple[str, ...]
) -> tuple[str, ...]:
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Catalog named weapon lookup requires an ArmyCatalog.")
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Catalog named weapon lookup requires a model instance.")
    catalog = {gear.wargear_id: gear for gear in army_catalog.wargear}
    if any(gear_id not in catalog for gear_id in model.wargear_ids):
        raise GameLifecycleError("Catalog named weapon lookup found unknown wargear.")
    equipped = tuple(catalog[gear_id] for gear_id in dict.fromkeys(model.wargear_ids))
    profile_ids: set[str] = set()
    for name in weapon_names:
        token = weapon_name_match_token(name)
        matched_gears: list[tuple[str, tuple[str, ...]]] = []
        for gear in equipped:
            family_match = token == weapon_name_match_token(gear.name)
            ids = tuple(
                profile.profile_id
                for profile in gear.weapon_profiles
                if family_match or token == weapon_name_match_token(profile.name)
            )
            if not family_match and len(ids) > 1:
                raise GameLifecycleError(
                    "Catalog named weapon selector has ambiguous equipped profiles."
                )
            if ids:
                matched_gears.append((gear.wargear_id, ids))
        if len(matched_gears) > 1:
            raise GameLifecycleError(
                "Catalog named weapon selector has ambiguous equipped wargear."
            )
        for _gear_id, ids in matched_gears:
            profile_ids.update(ids)
    return tuple(sorted(profile_ids))
