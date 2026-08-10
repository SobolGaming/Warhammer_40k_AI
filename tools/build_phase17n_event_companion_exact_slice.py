from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

EXPECTED_EXTRACTION_HASH = "8d0082df6516b8927cf8666042a9a679863b81205d41377a85c1823cf8e35b30"
ARTIFACT_SCHEMA = "core-v2-phase17n-event-companion-exact-slice-v1"
SOURCE_PDF_SHA256 = "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-1-2026-07"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXTRACTION_PATH = (
    REPOSITORY_ROOT
    / "data/source_audits/event_companion_2026_06"
    / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
)
DEFAULT_OUTPUT_PATH = (
    REPOSITORY_ROOT
    / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
    / "event_companion_layouts_2026_06/artifacts"
    / "purge-the-foe-vs-purge-the-foe-meatgrinder.json"
)
SOURCE_PDF_PATH = (
    REPOSITORY_ROOT
    / "docs/source_rules"
    / "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
)

# Canonical vertex zero for each reviewed terrain-area template. Keeping this
# source-local table makes the artifact builder bootstrappable: it does not import
# the runtime provider whose eager validation consumes the artifact being rebuilt.
_TEMPLATE_ANCHOR_POINTS = {
    "FOOTPRINT_6X4": (-3.25, 2.25),
    "FOOTPRINT_10X2_5": (-5.0, 1.2),
    "FOOTPRINT_6X2": (-3.05, 1.15),
    "FOOTPRINT_7X11_5": (-3.8, 5.75),
    "FOOTPRINT_8X11_5_POLYGON": (-5.5, 4.0),
}

_ARCHETYPES = {
    5462: (
        "dense-downed-hovercraft",
        "Downed Hovercraft",
        "dense_solid",
        "battlefield_debris_and_statuary",
        "dense",
        None,
        "FOOTPRINT_6X4",
        3.0,
        1.0,
        3.5,
        0,
    ),
    5464: (
        "light-long-barricade",
        "Long Light Barricade",
        "light_solid",
        "battlefield_debris_and_statuary",
        "light",
        None,
        "FOOTPRINT_6X2",
        4.0,
        0.45,
        2.0,
        0,
    ),
    5466: (
        "dense-industrial-crates",
        "Industrial Crate Stack",
        "dense_solid",
        "battlefield_debris_and_statuary",
        "dense",
        None,
        "FOOTPRINT_10X2_5",
        2.2,
        1.0,
        3.5,
        0,
    ),
    5468: (
        "light-end-barricade",
        "Light End Barricade",
        "light_solid",
        "battlefield_debris_and_statuary",
        "light",
        None,
        "FOOTPRINT_10X2_5",
        0.8,
        0.2,
        2.0,
        0,
    ),
    5470: (
        "ruins-cd",
        "Ruin CD",
        "ruin",
        "ruins",
        "dense",
        "CD",
        "FOOTPRINT_7X11_5",
        1.0,
        3.0,
        0.0,
        2,
    ),
    5472: (
        "ruins-gh",
        "Ruin GH",
        "ruin",
        "ruins",
        "dense",
        "GH",
        "FOOTPRINT_7X11_5",
        3.0,
        1.0,
        0.0,
        2,
    ),
    5474: (
        "ruins-ef",
        "Ruin EF",
        "ruin",
        "ruins",
        "dense",
        "EF",
        "FOOTPRINT_7X11_5",
        3.0,
        2.0,
        0.0,
        3,
    ),
    5476: (
        "ruins-ab",
        "Ruin AB",
        "ruin",
        "ruins",
        "dense",
        "AB",
        "FOOTPRINT_8X11_5_POLYGON",
        1.2,
        1.6,
        0.0,
        3,
    ),
    5478: (
        "light-corner-ab",
        "Light Corner Piece AB",
        "light_solid",
        "battlefield_debris_and_statuary",
        "light",
        None,
        "FOOTPRINT_8X11_5_POLYGON",
        0.7,
        0.7,
        2.0,
        0,
    ),
    5480: (
        "light-corner-cd",
        "Light Corner Piece CD",
        "light_solid",
        "battlefield_debris_and_statuary",
        "light",
        None,
        "FOOTPRINT_6X4",
        1.0,
        0.5,
        2.0,
        0,
    ),
    5482: (
        "light-corner-ef",
        "Light Corner Piece EF",
        "light_solid",
        "battlefield_debris_and_statuary",
        "light",
        None,
        "FOOTPRINT_7X11_5",
        0.2,
        0.6,
        2.0,
        0,
    ),
    5484: (
        "light-corner-gh",
        "Light Corner Piece GH",
        "light_solid",
        "battlefield_debris_and_statuary",
        "light",
        None,
        "FOOTPRINT_6X4",
        1.2,
        0.7,
        2.0,
        0,
    ),
    5486: (
        "dense-tall-crates",
        "Tall Crate Stack",
        "dense_solid",
        "battlefield_debris_and_statuary",
        "dense",
        None,
        "FOOTPRINT_6X4",
        1.0,
        1.2,
        3.5,
        0,
    ),
    5488: (
        "dense-long-pipes",
        "Long Dense Pipe Stack",
        "dense_solid",
        "battlefield_debris_and_statuary",
        "dense",
        None,
        "FOOTPRINT_6X2",
        4.0,
        0.45,
        3.5,
        0,
    ),
}

