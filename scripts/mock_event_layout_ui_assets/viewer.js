"use strict";

const VIEWER_SCHEMA = "event-companion-battlefield-viewer-v2";
const BATTLEFIELD_VIEW_SCHEMA = "battlefield-view-v2-phase17n";
const COORDINATE_SPEC = "battlefield-coordinate-v1";
const COORDINATE_SPACE = "battlefield_inches_right_handed_z_up";
const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;

const COLORS = Object.freeze({
  board: "#f5f0e5",
  boardEdge: "#555e64",
  gridMinor: "rgba(78, 88, 94, 0.17)",
  gridMajor: "rgba(61, 70, 77, 0.35)",
  dense: "#356346",
  light: "#c79738",
  mixed: "#77713b",
  unknown: "#76818a",
  attacker: "#a9452f",
  defender: "#256a98",
  noMansLand: "#776685",
  objective: "#ddad35",
  selected: "#f24b31",
  wallEdge: "rgba(25, 31, 34, 0.62)",
  floor: "#aa9f88",
});

const CAMERA_PRESETS = Object.freeze({
  isometric: { azimuth: 315, elevation: 48, zoom: 1 },
  top: { azimuth: 0, elevation: 89.5, zoom: 1 },
});

const state = {
  data: null,
  layout: null,
  selectedEntity: null,
  hitRegions: [],
  frameRequested: false,
  pointer: null,
  camera: {
    azimuth: CAMERA_PRESETS.isometric.azimuth * DEG_TO_RAD,
    elevation: CAMERA_PRESETS.isometric.elevation * DEG_TO_RAD,
    zoom: CAMERA_PRESETS.isometric.zoom,
  },
  forceOne: requiredElement("force-one"),
  forceTwo: requiredElement("force-two"),
  layoutVariant: requiredElement("layout-variant"),
  canvas: requiredElement("battlefield"),
  layoutName: requiredElement("layout-name"),
  layoutId: requiredElement("layout-id"),
  attackerEdge: requiredElement("attacker-edge"),
  defenderEdge: requiredElement("defender-edge"),
  terrainCount: requiredElement("terrain-count"),
  projectionVersion: requiredElement("projection-version"),
  geometryHash: requiredElement("geometry-hash"),
  geometryStatus: requiredElement("geometry-status"),
  cameraSummary: requiredElement("camera-summary"),
  entityDetails: requiredElement("entity-details"),
  viewerError: requiredElement("viewer-error"),
  azimuthInput: requiredElement("camera-azimuth"),
  elevationInput: requiredElement("camera-elevation"),
  zoomInput: requiredElement("camera-zoom"),
  azimuthValue: requiredElement("azimuth-value"),
  elevationValue: requiredElement("elevation-value"),
  zoomValue: requiredElement("zoom-value"),
  layers: {
    grid: requiredElement("show-grid"),
    regions: requiredElement("show-regions"),
    deployment: requiredElement("show-deployment"),
    areas: requiredElement("show-areas"),
    components: requiredElement("show-components"),
    walls: requiredElement("show-walls"),
    floors: requiredElement("show-floors"),
    objectives: requiredElement("show-objectives"),
  },
};

installEventHandlers();

try {
  initializeData(JSON.parse(requiredElement("layout-data").textContent));
} catch (error) {
  showError(error);
}

