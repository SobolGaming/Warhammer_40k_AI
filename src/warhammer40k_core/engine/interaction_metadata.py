from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TypedDict, cast

from warhammer40k_core.engine.decision_request import (
    DecisionOptionPayload,
    DecisionRequest,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

INTERACTION_DESCRIPTOR_SCHEMA_VERSION = "interaction-descriptor-v2-variants"
INTERACTION_ANNOTATED_REQUEST_SCHEMA_VERSION = "annotated-decision-request-v1"
NESTED_INTERACTION_REQUESTS_KEY = "nested_interaction_requests"


class InteractionKind(StrEnum):
    FINITE_OPTION_LIST = "finite_option_list"
    ENTITY_SELECTION = "entity_selection"
    WEAPON_ALLOCATION_MATRIX = "weapon_allocation_matrix"
    DICE_SELECTION = "dice_selection"
    ORDERED_SEQUENCING = "ordered_sequencing"
    BATTLEFIELD_POINT_PLACEMENT = "battlefield_point_placement"
    MODEL_POSE_PLACEMENT = "model_pose_placement"
    MULTI_MODEL_PLACEMENT = "multi_model_placement"
    PATH_EDITOR = "path_editor"
    ROSTER_CONSTRUCTION = "roster_construction"
    CONFIRMATION = "confirmation"
    QUANTITY_SELECTION = "quantity_selection"
    OPPORTUNITY_WINDOW = "opportunity_window"


class InteractionConstraintsPayload(TypedDict):
    candidate_option_ids: list[str]
    entity_kinds: list[str]
    minimum_selections: int | None
    maximum_selections: int | None
    maximum_distance_in: float | None
    minimum_enemy_distance_in: float | None
    exact_model_count: int | None
    must_preserve_coherency: bool | None
    may_enter_engagement_range: bool | None
    placement_kinds: list[str]
    submission_schema_ref: str
    proposal_schema_ref: str | None


class InteractionDisplayHintsPayload(TypedDict):
    confirm_label: str
    decline_label: str | None


class InteractionSubmissionVariantPayload(TypedDict):
    variant_id: str
    interaction_kind: str
    required_inputs: list[str]
    proposal_schema_ref: str | None
    display_label: str


class InteractionDescriptorPayload(TypedDict):
    schema_version: str
    interaction_kind: str
    submission_kind: str
    proposal_kind: str | None
    selected_entity_ids: list[str]
    required_inputs: list[str]
    submission_variants: list[InteractionSubmissionVariantPayload]
    constraints: InteractionConstraintsPayload
    display_hints: InteractionDisplayHintsPayload


class DecisionInteractionSupportPayload(TypedDict):
    decision_type: str
    submission_kind: str
    interaction_kinds: list[str]


class InteractionAnnotatedDecisionRequestPayload(TypedDict):
    schema_version: str
    request_id: str
    decision_type: str
    actor_id: str
    payload: JsonValue
    options: list[DecisionOptionPayload]
    is_parameterized: bool
    interaction: InteractionDescriptorPayload


@dataclass(frozen=True, slots=True)
class InteractionSpec:
    interaction_kind: InteractionKind
    entity_kinds: tuple[str, ...] = ()
    alternative_interaction_kinds: tuple[InteractionKind, ...] = ()

    def __post_init__(self) -> None:
        if type(self.interaction_kind) is not InteractionKind:
            raise GameLifecycleError("InteractionSpec requires an interaction kind.")
        if type(self.entity_kinds) is not tuple or any(
            type(value) is not str or not value for value in self.entity_kinds
        ):
            raise GameLifecycleError("InteractionSpec entity kinds must be identifiers.")
        if type(self.alternative_interaction_kinds) is not tuple or any(
            type(value) is not InteractionKind for value in self.alternative_interaction_kinds
        ):
            raise GameLifecycleError(
                "InteractionSpec alternative interaction kinds must be interaction kinds."
            )
        if self.interaction_kind in self.alternative_interaction_kinds or len(
            self.alternative_interaction_kinds
        ) != len(set(self.alternative_interaction_kinds)):
            raise GameLifecycleError("InteractionSpec interaction kinds must be unique.")

    @property
    def interaction_kinds(self) -> tuple[InteractionKind, ...]:
        return (self.interaction_kind, *self.alternative_interaction_kinds)


_FINITE_INTERACTION_SPECS = MappingProxyType(
    {
        "discard_tactical_secondary_mission": InteractionSpec(InteractionKind.CONFIRMATION),
        "draw_tactical_secondary_missions": InteractionSpec(InteractionKind.CONFIRMATION),
        "replace_tactical_secondary_mission": InteractionSpec(InteractionKind.CONFIRMATION),
        "resolve_fight_interrupt": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "resolve_reaction_window": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "resolve_sequencing_order": InteractionSpec(InteractionKind.ORDERED_SEQUENCING),
        "score_tactical_secondary_mission": InteractionSpec(InteractionKind.CONFIRMATION),
        "select_allocation_order": InteractionSpec(InteractionKind.ORDERED_SEQUENCING),
        "select_attack_weapon_group": InteractionSpec(
            InteractionKind.WEAPON_ALLOCATION_MATRIX,
            ("weapon_group",),
        ),
        "select_catalog_any_phase_once_per_battle_ability": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_catalog_post_shoot_hit_target_effect": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("target_unit",),
        ),
        "select_catalog_post_shoot_hit_target_status": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("target_unit",),
        ),
        "select_catalog_setup_reactive_shoot_charge": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_catalog_movement_target_pair": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_catalog_unit_move_completed_mortal_wounds_target": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("target_unit",),
        ),
        "select_charge_declaration_grant": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_charging_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_cult_ambush_resurgence": InteractionSpec(InteractionKind.CONFIRMATION),
        "select_damage_allocation_model": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("model",),
        ),
        "select_deployment_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_desperate_escape_model": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("model",),
        ),
        "select_destruction_reaction": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_dice_reroll": InteractionSpec(InteractionKind.DICE_SELECTION, ("die",)),
        "select_dice_result_override": InteractionSpec(
            InteractionKind.DICE_SELECTION,
            ("die",),
        ),
        "select_disembark_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_embark_transport": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("transport",),
        ),
        "select_faction_rule_battle_round_option": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_faction_rule_command_phase_start_option": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_faction_rule_fight_phase_end_option": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_faction_rule_fight_phase_start_option": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_faction_rule_setup_option": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_faction_rule_shooting_phase_start_option": InteractionSpec(
            InteractionKind.OPPORTUNITY_WINDOW
        ),
        "select_faction_rule_turn_end_option": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_feel_no_pain": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_fight_activation": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_fight_activation_ability": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_fight_unit_grant": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_healing_model": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("model",),
        ),
        "select_movement_action": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_movement_action_grant": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_movement_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_prebattle_action": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_precision_allocation": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("model_group",),
        ),
        "select_psychic_attack_modifier_ignores": InteractionSpec(
            InteractionKind.FINITE_OPTION_LIST
        ),
        "select_redeploy_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_reinforcement_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_reserve_declaration": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_resolve_target_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("target_unit",),
        ),
        "select_secondary_missions": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_shooting_type": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "select_shooting_unit": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("unit",),
        ),
        "select_shooting_unit_grant": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_stratagem_cost_modifier_option": InteractionSpec(InteractionKind.CONFIRMATION),
        "select_tracked_target": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("target_unit",),
        ),
        "select_triggered_movement": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
        "select_weapon_ability_instance": InteractionSpec(InteractionKind.FINITE_OPTION_LIST),
        "start_mission_action": InteractionSpec(InteractionKind.CONFIRMATION),
        "use_stratagem": InteractionSpec(InteractionKind.OPPORTUNITY_WINDOW),
    }
)

