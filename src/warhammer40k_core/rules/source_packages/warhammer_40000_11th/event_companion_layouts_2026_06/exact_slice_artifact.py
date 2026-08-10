from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Callable

import msgspec

ARTIFACT_SCHEMA = "core-v2-phase17n-event-companion-exact-slice-v1"
SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-1-2026-07"
SOURCE_PDF_FILENAME = "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
SOURCE_PDF_SHA256 = "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
SOURCE_PAGES = (24, 25, 26)
SOURCE_EXTRACTION_PAYLOAD_SHA256 = (
    "8d0082df6516b8927cf8666042a9a679863b81205d41377a85c1823cf8e35b30"
)
EXPECTED_PACKAGE_HASH = "90b60b7621659917cd9e2cbeed9dde0f172c178b1c9a92cfe54cf75805800744"
EXPECTED_ARTIFACT_SHA256 = "048d04f87437692053c34612db07098ecd4c455ac8fa34d38e357635339285bb"
PRIMARY_MISSION_ID = "primary-meatgrinder"
FORCE_DISPOSITION_ID = "purge-the-foe"
BATTLEFIELD_WIDTH_INCHES = 44.0
BATTLEFIELD_DEPTH_INCHES = 60.0
TERRAIN_PLACEMENT_INCREMENT_INCHES = 0.05

EXPECTED_LAYOUT_IDS = frozenset(
    {
        "purge-the-foe-vs-purge-the-foe-layout-1",
        "purge-the-foe-vs-purge-the-foe-layout-2",
        "purge-the-foe-vs-purge-the-foe-layout-3",
    }
)
EXPECTED_ARCHETYPE_BY_PRIMARY_XREF = {
    5462: (
        "dense-downed-hovercraft",
        "dense_solid",
        "battlefield_debris_and_statuary",
        "dense",
        None,
    ),
    5464: ("light-long-barricade", "light_solid", "battlefield_debris_and_statuary", "light", None),
    5466: (
        "dense-industrial-crates",
        "dense_solid",
        "battlefield_debris_and_statuary",
        "dense",
        None,
    ),
    5468: ("light-end-barricade", "light_solid", "battlefield_debris_and_statuary", "light", None),
    5470: ("ruins-cd", "ruin", "ruins", "dense", "CD"),
    5472: ("ruins-gh", "ruin", "ruins", "dense", "GH"),
    5474: ("ruins-ef", "ruin", "ruins", "dense", "EF"),
    5476: ("ruins-ab", "ruin", "ruins", "dense", "AB"),
    5478: ("light-corner-ab", "light_solid", "battlefield_debris_and_statuary", "light", None),
    5480: ("light-corner-cd", "light_solid", "battlefield_debris_and_statuary", "light", None),
    5482: ("light-corner-ef", "light_solid", "battlefield_debris_and_statuary", "light", None),
    5484: ("light-corner-gh", "light_solid", "battlefield_debris_and_statuary", "light", None),
    5486: ("dense-tall-crates", "dense_solid", "battlefield_debris_and_statuary", "dense", None),
    5488: ("dense-long-pipes", "dense_solid", "battlefield_debris_and_statuary", "dense", None),
}
EXPECTED_ARCHETYPE_SOURCE_XREFS = {
    archetype_id: ((primary_xref, 5675) if primary_xref == 5486 else (primary_xref,))
    for primary_xref, (archetype_id, *_rest) in EXPECTED_ARCHETYPE_BY_PRIMARY_XREF.items()
}
EXPECTED_COMPONENT_XREF_COUNTS_BY_LAYOUT = {
    layout_id: Counter(
        {
            xref: (4 if xref == 5468 else 2)
            for xref in (
                set(EXPECTED_ARCHETYPE_BY_PRIMARY_XREF)
                if layout_id != "purge-the-foe-vs-purge-the-foe-layout-3"
                else (set(EXPECTED_ARCHETYPE_BY_PRIMARY_XREF) - {5486}) | {5675}
            )
        }
    )
    for layout_id in EXPECTED_LAYOUT_IDS
}
EXPECTED_TERRAIN_TEMPLATE_COUNTS = Counter(
    {
        "FOOTPRINT_6X4": 4,
        "FOOTPRINT_10X2_5": 2,
        "FOOTPRINT_6X2": 4,
        "FOOTPRINT_7X11_5": 4,
        "FOOTPRINT_8X11_5_POLYGON": 2,
    }
)
EXPECTED_DEPLOYMENT_TEMPLATES_BY_LAYOUT = {
    "purge-the-foe-vs-purge-the-foe-layout-1": 3,
    "purge-the-foe-vs-purge-the-foe-layout-2": 1,
    "purge-the-foe-vs-purge-the-foe-layout-3": 4,
}
EXPECTED_OBJECTIVE_AREA_SUFFIXES_BY_LAYOUT = {
    "purge-the-foe-vs-purge-the-foe-layout-1": {
        "attacker-home": "03",
        "defender-home": "14",
        "central-north": "07",
        "central-south": "10",
        "expansion-north-east": "01",
        "expansion-south-west": "16",
    },
    "purge-the-foe-vs-purge-the-foe-layout-2": {
        "attacker-home": "03",
        "defender-home": "14",
        "central-west": "09",
        "central-east": "08",
        "expansion-north-east": "04",
        "expansion-south-west": "13",
    },
    "purge-the-foe-vs-purge-the-foe-layout-3": {
        "attacker-home": "03",
        "defender-home": "14",
        "central-north": "07",
        "central-south": "10",
        "expansion-north-east": "01",
        "expansion-south-west": "16",
    },
}
EXPECTED_VECTOR_PATH_PROVENANCE_BY_AREA = {
    "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-02": (101, 58),
    "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-15": (61, 58),
    "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-03": (174, 58),
    "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-14": (91, 58),
    "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-05": (62, 58),
    "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-12": (55, 58),
}