fetch("/data.json", { cache: "no-store" })
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Data request failed: ${response.status}`);
    }
    return response.json();
  })
  .then((data) => initializeData(data))
  .catch((error) => {
    if (state.data === null) {
      showError(error);
    }
  });

function requiredElement(id) {
  const element = document.getElementById(id);
  if (element === null) {
    throw new Error(`Viewer element is missing: ${id}`);
  }
  return element;
}

function initializeData(data) {
  validateViewerPayload(data);
  const previousOne = state.forceOne.value;
  const previousTwo = state.forceTwo.value;
  state.data = data;
  populateForceDispositions(data.force_dispositions, previousOne, previousTwo);
  renderSelection();
}

function validateViewerPayload(data) {
  if (data === null || typeof data !== "object" || Array.isArray(data)) {
    throw new Error("Viewer payload must be an object.");
  }
  if (data.viewer_schema !== VIEWER_SCHEMA) {
    throw new Error(`Unsupported viewer schema: ${String(data.viewer_schema)}.`);
  }
  if (data.battlefield_view_schema !== BATTLEFIELD_VIEW_SCHEMA) {
    throw new Error(
      `Unsupported battlefield projection schema: ${String(data.battlefield_view_schema)}.`,
    );
  }
  if (!Array.isArray(data.force_dispositions)) {
    throw new Error("Force dispositions must be an array.");
  }
  if (data.matrix === null || typeof data.matrix !== "object" || Array.isArray(data.matrix)) {
    throw new Error("Mission matrix must be an object.");
  }
  if (data.layouts === null || typeof data.layouts !== "object" || Array.isArray(data.layouts)) {
    throw new Error("Viewer layouts must be an object.");
  }
}

function validateBattlefieldView(view) {
  if (view === null || typeof view !== "object" || Array.isArray(view)) {
    throw new Error("Selected layout is missing its battlefield projection.");
  }
  if (view.schema_version !== BATTLEFIELD_VIEW_SCHEMA) {
    throw new Error(`Selected layout uses unsupported schema: ${String(view.schema_version)}.`);
  }
  if (view.coordinate_spec_version !== COORDINATE_SPEC) {
    throw new Error(
      `Selected layout uses unsupported coordinates: ${String(view.coordinate_spec_version)}.`,
    );
  }
  if (view.coordinate_space !== COORDINATE_SPACE) {
    throw new Error(`Selected layout uses unsupported coordinate space: ${String(view.coordinate_space)}.`);
  }
  if (view.authoritative === null || typeof view.authoritative !== "object") {
    throw new Error("Selected layout has no authoritative geometry section.");
  }
  const bounds = view.bounds;
  if (
    bounds === null ||
    typeof bounds !== "object" ||
    !(Number(bounds.max_x_inches) > 0) ||
    !(Number(bounds.max_y_inches) > 0)
  ) {
    throw new Error("Selected layout has invalid battlefield bounds.");
  }
}

function populateForceDispositions(forceDispositions, previousOne, previousTwo) {
  const optionIds = new Set(forceDispositions.map((force) => force.id));
  if (!optionIds.has("purge-the-foe")) {
    throw new Error("Default force disposition is missing: purge-the-foe.");
  }
  for (const select of [state.forceOne, state.forceTwo]) {
    select.replaceChildren();
    for (const force of forceDispositions) {
      const option = document.createElement("option");
      option.value = force.id;
      option.textContent = force.name;
      select.append(option);
    }
  }
  state.forceOne.value = optionIds.has(previousOne) ? previousOne : "purge-the-foe";
  state.forceTwo.value = optionIds.has(previousTwo) ? previousTwo : "purge-the-foe";
}

function installEventHandlers() {
  state.forceOne.addEventListener("change", renderSelection);
  state.forceTwo.addEventListener("change", renderSelection);
  state.layoutVariant.addEventListener("change", renderSelection);

  for (const checkbox of Object.values(state.layers)) {
    checkbox.addEventListener("change", scheduleRender);
  }

  requiredElement("view-isometric").addEventListener("click", () => applyPreset("isometric"));
  requiredElement("view-top").addEventListener("click", () => applyPreset("top"));
  requiredElement("view-attacker").addEventListener("click", () => viewFromPlayerEdge("attacker"));
  requiredElement("view-defender").addEventListener("click", () => viewFromPlayerEdge("defender"));

  state.azimuthInput.addEventListener("input", () => {
    state.camera.azimuth = Number(state.azimuthInput.value) * DEG_TO_RAD;
    updateCameraReadout();
    scheduleRender();
  });
  state.elevationInput.addEventListener("input", () => {
    state.camera.elevation = clamp(Number(state.elevationInput.value), 12, 89.5) * DEG_TO_RAD;
    updateCameraReadout();
    scheduleRender();
  });
  state.zoomInput.addEventListener("input", () => {
    state.camera.zoom = Number(state.zoomInput.value) / 100;
    updateCameraReadout();
    scheduleRender();
  });

  state.canvas.addEventListener("pointerdown", pointerDown);
  state.canvas.addEventListener("pointermove", pointerMove);
  state.canvas.addEventListener("pointerup", pointerUp);
  state.canvas.addEventListener("pointercancel", pointerCancel);
  state.canvas.addEventListener("wheel", wheelCamera, { passive: false });
  state.canvas.addEventListener("keydown", keyboardCamera);
  new ResizeObserver(scheduleRender).observe(state.canvas);
}

function renderSelection() {
  try {
    if (state.data === null) {
      return;
    }
    const key = `${state.forceOne.value}|${state.forceTwo.value}`;
    const cell = state.data.matrix[key];
    if (cell === undefined || !Array.isArray(cell.layout_ids)) {
      throw new Error(`Mission matrix cell is unavailable: ${key}.`);
    }
    const layoutIndex = Number(state.layoutVariant.value);
    const layoutId = cell.layout_ids[layoutIndex];
    const layout = state.data.layouts[layoutId];
    if (layout === undefined) {
      throw new Error(`Layout is unavailable: ${String(layoutId)}.`);
    }
    validateBattlefieldView(layout.battlefield_view);
    state.layout = layout;
    state.selectedEntity = null;
    updateLayoutSummary(layout);
    showEntityDetails(null);
    hideError();
    scheduleRender();
  } catch (error) {
    state.layout = null;
    showError(error);
    scheduleRender();
  }
}

function updateLayoutSummary(layout) {
  const view = layout.battlefield_view;
  const authoritative = view.authoritative;
  const features = Object.values(authoritative.terrain_features_by_id);
  const areas = Object.values(authoritative.terrain_areas_by_id);
  const regions = Object.values(authoritative.battlefield_regions_by_id);
  const volumeCounts = countVolumes(features);
  const territoryCount = regions.filter((region) => region.region_kind === "territory").length;
  const noMansLandCount = regions.filter((region) => region.region_kind === "no_mans_land").length;

  state.layoutName.textContent = layout.name;
  state.layoutId.textContent = layout.id;
  state.attackerEdge.textContent = humanize(layout.attacker_edge);
  state.defenderEdge.textContent = humanize(layout.defender_edge);
  state.terrainCount.textContent = [
    `${areas.length} areas`,
    `${features.length} components`,
    `${volumeCounts.wall} walls`,
    `${volumeCounts.floor} floors`,
    `${territoryCount} territories`,
    `${noMansLandCount} No Man's Land`,
  ].join(" · ");
  state.projectionVersion.textContent = view.schema_version;
  state.geometryHash.textContent = view.authoritative_geometry_hash;

  const runtimeGeometryAvailable = layout.geometry_status === "runtime_geometry_available";
  state.geometryStatus.classList.toggle("pending", !runtimeGeometryAvailable);
  state.geometryStatus.textContent = runtimeGeometryAvailable
    ? "Runtime terrain geometry is available for this layout."
    : "Terrain geometry is pending; only currently projected objectives and zones are shown.";
  state.canvas.setAttribute("aria-label", `Interactive three-dimensional battlefield: ${layout.name}`);
}

function countVolumes(features) {
  const counts = { wall: 0, floor: 0 };
  for (const feature of features) {
    for (const volume of feature.volumes) {
      if (volume.volume_kind === "wall" || volume.volume_kind === "floor") {
        counts[volume.volume_kind] += 1;
      }
    }
  }
  return counts;
}