_OBJECTIVE_AREA_INDICES = {
    "a": (3, 14, 7, 10, 1, 16),
    "b": (3, 14, 9, 8, 4, 13),
    "c": (3, 14, 7, 10, 1, 16),
}

_ACCEPTED_EXTRACTION_STATUS = "reviewed_source_registration_ready_for_exact_runtime"
_ACCEPTED_POSE_STATUS = "accepted_for_exact_runtime"
_SUPERSEDED_ESTIMATE_STATUS = "superseded_by_accepted_pose_review"
_RASTER_REVIEW_METHOD = "source_page_raster_overlay_registration_review"
_VECTOR_REVIEW_METHOD = "pdf_vector_edge_correction_plus_source_page_raster_overlay_review"
_REVIEW_RESULT = "canonical_template_outline_aligned_to_source_page_terrain_area"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the reviewed Phase 17N Purge/Meatgrinder exact-slice artifact."
    )
    parser.add_argument(
        "extraction",
        type=Path,
        nargs="?",
        default=DEFAULT_EXTRACTION_PATH,
        help="Reviewed PDF extraction JSON (defaults to the committed source audit).",
    )
    parser.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=DEFAULT_OUTPUT_PATH,
        help="Generated exact-slice JSON (defaults to the committed package artifact).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed output differs; never write in check mode.",
    )
    return parser.parse_args()


def _canonical_hash(
    payload: dict[str, Any],
    *,
    blank_field: str | None = None,
    omitted_field: str | None = None,
) -> str:
    if (blank_field is None) == (omitted_field is None):
        raise ValueError("Canonical hashing requires exactly one excluded-field policy.")
    candidate = dict(payload)
    if blank_field is not None:
        candidate[blank_field] = ""
    else:
        assert omitted_field is not None
        del candidate[omitted_field]
    encoded = json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_exact_keys(
    *,
    field_name: str,
    value: object,
    expected_keys: frozenset[str],
) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError(f"{field_name} must be an object.")
    row = value
    if set(row) != expected_keys:
        raise ValueError(f"{field_name} fields drifted.")
    return row


def _finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise ValueError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field_name} must be finite.")
    return number