class EventCompanionExactSliceArtifactError(ValueError):
    """Raised when the exact Event Companion slice artifact is invalid or stale."""


class PointArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    x_inches: float
    y_inches: float


class PdfBoundsArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    x0_points: float
    y0_points: float
    x1_points: float
    y1_points: float


class PdfAffineArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    a: float
    b: float
    c: float
    d: float
    e: float
    f: float


class SourceCoordinateFrameArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    pdf_background_image_xref: int
    pdf_background_image_sha256: str
    pdf_background_bounds: PdfBoundsArtifact
    battlefield_width_inches: float
    battlefield_depth_inches: float
    battlefield_origin: str
    battlefield_orientation: str
    coordinate_precision_decimal_places: int
    terrain_placement_increment_inches: float


class TerrainWallArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    wall_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    height_inches: float
    rotation_degrees: float


class TerrainFloorArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    floor_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    thickness_inches: float
    rotation_degrees: float


class TerrainFeatureArchetypeArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    archetype_id: str
    name: str
    source_assets: tuple[SourceImageAssetArtifact, ...]
    source_component_label: str | None
    model_kind: str
    feature_kind: str
    classification: str
    footprint_template_id: str
    rules_footprint_polygon: tuple[PointArtifact, ...]
    walls: tuple[TerrainWallArtifact, ...]
    floors: tuple[TerrainFloorArtifact, ...]
    modeling_basis: str


class SourceImageAssetArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_pdf_image_xref: int
    image_sha256: str
    pixel_width: int
    pixel_height: int
    soft_mask_xref: int | None
    soft_mask_sha256: str | None


class TerrainAreaArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    area_id: str
    footprint_template_id: str
    classification: str
    anchor_x_inches: float
    anchor_y_inches: float
    rotation_degrees: float
    local_transform: str
    pose_basis: str
    source_pdf_vector_path_index_zero_based: int | None
    source_pdf_vector_path_item_index_zero_based: int | None
    mirror_area_id: str
    source_pdf_image_xref: int
    source_image_sha256: str
    source_soft_mask_sha256: str
    source_pdf_bounds: PdfBoundsArtifact
    source_pdf_affine: PdfAffineArtifact


class TerrainComponentPlacementArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    component_id: str
    terrain_area_id: str
    archetype_id: str
    local_offset_x_inches: float
    local_offset_y_inches: float
    local_rotation_degrees: float
    local_transform: str
    battlefield_center_x_inches: float
    battlefield_center_y_inches: float
    battlefield_rotation_degrees: float
    source_pdf_image_xref: int
    source_pdf_bounds: PdfBoundsArtifact
    source_pdf_affine: PdfAffineArtifact


class ObjectiveArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    objective_id: str
    name: str
    role: str
    x_inches: float
    y_inches: float
    terrain_area_ids: tuple[str, ...]
    source_symbol_kind: str


class BattlefieldShapeArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    shape_id: str
    role: str
    owner_role: str | None
    polygons: tuple[tuple[PointArtifact, ...], ...]
    source_kind: str


class ExactBattlefieldLayoutArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    layout_id: str
    layout_letter: str
    name: str
    source_layout_id: str
    source_page: int
    deployment_zone_template_number: int
    attacker_edge: str
    defender_edge: str
    terrain_areas: tuple[TerrainAreaArtifact, ...]
    terrain_components: tuple[TerrainComponentPlacementArtifact, ...]
    objectives: tuple[ObjectiveArtifact, ...]
    deployment_zones: tuple[BattlefieldShapeArtifact, ...]
    no_mans_land: BattlefieldShapeArtifact
    territories: tuple[BattlefieldShapeArtifact, ...]


class EventCompanionExactSliceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_pdf_filename: str
    source_pdf_sha256: str
    source_pages: tuple[int, ...]
    source_extraction_payload_sha256: str
    source_coordinate_frame: SourceCoordinateFrameArtifact
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    primary_mission_id: str
    feature_archetypes: tuple[TerrainFeatureArchetypeArtifact, ...]
    layouts: tuple[ExactBattlefieldLayoutArtifact, ...]
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion exact-slice artifact schema is unsupported."
            )
        if (
            self.source_package_id,
            self.source_pdf_filename,
            self.source_pdf_sha256,
            self.source_pages,
            self.source_extraction_payload_sha256,
        ) != (
            SOURCE_PACKAGE_ID,
            SOURCE_PDF_FILENAME,
            SOURCE_PDF_SHA256,
            SOURCE_PAGES,
            SOURCE_EXTRACTION_PAYLOAD_SHA256,
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion exact-slice source provenance drifted."
            )
        if (
            self.player_force_disposition_id,
            self.opponent_force_disposition_id,
            self.primary_mission_id,
        ) != (FORCE_DISPOSITION_ID, FORCE_DISPOSITION_ID, PRIMARY_MISSION_ID):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion exact-slice mission identity drifted."
            )
        _validate_source_coordinate_frame(self.source_coordinate_frame)
        archetypes_by_id = _validate_archetypes(self.feature_archetypes)
        layouts_by_id = _unique_by_id(
            "layout",
            self.layouts,
            lambda layout: layout.layout_id,
        )
        if frozenset(layouts_by_id) != EXPECTED_LAYOUT_IDS:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion exact-slice layout inventory drifted."
            )
        for layout in self.layouts:
            _validate_layout(layout, archetypes_by_id=archetypes_by_id)
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != package_hash(self):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion exact-slice package hash is stale."
            )
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion exact-slice package hash drifted from its reviewed pin."
            )


def event_companion_exact_slice_artifact_from_json_bytes(
    raw: bytes,
) -> EventCompanionExactSliceArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=EventCompanionExactSliceArtifact)
    except msgspec.DecodeError as exc:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact-slice artifact is invalid."
        ) from exc
    artifact.validate()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact-slice artifact bytes drifted from their reviewed pin."
        )
    return artifact


def package_hash(artifact: EventCompanionExactSliceArtifact) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact-slice artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_source_coordinate_frame(frame: SourceCoordinateFrameArtifact) -> None:
    if frame.pdf_background_image_xref != 5490:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion source coordinate-frame background xref drifted."
        )
    _validate_sha256(
        "source coordinate-frame background image SHA-256",
        frame.pdf_background_image_sha256,
    )
    _validate_pdf_bounds(frame.pdf_background_bounds)
    expected_bounds = (127.690826, 276.662323, 468.448334, 741.498596)
    actual_bounds = (
        frame.pdf_background_bounds.x0_points,
        frame.pdf_background_bounds.y0_points,
        frame.pdf_background_bounds.x1_points,
        frame.pdf_background_bounds.y1_points,
    )
    if any(
        not math.isclose(actual, expected, rel_tol=0.0, abs_tol=1e-6)
        for actual, expected in zip(actual_bounds, expected_bounds, strict=True)
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion source coordinate-frame bounds drifted."
        )
    if (
        frame.battlefield_width_inches,
        frame.battlefield_depth_inches,
        frame.battlefield_origin,
        frame.battlefield_orientation,
        frame.coordinate_precision_decimal_places,
        frame.terrain_placement_increment_inches,
    ) != (
        BATTLEFIELD_WIDTH_INCHES,
        BATTLEFIELD_DEPTH_INCHES,
        "bottom_left",
        "x_right_along_44_inch_edge_y_up_along_60_inch_edge",
        6,
        TERRAIN_PLACEMENT_INCREMENT_INCHES,
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion source coordinate-frame semantics drifted."
        )