function applyPreset(name) {
  const preset = CAMERA_PRESETS[name];
  if (preset === undefined) {
    throw new Error(`Unknown camera preset: ${name}.`);
  }
  state.camera.azimuth = preset.azimuth * DEG_TO_RAD;
  state.camera.elevation = preset.elevation * DEG_TO_RAD;
  state.camera.zoom = preset.zoom;
  updateCameraReadout();
  scheduleRender();
}

function viewFromPlayerEdge(role) {
  if (state.layout === null) {
    return;
  }
  const edge = role === "attacker" ? state.layout.attacker_edge : state.layout.defender_edge;
  const azimuthByEdge = {
    east: 0,
    north: 90,
    north_west_corner: 135,
    west: 180,
    south: 270,
    south_east_corner: 315,
  };
  const azimuth = azimuthByEdge[edge];
  if (azimuth === undefined) {
    throw new Error(`Unsupported battlefield edge: ${String(edge)}.`);
  }
  state.camera.azimuth = azimuth * DEG_TO_RAD;
  state.camera.elevation = 28 * DEG_TO_RAD;
  state.camera.zoom = 1;
  updateCameraReadout();
  scheduleRender();
}

function pointerDown(event) {
  if (event.button !== 0) {
    return;
  }
  state.canvas.setPointerCapture(event.pointerId);
  state.canvas.classList.add("orbiting");
  state.pointer = {
    id: event.pointerId,
    x: event.clientX,
    y: event.clientY,
    startX: event.clientX,
    startY: event.clientY,
    moved: false,
  };
}

function pointerMove(event) {
  if (state.pointer === null || state.pointer.id !== event.pointerId) {
    return;
  }
  const dx = event.clientX - state.pointer.x;
  const dy = event.clientY - state.pointer.y;
  if (Math.hypot(event.clientX - state.pointer.startX, event.clientY - state.pointer.startY) > 3) {
    state.pointer.moved = true;
  }
  state.pointer.x = event.clientX;
  state.pointer.y = event.clientY;
  state.camera.azimuth = normalizeRadians(state.camera.azimuth + dx * 0.008);
  state.camera.elevation = clamp(
    state.camera.elevation + dy * 0.006,
    12 * DEG_TO_RAD,
    89.5 * DEG_TO_RAD,
  );
  updateCameraReadout();
  scheduleRender();
}

function pointerUp(event) {
  if (state.pointer === null || state.pointer.id !== event.pointerId) {
    return;
  }
  const wasMoved = state.pointer.moved;
  state.pointer = null;
  state.canvas.classList.remove("orbiting");
  state.canvas.releasePointerCapture(event.pointerId);
  if (!wasMoved) {
    selectAtCanvasPoint(event);
  }
}

function pointerCancel(event) {
  if (state.pointer !== null && state.pointer.id === event.pointerId) {
    state.pointer = null;
    state.canvas.classList.remove("orbiting");
  }
}

function wheelCamera(event) {
  event.preventDefault();
  state.camera.zoom = clamp(state.camera.zoom * Math.exp(-event.deltaY * 0.001), 0.45, 3.5);
  updateCameraReadout();
  scheduleRender();
}

function keyboardCamera(event) {
  let handled = true;
  switch (event.key) {
    case "ArrowLeft":
      state.camera.azimuth -= 5 * DEG_TO_RAD;
      break;
    case "ArrowRight":
      state.camera.azimuth += 5 * DEG_TO_RAD;
      break;
    case "ArrowUp":
      state.camera.elevation += 4 * DEG_TO_RAD;
      break;
    case "ArrowDown":
      state.camera.elevation -= 4 * DEG_TO_RAD;
      break;
    case "+":
    case "=":
      state.camera.zoom *= 1.1;
      break;
    case "-":
    case "_":
      state.camera.zoom /= 1.1;
      break;
    case "t":
    case "T":
      applyPreset("top");
      return;
    case "0":
      applyPreset("isometric");
      return;
    default:
      handled = false;
  }
  if (!handled) {
    return;
  }
  event.preventDefault();
  state.camera.azimuth = normalizeRadians(state.camera.azimuth);
  state.camera.elevation = clamp(
    state.camera.elevation,
    12 * DEG_TO_RAD,
    89.5 * DEG_TO_RAD,
  );
  state.camera.zoom = clamp(state.camera.zoom, 0.45, 3.5);
  updateCameraReadout();
  scheduleRender();
}

function updateCameraReadout() {
  const azimuth = normalizeDegrees(state.camera.azimuth * RAD_TO_DEG);
  const elevation = state.camera.elevation * RAD_TO_DEG;
  state.azimuthInput.value = String(Math.round(azimuth));
  state.elevationInput.value = String(Math.round(elevation));
  state.zoomInput.value = String(Math.round(state.camera.zoom * 100));
  state.azimuthValue.textContent = `${Math.round(azimuth)}°`;
  state.elevationValue.textContent = `${Math.round(elevation)}°`;
  state.zoomValue.textContent = `${state.camera.zoom.toFixed(2)}×`;
  state.cameraSummary.textContent = [
    `Azimuth ${Math.round(azimuth)}°`,
    `Elevation ${Math.round(elevation)}°`,
    `Zoom ${state.camera.zoom.toFixed(2)}×`,
  ].join(" · ");
}

function scheduleRender() {
  if (state.frameRequested) {
    return;
  }
  state.frameRequested = true;
  requestAnimationFrame(() => {
    state.frameRequested = false;
    renderScene();
  });
}

