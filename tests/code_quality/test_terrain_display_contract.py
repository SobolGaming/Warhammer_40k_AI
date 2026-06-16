from __future__ import annotations

import ast
import json
from pathlib import Path

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src" / "warhammer40k_core"
FIXTURE_ROOT = ROOT / "tests" / "fixtures"
SOURCE_ID_STRING_PARSE_METHODS = frozenset(
    (
        "partition",
        "removeprefix",
        "removesuffix",
        "rpartition",
        "split",
    )
)


def test_terrain_display_contract_forbids_source_id_string_parsing() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func
            if not isinstance(function, ast.Attribute):
                continue
            if function.attr not in SOURCE_ID_STRING_PARSE_METHODS:
                continue
            if _is_source_id_expression(function.value):
                violations.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} parses source_id with {function.attr}"
                )

    assert not violations, (
        "Terrain display geometry must be first-class structured data; "
        "production code must not parse source_id strings for rendering details:\n"
        + "\n".join(violations)
    )


def test_projection_fixtures_with_terrain_features_include_display_geometry() -> None:
    violations: list[str] = []
    for path in sorted(FIXTURE_ROOT.rglob("*.json")):
        payload = validate_json_value(json.loads(path.read_text(encoding="utf-8")))
        for feature_path, feature in _terrain_feature_payloads(payload, path="$"):
            if "display_geometry" not in feature:
                violations.append(f"{path.relative_to(ROOT)}:{feature_path}")

    assert not violations, (
        "Projection fixtures that expose terrain features must include typed display_geometry:\n"
        + "\n".join(violations)
    )


def test_projection_fixtures_with_terrain_areas_include_typed_footprints() -> None:
    violations: list[str] = []
    for path in sorted(FIXTURE_ROOT.rglob("*.json")):
        payload = validate_json_value(json.loads(path.read_text(encoding="utf-8")))
        for area_path, area in _terrain_area_payloads(payload, path="$"):
            footprint_polygon = area.get("footprint_polygon")
            if not isinstance(footprint_polygon, list) or not footprint_polygon:
                violations.append(f"{path.relative_to(ROOT)}:{area_path}")

    assert not violations, (
        "Projection fixtures that expose terrain areas must include typed footprint_polygon:\n"
        + "\n".join(violations)
    )


def _is_source_id_expression(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "source_id"
    if isinstance(node, ast.Attribute):
        return node.attr == "source_id"
    if isinstance(node, ast.Subscript):
        return _is_source_id_key(node.slice)
    return False


def _is_source_id_key(node: ast.expr) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == "source_id"
    return False


def _terrain_feature_payloads(
    value: JsonValue,
    *,
    path: str,
) -> list[tuple[str, dict[str, JsonValue]]]:
    matches: list[tuple[str, dict[str, JsonValue]]] = []
    if isinstance(value, dict):
        terrain_feature = value.get("terrain_feature")
        if isinstance(terrain_feature, dict):
            matches.append((f"{path}.terrain_feature", terrain_feature))
        terrain_features = value.get("terrain_features")
        if isinstance(terrain_features, list):
            for index, feature in enumerate(terrain_features):
                if isinstance(feature, dict):
                    matches.append(
                        (
                            f"{path}.terrain_features[{index}]",
                            feature,
                        )
                    )
        for key, child in value.items():
            if key in {"terrain_feature", "terrain_features"}:
                continue
            matches.extend(_terrain_feature_payloads(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_terrain_feature_payloads(child, path=f"{path}[{index}]"))
    return matches


def _terrain_area_payloads(
    value: JsonValue,
    *,
    path: str,
) -> list[tuple[str, dict[str, JsonValue]]]:
    matches: list[tuple[str, dict[str, JsonValue]]] = []
    if isinstance(value, dict):
        terrain_area = value.get("terrain_area")
        if isinstance(terrain_area, dict):
            matches.append((f"{path}.terrain_area", terrain_area))
        terrain_areas = value.get("terrain_areas")
        if isinstance(terrain_areas, list):
            for index, area in enumerate(terrain_areas):
                if isinstance(area, dict):
                    matches.append((f"{path}.terrain_areas[{index}]", area))
        for key, child in value.items():
            if key in {"terrain_area", "terrain_areas"}:
                continue
            matches.extend(_terrain_area_payloads(child, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_terrain_area_payloads(child, path=f"{path}[{index}]"))
    return matches