_PARAMETERIZED_INTERACTION_SPECS = MappingProxyType(
    {
        "submit_cult_ambush_marker_placement": InteractionSpec(
            InteractionKind.BATTLEFIELD_POINT_PLACEMENT,
            ("marker",),
            (InteractionKind.CONFIRMATION,),
        ),
        "submit_deployment_placement": InteractionSpec(
            InteractionKind.MULTI_MODEL_PLACEMENT,
            ("unit", "model"),
        ),
        "submit_melee_declaration": InteractionSpec(
            InteractionKind.WEAPON_ALLOCATION_MATRIX,
            ("attacking_model", "target_unit"),
        ),
        "submit_movement_proposal": InteractionSpec(
            InteractionKind.PATH_EDITOR,
            ("unit", "model"),
        ),
        "submit_placement_proposal": InteractionSpec(
            InteractionKind.MULTI_MODEL_PLACEMENT,
            ("unit", "model"),
        ),
        "submit_redeploy_placement": InteractionSpec(
            InteractionKind.MULTI_MODEL_PLACEMENT,
            ("unit", "model"),
        ),
        "submit_return_on_death_placement": InteractionSpec(
            InteractionKind.MODEL_POSE_PLACEMENT,
            ("model",),
        ),
        "submit_scout_move": InteractionSpec(
            InteractionKind.PATH_EDITOR,
            ("unit", "model"),
        ),
        "submit_scout_reserve_setup": InteractionSpec(
            InteractionKind.MULTI_MODEL_PLACEMENT,
            ("unit", "model"),
        ),
        "submit_shooting_declaration": InteractionSpec(
            InteractionKind.WEAPON_ALLOCATION_MATRIX,
            ("attacking_model", "target_unit"),
        ),
        "submit_stratagem_target_proposal": InteractionSpec(
            InteractionKind.ENTITY_SELECTION,
            ("target",),
        ),
    }
)

