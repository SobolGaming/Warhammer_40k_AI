"""Versioned v995 roster catalog; the authenticated July catalog remains unchanged."""

import json
from functools import cache
from hashlib import sha256
from typing import Final, cast

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

CATALOG_ID: Final = "core-v2:chaos-daemons-cavalcade:2026-11-v995"
PACKAGE_ID: Final = "data-package:core-v2:chaos-daemons-cavalcade:2026-11-v995"
CATALOG_SHA256: Final = "d174bea9f2adb2a0d9b319fa3cfe0a0f43ef2157161df78b59ec90e3fc5bc8b2"
DATASHEET_IDS: Final = (
    "000001115",
    "000001120",
    "000001132",
    "000001133",
    "000001145",
    "000001148",
    "000002582",
)
GEOMETRY_PROFILE_IDS: Final = (
    "000001115:bloodcrushers",
    "000001115:bloodhunter",
    "000001120:lord-of-change",
    "000001132:plaguebearers",
    "000001132:plagueridden",
    "000001133:nurgling-swarms",
    "000001145:heartseeker",
    "000001145:seekers",
    "000001148:belakor-epic-hero",
    "000002582:bloodthirster",
)


class CavalcadeCatalogError(ValueError):
    """The versioned roster catalog or its source evidence has drifted."""


@cache
def catalog_package() -> CanonicalCatalogPackage:
    raw = package_artifact_bytes(__name__, "artifacts/catalog.json")
    if sha256(raw).hexdigest() != CATALOG_SHA256:
        raise CavalcadeCatalogError("Cavalcade v995 catalog bytes drifted.")
    payload = cast(CanonicalCatalogPackagePayload, json.loads(raw))
    package = CanonicalCatalogPackage.from_payload(payload)
    if package.package_id.stable_identity() != PACKAGE_ID:
        raise CavalcadeCatalogError("Cavalcade v995 package identity drifted.")
    catalog = package.army_catalog
    if catalog.catalog_id != CATALOG_ID:
        raise CavalcadeCatalogError("Cavalcade v995 catalog identity drifted.")
    if tuple(d.datasheet_id for d in catalog.datasheets) != DATASHEET_IDS:
        raise CavalcadeCatalogError("Cavalcade v995 datasheet closure drifted.")
    if tuple(g.model_profile_id for g in package.model_geometries) != GEOMETRY_PROFILE_IDS:
        raise CavalcadeCatalogError("Cavalcade v995 geometry closure drifted.")
    if any(d.blocking for d in package.diagnostics):
        raise CavalcadeCatalogError("Cavalcade v995 has blocking geometry diagnostics.")
    sources = {a.artifact_name: a.artifact_hash for a in package.source_artifacts}
    for name in ("source-review.json", "geometry.json"):
        observed = sha256(package_artifact_bytes(__name__, f"artifacts/{name}")).hexdigest()
        if sources.get(name) != observed:
            raise CavalcadeCatalogError("Cavalcade v995 source evidence drifted.")
    return package
