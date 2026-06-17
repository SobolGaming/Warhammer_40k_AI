from __future__ import annotations

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
