"""Current Chaos Daemons development catalog with the reviewed Gnarlmaw entry."""

import json
from functools import cache
from hashlib import sha256
from typing import Final, cast

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

DATASHEET_ID: Final = "000001470"
PROFILE_ID: Final = f"{DATASHEET_ID}:feculent-gnarlmaw"
CATALOG_ID: Final = "core-v2:chaos-daemons-gnarlmaw:2026-11"
PACKAGE_ID: Final = f"data-package:{CATALOG_ID}"
CATALOG_SHA256: Final = "15864f07cf2a3a0d179cf43f74f5b4b8a712748c388566d1f70b0cffc25e329a"


@cache
def catalog_package() -> CanonicalCatalogPackage:
    raw = package_artifact_bytes(__name__, "artifacts/catalog.json")
    if sha256(raw).hexdigest() != CATALOG_SHA256:
        raise ValueError("Gnarlmaw development catalog bytes drifted.")
    package = CanonicalCatalogPackage.from_payload(
        cast(CanonicalCatalogPackagePayload, json.loads(raw))
    )
    if (
        package.package_id.stable_identity() != PACKAGE_ID
        or package.army_catalog.catalog_id != CATALOG_ID
        or any(row.blocking for row in package.diagnostics)
    ):
        raise ValueError("Gnarlmaw development catalog identity or support drifted.")
    return package
