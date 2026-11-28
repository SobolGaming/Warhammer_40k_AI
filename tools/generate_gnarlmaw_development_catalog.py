"""Generate the Gnarlmaw development catalog from retained source and approved geometry."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

from tools import generate_chaos_daemons_roster_catalog as historical
from tools.generate_cavalcade_v995_catalog import _promote  # pyright: ignore[reportPrivateUsage]
from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryReviewStatus,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_report
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_gnarlmaw_2026_11 as gnarlmaw,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_monster_mash_2026_11 as predecessor,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_daemons_roster_2026_07 as reviewed,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import core_descriptions_2026_11
from warhammer40k_core.rules.wahapedia_bridge import build_wahapedia_canonical_bridge_artifacts
from warhammer40k_core.rules.wahapedia_bridge_defaults import (
    DEFAULT_HEIGHT_OVERRIDES,
    ModelHeightOverride,
)
from warhammer40k_core.rules.wahapedia_bridge_rows import SelectedSourceRows, bridge_rows_by_table
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    NormalizedSourceRowPayload,
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / (
    "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th/"
    "chaos_daemons_gnarlmaw_2026_11/artifacts/catalog.json"
)
GEOMETRY = ROOT / "data/source_audits/feculent_gnarlmaw_2026_11/geometry.json"
FACTION_PDF = ROOT / (
    "data/raw/faction_packs/"
    "eng_22-07_warhammer_40,000_faction_pack_chaos_daemons-lycqqrymwe-qogh4b5yly.pdf"
)
FACTION_SOURCE_ID = (
    f"{reviewed.EXPECTED_CURRENT_FACTION_SOURCE_PACKAGE_ID}:"
    f"datasheet:{gnarlmaw.DATASHEET_ID}:pages-86-87"
)
INFILTRATORS_SOURCE_ID = "gw-11e-core-abilities:core:infiltrators"
PACKAGE = DataPackageId(
    namespace="core-v2", package_name="chaos-daemons-gnarlmaw", version="2026-11"
)
BRIDGE_PACKAGE = DataPackageId(
    namespace="core-v2", package_name="chaos-daemons-gnarlmaw-bridge", version="2026-11"
)
REVIEWED_DATASHEET_SOURCE = DataPackageId(
    namespace="core-v2", package_name="chaos-daemons-gnarlmaw-reviewed-datasheet", version="2026-11"
)
RETAINED_DATASHEET_SHA256 = "e637f6662a425d0b32e1fad52f3de8a714b0202eac693059c1f0231b9a71724c"
BRIDGE_DATASHEETS = ("000001148", gnarlmaw.DATASHEET_ID)
VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-chaos-daemons-gnarlmaw", source_date=date(2026, 11, 27)
)


def _geometry() -> ModelGeometryCatalogRecord:
    record = json.loads(GEOMETRY.read_bytes())
    if (
        record["schema"] != "explicit-provisional-model-geometry-v1"
        or record["datasheet_id"] != gnarlmaw.DATASHEET_ID
        or record["model_profile_id"] != gnarlmaw.PROFILE_ID
        or record["source_base_designation"] != "Hull"
        or record["evidence_kind"] != "user_supplied_estimate"
        or record["reviewer_status"] != "provisional_estimate"
    ):
        raise ValueError("Gnarlmaw provisional geometry evidence identity drifted.")
    owner_source_id = f"owner-instruction:{record['owner_message']}"
    reference = GEOMETRY.relative_to(ROOT).as_posix()
    footprint = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{gnarlmaw.PROFILE_ID}:footprint",
        evidence_kind=GeometryEvidenceKind.USER_SUPPLIED_ESTIMATE,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id=owner_source_id,
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(
            ("length", record["footprint_length_mm"]),
            ("width", record["footprint_width_mm"]),
        ),
        document_reference=reference,
        reviewer_status=GeometryReviewStatus.PROVISIONAL_ESTIMATE,
    )
    height = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{gnarlmaw.PROFILE_ID}:height",
        evidence_kind=GeometryEvidenceKind.USER_SUPPLIED_ESTIMATE,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id=owner_source_id,
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", record["height_inches"]),),
        document_reference=reference,
        reviewer_status=GeometryReviewStatus.PROVISIONAL_ESTIMATE,
    )
    kind = ModelFootprintKind(record["footprint_kind"])
    return ModelGeometryCatalogRecord(
        model_geometry_id=gnarlmaw.PROFILE_ID,
        model_profile_id=gnarlmaw.PROFILE_ID,
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_HULL,
        footprint=ModelFootprintDefinition.single_part(
            footprint_id=f"{gnarlmaw.PROFILE_ID}:hull",
            footprint_kind=kind,
            part=ModelFootprintPartDefinition.from_evidence(
                part_id="hull", footprint_kind=kind, evidence=footprint
            ),
        ),
        support_base=None,
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height),
        evidence=(footprint, height),
        source_ids=(FACTION_SOURCE_ID, owner_source_id),
    )


def _reviewed_source_rows(artifacts: tuple[WahapediaJsonArtifact, ...]) -> SelectedSourceRows:
    retained_digest = historical._generator_input_datasheet_payload_hash(  # pyright: ignore[reportPrivateUsage]
        source_artifacts=artifacts, datasheet_id=gnarlmaw.DATASHEET_ID
    )
    if retained_digest != RETAINED_DATASHEET_SHA256:
        raise ValueError("Gnarlmaw reviewed generator rows drifted.")

    rows_by_table = bridge_rows_by_table(artifacts, error_type=ValueError)
    old_identity = historical.EXPECTED_GENERATOR_INPUT_PACKAGE_ID.stable_identity()
    tables: list[tuple[str, tuple[NormalizedSourceRow, ...]]] = []
    for table, rows in rows_by_table.items():
        reviewed_rows: list[NormalizedSourceRow] = []
        for row in rows:
            if row.source_row_id.partition(":")[0] != gnarlmaw.DATASHEET_ID:
                reviewed_rows.append(row)
                continue
            # The July pack omits this retired keyword. FRAME comes from the PDF correction.
            if (
                table == "Datasheets_keywords"
                and row.runtime_fields_payload()["keyword"] == "Shadow Legion"
            ):
                continue
            payload = _promote(row.to_payload(), old_identity, REVIEWED_DATASHEET_SOURCE)
            reviewed_rows.append(
                NormalizedSourceRow.from_payload(cast(NormalizedSourceRowPayload, payload))
            )
        tables.append((table, tuple(reviewed_rows)))
    return SelectedSourceRows(tuple(tables), BRIDGE_DATASHEETS)


def build_catalog_package() -> CanonicalCatalogPackage:
    base = predecessor.catalog_package()
    if hashlib.sha256(FACTION_PDF.read_bytes()).hexdigest() != reviewed.OFFICIAL_PDF_SHA256:
        raise ValueError("Gnarlmaw official faction pack source drifted.")
    artifacts = tuple(
        WahapediaJsonArtifact.from_payload(
            cast(
                WahapediaJsonArtifactPayload,
                json.loads((historical.SOURCE_JSON_DIR / f"{table}.json").read_bytes()),
            )
        )
        for table in historical.REQUIRED_TABLES
    )
    if {row.source_table: row.artifact_hash() for row in artifacts} != dict(
        reviewed.EXPECTED_GENERATOR_INPUT_ARTIFACT_HASHES
    ):
        raise ValueError("Gnarlmaw bridge source closure drifted.")
    geometry = _geometry()
    height = geometry.height
    (_, height_evidence) = geometry.evidence
    # Include existing Be'lakor in the bridge build because the canonical builder
    # requires a nonempty wargear table. Its existing catalog entry is retained.
    bridge = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=_reviewed_source_rows(artifacts),
        bridge_package_id=BRIDGE_PACKAGE,
        datasheet_ids=BRIDGE_DATASHEETS,
        height_overrides=(
            *DEFAULT_HEIGHT_OVERRIDES,
            ModelHeightOverride(
                datasheet_id=gnarlmaw.DATASHEET_ID,
                model_name="Feculent Gnarlmaw",
                height=height.height_inches,
                height_units=height.source_units,
                height_source_id=height_evidence.source_id,
                height_document_reference=GEOMETRY.relative_to(ROOT).as_posix(),
                reviewer_status=height_evidence.reviewer_status,
                evidence_kind=height_evidence.evidence_kind,
            ),
        ),
    )
    report = build_canonical_catalog_report(
        package_id=PACKAGE,
        catalog_version=VERSION,
        source_artifacts=bridge,
        geometry_overrides=(geometry,),
    )
    if report.package is None or report.blocking_diagnostics():
        raise ValueError(f"Gnarlmaw reviewed bridge remains blocked: {report.diagnostics}")
    bridged = report.package.army_catalog.datasheet_by_id(gnarlmaw.DATASHEET_ID)
    (infiltrators,) = (
        row
        for row in core_descriptions_2026_11.source_rules()
        if row.source_id == INFILTRATORS_SOURCE_ID
    )
    if (
        tuple(a.ability_id for a in bridged.abilities)
        != (
            "000001470:diseased-cover",
            "000001470:fortification",
            "000001470:shroud-of-flies-aura",
            "000008345",
            "000008433",
        )
        or bridged.wargear_options
        or len(bridged.model_profiles) != 1
    ):
        raise ValueError("Gnarlmaw reviewed official datasheet inventory drifted.")
    sheet = replace(
        bridged,
        abilities=tuple(
            replace(a, effect_description=infiltrators.source_text)
            if a.ability_id == "000008345"
            else a
            for a in bridged.abilities
        ),
        source_ids=tuple(sorted({*bridged.source_ids, FACTION_SOURCE_ID, INFILTRATORS_SOURCE_ID})),
    )
    catalog = base.army_catalog
    return replace(
        base,
        package_id=PACKAGE,
        catalog_version=VERSION,
        army_catalog=replace(
            catalog,
            catalog_id=gnarlmaw.CATALOG_ID,
            source_package_id=PACKAGE.stable_identity(),
            datasheets=(*catalog.datasheets, sheet),
            source_ids=tuple(sorted({*catalog.source_ids, *sheet.source_ids})),
        ),
        model_geometries=(*base.model_geometries, geometry),
        source_artifacts=(
            *base.source_artifacts,
            *(
                SourceArtifactHash(f"gnarlmaw-{a.artifact_name}", a.artifact_hash)
                for a in report.package.source_artifacts
            ),
            SourceArtifactHash(
                "gnarlmaw-approved-geometry.json",
                hashlib.sha256(GEOMETRY.read_text(encoding="utf-8").encode()).hexdigest(),
            ),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    check = parser.parse_args().check
    data = build_catalog_package().to_json_bytes()
    if check:
        if OUTPUT.read_bytes() != data:
            raise SystemExit("Gnarlmaw development catalog is stale.")
        gnarlmaw.catalog_package()
    else:
        OUTPUT.write_bytes(data)


if __name__ == "__main__":
    main()
