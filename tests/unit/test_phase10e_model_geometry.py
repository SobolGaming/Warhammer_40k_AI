from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
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
from warhammer40k_core.engine.list_validation import ModelProfileSelection, UnitMusterSelection
from warhammer40k_core.engine.unit_factory import (
    ModelInstance,
    ModelInstancePayload,
    UnitFactory,
    UnitFactoryError,
)
from warhammer40k_core.geometry.measurement import millimeters_to_inches
from warhammer40k_core.geometry.model_geometry import (
    BaseFootprintKind,
    FootprintPart,
    GeometrySourceKind,
    HeightSourceKind,
    ModelGeometry,
    ModelGeometryPayload,
)
from warhammer40k_core.geometry.pose import GeometryError


def test_circular_base_resolves_to_inch_radius() -> None:
    geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.circular(32.0),
        keywords=("Infantry",),
        geometry_source_id="core-intercessor-like",
    )
    part = geometry.primary_part()

    assert geometry.footprint_kind is BaseFootprintKind.CIRCULAR
    assert part.footprint_kind is BaseFootprintKind.CIRCULAR
    assert math.isclose(part.radius_x_inches, millimeters_to_inches(32.0) / 2.0)
    assert part.radius_x_inches == part.radius_y_inches
    assert geometry.geometry_source_kind is GeometrySourceKind.CATALOG_BASE_SIZE
    assert geometry.geometry_source_id == "core-intercessor-like"
    assert geometry.height_source_kind is HeightSourceKind.KEYWORD_HEURISTIC
    assert geometry.height_source_id == "keyword:infantry_or_character"


def test_oval_base_resolves_major_and_minor_inch_radii() -> None:
    geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.oval(length_mm=75.0, width_mm=42.0),
        keywords=("Beast",),
        geometry_source_id="oval-profile",
    )
    part = geometry.primary_part()

    assert geometry.footprint_kind is BaseFootprintKind.OVAL
    assert part.footprint_kind is BaseFootprintKind.OVAL
    assert math.isclose(part.radius_x_inches, millimeters_to_inches(75.0) / 2.0)
    assert math.isclose(part.radius_y_inches, millimeters_to_inches(42.0) / 2.0)
    assert geometry.height_source_kind is HeightSourceKind.KEYWORD_HEURISTIC
    assert geometry.height_source_id == "keyword:beast_or_cavalry"


def test_resolved_geometry_stores_inches_only_while_catalog_base_remains_millimeters() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog).instantiate_unit(
        army_id="army-alpha",
        selection=_unit_selection(),
        datasheet=datasheet,
    )
    model = unit.own_models[0]
    payload = model.geometry.to_payload()
    blob = json.dumps(payload, sort_keys=True)

    assert model.base_size.diameter_mm == 32.0
    assert "inch" in blob
    assert "mm" not in blob.lower()
    assert "<" not in blob
    assert "object at 0x" not in blob


def test_missing_height_uses_explicit_keyword_or_fallback_provenance() -> None:
    infantry_geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.circular(32.0),
        keywords=("Infantry",),
        geometry_source_id="infantry-profile",
    )
    fallback_geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.circular(32.0),
        keywords=(),
        geometry_source_id="unknown-profile",
    )

    assert infantry_geometry.height_source_kind is HeightSourceKind.KEYWORD_HEURISTIC
    assert infantry_geometry.height_source_id == "keyword:infantry_or_character"
    assert fallback_geometry.height_source_kind is HeightSourceKind.FALLBACK_BASE_MINOR_DIAMETER
    assert fallback_geometry.height_source_id == "base_minor_diameter"
    assert math.isclose(
        fallback_geometry.height_inches,
        fallback_geometry.primary_part().radius_y_inches * 2.0,
    )


def test_invalid_source_dimensions_and_shapes_fail_fast() -> None:
    valid_geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.circular(32.0),
        keywords=("Infantry",),
        geometry_source_id="profile",
    )

    with pytest.raises(GeometryError, match="greater than 0"):
        millimeters_to_inches(0.0)
    with pytest.raises(GeometryError, match="BaseSizeDefinition"):
        ModelGeometry.from_base_size(
            cast(BaseSizeDefinition, "bad-base-size"),
            geometry_source_id="profile",
        )
    with pytest.raises(GeometryError, match="greater than 0"):
        FootprintPart(
            part_id="base",
            footprint_kind=BaseFootprintKind.CIRCULAR,
            radius_x_inches=0.0,
            radius_y_inches=0.0,
        )
    with pytest.raises(GeometryError, match="Unsupported BaseFootprintKind"):
        replace(valid_geometry, footprint_kind=cast(BaseFootprintKind, "bad-kind"))
    with pytest.raises(GeometryError, match="keyword"):
        ModelGeometry.from_base_size(
            BaseSizeDefinition.circular(32.0),
            keywords=cast(tuple[str, ...], ("",)),
            geometry_source_id="profile",
        )


def test_model_geometry_requires_explicit_provenance_for_resolved_sources() -> None:
    part = FootprintPart(
        part_id="base",
        footprint_kind=BaseFootprintKind.CIRCULAR,
        radius_x_inches=1.0,
        radius_y_inches=1.0,
    )

    with pytest.raises(GeometryError, match="Catalog-derived geometry requires"):
        ModelGeometry(
            footprint_kind=BaseFootprintKind.CIRCULAR,
            parts=(part,),
            height_inches=1.0,
            geometry_source_kind=GeometrySourceKind.CATALOG_BASE_SIZE,
            geometry_source_id=None,
            height_source_kind=HeightSourceKind.MANUAL_OVERRIDE,
            height_source_id=None,
        )
    for height_source_kind in (
        HeightSourceKind.KEYWORD_HEURISTIC,
        HeightSourceKind.FALLBACK_BASE_MINOR_DIAMETER,
    ):
        with pytest.raises(GeometryError, match="Resolved model height requires"):
            ModelGeometry(
                footprint_kind=BaseFootprintKind.CIRCULAR,
                parts=(part,),
                height_inches=1.0,
                geometry_source_kind=GeometrySourceKind.MANUAL_OVERRIDE,
                geometry_source_id=None,
                height_source_kind=height_source_kind,
                height_source_id=None,
            )


