"""Reconcile only the reviewed current Core 24.08 catalog descriptions."""

from dataclasses import replace
from hashlib import sha256
from typing import Final

from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_abilities_2026_09

ABILITY_ID: Final = "000008339"
SOURCE_ID: Final = "gw-11e-core-abilities:core:deadly-demise"
SOURCE_ARTIFACT: Final = SourceArtifactHash(
    artifact_name="core-abilities-2026-09.json",
    artifact_hash="c45ac9d1ea006d32f8fc803940f51f971e934acbd6f09c51ef263c64b7f69c7b",
)
CURRENT_TEXT_SHA256: Final = "a5ca19362fe04090968372fe83f3398cfa1236d52d69a2a87ad6ca555f429ff4"
HISTORICAL_TEXT_SHA256: Final = "77abd1f1b24c3a5190d0232154a41a1f0116c355fc748714fbdc5ed94717e0d0"
REVIEWED_PARAMETERS: Final = {
    "000000599": "D3",
    "000000605": "1",
    "000000611": "D3",
    "000000613": "1",
    "000000968": "D3",
    "000000969": "D6",
    "000001029": "D3",
    "000001030": "D6",
    "000001120": "D6",
    "000001148": "D6",
    "000001149": "D3",
    "000001151": "D3",
    "000002582": "D6",
    "000002639": "D3",
    "000002758": "D3",
    "000004077": "D6",
    "000004086": "D3",
    "000004091": "D3",
    "000004195": "1",
    "000004207": "D6",
    "000004208": "D6",
    "000004209": "D6",
}
_BRIDGE_PREFIXES: Final = {
    "data-package:core-v2:chaos-daemons-bridge-catalog:phase17k-generated": (
        "data-package:core-v2:wahapedia-10e-bridge:phase17k-generated:Datasheets_abilities:"
    ),
    "data-package:core-v2:chaos-daemons-roster:2026-07": (
        "data-package:core-v2:chaos-daemons-roster-bridge:2026-07:Datasheets_abilities:"
    ),
}


def with_current_deadly_demise(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Replace the entire stale paragraph/example, preserving structured occurrences."""
    catalog = package.army_catalog
    expected = {
        row.datasheet_id for row in catalog.datasheets if row.datasheet_id in REVIEWED_PARAMETERS
    }
    occurrences = tuple(
        (row.datasheet_id, ability)
        for row in catalog.datasheets
        for ability in row.abilities
        if ability.ability_id == ABILITY_ID
    )
    if not expected and not occurrences:
        return package
    if len(occurrences) != len(expected) or {owner for owner, _ in occurrences} != expected:
        raise ValueError("Deadly Demise reviewed occurrence closure drifted.")
    package_id = package.package_id.stable_identity()
    if package_id not in _BRIDGE_PREFIXES:
        raise ValueError("Deadly Demise current catalog owner is unreviewed.")
    prefix = _BRIDGE_PREFIXES[package_id]
    rule = core_abilities_2026_09.source_rule_record()
    if (
        SOURCE_ARTIFACT.artifact_hash != core_abilities_2026_09.EXPECTED_ARTIFACT_SHA256
        or rule.source_id != SOURCE_ID
        or sha256(rule.source_text.encode()).hexdigest() != CURRENT_TEXT_SHA256
    ):
        raise ValueError("Deadly Demise current Core source pin drifted.")
    if SOURCE_ID in catalog.source_ids or any(
        row.artifact_name == SOURCE_ARTIFACT.artifact_name for row in package.source_artifacts
    ):
        raise ValueError("Deadly Demise current description was already applied.")
    for owner, ability in occurrences:
        if (
            ability.source_id != f"{prefix}{owner}:1"
            or ability.source_kind is not CatalogAbilitySourceKind.CORE
            or ability.parameter_tokens != (REVIEWED_PARAMETERS[owner],)
            or sha256(ability.effect_description.encode()).hexdigest() != HISTORICAL_TEXT_SHA256
        ):
            raise ValueError("Deadly Demise reviewed descriptor input drifted.")
    return replace(
        package,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(ability, effect_description=rule.source_text)
                        if ability.ability_id == ABILITY_ID
                        else ability
                        for ability in row.abilities
                    ),
                )
                for row in catalog.datasheets
            ),
            source_ids=tuple(sorted((*catalog.source_ids, SOURCE_ID))),
        ),
        source_artifacts=(*package.source_artifacts, SOURCE_ARTIFACT),
    )
