"""Apply only the reviewed complete Deep Strike description to current catalog inputs."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Final

from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.core_deep_strike_successor import (
    ABILITY_ID,
    CURRENT_TEXT,
    DEPENDENCY_ID,
    DESCRIPTOR_HASHES,
    SOURCE_ID,
    descriptor_hash,
)
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_deep_strike_description_2026_11 as source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_reserve_lifetimes_2026_09 as ingress,
)

SOURCE_ARTIFACTS: Final = (
    SourceArtifactHash(
        artifact_name="core-deep-strike-description-2026-11.json",
        artifact_hash=source.EXPECTED_ARTIFACT_SHA256,
    ),
    SourceArtifactHash(
        artifact_name="core-reserve-lifetimes-2026-09.json",
        artifact_hash="d22f5ca58b27172445f595ebe4a4763e372162950cb825d48cb7816073c488c1",
    ),
)
OWNERS: Final = {
    "data-package:core-v2:chaos-daemons-bridge-catalog:phase17k-generated": (
        "chaos-daemons-bridge-catalog"
    ),
    "data-package:core-v2:chaos-daemons-roster:2026-07": "core-v2:chaos-daemons-roster:2026-07",
}


def with_current_deep_strike(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Preserve every structured field, requiring the exact reviewed stale descriptors."""
    catalog = package.army_catalog
    known = {owner for rows in DESCRIPTOR_HASHES.values() for owner in rows}
    expected = {row.datasheet_id for row in catalog.datasheets if row.datasheet_id in known}
    occurrences = tuple(
        (row.datasheet_id, a)
        for row in catalog.datasheets
        for a in row.abilities
        if a.ability_id == ABILITY_ID
    )
    if not expected and not occurrences:
        return package
    if OWNERS.get(package.package_id.stable_identity()) != catalog.catalog_id:
        raise ValueError("Deep Strike current catalog owner is unreviewed.")
    reviewed = DESCRIPTOR_HASHES[catalog.catalog_id]
    if len(occurrences) != len(expected) or {owner for owner, _ in occurrences} != expected:
        raise ValueError("Deep Strike reviewed occurrence closure drifted.")
    rule = source.source_rules()[0]
    dependency = next(row for row in ingress.source_rules() if row.source_id == DEPENDENCY_ID)
    source.source_package()
    ingress.source_package()
    if (
        rule.source_id != SOURCE_ID
        or rule.source_text != CURRENT_TEXT
        or rule.dependency_source_ids != (DEPENDENCY_ID,)
        or sha256(dependency.source_text.encode()).hexdigest()
        != "3ebcf9f594a98f20242c6e3272a5bb3ef63345bd1aff0657560b887321464eba"
        or SOURCE_ARTIFACTS[1].artifact_hash != ingress.EXPECTED_ARTIFACT_SHA256
        or SOURCE_ARTIFACTS[0].artifact_hash != source.EXPECTED_ARTIFACT_SHA256
    ):
        raise ValueError("Deep Strike complete source or dependency pin drifted.")
    if {SOURCE_ID, DEPENDENCY_ID}.intersection(catalog.source_ids) or any(
        a.artifact_name in {s.artifact_name for s in SOURCE_ARTIFACTS}
        for a in package.source_artifacts
    ):
        raise ValueError("Deep Strike current description was already applied.")
    for owner, ability in occurrences:
        if owner not in reviewed or descriptor_hash(ability) != reviewed[owner][0]:
            raise ValueError("Deep Strike reviewed descriptor input drifted.")
    return replace(
        package,
        army_catalog=replace(
            catalog,
            source_ids=tuple(sorted((*catalog.source_ids, SOURCE_ID, DEPENDENCY_ID))),
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(a, effect_description=rule.source_text)
                        if a.ability_id == ABILITY_ID
                        else a
                        for a in row.abilities
                    ),
                )
                for row in catalog.datasheets
            ),
        ),
        source_artifacts=(*package.source_artifacts, *SOURCE_ARTIFACTS),
    )
