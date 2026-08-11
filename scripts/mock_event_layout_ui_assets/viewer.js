"use strict";

const VIEWER_SCHEMA = "event-companion-battlefield-viewer-v3";
const BATTLEFIELD_VIEW_SCHEMA = "battlefield-view-v3-phase17n";
const COORDINATE_SPEC = "battlefield-coordinate-v1";
const COORDINATE_SPACE = "battlefield_inches_right_handed_z_up";
const VIEWER_GEOMETRY = globalThis.BattlefieldViewerGeometry;
if (VIEWER_GEOMETRY === undefined) {
  throw new Error("Battlefield viewer geometry module is missing.");
}
const {
  DEG_TO_RAD,
  RAD_TO_DEG,
  cameraForBounds,
  clipWorldLineToNearPlane,
  hatchLineSegments,
  projectPoint,
  projectWorldPoints,
  rectangleWorldPoints,
  sharedTerritoryBoundarySegments,
  shapeWorldPoints,
  worldPoint,
} = VIEWER_GEOMETRY;

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
  singleAreaContact: "#176b87",
  separateAreaContact: "#8b3a35",
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
  const objectives = Object.values(authoritative.objectives_by_id);
  const regions = Object.values(authoritative.battlefield_regions_by_id);
  const volumeCounts = countVolumes(features);
  const territoryCount = regions.filter((region) => region.region_kind === "territory").length;
  const noMansLandCount = regions.filter((region) => region.region_kind === "no_mans_land").length;
  const objectiveFootprints = resolveObjectiveTerrainFootprints(
    authoritative.objectives_by_id,
    authoritative.terrain_areas_by_id,
    layout.objective_terrain_areas,
  );
  const sourceUnboundObjectiveIds = new Set(layout.source_unbound_objective_ids);
  const boundObjectiveIds = new Set(
    layout.objective_terrain_areas.map((binding) => binding.objective_marker_id),
  );
  const allObjectiveIds = new Set(objectives.map((objective) => objective.objective_id));
  const reviewedObjectiveIds = new Set([...boundObjectiveIds, ...sourceUnboundObjectiveIds]);
  const hasInvalidSourceUnboundId = [...sourceUnboundObjectiveIds].some(
    (objectiveId) => !allObjectiveIds.has(objectiveId) || boundObjectiveIds.has(objectiveId),
  );
  const sourceReviewIsComplete = !hasInvalidSourceUnboundId
    && reviewedObjectiveIds.size === allObjectiveIds.size;
  const pendingObjectiveFootprintCount = [...allObjectiveIds].filter(
    (objectiveId) => !reviewedObjectiveIds.has(objectiveId),
  ).length;
  const expectedObjectiveFootprintStatus = sourceReviewIsComplete
    ? "source_linked_footprints_available"
    : "footprint_binding_pending";
  if (layout.objective_footprint_status !== expectedObjectiveFootprintStatus) {
    throw new Error("Objective footprint status does not match its source bindings.");
  }
  const terrainAreaContactCounts = validateTerrainAreaContacts(
    layout.terrain_area_contacts,
    authoritative.terrain_areas_by_id,
  );
  const expectedLogicalTerrainAreaCount = areas.length - terrainAreaContactCounts.single;
  if (layout.logical_terrain_area_count !== expectedLogicalTerrainAreaCount) {
    throw new Error("Logical terrain-area count does not match source contact semantics.");
  }

  state.layoutName.textContent = layout.name;
  state.layoutId.textContent = layout.id;
  state.attackerEdge.textContent = humanize(layout.attacker_edge);
  state.defenderEdge.textContent = humanize(layout.defender_edge);
  state.terrainCount.textContent = [
    `${layout.logical_terrain_area_count} logical areas`,
    `${areas.length} footprint pieces`,
    `${terrainAreaContactCounts.single} single-area joins`,
    `${terrainAreaContactCounts.separate} separate seams`,
    `${terrainAreaContactCounts.maximumRuntimeGapInches.toFixed(3)}\u2033 max quantized seam`,
    `${features.length} components`,
    `${volumeCounts.wall} walls`,
    `${volumeCounts.floor} floors`,
    `${objectiveFootprints.length} terrain-linked objectives`,
    `${sourceUnboundObjectiveIds.size} open-field objectives`,
    `${territoryCount} territories`,
    `${noMansLandCount} No Man's Land`,
  ].join(" · ");
  state.projectionVersion.textContent = view.schema_version;
  state.geometryHash.textContent = view.authoritative_geometry_hash;

  const runtimeGeometryAvailable = layout.geometry_status === "runtime_geometry_available";
  const objectiveFootprintsPending = pendingObjectiveFootprintCount > 0;
  state.geometryStatus.classList.toggle(
    "pending",
    !runtimeGeometryAvailable || objectiveFootprintsPending,
  );
  if (!runtimeGeometryAvailable && objectiveFootprintsPending) {
    state.geometryStatus.textContent =
      `Terrain geometry and ${pendingObjectiveFootprintCount} objective footprints are pending; ` +
      "objective identity labels and currently projected zones remain visible.";
  } else if (objectiveFootprintsPending) {
    state.geometryStatus.textContent =
      `${pendingObjectiveFootprintCount} objective footprints are pending source bindings; ` +
      "no standalone marker geometry is inferred.";
  } else if (!runtimeGeometryAvailable) {
    state.geometryStatus.textContent =
      "Terrain geometry is pending; source-linked objective footprints and projected zones remain visible.";
  } else {
    state.geometryStatus.textContent =
      "Runtime terrain and source-linked objective footprint geometry is available for this layout.";
  }
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
    const camera = cameraForBounds(view.bounds, size.width, size.height, state.camera);
    const authoritative = view.authoritative;
    const objectiveFootprints = resolveObjectiveTerrainFootprints(
      authoritative.objectives_by_id,
      authoritative.terrain_areas_by_id,
      state.layout.objective_terrain_areas,
    );
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
      drawTerrainAreaContacts(context, camera, state.layout.terrain_area_contacts);
    }
    if (state.layers.objectives.checked) {
      drawObjectiveTerrainFootprints(context, camera, objectiveFootprints);
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
  drawTerritoryDivider(context, camera, regionsById);
}