function renderScene() {
  const canvas = state.canvas;
  const context = canvas.getContext("2d");
  if (context === null) {
    showError(new Error("This browser does not provide a two-dimensional canvas context."));
    return;
  }
  const size = resizeCanvas(canvas);
  context.setTransform(size.pixelRatio, 0, 0, size.pixelRatio, 0, 0);
  context.clearRect(0, 0, size.width, size.height);
  drawBackdrop(context, size.width, size.height);
  state.hitRegions = [];
  if (state.layout === null) {
    return;
  }

  try {
    const view = state.layout.battlefield_view;
    validateBattlefieldView(view);
    const camera = cameraForBounds(view.bounds, size.width, size.height);
    const authoritative = view.authoritative;
    drawBoard(context, camera, view.bounds);
    if (state.layers.grid.checked) {
      drawGrid(context, camera, view.bounds);
    }
    if (state.layers.regions.checked) {
      drawBattlefieldRegions(context, camera, authoritative.battlefield_regions_by_id);
    }
    if (state.layers.deployment.checked) {
      drawDeploymentZones(context, camera, authoritative.deployment_zones_by_id);
    }
    if (state.layers.areas.checked) {
      drawTerrainAreas(context, camera, authoritative.terrain_areas_by_id);
      drawObjectiveTerrainOutlines(
        context,
        camera,
        authoritative.terrain_areas_by_id,
        state.layout.objective_terrain_areas,
      );
    }
    if (state.layers.components.checked) {
      drawTerrainFootprints(
        context,
        camera,
        authoritative.terrain_features_by_id,
        view.render.hints_by_entity_id,
      );
    }

    const faces = [];
    collectTerrainVolumeFaces(
      faces,
      authoritative.terrain_features_by_id,
      view.render.hints_by_entity_id,
    );
    if (state.layers.objectives.checked) {
      collectObjectiveFaces(faces, authoritative.objectives_by_id);
    }
    drawSortedFaces(context, camera, faces);

    if (state.layers.objectives.checked) {
      drawObjectiveLabels(context, camera, authoritative.objectives_by_id);
    }
    drawSelectedOutline(context, camera);
  } catch (error) {
    showError(error);
  }
}

function resizeCanvas(canvas) {
  const rectangle = canvas.getBoundingClientRect();
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.max(1, rectangle.width);
  const height = Math.max(1, rectangle.height);
  const pixelWidth = Math.round(width * pixelRatio);
  const pixelHeight = Math.round(height * pixelRatio);
  if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
    canvas.width = pixelWidth;
    canvas.height = pixelHeight;
  }
  return { width, height, pixelRatio };
}

function drawBackdrop(context, width, height) {
  const gradient = context.createRadialGradient(
    width * 0.48,
    height * 0.32,
    20,
    width * 0.5,
    height * 0.5,
    Math.max(width, height) * 0.75,
  );
  gradient.addColorStop(0, "#f7f9f9");
  gradient.addColorStop(1, "#bdc8cd");
  context.fillStyle = gradient;
  context.fillRect(0, 0, width, height);
}

function cameraForBounds(bounds, width, height) {
  const battlefieldWidth = Number(bounds.max_x_inches) - Number(bounds.min_x_inches);
  const battlefieldDepth = Number(bounds.max_y_inches) - Number(bounds.min_y_inches);
  const target = {
    x: Number(bounds.min_x_inches) + battlefieldWidth / 2,
    y: Number(bounds.min_y_inches) + battlefieldDepth / 2,
    z: 2.25,
  };
  const distance = Math.max(battlefieldWidth, battlefieldDepth) * 1.48 / state.camera.zoom;
  const elevation = clamp(state.camera.elevation, 12 * DEG_TO_RAD, 89.5 * DEG_TO_RAD);
  const horizontalDistance = distance * Math.cos(elevation);
  const cameraPosition = {
    x: target.x + horizontalDistance * Math.cos(state.camera.azimuth),
    y: target.y + horizontalDistance * Math.sin(state.camera.azimuth),
    z: target.z + distance * Math.sin(elevation),
  };
  const forward = normalize(subtract(target, cameraPosition));
  const right = normalize(cross(forward, { x: 0, y: 0, z: 1 }));
  const up = normalize(cross(right, forward));
  const focalLength = Math.min(width, height) * 0.92;
  return { position: cameraPosition, forward, right, up, focalLength, width, height };
}

function projectPoint(point, camera) {
  const relative = subtract(point, camera.position);
  const depth = dot(relative, camera.forward);
  if (depth <= 0.01) {
    return null;
  }
  const perspective = camera.focalLength / depth;
  return {
    x: camera.width / 2 + dot(relative, camera.right) * perspective,
    y: camera.height / 2 - dot(relative, camera.up) * perspective,
    depth,
  };
}

function drawBoard(context, camera, bounds) {
  const points = [
    worldPoint(bounds.min_x_inches, bounds.min_y_inches, -0.16),
    worldPoint(bounds.max_x_inches, bounds.min_y_inches, -0.16),
    worldPoint(bounds.max_x_inches, bounds.max_y_inches, -0.16),
    worldPoint(bounds.min_x_inches, bounds.max_y_inches, -0.16),
  ];
  drawWorldPolygon(context, camera, points, {
    fill: COLORS.board,
    stroke: COLORS.boardEdge,
    lineWidth: 1.5,
  });
}

function drawGrid(context, camera, bounds) {
  const minX = Number(bounds.min_x_inches);
  const minY = Number(bounds.min_y_inches);
  const maxX = Number(bounds.max_x_inches);
  const maxY = Number(bounds.max_y_inches);
  for (let x = Math.ceil(minX); x <= maxX; x += 1) {
    drawWorldLine(
      context,
      camera,
      worldPoint(x, minY, -0.1),
      worldPoint(x, maxY, -0.1),
      x % 6 === 0 ? COLORS.gridMajor : COLORS.gridMinor,
      x % 6 === 0 ? 1 : 0.55,
    );
  }
  for (let y = Math.ceil(minY); y <= maxY; y += 1) {
    drawWorldLine(
      context,
      camera,
      worldPoint(minX, y, -0.1),
      worldPoint(maxX, y, -0.1),
      y % 6 === 0 ? COLORS.gridMajor : COLORS.gridMinor,
      y % 6 === 0 ? 1 : 0.55,
    );
  }
}

