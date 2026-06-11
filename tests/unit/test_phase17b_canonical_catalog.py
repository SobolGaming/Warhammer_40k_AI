from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.model_geometry_catalog import (
    GeometryCoordinateFrame,
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryOrigin,
    GeometryReviewStatus,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometryDiagnosticReason,
    ModelGeometryImportDiagnostic,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
    ModelZOffsetDefinition,
)
from warhammer40k_core.geometry.model_geometry import (
    GeometrySourceKind,
    HeightSourceKind,
    ModelGeometry,
)
from warhammer40k_core.rules.catalog_generation import (
    CatalogGenerationError,
    build_canonical_catalog_package,
    build_canonical_catalog_report,
)
from warhammer40k_core.rules.catalog_package import (
    CanonicalCatalogPackage,
    CanonicalCatalogPackagePayload,
)
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.wahapedia_schema import WahapediaCsvTable, WahapediaJsonArtifact

_DEATH_GUARD_PDF = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "raw"
    / "faction_packs"
    / "eng_10-06_warhammer40000_faction_pack_death_guard-dgm6djcpoa-iiqvmsh0op.pdf"
)
_DEATH_GUARD_SHA256 = "5430fe8d89047644aab0102d0265783db725655c4535ad6600c3925f2cf32885"


def test_phase17b_representative_datasheets_generate_deterministic_catalog_records() -> None:
    package = _catalog_package()
    second_package = _catalog_package()
    payload = cast(
        CanonicalCatalogPackagePayload,
        json.loads(package.to_json_bytes()),
    )
    datasheet = package.army_catalog.datasheet_by_id("dg-plague-marines")
    geometry_record = package.model_geometries[0]
    runtime_geometry = ModelGeometry.from_catalog_record(geometry_record)

    assert package.to_json_bytes() == second_package.to_json_bytes()
    assert CanonicalCatalogPackage.from_payload(payload).to_payload() == package.to_payload()
    assert math.isclose(datasheet.model_profiles[0].base_size.diameter_mm or 0.0, 32.0)
    assert datasheet.keywords.faction_keywords == ("Death Guard",)
    assert geometry_record.footprint.source_units is GeometrySourceUnits.MILLIMETERS
    assert geometry_record.footprint.canonical_units.value == "inches"
    assert geometry_record.footprint.coordinate_frame is GeometryCoordinateFrame.MODEL_CENTERED_Z_UP
    assert geometry_record.footprint.origin is GeometryOrigin.FOOTPRINT_CENTER_TABLE_SURFACE
    assert geometry_record.height.source_units is GeometrySourceUnits.INCHES
    assert runtime_geometry.geometry_source_kind is GeometrySourceKind.CATALOG_GEOMETRY_RECORD
    assert runtime_geometry.height_source_kind is HeightSourceKind.CATALOG_GEOMETRY_RECORD
    assert math.isclose(runtime_geometry.primary_part().radius_x_inches, 32.0 / 25.4 / 2.0)
    assert math.isclose(runtime_geometry.height_inches, 1.55)

    payload["package_hash"] = hashlib.sha256(b"tampered").hexdigest()
    with pytest.raises(ValueError, match="package_hash"):
        CanonicalCatalogPackage.from_payload(payload)


@pytest.mark.parametrize(
    ("base_size", "reason"),
    [
        ("", ModelGeometryDiagnosticReason.MISSING_BASE_SIZE),
        ("Use model", ModelGeometryDiagnosticReason.MISSING_OVERRIDE),
        ("No official base size", ModelGeometryDiagnosticReason.MISSING_OVERRIDE),
        ("Hull", ModelGeometryDiagnosticReason.MISSING_OVERRIDE),
        ("unique", ModelGeometryDiagnosticReason.MISSING_OVERRIDE),
        ("90 x 52mm rectangular", ModelGeometryDiagnosticReason.NON_DERIVABLE_FOOTPRINT),
    ],
)
def test_phase17b_non_derivable_geometry_rows_block_catalog_emission(
    base_size: str,
    reason: ModelGeometryDiagnosticReason,
) -> None:
    report = build_canonical_catalog_report(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_source_artifacts(model_base_size=base_size),
    )

    assert report.package is None
    assert report.blocking_diagnostics()[0].reason is reason
    with pytest.raises(CatalogGenerationError, match=reason.value):
        report.require_success()


