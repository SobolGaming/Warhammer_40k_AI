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