function drawBattlefieldRegions(context, camera, regionsById) {
  const regions = Object.values(regionsById).sort((left, right) => left.region_id.localeCompare(right.region_id));
  for (const region of regions) {
    if (region.region_kind === "deployment_zone") {
      continue;
    }
    const style = regionStyle(region);
    drawRegionShape(context, camera, region.shape, 0.015, style, entityRecord("region", region));
  }
}

function drawDeploymentZones(context, camera, zonesById) {
  const zones = Object.values(zonesById).sort((left, right) =>
    left.deployment_zone_id.localeCompare(right.deployment_zone_id),
  );
  for (const zone of zones) {
    const isAttacker = zone.owner_player_id === "viewer-attacker";
    drawRegionShape(
      context,
      camera,
      zone.shape,
      0.025,
      {
        fill: hexToRgba(isAttacker ? COLORS.attacker : COLORS.defender, 0.18),
        stroke: hexToRgba(isAttacker ? COLORS.attacker : COLORS.defender, 0.8),
        lineWidth: 1.25,
      },
      entityRecord("deployment_zone", zone),
    );
  }
}

function drawTerrainAreas(context, camera, areasById) {
  const areas = Object.values(areasById).sort((left, right) =>
    left.terrain_area_id.localeCompare(right.terrain_area_id),
  );
  for (const area of areas) {
    const points = shapeWorldPoints(area.footprint, 0.04);
    const screenPoints = projectWorldPoints(points, camera);
    if (screenPoints === null) {
      continue;
    }
    const color = classificationColor(area.classification);
    drawHatchedScreenPolygon(context, screenPoints, {
      fill: hexToRgba(color, 0.16),
      stroke: hexToRgba(color, 0.72),
      lineWidth: 1,
      classification: area.classification,
    });
    state.hitRegions.push(hitRecord([screenPoints], [], entityRecord("terrain_area", area)));
  }
}

function drawObjectiveTerrainOutlines(context, camera, areasById, objectiveTerrainAreas) {
  for (const objectiveTerrain of objectiveTerrainAreas) {
    for (const areaId of objectiveTerrain.terrain_area_ids) {
      const area = areasById[areaId];
      if (area === undefined) {
        throw new Error(`Objective terrain references unknown area: ${areaId}.`);
      }
      const points = shapeWorldPoints(area.footprint, 0.055);
      const screenPoints = projectWorldPoints(points, camera);
      if (screenPoints === null) {
        continue;
      }
      strokeScreenPolygon(context, screenPoints, hexToRgba(COLORS.objective, 0.95), 2);
    }
  }
}

function drawTerrainFootprints(context, camera, featuresById, hintsById) {
  const features = Object.values(featuresById).sort((left, right) =>
    left.terrain_feature_id.localeCompare(right.terrain_feature_id),
  );
  for (const feature of features) {
    const points = shapeWorldPoints(feature.footprint, 0.075);
    const screenPoints = projectWorldPoints(points, camera);
    if (screenPoints === null) {
      continue;
    }
    const color = classificationColor(feature.classification);
    drawHatchedScreenPolygon(context, screenPoints, {
      fill: hexToRgba(color, 0.32),
      stroke: hexToRgba(color, 0.96),
      lineWidth: 1.4,
      classification: feature.classification,
    });
    state.hitRegions.push(
      hitRecord(
        [screenPoints],
        [],
        entityRecord("terrain_feature", feature, hintsById[feature.terrain_feature_id]),
      ),
    );
  }
}

function collectTerrainVolumeFaces(faces, featuresById, hintsById) {
  const features = Object.values(featuresById).sort((left, right) =>
    left.terrain_feature_id.localeCompare(right.terrain_feature_id),
  );
  for (const feature of features) {
    const entity = entityRecord("terrain_feature", feature, hintsById[feature.terrain_feature_id]);
    for (const volume of feature.volumes) {
      if (volume.volume_kind === "wall" && !state.layers.walls.checked) {
        continue;
      }
      if (volume.volume_kind === "floor" && !state.layers.floors.checked) {
        continue;
      }
      const baseColor = volume.volume_kind === "floor"
        ? COLORS.floor
        : classificationColor(feature.classification);
      faces.push(...boxFaces(volume, baseColor, entity));
    }
  }
}

function collectObjectiveFaces(faces, objectivesById) {
  const objectives = Object.values(objectivesById).sort((left, right) =>
    left.objective_id.localeCompare(right.objective_id),
  );
  for (const objective of objectives) {
    const radius = Number(objective.marker_diameter_inches) / 2;
    const center = objective.position;
    const entity = entityRecord("objective", objective);
    faces.push(...cylinderFaces(center, radius, 0.22, COLORS.objective, entity));
  }
}

function drawSortedFaces(context, camera, faces) {
  const projectedFaces = [];
  for (const face of faces) {
    const screenPoints = projectWorldPoints(face.points, camera);
    if (screenPoints === null) {
      continue;
    }
    projectedFaces.push({
      ...face,
      screenPoints,
      depth: average(screenPoints.map((point) => point.depth)),
    });
  }
  projectedFaces.sort((left, right) => right.depth - left.depth);
  for (const face of projectedFaces) {
    drawScreenPolygon(context, face.screenPoints, {
      fill: face.fill,
      stroke: face.stroke,
      lineWidth: face.lineWidth,
    });
    state.hitRegions.push(hitRecord([face.screenPoints], [], face.entity));
  }
}

