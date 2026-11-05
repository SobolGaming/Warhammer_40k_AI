"""Build a current roster catalog without rewriting the authenticated July package."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

from tools import generate_chaos_daemons_roster_catalog as historical_generator
from tools.core_deep_strike_catalog_overlay import SOURCE_ARTIFACTS as DEEP_STRIKE_ARTIFACTS
from warhammer40k_core.core.datasheet import CatalogAbilitySourceKind
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryReviewStatus,
    GeometrySourceUnits,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_report
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_cavalcade_2026_11 as current,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as historical,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_deep_strike_description_2026_11,
    core_descriptions_2026_11,
    mfm_2026_10,
)
from warhammer40k_core.rules.wahapedia_bridge import build_wahapedia_canonical_bridge_artifacts
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    CHAOS_DAEMONS_BELAKOR_HEIGHT_OVERRIDES,
    CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES,
    ModelHeightOverride,
    PdfDatasheetCorrection,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    NormalizedSourceRowPayload,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = (
    ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "chaos_daemons_cavalcade_2026_11/artifacts"
)
VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-cavalcade-v995", source_date=date(2026, 11, 5)
)
PACKAGE = DataPackageId(
    namespace="core-v2", package_name="chaos-daemons-cavalcade", version="2026-11-v995"
)
REVIEWED = DataPackageId(
    namespace="core-v2", package_name="cavalcade-reviewed-datasheets", version="2026-11-v995"
)
ADDITIONAL_IDS = ("000001133", "000001145")


def build_catalog_package() -> CanonicalCatalogPackage:
    old = historical.catalog_package()
    review = json.loads((ARTIFACTS / "source-review.json").read_bytes())
    geometry = json.loads((ARTIFACTS / "geometry.json").read_bytes())
    pdf_bytes = (ROOT / review["official_pdf"]).read_bytes()
    if hashlib.sha256(pdf_bytes).hexdigest() != historical.OFFICIAL_PDF_SHA256:
        raise ValueError("Cavalcade official PDF bytes drifted.")
    if review["official_pdf_sha256"] != historical.OFFICIAL_PDF_SHA256:
        raise ValueError("Cavalcade official PDF review identity drifted.")
    heights = (
        *CHAOS_DAEMONS_BELAKOR_HEIGHT_OVERRIDES,
        *CHAOS_DAEMONS_BLOODCRUSHERS_HEIGHT_OVERRIDES,
        *(
            ModelHeightOverride(
                datasheet_id=r["datasheet_id"],
                model_name=r["model_name"],
                height=r["height_mm"],
                height_units=GeometrySourceUnits.MILLIMETERS,
                height_source_id=f"cavalcade-v995:geometry:{r['datasheet_id']}:{i}",
                height_document_reference=(ARTIFACTS / "geometry.json")
                .relative_to(ROOT)
                .as_posix(),
                reviewer_status=GeometryReviewStatus(r["reviewer_status"]),
                evidence_kind=GeometryEvidenceKind(r["evidence_kind"]),
            )
            for i, r in enumerate(geometry["heights"], 1)
        ),
    )
    old_sources, old_hashes = historical_generator._source_artifacts_and_provenance(  # pyright: ignore[reportPrivateUsage]
        reconciliation=historical.reconciliation_manifest()
    )
    old_bridge = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=old_sources,
        bridge_package_id=DataPackageId(
            namespace="core-v2", package_name="cavalcade-geometry", version="2026-11-v995"
        ),
        datasheet_ids=historical.EXPECTED_DATASHEET_IDS,
        pdf_corrections=historical_generator._official_pdf_keyword_corrections(  # pyright: ignore[reportPrivateUsage]
            historical.reconciliation_manifest()
        ),
        height_overrides=heights,
    )
    old_geometry = _catalog_from_bridge(old_bridge)
    added = _additional_catalog(review, heights)
    catalog = old.army_catalog
    datasheets = tuple(
        sorted((*catalog.datasheets, *added.army_catalog.datasheets), key=lambda d: d.datasheet_id)
    )
    faction = mfm_2026_10.faction_record("chaos-daemons")
    points_by_source_key = {
        (d.detachment_id, e.enhancement_id): e for d in faction.detachments for e in d.enhancements
    }
    enhancement_detachments = {
        e: d.detachment_id for d in catalog.detachments for e in d.enhancement_ids
    }
    enhancements = tuple(
        replace(
            e,
            points=points_by_source_key[
                (enhancement_detachments[e.enhancement_id], e.source_id.rsplit(":", 1)[1])
            ].points,
            source_id=points_by_source_key[
                (enhancement_detachments[e.enhancement_id], e.source_id.rsplit(":", 1)[1])
            ].source_id,
        )
        for e in catalog.enhancements
    )
    current_catalog = replace(
        catalog,
        catalog_id=current.CATALOG_ID,
        source_package_id=PACKAGE.stable_identity(),
        datasheets=datasheets,
        wargear=tuple(
            sorted((*catalog.wargear, *added.army_catalog.wargear), key=lambda w: w.wargear_id)
        ),
        enhancements=enhancements,
        detachments=tuple(
            replace(d, unit_datasheet_ids=current.DATASHEET_IDS) for d in catalog.detachments
        ),
        source_ids=tuple(
            sorted(
                {*catalog.source_ids, *added.army_catalog.source_ids, mfm_2026_10.SOURCE_PACKAGE_ID}
            )
        ),
    )
    provenance = {
        a.artifact_name: a for a in (*old.source_artifacts, *old_hashes, *added.source_artifacts)
    }
    for name in ("source-review.json", "geometry.json"):
        provenance[name] = SourceArtifactHash(
            artifact_name=name,
            artifact_hash=hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest(),
        )
    provenance["authenticated-july-catalog.json"] = SourceArtifactHash(
        artifact_name="authenticated-july-catalog.json", artifact_hash=old.package_hash()
    )
    package = CanonicalCatalogPackage(
        package_id=PACKAGE,
        catalog_version=VERSION,
        source_edition=old.source_edition,
        source_artifacts=tuple(provenance[k] for k in sorted(provenance)),
        army_catalog=current_catalog,
        model_geometries=tuple(
            sorted(
                (*old_geometry.model_geometries, *added.model_geometries),
                key=lambda g: g.model_profile_id,
            )
        ),
        diagnostics=(*old_geometry.diagnostics, *added.diagnostics),
    )
    if any(d.blocking for d in package.diagnostics):
        raise ValueError("Cavalcade geometry remains blocked.")
    return package


def _catalog_from_bridge(artifacts: tuple[WahapediaJsonArtifact, ...]) -> CanonicalCatalogPackage:
    report = build_canonical_catalog_report(
        package_id=PACKAGE, catalog_version=VERSION, source_artifacts=artifacts
    )
    if report.package is None:
        raise ValueError("Cavalcade source rows could not preserve physical model profiles.")
    return report.package


def _additional_catalog(
    review: dict[str, object], heights: tuple[ModelHeightOverride, ...]
) -> CanonicalCatalogPackage:
    originals = tuple(
        WahapediaJsonArtifact.from_payload(
            cast(
                WahapediaJsonArtifactPayload,
                json.loads((historical_generator.SOURCE_JSON_DIR / f"{table}.json").read_bytes()),
            )
        )
        for table in historical_generator.REQUIRED_TABLES
    )
    for artifact in originals:
        if (
            artifact.artifact_hash()
            != dict(historical.EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES)[artifact.source_table]
        ):
            raise ValueError("Cavalcade historical bridge input hash drifted.")
    reviews = cast(list[dict[str, object]], review["datasheets"])
    if tuple(r["datasheet_id"] for r in reviews) != ADDITIONAL_IDS:
        raise ValueError("Cavalcade additional PDF review closure drifted.")
    for row in reviews:
        digest = historical_generator._generator_input_datasheet_payload_hash(  # pyright: ignore[reportPrivateUsage]
            source_artifacts=originals, datasheet_id=cast(str, row["datasheet_id"])
        )
        if digest != row["input_payload_sha256"]:
            raise ValueError("Cavalcade reviewed generator input drifted.")
        if (
            hashlib.sha256(cast(str, row["official_text"]).encode()).hexdigest()
            != row["official_text_sha256"]
        ):
            raise ValueError("Cavalcade retained official text drifted.")
    linked = {
        r.runtime_fields_payload()["ability_id"]
        for a in originals
        if a.source_table == "Datasheets_abilities"
        for r in a.rows
        if r.runtime_fields_payload().get("datasheet_id") in ADDITIONAL_IDS
        and r.runtime_fields_payload().get("ability_id")
    }
    selected: list[WahapediaJsonArtifact] = []
    for artifact in originals:
        rows = []
        for r in artifact.rows:
            f = r.runtime_fields_payload()
            include = (
                f.get("datasheet_id") in ADDITIONAL_IDS
                or (artifact.source_table == "Datasheets" and f.get("id") in ADDITIONAL_IDS)
                or (artifact.source_table == "Factions" and f.get("id") == "CD")
                or (artifact.source_table == "Abilities" and f.get("id") in linked)
            )
            if not include or (
                artifact.source_table == "Datasheets_keywords"
                and f.get("keyword", "").upper() == "SHADOW LEGION"
            ):
                continue
            payload = _promote(r.to_payload(), artifact.source_package_id.stable_identity())
            rows.append(NormalizedSourceRow.from_payload(cast(NormalizedSourceRowPayload, payload)))
        selected.append(
            WahapediaJsonArtifact(
                source_package_id=REVIEWED,
                source_table=artifact.source_table,
                source_checksum_sha256=historical.OFFICIAL_PDF_SHA256,
                rows=tuple(rows),
            )
        )
    corrections = tuple(
        PdfDatasheetCorrection(
            datasheet_id=cast(str, r["datasheet_id"]),
            source_id=(
                f"{historical.EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID}:"
                f"datasheet:{r['datasheet_id']}:"
                f"pages-{cast(list[int], r['pages'])[0]}-{cast(list[int], r['pages'])[1]}"
            ),
            removed_keywords=("Shadow Legion",),
            source_package_version="2026-07",
        )
        for r in reviews
    )
    bridge = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=tuple(selected),
        bridge_package_id=REVIEWED,
        datasheet_ids=ADDITIONAL_IDS,
        pdf_corrections=corrections,
        height_overrides=heights,
    )
    return _current_additional_core_descriptions(_catalog_from_bridge(bridge))


def _current_additional_core_descriptions(
    package: CanonicalCatalogPackage,
) -> CanonicalCatalogPackage:
    """Reconcile the newly reviewed owners; preserve the existing overlay's closed scope."""
    descriptions = {r.source_id: r.source_text for r in core_descriptions_2026_11.source_rules()}
    deep_strike = core_deep_strike_description_2026_11.source_rules()[0]
    descriptions[deep_strike.source_id] = deep_strike.source_text
    sources = {
        "000008343": deep_strike.source_id,
        "000008344": "gw-11e-core-abilities:core:scouts",
        "000008345": "gw-11e-core-abilities:core:infiltrators",
    }
    expected = {
        ("000001133", "000008343"),
        ("000001133", "000008345"),
        ("000001145", "000008343"),
        ("000001145", "000008344"),
    }
    observed = {
        (d.datasheet_id, a.ability_id)
        for d in package.army_catalog.datasheets
        for a in d.abilities
        if a.source_kind is CatalogAbilitySourceKind.CORE
    }
    if observed != expected:
        raise ValueError("Cavalcade additional Core description closure drifted.")
    catalog = package.army_catalog
    return replace(
        package,
        army_catalog=replace(
            catalog,
            datasheets=tuple(
                replace(
                    d,
                    abilities=tuple(
                        replace(a, effect_description=descriptions[sources[a.ability_id]])
                        if a.source_kind is CatalogAbilitySourceKind.CORE
                        else a
                        for a in d.abilities
                    ),
                )
                for d in catalog.datasheets
            ),
            source_ids=tuple(
                sorted(
                    {
                        *catalog.source_ids,
                        *sources.values(),
                        core_descriptions_2026_11.SCOUT_MOVE_SOURCE_ID,
                    }
                )
            ),
        ),
        source_artifacts=(
            *package.source_artifacts,
            *DEEP_STRIKE_ARTIFACTS,
            SourceArtifactHash(
                "core-descriptions-2026-11.json", core_descriptions_2026_11.EXPECTED_ARTIFACT_SHA256
            ),
        ),
    )


def _promote(value: object, old_identity: str) -> object:
    if isinstance(value, str):
        return value.replace(old_identity, REVIEWED.stable_identity())
    if isinstance(value, list):
        return [_promote(v, old_identity) for v in value]
    if isinstance(value, dict):
        result = {k: _promote(v, old_identity) for k, v in value.items()}
        if "source_package_id" in result:
            result["source_package_id"] = REVIEWED.to_payload()
        return result
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generated = build_catalog_package().to_json_bytes()
    path = ARTIFACTS / "catalog.json"
    if args.check:
        if path.read_bytes() != generated:
            raise SystemExit("Cavalcade v995 catalog is stale.")
    else:
        path.write_bytes(generated)


if __name__ == "__main__":
    main()