_PROPOSAL_SCHEMA_DEFINITION_BY_KIND = MappingProxyType(
    {
        "advance": "movement",
        "charge_move": "charge_move",
        "consolidate": "fight_movement",
        "cult_ambush_placement": "generic_placement",
        "deep_strike_placement": "generic_placement",
        "deployment_placement": "deployment_placement",
        "disembark_placement": "generic_placement",
        "fall_back": "movement",
        "melee_declaration": "melee_declaration",
        "normal_move": "movement",
        "pile_in": "fight_movement",
        "redeploy_placement": "prebattle_placement",
        "reinforcement_placement": "generic_placement",
        "scout_move": "scout_move",
        "scout_reserve_setup": "prebattle_placement",
        "shooting_declaration": "shooting_declaration",
        "stratagem_target_binding": "stratagem_target_binding",
        "strategic_reserves_placement": "generic_placement",
        "surge_move": "movement",
    }
)

_SPECIAL_PROPOSAL_KIND_BY_DECISION_TYPE = MappingProxyType(
    {
        "submit_cult_ambush_marker_placement": "cult_ambush_marker_placement",
        "submit_return_on_death_placement": "return_on_death_placement",
    }
)

_SPECIAL_PROPOSAL_SCHEMA_DEFINITION_BY_DECISION_TYPE = MappingProxyType(
    {
        "submit_cult_ambush_marker_placement": "cult_ambush_marker_placement",
        "submit_return_on_death_placement": "return_on_death_placement",
    }
)

_SELECTED_ENTITY_KEYS = (
    "acting_unit_instance_id",
    "destroyed_model_instance_id",
    "destroyed_unit_instance_id",
    "marker_id",
    "model_instance_id",
    "replacement_unit_instance_id",
    "selected_model_instance_id",
    "selected_unit_instance_id",
    "target_model_instance_id",
    "target_unit_instance_id",
    "unit_instance_id",
)

_NESTED_INTERACTION_DECISION_TYPES = frozenset({"select_weapon_ability_instance"})

_ENGAGEMENT_PERMITTED_PATH_KINDS = frozenset({"charge_move", "consolidate", "pile_in"})
_ENGAGEMENT_FORBIDDEN_PATH_KINDS = frozenset(
    {"advance", "fall_back", "normal_move", "scout_move", "surge_move"}
)