def test_model_geometry_payloads_round_trip_without_object_reprs() -> None:
    geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.oval(length_mm=75.0, width_mm=42.0),
        keywords=(),
        geometry_source_id="oval-profile",
    )
    payload = cast(
        ModelGeometryPayload,
        json.loads(json.dumps(geometry.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert "mm" not in blob.lower()
    assert ModelGeometry.from_payload(payload).to_payload() == payload


def test_unit_factory_requires_resolved_model_geometry() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog).instantiate_unit(
        army_id="army-alpha",
        selection=_unit_selection(),
        datasheet=datasheet,
    )
    model = unit.own_models[0]

    assert isinstance(model.geometry, ModelGeometry)
    with pytest.raises(UnitFactoryError, match="geometry"):
        replace(model, geometry=cast(ModelGeometry, "bad-geometry"))


def test_unit_factory_rejects_partial_catalog_geometry_for_selected_profile() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-boyz-like-infantry")
    partial_catalog_geometry = (_catalog_geometry_record("core-intercessor-like"),)

    with pytest.raises(
        UnitFactoryError,
        match="Catalog model geometry is incomplete for selected profile",
    ):
        UnitFactory(
            catalog=catalog,
            model_geometries=partial_catalog_geometry,
        ).instantiate_unit(
            army_id="army-alpha",
            selection=UnitMusterSelection(
                unit_selection_id="boyz-unit-1",
                datasheet_id="core-boyz-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-boyz-like",
                        model_count=10,
                    ),
                ),
                wargear_selections=(),
            ),
            datasheet=datasheet,
        )


def test_model_instance_from_payload_rejects_geometry_footprint_kind_drift() -> None:
    payload = _runtime_model_payload()
    payload["geometry"] = ModelGeometry.from_base_size(
        BaseSizeDefinition.oval(length_mm=75.0, width_mm=42.0),
        keywords=("Infantry",),
        geometry_source_id=payload["model_profile_id"],
    ).to_payload()

    with pytest.raises(UnitFactoryError, match="footprint"):
        ModelInstance.from_payload(payload)


def test_model_instance_from_payload_rejects_geometry_radius_drift() -> None:
    payload = _runtime_model_payload()
    part = payload["geometry"]["parts"][0]
    part["radius_x_inches"] = part["radius_x_inches"] * 1.25
    part["radius_y_inches"] = part["radius_y_inches"] * 1.25

    with pytest.raises(UnitFactoryError, match="radius_x_inches"):
        ModelInstance.from_payload(payload)


def test_model_instance_rejects_wrong_catalog_base_geometry_on_replace() -> None:
    model = _runtime_model()
    wrong_catalog_base_geometry = ModelGeometry.from_base_size(
        BaseSizeDefinition.oval(length_mm=75.0, width_mm=42.0),
        keywords=("Infantry",),
        geometry_source_id=model.model_profile_id,
    )

    with pytest.raises(UnitFactoryError, match="footprint"):
        replace(model, geometry=wrong_catalog_base_geometry)


def _runtime_model() -> ModelInstance:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    datasheet = catalog.datasheet_by_id("core-intercessor-like-infantry")
    unit = UnitFactory(catalog).instantiate_unit(
        army_id="army-alpha",
        selection=_unit_selection(),
        datasheet=datasheet,
    )
    return unit.own_models[0]


def _runtime_model_payload() -> ModelInstancePayload:
    return cast(
        ModelInstancePayload,
        json.loads(json.dumps(_runtime_model().to_payload(), sort_keys=True)),
    )


def _catalog_geometry_record(model_profile_id: str) -> ModelGeometryCatalogRecord:
    footprint_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{model_profile_id}:footprint",
        evidence_kind=GeometryEvidenceKind.OFFICIAL_BASE_SIZE,
        measurement_kind=GeometryMeasurementKind.FOOTPRINT,
        source_id=f"{model_profile_id}:source-footprint",
        source_units=GeometrySourceUnits.MILLIMETERS,
        source_dimensions=(("diameter", 32.0),),
        document_reference="Phase 10E geometry fixture",
    )
    height_evidence = ModelGeometrySourceEvidence.from_source_dimensions(
        evidence_id=f"{model_profile_id}:height",
        evidence_kind=GeometryEvidenceKind.MANUAL_MEASUREMENT,
        measurement_kind=GeometryMeasurementKind.HEIGHT,
        source_id=f"{model_profile_id}:source-height",
        source_units=GeometrySourceUnits.INCHES,
        source_dimensions=(("height", 1.55),),
        document_reference="Phase 10E geometry fixture",
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
            footprint_id=f"{model_profile_id}:footprint",
            footprint_kind=ModelFootprintKind.CIRCULAR,
            part=footprint_part,
        ),
        support_base=None,
        z_offset=None,
        height=ModelHeightDefinition.from_evidence(height_evidence),
        evidence=(footprint_evidence, height_evidence),
        source_ids=(f"{model_profile_id}:fixture",),
    )


def _unit_selection() -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id="intercessor-unit-1",
        datasheet_id="core-intercessor-like-infantry",
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
        wargear_selections=(),
    )
