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