def _accepted_pose_review(
    *,
    layout: dict[str, Any],
    raw: dict[str, Any],
    source_pdf_sha256: str,
) -> dict[str, Any]:
    area_id = raw["terrain_area_id"]
    estimate = raw["template_pose_initial_estimate"]
    if estimate["status"] != _SUPERSEDED_ESTIMATE_STATUS:
        raise ValueError(
            f"{area_id} initial pose estimate must be superseded by an accepted review."
        )
    review = _require_exact_keys(
        field_name=f"{area_id} accepted_pose_review",
        value=raw.get("accepted_pose_review"),
        expected_keys=frozenset(
            {
                "accepted_anchor_inches",
                "accepted_confidence",
                "accepted_rotation_degrees",
                "method",
                "rendered_overlay_authoritative",
                "review_result",
                "reviewed_against_source_pdf_page",
                "reviewed_on",
                "reviewed_source_pdf_sha256",
                "source_pdf_vector_path_index_zero_based",
                "source_pdf_vector_path_item_index_zero_based",
                "status",
            }
        ),
    )
    if review["status"] != _ACCEPTED_POSE_STATUS:
        raise ValueError(f"{area_id} pose review is not accepted for exact runtime use.")
    if review["accepted_confidence"] not in {"high", "medium"}:
        raise ValueError(f"{area_id} accepted pose review confidence is unsupported.")
    if review["review_result"] != _REVIEW_RESULT:
        raise ValueError(f"{area_id} accepted pose review result is unsupported.")
    if review["rendered_overlay_authoritative"] is not False:
        raise ValueError(f"{area_id} review overlay must remain non-authoritative.")
    if review["reviewed_against_source_pdf_page"] != layout["source_pdf_page_number"]:
        raise ValueError(f"{area_id} accepted pose review page drifted.")
    if review["reviewed_source_pdf_sha256"] != source_pdf_sha256:
        raise ValueError(f"{area_id} accepted pose review source hash drifted.")
    if review["reviewed_on"] != "2026-08-09":
        raise ValueError(f"{area_id} accepted pose review date drifted.")
    anchor = review["accepted_anchor_inches"]
    if type(anchor) is not list or len(anchor) != 2:
        raise ValueError(f"{area_id} accepted pose review anchor is invalid.")
    accepted_pose = (
        _finite_number(f"{area_id} accepted anchor x", anchor[0]),
        _finite_number(f"{area_id} accepted anchor y", anchor[1]),
        _finite_number(
            f"{area_id} accepted rotation",
            review["accepted_rotation_degrees"],
        ),
    )
    estimate_anchor = estimate["first_template_vertex_anchor_inches"]
    estimate_pose = (
        float(estimate_anchor[0]),
        float(estimate_anchor[1]),
        float(estimate["rotation_degrees"]),
    )
    method = review["method"]
    vector_path = (
        review["source_pdf_vector_path_index_zero_based"],
        review["source_pdf_vector_path_item_index_zero_based"],
    )
    if method == _RASTER_REVIEW_METHOD:
        if accepted_pose != estimate_pose:
            raise ValueError(f"{area_id} raster-reviewed pose must pin the reviewed estimate.")
        if vector_path != (None, None):
            raise ValueError(f"{area_id} raster-reviewed pose must not claim vector correction.")
    elif method == _VECTOR_REVIEW_METHOD:
        if accepted_pose == estimate_pose:
            raise ValueError(f"{area_id} vector-corrected pose must differ from its estimate.")
        if any(type(value) is not int or value < 0 for value in vector_path):
            raise ValueError(f"{area_id} vector-corrected pose requires exact path indices.")
    else:
        raise ValueError(f"{area_id} accepted pose review method is unsupported.")
    return review


def _validate_extraction_pose_reviews(extraction: dict[str, Any]) -> None:
    if extraction.get("status") != _ACCEPTED_EXTRACTION_STATUS:
        raise ValueError("Phase 17N extraction is not accepted for exact runtime use.")
    source_pdf_sha256 = extraction["source"]["sha256"]
    method_counts = {_RASTER_REVIEW_METHOD: 0, _VECTOR_REVIEW_METHOD: 0}
    reviewed_area_ids: set[str] = set()
    for layout in extraction["layouts"]:
        for raw in layout["terrain_areas"]:
            area_id = raw["terrain_area_id"]
            if area_id in reviewed_area_ids:
                raise ValueError("Phase 17N accepted pose reviews duplicate an area ID.")
            reviewed_area_ids.add(area_id)
            review = _accepted_pose_review(
                layout=layout,
                raw=raw,
                source_pdf_sha256=source_pdf_sha256,
            )
            method_counts[review["method"]] += 1
    summary = extraction.get("placement_pose_review")
    if summary != {
        "accepted_area_count": 48,
        "rendered_overlays_authoritative": False,
        "reviewed_on": "2026-08-09",
        "reviewed_source_pdf_pages": [24, 25, 26],
        "reviewed_source_pdf_sha256": source_pdf_sha256,
        "source_page_raster_overlay_registration_review_count": 42,
        "status": _ACCEPTED_POSE_STATUS,
        "vector_edge_correction_plus_raster_review_count": 6,
    }:
        raise ValueError("Phase 17N extraction pose-review summary drifted.")
    if len(reviewed_area_ids) != 48 or method_counts != {
        _RASTER_REVIEW_METHOD: 42,
        _VECTOR_REVIEW_METHOD: 6,
    }:
        raise ValueError("Phase 17N extraction accepted pose-review counts drifted.")


def _rectangle(width: float, depth: float) -> list[dict[str, float]]:
    return [
        {"x_inches": -width / 2.0, "y_inches": -depth / 2.0},
        {"x_inches": width / 2.0, "y_inches": -depth / 2.0},
        {"x_inches": width / 2.0, "y_inches": depth / 2.0},
        {"x_inches": -width / 2.0, "y_inches": depth / 2.0},
    ]


