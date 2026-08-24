from __future__ import annotations

import json
from functools import cache
from typing import Final, cast

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

ARTIFACT_PATH: Final = "artifacts/catalog.json"
EXPECTED_PACKAGE_ID: Final = "data-package:core-v2:court-of-slaughter-anvanth:2026-08"
EXPECTED_CATALOG_ID: Final = "core-v2:court-of-slaughter-anvanth:2026-08"
EXPECTED_PACKAGE_HASH: Final = "9a4ee814aad8d908b47d605965e8bf29e7e443bba8246362a45f63059d41fa47"
EXPECTED_BRIDGE_SOURCE_PREFIX: Final = (
    "data-package:core-v2:court-of-slaughter-anvanth-bridge:2026-08:"
)
EXPECTED_REVIEWED_SOURCE_PREFIX: Final = (
    "data-package:core-v2:court-of-slaughter-anvanth-current-source-review:2026-08:"
)
EXPECTED_DATASHEET_IDS: Final = (
    "000000592",
    "000000596",
    "000000598",
    "000000600",
    "000000601",
    "000000611",
    "000000612",
    "000000613",
    "000002531",
    "000002532",
    "000002533",
    "000002538",
    "000002759",
    "000003909",
    "000004077",
    "000004078",
    "000004079",
    "000004080",
    "000004081",
    "000004083",
    "000004084",
    "000004086",
    "000004088",
    "000004089",
    "000004091",
    "000004194",
)
EXPECTED_FACTION_IDS: Final = ("aeldari", "emperors-children")
EXPECTED_DETACHMENT_IDS: Final = (
    "corsair-coterie",
    "court-of-the-phoenician",
    "path-of-the-outcast",
    "spectacle-of-slaughter",
)
EXPECTED_ENHANCEMENT_IDS: Final = (
    "000010654002",
    "000010654003",
    "000010654004",
    "000010654005",
    "000010900002",
    "000010900003",
    "aeldari:path-of-the-outcast:assassins-eye-upgrade",
    "aeldari:path-of-the-outcast:camouflaged-snipers-upgrade",
    "archraider",
    "infamy",
    "voidstone",
    "webway-pathstone",
)


class CourtOfSlaughterAnvanthCatalogError(ValueError):
    """Raised when the committed paired-roster catalog is invalid or stale."""


@cache
def catalog_package() -> CanonicalCatalogPackage:
    try:
        raw = package_artifact_bytes(__name__, ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth catalog artifact could not be loaded."
        ) from exc
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth catalog artifact is not valid JSON."
        ) from exc
    if not isinstance(decoded, dict):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth catalog artifact must be a JSON object."
        )
    package = CanonicalCatalogPackage.from_payload(cast(CanonicalCatalogPackagePayload, decoded))
    validate_catalog_package(package)
    return package


def validate_catalog_package(package: CanonicalCatalogPackage) -> None:
    if type(package) is not CanonicalCatalogPackage:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Paired-roster validation requires CanonicalCatalogPackage."
        )
    if package.package_id.stable_identity() != EXPECTED_PACKAGE_ID:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth package identity drifted."
        )
    if EXPECTED_PACKAGE_HASH and package.package_hash() != EXPECTED_PACKAGE_HASH:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth package content hash drifted."
        )
    catalog = package.army_catalog
    if catalog.catalog_id != EXPECTED_CATALOG_ID:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth ArmyCatalog identity drifted."
        )
    if catalog.source_package_id != EXPECTED_PACKAGE_ID:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth ArmyCatalog source identity drifted."
        )
    if tuple(datasheet.datasheet_id for datasheet in catalog.datasheets) != (
        EXPECTED_DATASHEET_IDS
    ):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth datasheet closure drifted."
        )
    if tuple(faction.faction_id for faction in catalog.factions) != EXPECTED_FACTION_IDS:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth faction closure drifted."
        )
    if tuple(detachment.detachment_id for detachment in catalog.detachments) != (
        EXPECTED_DETACHMENT_IDS
    ):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth detachment closure drifted."
        )
    if tuple(enhancement.enhancement_id for enhancement in catalog.enhancements) != (
        EXPECTED_ENHANCEMENT_IDS
    ):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth Enhancement closure drifted."
        )
    expected_geometry_ids = tuple(
        sorted(
            model.model_profile_id
            for datasheet in catalog.datasheets
            for model in datasheet.model_profiles
        )
    )
    if tuple(record.model_profile_id for record in package.model_geometries) != (
        expected_geometry_ids
    ):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth reviewed geometry closure drifted."
        )
    if package.diagnostics:
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth catalog must not retain geometry diagnostics."
        )
    required_source_ids = {
        "gw-11e-faction-detachments-2026-27",
        "gw-11e-phase17e-exact-faction-subrules-2026-27",
        "gw-11e-mfm-2026-07",
    }
    if not required_source_ids.issubset(catalog.source_ids):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth source-package provenance is incomplete."
        )
    required_source_prefixes = (
        EXPECTED_BRIDGE_SOURCE_PREFIX,
        EXPECTED_REVIEWED_SOURCE_PREFIX,
    )
    if any(
        not any(source_id.startswith(prefix) for source_id in catalog.source_ids)
        for prefix in required_source_prefixes
    ):
        raise CourtOfSlaughterAnvanthCatalogError(
            "Court of Slaughter/Anvanth current source identity closure is incomplete."
        )


__all__ = (
    "ARTIFACT_PATH",
    "EXPECTED_BRIDGE_SOURCE_PREFIX",
    "EXPECTED_CATALOG_ID",
    "EXPECTED_DATASHEET_IDS",
    "EXPECTED_DETACHMENT_IDS",
    "EXPECTED_ENHANCEMENT_IDS",
    "EXPECTED_FACTION_IDS",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_PACKAGE_ID",
    "EXPECTED_REVIEWED_SOURCE_PREFIX",
    "CourtOfSlaughterAnvanthCatalogError",
    "catalog_package",
    "validate_catalog_package",
)