def interaction_kinds_for_decision_type(
    *,
    decision_type: str,
    submission_kind: str,
) -> tuple[str, ...]:
    spec = _interaction_spec(decision_type=decision_type, submission_kind=submission_kind)
    return tuple(kind.value for kind in spec.interaction_kinds)


def interaction_descriptor_for_request(request: DecisionRequest) -> InteractionDescriptorPayload:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Interaction metadata requires a DecisionRequest.")
    submission_kind = "parameterized" if request.is_parameterized_submission_request() else "finite"
    spec = _interaction_spec(
        decision_type=request.decision_type,
        submission_kind=submission_kind,
    )
    context = _request_context(request)
    proposal_kind = _proposal_kind(request=request, context=context)
    variants = _submission_variants(
        request=request,
        interaction_kind=spec.interaction_kind,
        proposal_kind=proposal_kind,
    )
    required_inputs = variants[0]["required_inputs"] if len(variants) == 1 else []
    return {
        "schema_version": INTERACTION_DESCRIPTOR_SCHEMA_VERSION,
        "interaction_kind": spec.interaction_kind.value,
        "submission_kind": submission_kind,
        "proposal_kind": proposal_kind,
        "selected_entity_ids": _selected_entity_ids(context),
        "required_inputs": list(required_inputs),
        "submission_variants": variants,
        "constraints": _constraints(
            request=request,
            context=context,
            spec=spec,
            proposal_kind=proposal_kind,
        ),
        "display_hints": _display_hints(
            spec.interaction_kind,
            has_alternative=len(variants) > 1,
        ),
    }


def interaction_annotated_decision_request_payload(
    request: DecisionRequest,
) -> InteractionAnnotatedDecisionRequestPayload:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Interaction annotation requires a DecisionRequest.")
    if request.actor_id is None:
        raise GameLifecycleError("Interaction annotation requires an actor.")
    return {
        "schema_version": INTERACTION_ANNOTATED_REQUEST_SCHEMA_VERSION,
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
        "payload": request.payload,
        "options": [option.to_payload() for option in request.options],
        "is_parameterized": request.is_parameterized_submission_request(),
        "interaction": interaction_descriptor_for_request(request),
    }


def nested_interaction_request_payloads(
    request: DecisionRequest,
) -> list[InteractionAnnotatedDecisionRequestPayload]:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Nested interaction lookup requires a DecisionRequest.")
    if not isinstance(request.payload, dict):
        return []
    if NESTED_INTERACTION_REQUESTS_KEY not in request.payload:
        return []
    value = validate_json_value(request.payload[NESTED_INTERACTION_REQUESTS_KEY])
    if not isinstance(value, list):
        raise GameLifecycleError("Nested interaction requests must be an array.")
    for entry in value:
        if not isinstance(entry, dict):
            raise GameLifecycleError("Nested interaction request entries must be objects.")
        if entry.get("schema_version") != INTERACTION_ANNOTATED_REQUEST_SCHEMA_VERSION:
            raise GameLifecycleError("Nested interaction request schema version drifted.")
        if not isinstance(entry.get("interaction"), dict):
            raise GameLifecycleError("Nested interaction request requires metadata.")
    return cast(list[InteractionAnnotatedDecisionRequestPayload], value)


def adapter_visible_interaction_decision_types() -> tuple[str, ...]:
    return tuple(sorted((*_FINITE_INTERACTION_SPECS, *_PARAMETERIZED_INTERACTION_SPECS)))


def registered_interaction_decision_types() -> tuple[str, ...]:
    return tuple(
        decision_type
        for decision_type in adapter_visible_interaction_decision_types()
        if decision_type not in _NESTED_INTERACTION_DECISION_TYPES
    )


