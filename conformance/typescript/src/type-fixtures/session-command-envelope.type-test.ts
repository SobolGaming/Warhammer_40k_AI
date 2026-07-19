import type { SessionCommandEnvelope } from "../contract.js";

const validFiniteCommand = {
  schema_version: "session-command-envelope-v1",
  command_id: "command-valid",
  session_id: "session-valid",
  expected_session_revision: 4,
  request_id: "request-valid",
  result_id: "result-valid",
  submission: { submission_kind: "finite_option", option_id: "option-valid" },
} satisfies SessionCommandEnvelope;
void validFiniteCommand;

// @ts-expect-error command_id is required by the generated operation request body.
const missingRequiredField: SessionCommandEnvelope = {
  schema_version: "session-command-envelope-v1",
  session_id: "session-missing",
  expected_session_revision: 0,
  request_id: null,
  result_id: null,
  submission: { submission_kind: "start_session" },
};
void missingRequiredField;

const extraRequestField = {
  schema_version: "session-command-envelope-v1",
  command_id: "command-extra",
  session_id: "session-extra",
  expected_session_revision: 0,
  request_id: null,
  result_id: null,
  submission: { submission_kind: "start_session" },
  // @ts-expect-error extra request fields fail generated-operation structural checking.
  actor_id: "player-a",
} satisfies SessionCommandEnvelope;
void extraRequestField;

const invalidSubmissionCombination = {
  schema_version: "session-command-envelope-v1",
  command_id: "command-invalid-combination",
  session_id: "session-invalid-combination",
  expected_session_revision: 2,
  request_id: "request-invalid-combination",
  result_id: "result-invalid-combination",
  submission: {
    submission_kind: "finite_option",
    // @ts-expect-error finite submissions accept option_id, not parameterized payload.
    payload: { proposal_kind: "deployment_placement" },
  },
} satisfies SessionCommandEnvelope;
void invalidSubmissionCombination;
