from __future__ import annotations

import json
from typing import cast

from scripts import mock_event_layout_ui


def test_mock_event_layout_ui_exposes_terrain_anchor_rotation_tooltips() -> None:
    data = mock_event_layout_ui.build_data_payload()
    assert data["force_dispositions"] == [
        {"id": "purge-the-foe", "name": "Purge the Foe"},
        {"id": "take-and-hold", "name": "Take and Hold"},
        {"id": "disruption", "name": "Disruption"},
        {"id": "reconnaissance", "name": "Reconnaissance"},
        {"id": "priority-assets", "name": "Priority Assets"},
    ]

    layouts = _object_map(data["layouts"])
    layout_b = _object_map(layouts["take-and-hold-vs-take-and-hold-layout-2"])
    terrain_areas = _object_list(layout_b["terrain_areas"])
    area_by_name = {_string(area["name"]): area for area in terrain_areas}

    central = area_by_name["8x11-5-polygon-central-north"]
    assert central["anchor_x_inches"] == 27.0
    assert central["anchor_y_inches"] == 24.0
    assert central["rotation_degrees"] == -90.0

    north_expansion = area_by_name["7x11-5-north-expansion"]
    assert north_expansion["footprint_template_id"] == "FOOTPRINT_7X11_5"
    assert north_expansion["anchor_x_inches"] == 31.0
    assert north_expansion["anchor_y_inches"] == 14.0
    assert north_expansion["rotation_degrees"] == 180.0

    north_west = area_by_name["6x4-north-west"]
    assert north_west["anchor_x_inches"] == 14.0
    assert north_west["anchor_y_inches"] == 17.0
    assert north_west["rotation_degrees"] == 30.0

    html = mock_event_layout_ui.html_document()
    assert "terrainAreaTitle(area)" in html
    assert "Anchor:" in html
    assert "Rotation:" in html
    assert "stroke: #b8c2cc;" in html
    assert "stroke: #8895a3;" in html
    assert html.count('<option value="take-and-hold" selected>Take and Hold</option>') == 2
    assert '<option value="purge-the-foe">Purge the Foe</option>' in html


def test_mock_event_layout_ui_embeds_renderable_default_layout_data() -> None:
    data = mock_event_layout_ui.build_data_payload()
    html = mock_event_layout_ui.html_document(data=data)
    embedded_data = _embedded_layout_data(html)

    assert embedded_data == data
    assert "initializeData(JSON.parse" in html
    assert 'fetch("/data.json")' in html
    assert "`${marker.name}\\n${terrainAreaTitle(area)}`" in html
    assert '].join("\\n");' in html

    matrix = _object_map(embedded_data["matrix"])
    default_cell = _object_map(matrix["take-and-hold|take-and-hold"])
    layout_ids = _string_list(default_cell["layout_ids"])
    layouts = _object_map(embedded_data["layouts"])
    layout = _object_map(layouts[layout_ids[0]])

    assert layout["id"] == "take-and-hold-vs-take-and-hold-layout-1"
    assert _object_list(layout["deployment_zones"])
    assert _object_list(layout["terrain_areas"])
    assert _object_list(layout["objective_terrain_areas"])


def _embedded_layout_data(html: str) -> dict[str, object]:
    start_tag = '  <script id="layout-data" type="application/json">\n'
    end_tag = "\n  </script>\n  <script>"
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


def _string_list(value: object) -> list[str]:
    assert isinstance(value, list)
    raw = cast(list[object], value)
    result: list[str] = []
    for item in raw:
        result.append(_string(item))
    return result
