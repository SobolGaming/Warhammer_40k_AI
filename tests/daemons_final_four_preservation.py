"""Exact selected Daemons successor projections for retained historical controls."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from tests.icon_provenance_helpers import before_icon_catalog
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash


@cache
def daemons_audit(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            Path("data/source_audits/daemons_final_four_2026_11", name + ".json").read_bytes()
        ),
    )


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def before_daemons_final_four(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    audit = daemons_audit("catalog-delta")
    if package.package_hash() == audit["prior_package_hash"]:
        return package
    package = before_icon_catalog(package)
    if package.army_catalog.catalog_id != "chaos-daemons-bridge-catalog":
        assert package.package_hash() in audit["unchanged_counterparts"].values()
        return package
    if package.package_hash() == audit["prior_package_hash"]:
        return package
    assert package.package_hash() == audit["current_package_hash"]
    previous: dict[str, DatasheetDefinition] = {}
    for record in audit["rows"]:
        row = package.army_catalog.datasheet_by_id(record["datasheet_id"])
        assert _hash(row.to_payload()) == record["current_sha256"]
        assert "SHADOW LEGION" not in row.keywords.keywords
        prior = replace(
            row,
            keywords=replace(
                row.keywords, keywords=tuple(sorted((*row.keywords.keywords, "SHADOW LEGION")))
            ),
            source_ids=tuple(record["prior"]["source_ids"]),
        )
        assert prior.to_payload() == record["prior"]
        previous[row.datasheet_id] = prior
    projected = replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(
                previous.get(row.datasheet_id, row) for row in package.army_catalog.datasheets
            ),
            source_ids=tuple(audit["prior_source_ids"]),
        ),
        source_artifacts=tuple(
            SourceArtifactHash(**row) for row in audit["prior_source_artifacts"]
        ),
    )
    assert projected.package_hash() == audit["prior_package_hash"]
    return projected


def before_final_four_registry(value: dict[str, Any]) -> dict[str, Any]:
    audit = daemons_audit("registry-delta")
    if _hash(value) == audit["prior_sha256"]:
        return value
    assert _hash(value) == audit["current_sha256"]
    prior = deepcopy(value)
    assert prior["scopes"][1]["audit_rows"][-4:] == audit["audit_rows"]
    del prior["scopes"][1]["audit_rows"][-4:]
    assert prior["scopes"][1]["source_packages"].pop() == audit["source_package"]
    assert _hash(prior) == audit["prior_sha256"]
    return prior
