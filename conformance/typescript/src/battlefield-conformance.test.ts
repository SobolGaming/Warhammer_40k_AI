import assert from "node:assert/strict";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  type BattlefieldView,
  ContractRegistry,
  type SessionProjection,
  parseJsonFile,
} from "./contract.js";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const contractRoot = resolve(repositoryRoot, "contracts");

test("generated client round-trips the Phase 18J battlefield coordinate contract", () => {
  const registry = new ContractRegistry(contractRoot);
  const gameView = registry.validate<SessionProjection["projection"]>(
    "game-view.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/projections/post_deployment_view.json")),
  );
  const battlefield = gameView.battlefield_view;
  if (battlefield === null || battlefield === undefined) {
    throw new Error("Post-deployment fixture requires battlefield_view.");
  }

  assert.equal(battlefield.coordinate_spec_version, "battlefield-coordinate-v1");
  assert.equal(battlefield.coordinate_space, "battlefield_inches_right_handed_z_up");
  assert.deepEqual(battlefield.bounds, {
    max_x_inches: 60,
    max_y_inches: 44,
    min_x_inches: 0,
    min_y_inches: 0,
    min_z_inches: 0,
  });
  const firstModel = Object.values(battlefield.authoritative.models_by_id)[0];
  assert.notEqual(firstModel, undefined);
  assert.notEqual(firstModel?.pose, null);
  assert.equal(firstModel?.geometry.measurement_shapes[0]?.kind, "circle");
  assert.equal(firstModel?.geometry.support_shape?.kind, "circle");

  const roundTrip = JSON.parse(JSON.stringify(battlefield)) as BattlefieldView;
  assert.deepEqual(roundTrip, battlefield);
  registry.validate<BattlefieldView>("battlefield-view.schema.json", roundTrip);
});

test("published geometry fixture crosses every generated battlefield union surface", () => {
  const registry = new ContractRegistry(contractRoot);
  const battlefield = registry.validate<BattlefieldView>(
    "battlefield-view.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/battlefield/geometry-conformance.json")),
  );
  const models = battlefield.authoritative.models_by_id;
  const circle = models["geometry-conformance-circle-model"];
  const oval = models["geometry-conformance-oval-model"];
  const hull = models["geometry-conformance-hull-model"];
  if (circle === undefined || oval === undefined || hull === undefined) {
    throw new Error("Geometry conformance fixture requires circle, oval, and hull models.");
  }

  assert.equal(circle.geometry.measurement_basis, "base");
  assert.equal(circle.geometry.measurement_shapes[0]?.kind, "circle");
  assert.notEqual(circle.geometry.measurement_shapes[0]?.center, null);
  assert.equal(circle.geometry.support_shape.kind, "circle");
  assert.notEqual(circle.pose?.facing_degrees, 0);

  assert.equal(oval.geometry.measurement_basis, "base");
  assert.equal(oval.geometry.measurement_shapes[0]?.kind, "ellipse");
  assert.equal(oval.geometry.measurement_shapes[0]?.rotation_degrees, 15);
  assert.equal(oval.geometry.support_shape.kind, "ellipse");

  assert.equal(hull.geometry.measurement_basis, "hull");
  assert.equal(hull.geometry.measurement_shapes[0]?.kind, "rectangle");
  assert.equal(hull.geometry.support_shape.kind, "circle");

  const terrain =
    battlefield.authoritative.terrain_features_by_id["geometry-conformance-terrain"];
  if (terrain === undefined) {
    throw new Error("Geometry conformance fixture requires terrain feature geometry.");
  }
  assert.equal(terrain.footprint.kind, "rectangle");
  assert.deepEqual(
    new Set(terrain.volumes.map((volume) => volume.volume_kind)),
    new Set(["wall", "floor"]),
  );
  assert.equal(
    battlefield.authoritative.terrain_areas_by_id["geometry-conformance-area"]?.footprint.kind,
    "polygon",
  );
  assert.notEqual(
    battlefield.authoritative.objectives_by_id["geometry-conformance-objective"],
    undefined,
  );

  const zone =
    battlefield.authoritative.deployment_zones_by_id["geometry-conformance-zone"];
  if (zone === undefined) {
    throw new Error("Geometry conformance fixture requires deployment-zone cutouts.");
  }
  assert.equal(zone.shape.circle_cutouts[0]?.kind, "circle");
  assert.equal(zone.shape.polygon_cutouts[0]?.kind, "polygon");
  assert.equal(battlefield.interaction.measurement_overlays.length, 1);
  assert.equal(battlefield.interaction.path_overlays[0]?.segments.length, 2);
  assert.equal(
    battlefield.render.hit_regions_by_entity_id["geometry-conformance-terrain"]?.shape.kind,
    "polygon",
  );

  const roundTrip = JSON.parse(JSON.stringify(battlefield)) as BattlefieldView;
  assert.deepEqual(roundTrip, battlefield);
  registry.validate<BattlefieldView>("battlefield-view.schema.json", roundTrip);
});
