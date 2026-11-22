"""Versioned source catalog for native Monster Mash and the retained Cavalcade roster."""

import json
from functools import cache
from hashlib import sha256
from typing import Final, cast

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

CATALOG_ID: Final = "core-v2:chaos-daemons-monster-mash:2026-11-v995"
PACKAGE_ID: Final = "data-package:core-v2:chaos-daemons-monster-mash:2026-11-v995"
CATALOG_SHA256: Final = "a990509b4ec88a69909aa673c12a40b54322d67730484539f5d22f1e27f0ae64"


class MonsterMashCatalogError(ValueError):
    """The mixed-roster catalog or its reviewed evidence has drifted."""


@cache
def catalog_package() -> CanonicalCatalogPackage:
    raw = package_artifact_bytes(__name__, "artifacts/catalog.json")
    if sha256(raw).hexdigest() != CATALOG_SHA256:
        raise MonsterMashCatalogError("Monster Mash v995 catalog bytes drifted.")
    package = CanonicalCatalogPackage.from_payload(
        cast(CanonicalCatalogPackagePayload, json.loads(raw))
    )
    if (
        package.package_id.stable_identity() != PACKAGE_ID
        or package.army_catalog.catalog_id != CATALOG_ID
    ):
        raise MonsterMashCatalogError("Monster Mash v995 catalog identity drifted.")
    if any(row.blocking for row in package.diagnostics):
        raise MonsterMashCatalogError("Monster Mash v995 has blocking source diagnostics.")
    sources = {
        artifact.artifact_name: artifact.artifact_hash for artifact in package.source_artifacts
    }
    for name in ("source-review.json", "geometry.json"):
        raw_source = package_artifact_bytes(__name__, f"artifacts/{name}")
        if sources.get(f"monster-mash-{name}") != sha256(raw_source).hexdigest():
            raise MonsterMashCatalogError(f"Monster Mash v995 {name} evidence drifted.")
    return package
