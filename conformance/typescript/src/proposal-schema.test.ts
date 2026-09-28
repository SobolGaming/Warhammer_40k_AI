import assert from "node:assert/strict";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { ContractRegistry, type InteractionConformance, parseJsonFile } from "./contract.js";
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