def decision_interaction_support_rows() -> list[DecisionInteractionSupportPayload]:
    rows = [
        DecisionInteractionSupportPayload(
            decision_type=decision_type,
            submission_kind="finite",
            interaction_kinds=[kind.value for kind in spec.interaction_kinds],
        )
        for decision_type, spec in _FINITE_INTERACTION_SPECS.items()
    ]
    rows.extend(
        DecisionInteractionSupportPayload(
            decision_type=decision_type,
            submission_kind="parameterized",
            interaction_kinds=[kind.value for kind in spec.interaction_kinds],
        )
        for decision_type, spec in _PARAMETERIZED_INTERACTION_SPECS.items()
    )
    return sorted(rows, key=lambda row: row["decision_type"])


def _interaction_spec(*, decision_type: str, submission_kind: str) -> InteractionSpec:
    if type(decision_type) is not str or not decision_type:
        raise GameLifecycleError("Interaction metadata requires a decision type.")
    if submission_kind == "finite":
        spec = _FINITE_INTERACTION_SPECS.get(decision_type)
    elif submission_kind == "parameterized":
        spec = _PARAMETERIZED_INTERACTION_SPECS.get(decision_type)
    else:
        raise GameLifecycleError("Interaction metadata submission kind is unsupported.")
    if spec is None:
        raise GameLifecycleError(
            "Decision type is missing required engine-authored interaction metadata."
        )
    return spec


def _request_context(request: DecisionRequest) -> dict[str, JsonValue]:
    if not isinstance(request.payload, dict):
        if request.is_parameterized_submission_request():
            raise GameLifecycleError("Parameterized interaction payload must be an object.")
        return {}
    proposal_request = request.payload.get("proposal_request")
    if proposal_request is None:
        return request.payload
    if not isinstance(proposal_request, dict):
        raise GameLifecycleError("Interaction proposal_request must be an object.")
    return proposal_request


def _proposal_kind(
    *,
    request: DecisionRequest,
    context: dict[str, JsonValue],
) -> str | None:
    if not request.is_parameterized_submission_request():
        return None
    special = _SPECIAL_PROPOSAL_KIND_BY_DECISION_TYPE.get(request.decision_type)
    if special is not None:
        return special
    value = context.get("proposal_kind")
    if type(value) is not str or not value:
        raise GameLifecycleError("Parameterized interaction requires proposal_kind metadata.")
    if value not in _PROPOSAL_SCHEMA_DEFINITION_BY_KIND:
        raise GameLifecycleError("Parameterized interaction proposal kind is unsupported.")
    return value


def _selected_entity_ids(context: dict[str, JsonValue]) -> list[str]:
    values: set[str] = set()
    for key in _SELECTED_ENTITY_KEYS:
        value = context.get(key)
        if type(value) is str and value:
            values.add(value)
    return sorted(values)


def _required_inputs(interaction_kind: InteractionKind) -> tuple[str, ...]:
    if interaction_kind is InteractionKind.PATH_EDITOR:
        return ("model_paths", "final_poses")
    if interaction_kind is InteractionKind.MULTI_MODEL_PLACEMENT:
        return ("model_poses",)
    if interaction_kind is InteractionKind.MODEL_POSE_PLACEMENT:
        return ("model_pose",)
    if interaction_kind is InteractionKind.BATTLEFIELD_POINT_PLACEMENT:
        return ("battlefield_point",)
    if interaction_kind is InteractionKind.WEAPON_ALLOCATION_MATRIX:
        return ("weapon_allocations", "target_allocations")
    if interaction_kind is InteractionKind.ENTITY_SELECTION:
        return ("selected_entities",)
    if interaction_kind is InteractionKind.DICE_SELECTION:
        return ("selected_dice",)
    if interaction_kind is InteractionKind.ORDERED_SEQUENCING:
        return ("ordered_options",)
    if interaction_kind is InteractionKind.QUANTITY_SELECTION:
        return ("quantity",)
    if interaction_kind is InteractionKind.ROSTER_CONSTRUCTION:
        return ("roster",)
    return ("selected_option",)


