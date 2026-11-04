"""Pinned test-only inverse for historical controls predating the Icon owner repair."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from functools import cache
from pathlib import Path
from typing import Any, cast

from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@cache
def icon_successor_audit() -> dict[str, Any]:
    raw = Path("data/source_audits/later_ir_icon_2026_11/provenance-successor.json").read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "e15437f43367d05e48bce8ebafb5379155033df4c5af9bb4ca50d2fb4023197e"
    )
    return cast(dict[str, Any], json.loads(raw))


def _inverse(payload: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    prior = deepcopy(payload)
    for change in record["inverse"]:
        cursor: Any = prior
        path: list[str | int] = change["path"]
        for key in path[:-1]:
            cursor = cursor[key]
        assert cursor[path[-1]] == change["current"]
        cursor[path[-1]] = change["prior"]
    return prior


def before_icon_catalog(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    """Authenticate the complete catalog, then reverse only the pinned six scalar deltas."""
    audit = icon_successor_audit()
    if package.army_catalog.catalog_id == audit["unchanged_catalog"]["catalog_id"]:
        assert package.package_hash() == audit["unchanged_catalog"]["hash"]
        return package
    (surface,) = tuple(
        row
        for row in audit["catalog_surfaces"]
        if row["catalog_id"] == package.army_catalog.catalog_id
    )
    if package.package_hash() == surface["prior_hash"]:
        return package
    assert package.package_hash() == surface["current_hash"]
    previous = CanonicalCatalogPackage.from_payload(
        cast(
            CanonicalCatalogPackagePayload,
            _inverse(cast(dict[str, Any], package.to_payload()), surface),
        )
    )
    assert previous.package_hash() == surface["prior_hash"]
    return previous


def before_icon_component(payload: dict[str, Any]) -> dict[str, Any]:
    """Verify the complete current component and exact unchanged Sticky record."""
    row = icon_successor_audit()["ir_component"]
    assert _digest(payload) == row["current_hash"]
    assert payload["package_hash"] == row["current_package_hash"]
    assert _digest(payload["records"]["000004079:3"]) == row["unchanged_sticky_record_sha256"]
    previous = _inverse(payload, row)
    assert _digest(previous) == row["prior_hash"]
    assert previous["package_hash"] == row["prior_package_hash"]
    assert previous["records"]["000004079:3"] == payload["records"]["000004079:3"]
    return previous
