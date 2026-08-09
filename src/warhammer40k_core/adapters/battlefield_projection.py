from __future__ import annotations

import hashlib
from typing import Literal, TypedDict, cast

from warhammer40k_core.core.datasheet import BaseSizeKind
from warhammer40k_core.core.deployment_zones import (
    DeploymentZoneCircleCutout,
    DeploymentZonePolygonCutout,
    DeploymentZoneShape,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserves import ReserveStatus
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.measurement import millimeters_to_inches
from warhammer40k_core.geometry.model_geometry import BaseFootprintKind
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

BATTLEFIELD_VIEW_SCHEMA_VERSION = "battlefield-view-v2-phase17n"
BATTLEFIELD_COORDINATE_SPEC_VERSION = "battlefield-coordinate-v1"
BATTLEFIELD_COORDINATE_SPACE = "battlefield_inches_right_handed_z_up"


class BattlefieldPointPayload(TypedDict):
    x_inches: float
    y_inches: float


class BattlefieldPositionPayload(BattlefieldPointPayload):
    z_inches: float


class BattlefieldPosePayload(TypedDict):
    position: BattlefieldPositionPayload
    facing_degrees: float


class BattlefieldShapePayload(TypedDict):
    kind: Literal["circle", "ellipse", "rectangle", "polygon"]
    center: BattlefieldPointPayload | None
    rotation_degrees: float
    radius_inches: float | None
    length_inches: float | None
    width_inches: float | None
    vertices: list[BattlefieldPointPayload]


class BattlefieldBoundsPayload(TypedDict):
    min_x_inches: float
    min_y_inches: float
    min_z_inches: float
    max_x_inches: float
    max_y_inches: float


class BattlefieldModelGeometryPayload(TypedDict):
    measurement_basis: Literal["base", "hull"]
    measurement_shapes: list[BattlefieldShapePayload]
    support_shape: BattlefieldShapePayload
    height_inches: float
    geometry_source_kind: str
    geometry_source_id: str | None
    height_source_kind: str
    height_source_id: str | None


class BattlefieldModelStateContextPayload(TypedDict):
    transport_unit_instance_id: str | None
    reserve_kind: str | None


class BattlefieldModelEntityPayload(TypedDict):
    entity_kind: Literal["model"]
    model_instance_id: str
    unit_instance_id: str
    owner_player_id: str
    state: Literal["placed", "destroyed", "embarked", "reserves", "removed", "undeployed"]
    pose: BattlefieldPosePayload | None
    geometry: BattlefieldModelGeometryPayload
    state_context: BattlefieldModelStateContextPayload


class BattlefieldVolumePayload(TypedDict):
    volume_id: str
    volume_kind: Literal["wall", "floor"]
    bottom_center: BattlefieldPositionPayload
    width_inches: float
    depth_inches: float
    height_inches: float
    rotation_degrees: float


class BattlefieldTerrainFeatureEntityPayload(TypedDict):
    entity_kind: Literal["terrain_feature"]
    terrain_feature_id: str
    terrain_feature_kind: str
    classification: str
    footprint: BattlefieldShapePayload
    volumes: list[BattlefieldVolumePayload]
    source_id: str | None


class BattlefieldTerrainAreaEntityPayload(TypedDict):
    entity_kind: Literal["terrain_area"]
    terrain_area_id: str
    classification: str
    footprint: BattlefieldShapePayload
    source_id: str


class BattlefieldObjectiveEntityPayload(TypedDict):
    entity_kind: Literal["objective"]
    objective_id: str
    objective_role: str
    position: BattlefieldPositionPayload
    marker_diameter_inches: float
    measurement_anchor: str
    source_id: str


class BattlefieldRegionShapePayload(TypedDict):
    polygons: list[list[BattlefieldPointPayload]]
    circle_cutouts: list[BattlefieldShapePayload]
    polygon_cutouts: list[BattlefieldShapePayload]


class BattlefieldDeploymentZoneEntityPayload(TypedDict):
    entity_kind: Literal["deployment_zone"]
    deployment_zone_id: str
    owner_player_id: str
    shape: BattlefieldRegionShapePayload


class BattlefieldRegionEntityPayload(TypedDict):
    entity_kind: Literal["battlefield_region"]
    region_id: str
    region_kind: str
    owner_role: str | None
    shape: BattlefieldRegionShapePayload
    source_id: str


class BattlefieldAuthoritativeEntitiesPayload(TypedDict):
    models_by_id: dict[str, BattlefieldModelEntityPayload]
    terrain_features_by_id: dict[str, BattlefieldTerrainFeatureEntityPayload]
    terrain_areas_by_id: dict[str, BattlefieldTerrainAreaEntityPayload]
    objectives_by_id: dict[str, BattlefieldObjectiveEntityPayload]
    deployment_zones_by_id: dict[str, BattlefieldDeploymentZoneEntityPayload]
    battlefield_regions_by_id: dict[str, BattlefieldRegionEntityPayload]


class BattlefieldCandidateReferencePayload(TypedDict):
    reference_kind: Literal["decision_option"]
    reference_id: str


class BattlefieldMeasurementOverlayPayload(TypedDict):
    overlay_id: str
    start: BattlefieldPositionPayload
    end: BattlefieldPositionPayload
    distance_inches: float


class BattlefieldPathSegmentPayload(TypedDict):
    segment_kind: Literal["line"]
    start: BattlefieldPosePayload
    end: BattlefieldPosePayload


class BattlefieldPathOverlayPayload(TypedDict):
    overlay_id: str
    model_instance_id: str
    segments: list[BattlefieldPathSegmentPayload]


class BattlefieldInteractionPayload(TypedDict):
    request_id: str | None
    selected_or_acting_entity_ids: list[str]
    legal_candidate_refs: list[BattlefieldCandidateReferencePayload]
    measurement_overlays: list[BattlefieldMeasurementOverlayPayload]
    path_overlays: list[BattlefieldPathOverlayPayload]


class BattlefieldHitRegionPayload(TypedDict):
    entity_id: str
    shape: BattlefieldShapePayload


class BattlefieldRenderHintPayload(TypedDict):
    entity_id: str
    asset_id: str | None


class BattlefieldRenderPayload(TypedDict):
    hit_regions_by_entity_id: dict[str, BattlefieldHitRegionPayload]
    hints_by_entity_id: dict[str, BattlefieldRenderHintPayload]


class BattlefieldViewPayload(TypedDict):
    schema_version: str
    coordinate_spec_version: str
    coordinate_space: str
    battlefield_id: str
    bounds: BattlefieldBoundsPayload
    authoritative_geometry_hash: str
    authoritative: BattlefieldAuthoritativeEntitiesPayload
    interaction: BattlefieldInteractionPayload
    render: BattlefieldRenderPayload


def project_battlefield_view(
    *,
    state: GameState,
    visible_model_ids: frozenset[str],
    pending_request_id: str | None,
    selected_entity_ids: tuple[str, ...],
    legal_option_ids: tuple[str, ...],
) -> BattlefieldViewPayload | None:
    if type(state) is not GameState:
        raise GameLifecycleError("Battlefield projection requires GameState.")
    if type(visible_model_ids) is not frozenset or any(
        type(model_id) is not str or not model_id for model_id in visible_model_ids
    ):
        raise GameLifecycleError("Battlefield projection visible model IDs are invalid.")
    battlefield = state.battlefield_state
    mission = state.mission_setup
    if battlefield is None or mission is None:
        return None
    if battlefield.battlefield_width_inches != mission.battlefield_width_inches:
        raise GameLifecycleError("Battlefield and mission widths drifted.")
    if battlefield.battlefield_depth_inches != mission.battlefield_depth_inches:
        raise GameLifecycleError("Battlefield and mission depths drifted.")

    authoritative: BattlefieldAuthoritativeEntitiesPayload = {
        "models_by_id": _model_entities(state=state, visible_model_ids=visible_model_ids),
        "terrain_features_by_id": {
            feature.feature_id: _terrain_feature_entity(feature)
            for feature in sorted(battlefield.terrain_features, key=lambda item: item.feature_id)
        },
        "terrain_areas_by_id": {
            area.terrain_area_id: {
                "entity_kind": "terrain_area",
                "terrain_area_id": area.terrain_area_id,
                "classification": area.classification.value,
                "footprint": _polygon_shape(
                    tuple((point.x_inches, point.y_inches) for point in area.footprint_polygon)
                ),
                "source_id": area.source_id,
            }
            for area in sorted(mission.terrain_areas, key=lambda item: item.terrain_area_id)
        },
        "objectives_by_id": {
            marker.objective_marker_id: {
                "entity_kind": "objective",
                "objective_id": marker.objective_marker_id,
                "objective_role": marker.objective_role.value,
                "position": _position(marker.x_inches, marker.y_inches, marker.z_inches),
                "marker_diameter_inches": millimeters_to_inches(marker.marker_diameter_mm),
                "measurement_anchor": marker.measurement_anchor,
                "source_id": marker.source_id,
            }
            for marker in sorted(
                mission.objective_markers,
                key=lambda item: item.objective_marker_id,
            )
        },
        "deployment_zones_by_id": {
            zone.deployment_zone_id: {
                "entity_kind": "deployment_zone",
                "deployment_zone_id": zone.deployment_zone_id,
                "owner_player_id": zone.player_id,
                "shape": _region_shape(zone.shape),
            }
            for zone in sorted(
                mission.deployment_zones,
                key=lambda item: item.deployment_zone_id,
            )
        },
        "battlefield_regions_by_id": {
            region.region_id: {
                "entity_kind": "battlefield_region",
                "region_id": region.region_id,
                "region_kind": region.region_kind.value,
                "owner_role": region.owner_role,
                "shape": _region_shape(region.shape),
                "source_id": region.source_id,
            }
            for region in sorted(mission.battlefield_regions, key=lambda item: item.region_id)
        },
    }
    bounds: BattlefieldBoundsPayload = {
        "min_x_inches": 0.0,
        "min_y_inches": 0.0,
        "min_z_inches": 0.0,
        "max_x_inches": battlefield.battlefield_width_inches,
        "max_y_inches": battlefield.battlefield_depth_inches,
    }
    render = _render_payload(battlefield.terrain_features)
    return {
        "schema_version": BATTLEFIELD_VIEW_SCHEMA_VERSION,
        "coordinate_spec_version": BATTLEFIELD_COORDINATE_SPEC_VERSION,
        "coordinate_space": BATTLEFIELD_COORDINATE_SPACE,
        "battlefield_id": battlefield.battlefield_id,
        "bounds": bounds,
        "authoritative_geometry_hash": authoritative_geometry_hash(
            bounds=bounds,
            authoritative=authoritative,
        ),
        "authoritative": authoritative,
        "interaction": {
            "request_id": pending_request_id,
            "selected_or_acting_entity_ids": list(selected_entity_ids),
            "legal_candidate_refs": [
                {
                    "reference_kind": "decision_option",
                    "reference_id": option_id,
                }
                for option_id in legal_option_ids
            ],
            "measurement_overlays": [],
            "path_overlays": [],
        },
        "render": render,
    }


def _model_entities(
    *,
    state: GameState,
    visible_model_ids: frozenset[str],
) -> dict[str, BattlefieldModelEntityPayload]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Battlefield model projection requires battlefield state.")
    placement_by_model_id = {
        placement.model_instance_id: placement
        for army in battlefield.placed_armies
        for unit in army.unit_placements
        for placement in unit.model_placements
    }
    reserve_by_unit_id = {reserve.unit_instance_id: reserve for reserve in state.reserve_states}
    transport_by_embarked_unit_id = {
        unit_id: cargo.transport_unit_instance_id
        for cargo in state.transport_cargo_states
        for unit_id in cargo.embarked_unit_instance_ids
    }
    removed_model_ids = frozenset(battlefield.removed_model_ids)
    projected: dict[str, BattlefieldModelEntityPayload] = {}
    for army in state.army_definitions:
        for unit in army.units:
            reserve = reserve_by_unit_id.get(unit.unit_instance_id)
            transport_unit_id = transport_by_embarked_unit_id.get(unit.unit_instance_id)
            for model in unit.own_models:
                if model.model_instance_id not in visible_model_ids:
                    continue
                placement = placement_by_model_id.get(model.model_instance_id)
                state_token = _model_state(
                    model=model,
                    placement_exists=placement is not None,
                    removed=model.model_instance_id in removed_model_ids,
                    transport_unit_id=transport_unit_id,
                    reserve_status=None if reserve is None else reserve.status,
                )
                projected[model.model_instance_id] = {
                    "entity_kind": "model",
                    "model_instance_id": model.model_instance_id,
                    "unit_instance_id": unit.unit_instance_id,
                    "owner_player_id": army.player_id,
                    "state": state_token,
                    "pose": None if placement is None else _pose(placement.pose),
                    "geometry": _model_geometry(model),
                    "state_context": {
                        "transport_unit_instance_id": transport_unit_id,
                        "reserve_kind": None if reserve is None else reserve.reserve_kind.value,
                    },
                }
    return dict(sorted(projected.items()))


def _model_state(
    *,
    model: ModelInstance,
    placement_exists: bool,
    removed: bool,
    transport_unit_id: str | None,
    reserve_status: ReserveStatus | None,
) -> Literal["placed", "destroyed", "embarked", "reserves", "removed", "undeployed"]:
    if reserve_status is ReserveStatus.DESTROYED or model.wounds_remaining == 0:
        return "destroyed"
    if removed:
        return "removed"
    if transport_unit_id is not None:
        return "embarked"
    if reserve_status is ReserveStatus.IN_RESERVES:
        return "reserves"
    if placement_exists:
        return "placed"
    return "undeployed"


def _model_geometry(model: ModelInstance) -> BattlefieldModelGeometryPayload:
    measurement_shapes = [
        _footprint_part_shape(
            kind=part.footprint_kind,
            radius_x=part.radius_x_inches,
            radius_y=part.radius_y_inches,
            offset_x=part.offset_x_inches,
            offset_y=part.offset_y_inches,
        )
        for part in model.geometry.parts
    ]
    return {
        "measurement_basis": (
            "hull" if model.geometry.footprint_kind is BaseFootprintKind.HULL else "base"
        ),
        "measurement_shapes": measurement_shapes,
        "support_shape": _support_shape(model),
        "height_inches": model.geometry.height_inches,
        "geometry_source_kind": model.geometry.geometry_source_kind.value,
        "geometry_source_id": model.geometry.geometry_source_id,
        "height_source_kind": model.geometry.height_source_kind.value,
        "height_source_id": model.geometry.height_source_id,
    }


def _footprint_part_shape(
    *,
    kind: BaseFootprintKind,
    radius_x: float,
    radius_y: float,
    offset_x: float,
    offset_y: float,
) -> BattlefieldShapePayload:
    center = (offset_x, offset_y)
    if kind is BaseFootprintKind.CIRCULAR:
        return _circle_shape(radius_x, center=center)
    if kind is BaseFootprintKind.OVAL:
        return _ellipse_shape(length=radius_x * 2.0, width=radius_y * 2.0, center=center)
    if kind in {BaseFootprintKind.RECTANGULAR, BaseFootprintKind.HULL}:
        return _rectangle_shape(
            length=radius_x * 2.0,
            width=radius_y * 2.0,
            center=center,
        )
    raise GameLifecycleError("Model footprint geometry is unsupported by battlefield projection.")


def _support_shape(model: ModelInstance) -> BattlefieldShapePayload:
    base_size = model.base_size
    if base_size.kind is BaseSizeKind.CIRCULAR and base_size.diameter_mm is not None:
        return _circle_shape(
            millimeters_to_inches(base_size.diameter_mm) / 2.0,
            center=(0.0, 0.0),
        )
    if (
        base_size.kind in {BaseSizeKind.OVAL, BaseSizeKind.RECTANGULAR}
        and base_size.length_mm is not None
        and base_size.width_mm is not None
    ):
        length = millimeters_to_inches(base_size.length_mm)
        width = millimeters_to_inches(base_size.width_mm)
        if base_size.kind is BaseSizeKind.OVAL:
            return _ellipse_shape(length=length, width=width, center=(0.0, 0.0))
        return _rectangle_shape(length=length, width=width, center=(0.0, 0.0))
    raise GameLifecycleError("Model support geometry is unsupported by battlefield projection.")


def _terrain_feature_entity(
    feature: TerrainFeatureDefinition,
) -> BattlefieldTerrainFeatureEntityPayload:
    if type(feature) is not TerrainFeatureDefinition:
        raise GameLifecycleError("Terrain feature projection requires TerrainFeatureDefinition.")
    volumes: list[BattlefieldVolumePayload] = [
        {
            "volume_id": wall.wall_id,
            "volume_kind": "wall",
            "bottom_center": _position(
                wall.center_x_inches,
                wall.center_y_inches,
                wall.bottom_z_inches,
            ),
            "width_inches": wall.width_inches,
            "depth_inches": wall.depth_inches,
            "height_inches": wall.height_inches,
            "rotation_degrees": wall.rotation_degrees % 360.0,
        }
        for wall in feature.walls
    ]
    volumes.extend(
        {
            "volume_id": floor.floor_id,
            "volume_kind": "floor",
            "bottom_center": _position(
                floor.center_x_inches,
                floor.center_y_inches,
                floor.bottom_z_inches,
            ),
            "width_inches": floor.width_inches,
            "depth_inches": floor.depth_inches,
            "height_inches": floor.thickness_inches,
            "rotation_degrees": floor.rotation_degrees % 360.0,
        }
        for floor in feature.floors
    )
    return {
        "entity_kind": "terrain_feature",
        "terrain_feature_id": feature.feature_id,
        "terrain_feature_kind": feature.feature_kind.value,
        "classification": feature.classification.value,
        "footprint": _polygon_shape(
            tuple((point.x_inches, point.y_inches) for point in feature.rules_footprint_polygon)
        ),
        "volumes": sorted(volumes, key=lambda item: (item["volume_kind"], item["volume_id"])),
        "source_id": feature.source_id,
    }


def _render_payload(
    features: tuple[TerrainFeatureDefinition, ...],
) -> BattlefieldRenderPayload:
    hit_regions: dict[str, BattlefieldHitRegionPayload] = {}
    hints: dict[str, BattlefieldRenderHintPayload] = {}
    for feature in sorted(features, key=lambda item: item.feature_id):
        display = feature.display_geometry
        hit_regions[feature.feature_id] = {
            "entity_id": feature.feature_id,
            "shape": _polygon_shape(
                tuple((point.x_inches, point.y_inches) for point in display.footprint_polygon)
            ),
        }
        hints[feature.feature_id] = {
            "entity_id": feature.feature_id,
            "asset_id": display.display_template_id,
        }
    return {
        "hit_regions_by_entity_id": hit_regions,
        "hints_by_entity_id": hints,
    }


def _region_shape(shape: DeploymentZoneShape) -> BattlefieldRegionShapePayload:
    if type(shape) is not DeploymentZoneShape:
        raise GameLifecycleError("Battlefield region projection requires DeploymentZoneShape.")
    circle_cutouts: list[BattlefieldShapePayload] = []
    polygon_cutouts: list[BattlefieldShapePayload] = []
    for cutout in shape.cutouts:
        if type(cutout) is DeploymentZoneCircleCutout:
            circle_cutouts.append(
                _circle_shape(
                    cutout.radius,
                    center=(cutout.center_x, cutout.center_y),
                )
            )
        elif type(cutout) is DeploymentZonePolygonCutout:
            polygon_cutouts.append(
                _polygon_shape(tuple((point.x, point.y) for point in cutout.vertices))
            )
        else:
            raise GameLifecycleError("Deployment-zone cutout geometry is unsupported.")
    return {
        "polygons": [
            _normalized_polygon(tuple((point.x, point.y) for point in polygon.vertices))
            for polygon in shape.polygons
        ],
        "circle_cutouts": circle_cutouts,
        "polygon_cutouts": polygon_cutouts,
    }


def _circle_shape(
    radius: float,
    *,
    center: tuple[float, float],
) -> BattlefieldShapePayload:
    return {
        "kind": "circle",
        "center": _point(*center),
        "rotation_degrees": 0.0,
        "radius_inches": radius,
        "length_inches": None,
        "width_inches": None,
        "vertices": [],
    }


def _ellipse_shape(
    *,
    length: float,
    width: float,
    center: tuple[float, float],
) -> BattlefieldShapePayload:
    return {
        "kind": "ellipse",
        "center": _point(*center),
        "rotation_degrees": 0.0,
        "radius_inches": None,
        "length_inches": length,
        "width_inches": width,
        "vertices": [],
    }


def _rectangle_shape(
    *,
    length: float,
    width: float,
    center: tuple[float, float],
    rotation_degrees: float = 0.0,
) -> BattlefieldShapePayload:
    return {
        "kind": "rectangle",
        "center": _point(*center),
        "rotation_degrees": rotation_degrees % 360.0,
        "radius_inches": None,
        "length_inches": length,
        "width_inches": width,
        "vertices": [],
    }


def _polygon_shape(points: tuple[tuple[float, float], ...]) -> BattlefieldShapePayload:
    return {
        "kind": "polygon",
        "center": None,
        "rotation_degrees": 0.0,
        "radius_inches": None,
        "length_inches": None,
        "width_inches": None,
        "vertices": _normalized_polygon(points),
    }


def _normalized_polygon(points: tuple[tuple[float, float], ...]) -> list[BattlefieldPointPayload]:
    if len(points) < 3:
        raise GameLifecycleError("Battlefield polygon requires at least three vertices.")
    area = sum(
        (point[0] * points[(index + 1) % len(points)][1])
        - (points[(index + 1) % len(points)][0] * point[1])
        for index, point in enumerate(points)
    )
    if area == 0.0:
        raise GameLifecycleError("Battlefield polygon requires non-zero area.")
    ordered = points if area > 0.0 else tuple(reversed(points))
    return [_point(x, y) for x, y in ordered]


def _point(x: float, y: float) -> BattlefieldPointPayload:
    return {"x_inches": float(x), "y_inches": float(y)}


def _position(x: float, y: float, z: float) -> BattlefieldPositionPayload:
    return {
        "x_inches": float(x),
        "y_inches": float(y),
        "z_inches": float(z),
    }


def _pose(pose: Pose) -> BattlefieldPosePayload:
    if type(pose) is not Pose:
        raise GameLifecycleError("Battlefield pose projection requires Pose.")
    return {
        "position": _position(pose.position.x, pose.position.y, pose.position.z),
        "facing_degrees": pose.facing.degrees,
    }


def authoritative_geometry_hash(
    *,
    bounds: BattlefieldBoundsPayload,
    authoritative: BattlefieldAuthoritativeEntitiesPayload,
) -> str:
    payload = validate_json_value(
        {
            "coordinate_spec_version": BATTLEFIELD_COORDINATE_SPEC_VERSION,
            "bounds": cast(JsonValue, bounds),
            "authoritative": cast(JsonValue, authoritative),
        }
    )
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
