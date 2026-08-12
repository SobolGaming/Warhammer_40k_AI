from __future__ import annotations

import math
from decimal import Decimal

from warhammer40k_core.geometry import shapely_backend

from .event_companion_full_artifact_errors import EventCompanionBattlefieldArtifactError
from .event_companion_full_artifact_types import (
    BattlefieldLayoutArtifact,
    BattlefieldShapeArtifact,
    PdfAffineArtifact,
    PointArtifact,
    TerrainAreaArtifact,
    TerrainAreaContactArtifact,
    TerrainComponentPlacementArtifact,
    TerrainFeatureArchetypeArtifact,
)

_EXPECTED_COMPONENT_CAPACITY_BY_FOOTPRINT = {
    "FOOTPRINT_6X4": 2,
    "FOOTPRINT_10X2_5": 3,
    "FOOTPRINT_6X2": 1,
    "FOOTPRINT_7X11_5": 2,
    "FOOTPRINT_8X11_5_POLYGON": 2,
}
_FOOTPRINT_FIRST_VERTEX_BY_ID = {
    "FOOTPRINT_6X4": (-3.25, 2.25),
    "FOOTPRINT_10X2_5": (-5.0, 1.2),
    "FOOTPRINT_6X2": (-3.05, 1.15),
    "FOOTPRINT_7X11_5": (-3.8, 5.75),
    "FOOTPRINT_8X11_5_POLYGON": (-5.5, 4.0),
}
_PIPE_PARENT_FOOTPRINT_VERTICES = (
    (-3.05, 1.15),
    (-2.05, 1.15),
    (-2.05, 1.35),
    (-1.05, 1.35),
    (-1.05, 1.15),
    (3.05, 1.15),
    (3.05, -0.85),
    (2.15, -0.85),
    (1.3, -1.35),
    (0.45, -0.85),
    (-3.05, -0.85),
)
_PIPE_PARENT_FOOTPRINT_TEMPLATE_ID = "FOOTPRINT_6X2"
_PIPE_CENTER_SEARCH_STEPS = 2
_TERRAIN_GRID_INCHES = 0.05
_SOURCE_AREA_ORIENTATION_BASIS = "source_area_affine_determinant"
_SOURCE_COMPONENT_ORIENTATION_BASIS = "source_parent_relative_affine_determinant"
_COMPONENT_ORIENTATION_OVERRIDES = {
    "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-05-component-01": (
        "reviewed_shared_legal_pipe_solid_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-12-component-01": (
        "reviewed_shared_legal_pipe_solid_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-07-component-01": (
        "reviewed_shared_legal_pipe_solid_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-10-component-01": (
        "reviewed_shared_legal_pipe_solid_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-11-component-01": (
        "reviewed_point_symmetry_inherits_primary_component_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-11-component-02": (
        "reviewed_point_symmetry_inherits_primary_component_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-02-component-01": (
        "reviewed_shared_legal_pipe_solid_orientation"
    ),
    "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-15-component-01": (
        "reviewed_shared_legal_pipe_solid_orientation"
    ),
}
_NEW_AREA_POSE_BASIS = "reviewed_source_pose_candidate_with_bounded_seam_adjustment"
_NEW_COMPONENT_POSE_BASIS = "reviewed_source_quantized_pose"
_EXACT_SEAM_AREA_POSE_BASIS = "reviewed_source_pose_with_exact_seam_closure"
_PIPE_COMPONENT_POSE_BASIS = "reviewed_parent_footprint_centered_pipe_pose"
_COMPONENT_CONTAINMENT_ADJUSTMENT_POSE_BASIS = "reviewed_source_quantization_containment_adjustment"
_MEATGRINDER_SOURCE_POSE_BASIS = "accepted_meatgrinder_exemplar_source_pose"
_MEATGRINDER_SYMMETRY_POSE_BASIS = "accepted_meatgrinder_exemplar_exact_point_symmetry"
_CONTACT_CLOSURE_TOLERANCE_INCHES = 0.05
_GEOMETRY_TOLERANCE = 1e-6
_EXACT_WITNESS_TOLERANCE = 5e-13
_REVIEWED_FIXED_AREA_POSE_WITNESSES = {
    # Exact candidate identity and runtime anchor delta for every reviewed row
    # in the generator's fixed area-pose table.
    "disruption-vs-disruption-layout-1-terrain-area-07": (2, 0.15, -0.1),
    "disruption-vs-disruption-layout-1-terrain-area-10": (
        2,
        -0.194559638906,
        0.110510105572,
    ),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-02": (1, 0.1, -0.35),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-04": (2, -0.1, 0.3),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-13": (2, 0.05, -0.35),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-15": (1, -0.05, 0.3),
    "purge-the-foe-vs-reconnaissance-layout-1-terrain-area-13": (0, 0.0, 0.05),
    "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07": (2, 0.15, -0.1),
    "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (
        2,
        -0.194559638906,
        0.110510105572,
    ),
    "disruption-vs-disruption-layout-2-terrain-area-06": (2, 0.0, 0.1),
    "disruption-vs-disruption-layout-2-terrain-area-11": (2, -0.2, 0.05),
    "reconnaissance-vs-reconnaissance-layout-3-terrain-area-06": (2, 0.0, 0.1),
    "reconnaissance-vs-reconnaissance-layout-3-terrain-area-11": (2, -0.2, 0.05),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-02": (1, 0.2, -0.05),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-04": (2, -0.2, 0.0),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-13": (2, 0.2, -0.05),
    "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-15": (1, -0.2, 0.05),
    "take-and-hold-vs-take-and-hold-layout-3-terrain-area-08": (2, 0.1, 0.0),
    "take-and-hold-vs-take-and-hold-layout-3-terrain-area-09": (2, -0.15, 0.0),
    "take-and-hold-vs-take-and-hold-layout-3-terrain-area-11": (1, 0.0, -0.05),
}
_REVIEWED_EXACT_SEAM_AREA_IDS = frozenset(
    {
        "disruption-vs-disruption-layout-1-terrain-area-07",
        "disruption-vs-disruption-layout-1-terrain-area-10",
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07",
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10",
    }
)
_REVIEWED_COMPONENT_CONTAINMENT_ADJUSTMENTS = {
    # Minimum 0.05-inch-grid corrections from an exhaustive 17-by-17 search.
    # These preserve source rotations and close numerical footprint slivers
    # without changing sibling/contact semantics.
    "purge-the-foe-vs-disruption-layout-3-terrain-area-04-component-01": (-0.1, 0.0),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-07-component-01": (0.0, 0.05),
    "purge-the-foe-vs-disruption-layout-3-terrain-area-13-component-01": (0.05, -0.05),
    "disruption-vs-disruption-layout-3-terrain-area-02-component-01": (0.0, -0.05),
    "reconnaissance-vs-reconnaissance-layout-1-terrain-area-02-component-01": (0.0, -0.05),
    "take-and-hold-vs-priority-assets-layout-3-terrain-area-08-component-03": (0.0, -0.05),
    "take-and-hold-vs-priority-assets-layout-3-terrain-area-09-component-02": (0.0, 0.05),
}
_PAGE_9_UNPAIRED_SOURCE_COMPONENT_ID = (
    "take-and-hold-vs-take-and-hold-layout-1-terrain-area-11-component-02"
)
_EXPECTED_TERRITORY_POLYGONS_BY_TEMPLATE = {
    1: {
        "attacker_territory": (((0.0, 26.0), (44.0, 34.0), (44.0, 60.0), (0.0, 60.0)),),
        "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 34.0), (0.0, 26.0)),),
    },
    2: {
        "attacker_territory": (((0.0, 0.0), (22.0, 0.0), (22.0, 60.0), (0.0, 60.0)),),
        "defender_territory": (((22.0, 0.0), (44.0, 0.0), (44.0, 60.0), (22.0, 60.0)),),
    },
    3: {
        "attacker_territory": (((0.0, 0.0), (44.0, 60.0), (0.0, 60.0)),),
        "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 60.0)),),
    },
    4: {
        "attacker_territory": (((0.0, 0.0), (19.0, 0.0), (25.0, 60.0), (0.0, 60.0)),),
        "defender_territory": (((19.0, 0.0), (44.0, 0.0), (44.0, 60.0), (25.0, 60.0)),),
    },
    5: {
        "attacker_territory": (((0.0, 30.0), (44.0, 30.0), (44.0, 60.0), (0.0, 60.0)),),
        "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 30.0), (0.0, 30.0)),),
    },
    6: {
        "attacker_territory": (((0.0, 15.0), (44.0, 45.0), (44.0, 60.0), (0.0, 60.0)),),
        "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 45.0), (0.0, 15.0)),),
    },
}


def validate_artifact_polygon(
    polygon: tuple[PointArtifact, ...],
    *,
    within_battlefield: bool,
) -> None:
    if len(polygon) < 3:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion polygon requires at least three vertices."
        )
    if polygon[0] == polygon[-1]:
        raise EventCompanionBattlefieldArtifactError("Event Companion polygons must be unclosed.")
    points = tuple((point.x_inches, point.y_inches) for point in polygon)
    if any(not math.isfinite(coordinate) for point in points for coordinate in point):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion coordinates must be finite numbers."
        )
    area = abs(
        sum(
            (x1 * y2) - (x2 * y1)
            for (x1, y1), (x2, y2) in zip(
                points,
                (*points[1:], points[0]),
                strict=True,
            )
        )
        / 2.0
    )
    if area <= 1e-9:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion polygon requires non-zero area."
        )
    if within_battlefield and any(
        not (0.0 <= x_inches <= 44.0 and 0.0 <= y_inches <= 60.0) for x_inches, y_inches in points
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion battlefield-region polygon is outside the battlefield."
        )


def validate_territory_geometry(
    *,
    template_number: int,
    territories_by_role: dict[str, BattlefieldShapeArtifact],
) -> None:
    actual_polygons = {
        role: tuple(
            tuple((point.x_inches, point.y_inches) for point in polygon)
            for polygon in territory.polygons
        )
        for role, territory in territories_by_role.items()
    }
    if actual_polygons != _EXPECTED_TERRITORY_POLYGONS_BY_TEMPLATE[template_number]:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion territory geometry drifted from its source template."
        )


def validate_centered_archetype_polygon(polygon: tuple[PointArtifact, ...]) -> None:
    x_values = tuple(point.x_inches for point in polygon)
    y_values = tuple(point.y_inches for point in polygon)
    if not (
        math.isclose(min(x_values) + max(x_values), 0.0, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(min(y_values) + max(y_values), 0.0, rel_tol=0.0, abs_tol=1e-6)
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-archetype footprints must be centered at the origin."
        )


def validate_area_runtime_orientation(area: TerrainAreaArtifact) -> None:
    if area.local_transform != _transform_for_affine(area.source_pdf_affine):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-area reflection must match its source affine."
        )
    if area.local_transform_basis != _SOURCE_AREA_ORIENTATION_BASIS:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-area runtime orientation drifted from its reviewed basis."
        )