def _validate_archetypes(
    archetypes: tuple[TerrainFeatureArchetypeArtifact, ...],
) -> dict[str, TerrainFeatureArchetypeArtifact]:
    archetypes_by_id = _unique_by_id(
        "feature archetype",
        archetypes,
        lambda archetype: archetype.archetype_id,
    )
    if any(not archetype.source_assets for archetype in archetypes):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion feature archetypes require source-image assets."
        )
    by_primary_xref = _unique_by_id(
        "feature archetype primary source xref",
        archetypes,
        lambda archetype: archetype.source_assets[0].source_pdf_image_xref,
    )
    if set(by_primary_xref) != set(EXPECTED_ARCHETYPE_BY_PRIMARY_XREF):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion feature-archetype source-xref inventory drifted."
        )
    for xref, expected in EXPECTED_ARCHETYPE_BY_PRIMARY_XREF.items():
        archetype = by_primary_xref[xref]
        actual = (
            archetype.archetype_id,
            archetype.model_kind,
            archetype.feature_kind,
            archetype.classification,
            archetype.source_component_label,
        )
        if actual != expected:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion feature-archetype identity or semantics drifted."
            )
        assets_by_xref = _unique_by_id(
            "feature archetype source asset",
            archetype.source_assets,
            lambda asset: asset.source_pdf_image_xref,
        )
        if tuple(assets_by_xref) != EXPECTED_ARCHETYPE_SOURCE_XREFS[archetype.archetype_id]:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion feature-archetype source-asset aliases drifted."
            )
        for asset in archetype.source_assets:
            _validate_source_image_asset(asset)
        _validate_non_empty_strings(
            archetype.name,
            archetype.footprint_template_id,
            archetype.modeling_basis,
        )
        _validate_polygon(archetype.rules_footprint_polygon, within_battlefield=False)
        _validate_centered_archetype_polygon(archetype.rules_footprint_polygon)
        _validate_archetype_parts(archetype)
    return archetypes_by_id


def _validate_archetype_parts(archetype: TerrainFeatureArchetypeArtifact) -> None:
    wall_ids = _unique_by_id("archetype wall", archetype.walls, lambda wall: wall.wall_id)
    floor_ids = _unique_by_id("archetype floor", archetype.floors, lambda floor: floor.floor_id)
    for wall in wall_ids.values():
        _validate_finite_values(
            wall.center_x_inches,
            wall.center_y_inches,
            wall.bottom_z_inches,
            wall.width_inches,
            wall.depth_inches,
            wall.height_inches,
            wall.rotation_degrees,
        )
        if (
            min(
                wall.bottom_z_inches,
                wall.width_inches,
                wall.depth_inches,
                wall.height_inches,
            )
            < 0.0
            or min(wall.width_inches, wall.depth_inches, wall.height_inches) == 0.0
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion archetype wall dimensions are invalid."
            )
    for floor in floor_ids.values():
        _validate_finite_values(
            floor.center_x_inches,
            floor.center_y_inches,
            floor.bottom_z_inches,
            floor.width_inches,
            floor.depth_inches,
            floor.thickness_inches,
            floor.rotation_degrees,
        )
        if (
            min(
                floor.bottom_z_inches,
                floor.width_inches,
                floor.depth_inches,
                floor.thickness_inches,
            )
            < 0.0
            or min(floor.width_inches, floor.depth_inches, floor.thickness_inches) == 0.0
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion archetype floor dimensions are invalid."
            )
    if archetype.model_kind == "ruin":
        floor_levels = tuple(sorted(floor.bottom_z_inches for floor in archetype.floors))
        if floor_levels not in {(0.0, 3.0), (0.0, 3.0, 6.0)}:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion ruins require two or three explicit three-inch floor levels."
            )
        wall_levels = {wall.bottom_z_inches for wall in archetype.walls}
        if wall_levels != set(floor_levels):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion ruins require walls at every floor level."
            )
        top_floor_level = floor_levels[-1]
        if any(
            wall.height_inches != (2.0 if wall.bottom_z_inches == top_floor_level else 3.0)
            for wall in archetype.walls
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion ruins require solid three-inch walls below every upper "
                "floor and two-inch top-floor walls."
            )
    elif archetype.model_kind == "dense_solid":
        if (
            archetype.floors
            or not archetype.walls
            or any(
                wall.bottom_z_inches != 0.0 or wall.height_inches <= 2.0 for wall in archetype.walls
            )
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion dense non-ruin terrain requires solid bodies taller "
                "than two inches."
            )
    elif archetype.model_kind == "light_solid":
        if (
            archetype.floors
            or not archetype.walls
            or any(
                wall.bottom_z_inches != 0.0 or wall.height_inches != 2.0 for wall in archetype.walls
            )
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion light terrain requires explicit two-inch solid bodies."
            )
    else:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain archetype model kind is unsupported."
        )


