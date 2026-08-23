import type { ParameterizedPayload, SessionCommandEnvelope } from "../contract.js";

const validFiniteCommand = {
  schema_version: "session-command-envelope-v2-weapon-instances",
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
  schema_version: "session-command-envelope-v2-weapon-instances",
  session_id: "session-missing",
  expected_session_revision: 0,
  request_id: null,
  result_id: null,
  submission: { submission_kind: "start_session" },
};
void missingRequiredField;

const extraRequestField = {
  schema_version: "session-command-envelope-v2-weapon-instances",
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
  schema_version: "session-command-envelope-v2-weapon-instances",
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

type ShootingDeclarationPayload = Extract<
  ParameterizedPayload,
  { proposal_kind: "shooting_declaration" }
>;
type FiringDeckSelection = NonNullable<
  ShootingDeclarationPayload["firing_deck_selection"]
>;
type FiringDeckWeaponSelection = FiringDeckSelection["weapon_selections"][number];
type IsRequiredKey<Value, Key extends keyof Value> = Record<never, never> extends Pick<
  Value,
  Key
>
  ? false
  : true;

const firingDeckWeaponInstanceIdIsRequired: IsRequiredKey<
  FiringDeckWeaponSelection,
  "weapon_instance_id"
> = true;
void firingDeckWeaponInstanceIdIsRequired;

const firingDeckSelectionHasExactRuntimeFields: Record<keyof FiringDeckSelection, true> = {
  player_id: true,
  battle_round: true,
  transport_unit_instance_id: true,
  firing_deck_value: true,
  weapon_selections: true,
  already_shot_unit_instance_ids: true,
};
void firingDeckSelectionHasExactRuntimeFields;

const firingDeckWeaponSelectionHasExactRuntimeFields: Record<
  keyof FiringDeckWeaponSelection,
  true
> = {
  weapon_instance_id: true,
  embarked_unit_instance_id: true,
  model_instance_id: true,
  wargear_id: true,
  weapon_profile: true,
};
void firingDeckWeaponSelectionHasExactRuntimeFields;