def _l_shape(
    width: float,
    depth: float,
    *,
    right_top: bool = False,
) -> list[dict[str, float]]:
    arm_thickness = min(width, depth) * 0.35
    if right_top:
        return [
            {"x_inches": -width / 2.0, "y_inches": -depth / 2.0},
            {
                "x_inches": -width / 2.0,
                "y_inches": (-depth / 2.0) + arm_thickness,
            },
            {
                "x_inches": (width / 2.0) - arm_thickness,
                "y_inches": (-depth / 2.0) + arm_thickness,
            },
            {"x_inches": (width / 2.0) - arm_thickness, "y_inches": depth / 2.0},
            {"x_inches": width / 2.0, "y_inches": depth / 2.0},
            {"x_inches": width / 2.0, "y_inches": -depth / 2.0},
        ]
    return [
        {"x_inches": -width / 2.0, "y_inches": -depth / 2.0},
        {"x_inches": -width / 2.0, "y_inches": depth / 2.0},
        {"x_inches": width / 2.0, "y_inches": depth / 2.0},
        {"x_inches": width / 2.0, "y_inches": (depth / 2.0) - arm_thickness},
        {
            "x_inches": (-width / 2.0) + arm_thickness,
            "y_inches": (depth / 2.0) - arm_thickness,
        },
        {"x_inches": (-width / 2.0) + arm_thickness, "y_inches": -depth / 2.0},
    ]


