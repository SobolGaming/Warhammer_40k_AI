from __future__ import annotations

import json
from collections import Counter
from typing import cast

import pytest
from scripts import mock_event_layout_ui


@pytest.fixture(scope="module")
def viewer_data() -> dict[str, object]:
    return mock_event_layout_ui.build_data_payload()


def test_mock_event_layout_ui_consumes_exact_battlefield_projections(
    viewer_data: dict[str, object],
) -> None:
    assert viewer_data["viewer_schema"] == "event-companion-battlefield-viewer-v2"
    assert viewer_data["battlefield_view_schema"] == "battlefield-view-v2-phase17n"
    assert viewer_data["force_dispositions"] == [
        {"id": "purge-the-foe", "name": "Purge the Foe"},
        {"id": "take-and-hold", "name": "Take and Hold"},
        {"id": "disruption", "name": "Disruption"},
        {"id": "reconnaissance", "name": "Reconnaissance"},
        {"id": "priority-assets", "name": "Priority Assets"},
    ]

    matrix = _object_map(viewer_data["matrix"])
    exact_cell = _object_map(matrix["purge-the-foe|purge-the-foe"])
    exact_layout_ids = _string_list(exact_cell["layout_ids"])
    assert exact_layout_ids == [
        "purge-the-foe-vs-purge-the-foe-layout-1",
        "purge-the-foe-vs-purge-the-foe-layout-2",
        "purge-the-foe-vs-purge-the-foe-layout-3",
    ]

    layouts = _object_map(viewer_data["layouts"])
    hashes: set[str] = set()
    for layout_id in exact_layout_ids:
        layout = _object_map(layouts[layout_id])
        assert layout["geometry_status"] == "runtime_geometry_available"
        assert "terrain_areas" not in layout
        assert "terrain_features" not in layout

        view = _object_map(layout["battlefield_view"])
        assert view["schema_version"] == "battlefield-view-v2-phase17n"
        assert view["coordinate_spec_version"] == "battlefield-coordinate-v1"
        assert view["coordinate_space"] == "battlefield_inches_right_handed_z_up"
        bounds = _object_map(view["bounds"])
        assert bounds["max_x_inches"] == 44.0
        assert bounds["max_y_inches"] == 60.0
        geometry_hash = _string(view["authoritative_geometry_hash"])
        assert len(geometry_hash) == 64
        hashes.add(geometry_hash)

        authoritative = _object_map(view["authoritative"])
        areas = _object_map(authoritative["terrain_areas_by_id"])
        features = _object_map(authoritative["terrain_features_by_id"])
        objectives = _object_map(authoritative["objectives_by_id"])
        deployment_zones = _object_map(authoritative["deployment_zones_by_id"])
        regions = _object_map(authoritative["battlefield_regions_by_id"])
        assert len(areas) == 16
        assert len(features) == 30
        assert len(objectives) == 6
        assert len(deployment_zones) == 2
        assert len(regions) == 5
        assert Counter(
            _string(_object_map(area)["classification"]) for area in areas.values()
        ) == Counter({"dense": 6, "mixed": 6, "light": 4})
        assert Counter(
            _string(_object_map(feature)["classification"]) for feature in features.values()
        ) == Counter({"dense": 16, "light": 14})
        assert Counter(
            _string(_object_map(region)["region_kind"]) for region in regions.values()
        ) == Counter({"deployment_zone": 2, "territory": 2, "no_mans_land": 1})

        volumes = [
            _object_map(volume)
            for feature in features.values()
            for volume in _object_list(_object_map(feature)["volumes"])
        ]
        assert Counter(_string(volume["volume_kind"]) for volume in volumes) == Counter(
            {"wall": 70, "floor": 20}
        )
        assert (
            max(
                _number(_object_map(volume["bottom_center"])["z_inches"])
                + _number(volume["height_inches"])
                for volume in volumes
            )
            == 8.0
        )

        render = _object_map(view["render"])
        hints = _object_map(render["hints_by_entity_id"])
        assert set(hints) == set(features)
        assert all(_object_map(hint)["asset_id"] is not None for hint in hints.values())
        assert len(_object_list(layout["objective_terrain_areas"])) == 6
        assert layout["objective_footprint_status"] == "source_linked_footprints_available"

    assert len(hashes) == 3


def test_mock_event_layout_ui_marks_source_only_geometry_without_fallback(
    viewer_data: dict[str, object],
) -> None:
    layouts = _object_map(viewer_data["layouts"])
    status_counts = Counter(
        _string(_object_map(layout)["geometry_status"]) for layout in layouts.values()
    )
    assert status_counts == Counter(
        {"runtime_geometry_available": 9, "terrain_geometry_pending": 36}
    )

    for layout_value in layouts.values():
        layout = _object_map(layout_value)
        view = _object_map(layout["battlefield_view"])
        authoritative = _object_map(view["authoritative"])
        feature_count = len(_object_map(authoritative["terrain_features_by_id"]))
        area_count = len(_object_map(authoritative["terrain_areas_by_id"]))
        region_count = len(_object_map(authoritative["battlefield_regions_by_id"]))
        if layout["geometry_status"] == "runtime_geometry_available":
            assert feature_count > 0
            assert area_count > 0
            assert region_count > 0
        else:
            assert (feature_count, area_count, region_count) == (0, 0, 0)


