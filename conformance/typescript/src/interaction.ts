import type { SessionProjection } from "./contract.js";

type PendingDecision = NonNullable<SessionProjection["projection"]["pending_decision"]>;
type InteractionDescriptor = NonNullable<PendingDecision["interaction"]>;

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
}

export function selectInteractionRenderer(
  request: PendingDecision,
): InteractionRendererSelection {
  const interaction = request.interaction;
  if (interaction === undefined || interaction === null) {
    throw new Error("Visible pending decision requires engine-authored interaction metadata.");
  }
  return {
    renderer: rendererForKind(interaction.interaction_kind),
    requiredInputs: interaction.required_inputs,
    submissionSchemaRef: interaction.constraints.submission_schema_ref,
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
