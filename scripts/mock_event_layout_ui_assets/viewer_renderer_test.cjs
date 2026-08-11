"use strict";

const fs = require("node:fs");
const geometry = require("./viewer_geometry.js");

const VIEWPORT_WIDTH = 1280;
const VIEWPORT_HEIGHT = 720;
const CLOSE_CAMERA = Object.freeze({
  azimuth: 315 * geometry.DEG_TO_RAD,
  elevation: 12 * geometry.DEG_TO_RAD,
  zoom: 3.5,
});

const payload = JSON.parse(fs.readFileSync(0, "utf8"));
const layoutId = "purge-the-foe-vs-purge-the-foe-layout-1";
const layout = payload.layouts[layoutId];
if (layout === undefined) {
  throw new Error(`Renderer regression layout is missing: ${layoutId}.`);
}
const view = layout.battlefield_view;
const authoritative = view.authoritative;
const closeCamera = geometry.cameraForBounds(
  view.bounds,
  VIEWPORT_WIDTH,
  VIEWPORT_HEIGHT,
  CLOSE_CAMERA,
);

const boardVisible = projectBoard(view.bounds, closeCamera) !== null;
const terrainArea14 = authoritative.terrain_areas_by_id[`${layoutId}-terrain-area-14`];
if (terrainArea14 === undefined) {
  throw new Error("Renderer regression terrain area 14 is missing.");
}
const terrainArea14Visible = projectShape(terrainArea14.footprint, 0.04, closeCamera) !== null;
const defenderZone = Object.values(authoritative.deployment_zones_by_id).find(
  (zone) => zone.owner_player_id === "viewer-defender",
);
if (defenderZone === undefined) {
  throw new Error("Renderer regression defender deployment zone is missing.");
}
const defenderTerritory = Object.values(authoritative.battlefield_regions_by_id).find(
  (region) => region.region_kind === "territory" && region.owner_role === "defender",
);
if (defenderTerritory === undefined) {
  throw new Error("Renderer regression defender territory is missing.");
}
const territoryDividerSegmentsByLayout = {};
for (let layoutNumber = 1; layoutNumber <= 3; layoutNumber += 1) {
  const testedLayoutId = `purge-the-foe-vs-purge-the-foe-layout-${String(layoutNumber)}`;
  const testedLayout = payload.layouts[testedLayoutId];
  if (testedLayout === undefined) {
    throw new Error(`Territory-divider regression layout is missing: ${testedLayoutId}.`);
  }
  const segments = geometry.sharedTerritoryBoundarySegments(
    testedLayout.battlefield_view.authoritative.battlefield_regions_by_id,
  );
  if (segments.length !== 1) {
    throw new Error(
      `Territory-divider regression expected one shared segment for ${testedLayoutId}.`,
    );
  }
  territoryDividerSegmentsByLayout[String(layoutNumber)] = segments.length;
}
const closeCameraTerritoryDividerVisible = geometry
  .sharedTerritoryBoundarySegments(authoritative.battlefield_regions_by_id)
  .some((segment) =>
    geometry.clipWorldLineToNearPlane(
      geometry.worldPoint(segment.start.x_inches, segment.start.y_inches, 0.022),
      geometry.worldPoint(segment.end.x_inches, segment.end.y_inches, 0.022),
      closeCamera,
    ) !== null,
  );