def test_phase17b_missing_representative_height_blocks_catalog_emission() -> None:
    report = build_canonical_catalog_report(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_source_artifacts(include_height=False),
    )

    assert report.package is None
    assert report.blocking_diagnostics()[0].reason is ModelGeometryDiagnosticReason.MISSING_HEIGHT


def test_phase17b_flying_base_override_round_trips_support_hull_and_z_offset() -> None:
    override = _flying_hull_override()
    package = _catalog_package(model_base_size="Use model", geometry_overrides=(override,))
    record = package.model_geometries[0]
    runtime_geometry = ModelGeometry.from_catalog_record(record)

    assert record.support_base is not None
    assert record.support_base.footprint_kind is ModelFootprintKind.CIRCULAR
    assert record.footprint.footprint_kind is ModelFootprintKind.HULL
    assert record.z_offset is not None
    assert record.z_offset.evidence_id == "dg-bloat-drone:z-offset"
    assert math.isclose(record.z_offset.z_offset_inches, 35.0 / 25.4)
    assert record.rules_footprint_policy is GeometryRulesFootprintPolicy.USE_HULL
    assert runtime_geometry.footprint_kind.value == "hull"
    assert not math.isclose(
        record.z_offset.z_offset_inches,
        record.footprint.parts[0].radius_y_inches,
    )

    payload = record.to_payload()
    assert ModelGeometryCatalogRecord.from_payload(payload).to_payload() == payload


def test_phase17b_measurement_evidence_units_and_conversion_affect_package_hash() -> None:
    inches_package = _catalog_package(height="1.55", height_units="inches")
    millimeters_package = _catalog_package(height="39.37", height_units="millimeters")
    inches_height = inches_package.model_geometries[0].height.height_inches
    millimeters_height = millimeters_package.model_geometries[0].height.height_inches

    assert math.isclose(inches_height, millimeters_height)
    assert inches_package.package_hash() != millimeters_package.package_hash()
    assert inches_package.model_geometries[0].evidence[1].source_units is GeometrySourceUnits.INCHES
    assert (
        millimeters_package.model_geometries[0].evidence[1].source_units
        is GeometrySourceUnits.MILLIMETERS
    )


def test_phase17b_oval_base_and_melee_weapon_source_rows_are_canonicalized() -> None:
    package = _catalog_package(
        model_base_size="75 x 42mm",
        weapon_range="melee",
        skill_characteristic="weapon_skill",
        skill="3+",
        weapon_keywords="Sustained Hits",
    )
    datasheet = package.army_catalog.datasheet_by_id("dg-plague-marines")
    profile = datasheet.model_profiles[0]
    weapon_profile = package.army_catalog.wargear[0].weapon_profiles[0]
    geometry_record = package.model_geometries[0]
    runtime_geometry = ModelGeometry.from_catalog_record(geometry_record)

    assert profile.base_size.length_mm == 75.0
    assert profile.base_size.width_mm == 42.0
    assert runtime_geometry.footprint_kind.value == "oval"
    assert math.isclose(runtime_geometry.primary_part().radius_x_inches, 75.0 / 25.4 / 2.0)
    assert weapon_profile.range_profile.kind.value == "melee"
    assert weapon_profile.keywords[0].value == "Sustained Hits"


