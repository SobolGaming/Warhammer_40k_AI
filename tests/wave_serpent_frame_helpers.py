"""Exact bounded FRAME successor projections; historical pins remain unchanged."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.source_catalog import SourceArtifactHash


@cache
def frame_audit(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(
            Path("data/source_audits/wave_serpent_frame_2026_11", name + ".json").read_bytes()
        ),
    )


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def before_wave_frame(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    audit = frame_audit("catalog-delta")
    if package.army_catalog.catalog_id != "chaos-daemons-bridge-catalog":
        assert package.package_hash() in audit["unchanged_counterparts"].values()
        return package
    assert package.package_hash() == audit["current_package_hash"]
    wave = package.army_catalog.datasheet_by_id("000000599")
    assert _hash(wave.to_payload()) == audit["current_wave_sha256"]
    assert wave.keywords.keywords.count("FRAME") == 1
    prior = replace(
        wave,
        keywords=replace(
            wave.keywords, keywords=tuple(k for k in wave.keywords.keywords if k != "FRAME")
        ),
        source_ids=tuple(audit["prior_wave"]["source_ids"]),
    )
    assert prior.to_payload() == audit["prior_wave"]
    projected = replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(prior if d is wave else d for d in package.army_catalog.datasheets),
            source_ids=tuple(audit["prior_source_ids"]),
        ),
        source_artifacts=tuple(
            SourceArtifactHash(**row) for row in audit["prior_source_artifacts"]
        ),
    )
    assert projected.package_hash() == audit["prior_package_hash"]
    return projected


def before_wave_registry(value: dict[str, Any]) -> dict[str, Any]:
    audit = frame_audit("registry-delta")
    if _hash(value) == audit["prior_sha256"]:
        return value
    assert _hash(value) == audit["current_sha256"]
    prior = deepcopy(value)
    assert prior["scopes"][1]["audit_rows"].pop() == audit["audit_row"]
    assert prior["scopes"][1]["source_packages"].pop() == audit["source_package"]
    assert _hash(prior) == audit["prior_sha256"]
    return prior


def before_wave_provenance(raw: bytes) -> bytes:
    audit = frame_audit("provenance-delta")
    observed = sha256(raw).hexdigest()
    # Earlier callers authenticate their own older predecessor after this boundary.
    if b"WAVE_FRAME_OVERLAY" not in raw:
        return raw
    if observed != audit["current_sha256"]:
        raise ValueError("Exact registered edition provenance inputs changed.")
    block, entry = audit["block"].encode(), audit["entry"].encode()
    if raw.count(block) != 1 or raw.count(entry) != 1:
        raise ValueError("Exact registered edition provenance inputs changed.")
    prior = raw.replace(block, b"", 1).replace(entry, b"", 1)
    if sha256(prior).hexdigest() != audit["prior_sha256"]:
        raise ValueError("Exact registered edition provenance inputs changed.")
    return prior