def test_mock_event_layout_ui_preserves_source_linked_objective_footprints(
    viewer_data: dict[str, object],
) -> None:
    layouts = _object_map(viewer_data["layouts"])
    for layout_value in layouts.values():
        layout = _object_map(layout_value)
        view = _object_map(layout["battlefield_view"])
        authoritative = _object_map(view["authoritative"])
        objectives = _object_map(authoritative["objectives_by_id"])
        areas = _object_map(authoritative["terrain_areas_by_id"])
        bindings = _object_list(layout["objective_terrain_areas"])

        bound_objective_ids: set[str] = set()
        for binding in bindings:
            objective_id = _string(binding["objective_marker_id"])
            assert objective_id not in bound_objective_ids
            bound_objective_ids.add(objective_id)
            objective = _object_map(objectives[objective_id])
            assert binding["objective_role"] == objective["objective_role"]
            area_ids = _string_list(binding["terrain_area_ids"])
            assert area_ids
            assert set(area_ids) <= set(areas)

        expected_status = (
            "source_linked_footprints_available"
            if bound_objective_ids == set(objectives)
            else "footprint_binding_pending"
        )
        assert layout["objective_footprint_status"] == expected_status
        if bindings:
            assert bound_objective_ids == set(objectives)


def test_mock_event_layout_ui_embeds_projection_and_interactive_3d_controls(
    viewer_data: dict[str, object],
) -> None:
    html = mock_event_layout_ui.html_document(data=viewer_data)
    javascript = mock_event_layout_ui.viewer_javascript()
    stylesheet = mock_event_layout_ui.viewer_stylesheet()
    embedded_data = _embedded_layout_data(html)

    assert embedded_data == viewer_data
    assert '<canvas\n          id="battlefield"' in html
    assert '<script src="/viewer.js" defer></script>' in html
    assert '<link rel="stylesheet" href="/viewer.css">' in html
    assert html.count('<option value="purge-the-foe" selected>Purge the Foe</option>') == 2
    assert 'id="view-isometric"' in html
    assert 'id="view-top"' in html
    assert 'id="view-attacker"' in html
    assert 'id="view-defender"' in html
    assert 'id="camera-azimuth"' in html
    assert 'id="camera-elevation"' in html
    assert 'id="camera-zoom"' in html
    assert 'id="show-regions"' in html
    assert 'id="show-components"' in html
    assert 'id="show-walls"' in html
    assert 'id="show-floors"' in html
    assert 'id="entity-details" aria-live="polite"' in html

    assert 'const BATTLEFIELD_VIEW_SCHEMA = "battlefield-view-v2-phase17n";' in javascript
    assert 'const COORDINATE_SPACE = "battlefield_inches_right_handed_z_up";' in javascript
    assert "layout.battlefield_view" in javascript
    assert "view.authoritative" in javascript
    assert "authoritative.terrain_features_by_id" in javascript
    assert "authoritative.battlefield_regions_by_id" in javascript
    assert "volume.bottom_center" in javascript
    assert "volume.rotation_degrees" in javascript
    assert 'addEventListener("pointermove", pointerMove)' in javascript
    assert 'addEventListener("wheel", wheelCamera' in javascript
    assert 'addEventListener("keydown", keyboardCamera)' in javascript
    assert "cameraForBounds" in javascript
    assert "projectPoint" in javascript
    assert "resolveObjectiveTerrainFootprints" in javascript
    assert "drawObjectiveTerrainFootprints" in javascript
    assert "clipWorldPolygonToNearPlane" in javascript
    assert "clipWorldLineToNearPlane" in javascript
    assert "collectObjectiveFaces" not in javascript
    assert "cylinderFaces" not in javascript
    assert "marker_diameter_inches" not in javascript
    assert "layout.terrain_features" not in javascript
    assert "row.terrain_features" not in javascript

    assert "canvas.orbiting" in stylesheet
    assert ".swatch.dense" in stylesheet
    assert ".swatch.light" in stylesheet
    assert ".swatch.mixed" in stylesheet
    assert ".swatch.no-mans-land" in stylesheet


def _embedded_layout_data(html: str) -> dict[str, object]:
    start_tag = '  <script id="layout-data" type="application/json">\n'
    end_tag = '\n  </script>\n  <script src="/viewer.js" defer></script>'
    start = html.index(start_tag) + len(start_tag)
    end = html.index(end_tag, start)
    return _object_map(json.loads(html[start:end].strip()))


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    raw = cast(dict[object, object], value)
    result: dict[str, object] = {}
    for key, item in raw.items():
        assert isinstance(key, str)
        result[key] = item
    return result


def _object_list(value: object) -> list[dict[str, object]]:
    assert isinstance(value, list)
    raw = cast(list[object], value)
    result: list[dict[str, object]] = []
    for item in raw:
        result.append(_object_map(item))
    return result


def _string(value: object) -> str:
    assert isinstance(value, str)
    return value


def _number(value: object) -> float:
    assert isinstance(value, int | float)
    return float(value)


def _string_list(value: object) -> list[str]:
    assert isinstance(value, list)
    raw = cast(list[object], value)
    result: list[str] = []
    for item in raw:
        result.append(_string(item))
    return result