def validate_component_runtime_pose(
    component: TerrainComponentPlacementArtifact,
    *,
    area: TerrainAreaArtifact,
) -> None:
    source_transform = (
        "mirror_y_axis"
        if _affine_determinant(area.source_pdf_affine)
        * _affine_determinant(component.source_pdf_affine)
        < 0.0
        else "identity"
    )
    override_basis = _COMPONENT_ORIENTATION_OVERRIDES.get(component.component_id)
    expected_transform = "identity" if override_basis is not None else source_transform
    expected_basis = override_basis or _SOURCE_COMPONENT_ORIENTATION_BASIS
    if (
        component.local_transform != expected_transform
        or component.local_transform_basis != expected_basis
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion component orientation drifted from its reviewed source basis."
        )
    first_vertex_x, first_vertex_y = _FOOTPRINT_FIRST_VERTEX_BY_ID[area.footprint_template_id]
    radians = math.radians(area.rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    area_center_x = area.anchor_x_inches - ((first_vertex_x * cosine) - (first_vertex_y * sine))
    area_center_y = area.anchor_y_inches - ((first_vertex_x * sine) + (first_vertex_y * cosine))
    local_x = component.local_offset_x_inches
    if area.local_transform == "mirror_y_axis":
        local_x = (2.0 * first_vertex_x) - local_x
    expected_center_x = area_center_x + (
        (local_x * cosine) - (component.local_offset_y_inches * sine)
    )
    expected_center_y = area_center_y + (
        (local_x * sine) + (component.local_offset_y_inches * cosine)
    )
    if not (
        math.isclose(
            component.battlefield_center_x_inches,
            expected_center_x,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
        and math.isclose(
            component.battlefield_center_y_inches,
            expected_center_y,
            rel_tol=0.0,
            abs_tol=1e-6,
        )
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion component local offsets drifted from their battlefield centers."
        )

    expected_local_rotation = component.local_rotation_degrees
    if component.local_transform == "mirror_y_axis":
        expected_local_rotation += 180.0
    if area.local_transform == "mirror_y_axis":
        expected_local_rotation = 180.0 - expected_local_rotation
    expected_battlefield_rotation = area.rotation_degrees + expected_local_rotation
    difference = (
        component.battlefield_rotation_degrees - expected_battlefield_rotation + 180.0
    ) % 360.0 - 180.0
    if not math.isclose(difference, 0.0, rel_tol=0.0, abs_tol=1e-6):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion component local rotations drifted from battlefield rotation."
        )


def validate_area_pose_witness(
    area: TerrainAreaArtifact,
    *,
    is_meatgrinder: bool,
    source_area_index: int,
) -> None:
    reviewed_pose_witness = _REVIEWED_FIXED_AREA_POSE_WITNESSES.get(area.source_area_id)
    has_exact_seam = area.source_area_id in _REVIEWED_EXACT_SEAM_AREA_IDS
    values = (
        area.source_anchor_x_inches,
        area.source_anchor_y_inches,
        area.source_rotation_degrees,
        area.runtime_adjustment_x_inches,
        area.runtime_adjustment_y_inches,
        area.runtime_rotation_adjustment_degrees,
    )
    if (
        type(area.source_pose_candidate_index) is not int
        or not 0 <= area.source_pose_candidate_index <= 3
        or any(not math.isfinite(value) for value in values)
        or (
            area.source_pose_fit_residual_inches is not None
            and (
                not math.isfinite(area.source_pose_fit_residual_inches)
                or area.source_pose_fit_residual_inches < 0.0
            )
        )
        or not all(_is_on_terrain_grid(value) for value in values[:2])
        or (not has_exact_seam and not all(_is_on_terrain_grid(value) for value in values[3:5]))
        or (
            has_exact_seam
            and not all(
                _has_at_most_decimal_places(value, 12)
                for value in (
                    area.anchor_x_inches,
                    area.anchor_y_inches,
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            )
        )
        or not math.isclose(
            area.anchor_x_inches,
            area.source_anchor_x_inches + area.runtime_adjustment_x_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            area.anchor_y_inches,
            area.source_anchor_y_inches + area.runtime_adjustment_y_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            _rotation_difference(area.rotation_degrees, area.source_rotation_degrees),
            area.runtime_rotation_adjustment_degrees,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-area pose witness is invalid."
        )
    expected_basis = _EXACT_SEAM_AREA_POSE_BASIS if has_exact_seam else _NEW_AREA_POSE_BASIS
    if is_meatgrinder:
        expected_basis = (
            _MEATGRINDER_SOURCE_POSE_BASIS
            if source_area_index <= 8
            else _MEATGRINDER_SYMMETRY_POSE_BASIS
        )
    if area.pose_basis != expected_basis:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-area pose basis drifted."
        )
    if not is_meatgrinder:
        adjustment_is_valid = (
            (
                abs(area.runtime_adjustment_x_inches) <= 0.2 + 1e-9
                and abs(area.runtime_adjustment_y_inches) <= 0.2 + 1e-9
            )
            if reviewed_pose_witness is None
            else (
                area.source_pose_candidate_index == reviewed_pose_witness[0]
                and math.isclose(
                    area.runtime_adjustment_x_inches,
                    reviewed_pose_witness[1],
                    rel_tol=0.0,
                    abs_tol=_EXACT_WITNESS_TOLERANCE,
                )
                and math.isclose(
                    area.runtime_adjustment_y_inches,
                    reviewed_pose_witness[2],
                    rel_tol=0.0,
                    abs_tol=_EXACT_WITNESS_TOLERANCE,
                )
            )
        )
        if not adjustment_is_valid or not math.isclose(
            area.runtime_rotation_adjustment_degrees,
            0.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion terrain-area source adjustment exceeds its reviewed bound."
            )


def validate_component_pose_witness(
    component: TerrainComponentPlacementArtifact,
    *,
    area: TerrainAreaArtifact,
    archetype: TerrainFeatureArchetypeArtifact,
    is_meatgrinder: bool,
    source_area_index: int,
) -> None:
    values = (
        component.source_battlefield_center_x_inches,
        component.source_battlefield_center_y_inches,
        component.source_battlefield_rotation_degrees,
        component.runtime_adjustment_x_inches,
        component.runtime_adjustment_y_inches,
        component.runtime_rotation_adjustment_degrees,
    )
    if (
        any(not math.isfinite(value) for value in values)
        or not all(_is_on_terrain_grid(value) for value in values[:2])
        or not all(_is_on_terrain_grid(value) for value in values[3:5])
        or not math.isclose(
            component.battlefield_center_x_inches,
            component.source_battlefield_center_x_inches + component.runtime_adjustment_x_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            component.battlefield_center_y_inches,
            component.source_battlefield_center_y_inches + component.runtime_adjustment_y_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            _rotation_difference(
                component.battlefield_rotation_degrees,
                component.source_battlefield_rotation_degrees,
            ),
            component.runtime_rotation_adjustment_degrees,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion component pose witness is invalid."
        )
    reviewed_adjustment = _REVIEWED_COMPONENT_CONTAINMENT_ADJUSTMENTS.get(
        component.source_component_id
    )
    if is_meatgrinder:
        expected_basis = (
            _MEATGRINDER_SOURCE_POSE_BASIS
            if source_area_index <= 8
            else _MEATGRINDER_SYMMETRY_POSE_BASIS
        )
    elif reviewed_adjustment is not None:
        expected_basis = _COMPONENT_CONTAINMENT_ADJUSTMENT_POSE_BASIS
    elif component.archetype_id == "dense-long-pipes":
        expected_basis = _PIPE_COMPONENT_POSE_BASIS
    else:
        expected_basis = _NEW_COMPONENT_POSE_BASIS
    if component.pose_basis != expected_basis:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion component pose basis drifted."
        )
    if is_meatgrinder:
        return
    if reviewed_adjustment is not None:
        if not (
            math.isclose(
                component.runtime_adjustment_x_inches,
                reviewed_adjustment[0],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                component.runtime_adjustment_y_inches,
                reviewed_adjustment[1],
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            and math.isclose(
                component.runtime_rotation_adjustment_degrees,
                0.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion component containment adjustment drifted."
            )
        return
    if component.archetype_id == "dense-long-pipes":
        _validate_parent_centered_pipe_pose(
            component,
            area=area,
            archetype=archetype,
        )
        return
    if any(
        not math.isclose(value, 0.0, rel_tol=0.0, abs_tol=1e-9)
        for value in (
            component.runtime_adjustment_x_inches,
            component.runtime_adjustment_y_inches,
            component.runtime_rotation_adjustment_degrees,
        )
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion independently observed component poses must not be shifted."
        )


def _validate_parent_centered_pipe_pose(
    component: TerrainComponentPlacementArtifact,
    *,
    area: TerrainAreaArtifact,
    archetype: TerrainFeatureArchetypeArtifact,
) -> None:
    expected_center_x, expected_center_y, expected_rotation = _parent_centered_pipe_pose(
        component,
        area=area,
        archetype=archetype,
    )
    if not (
        math.isclose(
            component.battlefield_center_x_inches,
            expected_center_x,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and math.isclose(
            component.battlefield_center_y_inches,
            expected_center_y,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        and math.isclose(
            _rotation_difference(component.battlefield_rotation_degrees, expected_rotation),
            0.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion parent-centered pipe pose drifted."
        )


def _parent_centered_pipe_pose(
    component: TerrainComponentPlacementArtifact,
    *,
    area: TerrainAreaArtifact,
    archetype: TerrainFeatureArchetypeArtifact,
) -> tuple[float, float, float]:
    if (
        area.footprint_template_id != _PIPE_PARENT_FOOTPRINT_TEMPLATE_ID
        or archetype.footprint_template_id != _PIPE_PARENT_FOOTPRINT_TEMPLATE_ID
    ):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion parent-centered pipe footprint family drifted."
        )
    first_vertex_x, first_vertex_y = _FOOTPRINT_FIRST_VERTEX_BY_ID[area.footprint_template_id]
    radians = math.radians(area.rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    area_center_x = area.anchor_x_inches - ((first_vertex_x * cosine) - (first_vertex_y * sine))
    area_center_y = area.anchor_y_inches - ((first_vertex_x * sine) + (first_vertex_y * cosine))
    mirrored_center_x = 2.0 * first_vertex_x if area.local_transform == "mirror_y_axis" else 0.0
    centered_x = _quantize_terrain_coordinate(area_center_x + mirrored_center_x * cosine)
    centered_y = _quantize_terrain_coordinate(area_center_y + mirrored_center_x * sine)
    rotation = (
        area.rotation_degrees + (180.0 if area.local_transform == "mirror_y_axis" else 0.0)
    ) % 360.0
    parent_polygon = shapely_backend.footprint_for_polygon(_pipe_parent_polygon(area))
    ranked_candidates: list[
        tuple[tuple[bool, float, int, int, int, int], tuple[float, float, float]]
    ] = []
    for x_steps in range(-_PIPE_CENTER_SEARCH_STEPS, _PIPE_CENTER_SEARCH_STEPS + 1):
        for y_steps in range(-_PIPE_CENTER_SEARCH_STEPS, _PIPE_CENTER_SEARCH_STEPS + 1):
            center_x = round(centered_x + x_steps * _TERRAIN_GRID_INCHES, 6)
            center_y = round(centered_y + y_steps * _TERRAIN_GRID_INCHES, 6)
            component_polygon = shapely_backend.footprint_for_polygon(
                _pipe_component_polygon(
                    component,
                    area=area,
                    archetype=archetype,
                    center_x=center_x,
                    center_y=center_y,
                    rotation=rotation,
                )
            )
            outside_area = max(
                0.0,
                component_polygon.area - parent_polygon.intersection(component_polygon).area,
            )
            ranked_candidates.append(
                (
                    (
                        outside_area > _GEOMETRY_TOLERANCE,
                        round(outside_area, 12),
                        x_steps * x_steps + y_steps * y_steps,
                        abs(x_steps) + abs(y_steps),
                        x_steps,
                        y_steps,
                    ),
                    (center_x, center_y, rotation),
                )
            )
    ranked_candidates.sort(key=lambda candidate: candidate[0])
    return ranked_candidates[0][1]


def _pipe_parent_polygon(
    area: TerrainAreaArtifact,
) -> tuple[tuple[float, float], ...]:
    first_vertex_x = _PIPE_PARENT_FOOTPRINT_VERTICES[0][0]
    if area.local_transform not in {"identity", "mirror_y_axis"}:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion parent-centered pipe area transform is unsupported."
        )
    area_center_x, area_center_y = _pipe_area_center(area)
    points: list[tuple[float, float]] = []
    for x_inches, y_inches in _PIPE_PARENT_FOOTPRINT_VERTICES:
        if area.local_transform == "mirror_y_axis":
            x_inches = 2.0 * first_vertex_x - x_inches
        rotated_x, rotated_y = _rotate_pipe_point(
            x_inches,
            y_inches,
            area.rotation_degrees,
        )
        points.append((rotated_x + area_center_x, rotated_y + area_center_y))
    return tuple(points)


def _pipe_component_polygon(
    component: TerrainComponentPlacementArtifact,
    *,
    area: TerrainAreaArtifact,
    archetype: TerrainFeatureArchetypeArtifact,
    center_x: float,
    center_y: float,
    rotation: float,
) -> tuple[tuple[float, float], ...]:
    offset_x, offset_y, local_rotation = _pipe_component_local_placement(
        component,
        area=area,
        center_x=center_x,
        center_y=center_y,
        rotation=rotation,
    )
    if component.local_transform not in {"identity", "mirror_y_axis"}:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion parent-centered pipe component transform is unsupported."
        )
    first_vertex_x = _PIPE_PARENT_FOOTPRINT_VERTICES[0][0]
    if area.local_transform not in {"identity", "mirror_y_axis"}:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion parent-centered pipe area transform is unsupported."
        )
    area_center_x, area_center_y = _pipe_area_center(area)
    points: list[tuple[float, float]] = []
    for point in archetype.rules_footprint_polygon:
        x_inches = point.x_inches
        if component.local_transform == "mirror_y_axis":
            x_inches = -x_inches
        local_x, local_y = _rotate_pipe_point(
            x_inches,
            point.y_inches,
            local_rotation,
        )
        local_x += offset_x
        local_y += offset_y
        if area.local_transform == "mirror_y_axis":
            local_x = 2.0 * first_vertex_x - local_x
        rotated_x, rotated_y = _rotate_pipe_point(
            local_x,
            local_y,
            area.rotation_degrees,
        )
        points.append((rotated_x + area_center_x, rotated_y + area_center_y))
    return tuple(points)


def _pipe_component_local_placement(
    component: TerrainComponentPlacementArtifact,
    *,
    area: TerrainAreaArtifact,
    center_x: float,
    center_y: float,
    rotation: float,
) -> tuple[float, float, float]:
    area_center_x, area_center_y = _pipe_area_center(area)
    delta_x = center_x - area_center_x
    delta_y = center_y - area_center_y
    radians = math.radians(area.rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    transformed_x = delta_x * cosine + delta_y * sine
    local_y = -delta_x * sine + delta_y * cosine
    first_vertex_x = _PIPE_PARENT_FOOTPRINT_VERTICES[0][0]
    local_x = (
        (2.0 * first_vertex_x) - transformed_x
        if area.local_transform == "mirror_y_axis"
        else transformed_x
    )
    inner_rotation = (
        180.0 + area.rotation_degrees - rotation
        if area.local_transform == "mirror_y_axis"
        else rotation - area.rotation_degrees
    )
    local_rotation = inner_rotation - (
        180.0 if component.local_transform == "mirror_y_axis" else 0.0
    )
    return (round(local_x, 6), round(local_y, 6), round(local_rotation % 360.0, 6))


def _pipe_area_center(area: TerrainAreaArtifact) -> tuple[float, float]:
    first_vertex_x, first_vertex_y = _PIPE_PARENT_FOOTPRINT_VERTICES[0]
    radians = math.radians(area.rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (
        area.anchor_x_inches - ((first_vertex_x * cosine) - (first_vertex_y * sine)),
        area.anchor_y_inches - ((first_vertex_x * sine) + (first_vertex_y * cosine)),
    )


def _rotate_pipe_point(
    x_inches: float,
    y_inches: float,
    rotation_degrees: float,
) -> tuple[float, float]:
    radians = math.radians(rotation_degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (
        x_inches * cosine - y_inches * sine,
        x_inches * sine + y_inches * cosine,
    )


def validate_component_mirror_links(
    layout: BattlefieldLayoutArtifact,
    *,
    components_by_id: dict[str, TerrainComponentPlacementArtifact],
    components_by_source_id: dict[str, TerrainComponentPlacementArtifact],
    areas_by_id: dict[str, TerrainAreaArtifact],
    is_meatgrinder: bool,
) -> None:
    for component in components_by_id.values():
        if component.mirror_component_id is None:
            if (
                component.source_mirror_component_id is not None
                or component.source_component_id != _PAGE_9_UNPAIRED_SOURCE_COMPONENT_ID
                or layout.source_page != 9
            ):
                raise EventCompanionBattlefieldArtifactError(
                    "Event Companion component has an invalid absent mirror record."
                )
            continue
        mirror = components_by_id.get(component.mirror_component_id)
        source_mirror = components_by_source_id.get(component.source_mirror_component_id or "")
        if (
            mirror is None
            or source_mirror is not mirror
            or mirror.mirror_component_id != component.component_id
            or mirror.source_mirror_component_id != component.source_component_id
            or areas_by_id[component.terrain_area_id].mirror_area_id != mirror.terrain_area_id
        ):
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion component mirror provenance is invalid."
            )
        if is_meatgrinder and not (
            component.archetype_id == mirror.archetype_id
            and component.local_transform == mirror.local_transform
            and _is_exact_sum(
                component.battlefield_center_x_inches,
                mirror.battlefield_center_x_inches,
                44.0,
            )
            and _is_exact_sum(
                component.battlefield_center_y_inches,
                mirror.battlefield_center_y_inches,
                60.0,
            )
            and _is_half_turn(
                component.battlefield_rotation_degrees,
                mirror.battlefield_rotation_degrees,
            )
        ):
            raise EventCompanionBattlefieldArtifactError(
                "Meatgrinder component point symmetry drifted from the accepted exemplar."
            )


def validate_component_capacities(
    layout: BattlefieldLayoutArtifact,
    *,
    areas_by_id: dict[str, TerrainAreaArtifact],
    components_by_id: dict[str, TerrainComponentPlacementArtifact],
) -> None:
    components_by_area: dict[str, list[TerrainComponentPlacementArtifact]] = {
        area_id: [] for area_id in areas_by_id
    }
    for component in components_by_id.values():
        components_by_area[component.terrain_area_id].append(component)
    page_9_missing_component_source_area_id = (
        "take-and-hold-vs-take-and-hold-layout-1-terrain-area-06"
    )
    for area_id, area in areas_by_id.items():
        components = components_by_area[area_id]
        expected_count = _EXPECTED_COMPONENT_CAPACITY_BY_FOOTPRINT[area.footprint_template_id]
        if area.source_area_id == page_9_missing_component_source_area_id:
            expected_count = 1
        expected_ids = {
            f"{area_id}-component-{ordinal:02d}" for ordinal in range(1, expected_count + 1)
        }
        if (
            len(components) != expected_count
            or {component.component_id for component in components} != expected_ids
        ):
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion terrain-area component capacity drifted from the source page."
            )
        if area.source_area_id == page_9_missing_component_source_area_id and (
            components[0].archetype_id != "dense-downed-hovercraft"
        ):
            raise EventCompanionBattlefieldArtifactError(
                "The page 9 source exception must retain its lone downed hovercraft."
            )


def validate_area_contacts(
    layout: BattlefieldLayoutArtifact,
    *,
    areas_by_id: dict[str, TerrainAreaArtifact],
    areas_by_source_id: dict[str, TerrainAreaArtifact],
    expected_count: int,
) -> None:
    contacts_by_pair: dict[frozenset[str], TerrainAreaContactArtifact] = {}
    source_icon_ids: set[str] = set()
    single_contact_member_ids: set[str] = set()
    for contact in layout.terrain_area_contacts:
        first_id, second_id = contact.terrain_area_ids
        source_first_id, source_second_id = contact.source_terrain_area_ids
        canonical_pair = frozenset(contact.terrain_area_ids)
        expected_source_icon_drawing_count = 1 if contact.kind == "single" else 2
        if (
            first_id == second_id
            or first_id not in areas_by_id
            or second_id not in areas_by_id
            or canonical_pair in contacts_by_pair
            or contact.kind not in {"single", "separate"}
            or source_first_id not in areas_by_source_id
            or source_second_id not in areas_by_source_id
            or areas_by_id[first_id].source_area_id != source_first_id
            or areas_by_id[second_id].source_area_id != source_second_id
            or len(contact.source_icon_ids) != 1
            or contact.source_icon_ids[0] in source_icon_ids
            or not contact.source_icon_ids[0].startswith(
                f"{layout.layout_id}-terrain-contact-icon-"
            )
            or len(contact.source_pdf_drawing_indices_zero_based)
            != expected_source_icon_drawing_count
            or len(contact.source_pdf_seqnos) != expected_source_icon_drawing_count
            or any(index < 0 for index in contact.source_pdf_drawing_indices_zero_based)
            or any(seqno < 0 for seqno in contact.source_pdf_seqnos)
            or not math.isfinite(contact.source_icon_x_inches)
            or not math.isfinite(contact.source_icon_y_inches)
            or not 0.0 <= contact.source_icon_x_inches <= 44.0
            or not 0.0 <= contact.source_icon_y_inches <= 60.0
            or not math.isfinite(contact.source_pair_gap_inches)
            or contact.source_pair_gap_inches < 0.0
            or not math.isfinite(contact.runtime_pair_gap_inches)
            or not 0.0
            <= contact.runtime_pair_gap_inches
            <= _CONTACT_CLOSURE_TOLERANCE_INCHES + _GEOMETRY_TOLERANCE
            or not math.isfinite(contact.runtime_pair_overlap_square_inches)
            or not 0.0 <= contact.runtime_pair_overlap_square_inches <= _GEOMETRY_TOLERANCE
        ):
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion terrain-area source-contact record is invalid."
            )
        contacts_by_pair[canonical_pair] = contact
        source_icon_ids.add(contact.source_icon_ids[0])
        if contact.kind == "single":
            if first_id in single_contact_member_ids or second_id in single_contact_member_ids:
                raise EventCompanionBattlefieldArtifactError(
                    "Event Companion physical terrain area belongs to multiple logical areas."
                )
            single_contact_member_ids.update((first_id, second_id))
    if len(contacts_by_pair) != expected_count:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-area source-contact inventory drifted."
        )
    for contact in layout.terrain_area_contacts:
        first_id, second_id = contact.terrain_area_ids
        mirrored_pair = frozenset(
            (
                areas_by_id[first_id].mirror_area_id,
                areas_by_id[second_id].mirror_area_id,
            )
        )
        mirrored_contact = contacts_by_pair.get(mirrored_pair)
        if mirrored_contact is None or mirrored_contact.kind != contact.kind:
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion terrain-area contacts and kinds must preserve point symmetry."
            )


def validate_contact_pairs(
    field_name: str,
    pairs: tuple[tuple[str, str], ...],
    *,
    valid_ids: frozenset[str],
) -> None:
    seen: set[frozenset[str]] = set()
    for first_id, second_id in pairs:
        canonical_pair = frozenset((first_id, second_id))
        if (
            not first_id.strip()
            or not second_id.strip()
            or first_id == second_id
            or first_id not in valid_ids
            or second_id not in valid_ids
            or canonical_pair in seen
        ):
            raise EventCompanionBattlefieldArtifactError(
                f"Event Companion {field_name} pair IDs must be known, distinct, and unique."
            )
        seen.add(canonical_pair)


def validate_component_contact_semantics(
    layout: BattlefieldLayoutArtifact,
    *,
    components_by_id: dict[str, TerrainComponentPlacementArtifact],
) -> None:
    expected_pairs: set[frozenset[str]] = set()
    components_by_area: dict[str, list[TerrainComponentPlacementArtifact]] = {}
    for component in components_by_id.values():
        components_by_area.setdefault(component.terrain_area_id, []).append(component)
    for components in components_by_area.values():
        by_archetype: dict[str, list[str]] = {}
        for component in components:
            by_archetype.setdefault(component.archetype_id, []).append(component.component_id)
        hovercraft_ids = by_archetype.get("dense-downed-hovercraft", [])
        tall_crate_ids = by_archetype.get("dense-tall-crates", [])
        industrial_crate_ids = by_archetype.get("dense-industrial-crates", [])
        end_barricade_ids = by_archetype.get("light-end-barricade", [])
        if hovercraft_ids and tall_crate_ids:
            if len(hovercraft_ids) != 1 or len(tall_crate_ids) != 1:
                raise EventCompanionBattlefieldArtifactError(
                    "Event Companion hovercraft composites require one companion crate."
                )
            expected_pairs.add(frozenset((*hovercraft_ids, *tall_crate_ids)))
        if industrial_crate_ids or end_barricade_ids:
            if len(industrial_crate_ids) != 1 or len(end_barricade_ids) != 2:
                raise EventCompanionBattlefieldArtifactError(
                    "Event Companion industrial-crate composites require two end barricades."
                )
            expected_pairs.update(
                frozenset((industrial_crate_ids[0], end_id)) for end_id in end_barricade_ids
            )
    actual_pairs = {frozenset(pair) for pair in layout.terrain_component_contact_pairs}
    if actual_pairs != expected_pairs:
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion terrain-component contacts drifted from composite source pieces."
        )


def _affine_determinant(affine: PdfAffineArtifact) -> float:
    return (affine.a * affine.d) - (affine.b * affine.c)


def _transform_for_affine(affine: PdfAffineArtifact) -> str:
    return "mirror_y_axis" if _affine_determinant(affine) < 0.0 else "identity"


def _is_on_terrain_grid(value: float) -> bool:
    return math.isclose(
        value / _TERRAIN_GRID_INCHES,
        round(value / _TERRAIN_GRID_INCHES),
        rel_tol=0.0,
        abs_tol=1e-9,
    )


def _has_at_most_decimal_places(value: float, decimal_places: int) -> bool:
    exponent = Decimal(str(value)).as_tuple().exponent
    return type(exponent) is int and exponent >= -decimal_places


def _quantize_terrain_coordinate(value: float) -> float:
    return round(
        round(value / _TERRAIN_GRID_INCHES) * _TERRAIN_GRID_INCHES,
        6,
    )


def _rotation_difference(value: float, source: float) -> float:
    return (value - source + 180.0) % 360.0 - 180.0


def _is_exact_sum(first: float, second: float, expected: float) -> bool:
    return math.isclose(first + second, expected, rel_tol=0.0, abs_tol=1e-9)


def _is_half_turn(primary_degrees: float, mirror_degrees: float) -> bool:
    return math.isclose(
        (mirror_degrees - primary_degrees) % 360.0,
        180.0,
        rel_tol=0.0,
        abs_tol=1e-9,
    )


__all__ = (
    "validate_area_contacts",
    "validate_area_pose_witness",
    "validate_area_runtime_orientation",
    "validate_component_capacities",
    "validate_component_contact_semantics",
    "validate_component_mirror_links",
    "validate_component_pose_witness",
    "validate_component_runtime_pose",
    "validate_contact_pairs",
    "validate_territory_geometry",
)