def _validate_layout(
    layout: ExactBattlefieldLayoutArtifact,
    *,
    archetypes_by_id: dict[str, TerrainFeatureArchetypeArtifact],
) -> None:
    expected_layout_index = int(layout.layout_id.rsplit("-", maxsplit=1)[-1])
    if (
        layout.layout_letter,
        layout.source_page,
        layout.deployment_zone_template_number,
    ) != (
        "ABC"[expected_layout_index - 1],
        SOURCE_PAGES[expected_layout_index - 1],
        EXPECTED_DEPLOYMENT_TEMPLATES_BY_LAYOUT[layout.layout_id],
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion layout page, letter, or deployment template drifted."
        )
    _validate_non_empty_strings(
        layout.name,
        layout.source_layout_id,
        layout.attacker_edge,
        layout.defender_edge,
    )
    areas_by_id = _unique_by_id("terrain area", layout.terrain_areas, lambda area: area.area_id)
    if (
        len(areas_by_id) != 16
        or Counter(area.footprint_template_id for area in layout.terrain_areas)
        != EXPECTED_TERRAIN_TEMPLATE_COUNTS
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact layout terrain-area inventory drifted."
        )
    for area in layout.terrain_areas:
        _validate_terrain_area(area, areas_by_id=areas_by_id)
    components_by_id = _unique_by_id(
        "terrain component",
        layout.terrain_components,
        lambda component: component.component_id,
    )
    if (
        len(components_by_id) != 30
        or Counter(component.source_pdf_image_xref for component in layout.terrain_components)
        != EXPECTED_COMPONENT_XREF_COUNTS_BY_LAYOUT[layout.layout_id]
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact layout must preserve all 30 source terrain components."
        )
    for component in layout.terrain_components:
        _validate_component(
            component,
            areas_by_id=areas_by_id,
            archetypes_by_id=archetypes_by_id,
        )
    _validate_component_point_symmetry(components_by_id)
    _validate_area_classifications(
        layout.terrain_areas,
        layout.terrain_components,
        archetypes_by_id=archetypes_by_id,
    )
    _validate_objectives(
        layout.objectives,
        layout_id=layout.layout_id,
        areas_by_id=areas_by_id,
    )
    _validate_regions(layout)