const fullCatalogProjectionCounts = {
  layouts: 0,
  terrain_areas: 0,
  terrain_features: 0,
  terrain_area_contacts: 0,
  deployment_zones: 0,
  battlefield_regions: 0,
  objective_binding_records: 0,
  objective_binding_areas: 0,
};
for (const [testedLayoutId, testedLayout] of Object.entries(payload.layouts)) {
  const testedView = testedLayout.battlefield_view;
  const testedAuthoritative = testedView.authoritative;
  const cameras = [
    geometry.cameraForBounds(testedView.bounds, VIEWPORT_WIDTH, VIEWPORT_HEIGHT, {
      azimuth: 315 * geometry.DEG_TO_RAD,
      elevation: 55 * geometry.DEG_TO_RAD,
      zoom: 1.1,
    }),
    geometry.cameraForBounds(testedView.bounds, VIEWPORT_WIDTH, VIEWPORT_HEIGHT, {
      azimuth: 270 * geometry.DEG_TO_RAD,
      elevation: 88 * geometry.DEG_TO_RAD,
      zoom: 1.1,
    }),
  ];
  for (const camera of cameras) {
    if (projectBoard(testedView.bounds, camera) === null) {
      throw new Error(`Full-catalog board did not project for ${testedLayoutId}.`);
    }
  }
  for (const area of Object.values(testedAuthoritative.terrain_areas_by_id)) {
    if (
      typeof area.logical_terrain_area_id !== "string"
      || area.logical_terrain_area_id.length === 0
    ) {
      throw new Error(`Full-catalog terrain area lacks logical identity: ${area.terrain_area_id}.`);
    }
    requireProjectedShape(area.footprint, 0.04, cameras, area.terrain_area_id);
    fullCatalogProjectionCounts.terrain_areas += 1;
  }
  for (const feature of Object.values(testedAuthoritative.terrain_features_by_id)) {
    requireProjectedShape(feature.footprint, 0.075, cameras, feature.terrain_feature_id);
    fullCatalogProjectionCounts.terrain_features += 1;
  }
  for (const contact of testedLayout.terrain_area_contacts) {
    const [firstAreaId, secondAreaId] = contact.terrain_area_ids;
    const firstArea = testedAuthoritative.terrain_areas_by_id[firstAreaId];
    const secondArea = testedAuthoritative.terrain_areas_by_id[secondAreaId];
    if (firstArea === undefined || secondArea === undefined) {
      throw new Error(`Full-catalog contact references unknown areas for ${testedLayoutId}.`);
    }
    const sharesLogicalArea =
      firstArea.logical_terrain_area_id === secondArea.logical_terrain_area_id;
    if (sharesLogicalArea !== (contact.kind === "single")) {
      throw new Error(`Full-catalog logical terrain grouping drifted for ${testedLayoutId}.`);
    }
    const sourceX = contact.source_icon_x_inches;
    const sourceY = contact.source_icon_y_inches;
    if (
      !Array.isArray(contact.source_icon_ids)
      || contact.source_icon_ids.length !== 1
      || typeof contact.source_icon_ids[0] !== "string"
      || contact.source_icon_ids[0].length === 0
      || typeof sourceX !== "number"
      || !Number.isFinite(sourceX)
      || sourceX < 0
      || sourceX > 44
      || Math.abs(sourceX / 0.05 - Math.round(sourceX / 0.05)) > 0.000001
      || typeof sourceY !== "number"
      || !Number.isFinite(sourceY)
      || sourceY < 0
      || sourceY > 60
      || Math.abs(sourceY / 0.05 - Math.round(sourceY / 0.05)) > 0.000001
      || typeof contact.source_pair_gap_inches !== "number"
      || !Number.isFinite(contact.source_pair_gap_inches)
      || contact.source_pair_gap_inches < 0
    ) {
      throw new Error(`Full-catalog terrain source contact is invalid for ${testedLayoutId}.`);
    }
    const runtimeGapLimit = 0.050001;
    if (
      typeof contact.runtime_pair_gap_inches !== "number"
      || !Number.isFinite(contact.runtime_pair_gap_inches)
      || contact.runtime_pair_gap_inches < 0
      || contact.runtime_pair_gap_inches > runtimeGapLimit
      || typeof contact.runtime_pair_overlap_square_inches !== "number"
      || !Number.isFinite(contact.runtime_pair_overlap_square_inches)
      || contact.runtime_pair_overlap_square_inches < 0
      || contact.runtime_pair_overlap_square_inches > 0.000001
    ) {
      throw new Error(`Full-catalog terrain seam violates its closure tolerance for ${testedLayoutId}.`);
    }
    for (const camera of cameras) {
      const projected = geometry.projectPoint(
        geometry.worldPoint(contact.source_icon_x_inches, contact.source_icon_y_inches, 0.11),
        camera,
      );
      if (projected === null) {
        throw new Error(
          `Full-catalog terrain-area contact did not project for ${testedLayoutId}.`,
        );
      }
    }
    fullCatalogProjectionCounts.terrain_area_contacts += 1;
  }
  for (const zone of Object.values(testedAuthoritative.deployment_zones_by_id)) {
    for (const camera of cameras) {
      if (!projectRegion(zone.shape, 0.025, camera)) {
        throw new Error(`Full-catalog deployment zone did not project: ${zone.deployment_zone_id}.`);
      }
    }
    fullCatalogProjectionCounts.deployment_zones += 1;
  }
  for (const region of Object.values(testedAuthoritative.battlefield_regions_by_id)) {
    for (const camera of cameras) {
      if (!projectRegion(region.shape, 0.015, camera)) {
        throw new Error(`Full-catalog battlefield region did not project: ${region.region_id}.`);
      }
    }
    fullCatalogProjectionCounts.battlefield_regions += 1;
  }
  for (const binding of testedLayout.objective_terrain_areas) {
    fullCatalogProjectionCounts.objective_binding_records += 1;
    for (const areaId of binding.terrain_area_ids) {
      const area = testedAuthoritative.terrain_areas_by_id[areaId];
      if (area === undefined) {
        throw new Error(`Full-catalog objective binding references unknown area: ${areaId}.`);
      }
      requireProjectedShape(area.footprint, 0.055, cameras, areaId);
      fullCatalogProjectionCounts.objective_binding_areas += 1;
    }
  }
  fullCatalogProjectionCounts.layouts += 1;
}
if (fullCatalogProjectionCounts.layouts !== 45) {
  throw new Error("Full-catalog renderer regression requires all 45 layouts.");
}

