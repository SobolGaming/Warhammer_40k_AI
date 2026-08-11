from __future__ import annotations

import json
import math
import shutil
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from scripts import mock_event_layout_ui

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)

_VIEWER_RENDERER_TEST = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "mock_event_layout_ui_assets"
    / "viewer_renderer_test.cjs"
)


@pytest.fixture(scope="module")
def viewer_data() -> dict[str, object]:
    return mock_event_layout_ui.build_data_payload()


def test_mock_event_layout_ui_consumes_exact_battlefield_projections(
    viewer_data: dict[str, object],
) -> None:
    assert viewer_data["viewer_schema"] == "event-companion-battlefield-viewer-v3"
    assert viewer_data["battlefield_view_schema"] == "battlefield-view-v3-phase17n"
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
        assert view["schema_version"] == "battlefield-view-v3-phase17n"
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


def test_mock_event_layout_ui_exposes_full_runtime_geometry_without_fallback(
    viewer_data: dict[str, object],
) -> None:
    layouts = _object_map(viewer_data["layouts"])
    assert len(layouts) == 45
    status_counts = Counter(
        _string(_object_map(layout)["geometry_status"]) for layout in layouts.values()
    )
    assert status_counts == Counter({"runtime_geometry_available": 45})

    total_area_count = 0
    total_component_count = 0
    total_contact_count = 0
    total_logical_area_count = 0
    contact_kind_counts: Counter[str] = Counter()
    page_9_layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    for layout_id, layout_value in layouts.items():
        layout = _object_map(layout_value)
        view = _object_map(layout["battlefield_view"])
        authoritative = _object_map(view["authoritative"])
        feature_count = len(_object_map(authoritative["terrain_features_by_id"]))
        area_count = len(_object_map(authoritative["terrain_areas_by_id"]))
        region_count = len(_object_map(authoritative["battlefield_regions_by_id"]))
        assert layout["geometry_status"] == "runtime_geometry_available"
        assert area_count == 16
        assert feature_count == (29 if layout_id == page_9_layout_id else 30)
        assert region_count > 0
        assert layout["objective_footprint_status"] == ("source_linked_footprints_available")
        contacts = _object_list(layout["terrain_area_contacts"])
        single_contact_count = 0
        for contact in contacts:
            contact_record = _object_map(contact)
            area_ids = _string_list(contact_record["terrain_area_ids"])
            assert len(area_ids) == 2
            assert set(area_ids) <= set(_object_map(authoritative["terrain_areas_by_id"]))
            assert len(_string_list(contact_record["source_icon_ids"])) == 1
            kind = _string(contact_record["kind"])
            contact_kind_counts[kind] += 1
            single_contact_count += int(kind == "single")
            for field_name in ("source_icon_x_inches", "source_icon_y_inches"):
                coordinate = _number(contact_record[field_name])
                assert math.isclose(
                    coordinate,
                    round(coordinate / 0.05) * 0.05,
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            assert 0.0 <= _number(contact_record["runtime_pair_gap_inches"]) <= 0.050001
            assert 0.0 <= _number(contact_record["runtime_pair_overlap_square_inches"]) <= 0.000001
        logical_area_count = int(_number(layout["logical_terrain_area_count"]))
        assert logical_area_count == area_count - single_contact_count
        total_contact_count += len(contacts)
        total_logical_area_count += logical_area_count
        total_area_count += area_count
        total_component_count += feature_count

    assert total_area_count == 720
    assert total_component_count == 1_349
    assert total_logical_area_count == 608
    assert total_contact_count == 224
    assert contact_kind_counts == Counter({"single": 112, "separate": 112})


def test_mock_event_layout_ui_rejects_contacts_without_logical_area_ids() -> None:
    layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    artifact_layout = next(
        candidate
        for candidate in event_layouts.battlefield_artifact().layouts
        if candidate.layout_id == layout_id
    )
    terrain_areas_by_id: dict[str, dict[str, object]] = {
        area.area_id: {"logical_terrain_area_id": area.area_id}
        for area in artifact_layout.terrain_areas
    }
    for contact in artifact_layout.terrain_area_contacts:
        if contact.kind != "single":
            continue
        logical_group_id = contact.source_icon_ids[0]
        for area_id in contact.terrain_area_ids:
            terrain_areas_by_id[area_id]["logical_terrain_area_id"] = logical_group_id
    single_contact = next(
        contact for contact in artifact_layout.terrain_area_contacts if contact.kind == "single"
    )
    for area_id in single_contact.terrain_area_ids:
        terrain_areas_by_id[area_id].pop("logical_terrain_area_id")

    validate_contacts = cast(
        Callable[..., None],
        vars(mock_event_layout_ui)["_validate_terrain_area_contacts"],
    )
    with pytest.raises(
        GameLifecycleError,
        match="requires runtime logical terrain-area IDs",
    ):
        validate_contacts(
            artifact_layout=artifact_layout,
            terrain_areas_by_id=terrain_areas_by_id,
        )


def test_mock_event_layout_ui_preserves_source_linked_objective_footprints(
    viewer_data: dict[str, object],
) -> None:
    layouts = _object_map(viewer_data["layouts"])
    total_source_unbound = 0
    for layout_value in layouts.values():
        layout = _object_map(layout_value)
        view = _object_map(layout["battlefield_view"])
        authoritative = _object_map(view["authoritative"])
        objectives = _object_map(authoritative["objectives_by_id"])
        areas = _object_map(authoritative["terrain_areas_by_id"])
        bindings = _object_list(layout["objective_terrain_areas"])
        source_unbound_objective_ids = set(_string_list(layout["source_unbound_objective_ids"]))

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

        assert bindings
        assert not bound_objective_ids & source_unbound_objective_ids
        assert bound_objective_ids | source_unbound_objective_ids == set(objectives)
        assert layout["objective_footprint_status"] == ("source_linked_footprints_available")
        total_source_unbound += len(source_unbound_objective_ids)

    assert total_source_unbound == 3


def test_mock_event_layout_ui_embeds_projection_and_interactive_3d_controls(
    viewer_data: dict[str, object],
) -> None:
    html = mock_event_layout_ui.html_document(data=viewer_data)
    geometry_javascript = mock_event_layout_ui.viewer_geometry_javascript()
    javascript = mock_event_layout_ui.viewer_javascript()
    stylesheet = mock_event_layout_ui.viewer_stylesheet()
    embedded_data = _embedded_layout_data(html)

    assert embedded_data == viewer_data
    assert '<canvas\n          id="battlefield"' in html
    assert '<script src="/viewer-geometry.js"></script>' in html
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
    assert "Legend (PDF p. 8)" in html
    assert "Single terrain area" in html
    assert "Separate terrain areas" in html

    assert 'const BATTLEFIELD_VIEW_SCHEMA = "battlefield-view-v3-phase17n";' in javascript
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
    assert "validateTerrainAreaContacts" in javascript
    assert 'appendDetail(definitionList, "Logical area", payload.logical_terrain_area_id)' in (
        javascript
    )
    assert 'typeof runtimeGap !== "number"' in javascript
    assert 'typeof sourceGap !== "number"' in javascript
    assert "contact.source_icon_ids.length !== 1" in javascript
    assert "drawTerrainAreaContacts" in javascript
    assert "clipWorldPolygonToNearPlane" in geometry_javascript
    assert "clipWorldLineToNearPlane" in geometry_javascript
    assert "hatchLineSegments" in geometry_javascript
    assert "sharedTerritoryBoundarySegments" in geometry_javascript
    assert "context.setLineDash(lineDash)" in javascript
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


def test_mock_event_layout_ui_executes_bounded_close_camera_rendering(
    viewer_data: dict[str, object],
) -> None:
    completed = _execute_viewer_renderer(viewer_data)
    assert completed.returncode == 0, completed.stderr
    result = _object_map(json.loads(completed.stdout))
    close_camera = _object_map(result["close_camera"])
    assert close_camera == {
        "azimuth_degrees": 315,
        "board_visible": True,
        "defender_territory_visible": True,
        "defender_zone_visible": True,
        "elevation_degrees": 12,
        "terrain_area_14_visible": True,
        "territory_divider_visible": True,
        "zoom": 3.5,
    }
    assert result["tested_azimuth_count"] == 360
    assert _number(result["maximum_hatch_strokes"]) <= _number(result["hatch_stroke_budget"])
    assert result["territory_divider_segments_by_layout"] == {"1": 1, "2": 1, "3": 1}
    assert result["full_catalog_projection_counts"] == {
        "layouts": 45,
        "terrain_areas": 720,
        "terrain_features": 1_349,
        "terrain_area_contacts": 224,
        "deployment_zones": 90,
        "battlefield_regions": 225,
        "objective_binding_records": 243,
        "objective_binding_areas": 264,
    }


def test_mock_event_layout_ui_renderer_rejects_coerced_contact_evidence(
    viewer_data: dict[str, object],
) -> None:
    mutations: tuple[tuple[str, object], ...] = (
        ("source_icon_ids", []),
        ("source_icon_x_inches", None),
        ("source_icon_y_inches", "0"),
        ("source_pair_gap_inches", None),
        ("runtime_pair_gap_inches", "0"),
        ("runtime_pair_overlap_square_inches", None),
    )

    for field_name, invalid_value in mutations:
        invalid_payload = _object_map(json.loads(json.dumps(viewer_data)))
        layouts = _object_map(invalid_payload["layouts"])
        first_layout_id, first_layout_value = next(iter(layouts.items()))
        first_layout = _object_map(first_layout_value)
        contacts = cast(list[object], first_layout["terrain_area_contacts"])
        raw_first_contact: object = contacts[0]
        assert isinstance(raw_first_contact, dict)
        first_contact = cast(dict[str, object], raw_first_contact)
        first_contact[field_name] = invalid_value

        completed = _execute_viewer_renderer(invalid_payload)

        assert completed.returncode != 0, (field_name, first_layout_id)


def _execute_viewer_renderer(payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for the executable viewer renderer regression."
    return subprocess.run(
        [node, str(_VIEWER_RENDERER_TEST)],
        input=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        text=True,
        capture_output=True,
        check=False,
    )


def _embedded_layout_data(html: str) -> dict[str, object]:
    start_tag = '  <script id="layout-data" type="application/json">\n'
    end_tag = (
        '\n  </script>\n  <script src="/viewer-geometry.js"></script>\n'
        '  <script src="/viewer.js" defer></script>'
    )
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
