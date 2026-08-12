from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from event_companion_battlefield_builder_catalog import (
    ARCHETYPE_IDS as _ARCHETYPE_IDS,
)
from event_companion_battlefield_builder_catalog import (
    DISPLAY_NAME as _DISPLAY_NAME,
)
from event_companion_battlefield_builder_catalog import (
    LAYOUT_CONFIG_BY_PAGE as _LAYOUT_CONFIG_BY_PAGE,
)
from event_companion_battlefield_builder_catalog import (
    PRIMARY_MISSION_DISPLAY_NAME as _PRIMARY_MISSION_DISPLAY_NAME,
)
from event_companion_battlefield_builder_catalog import (
    REVIEWED_FIXED_COMPONENT_CENTERS as _REVIEWED_FIXED_COMPONENT_CENTERS,
)
from event_companion_battlefield_builder_catalog import (
    SOURCE_COORDINATE_FRAME as _SOURCE_COORDINATE_FRAME,
)
from event_companion_battlefield_builder_geometry import (
    AreaPose,
    ComponentPose,
    area_polygon,
    component_local_placement,
    component_local_polygon,
    region_rows,
    solve_area_poses,
    uses_reviewed_exact_seam_pose,
)
from shapely import affinity
from shapely.geometry import Point, Polygon

ARTIFACT_SCHEMA = "core-v2-event-companion-full-battlefield-layouts-v1"
SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-1-2026-07"
SOURCE_PDF_FILENAME = "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
SOURCE_PDF_SHA256 = "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
EXPECTED_EXTRACTION_SHA256 = "a3e9392adeb52696902a016e3c3529933d1e99f3bfd67069d607410d8e1c137f"
EXPECTED_STABLE_IDENTITY_SHA256 = "742ab841d1ec1e696f4a5c0e3f2e8c251203d510bf1da85fb30af88023cb64f3"
_TERRAIN_GRID_INCHES = 0.05
_GEOMETRY_TOLERANCE = 1e-6
_PIPE_CENTER_SEARCH_STEPS = 2

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTION_PATH = (
    REPOSITORY_ROOT
    / "data/source_audits/event_companion_2026_06"
    / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
)
STABLE_IDENTITY_PATH = (
    REPOSITORY_ROOT
    / "data/source_audits/event_companion_2026_06"
    / "phase17n_event_companion_stable_runtime_identity_map.json"
)
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "event_companion_layouts_2026_06/artifacts/event-companion-battlefields.json"
)
SOURCE_PDF_PATH = REPOSITORY_ROOT / "docs/source_rules" / SOURCE_PDF_FILENAME


@dataclass(frozen=True, slots=True)
class StableRuntimeIdentities:
    source_layout_id_by_layout_id: dict[str, str]
    area_id_by_source_id: dict[str, str]
    objective_id_by_source_id: dict[str, str]

    def source_layout_id(self, layout_id: str) -> str:
        established = self.source_layout_id_by_layout_id.get(layout_id)
        if established is not None:
            return established
        return f"gw_event_companion_v1_{layout_id.replace('-', '_')}"

    def area_id(self, source_area_id: str) -> str:
        return self.area_id_by_source_id.get(source_area_id, source_area_id)

    def objective_id(self, source_objective_id: str) -> str:
        return self.objective_id_by_source_id.get(source_objective_id, source_objective_id)


@dataclass(frozen=True, slots=True)
class SourceLayoutMetadata:
    layout_id: str
    force_pair: tuple[str, str]
    missions: tuple[str, str]
    template_number: int
    variant: str
    force_names: tuple[str, str]
    mission_names: tuple[str, str]


