"""One immutable selected catalog; small fresh Core ability consumer states.

Constructed grants/descriptors are explicit supported Core inputs. They do not
admit a faction provider, a mixed-faction legal roster or a full-game setup.
"""

import hashlib
import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import pytest
from tests.support.section02_fixtures import Section02Definitions
from tools.generate_ability_support_matrix import (
    _ability_support_catalog_package,  # pyright: ignore[reportPrivateUsage]
)

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.unit_factory import UnitInstance

LORD = "000004078"
BODY = "000004080"
AVENGERS = "000000593"
RANGERS = "000000592"
MAULER = "000000968"
HAWKS = "000000600"
SERPENT = "000000599"
SPAWN = "000004090"
IDS = (LORD, BODY, AVENGERS, RANGERS, MAULER, HAWKS, SERPENT, SPAWN)


@pytest.fixture(scope="session")
def section24_definitions(
    selected_army_source_index: Path | None,
) -> Iterator[Section02Definitions]:
    started = perf_counter()
    package = _ability_support_catalog_package(
        datasheet_ids=IDS, source_index_dir=selected_army_source_index
    )

    def digest() -> str:
        return hashlib.sha256(json.dumps(package.to_payload(), sort_keys=True).encode()).hexdigest()

    before = digest()
    seconds = perf_counter() - started
    print(f"Section24 preparation: {seconds:.6f}s; one immutable eight-datasheet package")
    yield Section02Definitions(package, seconds)
    assert digest() == before


def core_ability(family: str, *tokens: str) -> DatasheetAbilityDescriptor:
    return DatasheetAbilityDescriptor(
        ability_id=f"core-{family}",
        name=family.replace("-", " ").title(),
        source_id=f"constructed:s24:{family}:{':'.join(tokens) or 'bare'}",
        source_kind=CatalogAbilitySourceKind.CORE,
        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
        effect_description="Explicit Core ability consumer input",
        parameter_tokens=tokens,
    )


def with_core(unit: UnitInstance, family: str, *tokens: str) -> UnitInstance:
    return replace(unit, datasheet_abilities=(core_ability(family, *tokens),))


def bolt(d: Section02Definitions) -> WeaponProfile:
    return d.weapon(f"{LORD}:bolt-pistol")


def profile_grant(
    profile: WeaponProfile,
    keyword: WeaponKeyword,
    descriptor: AbilityDescriptor | None = None,
) -> WeaponProfile:
    from warhammer40k_core.core.weapon_ability_sources import grant_weapon_ability

    return grant_weapon_ability(
        profile,
        keyword=keyword,
        ability=descriptor,
        source_id=f"constructed:s24:{keyword.value}",
        source_instance_id=f"constructed:s24:{keyword.value}:grant",
    )


def with_profile(d: Section02Definitions, profile: WeaponProfile) -> Section02Definitions:
    """Change only this small catalog view, retaining physical equipped identities."""
    catalog = replace(
        d.package.army_catalog,
        wargear=tuple(
            replace(
                w,
                weapon_profiles=tuple(
                    profile if p.profile_id == profile.profile_id else p for p in w.weapon_profiles
                ),
            )
            for w in d.package.army_catalog.wargear
        ),
    )
    return Section02Definitions(replace(d.package, army_catalog=catalog), d.preparation_seconds)
