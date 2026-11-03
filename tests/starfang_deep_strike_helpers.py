"""Exact authenticated successor for retained source-description preservation checks."""

from __future__ import annotations

import json
from dataclasses import replace
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.core_deep_strike_successor import (
    before_deep_strike_catalog,
)
from warhammer40k_core.rules.source_catalog import SourceArtifactHash


@cache
def correction_audit() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            Path("data/source_audits/starfang_deep_strike_2026_11/catalog-delta.json").read_bytes()
        ),
    )


def before_starfang_deep_strike(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    surface = next(
        row
        for row in correction_audit()["surfaces"]
        if row["catalog_id"] == package.army_catalog.catalog_id
    )
    assert package.army_catalog.source_ids == tuple(surface["current_source_ids"])
    assert package.source_artifacts == tuple(
        SourceArtifactHash(**row) for row in surface["current_source_artifacts"]
    )
    catalog = before_deep_strike_catalog(package.army_catalog)
    old = surface["starfang_prior"]
    if old is not None:
        row = catalog.datasheet_by_id("000004195")
        assert (
            sha256(
                json.dumps(row.to_payload(), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            == surface["starfang_current_sha256"]
        )
        keyword = replace(row.keywords, keywords=tuple(old["keywords"]["keywords"]))
        previous = replace(row, keywords=keyword, source_ids=tuple(old["source_ids"]))
        assert previous.to_payload() == old
        catalog = replace(
            catalog, datasheets=tuple(previous if d is row else d for d in catalog.datasheets)
        )
    projected = replace(
        package,
        army_catalog=replace(catalog, source_ids=tuple(surface["prior_source_ids"])),
        source_artifacts=tuple(
            SourceArtifactHash(**row) for row in surface["prior_source_artifacts"]
        ),
    )
    assert projected.package_hash() == surface["prior_package_hash"]
    return projected


def before_starfang_source_registry(value: dict[str, Any]) -> dict[str, Any]:
    """Authenticate exactly the two new admissions before retained registry controls."""
    from copy import deepcopy

    assert (
        sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        == "a08c9d198b7a944a7b2ac555bbf9f078f549a8ed8d77003d22dc9e839a454879"
    )
    prior = deepcopy(value)
    prior["scopes"][0]["audit_rows"].pop()
    prior["scopes"][0]["source_package_extensions"].pop()
    prior["scopes"][1]["audit_rows"].pop()
    prior["scopes"][1]["source_packages"].pop()
    assert (
        sha256(json.dumps(prior, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        == "33b7c2ba02d3854d7b3c1181438f76d0e7faab6b5d19d5b4c84da07d30e7dd15"
    )
    return prior