function drawObjectiveLabels(context, camera, objectivesById) {
  context.save();
  context.textAlign = "center";
  context.textBaseline = "bottom";
  context.font = "700 11px ui-sans-serif, system-ui, sans-serif";
  for (const objective of Object.values(objectivesById)) {
    const projected = projectPoint(
      worldPoint(
        objective.position.x_inches,
        objective.position.y_inches,
        Number(objective.position.z_inches) + 0.55,
      ),
      camera,
    );
    if (projected === null) {
      continue;
    }
    const label = objectiveRoleLabel(objective.objective_role);
    context.lineWidth = 3;
    context.strokeStyle = "rgba(255, 255, 255, 0.92)";
    context.strokeText(label, projected.x, projected.y);
    context.fillStyle = "#222a2f";
    context.fillText(label, projected.x, projected.y);
  }
  context.restore();
}

function drawSelectedOutline(context, camera) {
  const selected = state.selectedEntity;
  if (selected === null) {
    return;
  }
  let shape = null;
  if (selected.kind === "terrain_feature" || selected.kind === "terrain_area") {
    shape = selected.payload.footprint;
  }
  if (shape === null) {
    return;
  }
  const points = projectWorldPoints(shapeWorldPoints(shape, 0.14), camera);
  if (points !== null) {
    strokeScreenPolygon(context, points, COLORS.selected, 3);
  }
}

function drawRegionShape(context, camera, shape, z, style, entity) {
  const outerPolygons = [];
  for (const polygon of shape.polygons) {
    const projected = projectWorldPoints(
      polygon.map((point) => worldPoint(point.x_inches, point.y_inches, z)),
      camera,
    );
    if (projected !== null) {
      outerPolygons.push(projected);
    }
  }
  const holes = [];
  for (const cutout of [...shape.circle_cutouts, ...shape.polygon_cutouts]) {
    const projected = projectWorldPoints(shapeWorldPoints(cutout, z + 0.001), camera);
    if (projected !== null) {
      holes.push(projected);
    }
  }
  if (outerPolygons.length === 0) {
    return;
  }
  context.save();
  const path = new Path2D();
  for (const polygon of outerPolygons) {
    addPolygonToPath(path, polygon);
  }
  for (const hole of holes) {
    addPolygonToPath(path, hole);
  }
  context.fillStyle = style.fill;
  context.fill(path, "evenodd");
  context.strokeStyle = style.stroke;
  context.lineWidth = style.lineWidth;
  context.stroke(path);
  context.restore();
  state.hitRegions.push(hitRecord(outerPolygons, holes, entity));
}

function regionStyle(region) {
  if (region.region_kind === "no_mans_land") {
    return {
      fill: hexToRgba(COLORS.noMansLand, 0.11),
      stroke: hexToRgba(COLORS.noMansLand, 0.58),
      lineWidth: 1,
    };
  }
  const color = region.owner_role === "attacker" ? COLORS.attacker : COLORS.defender;
  return {
    fill: hexToRgba(color, 0.1),
    stroke: hexToRgba(color, 0.5),
    lineWidth: 1,
  };
}

function drawWorldPolygon(context, camera, worldPoints, style) {
  const screenPoints = projectWorldPoints(worldPoints, camera);
  if (screenPoints !== null) {
    drawScreenPolygon(context, screenPoints, style);
  }
}

function drawScreenPolygon(context, points, style) {
  context.save();
  context.beginPath();
  movePolygonPath(context, points);
  if (style.fill !== null) {
    context.fillStyle = style.fill;
    context.fill();
  }
  if (style.stroke !== null) {
    context.strokeStyle = style.stroke;
    context.lineWidth = style.lineWidth;
    context.lineJoin = "round";
    context.stroke();
  }
  context.restore();
}

function drawHatchedScreenPolygon(context, points, style) {
  drawScreenPolygon(context, points, style);
  context.save();
  context.beginPath();
  movePolygonPath(context, points);
  context.clip();
  const bounds = screenBounds(points);
  const spacing = 9;
  context.strokeStyle = hexToRgba(classificationColor(style.classification), 0.28);
  context.lineWidth = 0.7;
  const directions = style.classification === "mixed" ? [1, -1] : [style.classification === "light" ? -1 : 1];
  for (const direction of directions) {
    for (let offset = bounds.minX - bounds.height; offset < bounds.maxX + bounds.height; offset += spacing) {
      context.beginPath();
      context.moveTo(offset, direction > 0 ? bounds.maxY : bounds.minY);
      context.lineTo(offset + bounds.height, direction > 0 ? bounds.minY : bounds.maxY);
      context.stroke();
    }
  }
  context.restore();
}

function strokeScreenPolygon(context, points, stroke, lineWidth) {
  drawScreenPolygon(context, points, { fill: null, stroke, lineWidth });
}

function movePolygonPath(context, points) {
  context.moveTo(points[0].x, points[0].y);
  for (let index = 1; index < points.length; index += 1) {
    context.lineTo(points[index].x, points[index].y);
  }
  context.closePath();
}

function addPolygonToPath(path, points) {
  path.moveTo(points[0].x, points[0].y);
  for (let index = 1; index < points.length; index += 1) {
    path.lineTo(points[index].x, points[index].y);
  }
  path.closePath();
}

function drawWorldLine(context, camera, start, end, stroke, lineWidth) {
  const projectedStart = projectPoint(start, camera);
  const projectedEnd = projectPoint(end, camera);
  if (projectedStart === null || projectedEnd === null) {
    return;
  }
  context.save();
  context.beginPath();
  context.moveTo(projectedStart.x, projectedStart.y);
  context.lineTo(projectedEnd.x, projectedEnd.y);
  context.strokeStyle = stroke;
  context.lineWidth = lineWidth;
  context.stroke();
  context.restore();
}

function projectWorldPoints(points, camera) {
  const projected = [];
  for (const point of points) {
    const screenPoint = projectPoint(point, camera);
    if (screenPoint === null) {
      return null;
    }
    projected.push(screenPoint);
  }
  return projected;
}