function drawTerritoryDivider(context, camera, regionsById) {
  for (const segment of sharedTerritoryBoundarySegments(regionsById)) {
    drawWorldLine(
      context,
      camera,
      worldPoint(segment.start.x_inches, segment.start.y_inches, 0.022),
      worldPoint(segment.end.x_inches, segment.end.y_inches, 0.022),
      "#000000",
      3.5,
      [10, 7],
    );
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
    drawHatchedScreenPolygon(
      context,
      screenPoints,
      {
        fill: hexToRgba(color, 0.16),
        stroke: hexToRgba(color, 0.72),
        lineWidth: 1,
        classification: area.classification,
      },
      camera,
    );
    state.hitRegions.push(hitRecord([screenPoints], [], entityRecord("terrain_area", area)));
  }
}

function validateTerrainAreaContacts(contacts, areasById) {
  if (!Array.isArray(contacts)) {
    throw new Error("Terrain-area contacts must be an array.");
  }
  const counts = { single: 0, separate: 0, maximumRuntimeGapInches: 0 };
  const seenPairs = new Set();
  const groupedPhysicalAreaIds = new Set();
  for (const contact of contacts) {
    if (
      contact === null
      || typeof contact !== "object"
      || !Array.isArray(contact.terrain_area_ids)
      || contact.terrain_area_ids.length !== 2
    ) {
      throw new Error("Terrain-area contact must reference exactly two areas.");
    }
    const [firstId, secondId] = contact.terrain_area_ids;
    if (firstId === secondId || areasById[firstId] === undefined || areasById[secondId] === undefined) {
      throw new Error("Terrain-area contact references invalid physical areas.");
    }
    const pairKey = [firstId, secondId].sort().join("|");
    if (seenPairs.has(pairKey)) {
      throw new Error("Terrain-area contact pair is duplicated.");
    }
    seenPairs.add(pairKey);
    if (contact.kind !== "single" && contact.kind !== "separate") {
      throw new Error(`Unsupported terrain-area contact kind: ${String(contact.kind)}.`);
    }
    const firstLogicalId = areasById[firstId].logical_terrain_area_id;
    const secondLogicalId = areasById[secondId].logical_terrain_area_id;
    if (
      typeof firstLogicalId !== "string"
      || firstLogicalId.length === 0
      || typeof secondLogicalId !== "string"
      || secondLogicalId.length === 0
    ) {
      throw new Error("Terrain-area contact requires authoritative logical area IDs.");
    }
    if (contact.kind === "single" && firstLogicalId !== secondLogicalId) {
      throw new Error("Single terrain-area contact does not share one logical area ID.");
    }
    if (contact.kind === "separate" && firstLogicalId === secondLogicalId) {
      throw new Error("Separate terrain-area contact unexpectedly shares a logical area ID.");
    }
    counts[contact.kind] += 1;
    if (contact.kind === "single") {
      if (groupedPhysicalAreaIds.has(firstId) || groupedPhysicalAreaIds.has(secondId)) {
        throw new Error("Physical terrain area belongs to multiple logical groups.");
      }
      groupedPhysicalAreaIds.add(firstId);
      groupedPhysicalAreaIds.add(secondId);
    }
    if (
      !Array.isArray(contact.source_icon_ids)
      || contact.source_icon_ids.length !== 1
      || typeof contact.source_icon_ids[0] !== "string"
      || contact.source_icon_ids[0].length === 0
    ) {
      throw new Error("Terrain-area contact requires exactly one source icon ID.");
    }
    const sourceX = contact.source_icon_x_inches;
    const sourceY = contact.source_icon_y_inches;
    if (
      typeof sourceX !== "number"
      || !Number.isFinite(sourceX)
      || sourceX < 0
      || sourceX > 44
      || Math.abs(sourceX / 0.05 - Math.round(sourceX / 0.05)) > 0.000001
      || typeof sourceY !== "number"
      || !Number.isFinite(sourceY)
      || sourceY < 0
      || sourceY > 60
      || Math.abs(sourceY / 0.05 - Math.round(sourceY / 0.05)) > 0.000001
    ) {
      throw new Error("Terrain-area contact source position is invalid.");
    }
    const sourceGap = contact.source_pair_gap_inches;
    const runtimeGap = contact.runtime_pair_gap_inches;
    const runtimeOverlap = contact.runtime_pair_overlap_square_inches;
    const runtimeGapLimit = 0.050001;
    if (
      typeof sourceGap !== "number"
      || !Number.isFinite(sourceGap)
      || sourceGap < 0
      || typeof runtimeGap !== "number"
      || !Number.isFinite(runtimeGap)
      || runtimeGap < 0
      || runtimeGap > runtimeGapLimit
      || typeof runtimeOverlap !== "number"
      || !Number.isFinite(runtimeOverlap)
      || runtimeOverlap < 0
      || runtimeOverlap > 0.000001
    ) {
      throw new Error("Terrain-area contact violates the 0.05-inch closure tolerance.");
    }
    counts.maximumRuntimeGapInches = Math.max(
      counts.maximumRuntimeGapInches,
      runtimeGap,
    );
  }
  return counts;
}

