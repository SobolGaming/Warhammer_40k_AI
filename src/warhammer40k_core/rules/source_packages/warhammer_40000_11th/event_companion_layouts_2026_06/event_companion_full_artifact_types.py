from __future__ import annotations

import msgspec

ARTIFACT_SCHEMA = "core-v2-event-companion-full-battlefield-layouts-v1"


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
    runtime_exact_seam_closure_precision_decimal_places: int


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


class SourceImageAssetArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_pdf_image_xref: int
    image_sha256: str
    pixel_width: int
    pixel_height: int
    soft_mask_xref: int | None
    soft_mask_sha256: str | None


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


class TerrainAreaArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    area_id: str
    source_area_id: str
    footprint_template_id: str
    classification: str
    anchor_x_inches: float
    anchor_y_inches: float
    rotation_degrees: float
    local_transform: str
    local_transform_basis: str
    pose_basis: str
    source_pose_candidate_index: int
    source_anchor_x_inches: float
    source_anchor_y_inches: float
    source_rotation_degrees: float
    source_pose_fit_residual_inches: float | None
    runtime_adjustment_x_inches: float
    runtime_adjustment_y_inches: float
    runtime_rotation_adjustment_degrees: float
    source_pdf_extended_drawing_index_zero_based: int
    source_pdf_seqno: int
    source_pdf_vector_item_count: int
    mirror_area_id: str
    source_mirror_area_id: str
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
    source_component_id: str
    terrain_area_id: str
    mirror_component_id: str | None
    source_mirror_component_id: str | None
    archetype_id: str
    local_offset_x_inches: float
    local_offset_y_inches: float
    local_rotation_degrees: float
    local_transform: str
    local_transform_basis: str
    pose_basis: str
    source_battlefield_center_x_inches: float
    source_battlefield_center_y_inches: float
    source_battlefield_rotation_degrees: float
    runtime_adjustment_x_inches: float
    runtime_adjustment_y_inches: float
    runtime_rotation_adjustment_degrees: float
    battlefield_center_x_inches: float
    battlefield_center_y_inches: float
    battlefield_rotation_degrees: float
    source_pdf_image_xref: int
    source_pdf_bounds: PdfBoundsArtifact
    source_pdf_affine: PdfAffineArtifact


class ObjectiveArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    objective_id: str
    source_objective_id: str
    name: str
    role: str
    x_inches: float
    y_inches: float
    terrain_area_ids: tuple[str, ...]
    source_symbol_kind: str


class TerrainAreaContactArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    terrain_area_ids: tuple[str, str]
    source_terrain_area_ids: tuple[str, str]
    kind: str
    source_icon_ids: tuple[str, ...]
    source_pdf_drawing_indices_zero_based: tuple[int, ...]
    source_pdf_seqnos: tuple[int, ...]
    source_icon_x_inches: float
    source_icon_y_inches: float
    source_pair_gap_inches: float
    runtime_pair_gap_inches: float
    runtime_pair_overlap_square_inches: float


class BattlefieldShapeArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    shape_id: str
    role: str
    owner_role: str | None
    polygons: tuple[tuple[PointArtifact, ...], ...]
    source_kind: str


class BattlefieldLayoutArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    layout_id: str
    layout_letter: str
    name: str
    source_layout_id: str
    source_page: int
    force_disposition_pair: tuple[str, str]
    primary_missions: tuple[str, str]
    deployment_zone_template_number: int
    attacker_edge: str
    defender_edge: str
    terrain_areas: tuple[TerrainAreaArtifact, ...]
    terrain_components: tuple[TerrainComponentPlacementArtifact, ...]
    terrain_area_contacts: tuple[TerrainAreaContactArtifact, ...]
    terrain_component_contact_pairs: tuple[tuple[str, str], ...]
    objectives: tuple[ObjectiveArtifact, ...]
    deployment_zones: tuple[BattlefieldShapeArtifact, ...]
    no_mans_land: BattlefieldShapeArtifact
    territories: tuple[BattlefieldShapeArtifact, ...]


class EventCompanionBattlefieldArtifact(
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
    feature_archetypes: tuple[TerrainFeatureArchetypeArtifact, ...]
    layouts: tuple[BattlefieldLayoutArtifact, ...]
    package_hash: str


__all__ = [
    "ARTIFACT_SCHEMA",
    "BattlefieldLayoutArtifact",
    "BattlefieldShapeArtifact",
    "EventCompanionBattlefieldArtifact",
    "ObjectiveArtifact",
    "PdfAffineArtifact",
    "PdfBoundsArtifact",
    "PointArtifact",
    "SourceCoordinateFrameArtifact",
    "SourceImageAssetArtifact",
    "TerrainAreaArtifact",
    "TerrainAreaContactArtifact",
    "TerrainComponentPlacementArtifact",
    "TerrainFeatureArchetypeArtifact",
    "TerrainFloorArtifact",
    "TerrainWallArtifact",
]
