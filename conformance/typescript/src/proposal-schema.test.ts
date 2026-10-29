import assert from "node:assert/strict";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ContractRegistry, type InteractionConformance, parseJsonFile,
  type SessionCommandEnvelope, type SessionCommandOutcome,
} from "./contract.js";
import { ContractHttpClient } from "./client.js";
import { selectSubmissionVariant } from "./interaction.js";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const contractRoot = resolve(repositoryRoot, "contracts");

test("ranged proposal accepts explicit target decline and an empty weapon selection", () => {
  const registry = new ContractRegistry(contractRoot);
  const artifact = registry.validate<InteractionConformance>(
    "interaction-conformance.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/decisions/interaction-conformance.json")),
  );
  const shooting = artifact.cases.find(
    (row) => row.request.decision_type === "submit_shooting_declaration",
  );
  assert.ok(shooting);
  const proposal = structuredClone(shooting.proposal_payload) as {
    declarations: { target_unit_instance_id: string | null }[];
  };
  assert.ok(proposal.declarations.length > 0);
  const variant = selectSubmissionVariant(shooting.request, shooting.submission_variant_id);
  assert.ok(variant.proposalSchemaRef);
  for (const declaration of proposal.declarations) declaration.target_unit_instance_id = null;
  registry.validateReference(variant.proposalSchemaRef, proposal);
  proposal.declarations = [];
  registry.validateReference(variant.proposalSchemaRef, proposal);
});


test("closed command error union preserves diagnostics and rejects private or mixed fields", () => {
  const registry = new ContractRegistry(contractRoot);
  for (const name of ["invalid", "unsupported", "invalid-diagnostics", "unsupported-diagnostics"]) {
    registry.validate("error-envelope.schema.json",
      parseJsonFile(resolve(contractRoot, `examples/errors/${name}.json`)));
  }
  const error = {
    schema_version: "error-envelope-v2-diagnostics",
    error: {code: "proposal_invalid", message: "Invalid proposal.", diagnostics: {
      kind: "proposal_validation",
      violations: [{violation_code: "movement_witness_model_inventory_mismatch", field: "witness"}],
    }},
  };
  registry.validate("error-envelope.schema.json", error);
  for (const diagnostics of [
    {...error.error.diagnostics, private_snapshot: {}},
    {...error.error.diagnostics, reason_code: "unsupported"},
    {...error.error.diagnostics, violations: []},
    {kind: "unsupported_reason", reason_code: "unsupported"},
  ]) {
    assert.throws(() => registry.validate("error-envelope.schema.json", {
      ...error, error: {...error.error, diagnostics},
    }));
  }
});


test("HTTP client accepts both current 422 outcome and error union branches", async (context) => {
  const registry = new ContractRegistry(contractRoot);
  const command = registry.validate<SessionCommandEnvelope>("session-command-envelope.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/sessions/session-command-envelope.json")));
  const outcome = registry.validate<SessionCommandOutcome>("session-command-outcome.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/sessions/session-command-outcome.json")));
  const responses = [
    {...outcome, accepted: false, committed: true, outcome_code: "proposal_invalid"},
    ...["invalid", "unsupported", "invalid-diagnostics", "unsupported-diagnostics"].map(name =>
      parseJsonFile(resolve(contractRoot, `examples/errors/${name}.json`))),
  ];
  const client = new ContractHttpClient("http://transport-fixture.invalid", "fixture-token", registry);
  for (const expected of responses) {
    const fetch = context.mock.method(globalThis, "fetch", async () => new Response(
      JSON.stringify(expected), {status: 422, headers: {"Content-Type": "application/json"}},
    ));
    const actual = await client.executeCommand({session_id: command.session_id}, command);
    assert.equal(actual.status, 422);
    assert.deepEqual(actual.body, expected);
    fetch.mock.restore();
  }
});
