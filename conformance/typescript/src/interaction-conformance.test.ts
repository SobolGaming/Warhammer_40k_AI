import assert from "node:assert/strict";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  ContractRegistry,
  type InteractionConformance,
  type ParameterizedSubmission,
  parseJsonFile,
} from "./contract.js";
import {
  constructInteractionSubmission,
  selectInteractionRenderer,
  selectSubmissionVariant,
} from "./interaction.js";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const contractRoot = resolve(repositoryRoot, "contracts");

test("generated client constructs every published interaction conformance case", () => {
  const registry = new ContractRegistry(contractRoot);
  const artifact = registry.validate<InteractionConformance>(
    "interaction-conformance.schema.json",
    parseJsonFile(resolve(contractRoot, "examples/decisions/interaction-conformance.json")),
  );
  const manifest = parseJsonFile(resolve(contractRoot, "manifest.json")) as {
    interaction_conformance_case_count: number;
  };
  assert.equal(artifact.cases.length, manifest.interaction_conformance_case_count);

  const seen = new Set<string>();
  for (const conformanceCase of artifact.cases) {
    assert.equal(seen.has(conformanceCase.case_id), false);
    seen.add(conformanceCase.case_id);

    const request = conformanceCase.request;
    const selection = selectInteractionRenderer(request);
    const variant = selectSubmissionVariant(request, conformanceCase.submission_variant_id);
    const proposalPayload = conformanceCase.proposal_payload;
    const firstOption = request.options[0];
    const submission =
      request.interaction.submission_kind === "finite"
        ? constructInteractionSubmission(request, {
            resultId: `typescript:${conformanceCase.case_id}`,
            selectedOptionId: firstOption?.option_id ?? "",
          })
        : constructInteractionSubmission(request, {
            resultId: `typescript:${conformanceCase.case_id}`,
            proposalPayload: proposalPayload as ParameterizedSubmission["payload"],
          });
    registry.validateReference(selection.submissionSchemaRef, submission);

    if (proposalPayload !== null) {
      assert.notEqual(variant.proposalSchemaRef, null);
      assert.notEqual(selection.proposalSchemaRef, null);
      registry.validateReference(variant.proposalSchemaRef as string, proposalPayload);
      registry.validateReference(selection.proposalSchemaRef as string, proposalPayload);
    }
  }
});
