"use strict";

(function installViewerGeometry(createGeometry) {
  const geometry = createGeometry();
  if (typeof module === "object" && module.exports !== undefined) {
    module.exports = geometry;
  }
  if (typeof globalThis === "object") {
    globalThis.BattlefieldViewerGeometry = geometry;
  }
})(function createViewerGeometry() {
  const DEG_TO_RAD = Math.PI / 180;
  const RAD_TO_DEG = 180 / Math.PI;
  const NEAR_PLANE_DEPTH = 0.05;
  const PROJECTION_EPSILON = 0.0000001;
  const HATCH_SPACING = 9;

  function cameraForBounds(bounds, width, height, cameraState) {
    const battlefieldWidth = Number(bounds.max_x_inches) - Number(bounds.min_x_inches);
    const battlefieldDepth = Number(bounds.max_y_inches) - Number(bounds.min_y_inches);
    const target = {
      x: Number(bounds.min_x_inches) + battlefieldWidth / 2,
      y: Number(bounds.min_y_inches) + battlefieldDepth / 2,
      z: 2.25,
    };
    const distance = Math.max(battlefieldWidth, battlefieldDepth) * 1.48 / cameraState.zoom;
    const elevation = clamp(cameraState.elevation, 12 * DEG_TO_RAD, 89.5 * DEG_TO_RAD);
    const horizontalDistance = distance * Math.cos(elevation);
    const cameraPosition = {
      x: target.x + horizontalDistance * Math.cos(cameraState.azimuth),
      y: target.y + horizontalDistance * Math.sin(cameraState.azimuth),
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
    if (depth < NEAR_PLANE_DEPTH - PROJECTION_EPSILON) {
      return null;
    }
    const perspective = camera.focalLength / depth;
    return {
      x: camera.width / 2 + dot(relative, camera.right) * perspective,
      y: camera.height / 2 - dot(relative, camera.up) * perspective,
      depth,
    };
  }

  function projectWorldPoints(points, camera) {
    const clippedPoints = clipWorldPolygonToNearPlane(points, camera);
    if (clippedPoints.length < 3) {
      return null;
    }
    const projected = [];
    for (const point of clippedPoints) {
      const screenPoint = projectPoint(point, camera);
      if (screenPoint === null) {
        throw new Error("Near-plane polygon clipping produced an unprojectable vertex.");
      }
      projected.push(screenPoint);
    }
    return projected;
  }

  function clipWorldPolygonToNearPlane(points, camera) {
    if (!Array.isArray(points) || points.length < 3) {
      throw new Error("World polygon must contain at least three points.");
    }
    const clipped = [];
    let previous = points[points.length - 1];
    let previousDepth = cameraDepth(previous, camera);
    for (const current of points) {
      const currentDepth = cameraDepth(current, camera);
      const previousInside = previousDepth >= NEAR_PLANE_DEPTH;
      const currentInside = currentDepth >= NEAR_PLANE_DEPTH;
      if (currentInside) {
        if (!previousInside) {
          clipped.push(nearPlaneIntersection(previous, current, previousDepth, currentDepth));
        }
        clipped.push(current);
      } else if (previousInside) {
        clipped.push(nearPlaneIntersection(previous, current, previousDepth, currentDepth));
      }
      previous = current;
      previousDepth = currentDepth;
    }
    return clipped;
  }

  function clipWorldLineToNearPlane(start, end, camera) {
    const startDepth = cameraDepth(start, camera);
    const endDepth = cameraDepth(end, camera);
    const startInside = startDepth >= NEAR_PLANE_DEPTH;
    const endInside = endDepth >= NEAR_PLANE_DEPTH;
    if (!startInside && !endInside) {
      return null;
    }
    if (startInside && endInside) {
      return [start, end];
    }
    const intersection = nearPlaneIntersection(start, end, startDepth, endDepth);
    return startInside ? [start, intersection] : [intersection, end];
  }

  function nearPlaneIntersection(start, end, startDepth, endDepth) {
    const depthDelta = endDepth - startDepth;
    if (Math.abs(depthDelta) <= PROJECTION_EPSILON) {
      throw new Error("Near-plane intersection requires a crossing segment.");
    }
    const amount = (NEAR_PLANE_DEPTH - startDepth) / depthDelta;
    return worldPoint(
      start.x + (end.x - start.x) * amount,
      start.y + (end.y - start.y) * amount,
      start.z + (end.z - start.z) * amount,
    );
  }

  function cameraDepth(point, camera) {
    return dot(subtract(point, camera.position), camera.forward);
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

  function hatchLineSegments(points, classification, viewport) {
    const bounds = visibleScreenBounds(points, viewport);
    if (bounds === null) {
      return [];
    }
    const segments = [];
    const directions = hatchDirections(classification);
    for (const direction of directions) {
      for (
        let offset = bounds.minX - bounds.height;
        offset < bounds.maxX + bounds.height;
        offset += HATCH_SPACING
      ) {
        segments.push({
          start: {
            x: offset,
            y: direction > 0 ? bounds.maxY : bounds.minY,
          },
          end: {
            x: offset + bounds.height,
            y: direction > 0 ? bounds.minY : bounds.maxY,
          },
        });
      }
    }
    return segments;
  }

  function maximumHatchStrokeCount(width, height, classification) {
    const directions = hatchDirections(classification).length;
    return directions * Math.ceil((Number(width) + Number(height) * 2) / HATCH_SPACING);
  }

  function visibleScreenBounds(points, viewport) {
    if (!(Number(viewport.width) > 0) || !(Number(viewport.height) > 0)) {
      throw new Error("Hatch viewport dimensions must be positive.");
    }
    const bounds = screenBounds(points);
    if (
      bounds.maxX < 0 ||
      bounds.minX > viewport.width ||
      bounds.maxY < 0 ||
      bounds.minY > viewport.height
    ) {
      return null;
    }
    const minX = clamp(bounds.minX, 0, viewport.width);
    const maxX = clamp(bounds.maxX, 0, viewport.width);
    const minY = clamp(bounds.minY, 0, viewport.height);
    const maxY = clamp(bounds.maxY, 0, viewport.height);
    return { minX, maxX, minY, maxY, height: maxY - minY };
  }

  function hatchDirections(classification) {
    if (classification === "mixed") {
      return [1, -1];
    }
    if (classification === "light") {
      return [-1];
    }
    if (classification === "dense" || classification === "unknown") {
      return [1];
    }
    throw new Error(`Unsupported hatch classification: ${String(classification)}.`);
  }

  function screenBounds(points) {
    if (!Array.isArray(points) || points.length < 3) {
      throw new Error("Screen polygon must contain at least three points.");
    }
    const xValues = points.map((point) => point.x);
    const yValues = points.map((point) => point.y);
    return {
      minX: Math.min(...xValues),
      maxX: Math.max(...xValues),
      minY: Math.min(...yValues),
      maxY: Math.max(...yValues),
    };
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

  function clamp(value, minimum, maximum) {
    return Math.min(maximum, Math.max(minimum, value));
  }

  return Object.freeze({
    DEG_TO_RAD,
    RAD_TO_DEG,
    cameraForBounds,
    clipWorldLineToNearPlane,
    clipWorldPolygonToNearPlane,
    ellipseWorldPoints,
    hatchLineSegments,
    maximumHatchStrokeCount,
    projectPoint,
    projectWorldPoints,
    rectangleWorldPoints,
    shapeWorldPoints,
    worldPoint,
  });
});
