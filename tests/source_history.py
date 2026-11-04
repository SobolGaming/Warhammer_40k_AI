"""Fixed full catalog roots for finite historical proofs, never current admission."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from functools import cache
from pathlib import Path
from typing import Any, cast

from tests.core_description_helpers import (
    before_core_description_correction,
    before_lhykhis_correction,
    before_mandiblasters_correction,
)
from tests.daemons_final_four_preservation import before_daemons_final_four
from tests.daemons_native_source_preservation import before_daemons_native
from tests.daemons_next_three_preservation import before_daemons_next_three
from tests.icon_provenance_helpers import before_icon_catalog, before_icon_component
from tests.starfang_deep_strike_helpers import before_starfang_deep_strike
from tests.wave_serpent_frame_helpers import before_wave_frame
from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "tests/fixtures/source_history/post_icon_2026_11"
MANIFEST_SHA256 = "e2419f6728ee7df32910d3a8288f0d0ac26cd8a3c1ee5b6d8d606296c0715ed8"
MEMBERS = ("native.json", "paired.json", "standalone.json", "icon-component.json")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError("Historical source roots: " + message)


def _contained(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    _require(path.is_relative_to(root.resolve()), "member escapes its root")
    return path


def read_manifest(directory: Path = HISTORY) -> dict[str, Any]:
    raw = _contained(directory, "manifest.json").read_bytes()
    _require(hashlib.sha256(raw).hexdigest() == MANIFEST_SHA256, "manifest raw digest changed")
    manifest = cast(dict[str, Any], json.loads(raw))
    _require(manifest["schema"] == "source-history-roots-v1", "unsupported manifest schema")
    _require(set(manifest["members"]) == set(MEMBERS), "manifest member inventory changed")
    _require(
        {str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file()}
        == {*MEMBERS, "manifest.json"},
        "exact member inventory changed",
    )
    for name, expected in manifest["members"].items():
        raw = _contained(directory, name).read_bytes()
        _require(
            hashlib.sha256(raw).hexdigest() == expected["raw_sha256"], name + " raw digest changed"
        )
        payload = json.loads(raw)
        _require(
            _digest(payload) == expected["canonical_sha256"], name + " canonical digest changed"
        )
        _require(len(raw) == expected["bytes"], name + " byte count changed")
    for name, expected in manifest["audit_links"].items():
        _require(
            hashlib.sha256(_contained(ROOT, name).read_bytes()).hexdigest() == expected,
            "original audit changed: " + name,
        )
    return manifest


def _package(directory: Path, name: str, manifest: dict[str, Any]) -> CanonicalCatalogPackage:
    package = CanonicalCatalogPackage.from_payload(
        cast(CanonicalCatalogPackagePayload, json.loads(_contained(directory, name).read_bytes()))
    )
    expected = manifest["members"][name]
    _require(package.package_hash() == expected["package_hash"], name + " package identity changed")
    _require(package.army_catalog.catalog_id == expected["owner"], name + " owner changed")
    return package


@cache
def historical_packages() -> tuple[CanonicalCatalogPackage, ...]:
    manifest = read_manifest()
    return tuple(_package(HISTORY, name, manifest) for name in MEMBERS[:3])


def historical_icon_component() -> dict[str, Any]:
    read_manifest()
    return cast(dict[str, Any], json.loads((HISTORY / "icon-component.json").read_bytes()))


def before_historical_deadly_demise(package: CanonicalCatalogPackage) -> CanonicalCatalogPackage:
    from tools.core_deadly_demise_catalog_overlay import SOURCE_ARTIFACT, SOURCE_ID

    from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
        chaos_daemons_roster_2026_07 as daemons,
    )

    audit = json.loads(
        (
            ROOT / "data/source_audits/deadly_demise_2026_11/catalog-description-delta.json"
        ).read_bytes()
    )
    return replace(
        package,
        army_catalog=replace(
            package.army_catalog,
            datasheets=tuple(
                replace(
                    row,
                    abilities=tuple(
                        replace(a, effect_description=audit["historical_text"])
                        if a.ability_id == "000008339"
                        else a
                        for a in row.abilities
                    ),
                )
                for row in package.army_catalog.datasheets
            ),
            source_ids=tuple(s for s in package.army_catalog.source_ids if s != SOURCE_ID),
        ),
        source_artifacts=tuple(
            a
            for a in package.source_artifacts
            if a.artifact_name
            not in {SOURCE_ARTIFACT.artifact_name, daemons.CURRENT_SOURCE_ARTIFACT[0]}
        ),
    )


def validate_source_history(directory: Path = HISTORY) -> None:
    """Validate fixed closure and current approved Sticky, without a native build."""
    if sys.flags.optimize:
        raise ValueError(
            "Historical source roots require assertions; optimized Python is unsupported."
        )
    manifest = read_manifest(directory)
    stages = (
        before_icon_catalog,
        before_daemons_final_four,
        before_daemons_next_three,
        before_daemons_native,
        before_wave_frame,
        before_starfang_deep_strike,
        before_lhykhis_correction,
        before_mandiblasters_correction,
        before_core_description_correction,
    )
    observed: list[dict[str, str]] = []
    for name in MEMBERS[:3]:
        package = _package(directory, name, manifest)
        for stage in stages:
            previous = stage(package)
            observed.append(
                {"member": name, "stage": stage.__name__, "package_hash": previous.package_hash()}
            )
        previous = before_historical_deadly_demise(before_core_description_correction(package))
        observed.append(
            {
                "member": name,
                "stage": "before_deadly_demise",
                "package_hash": previous.package_hash(),
            }
        )
    component = json.loads(_contained(directory, "icon-component.json").read_bytes())
    expected = manifest["members"]["icon-component.json"]
    _require(component["source_package_id"] == expected["owner"], "component owner changed")
    _require(component["artifact_schema"] == expected["schema"], "component schema changed")
    previous_component = before_icon_component(component)
    observed.append(
        {
            "member": "icon-component.json",
            "stage": "before_icon_component",
            "canonical_sha256": _digest(previous_component),
            "package_hash": previous_component["package_hash"],
        }
    )
    _require(observed == manifest["closure"], "complete historical closure changed")
    from tests.support.section08_native_mission_source import PATH, validate_observation

    validate_observation((ROOT / PATH).read_bytes())
