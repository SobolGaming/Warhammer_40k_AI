"""Exact selected Daemons successor projections for retained historical controls."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash


@cache
def daemons_audit(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(Path("data/source_audits/daemons_native_2026_11", name + ".json").read_bytes()),
    )


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def before_daemons_native(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    from tests.daemons_next_three_preservation import before_daemons_next_three

    package = before_daemons_next_three(package)
    audit = daemons_audit("catalog-delta")
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
        effects = row.damaged_effects
        if row.datasheet_id == "000001148":
            assert len(effects) == 1
            assert effects[0].wounds_max == 7
            effects = (replace(effects[0], wounds_max=6),)
        prior = replace(
            row,
            keywords=replace(
                row.keywords, keywords=tuple(sorted((*row.keywords.keywords, "SHADOW LEGION")))
            ),
            damaged_effects=effects,
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


def before_daemons_registry(value: dict[str, Any]) -> dict[str, Any]:
    from tests.daemons_next_three_preservation import before_next_three_registry

    value = before_next_three_registry(value)
    audit = daemons_audit("registry-delta")
    if _hash(value) == audit["prior_sha256"]:
        return value
    assert _hash(value) == audit["current_sha256"]
    prior = deepcopy(value)
    assert prior["scopes"][1]["audit_rows"][-2:] == audit["audit_rows"]
    del prior["scopes"][1]["audit_rows"][-2:]
    assert prior["scopes"][1]["source_packages"].pop() == audit["source_package"]
    assert _hash(prior) == audit["prior_sha256"]
    return prior


def before_pr2_comparison_provenance(raw: bytes) -> bytes:
    """Authenticate only the additive PR2 comparison registration before older proofs."""
    addition = (
        b"COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE, scopes.DEFILER_BASE, scopes.PR2_BASE)"
    )
    predecessor = b"COMPARISON_ONLY_SCOPE_BASES = (scopes.ACTS_BASE, scopes.DEFILER_BASE)"
    if b"scopes.PR2_BASE" not in raw:
        return raw
    error = "Exact registered edition provenance inputs changed."
    if (
        sha256(raw).hexdigest()
        != "84ee00289dbffa00eafcd889a9e047c541077e46970a1f6a933d6f3da3a77668"
        or raw.count(addition) != 1
    ):
        raise ValueError(error)
    prior = raw.replace(addition, predecessor, 1)
    if (
        sha256(prior).hexdigest()
        != "95244250ad88ac287f6bcef1c89eea29fe4f70318d9383e9a92b7c103240670d"
    ):
        raise ValueError(error)
    return prior


def before_daemons_provenance(raw: bytes) -> bytes:
    raw = before_pr2_comparison_provenance(raw)
    if b"DAEMONS_NATIVE_OVERLAY" not in raw:
        return raw
    audit = daemons_audit("provenance-delta")
    if sha256(raw).hexdigest() != audit["current_sha256"]:
        raise ValueError("Exact registered edition provenance inputs changed.")
    block, entry = audit["block"].encode(), audit["entry"].encode()
    if raw.count(block) != 1 or raw.count(entry) != 1:
        raise ValueError("Exact registered edition provenance inputs changed.")
    prior = raw.replace(block, b"", 1).replace(entry, b"", 1)
    if sha256(prior).hexdigest() != audit["prior_sha256"]:
        raise ValueError("Exact registered edition provenance inputs changed.")
    return prior