function shapeWorldPoints(shape, z) {
  if (shape.kind === "polygon") {
    return shape.vertices.map((point) => worldPoint(point.x_inches, point.y_inches, z));
  }
  if (shape.center === null) {
    throw new Error(`Shape ${String(shape.kind)} requires a center.`);
  }
  if (shape.kind === "circle") {
    return ellipseWorldPoints(
      shape.center,
      Number(shape.radius_inches),
      Number(shape.radius_inches),
      0,
      z,
    );
  }
  if (shape.kind === "ellipse") {
    return ellipseWorldPoints(
      shape.center,
      Number(shape.length_inches) / 2,
      Number(shape.width_inches) / 2,
      Number(shape.rotation_degrees),
      z,
    );
  }
  if (shape.kind === "rectangle") {
    return rectangleWorldPoints(
      shape.center,
      Number(shape.length_inches),
      Number(shape.width_inches),
      Number(shape.rotation_degrees),
      z,
    );
  }
  throw new Error(`Unsupported projected shape: ${String(shape.kind)}.`);
}

function ellipseWorldPoints(center, radiusX, radiusY, rotationDegrees, z) {
  const points = [];
  const rotation = rotationDegrees * DEG_TO_RAD;
  for (let index = 0; index < 32; index += 1) {
    const angle = (index / 32) * Math.PI * 2;
    const localX = Math.cos(angle) * radiusX;
    const localY = Math.sin(angle) * radiusY;
    points.push(
      worldPoint(
        Number(center.x_inches) + localX * Math.cos(rotation) - localY * Math.sin(rotation),
        Number(center.y_inches) + localX * Math.sin(rotation) + localY * Math.cos(rotation),
        z,
      ),
    );
  }
  return points;
}

function rectangleWorldPoints(center, width, depth, rotationDegrees, z) {
  const halfWidth = width / 2;
  const halfDepth = depth / 2;
  const rotation = rotationDegrees * DEG_TO_RAD;
  return [
    [-halfWidth, -halfDepth],
    [halfWidth, -halfDepth],
    [halfWidth, halfDepth],
    [-halfWidth, halfDepth],
  ].map(([localX, localY]) =>
    worldPoint(
      Number(center.x_inches) + localX * Math.cos(rotation) - localY * Math.sin(rotation),
      Number(center.y_inches) + localX * Math.sin(rotation) + localY * Math.cos(rotation),
      z,
    ),
  );
}

function boxFaces(volume, color, entity) {
  const center = volume.bottom_center;
  const bottomZ = Number(center.z_inches);
  const topZ = bottomZ + Number(volume.height_inches);
  const bottom = rectangleWorldPoints(
    center,
    Number(volume.width_inches),
    Number(volume.depth_inches),
    Number(volume.rotation_degrees),
    bottomZ,
  );
  const top = bottom.map((point) => worldPoint(point.x, point.y, topZ));
  const faces = [
    {
      points: top,
      fill: hexToRgba(lighten(color, 0.2), 0.9),
      stroke: COLORS.wallEdge,
      lineWidth: 0.75,
      entity,
    },
  ];
  for (let index = 0; index < 4; index += 1) {
    const next = (index + 1) % 4;
    faces.push({
      points: [bottom[index], bottom[next], top[next], top[index]],
      fill: hexToRgba(lighten(color, index % 2 === 0 ? -0.03 : -0.14), 0.88),
      stroke: COLORS.wallEdge,
      lineWidth: 0.7,
      entity,
    });
  }
  return faces;
}

function cylinderFaces(center, radius, height, color, entity) {
  const bottomZ = Number(center.z_inches) + 0.08;
  const topZ = bottomZ + height;
  const bottom = ellipseWorldPoints(center, radius, radius, 0, bottomZ);
  const top = bottom.map((point) => worldPoint(point.x, point.y, topZ));
  const faces = [
    {
      points: top,
      fill: hexToRgba(lighten(color, 0.16), 0.98),
      stroke: "rgba(76, 57, 15, 0.8)",
      lineWidth: 0.9,
      entity,
    },
  ];
  for (let index = 0; index < bottom.length; index += 1) {
    const next = (index + 1) % bottom.length;
    faces.push({
      points: [bottom[index], bottom[next], top[next], top[index]],
      fill: hexToRgba(lighten(color, -0.08), 0.94),
      stroke: "rgba(76, 57, 15, 0.45)",
      lineWidth: 0.45,
      entity,
    });
  }
  return faces;
}

function selectAtCanvasPoint(event) {
  const rectangle = state.canvas.getBoundingClientRect();
  const point = { x: event.clientX - rectangle.left, y: event.clientY - rectangle.top };
  let selected = null;
  for (let index = state.hitRegions.length - 1; index >= 0; index -= 1) {
    const hit = state.hitRegions[index];
    if (pointInHitRegion(point, hit)) {
      selected = hit.entity;
      break;
    }
  }
  state.selectedEntity = selected;
  showEntityDetails(selected);
  scheduleRender();
}

function pointInHitRegion(point, hit) {
  const insideOuter = hit.polygons.some((polygon) => pointInPolygon(point, polygon));
  if (!insideOuter) {
    return false;
  }
  return !hit.holes.some((hole) => pointInPolygon(point, hole));
}

function pointInPolygon(point, polygon) {
  let inside = false;
  for (let index = 0, previous = polygon.length - 1; index < polygon.length; previous = index, index += 1) {
    const currentPoint = polygon[index];
    const previousPoint = polygon[previous];
    const crosses =
      currentPoint.y > point.y !== previousPoint.y > point.y &&
      point.x <
        ((previousPoint.x - currentPoint.x) * (point.y - currentPoint.y)) /
          (previousPoint.y - currentPoint.y) +
          currentPoint.x;
    if (crosses) {
      inside = !inside;
    }
  }
  return inside;
}