def _submission_variants(
    *,
    request: DecisionRequest,
    interaction_kind: InteractionKind,
    proposal_kind: str | None,
) -> list[InteractionSubmissionVariantPayload]:
    if request.decision_type == "submit_cult_ambush_marker_placement":
        return [
            {
                "variant_id": "place_marker",
                "interaction_kind": InteractionKind.BATTLEFIELD_POINT_PLACEMENT.value,
                "required_inputs": ["battlefield_point"],
                "proposal_schema_ref": (
                    "proposal-payload.schema.json#/$defs/cult_ambush_marker_point"
                ),
                "display_label": "Place Marker",
            },
            {
                "variant_id": "no_marker",
                "interaction_kind": InteractionKind.CONFIRMATION.value,
                "required_inputs": ["no_marker_reason"],
                "proposal_schema_ref": (
                    "proposal-payload.schema.json#/$defs/cult_ambush_no_marker"
                ),
                "display_label": "No Legal Marker Position",
            },
        ]
    proposal_schema_ref = _proposal_schema_ref(
        request=request,
        proposal_kind=proposal_kind,
    )
    return [
        {
            "variant_id": "finite_option" if proposal_kind is None else proposal_kind,
            "interaction_kind": interaction_kind.value,
            "required_inputs": list(_required_inputs(interaction_kind)),
            "proposal_schema_ref": proposal_schema_ref,
            "display_label": _display_hints(
                interaction_kind,
                has_alternative=False,
            )["confirm_label"],
        }
    ]


def _constraints(
    *,
    request: DecisionRequest,
    context: dict[str, JsonValue],
    spec: InteractionSpec,
    proposal_kind: str | None,
) -> InteractionConstraintsPayload:
    maximum_distance = _optional_number(
        context,
        keys=("maximum_distance_inches", "scout_distance_inches"),
    )
    minimum_enemy_distance = _optional_number(
        context,
        keys=("required_enemy_horizontal_distance_inches", "minimum_enemy_distance_inches"),
    )
    model_ids = context.get("model_instance_ids")
    exact_model_count = None
    if isinstance(model_ids, list):
        if any(type(value) is not str or not value for value in model_ids):
            raise GameLifecycleError("Interaction model_instance_ids must contain identifiers.")
        exact_model_count = len(model_ids)
    placement_kinds = _identifier_list(context.get("placement_kinds"))
    placement_kind = context.get("placement_kind")
    if type(placement_kind) is str and placement_kind and placement_kind not in placement_kinds:
        placement_kinds.append(placement_kind)
    must_preserve_coherency: bool | None = None
    if spec.interaction_kind in {
        InteractionKind.MULTI_MODEL_PLACEMENT,
        InteractionKind.PATH_EDITOR,
    }:
        must_preserve_coherency = True
    may_enter_engagement_range: bool | None = None
    if proposal_kind in _ENGAGEMENT_PERMITTED_PATH_KINDS:
        may_enter_engagement_range = True
    elif proposal_kind in _ENGAGEMENT_FORBIDDEN_PATH_KINDS:
        may_enter_engagement_range = False
    candidate_option_ids = [option.option_id for option in request.options]
    minimum_selections, maximum_selections = _selection_cardinality(
        interaction_kind=spec.interaction_kind,
        exact_model_count=exact_model_count,
        has_alternative=request.decision_type == "submit_cult_ambush_marker_placement",
    )
    return {
        "candidate_option_ids": candidate_option_ids,
        "entity_kinds": list(spec.entity_kinds),
        "minimum_selections": minimum_selections,
        "maximum_selections": maximum_selections,
        "maximum_distance_in": maximum_distance,
        "minimum_enemy_distance_in": minimum_enemy_distance,
        "exact_model_count": exact_model_count,
        "must_preserve_coherency": must_preserve_coherency,
        "may_enter_engagement_range": may_enter_engagement_range,
        "placement_kinds": sorted(placement_kinds),
        "submission_schema_ref": _submission_schema_ref(request=request),
        "proposal_schema_ref": _proposal_schema_ref(
            request=request,
            proposal_kind=proposal_kind,
        ),
    }