def test_phase17b_wargear_faction_detachment_enhancement_and_stratagem_records_round_trip() -> None:
    package = _catalog_package()
    catalog = package.army_catalog
    datasheet = catalog.datasheet_by_id("dg-plague-marines")

    assert datasheet.wargear_options[0].default_wargear_ids == ("dg-plague-bolter",)
    assert catalog.wargear[0].wargear_id == "dg-plague-bolter"
    assert catalog.wargear[0].weapon_profiles[0].profile_id == "dg-plague-bolter:standard"
    assert catalog.factions[0].faction_id == "death-guard"
    assert catalog.army_rules[0].rule_id == "nurgles-gift"
    assert catalog.detachments[0].detachment_id == "plague-company"
    assert catalog.enhancements[0].enhancement_id == "deadly-pathogen"
    assert catalog.stratagems[0].stratagem_id == "cloud-of-flies"
    assert (
        CanonicalCatalogPackage.from_payload(package.to_payload()).to_payload()
        == package.to_payload()
    )


def test_phase17b_death_guard_pdf_local_cache_matches_manifest_hash_when_present() -> None:
    if not _DEATH_GUARD_PDF.exists():
        pytest.skip("Local Death Guard faction-pack PDF cache is not present.")
    digest = hashlib.sha256(_DEATH_GUARD_PDF.read_bytes()).hexdigest()

    assert digest == _DEATH_GUARD_SHA256


def test_phase17b_generation_shape_errors_are_fail_fast() -> None:
    override = _flying_hull_override()

    with pytest.raises(CatalogGenerationError, match="package_id"):
        build_canonical_catalog_report(
            package_id=cast(DataPackageId, "bad"),
            catalog_version=_catalog_version(),
            source_artifacts=_source_artifacts(),
        )
    with pytest.raises(CatalogGenerationError, match="source_artifacts"):
        build_canonical_catalog_report(
            package_id=_catalog_package_id(),
            catalog_version=_catalog_version(),
            source_artifacts=(),
        )
    with pytest.raises(CatalogGenerationError, match="normalized artifacts"):
        build_canonical_catalog_report(
            package_id=_catalog_package_id(),
            catalog_version=_catalog_version(),
            source_artifacts=(cast(WahapediaJsonArtifact, "bad"),),
        )
    with pytest.raises(CatalogGenerationError, match="duplicate"):
        build_canonical_catalog_report(
            package_id=_catalog_package_id(),
            catalog_version=_catalog_version(),
            source_artifacts=_source_artifacts(model_base_size="Use model"),
            geometry_overrides=(override, override),
        )


def test_phase17b_canonical_package_rejects_geometry_drift_and_duplicate_artifacts() -> None:
    package = _catalog_package()
    extra_geometry = replace(
        package.model_geometries[0],
        model_geometry_id="extra-profile",
        model_profile_id="extra-profile",
    )

    with pytest.raises(ValueError, match="model_geometries must not be empty"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=(),
        )
    with pytest.raises(ValueError, match="unknown profiles"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=(*package.model_geometries, extra_geometry),
        )
    with pytest.raises(ValueError, match="unique"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=(package.source_artifacts[0], package.source_artifacts[0]),
            army_catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        )
    with pytest.raises(ValueError, match="source_edition"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition="warhammer-40000-invalid",
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        )


def test_phase17b_geometry_catalog_validation_errors_are_explicit() -> None:
    override = _flying_hull_override()
    footprint_evidence = next(
        evidence
        for evidence in override.evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )
    unreviewed_height = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="unreviewed-height",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id="manual-review",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", 2.0),),
        document_reference="review packet",
        reviewer_status=GeometryReviewStatus.NEEDS_REVIEW,
    )

    with pytest.raises(ValueError, match="document_reference or url"):
        ModelGeometrySourceEvidence.from_source_dimensions(
            evidence_id="no-source",
            evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
            measurement_kind=GeometryMeasurementKind.HEIGHT,
            source_id="manual-review",
            source_units=GeometrySourceUnits.INCHES,
            source_dimensions=(("height", 2.0),),
        )
    with pytest.raises(ValueError, match="accepted"):
        ModelHeightDefinition.from_evidence(unreviewed_height)
    with pytest.raises(ValueError, match="height"):
        ModelHeightDefinition.from_evidence(footprint_evidence)
    with pytest.raises(ValueError, match="support-base policy"):
        replace(
            override,
            rules_footprint_policy=GeometryRulesFootprintPolicy.USE_SUPPORT_BASE,
            support_base=None,
        )
    with pytest.raises(ValueError, match="unknown geometry evidence"):
        replace(override, evidence=(override.evidence[0],))


