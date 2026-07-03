from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    PlacedTerrainAreaPayload,
    SymmetryAxis,
    TerrainAreaClassification,
    TerrainAreaError,
    TerrainAreaFootprintTemplate,
    TerrainAreaLocalTransform,
    mirror_placed_terrain_area,
    transform_polygon,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayPoint


def test_terrain_area_template_rejects_invalid_polygons() -> None:
    with pytest.raises(TerrainAreaError, match="at least three points"):
        TerrainAreaFootprintTemplate(
            footprint_template_id="bad-empty",
            name="Bad Empty",
            bounding_width_inches=4.0,
            bounding_depth_inches=2.0,
            polygon_vertices_inches=(),
            source_id="test-source",
        )

    with pytest.raises(TerrainAreaError, match="unclosed"):
        TerrainAreaFootprintTemplate(
            footprint_template_id="bad-closed",
            name="Bad Closed",
            bounding_width_inches=4.0,
            bounding_depth_inches=2.0,
            polygon_vertices_inches=(
                TerrainDisplayPoint(-2.0, -1.0),
                TerrainDisplayPoint(2.0, -1.0),
                TerrainDisplayPoint(2.0, 1.0),
                TerrainDisplayPoint(-2.0, -1.0),
            ),
            source_id="test-source",
        )

    with pytest.raises(TerrainAreaError, match="non-zero area"):
        TerrainAreaFootprintTemplate(
            footprint_template_id="bad-zero-area",
            name="Bad Zero Area",
            bounding_width_inches=4.0,
            bounding_depth_inches=2.0,
            polygon_vertices_inches=(
                TerrainDisplayPoint(-2.0, 0.0),
                TerrainDisplayPoint(0.0, 0.0),
                TerrainDisplayPoint(2.0, 0.0),
            ),
            source_id="test-source",
        )

    with pytest.raises(TerrainAreaError, match="self-intersect"):
        TerrainAreaFootprintTemplate(
            footprint_template_id="bad-self-intersection",
            name="Bad Self Intersection",
            bounding_width_inches=4.0,
            bounding_depth_inches=2.0,
            polygon_vertices_inches=(
                TerrainDisplayPoint(-2.0, -1.0),
                TerrainDisplayPoint(2.0, 1.0),
                TerrainDisplayPoint(-2.0, 1.0),
                TerrainDisplayPoint(2.0, -1.0),
                TerrainDisplayPoint(2.0, 0.0),
            ),
            source_id="test-source",
        )


def test_transform_polygon_rotates_and_translates_deterministically() -> None:
    transformed = transform_polygon(
        (
            TerrainDisplayPoint(-1.0, -0.5),
            TerrainDisplayPoint(1.0, -0.5),
            TerrainDisplayPoint(1.0, 0.5),
            TerrainDisplayPoint(-1.0, 0.5),
        ),
        center_x_inches=10.0,
        center_y_inches=20.0,
        rotation_degrees=90.0,
    )

    assert [(round(point.x_inches, 3), round(point.y_inches, 3)) for point in transformed] == [
        (10.5, 19.0),
        (10.5, 21.0),
        (9.5, 21.0),
        (9.5, 19.0),
    ]


def test_transform_polygon_can_mirror_across_anchor_y_axis() -> None:
    transformed = transform_polygon(
        (
            TerrainDisplayPoint(-3.0, 1.0),
            TerrainDisplayPoint(3.0, 1.0),
            TerrainDisplayPoint(3.0, -1.0),
            TerrainDisplayPoint(-3.0, -1.0),
        ),
        center_x_inches=10.0,
        center_y_inches=20.0,
        rotation_degrees=0.0,
        local_transform=TerrainAreaLocalTransform.MIRROR_Y_AXIS,
    )

    assert [(point.x_inches, point.y_inches) for point in transformed] == [
        (7.0, 21.0),
        (1.0, 21.0),
        (1.0, 19.0),
        (7.0, 19.0),
    ]


def test_mirrored_placement_expands_point_center_symmetry() -> None:
    template = _template()
    source = PlacedTerrainArea.from_template(
        terrain_area_id="source-area",
        template=template,
        terrain_feature_kind="terrain_area",
        classification=TerrainAreaClassification.DENSE,
        center_x_inches=8.0,
        center_y_inches=10.0,
        rotation_degrees=0.0,
        source_layout_id="layout-source",
        source_id="test-source:source",
    )
    mirrored = mirror_placed_terrain_area(
        source,
        battlefield_width_inches=44.0,
        battlefield_depth_inches=60.0,
        terrain_area_id="mirrored-area",
        source_id="test-source:mirrored",
        symmetry_axis=SymmetryAxis.POINT_CENTER,
    )

    assert mirrored.center_x_inches == 36.0
    assert mirrored.center_y_inches == 50.0
    assert mirrored.rotation_degrees == 180.0
    assert mirrored.source_transform == "mirrored_from:source-area"
    assert mirrored.symmetry_axis is SymmetryAxis.POINT_CENTER


def test_terrain_area_payload_round_trip_and_missing_vertices_fail_closed() -> None:
    template = _template()
    area = PlacedTerrainArea.from_template(
        terrain_area_id="round-trip-area",
        template=template,
        terrain_feature_kind="terrain_area",
        classification=TerrainAreaClassification.LIGHT,
        center_x_inches=12.0,
        center_y_inches=13.0,
        rotation_degrees=180.0,
        source_layout_id="layout-source",
        source_id="test-source:area",
    )

    encoded = json.dumps(area.to_payload(), sort_keys=True)
    decoded = cast(PlacedTerrainAreaPayload, json.loads(encoded))

    assert PlacedTerrainArea.from_payload(decoded).to_payload() == area.to_payload()
    assert "object at 0x" not in encoded

    template_payload = dict(template.to_payload())
    template_payload.pop("polygon_vertices_inches")
    with pytest.raises(TerrainAreaError, match="polygon_vertices_inches"):
        TerrainAreaFootprintTemplate.from_payload(template_payload)


def _template() -> TerrainAreaFootprintTemplate:
    return TerrainAreaFootprintTemplate(
        footprint_template_id="test-template",
        name="Test Template",
        bounding_width_inches=4.0,
        bounding_depth_inches=2.0,
        polygon_vertices_inches=(
            TerrainDisplayPoint(-2.0, -1.0),
            TerrainDisplayPoint(2.0, -1.0),
            TerrainDisplayPoint(2.0, 0.5),
            TerrainDisplayPoint(1.25, 1.0),
            TerrainDisplayPoint(-2.0, 1.0),
        ),
        source_id="test-source",
    )
