from __future__ import annotations

from warhammer40k_core.core.model_geometry_catalog import (
    GeometryEvidenceKind,
    GeometryMeasurementKind,
    GeometryRulesFootprintPolicy,
    GeometrySourceUnits,
    ModelFootprintDefinition,
    ModelFootprintKind,
    ModelFootprintPartDefinition,
    ModelGeometryCatalogRecord,
    ModelGeometrySourceEvidence,
    ModelHeightDefinition,
)


def accepted_model_geometry(
    model_profile_id: str = "core-intercessor-like",
) -> ModelGeometryCatalogRecord:
    footprint_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{model_profile_id}:accepted-footprint",
        evidence_kind=GeometryEvidenceKind.OFFICIAL_BASE_SIZE,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id=f"{model_profile_id}:official-base-size",
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(("diameter", 32.0),),
        document_reference="GameConfig geometry regression fixture",
    )
    height_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{model_profile_id}:accepted-height",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id=f"{model_profile_id}:reviewed-height",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", 1.55),),
        document_reference="GameConfig geometry regression fixture",
    )
    footprint_part = ModelFootprintPartDefinition.from_evidence(
        part_id="base",
        footprint_kind=ModelFootprintKind.CIRCULAR,
        evidence=footprint_evidence,
    )
    return ModelGeometryCatalogRecord(
        model_geometry_id=model_profile_id,
        model_profile_id=model_profile_id,
        rules_footprint_policy=GeometryRulesFootprintPolicy.USE_FOOTPRINT,
        footprint=ModelFootprintDefinition.single_part(
            footprint_id=f"{model_profile_id}:accepted-footprint",
            footprint_kind=ModelFootprintKind.CIRCULAR,
            part=footprint_part,
        ),
        support_base=None,
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height_evidence),
        evidence=(footprint_evidence, height_evidence),
        source_ids=(f"{model_profile_id}:geometry-review",),
    )


__all__ = ("accepted_model_geometry",)