def test_phase17b_generation_rejects_missing_tables_and_bad_weapon_keywords() -> None:
    with pytest.raises(CatalogGenerationError, match="Datasheets_models"):
        build_canonical_catalog_report(
            package_id=_catalog_package_id(),
            catalog_version=_catalog_version(),
            source_artifacts=(
                _artifact(
                    table_name="Factions",
                    csv_text=(
                        "id,name,content_scope,faction_keywords,army_rule_id,army_rule_name\n"
                        "death-guard,Death Guard,matched_play,Death Guard,nurgles-gift,"
                        "Nurgle's Gift\n"
                    ),
                ),
            ),
        )
    with pytest.raises(CatalogGenerationError, match="Unsupported weapon keyword"):
        _catalog_package(weapon_keywords="Unsupported")


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"height": "not-number"}, "numeric"),
        ({"height_units": "yards"}, "source units"),
        ({"height_evidence_kind": "unsupported"}, "evidence kind"),
        ({"height_reviewer_status": "unsupported"}, "review status"),
        ({"height_reviewer_status": "needs_review"}, "unreviewed_evidence"),
        ({"skill_characteristic": "leadership"}, "skill_characteristic"),
        ({"skill": "three"}, "integer"),
        ({"weapon_range": "eighteen"}, "integer"),
        ({"model_min": "0"}, "at least 1"),
        ({"detachment_point_cost": "-1"}, "must not be negative"),
        ({"datasheet_keywords": "Infantry, Infantry"}, "duplicates"),
    ],
)
def test_phase17b_generation_rejects_invalid_source_fields(
    kwargs: dict[str, str],
    message: str,
) -> None:
    if kwargs.get("height_reviewer_status") == "needs_review":
        report = build_canonical_catalog_report(
            package_id=_catalog_package_id(),
            catalog_version=_catalog_version(),
            source_artifacts=_source_artifacts_from_text_overrides(kwargs),
        )

        assert report.package is None
        assert (
            report.blocking_diagnostics()[0].reason
            is ModelGeometryDiagnosticReason.UNREVIEWED_EVIDENCE
        )
        with pytest.raises(CatalogGenerationError, match=message):
            report.require_success()
        return

    with pytest.raises(CatalogGenerationError, match=message):
        _catalog_package_from_text_overrides(kwargs)


def test_phase17b_catalog_package_tuple_validation_is_strict() -> None:
    package = _catalog_package()

    with pytest.raises(ValueError, match="package_id"):
        CanonicalCatalogPackage(
            package_id=cast(DataPackageId, "bad"),
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        )
    with pytest.raises(ValueError, match="catalog_version"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=cast(CatalogVersion, "bad"),
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=package.model_geometries,
        )
    with pytest.raises(ValueError, match="model_geometries must be a tuple"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=cast(
                tuple[ModelGeometryCatalogRecord, ...],
                list(package.model_geometries),
            ),
        )
    with pytest.raises(ValueError, match="duplicate model profiles"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=(package.model_geometries[0], package.model_geometries[0]),
        )
    with pytest.raises(ValueError, match="diagnostics must contain"):
        CanonicalCatalogPackage(
            package_id=package.package_id,
            catalog_version=package.catalog_version,
            source_edition=package.source_edition,
            source_artifacts=package.source_artifacts,
            army_catalog=package.army_catalog,
            model_geometries=package.model_geometries,
            diagnostics=cast(tuple[ModelGeometryImportDiagnostic, ...], ("bad",)),
        )