function drawTerrainAreaContacts(context, camera, contacts) {
  for (const contact of contacts) {
    const projected = projectPoint(
      worldPoint(contact.source_icon_x_inches, contact.source_icon_y_inches, 0.11),
      camera,
    );
    if (projected === null) {
      continue;
    }
    const isSingle = contact.kind === "single";
    const color = isSingle ? COLORS.singleAreaContact : COLORS.separateAreaContact;
    context.save();
    context.fillStyle = "rgba(255, 255, 255, 0.9)";
    context.strokeStyle = color;
    context.lineWidth = 1.8;
    for (const offset of [-3.2, 3.2]) {
      context.beginPath();
      context.arc(projected.x + offset, projected.y, 2.5, 0, Math.PI * 2);
      context.fill();
      context.stroke();
    }
    context.beginPath();
    if (isSingle) {
      context.moveTo(projected.x - 0.7, projected.y);
      context.lineTo(projected.x + 0.7, projected.y);
    } else {
      context.moveTo(projected.x, projected.y - 4.4);
      context.lineTo(projected.x, projected.y + 4.4);
    }
    context.stroke();
    context.restore();
  }
}

function resolveObjectiveTerrainFootprints(objectivesById, areasById, objectiveTerrainAreas) {
  if (!Array.isArray(objectiveTerrainAreas)) {
    throw new Error("Objective-terrain bindings must be an array.");
  }
  const seenObjectiveIds = new Set();
  const resolved = [];
  for (const binding of objectiveTerrainAreas) {
    const objectiveId = binding.objective_marker_id;
    const objective = objectivesById[objectiveId];
    if (objective === undefined) {
      throw new Error(`Objective-terrain binding references unknown objective: ${String(objectiveId)}.`);
    }
    if (seenObjectiveIds.has(objectiveId)) {
      throw new Error(`Objective has duplicate terrain bindings: ${objectiveId}.`);
    }
    if (binding.objective_role !== objective.objective_role) {
      throw new Error(`Objective-terrain binding role does not match objective: ${objectiveId}.`);
    }
    if (!Array.isArray(binding.terrain_area_ids) || binding.terrain_area_ids.length === 0) {
      throw new Error(`Objective-terrain binding has no footprint areas: ${objectiveId}.`);
    }
    const seenAreaIds = new Set();
    const areas = [];
    for (const areaId of binding.terrain_area_ids) {
      if (seenAreaIds.has(areaId)) {
        throw new Error(`Objective-terrain binding repeats area: ${areaId}.`);
      }
      const area = areasById[areaId];
      if (area === undefined) {
        throw new Error(`Objective-terrain binding references unknown area: ${areaId}.`);
      }
      seenAreaIds.add(areaId);
      areas.push(area);
    }
    seenObjectiveIds.add(objectiveId);
    resolved.push({ objective, binding, areas });
  }
  return resolved.sort((left, right) =>
    left.objective.objective_id.localeCompare(right.objective.objective_id),
  );
}