def _selection_cardinality(
    *,
    interaction_kind: InteractionKind,
    exact_model_count: int | None,
    has_alternative: bool,
) -> tuple[int | None, int | None]:
    if has_alternative:
        return None, None
    if interaction_kind in {
        InteractionKind.BATTLEFIELD_POINT_PLACEMENT,
        InteractionKind.CONFIRMATION,
        InteractionKind.ENTITY_SELECTION,
        InteractionKind.FINITE_OPTION_LIST,
        InteractionKind.MODEL_POSE_PLACEMENT,
        InteractionKind.OPPORTUNITY_WINDOW,
    }:
        return 1, 1
    if (
        interaction_kind
        in {
            InteractionKind.MULTI_MODEL_PLACEMENT,
            InteractionKind.PATH_EDITOR,
        }
        and exact_model_count is not None
    ):
        return exact_model_count, exact_model_count
    return None, None


def _submission_schema_ref(
    *,
    request: DecisionRequest,
) -> str:
    if not request.is_parameterized_submission_request():
        return "finite-submission.schema.json"
    return "parameterized-submission.schema.json"


def _proposal_schema_ref(
    *,
    request: DecisionRequest,
    proposal_kind: str | None,
) -> str | None:
    if not request.is_parameterized_submission_request():
        return None
    special_definition = _SPECIAL_PROPOSAL_SCHEMA_DEFINITION_BY_DECISION_TYPE.get(
        request.decision_type
    )
    if special_definition is not None:
        return f"proposal-payload.schema.json#/$defs/{special_definition}"
    if proposal_kind is None:
        raise GameLifecycleError("Parameterized interaction requires a proposal kind.")
    definition = _PROPOSAL_SCHEMA_DEFINITION_BY_KIND.get(proposal_kind)
    if definition is None:
        raise GameLifecycleError("Parameterized interaction schema reference is unsupported.")
    return f"proposal-payload.schema.json#/$defs/{definition}"


def _display_hints(
    interaction_kind: InteractionKind,
    *,
    has_alternative: bool,
) -> InteractionDisplayHintsPayload:
    labels = {
        InteractionKind.BATTLEFIELD_POINT_PLACEMENT: "Place Point",
        InteractionKind.CONFIRMATION: "Confirm",
        InteractionKind.DICE_SELECTION: "Confirm Dice",
        InteractionKind.ENTITY_SELECTION: "Confirm Selection",
        InteractionKind.FINITE_OPTION_LIST: "Confirm Option",
        InteractionKind.MODEL_POSE_PLACEMENT: "Place Model",
        InteractionKind.MULTI_MODEL_PLACEMENT: "Submit Placement",
        InteractionKind.OPPORTUNITY_WINDOW: "Resolve Opportunity",
        InteractionKind.ORDERED_SEQUENCING: "Confirm Order",
        InteractionKind.PATH_EDITOR: "Submit Paths",
        InteractionKind.QUANTITY_SELECTION: "Confirm Quantity",
        InteractionKind.ROSTER_CONSTRUCTION: "Confirm Roster",
        InteractionKind.WEAPON_ALLOCATION_MATRIX: "Submit Allocations",
    }
    return {
        "confirm_label": labels[interaction_kind],
        "decline_label": (
            "No Legal Marker Position"
            if has_alternative
            else ("Decline" if interaction_kind is InteractionKind.OPPORTUNITY_WINDOW else None)
        ),
    }


def _optional_number(
    payload: dict[str, JsonValue],
    *,
    keys: tuple[str, ...],
) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        if type(value) not in {int, float}:
            raise GameLifecycleError(f"Interaction {key} must be numeric.")
        return float(cast(int | float, value))
    return None


def _identifier_list(value: JsonValue | None) -> list[str]:
    if value is None:
        return []
    validated = validate_json_value(value)
    if not isinstance(validated, list) or any(
        type(item) is not str or not item for item in validated
    ):
        raise GameLifecycleError("Interaction placement_kinds must contain identifiers.")
    return cast(list[str], list(validated))