def test_phase17b_geometry_catalog_validation_covers_unsupported_links_and_parts() -> None:
    override = _flying_hull_override()
    footprint_evidence = next(
        evidence
        for evidence in override.evidence
        if evidence.measurement_kind is GeometryMeasurementKind.FOOTPRINT
    )
    height_evidence = next(
        evidence
        for evidence in override.evidence
        if evidence.measurement_kind is GeometryMeasurementKind.HEIGHT
    )
    footprint_part = override.footprint.parts[0]

    with pytest.raises(ValueError, match="dimension was not found"):
        footprint_evidence.dimension_inches("height")
    with pytest.raises(ValueError, match="z-offset"):
        ModelZOffsetDefinition.from_evidence(height_evidence)
    with pytest.raises(ValueError, match="footprint or support-base"):
        ModelFootprintPartDefinition.from_evidence(
            part_id="height-as-footprint",
            footprint_kind=ModelFootprintKind.CIRCULAR,
            evidence=height_evidence,
        )
    with pytest.raises(ValueError, match="part is invalid"):
        ModelFootprintDefinition.single_part(
            footprint_id="bad-footprint",
            footprint_kind=ModelFootprintKind.CIRCULAR,
            part=cast(ModelFootprintPartDefinition, "bad"),
        )
    with pytest.raises(ValueError, match="parts must not contain duplicates"):
        ModelFootprintDefinition(
            footprint_id="duplicate-parts",
            footprint_kind=ModelFootprintKind.HULL,
            parts=(footprint_part, footprint_part),
            source_units=footprint_part.source_units,
            canonical_units=footprint_part.canonical_units,
            coordinate_frame=footprint_part.coordinate_frame,
            origin=footprint_part.origin,
            evidence_id=footprint_part.evidence_id,
        )
    with pytest.raises(ValueError, match="evidence must not contain duplicates"):
        replace(override, evidence=(*override.evidence, override.evidence[0]))


def _catalog_package(
    *,
    model_base_size: str = "32mm",
    height: str = "1.55",
    height_units: str = "inches",
    height_source_id: str = "death-guard-pdf-p12",
    height_document_reference: str = "Death Guard Faction Pack p.12",
    height_reviewer_status: str = "accepted",
    height_evidence_kind: str = "manual_measurement",
    model_min: str = "5",
    model_max: str = "10",
    datasheet_keywords: str = "Infantry, Battleline",
    weapon_range: str = "24",
    skill_characteristic: str = "ballistic_skill",
    skill: str = "3+",
    weapon_keywords: str = "Lethal Hits",
    detachment_point_cost: str = "1",
    geometry_overrides: tuple[ModelGeometryCatalogRecord, ...] = (),
) -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_source_artifacts(
            model_base_size=model_base_size,
            height=height,
            height_units=height_units,
            height_source_id=height_source_id,
            height_document_reference=height_document_reference,
            height_reviewer_status=height_reviewer_status,
            height_evidence_kind=height_evidence_kind,
            model_min=model_min,
            model_max=model_max,
            datasheet_keywords=datasheet_keywords,
            weapon_range=weapon_range,
            skill_characteristic=skill_characteristic,
            skill=skill,
            weapon_keywords=weapon_keywords,
            detachment_point_cost=detachment_point_cost,
        ),
        geometry_overrides=geometry_overrides,
    )


def _catalog_package_from_text_overrides(
    overrides: dict[str, str],
) -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=_catalog_package_id(),
        catalog_version=_catalog_version(),
        source_artifacts=_source_artifacts_from_text_overrides(overrides),
    )


