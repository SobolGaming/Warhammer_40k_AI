import type {
  FiniteSubmission,
  InteractionRequest,
  ParameterizedSubmission,
} from "./contract.js";

type InteractionDescriptor = NonNullable<InteractionRequest["interaction"]>;
type InteractionVariant = InteractionDescriptor["submission_variants"][number];

export type InteractionRenderer =
  | "battlefield-point-picker"
  | "confirmation"
  | "dice-picker"
  | "entity-picker"
  | "finite-option-list"
  | "model-pose-editor"
  | "multi-model-placement"
  | "opportunity-window"
  | "ordered-sequencing"
  | "path-editor"
  | "quantity-picker"
  | "roster-editor"
  | "weapon-allocation-matrix";

export interface InteractionRendererSelection {
  readonly renderer: InteractionRenderer;
  readonly requiredInputs: readonly string[];
  readonly submissionSchemaRef: string;
  readonly proposalSchemaRef: string | null;
  readonly variants: readonly InteractionVariantSelection[];
}

export interface InteractionVariantSelection {
  readonly variantId: string;
  readonly renderer: InteractionRenderer;
  readonly requiredInputs: readonly string[];
  readonly proposalSchemaRef: string | null;
  readonly displayLabel: string;
}

export interface InteractionSubmissionInput {
  readonly resultId: string;
  readonly selectedOptionId?: string;
  readonly proposalPayload?: ParameterizedSubmission["payload"];
}

export type InteractionSubmission = FiniteSubmission | ParameterizedSubmission;

export function selectInteractionRenderer(
  request: InteractionRequest,
): InteractionRendererSelection {
  const interaction = request.interaction;
  if (interaction === undefined || interaction === null) {
    throw new Error("Visible pending decision requires engine-authored interaction metadata.");
  }
  return {
    renderer: rendererForKind(interaction.interaction_kind),
    requiredInputs: interaction.required_inputs,
    submissionSchemaRef: interaction.constraints.submission_schema_ref,
    proposalSchemaRef: interaction.constraints.proposal_schema_ref,
    variants: interaction.submission_variants.map(selectVariant),
  };
}

export function selectSubmissionVariant(
  request: InteractionRequest,
  variantId: string,
): InteractionVariantSelection {
  const selection = selectInteractionRenderer(request);
  const variant = selection.variants.find((candidate) => candidate.variantId === variantId);
  if (variant === undefined) {
    throw new Error(`Interaction does not publish submission variant ${variantId}.`);
  }
  return variant;
}

export function constructInteractionSubmission(
  request: InteractionRequest,
  input: InteractionSubmissionInput,
): InteractionSubmission {
  const interaction = request.interaction;
  if (interaction === null) {
    throw new Error("Visible interaction request requires metadata.");
  }
  if (interaction.submission_kind === "finite") {
    if (request.actor_id === null) {
      throw new Error("Finite interaction requires an actor.");
    }
    const optionId = input.selectedOptionId;
    if (optionId === undefined || !request.options.some((option) => option.option_id === optionId)) {
      throw new Error("Finite interaction requires a published option ID.");
    }
    return {
      schema_version: "finite-submission-v1",
      actor_id: request.actor_id,
      option_id: optionId,
      result_id: input.resultId,
    };
  }
  if (input.proposalPayload === undefined) {
    throw new Error("Parameterized interaction requires a proposal payload.");
  }
  if (request.actor_id === null) {
    throw new Error("Parameterized interaction requires an actor.");
  }
  return {
    schema_version: "parameterized-submission-v1",
    actor_id: request.actor_id,
    payload: input.proposalPayload,
    result_id: input.resultId,
  };
}

function selectVariant(variant: InteractionVariant): InteractionVariantSelection {
  return {
    variantId: variant.variant_id,
    renderer: rendererForKind(variant.interaction_kind),
    requiredInputs: variant.required_inputs,
    proposalSchemaRef: variant.proposal_schema_ref,
    displayLabel: variant.display_label,
  };
}

function rendererForKind(
  interactionKind: InteractionDescriptor["interaction_kind"],
): InteractionRenderer {
  switch (interactionKind) {
    case "battlefield_point_placement":
      return "battlefield-point-picker";
    case "confirmation":
      return "confirmation";
    case "dice_selection":
      return "dice-picker";
    case "entity_selection":
      return "entity-picker";
    case "finite_option_list":
      return "finite-option-list";
    case "model_pose_placement":
      return "model-pose-editor";
    case "multi_model_placement":
      return "multi-model-placement";
    case "opportunity_window":
      return "opportunity-window";
    case "ordered_sequencing":
      return "ordered-sequencing";
    case "path_editor":
      return "path-editor";
    case "quantity_selection":
      return "quantity-picker";
    case "roster_construction":
      return "roster-editor";
    case "weapon_allocation_matrix":
      return "weapon-allocation-matrix";
  }
}