function showEntityDetails(entity) {
  state.entityDetails.replaceChildren();
  if (entity === null) {
    state.entityDetails.textContent =
      "Click a terrain component, area, objective, or region to inspect it.";
    return;
  }
  const definitionList = document.createElement("dl");
  appendDetail(definitionList, "Type", humanize(entity.kind));
  appendDetail(definitionList, "ID", entity.id);
  const payload = entity.payload;
  if (entity.kind === "terrain_feature") {
    appendDetail(definitionList, "Kind", humanize(payload.terrain_feature_kind));
    appendDetail(definitionList, "Classification", humanize(payload.classification));
    const counts = countVolumes([payload]);
    appendDetail(definitionList, "Volumes", `${counts.wall} walls · ${counts.floor} floors`);
    appendDetail(definitionList, "Asset hint", entity.hint?.asset_id ?? "None");
    appendDetail(definitionList, "Source", payload.source_id ?? "None");
  } else if (entity.kind === "terrain_area") {
    appendDetail(definitionList, "Classification", humanize(payload.classification));
    appendDetail(definitionList, "Source", payload.source_id);
  } else if (entity.kind === "objective") {
    appendDetail(definitionList, "Role", humanize(payload.objective_role));
    appendDetail(
      definitionList,
      "Position",
      `${formatNumber(payload.position.x_inches)}, ${formatNumber(payload.position.y_inches)}, ${formatNumber(payload.position.z_inches)} in`,
    );
    appendDetail(definitionList, "Source", payload.source_id);
  } else if (entity.kind === "region") {
    appendDetail(definitionList, "Region", humanize(payload.region_kind));
    appendDetail(definitionList, "Owner", payload.owner_role === null ? "Neither" : humanize(payload.owner_role));
    appendDetail(definitionList, "Source", payload.source_id);
  } else if (entity.kind === "deployment_zone") {
    appendDetail(definitionList, "Player", humanize(payload.owner_player_id));
  }
  state.entityDetails.append(definitionList);
}

function appendDetail(definitionList, label, value) {
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = String(value);
  definitionList.append(term, description);
}

function entityRecord(kind, payload, hint = null) {
  const idByKind = {
    terrain_feature: payload.terrain_feature_id,
    terrain_area: payload.terrain_area_id,
    objective: payload.objective_id,
    region: payload.region_id,
    deployment_zone: payload.deployment_zone_id,
  };
  return { kind, id: idByKind[kind], payload, hint };
}

function hitRecord(polygons, holes, entity) {
  return { polygons, holes, entity };
}

function classificationColor(classification) {
  if (classification === "dense") {
    return COLORS.dense;
  }
  if (classification === "light") {
    return COLORS.light;
  }
  if (classification === "mixed") {
    return COLORS.mixed;
  }
  if (classification === "unknown") {
    return COLORS.unknown;
  }
  throw new Error(`Unsupported terrain classification: ${String(classification)}.`);
}

function objectiveRoleLabel(role) {
  if (role === "attacker_home") {
    return "A Home";
  }
  if (role === "defender_home") {
    return "D Home";
  }
  if (role === "central") {
    return "Central";
  }
  return "Expansion";
}

function humanize(value) {
  return String(value)
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatNumber(value) {
  return String(Math.round(Number(value) * 100) / 100);
}

function screenBounds(points) {
  const xValues = points.map((point) => point.x);
  const yValues = points.map((point) => point.y);
  const minX = Math.min(...xValues);
  const maxX = Math.max(...xValues);
  const minY = Math.min(...yValues);
  const maxY = Math.max(...yValues);
  return { minX, maxX, minY, maxY, height: maxY - minY };
}

function worldPoint(x, y, z) {
  return { x: Number(x), y: Number(y), z: Number(z) };
}

function subtract(left, right) {
  return { x: left.x - right.x, y: left.y - right.y, z: left.z - right.z };
}

function dot(left, right) {
  return left.x * right.x + left.y * right.y + left.z * right.z;
}

function cross(left, right) {
  return {
    x: left.y * right.z - left.z * right.y,
    y: left.z * right.x - left.x * right.z,
    z: left.x * right.y - left.y * right.x,
  };
}

function normalize(vector) {
  const length = Math.hypot(vector.x, vector.y, vector.z);
  if (!(length > 0.000001)) {
    throw new Error("Camera basis vector is degenerate.");
  }
  return { x: vector.x / length, y: vector.y / length, z: vector.z / length };
}

function average(values) {
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function clamp(value, minimum, maximum) {
  return Math.min(maximum, Math.max(minimum, value));
}

function normalizeRadians(value) {
  const fullTurn = Math.PI * 2;
  return ((value % fullTurn) + fullTurn) % fullTurn;
}

function normalizeDegrees(value) {
  return ((value % 360) + 360) % 360;
}

function hexToRgba(hex, alpha) {
  const normalized = hex.replace("#", "");
  const red = Number.parseInt(normalized.slice(0, 2), 16);
  const green = Number.parseInt(normalized.slice(2, 4), 16);
  const blue = Number.parseInt(normalized.slice(4, 6), 16);
  return `rgba(${red}, ${green}, ${blue}, ${alpha})`;
}

function lighten(hex, amount) {
  const normalized = hex.replace("#", "");
  const channels = [0, 2, 4].map((offset) => Number.parseInt(normalized.slice(offset, offset + 2), 16));
  const adjusted = channels.map((channel) =>
    Math.round(clamp(amount >= 0 ? channel + (255 - channel) * amount : channel * (1 + amount), 0, 255)),
  );
  return `#${adjusted.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function showError(error) {
  const message = error instanceof Error ? error.message : String(error);
  state.viewerError.textContent = message;
  state.viewerError.hidden = false;
}

function hideError() {
  state.viewerError.hidden = true;
  state.viewerError.textContent = "";
}

updateCameraReadout();