def _validate_terrain_area(
    area: TerrainAreaArtifact,
    *,
    areas_by_id: dict[str, TerrainAreaArtifact],
) -> None:
    _validate_non_empty_strings(area.area_id, area.footprint_template_id, area.pose_basis)
    area_index = int(area.area_id.rsplit("-", maxsplit=1)[-1])
    if area.classification not in {"dense", "light", "mixed"}:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain-area classification is unsupported."
        )
    if area.local_transform not in {"identity", "mirror_y_axis"}:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain-area local transform is unsupported."
        )
    expected_vector_path = EXPECTED_VECTOR_PATH_PROVENANCE_BY_AREA.get(area.area_id)
    actual_vector_path = (
        area.source_pdf_vector_path_index_zero_based,
        area.source_pdf_vector_path_item_index_zero_based,
    )
    source_affine_is_orientation_reversing = (
        (area.source_pdf_affine.a * area.source_pdf_affine.d)
        - (area.source_pdf_affine.b * area.source_pdf_affine.c)
    ) < 0.0
    if (area.local_transform == "mirror_y_axis") is not source_affine_is_orientation_reversing:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain-area local reflection must match its source affine."
        )
    reflection_suffix = (
        "_with_source_affine_reflection" if source_affine_is_orientation_reversing else ""
    )
    reviewed_half_turn_suffix = (
        "_and_reviewed_half_turn"
        if source_affine_is_orientation_reversing and area.source_pdf_image_xref == 5506
        else ""
    )
    reviewed_point_symmetry_suffix = "_with_reviewed_point_symmetry" if area_index > 8 else ""
    if expected_vector_path is None:
        if area.pose_basis != (
            "reviewed_pdf_raster_template_registration"
            f"{reflection_suffix}{reviewed_half_turn_suffix}"
            f"{reviewed_point_symmetry_suffix}"
        ) or actual_vector_path != (None, None):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion terrain-area raster pose provenance drifted."
            )
    elif (
        area.pose_basis
        != (
            "reviewed_pdf_vector_path_reversed_long_edge"
            f"{reflection_suffix}{reviewed_half_turn_suffix}"
            f"{reviewed_point_symmetry_suffix}"
        )
        or actual_vector_path != expected_vector_path
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain-area vector-path pose provenance drifted."
        )
    _validate_terrain_placement_coordinates(area.anchor_x_inches, area.anchor_y_inches)
    _validate_finite_values(area.rotation_degrees)
    mirror = areas_by_id.get(area.mirror_area_id)
    if mirror is None or mirror.mirror_area_id != area.area_id:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain-area mirror pair is invalid."
        )
    if mirror.footprint_template_id != area.footprint_template_id:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion mirrored terrain areas require the same footprint template."
        )
    if area_index <= 8 and (
        not math.isclose(
            area.anchor_x_inches + mirror.anchor_x_inches,
            BATTLEFIELD_WIDTH_INCHES,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            area.anchor_y_inches + mirror.anchor_y_inches,
            BATTLEFIELD_DEPTH_INCHES,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or not math.isclose(
            (mirror.rotation_degrees - area.rotation_degrees) % 360.0,
            180.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        or mirror.local_transform != area.local_transform
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain-area mirror pairs must use exact point symmetry."
        )
    _validate_pdf_bounds(area.source_pdf_bounds)
    _validate_pdf_affine(area.source_pdf_affine)
    _validate_sha256("terrain-area source image SHA-256", area.source_image_sha256)
    _validate_sha256("terrain-area source soft-mask SHA-256", area.source_soft_mask_sha256)


def _validate_component(
    component: TerrainComponentPlacementArtifact,
    *,
    areas_by_id: dict[str, TerrainAreaArtifact],
    archetypes_by_id: dict[str, TerrainFeatureArchetypeArtifact],
) -> None:
    _validate_non_empty_strings(
        component.component_id,
        component.terrain_area_id,
        component.archetype_id,
    )
    area = areas_by_id.get(component.terrain_area_id)
    archetype = archetypes_by_id.get(component.archetype_id)
    if area is None or archetype is None:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain component references an unknown area or archetype."
        )
    if archetype.footprint_template_id != area.footprint_template_id:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain component archetype does not match its area template."
        )
    if component.source_pdf_image_xref not in {
        asset.source_pdf_image_xref for asset in archetype.source_assets
    }:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain component source xref drifted from its archetype."
        )
    if component.local_transform not in {"identity", "mirror_y_axis"}:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain component local transform is unsupported."
        )
    _validate_finite_values(
        component.local_offset_x_inches,
        component.local_offset_y_inches,
        component.local_rotation_degrees,
        component.battlefield_rotation_degrees,
    )
    _validate_terrain_placement_coordinates(
        component.battlefield_center_x_inches,
        component.battlefield_center_y_inches,
    )
    if not (
        0.0 <= component.battlefield_center_x_inches <= BATTLEFIELD_WIDTH_INCHES
        and 0.0 <= component.battlefield_center_y_inches <= BATTLEFIELD_DEPTH_INCHES
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain component center is outside the battlefield."
        )
    _validate_pdf_bounds(component.source_pdf_bounds)
    _validate_pdf_affine(component.source_pdf_affine)


