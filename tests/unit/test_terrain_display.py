from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.terrain_display import (
    TerrainDisplayError,
    TerrainDisplayGeometry,
    TerrainDisplayGeometryPayload,
    TerrainDisplayPoint,
)


def test_axis_aligned_terrain_display_geometry_round_trips_without_object_reprs() -> None:
    geometry = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=10.0,
        center_y_inches=20.0,
        width_inches=6.0,
        depth_inches=4.0,
        display_template_id="ruins_rect_6x4",
    )

    payload = geometry.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert payload["schema_version"] == "terrain-display-v1"
    assert payload["coordinate_space"] == "battlefield_inches"
    assert payload["footprint_kind"] == "polygon"
    assert payload["footprint_polygon"][0] != payload["footprint_polygon"][-1]
    assert (
        TerrainDisplayGeometry.from_payload(cast(TerrainDisplayGeometryPayload, decoded))
        == geometry
    )
    assert geometry.is_within_bounds((7.0, 18.0, 13.0, 22.0))


def test_terrain_display_geometry_rejects_invalid_polygons() -> None:
    with pytest.raises(TerrainDisplayError, match="at least three points"):
        TerrainDisplayGeometry(
            display_template_id="bad",
            footprint_polygon=(
                TerrainDisplayPoint(0.0, 0.0),
                TerrainDisplayPoint(1.0, 0.0),
            ),
        )

    with pytest.raises(TerrainDisplayError, match="unclosed"):
        TerrainDisplayGeometry(
            display_template_id="bad",
            footprint_polygon=(
                TerrainDisplayPoint(0.0, 0.0),
                TerrainDisplayPoint(1.0, 0.0),
                TerrainDisplayPoint(1.0, 1.0),
                TerrainDisplayPoint(0.0, 0.0),
            ),
        )

    with pytest.raises(TerrainDisplayError, match="non-zero area"):
        TerrainDisplayGeometry(
            display_template_id="bad",
            footprint_polygon=(
                TerrainDisplayPoint(0.0, 0.0),
                TerrainDisplayPoint(1.0, 0.0),
                TerrainDisplayPoint(2.0, 0.0),
            ),
        )


def test_terrain_display_geometry_rejects_invalid_payload_metadata() -> None:
    geometry = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=0.0,
        center_y_inches=0.0,
        width_inches=2.0,
        depth_inches=2.0,
        display_template_id=None,
    )

    unsupported_schema = geometry.to_payload()
    unsupported_schema["schema_version"] = "terrain-display-v0"
    with pytest.raises(TerrainDisplayError, match="schema_version"):
        TerrainDisplayGeometry.from_payload(unsupported_schema)

    unsupported_space = geometry.to_payload()
    unsupported_space["coordinate_space"] = "pixels"
    with pytest.raises(TerrainDisplayError, match="coordinate_space"):
        TerrainDisplayGeometry.from_payload(unsupported_space)

    unsupported_kind = geometry.to_payload()
    unsupported_kind["footprint_kind"] = "rectangle"
    with pytest.raises(TerrainDisplayError, match="footprint_kind"):
        TerrainDisplayGeometry.from_payload(unsupported_kind)


def test_terrain_display_geometry_bounds_check_detects_out_of_bounds_polygon() -> None:
    geometry = TerrainDisplayGeometry(
        display_template_id="diagonal-estimate",
        footprint_polygon=(
            TerrainDisplayPoint(0.0, 1.0),
            TerrainDisplayPoint(1.0, 0.0),
            TerrainDisplayPoint(3.0, 2.0),
            TerrainDisplayPoint(2.0, 3.0),
        ),
    )

    assert geometry.is_within_bounds((0.0, 0.0, 3.0, 3.0))
    assert not geometry.is_within_bounds((0.5, 0.0, 3.0, 3.0))