function drawObjectiveTerrainFootprints(context, camera, objectiveFootprints) {
  for (const footprint of objectiveFootprints) {
    const projectedPolygons = [];
    for (const area of footprint.areas) {
      const points = shapeWorldPoints(area.footprint, 0.055);
      const screenPoints = projectWorldPoints(points, camera);
      if (screenPoints === null) {
        continue;
      }
      drawScreenPolygon(context, screenPoints, {
        fill: hexToRgba(COLORS.objective, 0.2),
        stroke: hexToRgba(COLORS.objective, 0.95),
        lineWidth: 2,
      });
      projectedPolygons.push(screenPoints);
    }
    if (projectedPolygons.length > 0) {
      state.hitRegions.push(
        hitRecord(
          projectedPolygons,
          [],
          entityRecord("objective", footprint.objective, footprint.binding),
        ),
      );
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
    drawHatchedScreenPolygon(
      context,
      screenPoints,
      {
        fill: hexToRgba(color, 0.32),
        stroke: hexToRgba(color, 0.96),
        lineWidth: 1.4,
        classification: feature.classification,
      },
      camera,
    );
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

function drawHatchedScreenPolygon(context, points, style, viewport) {
  drawScreenPolygon(context, points, style);
  context.save();
  context.beginPath();
  movePolygonPath(context, points);
  context.clip();
  context.strokeStyle = hexToRgba(classificationColor(style.classification), 0.28);
  context.lineWidth = 0.7;
  for (const segment of hatchLineSegments(points, style.classification, viewport)) {
    context.beginPath();
    context.moveTo(segment.start.x, segment.start.y);
    context.lineTo(segment.end.x, segment.end.y);
    context.stroke();
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

function drawWorldLine(context, camera, start, end, stroke, lineWidth, lineDash = []) {
  const clippedLine = clipWorldLineToNearPlane(start, end, camera);
  if (clippedLine === null) {
    return;
  }
  const projectedStart = projectPoint(clippedLine[0], camera);
  const projectedEnd = projectPoint(clippedLine[1], camera);
  if (projectedStart === null || projectedEnd === null) {
    throw new Error("Near-plane line clipping produced an unprojectable endpoint.");
  }
  context.save();
  context.beginPath();
  context.moveTo(projectedStart.x, projectedStart.y);
  context.lineTo(projectedEnd.x, projectedEnd.y);
  context.strokeStyle = stroke;
  context.lineWidth = lineWidth;
  context.setLineDash(lineDash);
  context.stroke();
  context.restore();
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
    appendDetail(definitionList, "Logical area", payload.logical_terrain_area_id);
    appendDetail(definitionList, "Classification", humanize(payload.classification));
    appendDetail(definitionList, "Source", payload.source_id);
  } else if (entity.kind === "objective") {
    appendDetail(definitionList, "Role", humanize(payload.objective_role));
    appendDetail(
      definitionList,
      "Footprint areas",
      entity.hint.terrain_area_ids.join(", "),
    );
    appendDetail(
      definitionList,
      "Position",
      `${formatNumber(payload.position.x_inches)}, ${formatNumber(payload.position.y_inches)}, ${formatNumber(payload.position.z_inches)} in`,
    );
    appendDetail(definitionList, "Footprint source", entity.hint.source_id);
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