def _validate_component_point_symmetry(
    components_by_id: dict[str, TerrainComponentPlacementArtifact],
) -> None:
    for component in components_by_id.values():
        area_prefix, component_suffix = component.component_id.rsplit(
            "-terrain-area-",
            maxsplit=1,
        )
        area_index_text, component_ordinal = component_suffix.split(
            "-component-",
            maxsplit=1,
        )
        area_index = int(area_index_text)
        if area_index > 8:
            continue
        mirror_component_id = (
            f"{area_prefix}-terrain-area-{17 - area_index:02d}-component-{component_ordinal}"
        )
        mirror = components_by_id.get(mirror_component_id)
        if mirror is None or (
            mirror.archetype_id != component.archetype_id
            or mirror.local_transform != component.local_transform
            or not math.isclose(
                component.battlefield_center_x_inches + mirror.battlefield_center_x_inches,
                BATTLEFIELD_WIDTH_INCHES,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                component.battlefield_center_y_inches + mirror.battlefield_center_y_inches,
                BATTLEFIELD_DEPTH_INCHES,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            or not math.isclose(
                (mirror.battlefield_rotation_degrees - component.battlefield_rotation_degrees)
                % 360.0,
                180.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion terrain-component mirror pairs must use exact point symmetry."
            )


def _validate_area_classifications(
    areas: tuple[TerrainAreaArtifact, ...],
    components: tuple[TerrainComponentPlacementArtifact, ...],
    *,
    archetypes_by_id: dict[str, TerrainFeatureArchetypeArtifact],
) -> None:
    classifications_by_area: dict[str, set[str]] = {area.area_id: set() for area in areas}
    for component in components:
        classifications_by_area[component.terrain_area_id].add(
            archetypes_by_id[component.archetype_id].classification
        )
    for area in areas:
        classifications = classifications_by_area[area.area_id]
        expected = next(iter(classifications)) if len(classifications) == 1 else "mixed"
        if not classifications or area.classification != expected:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion terrain-area classification does not match its components."
            )


def _validate_objectives(
    objectives: tuple[ObjectiveArtifact, ...],
    *,
    layout_id: str,
    areas_by_id: dict[str, TerrainAreaArtifact],
) -> None:
    objectives_by_id = _unique_by_id(
        "objective", objectives, lambda objective: objective.objective_id
    )
    roles = Counter(objective.role for objective in objectives)
    if len(objectives_by_id) != 6 or roles != Counter(
        {"attacker_home": 1, "defender_home": 1, "central": 2, "expansion": 2}
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion Meatgrinder objective-role inventory drifted."
        )
    expected_area_links = {
        f"{layout_id}-{objective_suffix}": (f"{layout_id}-terrain-area-{area_suffix}",)
        for objective_suffix, area_suffix in EXPECTED_OBJECTIVE_AREA_SUFFIXES_BY_LAYOUT[
            layout_id
        ].items()
    }
    if {
        objective.objective_id: objective.terrain_area_ids for objective in objectives
    } != expected_area_links:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion objective terrain-area mapping drifted."
        )
    for objective in objectives:
        _validate_non_empty_strings(
            objective.objective_id,
            objective.name,
            objective.source_symbol_kind,
        )
        _validate_finite_values(objective.x_inches, objective.y_inches)
        if not (
            0.0 <= objective.x_inches <= BATTLEFIELD_WIDTH_INCHES
            and 0.0 <= objective.y_inches <= BATTLEFIELD_DEPTH_INCHES
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion objective is outside the battlefield."
            )
        if not objective.terrain_area_ids or any(
            area_id not in areas_by_id for area_id in objective.terrain_area_ids
        ):
            raise EventCompanionExactSliceArtifactError(
                "Event Companion objective terrain-area reference is invalid."
            )


def _validate_regions(layout: ExactBattlefieldLayoutArtifact) -> None:
    deployment_by_role = _unique_by_id(
        "deployment zone role",
        layout.deployment_zones,
        lambda region: region.role,
    )
    territory_by_role = _unique_by_id(
        "territory role",
        layout.territories,
        lambda region: region.role,
    )
    if set(deployment_by_role) != {"attacker", "defender"}:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion deployment-zone role inventory drifted."
        )
    if set(territory_by_role) != {"attacker_territory", "defender_territory"}:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion territory role inventory drifted."
        )
    if layout.no_mans_land.role != "no_mans_land" or layout.no_mans_land.owner_role is not None:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion No Man's Land identity drifted."
        )
    for region in (*layout.deployment_zones, layout.no_mans_land, *layout.territories):
        _validate_non_empty_strings(region.shape_id, region.role, region.source_kind)
        if not region.polygons:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion battlefield region requires polygons."
            )
        for polygon in region.polygons:
            _validate_polygon(polygon, within_battlefield=True)