_MEATGRINDER_SOURCE_LAYOUT_IDS = {
    "purge-the-foe-vs-purge-the-foe-layout-1": (
        "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-2": (
        "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_b"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-3": (
        "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_c"
    ),
}


def _stable_runtime_identities(
    payload: dict[str, Any],
    *,
    payload_sha256: str,
) -> StableRuntimeIdentities:
    if payload_sha256 != EXPECTED_STABLE_IDENTITY_SHA256:
        raise ValueError("Event Companion stable runtime identity map bytes drifted.")
    if payload["audits"] != {
        "all_reciprocal_symmetry_pairs_preserved": True,
        "ambiguous_mapping_count": 0,
        "footprint_family_mismatch_count": 8,
        "layout_count": 6,
        "objective_mapping_count": 33,
        "terrain_area_mapping_count": 96,
    }:
        raise ValueError("Event Companion stable runtime identity map audit drifted.")
    source_layout_ids = dict(_MEATGRINDER_SOURCE_LAYOUT_IDS)
    area_ids: dict[str, str] = {}
    objective_ids: dict[str, str] = {}
    for layout in payload["layouts"]:
        layout_id = layout["audit_layout_id"]
        if layout_id != layout["established_runtime_layout_id"] or layout_id in source_layout_ids:
            raise ValueError("Stable runtime layout identity map contains a duplicate or drift.")
        source_layout_ids[layout_id] = layout["established_source_layout_id"]
        for source_id, evidence in layout["terrain_area_evidence"].items():
            if source_id in area_ids:
                raise ValueError("Stable terrain-area source identity is duplicated.")
            area_ids[source_id] = evidence["stable_runtime_terrain_area_id"]
        for source_id, evidence in layout["objective_evidence"].items():
            if source_id in objective_ids:
                raise ValueError("Stable objective source identity is duplicated.")
            objective_ids[source_id] = evidence["stable_runtime_objective_id"]
    if (
        len(source_layout_ids) != 9
        or len(area_ids) != 96
        or len(set(area_ids.values())) != 96
        or len(objective_ids) != 33
        or len(set(objective_ids.values())) != 33
    ):
        raise ValueError("Stable runtime identity inventory drifted.")
    return StableRuntimeIdentities(
        source_layout_id_by_layout_id=source_layout_ids,
        area_id_by_source_id=area_ids,
        objective_id_by_source_id=objective_ids,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build all 45 source-reviewed Event Companion battlefield layouts."
    )
    parser.add_argument(
        "extraction",
        type=Path,
        nargs="?",
        default=DEFAULT_EXTRACTION_PATH,
        help="Reviewed pages 9-53 extraction JSON.",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=DEFAULT_OUTPUT_PATH,
        help="Generated full battlefield artifact JSON.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed artifact differs; never write in check mode.",
    )
    return parser.parse_args()


def _canonical_hash(payload: dict[str, Any]) -> str:
    candidate = dict(payload)
    candidate["package_hash"] = ""
    encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_canonical_check_output(raw: bytes) -> None:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Event Companion battlefield artifact is stale.") from exc
    if type(payload) is not dict:
        raise ValueError("Event Companion battlefield artifact is stale.")
    canonical = (json.dumps(payload, indent=2) + "\n").encode()
    if raw != canonical:
        raise ValueError("Event Companion battlefield artifact is stale.")


def _canonical_stable_id(value: str, *, source_layout_id: str, layout_id: str) -> str:
    prefix = f"{source_layout_id}-"
    if not value.startswith(prefix):
        raise ValueError("Source stable ID does not belong to its layout.")
    return f"{layout_id}-{value.removeprefix(prefix)}"


def _pdf_bounds(values: list[object]) -> dict[str, float]:
    if len(values) != 4:
        raise ValueError("Source PDF bounds require four coordinates.")
    return {
        "x0_points": float(values[0]),
        "y0_points": float(values[1]),
        "x1_points": float(values[2]),
        "y1_points": float(values[3]),
    }


def _pdf_affine(values: list[object]) -> dict[str, float]:
    if len(values) != 6:
        raise ValueError("Source PDF affine requires six values.")
    return {
        "a": float(values[0]),
        "b": float(values[1]),
        "c": float(values[2]),
        "d": float(values[3]),
        "e": float(values[4]),
        "f": float(values[5]),
    }


def _templates(extraction: dict[str, Any]) -> dict[str, tuple[tuple[float, float], ...]]:
    result: dict[str, tuple[tuple[float, float], ...]] = {}
    for row in extraction["footprint_templates"]:
        template_id = row["footprint_template_id"]
        vertices = tuple(
            (float(point[0]), float(point[1])) for point in row["polygon_vertices_inches"]
        )
        if template_id in result or len(vertices) < 3:
            raise ValueError("Source footprint-template inventory is invalid.")
        result[template_id] = vertices
    if set(result) != {
        "FOOTPRINT_6X4",
        "FOOTPRINT_10X2_5",
        "FOOTPRINT_6X2",
        "FOOTPRINT_7X11_5",
        "FOOTPRINT_8X11_5_POLYGON",
    }:
        raise ValueError("Source footprint-template inventory drifted.")
    return result


def _reviewed_archetypes(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    rows = extraction["reviewed_feature_archetypes"]
    if tuple(row["archetype_id"] for row in rows) != _ARCHETYPE_IDS:
        raise ValueError("Reviewed terrain-feature archetype order drifted.")
    source_xrefs: set[int] = set()
    for row in rows:
        if not row["source_assets"]:
            raise ValueError("Reviewed terrain-feature archetypes require source assets.")
        for asset in row["source_assets"]:
            xref = asset["source_pdf_image_xref"]
            if xref in source_xrefs:
                raise ValueError("Reviewed source-image xrefs must belong to one archetype.")
            source_xrefs.add(xref)
    return rows


def _rotation_adjustment(runtime_degrees: float, source_degrees: float) -> float:
    rounded = round(runtime_degrees - source_degrees, 6)
    return round(((rounded + 180.0) % 360.0) - 180.0, 6)


def _source_pose_candidate(
    raw: dict[str, Any],
    *,
    pose: AreaPose,
) -> dict[str, Any]:
    candidates = raw["pose_recipe"]["candidates"]
    indexed = tuple(
        candidate
        for candidate in candidates
        if int(candidate["candidate_index"]) == pose.candidate_index
    )
    if len(indexed) == 1 and math.isclose(
        _rotation_adjustment(pose.rotation, float(indexed[0]["rotation_degrees"])),
        0.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        return indexed[0]
    return min(
        candidates,
        key=lambda candidate: (
            math.dist(
                (pose.anchor_x, pose.anchor_y),
                (
                    float(candidate["anchor_x_inches"]),
                    float(candidate["anchor_y_inches"]),
                ),
            )
            + abs(
                _rotation_adjustment(
                    pose.rotation,
                    float(candidate["rotation_degrees"]),
                )
            )
            / 1000.0,
            int(candidate["candidate_index"]),
        ),
    )


def _area_rows(
    layout: dict[str, Any],
    *,
    layout_id: str,
    solved_poses: dict[str, AreaPose],
    identities: StableRuntimeIdentities,
) -> list[dict[str, Any]]:
    source_layout_id = layout["layout_id"]
    rows: list[dict[str, Any]] = []
    for raw in layout["terrain_areas"]:
        source_area_id = _canonical_stable_id(
            raw["area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        area_id = identities.area_id(source_area_id)
        pose = solved_poses[source_area_id]
        source_image = raw["source_area_image"]
        source_path = raw["source_vector_path"]
        orientation_review = raw["runtime_orientation_review"]
        if pose.local_transform != orientation_review["local_transform"]:
            raise ValueError(
                f"Solved terrain-area reflection drifted from its runtime review: {area_id}."
            )
        source_mirror_area_id = _canonical_stable_id(
            raw["point_symmetry_partner_area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        mirror_id = identities.area_id(source_mirror_area_id)
        source_candidate = _source_pose_candidate(raw, pose=pose)
        page = int(layout["source_pdf_page_number"])
        if uses_reviewed_exact_seam_pose(source_area_id):
            pose_basis = "reviewed_source_pose_with_exact_seam_closure"
        elif page in {24, 25, 26}:
            area_index = int(source_area_id.rsplit("-", maxsplit=1)[-1])
            pose_basis = (
                "accepted_meatgrinder_exemplar_source_pose"
                if area_index <= 8
                else "accepted_meatgrinder_exemplar_exact_point_symmetry"
            )
        else:
            pose_basis = "reviewed_source_pose_candidate_with_bounded_seam_adjustment"
        rows.append(
            {
                "area_id": area_id,
                "source_area_id": source_area_id,
                "footprint_template_id": raw["footprint_template_id"],
                "classification": raw["classification"],
                "anchor_x_inches": pose.anchor_x,
                "anchor_y_inches": pose.anchor_y,
                "rotation_degrees": pose.rotation,
                "local_transform": pose.local_transform,
                "local_transform_basis": orientation_review["local_transform_basis"],
                "pose_basis": pose_basis,
                "source_pose_candidate_index": int(source_candidate["candidate_index"]),
                "source_anchor_x_inches": float(source_candidate["anchor_x_inches"]),
                "source_anchor_y_inches": float(source_candidate["anchor_y_inches"]),
                "source_rotation_degrees": float(source_candidate["rotation_degrees"]),
                "source_pose_fit_residual_inches": (
                    None
                    if source_candidate["fit_residual_inches"] is None
                    else float(source_candidate["fit_residual_inches"])
                ),
                "runtime_adjustment_x_inches": round(
                    pose.anchor_x - float(source_candidate["anchor_x_inches"]),
                    12,
                ),
                "runtime_adjustment_y_inches": round(
                    pose.anchor_y - float(source_candidate["anchor_y_inches"]),
                    12,
                ),
                "runtime_rotation_adjustment_degrees": _rotation_adjustment(
                    pose.rotation,
                    float(source_candidate["rotation_degrees"]),
                ),
                "source_pdf_extended_drawing_index_zero_based": source_path[
                    "extended_drawing_index_zero_based"
                ],
                "source_pdf_seqno": source_path["seqno"],
                "source_pdf_vector_item_count": source_path["item_count"],
                "mirror_area_id": mirror_id,
                "source_mirror_area_id": source_mirror_area_id,
                "source_pdf_image_xref": source_image["xref"],
                "source_image_sha256": source_image["source_image_sha256"],
                "source_soft_mask_sha256": source_image["source_soft_mask_sha256"],
                "source_pdf_bounds": _pdf_bounds(source_image["bbox_points"]),
                "source_pdf_affine": _pdf_affine(source_image["affine_normalized_image_to_points"]),
            }
        )
    return rows


def _area_contact_rows(
    layout: dict[str, Any],
    *,
    layout_id: str,
    identities: StableRuntimeIdentities,
    runtime_polygons: dict[str, Polygon],
) -> list[dict[str, Any]]:
    source_layout_id = layout["layout_id"]
    icons_by_id = {row["icon_id"]: row for row in layout["eye_contact_icons"]}
    result: list[dict[str, Any]] = []
    seen_pairs: set[frozenset[str]] = set()
    seen_icon_ids: set[str] = set()
    for raw in layout["source_contact_pairs"]:
        source_area_ids = tuple(
            _canonical_stable_id(
                area_id,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for area_id in raw["area_ids"]
        )
        area_ids = tuple(identities.area_id(area_id) for area_id in source_area_ids)
        source_icon_ids = tuple(
            _canonical_stable_id(
                icon_id,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for icon_id in raw["icon_ids"]
        )
        kinds = raw["kinds"]
        pair = frozenset(area_ids)
        if (
            len(area_ids) != 2
            or area_ids[0] == area_ids[1]
            or len(source_icon_ids) != 1
            or source_icon_ids[0] in seen_icon_ids
            or len(kinds) != 1
            or kinds[0] not in {"single", "separate"}
            or pair in seen_pairs
        ):
            raise ValueError("Source terrain-area contact inventory is invalid.")
        gap = float(raw["source_pair_gap_inches"])
        if not math.isfinite(gap) or gap < 0.0:
            raise ValueError("Source terrain-area contact gap is invalid.")
        seen_pairs.add(pair)
        seen_icon_ids.add(source_icon_ids[0])
        source_icon = icons_by_id.get(raw["icon_ids"][0])
        if source_icon is None:
            raise ValueError("Source terrain-area contact icon is missing.")
        first_polygon, second_polygon = (
            runtime_polygons[source_area_id] for source_area_id in source_area_ids
        )
        runtime_gap = first_polygon.distance(second_polygon)
        runtime_overlap = first_polygon.intersection(second_polygon).area
        if runtime_gap > 0.05 + 1e-6 or runtime_overlap > 1e-6:
            raise ValueError("Runtime terrain-area contact closure is invalid.")
        icon_x, icon_y = source_icon["battlefield_center_quantized_0_05_inches"]
        result.append(
            {
                "terrain_area_ids": list(area_ids),
                "source_terrain_area_ids": list(source_area_ids),
                "kind": kinds[0],
                "source_icon_ids": list(source_icon_ids),
                "source_pdf_drawing_indices_zero_based": list(
                    source_icon["source_drawing_indices_zero_based"]
                ),
                "source_pdf_seqnos": list(source_icon["source_seqnos"]),
                "source_icon_x_inches": float(icon_x),
                "source_icon_y_inches": float(icon_y),
                "source_pair_gap_inches": gap,
                "runtime_pair_gap_inches": round(runtime_gap + 0.0, 9),
                "runtime_pair_overlap_square_inches": round(runtime_overlap + 0.0, 9),
            }
        )
    return result


def _raw_components_by_id(
    layout: dict[str, Any],
    *,
    layout_id: str,
) -> dict[str, dict[str, Any]]:
    source_layout_id = layout["layout_id"]
    result: dict[str, dict[str, Any]] = {}
    for raw in layout["terrain_components"]:
        if raw["inferred"]:
            raise ValueError("Generated battlefield artifacts must not contain inferred pieces.")
        component_id = _canonical_stable_id(
            raw["component_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        if component_id in result:
            raise ValueError("Source terrain-component IDs must be unique.")
        result[component_id] = raw
    return result


def _component_area_id(
    raw: dict[str, Any],
    *,
    source_layout_id: str,
    layout_id: str,
) -> str:
    return _canonical_stable_id(
        raw["parent_area_id"],
        source_layout_id=source_layout_id,
        layout_id=layout_id,
    )


def _runtime_component_id(
    source_component_id: str,
    *,
    source_area_id: str,
    identities: StableRuntimeIdentities,
) -> str:
    prefix = f"{source_area_id}-component-"
    if not source_component_id.startswith(prefix):
        raise ValueError("Source terrain-component ID does not belong to its parent area.")
    ordinal = source_component_id.removeprefix(prefix)
    if len(ordinal) != 2 or not ordinal.isdecimal() or int(ordinal) < 1:
        raise ValueError("Source terrain-component ordinal is invalid.")
    return f"{identities.area_id(source_area_id)}-component-{ordinal}"


def _area_center(
    pose: AreaPose,
    vertices: tuple[tuple[float, float], ...],
) -> tuple[float, float]:
    first_x, first_y = vertices[0]
    radians = math.radians(pose.rotation)
    return (
        pose.anchor_x - (first_x * math.cos(radians) - first_y * math.sin(radians)),
        pose.anchor_y - (first_x * math.sin(radians) + first_y * math.cos(radians)),
    )


def _source_component_pose(raw: dict[str, Any]) -> ComponentPose:
    center_x, center_y = raw["battlefield_center_quantized_0_05_inches"]
    return ComponentPose(
        center_x=float(center_x),
        center_y=float(center_y),
        rotation=float(raw["battlefield_image_x_axis_rotation_degrees"]),
        local_transform=raw["local_orientation_relative_to_parent"]["local_transform"],
    )


def _reviewed_component_pose(
    component_id: str,
    raw: dict[str, Any],
) -> ComponentPose:
    source_pose = _source_component_pose(raw)
    reviewed_center = _REVIEWED_FIXED_COMPONENT_CENTERS.get(component_id)
    if reviewed_center is None:
        return source_pose
    return ComponentPose(
        center_x=reviewed_center[0],
        center_y=reviewed_center[1],
        rotation=source_pose.rotation,
        local_transform=source_pose.local_transform,
    )


def _component_world_polygon(
    vertices: tuple[tuple[float, float], ...],
    *,
    pose: ComponentPose,
    area_pose: AreaPose,
    area_vertices: tuple[tuple[float, float], ...],
) -> Polygon:
    offset_x, offset_y, local_rotation = component_local_placement(
        component_pose=pose,
        area_pose=area_pose,
        area_vertices=area_vertices,
    )
    polygon = component_local_polygon(
        vertices,
        offset_x=offset_x,
        offset_y=offset_y,
        rotation=local_rotation,
        local_transform=pose.local_transform,
    )
    anchor_x, _anchor_y = area_vertices[0]
    area_center_x, area_center_y = _area_center(area_pose, area_vertices)
    if area_pose.local_transform == "mirror_y_axis":
        polygon = affinity.scale(
            polygon,
            xfact=-1.0,
            yfact=1.0,
            origin=(anchor_x, 0.0),
        )
    elif area_pose.local_transform != "identity":
        raise ValueError("Unsupported terrain-area transform in source audit.")
    polygon = affinity.rotate(
        polygon,
        area_pose.rotation,
        origin=(0.0, 0.0),
        use_radians=False,
    )
    return affinity.translate(polygon, xoff=area_center_x, yoff=area_center_y)


def _pipe_component_pose(
    *,
    area_pose: AreaPose,
    area_vertices: tuple[tuple[float, float], ...],
    component_vertices: tuple[tuple[float, float], ...],
    local_transform: str,
) -> ComponentPose:
    area_center_x, area_center_y = _area_center(area_pose, area_vertices)
    transformed_center_x = (
        2.0 * area_vertices[0][0] if area_pose.local_transform == "mirror_y_axis" else 0.0
    )
    radians = math.radians(area_pose.rotation)
    centered_pose = ComponentPose(
        center_x=_quantize_terrain_coordinate(
            area_center_x + transformed_center_x * math.cos(radians)
        ),
        center_y=_quantize_terrain_coordinate(
            area_center_y + transformed_center_x * math.sin(radians)
        ),
        rotation=(
            area_pose.rotation + (180.0 if area_pose.local_transform == "mirror_y_axis" else 0.0)
        )
        % 360.0,
        local_transform=local_transform,
    )
    parent_polygon = area_polygon(area_vertices, area_pose)
    ranked: list[tuple[tuple[bool, float, int, int, int, int], ComponentPose]] = []
    for x_steps in range(-_PIPE_CENTER_SEARCH_STEPS, _PIPE_CENTER_SEARCH_STEPS + 1):
        for y_steps in range(-_PIPE_CENTER_SEARCH_STEPS, _PIPE_CENTER_SEARCH_STEPS + 1):
            candidate = ComponentPose(
                center_x=round(
                    centered_pose.center_x + x_steps * _TERRAIN_GRID_INCHES,
                    6,
                ),
                center_y=round(
                    centered_pose.center_y + y_steps * _TERRAIN_GRID_INCHES,
                    6,
                ),
                rotation=centered_pose.rotation,
                local_transform=centered_pose.local_transform,
            )
            component_polygon = _component_world_polygon(
                component_vertices,
                pose=candidate,
                area_pose=area_pose,
                area_vertices=area_vertices,
            )
            outside_area = max(
                0.0,
                component_polygon.area - parent_polygon.intersection(component_polygon).area,
            )
            ranked.append(
                (
                    (
                        outside_area > _GEOMETRY_TOLERANCE,
                        round(outside_area, 12),
                        x_steps * x_steps + y_steps * y_steps,
                        abs(x_steps) + abs(y_steps),
                        x_steps,
                        y_steps,
                    ),
                    candidate,
                )
            )
    ranked.sort(key=lambda row: row[0])
    return ranked[0][1]


def _quantize_terrain_coordinate(value: float) -> float:
    return round(round(value / _TERRAIN_GRID_INCHES) * _TERRAIN_GRID_INCHES, 6)


def _mirror_component_pose(pose: ComponentPose) -> ComponentPose:
    return ComponentPose(
        center_x=round(44.0 - pose.center_x, 6),
        center_y=round(60.0 - pose.center_y, 6),
        rotation=(pose.rotation + 180.0) % 360.0,
        local_transform=pose.local_transform,
    )


def _initial_component_poses(
    layout: dict[str, Any],
    *,
    layout_id: str,
    solved_area_poses: dict[str, AreaPose],
    templates: dict[str, tuple[tuple[float, float], ...]],
    raw_by_id: dict[str, dict[str, Any]],
    archetype_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, ComponentPose], dict[str, str]]:
    source_layout_id = layout["layout_id"]
    partner_by_id: dict[str, str] = {}
    for component_id, raw in raw_by_id.items():
        partner = raw["point_symmetry_partner_component_id"]
        if partner is not None:
            partner_by_id[component_id] = _canonical_stable_id(
                partner,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
    is_meatgrinder = layout["source_pdf_page_number"] in {24, 25, 26}
    if not is_meatgrinder:
        poses: dict[str, ComponentPose] = {}
        for component_id, raw in sorted(raw_by_id.items()):
            area_id = _component_area_id(
                raw,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            archetype = archetype_by_id[raw["archetype_id"]]
            component_vertices = tuple(
                (float(point["x_inches"]), float(point["y_inches"]))
                for point in archetype["rules_footprint_polygon"]
            )
            poses[component_id] = (
                _pipe_component_pose(
                    area_pose=solved_area_poses[area_id],
                    area_vertices=templates[archetype["footprint_template_id"]],
                    component_vertices=component_vertices,
                    local_transform=raw["local_orientation_relative_to_parent"]["local_transform"],
                )
                if raw["archetype_id"] == "dense-long-pipes"
                else _reviewed_component_pose(component_id, raw)
            )
        return poses, partner_by_id
    poses: dict[str, ComponentPose] = {}
    for component_id, raw in sorted(raw_by_id.items()):
        area_id = _component_area_id(
            raw,
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        area_index = int(area_id.rsplit("-", maxsplit=1)[-1])
        if area_index > 8 and component_id in partner_by_id:
            continue
        area_pose = solved_area_poses[area_id]
        archetype = archetype_by_id[raw["archetype_id"]]
        component_vertices = tuple(
            (float(point["x_inches"]), float(point["y_inches"]))
            for point in archetype["rules_footprint_polygon"]
        )
        pose = (
            _pipe_component_pose(
                area_pose=area_pose,
                area_vertices=templates[archetype["footprint_template_id"]],
                component_vertices=component_vertices,
                local_transform=raw["local_orientation_relative_to_parent"]["local_transform"],
            )
            if raw["archetype_id"] == "dense-long-pipes"
            else _reviewed_component_pose(component_id, raw)
        )
        poses[component_id] = pose
        partner_id = partner_by_id.get(component_id)
        if partner_id is not None:
            poses[partner_id] = _mirror_component_pose(pose)
    if set(poses) != set(raw_by_id):
        raise ValueError("Source component point-symmetry inventory is incomplete.")
    return poses, partner_by_id


def _logical_area_groups(
    layout: dict[str, Any],
    *,
    layout_id: str,
) -> tuple[tuple[str, ...], ...]:
    source_layout_id = layout["layout_id"]
    area_ids = tuple(
        sorted(
            _canonical_stable_id(
                raw["area_id"],
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for raw in layout["terrain_areas"]
        )
    )
    neighbors = {area_id: set() for area_id in area_ids}
    for contact in layout["source_contact_pairs"]:
        if contact["kinds"] != ["single"]:
            continue
        first_id, second_id = (
            _canonical_stable_id(
                source_area_id,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for source_area_id in contact["area_ids"]
        )
        neighbors[first_id].add(second_id)
        neighbors[second_id].add(first_id)
    if any(len(area_neighbors) > 1 for area_neighbors in neighbors.values()):
        raise ValueError("Source logical terrain-area groups must contain at most two areas.")
    result: list[tuple[str, ...]] = []
    seen: set[str] = set()
    for area_id in area_ids:
        if area_id in seen:
            continue
        group = tuple(sorted((area_id, *neighbors[area_id])))
        seen.update(group)
        result.append(group)
    if seen != set(area_ids):
        raise ValueError("Source logical terrain-area group inventory is incomplete.")
    return tuple(result)


def _component_inventory_constraint(
    layout: dict[str, Any],
    *,
    layout_id: str,
    templates: dict[str, tuple[tuple[float, float], ...]],
    archetypes: list[dict[str, Any]],
) -> Callable[[dict[str, AreaPose]], tuple[int, float]]:
    source_layout_id = layout["layout_id"]
    raw_by_id = _raw_components_by_id(layout, layout_id=layout_id)
    archetype_by_id = {row["archetype_id"]: row for row in archetypes}
    area_by_id = {
        _canonical_stable_id(
            raw["area_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        ): raw
        for raw in layout["terrain_areas"]
    }
    component_ids_by_area: dict[str, list[str]] = {area_id: [] for area_id in area_by_id}
    component_vertices_by_id: dict[str, tuple[tuple[float, float], ...]] = {}
    source_pose_by_id: dict[str, ComponentPose] = {}
    for component_id, raw in raw_by_id.items():
        area_id = _component_area_id(
            raw,
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        component_ids_by_area[area_id].append(component_id)
        archetype = archetype_by_id[raw["archetype_id"]]
        component_vertices_by_id[component_id] = tuple(
            (float(point["x_inches"]), float(point["y_inches"]))
            for point in archetype["rules_footprint_polygon"]
        )
        if raw["archetype_id"] != "dense-long-pipes":
            source_pose_by_id[component_id] = _reviewed_component_pose(component_id, raw)
    logical_groups = _logical_area_groups(layout, layout_id=layout_id)
    area_polygon_cache: dict[tuple[str, AreaPose], Polygon] = {}
    component_polygon_cache: dict[tuple[str, AreaPose], Polygon] = {}
    group_score_cache: dict[
        tuple[tuple[str, ...], tuple[AreaPose, ...]],
        tuple[int, float],
    ] = {}

    def constraint(poses: dict[str, AreaPose]) -> tuple[int, float]:
        if set(poses) != set(area_by_id):
            raise ValueError("Component constraint terrain-area pose inventory drifted.")
        invalid_count = 0
        outside_area = 0.0
        for group in logical_groups:
            cache_key = (group, tuple(poses[area_id] for area_id in group))
            cached = group_score_cache.get(cache_key)
            if cached is not None:
                group_invalid_count, group_outside_area = cached
                invalid_count += group_invalid_count
                outside_area += group_outside_area
                continue
            area_polygons_inventory: list[Polygon] = []
            for area_id in group:
                area_pose = poses[area_id]
                area_cache_key = (area_id, area_pose)
                area_geometry = area_polygon_cache.get(area_cache_key)
                if area_geometry is None:
                    area_geometry = area_polygon(
                        templates[area_by_id[area_id]["footprint_template_id"]],
                        area_pose,
                    )
                    area_polygon_cache[area_cache_key] = area_geometry
                area_polygons_inventory.append(area_geometry)
            area_polygons = tuple(area_polygons_inventory)
            logical_polygon = area_polygons[0]
            for area_geometry in area_polygons[1:]:
                logical_polygon = logical_polygon.union(area_geometry)
            group_invalid_count = 0
            group_outside_area = 0.0
            for area_id in group:
                area_pose = poses[area_id]
                for component_id in component_ids_by_area[area_id]:
                    raw = raw_by_id[component_id]
                    archetype = archetype_by_id[raw["archetype_id"]]
                    component_cache_key = (component_id, area_pose)
                    component_polygon = component_polygon_cache.get(component_cache_key)
                    if component_polygon is None:
                        area_vertices = templates[archetype["footprint_template_id"]]
                        component_pose = source_pose_by_id.get(component_id)
                        if component_pose is None:
                            component_pose = _pipe_component_pose(
                                area_pose=area_pose,
                                area_vertices=area_vertices,
                                component_vertices=component_vertices_by_id[component_id],
                                local_transform=raw["local_orientation_relative_to_parent"][
                                    "local_transform"
                                ],
                            )
                        component_polygon = _component_world_polygon(
                            component_vertices_by_id[component_id],
                            pose=component_pose,
                            area_pose=area_pose,
                            area_vertices=area_vertices,
                        )
                        component_polygon_cache[component_cache_key] = component_polygon
                    component_outside_area = max(
                        0.0,
                        component_polygon.area
                        - logical_polygon.intersection(component_polygon).area,
                    )
                    if component_outside_area > _GEOMETRY_TOLERANCE:
                        group_invalid_count += 1
                        group_outside_area += component_outside_area
            group_score = (group_invalid_count, round(group_outside_area, 9))
            group_score_cache[cache_key] = group_score
            invalid_count += group_score[0]
            outside_area += group_score[1]
        return invalid_count, round(outside_area, 9)

    return constraint


def _component_contact_pairs(raw_by_id: dict[str, dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    by_area: dict[str, dict[str, list[str]]] = {}
    for component_id, raw in raw_by_id.items():
        by_area.setdefault(raw["parent_area_id"], {}).setdefault(raw["archetype_id"], []).append(
            component_id
        )
    pairs: set[tuple[str, str]] = set()
    for by_archetype in by_area.values():
        hovercraft = by_archetype.get("dense-downed-hovercraft", [])
        tall_crates = by_archetype.get("dense-tall-crates", [])
        industrial = by_archetype.get("dense-industrial-crates", [])
        end_barricades = by_archetype.get("light-end-barricade", [])
        if hovercraft and tall_crates:
            pairs.add(tuple(sorted((hovercraft[0], tall_crates[0]))))
        if industrial or end_barricades:
            if len(industrial) != 1 or len(end_barricades) != 2:
                raise ValueError("Industrial-crate composites require two end barricades.")
            pairs.update(tuple(sorted((industrial[0], end_id))) for end_id in end_barricades)
    return tuple(sorted(pairs))


def _component_geometry(
    component_id: str,
    pose: ComponentPose,
    *,
    raw_by_id: dict[str, dict[str, Any]],
    source_layout_id: str,
    layout_id: str,
    solved_area_poses: dict[str, AreaPose],
    templates: dict[str, tuple[tuple[float, float], ...]],
    archetype_by_id: dict[str, dict[str, Any]],
) -> tuple[Polygon, Polygon]:
    raw = raw_by_id[component_id]
    area_id = _component_area_id(
        raw,
        source_layout_id=source_layout_id,
        layout_id=layout_id,
    )
    archetype = archetype_by_id[raw["archetype_id"]]
    area_vertices = templates[archetype["footprint_template_id"]]
    offset_x, offset_y, local_rotation = component_local_placement(
        component_pose=pose,
        area_pose=solved_area_poses[area_id],
        area_vertices=area_vertices,
    )
    archetype_vertices = tuple(
        (float(point["x_inches"]), float(point["y_inches"]))
        for point in archetype["rules_footprint_polygon"]
    )
    return (
        component_local_polygon(
            archetype_vertices,
            offset_x=offset_x,
            offset_y=offset_y,
            rotation=local_rotation,
            local_transform=pose.local_transform,
        ),
        Polygon(area_vertices),
    )


def _validate_component_contacts(
    *,
    source_layout_id: str,
    layout_id: str,
    poses: dict[str, ComponentPose],
    contact_pairs: tuple[tuple[str, str], ...],
    raw_by_id: dict[str, dict[str, Any]],
    solved_area_poses: dict[str, AreaPose],
    templates: dict[str, tuple[tuple[float, float], ...]],
    archetype_by_id: dict[str, dict[str, Any]],
) -> None:
    for first_id, second_id in contact_pairs:
        first_polygon, _first_parent = _component_geometry(
            first_id,
            poses[first_id],
            raw_by_id=raw_by_id,
            source_layout_id=source_layout_id,
            layout_id=layout_id,
            solved_area_poses=solved_area_poses,
            templates=templates,
            archetype_by_id=archetype_by_id,
        )
        second_polygon, _second_parent = _component_geometry(
            second_id,
            poses[second_id],
            raw_by_id=raw_by_id,
            source_layout_id=source_layout_id,
            layout_id=layout_id,
            solved_area_poses=solved_area_poses,
            templates=templates,
            archetype_by_id=archetype_by_id,
        )
        if first_polygon.distance(second_polygon) > 1e-6:
            raise ValueError(
                f"Composite terrain components have a final gap: {first_id}, {second_id}."
            )


def _component_rows(
    layout: dict[str, Any],
    *,
    layout_id: str,
    solved_area_poses: dict[str, AreaPose],
    templates: dict[str, tuple[tuple[float, float], ...]],
    archetypes: list[dict[str, Any]],
    identities: StableRuntimeIdentities,
) -> tuple[list[dict[str, Any]], tuple[tuple[str, str], ...]]:
    source_layout_id = layout["layout_id"]
    raw_by_id = _raw_components_by_id(layout, layout_id=layout_id)
    archetype_by_id = {row["archetype_id"]: row for row in archetypes}
    poses, _partner_by_id = _initial_component_poses(
        layout,
        layout_id=layout_id,
        solved_area_poses=solved_area_poses,
        templates=templates,
        raw_by_id=raw_by_id,
        archetype_by_id=archetype_by_id,
    )
    contact_pairs = _component_contact_pairs(raw_by_id)
    runtime_component_ids = {
        source_component_id: _runtime_component_id(
            source_component_id,
            source_area_id=_component_area_id(
                raw,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            ),
            identities=identities,
        )
        for source_component_id, raw in raw_by_id.items()
    }
    if len(set(runtime_component_ids.values())) != len(runtime_component_ids):
        raise ValueError("Runtime terrain-component identities must be unique.")
    _validate_component_contacts(
        source_layout_id=source_layout_id,
        layout_id=layout_id,
        poses=poses,
        contact_pairs=contact_pairs,
        raw_by_id=raw_by_id,
        solved_area_poses=solved_area_poses,
        templates=templates,
        archetype_by_id=archetype_by_id,
    )
    rows: list[dict[str, Any]] = []
    for source_component_id, raw in sorted(raw_by_id.items()):
        source_area_id = _component_area_id(
            raw,
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        area_id = identities.area_id(source_area_id)
        area_pose = solved_area_poses[source_area_id]
        archetype = archetype_by_id[raw["archetype_id"]]
        area_vertices = templates[archetype["footprint_template_id"]]
        pose = poses[source_component_id]
        source_center_x, source_center_y = raw["battlefield_center_quantized_0_05_inches"]
        source_rotation = float(raw["battlefield_image_x_axis_rotation_degrees"])
        source_mirror_component = raw["point_symmetry_partner_component_id"]
        source_mirror_component_id = (
            None
            if source_mirror_component is None
            else _canonical_stable_id(
                source_mirror_component,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
        )
        mirror_component_id = (
            None
            if source_mirror_component_id is None
            else runtime_component_ids[source_mirror_component_id]
        )
        page = int(layout["source_pdf_page_number"])
        if page in {24, 25, 26}:
            area_index = int(source_area_id.rsplit("-", maxsplit=1)[-1])
            pose_basis = (
                "accepted_meatgrinder_exemplar_source_pose"
                if area_index <= 8
                else "accepted_meatgrinder_exemplar_exact_point_symmetry"
            )
        elif source_component_id in _REVIEWED_FIXED_COMPONENT_CENTERS:
            pose_basis = "reviewed_source_quantization_containment_adjustment"
        elif raw["archetype_id"] == "dense-long-pipes":
            pose_basis = "reviewed_parent_footprint_centered_pipe_pose"
        else:
            pose_basis = "reviewed_source_quantized_pose"
        offset_x, offset_y, local_rotation = component_local_placement(
            component_pose=pose,
            area_pose=area_pose,
            area_vertices=area_vertices,
        )
        rows.append(
            {
                "component_id": runtime_component_ids[source_component_id],
                "source_component_id": source_component_id,
                "terrain_area_id": area_id,
                "mirror_component_id": mirror_component_id,
                "source_mirror_component_id": source_mirror_component_id,
                "archetype_id": raw["archetype_id"],
                "local_offset_x_inches": offset_x,
                "local_offset_y_inches": offset_y,
                "local_rotation_degrees": local_rotation,
                "local_transform": pose.local_transform,
                "local_transform_basis": raw["local_orientation_relative_to_parent"][
                    "local_transform_basis"
                ],
                "pose_basis": pose_basis,
                "source_battlefield_center_x_inches": float(source_center_x),
                "source_battlefield_center_y_inches": float(source_center_y),
                "source_battlefield_rotation_degrees": source_rotation,
                "runtime_adjustment_x_inches": round(pose.center_x - float(source_center_x), 6),
                "runtime_adjustment_y_inches": round(pose.center_y - float(source_center_y), 6),
                "runtime_rotation_adjustment_degrees": _rotation_adjustment(
                    pose.rotation,
                    source_rotation,
                ),
                "battlefield_center_x_inches": pose.center_x,
                "battlefield_center_y_inches": pose.center_y,
                "battlefield_rotation_degrees": pose.rotation,
                "source_pdf_image_xref": raw["source_xref"],
                "source_pdf_bounds": _pdf_bounds(raw["source_bbox_points"]),
                "source_pdf_affine": _pdf_affine(raw["source_affine_normalized_image_to_points"]),
            }
        )
    runtime_contact_pairs = tuple(
        (runtime_component_ids[first_id], runtime_component_ids[second_id])
        for first_id, second_id in contact_pairs
    )
    return rows, runtime_contact_pairs


def _objective_rows(
    layout: dict[str, Any],
    *,
    layout_id: str,
    solved_area_poses: dict[str, AreaPose],
    templates: dict[str, tuple[tuple[float, float], ...]],
    template_id_by_area: dict[str, str],
    identities: StableRuntimeIdentities,
) -> list[dict[str, Any]]:
    source_layout_id = layout["layout_id"]
    runtime_polygons = {
        area_id: area_polygon(templates[template_id_by_area[area_id]], pose)
        for area_id, pose in solved_area_poses.items()
    }
    role_counts: dict[str, int] = {}
    result: list[dict[str, Any]] = []
    for raw in layout["objectives"]:
        role = raw["role"]
        role_counts[role] = role_counts.get(role, 0) + 1
        x_inches, y_inches = raw["battlefield_center_quantized_0_01_inches"]
        source_ids = tuple(
            _canonical_stable_id(
                area_id,
                source_layout_id=source_layout_id,
                layout_id=layout_id,
            )
            for area_id in raw["nearest_area_ids"]
        )
        distances = raw["distances_to_area_polygons_inches"]
        if distances:
            if len(source_ids) != len(distances):
                raise ValueError("Objective source-distance inventory drifted.")
            source_ids = tuple(
                area_id
                for area_id, distance in zip(source_ids, distances, strict=True)
                if float(distance) <= 0.05 + 1e-9
            )
        elif layout["source_pdf_page_number"] not in {24, 25, 26}:
            raise ValueError("Non-Meatgrinder objectives require source distances.")
        point = Point(float(x_inches), float(y_inches))
        runtime_distances = tuple(
            runtime_polygons[area_id].distance(point) for area_id in source_ids
        )
        if any(distance > 0.05 + 1e-6 for distance in runtime_distances) or (
            runtime_distances and min(runtime_distances) > 1e-6
        ):
            raise ValueError(
                f"Objective {raw['objective_id']} exceeded source-proxy binding tolerance."
            )
        terrain_area_source_ids = source_ids
        source_objective_id = _canonical_stable_id(
            raw["objective_id"],
            source_layout_id=source_layout_id,
            layout_id=layout_id,
        )
        result.append(
            {
                "objective_id": identities.objective_id(source_objective_id),
                "source_objective_id": source_objective_id,
                "name": f"{role.replace('_', ' ').title()} Objective {role_counts[role]}",
                "role": role,
                "x_inches": float(x_inches),
                "y_inches": float(y_inches),
                "terrain_area_ids": [
                    identities.area_id(area_id) for area_id in terrain_area_source_ids
                ],
                "source_symbol_kind": "source_pdf_objective_marker_vector",
            }
        )
    return result


def _source_string_pair(value: object, *, field_name: str) -> tuple[str, str]:
    if (
        type(value) is not list
        or len(value) != 2
        or any(type(item) is not str or not item.strip() for item in value)
    ):
        raise ValueError(f"Event Companion {field_name} must contain two names.")
    return str(value[0]), str(value[1])


def _source_layout_metadata(layout: dict[str, Any], *, source_page: int) -> SourceLayoutMetadata:
    expected_layout_id, force_pair, missions, template_number = _LAYOUT_CONFIG_BY_PAGE[source_page]
    variant = "ABC"[(source_page - 9) % 3]
    force_names = _source_string_pair(
        layout["force_disposition_pair"],
        field_name="canonical force-disposition pair",
    )
    mission_names = _source_string_pair(
        layout["primary_missions"],
        field_name="canonical primary-mission pair",
    )
    if (
        layout["layout_id"] != expected_layout_id
        or layout["variant"] != variant.lower()
        or layout["source_pdf_zero_based_page_index"] != source_page - 1
        or force_names != tuple(_DISPLAY_NAME[force_id] for force_id in force_pair)
        or mission_names
        != tuple(_PRIMARY_MISSION_DISPLAY_NAME[mission_id] for mission_id in missions)
    ):
        raise ValueError("Event Companion canonical layout source metadata drifted.")
    printed = layout["source_printed_left_to_right"]
    if type(printed) is not dict or set(printed) != {
        "force_dispositions",
        "primary_missions",
        "layout_label",
    }:
        raise ValueError("Event Companion printed layout source metadata drifted.")
    printed_force_names = _source_string_pair(
        printed["force_dispositions"],
        field_name="printed force-disposition pair",
    )
    printed_mission_names = _source_string_pair(
        printed["primary_missions"],
        field_name="printed primary-mission pair",
    )
    printed_label = printed["layout_label"]
    expected_printed_title = (
        f"{printed_force_names[0]} vs {printed_force_names[1]} | "
        f"{printed_mission_names[0]} / {printed_mission_names[1]} | {printed_label}"
    )
    if (
        printed_force_names != force_names
        or printed_mission_names != mission_names
        or printed_label != f"Layout {variant}"
        or layout["printed_title"] != expected_printed_title
    ):
        raise ValueError("Event Companion printed layout source metadata drifted.")
    return SourceLayoutMetadata(
        layout_id=expected_layout_id,
        force_pair=force_pair,
        missions=missions,
        template_number=template_number,
        variant=variant,
        force_names=force_names,
        mission_names=mission_names,
    )


def _layout_row(
    layout: dict[str, Any],
    *,
    templates: dict[str, tuple[tuple[float, float], ...]],
    archetypes: list[dict[str, Any]],
    identities: StableRuntimeIdentities,
) -> dict[str, Any]:
    source_page = int(layout["source_pdf_page_number"])
    metadata = _source_layout_metadata(layout, source_page=source_page)
    layout_id = metadata.layout_id
    solved_poses, _area_contact_pairs = solve_area_poses(
        layout,
        layout_id=layout_id,
        templates=templates,
        component_constraint=_component_inventory_constraint(
            layout,
            layout_id=layout_id,
            templates=templates,
            archetypes=archetypes,
        ),
    )
    area_rows = _area_rows(
        layout,
        layout_id=layout_id,
        solved_poses=solved_poses,
        identities=identities,
    )
    template_id_by_area = {row["source_area_id"]: row["footprint_template_id"] for row in area_rows}
    component_rows, component_contact_pairs = _component_rows(
        layout,
        layout_id=layout_id,
        solved_area_poses=solved_poses,
        templates=templates,
        archetypes=archetypes,
        identities=identities,
    )
    objectives = _objective_rows(
        layout,
        layout_id=layout_id,
        solved_area_poses=solved_poses,
        templates=templates,
        template_id_by_area=template_id_by_area,
        identities=identities,
    )
    runtime_area_polygons = {
        source_area_id: area_polygon(
            templates[template_id_by_area[source_area_id]],
            pose,
        )
        for source_area_id, pose in solved_poses.items()
    }
    zones, no_mans_land, territories, attacker_edge, defender_edge = region_rows(
        layout_id,
        metadata.template_number,
    )
    return {
        "layout_id": layout_id,
        "layout_letter": metadata.variant,
        "name": (
            f"{metadata.force_names[0]} vs {metadata.force_names[1]} - "
            f"{metadata.mission_names[0]} / {metadata.mission_names[1]} - "
            f"Layout {metadata.variant}"
        ),
        "source_layout_id": identities.source_layout_id(layout_id),
        "source_page": source_page,
        "force_disposition_pair": list(metadata.force_pair),
        "primary_missions": list(metadata.missions),
        "deployment_zone_template_number": metadata.template_number,
        "attacker_edge": attacker_edge,
        "defender_edge": defender_edge,
        "terrain_areas": area_rows,
        "terrain_components": component_rows,
        "terrain_area_contacts": _area_contact_rows(
            layout,
            layout_id=layout_id,
            identities=identities,
            runtime_polygons=runtime_area_polygons,
        ),
        "terrain_component_contact_pairs": [list(pair) for pair in component_contact_pairs],
        "objectives": objectives,
        "deployment_zones": zones,
        "no_mans_land": no_mans_land,
        "territories": territories,
    }


def build_artifact(
    extraction: dict[str, Any],
    *,
    extraction_sha256: str,
    identities: StableRuntimeIdentities,
) -> dict[str, Any]:
    if extraction_sha256 != EXPECTED_EXTRACTION_SHA256:
        raise ValueError("Event Companion source extraction bytes drifted.")
    source = extraction["source"]
    if (
        source["pdf_filename"] != SOURCE_PDF_FILENAME
        or source["pdf_sha256"] != SOURCE_PDF_SHA256
        or source["included_pages"] != list(range(8, 54))
    ):
        raise ValueError("Event Companion extraction source provenance drifted.")
    if extraction["global_audits"] != {
        **extraction["global_audits"],
        "layout_count": 45,
        "terrain_area_count": 720,
        "component_count": 1349,
        "objective_count": 246,
        "source_contact_pair_count": 224,
        "validation_status": "passed",
    }:
        raise ValueError("Event Companion extraction global audit drifted.")
    templates = _templates(extraction)
    archetypes = _reviewed_archetypes(extraction)
    layouts_by_page = {
        int(layout["source_pdf_page_number"]): layout for layout in extraction["layouts"]
    }
    if tuple(sorted(layouts_by_page)) != tuple(range(9, 54)):
        raise ValueError("Event Companion extraction must contain pages 9 through 53 in order.")
    payload: dict[str, Any] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_pdf_filename": SOURCE_PDF_FILENAME,
        "source_pdf_sha256": SOURCE_PDF_SHA256,
        "source_pages": list(range(8, 54)),
        "source_extraction_payload_sha256": extraction_sha256,
        "source_coordinate_frame": _SOURCE_COORDINATE_FRAME,
        "feature_archetypes": archetypes,
        "layouts": [
            _layout_row(
                layouts_by_page[page],
                templates=templates,
                archetypes=archetypes,
                identities=identities,
            )
            for page in range(9, 54)
        ],
        "package_hash": "",
    }
    payload["package_hash"] = _canonical_hash(payload)
    return payload


def main() -> None:
    args = _parse_args()
    if args.check:
        if not args.output.is_file():
            raise ValueError("Event Companion battlefield artifact is missing.")
        _validate_canonical_check_output(args.output.read_bytes())
    pdf_hash = hashlib.sha256(SOURCE_PDF_PATH.read_bytes()).hexdigest()
    if pdf_hash != SOURCE_PDF_SHA256:
        raise ValueError("Event Companion source PDF hash drifted.")
    extraction_raw = args.extraction.read_bytes()
    extraction_hash = hashlib.sha256(extraction_raw).hexdigest()
    extraction = json.loads(extraction_raw)
    if type(extraction) is not dict:
        raise ValueError("Event Companion source extraction must be a JSON object.")
    stable_identity_raw = STABLE_IDENTITY_PATH.read_bytes()
    stable_identity_payload = json.loads(stable_identity_raw)
    if type(stable_identity_payload) is not dict:
        raise ValueError("Event Companion stable runtime identity map must be a JSON object.")
    identities = _stable_runtime_identities(
        stable_identity_payload,
        payload_sha256=hashlib.sha256(stable_identity_raw).hexdigest(),
    )
    payload = build_artifact(
        extraction,
        extraction_sha256=extraction_hash,
        identities=identities,
    )
    rendered = json.dumps(payload, indent=2) + "\n"
    if args.check:
        if args.output.read_text(encoding="utf-8") != rendered:
            raise ValueError("Event Companion battlefield artifact is stale.")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rendered.encode())


if __name__ == "__main__":
    main()