const hatchEntities = [
  ...Object.values(authoritative.terrain_areas_by_id).map((area) => ({
    entityId: area.terrain_area_id,
    shape: area.footprint,
    classification: area.classification,
    z: 0.04,
  })),
  ...Object.values(authoritative.terrain_features_by_id).map((feature) => ({
    entityId: feature.terrain_feature_id,
    shape: feature.footprint,
    classification: feature.classification,
    z: 0.075,
  })),
];

let maximumHatchStrokes = 0;
let maximumEntityId = null;
let maximumAzimuthDegrees = null;
for (let azimuthDegrees = 0; azimuthDegrees < 360; azimuthDegrees += 1) {
  const camera = geometry.cameraForBounds(
    view.bounds,
    VIEWPORT_WIDTH,
    VIEWPORT_HEIGHT,
    {
      azimuth: azimuthDegrees * geometry.DEG_TO_RAD,
      elevation: CLOSE_CAMERA.elevation,
      zoom: CLOSE_CAMERA.zoom,
    },
  );
  for (const entity of hatchEntities) {
    const projected = projectShape(entity.shape, entity.z, camera);
    if (projected === null) {
      continue;
    }
    const hatchStrokes = geometry.hatchLineSegments(
      projected,
      entity.classification,
      { width: VIEWPORT_WIDTH, height: VIEWPORT_HEIGHT },
    ).length;
    if (hatchStrokes > maximumHatchStrokes) {
      maximumHatchStrokes = hatchStrokes;
      maximumEntityId = entity.entityId;
      maximumAzimuthDegrees = azimuthDegrees;
    }
  }
}

const hatchStrokeBudget = geometry.maximumHatchStrokeCount(
  VIEWPORT_WIDTH,
  VIEWPORT_HEIGHT,
  "mixed",
);
if (maximumHatchStrokes > hatchStrokeBudget) {
  throw new Error(
    `Close-camera hatching exceeded its viewport budget: ${maximumHatchStrokes} > ` +
      `${hatchStrokeBudget} for ${String(maximumEntityId)} at ` +
      `${String(maximumAzimuthDegrees)} degrees.`,
  );
}

process.stdout.write(
  JSON.stringify({
    close_camera: {
      azimuth_degrees: 315,
      board_visible: boardVisible,
      territory_divider_visible: closeCameraTerritoryDividerVisible,
      defender_territory_visible: projectRegion(defenderTerritory.shape, 0.015, closeCamera),
      defender_zone_visible: projectRegion(defenderZone.shape, 0.025, closeCamera),
      elevation_degrees: 12,
      terrain_area_14_visible: terrainArea14Visible,
      zoom: 3.5,
    },
    full_catalog_projection_counts: fullCatalogProjectionCounts,
    hatch_stroke_budget: hatchStrokeBudget,
    maximum_azimuth_degrees: maximumAzimuthDegrees,
    maximum_entity_id: maximumEntityId,
    maximum_hatch_strokes: maximumHatchStrokes,
    tested_azimuth_count: 360,
    territory_divider_segments_by_layout: territoryDividerSegmentsByLayout,
  }),
);

function projectBoard(bounds, camera) {
  return geometry.projectWorldPoints(
    [
      geometry.worldPoint(bounds.min_x_inches, bounds.min_y_inches, -0.16),
      geometry.worldPoint(bounds.max_x_inches, bounds.min_y_inches, -0.16),
      geometry.worldPoint(bounds.max_x_inches, bounds.max_y_inches, -0.16),
      geometry.worldPoint(bounds.min_x_inches, bounds.max_y_inches, -0.16),
    ],
    camera,
  );
}

function projectShape(shape, z, camera) {
  return geometry.projectWorldPoints(geometry.shapeWorldPoints(shape, z), camera);
}

function projectRegion(shape, z, camera) {
  return shape.polygons.some(
    (polygon) =>
      geometry.projectWorldPoints(
        polygon.map((point) => geometry.worldPoint(point.x_inches, point.y_inches, z)),
        camera,
      ) !== null,
  );
}

function requireProjectedShape(shape, z, cameras, entityId) {
  for (const camera of cameras) {
    if (projectShape(shape, z, camera) === null) {
      throw new Error(`Full-catalog shape did not project: ${String(entityId)}.`);
    }
  }
}