def _validate_polygon(
    polygon: tuple[PointArtifact, ...],
    *,
    within_battlefield: bool,
) -> None:
    if len(polygon) < 3:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion polygon requires at least three vertices."
        )
    if polygon[0] == polygon[-1]:
        raise EventCompanionExactSliceArtifactError("Event Companion polygons must be unclosed.")
    points = tuple((point.x_inches, point.y_inches) for point in polygon)
    _validate_finite_values(*(coordinate for point in points for coordinate in point))
    area = abs(
        sum(
            (x1 * y2) - (x2 * y1)
            for (x1, y1), (x2, y2) in zip(points, (*points[1:], points[0]), strict=True)
        )
        / 2.0
    )
    if area <= 1e-9:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion polygon requires non-zero area."
        )
    if within_battlefield and any(
        x < 0.0 or x > BATTLEFIELD_WIDTH_INCHES or y < 0.0 or y > BATTLEFIELD_DEPTH_INCHES
        for x, y in points
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion battlefield-region polygon is outside the battlefield."
        )


def _validate_centered_archetype_polygon(polygon: tuple[PointArtifact, ...]) -> None:
    x_values = tuple(point.x_inches for point in polygon)
    y_values = tuple(point.y_inches for point in polygon)
    if not (
        math.isclose(min(x_values) + max(x_values), 0.0, rel_tol=0.0, abs_tol=1e-6)
        and math.isclose(min(y_values) + max(y_values), 0.0, rel_tol=0.0, abs_tol=1e-6)
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain archetype footprints must be centered at the origin."
        )


def _validate_source_image_asset(asset: SourceImageAssetArtifact) -> None:
    if (
        type(asset.source_pdf_image_xref) is not int
        or asset.source_pdf_image_xref <= 0
        or type(asset.pixel_width) is not int
        or asset.pixel_width <= 0
        or type(asset.pixel_height) is not int
        or asset.pixel_height <= 0
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion source-image asset dimensions or xref are invalid."
        )
    _validate_sha256("source image SHA-256", asset.image_sha256)
    if (asset.soft_mask_xref is None) != (asset.soft_mask_sha256 is None):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion source-image soft-mask identity is incomplete."
        )
    if asset.soft_mask_xref is not None:
        if type(asset.soft_mask_xref) is not int or asset.soft_mask_xref <= 0:
            raise EventCompanionExactSliceArtifactError(
                "Event Companion source-image soft-mask xref is invalid."
            )
        _validate_sha256("source-image soft-mask SHA-256", asset.soft_mask_sha256)


def _validate_pdf_bounds(bounds: PdfBoundsArtifact) -> None:
    _validate_finite_values(
        bounds.x0_points,
        bounds.y0_points,
        bounds.x1_points,
        bounds.y1_points,
    )
    if bounds.x1_points <= bounds.x0_points or bounds.y1_points <= bounds.y0_points:
        raise EventCompanionExactSliceArtifactError("Event Companion PDF bounds are invalid.")


def _validate_pdf_affine(affine: PdfAffineArtifact) -> None:
    _validate_finite_values(affine.a, affine.b, affine.c, affine.d, affine.e, affine.f)
    if math.isclose((affine.a * affine.d) - (affine.b * affine.c), 0.0, abs_tol=1e-9):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion PDF affine transform must be invertible."
        )


def _unique_by_id[T, K](
    field_name: str,
    values: tuple[T, ...],
    identifier: Callable[[T], K],
) -> dict[K, T]:
    result: dict[K, T] = {}
    for value in values:
        key = identifier(value)
        if key in result:
            raise EventCompanionExactSliceArtifactError(
                f"Event Companion {field_name} IDs must be unique."
            )
        result[key] = value
    return result


def _validate_non_empty_strings(*values: object) -> None:
    if any(
        type(value) is not str or not value.strip() or value != value.strip() for value in values
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact-slice text values must be non-empty stripped strings."
        )


def _validate_finite_values(*values: object) -> None:
    if any(
        not isinstance(value, int | float) or type(value) is bool or not math.isfinite(float(value))
        for value in values
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact-slice coordinates must be finite numbers."
        )


def _validate_terrain_placement_coordinates(*values: float) -> None:
    _validate_finite_values(*values)
    if any(
        not math.isclose(
            value / TERRAIN_PLACEMENT_INCREMENT_INCHES,
            round(value / TERRAIN_PLACEMENT_INCREMENT_INCHES),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for value in values
    ):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion terrain placements must use 0.05-inch coordinate increments."
        )


def _validate_sha256(field_name: str, value: object) -> str:
    _validate_non_empty_strings(value)
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise EventCompanionExactSliceArtifactError(
            f"Event Companion exact-slice {field_name} must be lowercase SHA-256."
        )
    return value
