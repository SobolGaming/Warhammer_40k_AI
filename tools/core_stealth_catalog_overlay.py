"""Apply the reviewed Core 24.33 wording to current 11th Edition catalog output."""

from dataclasses import replace

from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_stealth_2026_09


def with_current_stealth(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    (rule,) = core_stealth_2026_09.source_rules()
    catalog = package.army_catalog
    return replace(
        package,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    datasheet,
                    abilities=tuple(
                        replace(ability, effect_description=rule.source_text)
                        if ability.ability_id in {"000008337", "core-stealth", "stealth"}
                        else ability
                        for ability in datasheet.abilities
                    ),
                )
                for datasheet in catalog.datasheets
            ),
            source_ids=tuple(sorted({*catalog.source_ids, rule.source_id})),
        ),
        source_artifacts=(
            *package.source_artifacts,
            SourceArtifactHash(
                artifact_name="core-stealth-2026-09.json",
                artifact_hash=core_stealth_2026_09.EXPECTED_ARTIFACT_SHA256,
            ),
        ),
    )