def _source_artifacts_from_text_overrides(
    overrides: dict[str, str],
) -> tuple[WahapediaJsonArtifact, ...]:
    return _source_artifacts(
        model_base_size=overrides.get("model_base_size", "32mm"),
        height=overrides.get("height", "1.55"),
        height_units=overrides.get("height_units", "inches"),
        height_source_id=overrides.get("height_source_id", "death-guard-pdf-p12"),
        height_document_reference=overrides.get(
            "height_document_reference",
            "Death Guard Faction Pack p.12",
        ),
        height_reviewer_status=overrides.get("height_reviewer_status", "accepted"),
        height_evidence_kind=overrides.get("height_evidence_kind", "manual_measurement"),
        model_min=overrides.get("model_min", "5"),
        model_max=overrides.get("model_max", "10"),
        datasheet_keywords=overrides.get("datasheet_keywords", "Infantry, Battleline"),
        weapon_range=overrides.get("weapon_range", "24"),
        skill_characteristic=overrides.get("skill_characteristic", "ballistic_skill"),
        skill=overrides.get("skill", "3+"),
        weapon_keywords=overrides.get("weapon_keywords", "Lethal Hits"),
        detachment_point_cost=overrides.get("detachment_point_cost", "1"),
    )


def _source_artifacts(
    *,
    model_base_size: str = "32mm",
    height: str = "1.55",
    height_units: str = "inches",
    height_source_id: str = "death-guard-pdf-p12",
    height_document_reference: str = "Death Guard Faction Pack p.12",
    height_reviewer_status: str = "accepted",
    height_evidence_kind: str = "manual_measurement",
    model_min: str = "5",
    model_max: str = "10",
    datasheet_keywords: str = "Infantry, Battleline",
    weapon_range: str = "24",
    skill_characteristic: str = "ballistic_skill",
    skill: str = "3+",
    weapon_keywords: str = "Lethal Hits",
    detachment_point_cost: str = "1",
    include_height: bool = True,
) -> tuple[WahapediaJsonArtifact, ...]:
    height_columns = (
        ",height,height_units,height_source_id,height_document_reference,"
        "height_reviewer_status,height_evidence_kind"
    )
    height_values = (
        f",{height},{height_units},{height_source_id},"
        f"{height_document_reference},{height_reviewer_status},{height_evidence_kind}"
    )
    model_csv = (
        "datasheet_id,line,name,model_profile_id,content_scope,m,t,sv,w,ld,oc,ws,bs,"
        "min_models,max_models,base_size"
        f"{height_columns if include_height else ''}\n"
        'dg-plague-marines,1,Plague Marine,dg-plague-marine,matched_play,5",5,3+,2,6+,2,3+,3+,'
        f'{model_min},{model_max},"{model_base_size}"{height_values if include_height else ""}\n'
    )
    return (
        _artifact(
            table_name="Factions",
            csv_text=(
                "id,name,content_scope,faction_keywords,army_rule_id,army_rule_name\n"
                'death-guard,Death Guard,matched_play,"Death Guard",nurgles-gift,'
                "Nurgle's Gift\n"
            ),
        ),
        _artifact(
            table_name="Datasheets",
            csv_text=(
                "id,name,content_scope,keywords,faction_keywords\n"
                f'dg-plague-marines,Plague Marines,matched_play,"{datasheet_keywords}",'
                '"Death Guard"\n'
            ),
        ),
        _artifact(table_name="Datasheets_models", csv_text=model_csv),
        _artifact(
            table_name="Datasheets_wargear",
            csv_text=(
                "datasheet_id,line,name,wargear_id,weapon_profile_id,model_profile_id,range,a,"
                "skill_characteristic,skill,s,ap,d,weapon_keywords\n"
                "dg-plague-marines,1,Plague bolter,dg-plague-bolter,"
                "dg-plague-bolter:standard,dg-plague-marine,"
                f"{weapon_range},2,{skill_characteristic},{skill},4,-1,1,"
                f'"{weapon_keywords}"\n'
            ),
        ),
        _artifact(
            table_name="Enhancements",
            csv_text=(
                "id,name,description,content_scope,points\n"
                'deadly-pathogen,Deadly Pathogen,"Add 1 to Attacks.",matched_play,15\n'
            ),
        ),
        _artifact(
            table_name="Stratagems",
            csv_text=(
                "id,name,description,content_scope,command_point_cost,timing_tags\n"
                'cloud-of-flies,Cloud of Flies,"Use in the Shooting phase.",matched_play,1,'
                "shooting\n"
            ),
        ),
        _artifact(
            table_name="Detachments",
            csv_text=(
                "id,name,description,content_scope,faction_id,detachment_point_cost,"
                "unit_datasheet_ids,force_disposition_ids,enhancement_ids,stratagem_ids\n"
                'plague-company,Plague Company,"Death Guard detachment.",matched_play,'
                "death-guard,"
                f"{detachment_point_cost},dg-plague-marines,purge-the-foe,"
                "deadly-pathogen,cloud-of-flies\n"
            ),
        ),
    )


