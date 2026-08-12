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
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.shooting_terrain_visibility import (
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.terrain_area_visibility import (
    TerrainVisibilityArea,
    model_intersects_terrain_area,
    model_wholly_within_terrain_area,
    validate_terrain_visibility_areas,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume


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
        logical_terrain_area_id="source-area",
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
        logical_terrain_area_id="mirrored-area",
        source_id="test-source:mirrored",
        symmetry_axis=SymmetryAxis.POINT_CENTER,
    )

    assert mirrored.center_x_inches == 36.0
    assert mirrored.center_y_inches == 50.0
    assert mirrored.rotation_degrees == 180.0
    assert mirrored.logical_terrain_area_id == "mirrored-area"
    assert mirrored.source_transform == "mirrored_from:source-area"
    assert mirrored.symmetry_axis is SymmetryAxis.POINT_CENTER


def test_terrain_area_payload_round_trip_and_missing_vertices_fail_closed() -> None:
    template = _template()
    area = PlacedTerrainArea.from_template(
        terrain_area_id="round-trip-area",
        logical_terrain_area_id="round-trip-area",
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

    area_payload = dict(area.to_payload())
    area_payload.pop("logical_terrain_area_id")
    with pytest.raises(TerrainAreaError, match="logical_terrain_area_id"):
        PlacedTerrainArea.from_payload(area_payload)


def test_linked_physical_footprints_form_one_logical_visibility_area() -> None:
    left = _rectangle_area(
        terrain_area_id="physical-left",
        logical_terrain_area_id="logical-pair",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    right = _rectangle_area(
        terrain_area_id="physical-right",
        logical_terrain_area_id="logical-pair",
        center_x_inches=3.0,
        classification=TerrainAreaClassification.LIGHT,
    )

    (visibility_area,) = terrain_visibility_areas_from_placements((right, left))

    assert visibility_area.terrain_area_id == "logical-pair"
    assert visibility_area.member_terrain_area_ids == ("physical-left", "physical-right")
    assert visibility_area.classification is TerrainAreaClassification.MIXED
    assert TerrainVisibilityArea.from_payload(visibility_area.to_payload()) == visibility_area
    incomplete_visibility_payload = dict(visibility_area.to_payload())
    incomplete_visibility_payload.pop("footprint_polygons")
    with pytest.raises(GeometryError, match="footprint_polygons"):
        TerrainVisibilityArea.from_payload(incomplete_visibility_payload)
    seam_spanning_model = Model(
        model_id="seam-spanning-model",
        pose=Pose.at(x=2.0, y=1.0, z=0.0),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )
    assert model_wholly_within_terrain_area(seam_spanning_model, visibility_area)
    footprint_models = (
        Model(
            model_id="model-in-left-footprint",
            pose=Pose.at(x=1.0, y=1.0, z=0.0),
            base=CircularBase(radius=0.25),
            volume=ModelVolume(height=2.0),
        ),
        Model(
            model_id="model-in-right-footprint",
            pose=Pose.at(x=3.0, y=1.0, z=0.0),
            base=CircularBase(radius=0.25),
            volume=ModelVolume(height=2.0),
        ),
    )
    assert tuple(
        tuple(
            area.terrain_area_id
            for area in terrain_visibility_areas_from_placements((left, right))
            if model_intersects_terrain_area(model, area)
        )
        for model in footprint_models
    ) == (("logical-pair",), ("logical-pair",))


def test_logical_group_does_not_fill_open_board_between_physical_members() -> None:
    left = _rectangle_area(
        terrain_area_id="physical-gapped-left",
        logical_terrain_area_id="logical-gapped-pair",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    right = _rectangle_area(
        terrain_area_id="physical-gapped-right",
        logical_terrain_area_id="logical-gapped-pair",
        center_x_inches=3.05,
        classification=TerrainAreaClassification.DENSE,
    )
    (visibility_area,) = terrain_visibility_areas_from_placements((left, right))
    seam_spanning_model = Model(
        model_id="model-spanning-open-board",
        pose=Pose.at(x=2.025, y=1.0, z=0.0),
        base=CircularBase(radius=0.03),
        volume=ModelVolume(height=2.0),
    )

    assert visibility_area.terrain_area_id == "logical-gapped-pair"
    assert visibility_area.member_terrain_area_ids == (
        "physical-gapped-left",
        "physical-gapped-right",
    )
    assert model_intersects_terrain_area(seam_spanning_model, visibility_area)
    assert not model_wholly_within_terrain_area(seam_spanning_model, visibility_area)


def test_logical_terrain_grouping_rejects_aliases_singletons_and_unknown_mixes() -> None:
    isolated = _rectangle_area(
        terrain_area_id="physical-isolated",
        logical_terrain_area_id="physical-isolated",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    aliasing_member = _rectangle_area(
        terrain_area_id="physical-other",
        logical_terrain_area_id="physical-isolated",
        center_x_inches=3.0,
        classification=TerrainAreaClassification.DENSE,
    )
    with pytest.raises(GameLifecycleError, match="ambiguously alias"):
        terrain_visibility_areas_from_placements((isolated, aliasing_member))

    distinct_singleton = _rectangle_area(
        terrain_area_id="physical-singleton",
        logical_terrain_area_id="logical-singleton",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    with pytest.raises(GameLifecycleError, match="at least two"):
        terrain_visibility_areas_from_placements((distinct_singleton,))

    unknown_left = _rectangle_area(
        terrain_area_id="physical-unknown-left",
        logical_terrain_area_id="logical-unknown-only",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.UNKNOWN,
    )
    unknown_right = _rectangle_area(
        terrain_area_id="physical-unknown-right",
        logical_terrain_area_id="logical-unknown-only",
        center_x_inches=3.0,
        classification=TerrainAreaClassification.UNKNOWN,
    )
    (unknown_visibility_area,) = terrain_visibility_areas_from_placements(
        (unknown_left, unknown_right)
    )
    assert unknown_visibility_area.classification is TerrainAreaClassification.UNKNOWN

    unknown = _rectangle_area(
        terrain_area_id="physical-unknown",
        logical_terrain_area_id="logical-unknown-mix",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.UNKNOWN,
    )
    known = _rectangle_area(
        terrain_area_id="physical-known",
        logical_terrain_area_id="logical-unknown-mix",
        center_x_inches=3.0,
        classification=TerrainAreaClassification.LIGHT,
    )
    with pytest.raises(GameLifecycleError, match="UNKNOWN"):
        terrain_visibility_areas_from_placements((unknown, known))

    overlapping_left = _rectangle_area(
        terrain_area_id="physical-overlapping-left",
        logical_terrain_area_id="logical-overlapping-pair",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    overlapping_right = _rectangle_area(
        terrain_area_id="physical-overlapping-right",
        logical_terrain_area_id="logical-overlapping-pair",
        center_x_inches=2.5,
        classification=TerrainAreaClassification.DENSE,
    )
    with pytest.raises(GameLifecycleError, match="must not overlap"):
        terrain_visibility_areas_from_placements((overlapping_left, overlapping_right))

    disconnected_left = _rectangle_area(
        terrain_area_id="physical-disconnected-left",
        logical_terrain_area_id="logical-disconnected-pair",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    disconnected_right = _rectangle_area(
        terrain_area_id="physical-disconnected-right",
        logical_terrain_area_id="logical-disconnected-pair",
        center_x_inches=3.1,
        classification=TerrainAreaClassification.DENSE,
    )
    with pytest.raises(GameLifecycleError, match=r"connected within one 0\.05-inch"):
        terrain_visibility_areas_from_placements((disconnected_left, disconnected_right))

    chain_left = _rectangle_area(
        terrain_area_id="physical-chain-left",
        logical_terrain_area_id="logical-chain",
        center_x_inches=1.0,
        classification=TerrainAreaClassification.DENSE,
    )
    chain_middle = _rectangle_area(
        terrain_area_id="physical-chain-middle",
        logical_terrain_area_id="logical-chain",
        center_x_inches=3.0,
        classification=TerrainAreaClassification.DENSE,
    )
    chain_right = _rectangle_area(
        terrain_area_id="physical-chain-right",
        logical_terrain_area_id="logical-chain",
        center_x_inches=5.0,
        classification=TerrainAreaClassification.DENSE,
    )
    (chain_visibility_area,) = terrain_visibility_areas_from_placements(
        (chain_right, chain_left, chain_middle)
    )
    assert chain_visibility_area.member_terrain_area_ids == (
        "physical-chain-left",
        "physical-chain-middle",
        "physical-chain-right",
    )


def test_visibility_area_inventory_rejects_duplicate_physical_members() -> None:
    first = TerrainVisibilityArea(
        terrain_area_id="logical-first",
        member_terrain_area_ids=("physical-shared", "physical-first"),
        classification=TerrainAreaClassification.DENSE,
        footprint_polygons=(
            ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
            ((1.0, 0.0), (2.0, 0.0), (2.0, 1.0), (1.0, 1.0)),
        ),
    )
    second = TerrainVisibilityArea(
        terrain_area_id="logical-second",
        member_terrain_area_ids=("physical-shared", "physical-second"),
        classification=TerrainAreaClassification.LIGHT,
        footprint_polygons=(
            ((3.0, 0.0), (4.0, 0.0), (4.0, 1.0), (3.0, 1.0)),
            ((4.0, 0.0), (5.0, 0.0), (5.0, 1.0), (4.0, 1.0)),
        ),
    )

    with pytest.raises(GeometryError, match="physical member"):
        validate_terrain_visibility_areas("terrain areas", (first, second))


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


def _rectangle_area(
    *,
    terrain_area_id: str,
    logical_terrain_area_id: str,
    center_x_inches: float,
    classification: TerrainAreaClassification,
) -> PlacedTerrainArea:
    template = TerrainAreaFootprintTemplate(
        footprint_template_id="rectangle-template",
        name="Rectangle Template",
        bounding_width_inches=2.0,
        bounding_depth_inches=2.0,
        polygon_vertices_inches=(
            TerrainDisplayPoint(-1.0, -1.0),
            TerrainDisplayPoint(1.0, -1.0),
            TerrainDisplayPoint(1.0, 1.0),
            TerrainDisplayPoint(-1.0, 1.0),
        ),
        source_id="test-rectangle-source",
    )
    return PlacedTerrainArea.from_template(
        terrain_area_id=terrain_area_id,
        logical_terrain_area_id=logical_terrain_area_id,
        template=template,
        terrain_feature_kind="terrain_area",
        classification=classification,
        center_x_inches=center_x_inches,
        center_y_inches=1.0,
        rotation_degrees=0.0,
        source_layout_id="test-layout-source",
        source_id=f"test-source:{terrain_area_id}",
    )
