import assert from "node:assert/strict";
import test from "node:test";

import { canonicalJson, canonicalJsonSha256 } from "./canonical-json.js";

test("canonical replay comparison ignores JSON property order and whitespace", () => {
  const first: unknown = JSON.parse(
    '{"source_identity":{"game_id":"game-1","source_ids":["one","two"]},"events":[1,2]}',
  );
  const second: unknown = JSON.parse(`{
    "events": [1, 2],
    "source_identity": {"source_ids": ["one", "two"], "game_id": "game-1"}
  }`);

  assert.equal(canonicalJson(first), canonicalJson(second));
  assert.equal(canonicalJsonSha256(first), canonicalJsonSha256(second));
});

test("canonical replay comparison preserves semantic array and value differences", () => {
  const expected = { event_records: [{ event_id: "event-1", value: "café" }] };
  const reordered = { event_records: [{ value: "café", event_id: "event-1" }] };
  const drifted = { event_records: [{ event_id: "event-2", value: "café" }] };

  assert.equal(canonicalJson(expected), canonicalJson(reordered));
  assert.match(canonicalJson(expected), /caf\\u00e9/);
  assert.notEqual(canonicalJsonSha256(expected), canonicalJsonSha256(drifted));
});