def _artifact(*, table_name: str, csv_text: str) -> WahapediaJsonArtifact:
    return WahapediaJsonArtifact.from_csv_table(
        source_package_id=_source_package_id(),
        table=WahapediaCsvTable.from_csv_text(table_name=table_name, csv_text=csv_text),
    )


def _flying_hull_override() -> ModelGeometryCatalogRecord:
    hull_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="dg-bloat-drone:hull",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id="death-guard-pdf-p18-hull-review",
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(("length", 120.0), ("width", 85.0)),
        document_reference="Death Guard Faction Pack p.18",
    )
    support_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="dg-bloat-drone:support-base",
        evidence_kind=GeometryEvidenceKind.OFFICIAL_BASE_SIZE,
        measurement_kind=GeometryMeasurementKind.SUPPORT_BASE,
        source_id="death-guard-pdf-p18-base",
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(("diameter", 60.0),),
        coordinate_frame=GeometryCoordinateFrame.MODEL_CENTERED_Z_UP,
        origin=GeometryOrigin.SUPPORT_BASE_CENTER_TABLE_SURFACE,
        document_reference="Death Guard Faction Pack p.18",
    )
    z_offset_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="dg-bloat-drone:z-offset",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.Z_OFFSET,
        source_id="death-guard-pdf-p18-stem-review",
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(("z_offset", 35.0),),
        document_reference="Death Guard Faction Pack p.18",
        reviewer_status=GeometryReviewStatus.ACCEPTED,
    )
    height_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id="dg-bloat-drone:height",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id="death-guard-pdf-p18-height-review",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", 4.5),),
        document_reference="Death Guard Faction Pack p.18",
    )
    hull_part = ModelFootprintPartDefinition.from_evidence(
        part_id="hull",
        footprint_kind=ModelFootprintKind.HULL,
        evidence=hull_evidence,
    )
    support_part = ModelFootprintPartDefinition.from_evidence(
        part_id="support-base",
        footprint_kind=ModelFootprintKind.CIRCULAR,
        evidence=support_evidence,
    )
    return ModelGeometryCatalogRecord(
        model_geometry_id="dg-plague-marine",
        model_profile_id="dg-plague-marine",
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_HULL,
        footprint=ModelFootprintDefinition.single_part(
            footprint_id="dg-bloat-drone:hull",
            footprint_kind=ModelFootprintKind.HULL,
            part=hull_part,
        ),
        support_base=ModelFootprintDefinition.single_part(
            footprint_id="dg-bloat-drone:support-base",
            footprint_kind=ModelFootprintKind.CIRCULAR,
            part=support_part,
        ),
        z_offset=ModelZOffsetDefinition.from_evidence(z_offset_evidence),
        height=ModelHeightDefinition.from_evidence(height_evidence),
        evidence=(hull_evidence, support_evidence, z_offset_evidence, height_evidence),
        source_ids=("death-guard-pdf-p18",),
    )


def _source_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="gw",
        package_name="death-guard-faction-pack-source",
        version="2026-06-10",
    )


def _catalog_package_id() -> DataPackageId:
    return DataPackageId(
        namespace="core-v2",
        package_name="death-guard-catalog",
        version="phase17b",
    )


def _catalog_version() -> CatalogVersion:
    return CatalogVersion.dated(
        version_id="warhammer-40000-11th-phase17b",
        source_date=date(2026, 6, 10),
    )