def _ruin_parts(
    *, width: float, depth: float, floor_count: int
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    walls: list[dict[str, Any]] = []
    floors: list[dict[str, Any]] = []
    for floor_index in range(floor_count):
        bottom_z = float(floor_index * 3)
        floor_name = ("ground", "first", "second")[floor_index]
        walls.extend(
            (
                {
                    "wall_id": f"{floor_name}-long-solid-wall",
                    "center_x_inches": 0.0,
                    "center_y_inches": (depth / 2.0) - 0.07,
                    "bottom_z_inches": bottom_z,
                    "width_inches": width - 0.02,
                    "depth_inches": 0.12,
                    "height_inches": 2.0 if floor_index == floor_count - 1 else 3.0,
                    "rotation_degrees": 0.0,
                },
                {
                    "wall_id": f"{floor_name}-short-solid-wall",
                    "center_x_inches": (-width / 2.0) + 0.07,
                    "center_y_inches": 0.0,
                    "bottom_z_inches": bottom_z,
                    "width_inches": depth - 0.02,
                    "depth_inches": 0.12,
                    "height_inches": 2.0 if floor_index == floor_count - 1 else 3.0,
                    "rotation_degrees": 90.0,
                },
            )
        )
        floors.append(
            {
                "floor_id": f"{floor_name}-floor",
                "center_x_inches": 0.0,
                "center_y_inches": 0.0,
                "bottom_z_inches": bottom_z,
                "width_inches": max(0.2, width - 0.12),
                "depth_inches": max(0.2, depth - 0.12),
                "thickness_inches": 0.12,
                "rotation_degrees": 0.0,
            }
        )
    return walls, floors


def _solid_parts(*, width: float, depth: float, height: float) -> list[dict[str, Any]]:
    return [
        {
            "wall_id": "solid-body",
            "center_x_inches": 0.0,
            "center_y_inches": 0.0,
            "bottom_z_inches": 0.0,
            "width_inches": max(0.02, width - 0.02),
            "depth_inches": max(0.02, depth - 0.02),
            "height_inches": height,
            "rotation_degrees": 0.0,
        }
    ]


def _corner_parts(
    *,
    width: float,
    depth: float,
    height: float,
    right_top: bool = False,
) -> list[dict[str, Any]]:
    arm_thickness = min(width, depth) * 0.35
    horizontal_y = (
        (-depth / 2.0) + (arm_thickness / 2.0)
        if right_top
        else (depth / 2.0) - (arm_thickness / 2.0)
    )
    vertical_x = (
        (width / 2.0) - (arm_thickness / 2.0)
        if right_top
        else (-width / 2.0) + (arm_thickness / 2.0)
    )
    return [
        {
            "wall_id": "long-solid-arm",
            "center_x_inches": 0.0,
            "center_y_inches": horizontal_y,
            "bottom_z_inches": 0.0,
            "width_inches": width - 0.02,
            "depth_inches": arm_thickness - 0.02,
            "height_inches": height,
            "rotation_degrees": 0.0,
        },
        {
            "wall_id": "short-solid-arm",
            "center_x_inches": vertical_x,
            "center_y_inches": 0.0,
            "bottom_z_inches": 0.0,
            "width_inches": depth - 0.02,
            "depth_inches": arm_thickness - 0.02,
            "height_inches": height,
            "rotation_degrees": 90.0,
        },
    ]


def _source_asset(raw: dict[str, Any]) -> dict[str, Any]:
    soft_mask = raw["soft_mask"]
    return {
        "source_pdf_image_xref": raw["xref"],
        "image_sha256": raw["sha256"],
        "pixel_width": raw["pixel_width"],
        "pixel_height": raw["pixel_height"],
        "soft_mask_xref": None if soft_mask is None else soft_mask["xref"],
        "soft_mask_sha256": None if soft_mask is None else soft_mask["sha256"],
    }


def _archetypes(extraction: dict[str, Any]) -> list[dict[str, Any]]:
    source_assets = extraction["source_image_assets_by_xref"]
    rows: list[dict[str, Any]] = []
    for primary_xref, config in _ARCHETYPES.items():
        (
            archetype_id,
            name,
            model_kind,
            feature_kind,
            classification,
            label,
            footprint_template_id,
            width,
            depth,
            height,
            floor_count,
        ) = config
        if model_kind == "ruin":
            walls, floors = _ruin_parts(
                width=width,
                depth=depth,
                floor_count=floor_count,
            )
        elif archetype_id.startswith("light-corner-"):
            walls, floors = (
                _corner_parts(
                    width=width,
                    depth=depth,
                    height=height,
                    right_top=archetype_id == "light-corner-cd",
                ),
                [],
            )
        else:
            walls, floors = _solid_parts(width=width, depth=depth, height=height), []
        xrefs = (primary_xref, 5675) if primary_xref == 5486 else (primary_xref,)
        rows.append(
            {
                "archetype_id": archetype_id,
                "name": name,
                "source_assets": [_source_asset(source_assets[str(xref)]) for xref in xrefs],
                "source_component_label": label,
                "model_kind": model_kind,
                "feature_kind": feature_kind,
                "classification": classification,
                "footprint_template_id": footprint_template_id,
                "rules_footprint_polygon": (
                    _l_shape(
                        width,
                        depth,
                        right_top=archetype_id == "light-corner-cd",
                    )
                    if archetype_id.startswith("light-corner-")
                    else _rectangle(width, depth)
                ),
                "walls": walls,
                "floors": floors,
                "modeling_basis": _archetype_modeling_basis(model_kind),
            }
        )
    return rows


def _archetype_modeling_basis(model_kind: str) -> str:
    if model_kind == "ruin":
        return (
            "PDF pages 24-26 provide component identity and source-image pose. The user "
            "supplied the ruin category, three-inch floor spacing, solid three-inch walls "
            "below every upper floor, and approximately two-inch top-floor walls. Compact "
            "primitive dimensions and the reviewed AB/EF three-floor versus CD/GH two-floor "
            "assignment are engine modeling assumptions, not PDF measurements. Raster art "
            "remains non-authoritative."
        )
    if model_kind == "light_solid":
        return (
            "PDF pages 24-26 provide component identity and source-image pose; the PDF key "
            "and user instruction identify Light terrain, and the user supplied its "
            "approximately two-inch height. The compact rules polygon and solid primitives "
            "are reviewed engine models, not PDF measurements. Raster art remains "
            "non-authoritative."
        )
    if model_kind == "dense_solid":
        return (
            "PDF pages 24-26 provide component identity and source-image pose; the PDF key "
            "and user instruction identify Dense non-ruin terrain. The compact rules polygon, "
            "solid primitive dimensions, and 3.5-inch height are reviewed engine modeling "
            "assumptions, not PDF measurements. Raster art remains non-authoritative."
        )
    raise ValueError("Unsupported Event Companion terrain archetype model kind.")


def _pdf_bounds(source_image: dict[str, Any]) -> dict[str, float]:
    x0, y0, x1, y1 = source_image["pdf_page_bbox_points"]
    return {
        "x0_points": x0,
        "y0_points": y0,
        "x1_points": x1,
        "y1_points": y1,
    }


def _pdf_affine(source_image: dict[str, Any]) -> dict[str, float]:
    a, b, c, d, e, f = source_image["pdf_page_affine_normalized_image_to_points"]
    return {"a": a, "b": b, "c": c, "d": d, "e": e, "f": f}


def _source_image_is_orientation_reversing(source_image: dict[str, Any]) -> bool:
    a, b, c, d, _, _ = source_image["pdf_page_affine_normalized_image_to_points"]
    determinant = (a * d) - (b * c)
    if math.isclose(determinant, 0.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Phase 17N terrain-area source affine must be invertible.")
    orientation_reversing = determinant < 0.0
    if source_image["mirrored_in_image_y_up_to_battlefield_frame"] is not orientation_reversing:
        raise ValueError("Phase 17N terrain-area source affine mirror flag drifted.")
    return orientation_reversing


def _area_row(
    layout: dict[str, Any],
    raw: dict[str, Any],
    template_anchor_points: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    index = int(raw["terrain_area_id"].rsplit("-", maxsplit=1)[-1])
    source_asset = raw["source_image_asset"]
    components = [
        component
        for component in layout["terrain_components"]
        if component["terrain_area_id"] == raw["terrain_area_id"]
    ]
    classifications = {component["terrain_density_color"] for component in components}
    review = raw["accepted_pose_review"]
    reviewed_anchor_x, reviewed_anchor_y = review["accepted_anchor_inches"]
    rotation_degrees = review["accepted_rotation_degrees"]
    vector_path = (
        None
        if review["method"] == _RASTER_REVIEW_METHOD
        else (
            review["source_pdf_vector_path_index_zero_based"],
            review["source_pdf_vector_path_item_index_zero_based"],
        )
    )
    orientation_reversing = _source_image_is_orientation_reversing(raw["source_image"])
    anchor_x = reviewed_anchor_x
    anchor_y = reviewed_anchor_y
    if orientation_reversing:
        # Terrain-area MIRROR_Y_AXIS preserves the stored vertex-zero anchor. Shift that
        # anchor by the rotated distance to its reflected counterpart so the resulting
        # polygon is reflected about the reviewed template origin without moving its
        # source-registered footprint extents.
        template_anchor_x, _ = template_anchor_points[raw["footprint_template_id"]]
        radians = math.radians(rotation_degrees)
        anchor_delta = -2.0 * template_anchor_x
        anchor_x += anchor_delta * math.cos(radians)
        anchor_y += anchor_delta * math.sin(radians)
        anchor_x = round(anchor_x, 9)
        anchor_y = round(anchor_y, 9)
    pose_basis = (
        "reviewed_pdf_vector_path_reversed_long_edge"
        if vector_path is not None
        else "reviewed_pdf_raster_template_registration"
    )
    if orientation_reversing:
        pose_basis = f"{pose_basis}_with_source_affine_reflection"
    return {
        "area_id": raw["terrain_area_id"],
        "footprint_template_id": raw["footprint_template_id"],
        "classification": next(iter(classifications)) if len(classifications) == 1 else "mixed",
        "anchor_x_inches": anchor_x,
        "anchor_y_inches": anchor_y,
        "rotation_degrees": rotation_degrees,
        "local_transform": "mirror_y_axis" if orientation_reversing else "identity",
        "pose_basis": pose_basis,
        "source_pdf_vector_path_index_zero_based": (
            vector_path[0] if vector_path is not None else None
        ),
        "source_pdf_vector_path_item_index_zero_based": (
            vector_path[1] if vector_path is not None else None
        ),
        "mirror_area_id": raw["terrain_area_id"].rsplit("-", maxsplit=1)[0] + f"-{17 - index:02d}",
        "source_pdf_image_xref": raw["source_image"]["xref"],
        "source_image_sha256": source_asset["sha256"],
        "source_soft_mask_sha256": source_asset["soft_mask"]["sha256"],
        "source_pdf_bounds": _pdf_bounds(raw["source_image"]),
        "source_pdf_affine": _pdf_affine(raw["source_image"]),
    }


def _component_row(
    *,
    raw: dict[str, Any],
    area_by_id: dict[str, dict[str, Any]],
    template_anchor_points: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    area = area_by_id[raw["terrain_area_id"]]
    primary_xref = 5486 if raw["source_image"]["xref"] == 5675 else raw["source_image"]["xref"]
    archetype_id = _ARCHETYPES[primary_xref][0]
    template_anchor_x, template_anchor_y = template_anchor_points[area["footprint_template_id"]]
    area_radians = math.radians(area["rotation_degrees"])
    area_cosine = math.cos(area_radians)
    area_sine = math.sin(area_radians)
    rotated_anchor_x = (template_anchor_x * area_cosine) - (template_anchor_y * area_sine)
    rotated_anchor_y = (template_anchor_x * area_sine) + (template_anchor_y * area_cosine)
    area_center_x = area["anchor_x_inches"] - rotated_anchor_x
    area_center_y = area["anchor_y_inches"] - rotated_anchor_y
    center_x, center_y = raw["source_image"]["battlefield_image_center_inches"]
    battlefield_delta_x = center_x - area_center_x
    battlefield_delta_y = center_y - area_center_y
    transformed_local_x = (battlefield_delta_x * area_cosine) + (battlefield_delta_y * area_sine)
    local_y = (-battlefield_delta_x * area_sine) + (battlefield_delta_y * area_cosine)
    local_x = (
        (2.0 * template_anchor_x) - transformed_local_x
        if area["local_transform"] == "mirror_y_axis"
        else transformed_local_x
    )
    affine = raw["parent_image_local_affine_normalized_component_to_normalized_parent"]
    component_mirrored = ((affine[0] * affine[3]) - (affine[1] * affine[2])) < 0.0
    area_mirrored = area["local_transform"] == "mirror_y_axis"
    area_rotation = area["rotation_degrees"]
    battlefield_rotation = raw["source_image"]["battlefield_image_x_axis_rotation_degrees"]
    inner_rotation = (
        180.0 + area_rotation - battlefield_rotation
        if area_mirrored
        else battlefield_rotation - area_rotation
    )
    local_rotation = inner_rotation - (180.0 if component_mirrored else 0.0)
    return {
        "component_id": raw["component_id"],
        "terrain_area_id": raw["terrain_area_id"],
        "archetype_id": archetype_id,
        "local_offset_x_inches": round(local_x, 6),
        "local_offset_y_inches": round(local_y, 6),
        "local_rotation_degrees": round(local_rotation % 360.0, 6),
        "local_transform": "mirror_y_axis" if component_mirrored else "identity",
        "battlefield_center_x_inches": center_x,
        "battlefield_center_y_inches": center_y,
        "battlefield_rotation_degrees": battlefield_rotation,
        "source_pdf_image_xref": raw["source_image"]["xref"],
        "source_pdf_bounds": _pdf_bounds(raw["source_image"]),
        "source_pdf_affine": _pdf_affine(raw["source_image"]),
    }


def _shape(
    *,
    shape_id: str,
    role: str,
    owner_role: str | None,
    polygons: list[list[list[float]]],
    source_kind: str,
) -> dict[str, Any]:
    return {
        "shape_id": shape_id,
        "role": role,
        "owner_role": owner_role,
        "polygons": [
            [{"x_inches": float(point[0]), "y_inches": float(point[1])} for point in polygon]
            for polygon in polygons
        ],
        "source_kind": source_kind,
    }


def _layout_row(
    *,
    layout: dict[str, Any],
    template_anchor_points: dict[str, tuple[float, float]],
) -> dict[str, Any]:
    layout_id = layout["layout_id"]
    area_rows = [_area_row(layout, raw, template_anchor_points) for raw in layout["terrain_areas"]]
    area_by_id = {area["area_id"]: area for area in area_rows}
    component_rows = [
        _component_row(
            raw=raw,
            area_by_id=area_by_id,
            template_anchor_points=template_anchor_points,
        )
        for raw in layout["terrain_components"]
    ]
    objective_area_indices = _OBJECTIVE_AREA_INDICES[layout["variant"]]
    objectives = []
    role_counts: dict[str, int] = {}
    for raw, area_index in zip(layout["objectives"], objective_area_indices, strict=True):
        role_counts[raw["role"]] = role_counts.get(raw["role"], 0) + 1
        ordinal = role_counts[raw["role"]]
        objectives.append(
            {
                "objective_id": raw["objective_id"],
                "name": f"{raw['role'].replace('_', ' ').title()} Objective {ordinal}",
                "role": raw["role"],
                "x_inches": raw["x_inches"],
                "y_inches": raw["y_inches"],
                "terrain_area_ids": [f"{layout_id}-terrain-area-{area_index:02d}"],
                "source_symbol_kind": raw["coordinate_basis"],
            }
        )
    regions = layout["battlefield_regions"]
    deployment_zones = [
        _shape(
            shape_id=f"{layout_id}-{role}",
            role=role,
            owner_role=role,
            polygons=regions[f"{role}_deployment"]["polygons"],
            source_kind=regions["deployment_template_id"],
        )
        for role in ("attacker", "defender")
    ]
    territories = [
        _shape(
            shape_id=f"{layout_id}-{raw['role']}",
            role=raw["role"],
            owner_role=raw["role"].removesuffix("_territory"),
            polygons=raw["polygons"],
            source_kind="source_page_territory_boundary",
        )
        for raw in regions["territories"]
    ]
    return {
        "layout_id": layout_id,
        "layout_letter": layout["variant"].upper(),
        "name": (
            f"Purge the Foe vs Purge the Foe - Meatgrinder - Layout {layout['variant'].upper()}"
        ),
        "source_layout_id": (
            "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_"
            f"meatgrinder_layout_{layout['variant']}"
        ),
        "source_page": layout["source_pdf_page_number"],
        "deployment_zone_template_number": int(
            regions["deployment_template_id"].split("-layout-")[1].split("-", maxsplit=1)[0]
        ),
        "attacker_edge": regions["attacker_edge"],
        "defender_edge": regions["defender_edge"],
        "terrain_areas": area_rows,
        "terrain_components": component_rows,
        "objectives": objectives,
        "deployment_zones": deployment_zones,
        "no_mans_land": _shape(
            shape_id=f"{layout_id}-no-mans-land",
            role="no_mans_land",
            owner_role=None,
            polygons=regions["no_mans_land"]["polygons"],
            source_kind="source_page_complement_of_deployment_zones",
        ),
        "territories": territories,
    }


def build_artifact(extraction: dict[str, Any]) -> dict[str, Any]:
    _validate_extraction_pose_reviews(extraction)
    if extraction["canonical_payload_sha256_excluding_this_field"] != EXPECTED_EXTRACTION_HASH:
        raise ValueError("Unexpected Phase 17N PDF extraction hash.")
    if (
        _canonical_hash(
            extraction,
            omitted_field="canonical_payload_sha256_excluding_this_field",
        )
        != EXPECTED_EXTRACTION_HASH
    ):
        raise ValueError("Phase 17N PDF extraction payload is stale.")
    template_anchor_points = _TEMPLATE_ANCHOR_POINTS
    background = extraction["layouts"][0]["battlefield_background_image"]
    bounds = background["source_image"]["pdf_page_bbox_points"]
    payload: dict[str, Any] = {
        "artifact_schema": ARTIFACT_SCHEMA,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_pdf_filename": Path(extraction["source"]["relative_path"]).name,
        "source_pdf_sha256": extraction["source"]["sha256"],
        "source_pages": extraction["source"]["authoritative_pages"],
        "source_extraction_payload_sha256": extraction[
            "canonical_payload_sha256_excluding_this_field"
        ],
        "source_coordinate_frame": {
            "pdf_background_image_xref": background["source_image"]["xref"],
            "pdf_background_image_sha256": background["source_image_asset"]["sha256"],
            "pdf_background_bounds": {
                "x0_points": bounds[0],
                "y0_points": bounds[1],
                "x1_points": bounds[2],
                "y1_points": bounds[3],
            },
            "battlefield_width_inches": 44.0,
            "battlefield_depth_inches": 60.0,
            "battlefield_origin": "bottom_left",
            "battlefield_orientation": "x_right_along_44_inch_edge_y_up_along_60_inch_edge",
            "coordinate_precision_decimal_places": 6,
        },
        "player_force_disposition_id": "purge-the-foe",
        "opponent_force_disposition_id": "purge-the-foe",
        "primary_mission_id": "primary-meatgrinder",
        "feature_archetypes": _archetypes(extraction),
        "layouts": [
            _layout_row(
                layout=layout,
                template_anchor_points=template_anchor_points,
            )
            for layout in extraction["layouts"]
        ],
        "package_hash": "",
    }
    payload["package_hash"] = _canonical_hash(payload, blank_field="package_hash")
    return payload


def main() -> None:
    args = _parse_args()
    if hashlib.sha256(SOURCE_PDF_PATH.read_bytes()).hexdigest() != SOURCE_PDF_SHA256:
        raise ValueError("Phase 17N source PDF hash drifted.")
    extraction = json.loads(args.extraction.read_text(encoding="utf-8"))
    if extraction["source"]["sha256"] != SOURCE_PDF_SHA256:
        raise ValueError("Phase 17N source PDF hash drifted.")
    payload = build_artifact(extraction)
    rendered_text = json.dumps(payload, indent=2) + "\n"
    if args.check:
        if not args.output.is_file():
            raise ValueError("Phase 17N exact-slice artifact is missing.")
        if args.output.read_text(encoding="utf-8") != rendered_text:
            raise ValueError("Phase 17N exact-slice artifact is stale.")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(rendered_text.encode("utf-8"))


if __name__ == "__main__":
    main()
