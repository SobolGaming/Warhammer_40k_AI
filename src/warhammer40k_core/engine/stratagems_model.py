# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.selected_target_context import SELECTED_TARGET_UNIT_CONTEXT_KEY

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_requests import request_stratagem_use, request_stratagem_use_from_index, _request_stratagem_use_with_options, create_stratagem_use_decision_request, stratagem_decline_option, stratagem_decline_payload, is_stratagem_window_decline_result, stratagem_window_decline_allowed, stratagem_window_context_from_request, stratagem_window_decline_event_payload, stratagem_window_declined_for_context, stratagem_use_options, stratagem_use_options_from_index, stratagem_use_options_for_handler_from_index, hit_enemy_unit_effect_selection, engaged_enemy_unit_effect_selection, _stratagem_use_options_for_records, _effect_selections_for_binding, request_stratagem_target_proposal, create_stratagem_target_proposal_decision_request, stratagem_target_proposal_request_payload, stratagem_target_proposal_from_index
    from warhammer40k_core.engine.stratagems_apply import invalid_stratagem_use_status, apply_stratagem_decision, _apply_stratagem_use, invalid_stratagem_target_proposal_status, apply_stratagem_target_proposal, is_stratagem_placement_proposal_request, invalid_stratagem_placement_proposal_status, apply_stratagem_placement_proposal, is_heroic_intervention_charge_move_request, invalid_heroic_intervention_charge_move_status, apply_heroic_intervention_charge_move, _request_heroic_intervention_charge_move_retry
    from warhammer40k_core.engine.stratagems_selection import stratagem_availability_kind_from_token, stratagem_category_from_token, stratagem_target_kind_from_token, _stratagem_decision_option, _effect_selection_token, _stratagem_selection_from_result_payload, _require_stratagem_selection, stratagem_selection_from_decision_result, stratagem_selection_from_target_proposal_result, _record_is_available_for_context, _stratagem_unavailable_reason, _context_state_drift, _detachment_gate_allows, _effect_selection_error, _selected_command_point_cost, _selected_command_point_cost_result, _heroic_intervention_mode_error, _heroic_intervention_mode, _heroic_intervention_mode_additional_cost, _heroic_intervention_mode_costs, _required_effect_selection_fields_error, _effect_selection_string_or_none
    from warhammer40k_core.engine.stratagems_eligibility import _handler_unavailable_reason, _restriction_violation, _same_stratagem_phase, _stratagem_targeted_unit_ids, _stratagem_affected_unit_ids, _canonical_stratagem_affected_unit_id, _attached_unit_id_for_component, _unit_has_runtime_attached_role, _rules_unit_owner, _enumerated_target_bindings
    from warhammer40k_core.engine.stratagems_targeting import _target_binding_error, _target_unit_owner, _target_unit_has_keyword, _target_unit_within_controlled_objective_range, _objective_control_result_has_unit, _target_unit_satisfies_required_keywords, _target_unit_satisfies_required_keywords_any, _target_unit_satisfies_required_faction_keywords, _unit_has_keyword, _canonical_keyword, _active_tactical_secondary_cards, _battle_shock_test_unit_ids, _rapid_ingress_unit_ids, _strategic_reserves_ingress_unit_ids, _command_reroll_context_error, _command_reroll_roll_class, _command_reroll_state, _command_reroll_affected_unit_id, _command_reroll_permission, _selected_target_context_error, _selected_target_unit_ids_or_none, _selected_to_move_target_context_error, _selected_to_move_unit_id_or_none, _just_fell_back_target_context_error, _just_fell_back_unit_id_or_none, _just_shot_target_context_error, _just_shot_unit_id_or_none, _hit_target_unit_ids_or_empty, _engaged_enemy_unit_ids_or_empty, _effect_selection_required_target_keywords, _target_unit_has_all_keywords, destroyed_target_unit_ids_from_context, destroyed_enemy_unit_ids_from_context, _identifier_list_from_trigger_payload, _hit_enemy_unit_id_or_none, _engaged_enemy_unit_id_or_none, _engaged_with_fall_back_unit_target_context_error, _fall_back_unit_id_or_none, _engaged_fall_back_target_unit_ids, _fire_overwatch_target_binding_error
    from warhammer40k_core.engine.stratagems_geometry import _fire_overwatch_triggering_enemy_unit_id, _fire_overwatch_triggering_enemy_unit_id_or_none, _heroic_intervention_target_binding_error, _crushing_impact_context_error, _counteroffensive_target_context_error, _epic_challenge_context_error, _units_are_within_range_inches, _friendly_unit_within_enemy_range, _units_are_engaged, _model_engaged_with_unit, _geometry_model_for_model_id, _model_is_alive_and_placed, _model_toughness, _crushing_impact_enemy_target_id_or_none, _crushing_impact_model_id_or_none, _epic_challenge_character_model_id_or_none, _explosives_context_error, _explosives_target_unit_id, _explosives_target_unit_id_or_none, _explosives_target_is_visible_and_in_range, _unit_is_within_enemy_engagement_range, _enemy_unit_is_within_friendly_engagement_range, _any_models_within_engagement_range, _geometry_models_for_unit, _battlefield_scenario_for_stratagem, _stratagem_terrain_features, _stratagem_ruleset_descriptor, _explosives_visibility_profile, _unit_owner, _unit_by_id, _unit_by_id_or_none, _reserve_state_for_target, _unit_for_reserve_state, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _unit_has_deep_strike_keyword, _battlefield_scenario, _proposal_from_request_payload, _proposal_from_result_payload, _proposal_context_error, _movement_proposal_request_from_payload, _heroic_intervention_charge_move_from_result_payload, _heroic_intervention_charge_move_request_error, _heroic_intervention_maximum_distance, _heroic_intervention_mode_from_request, _heroic_intervention_requested_reachable_distances, _heroic_intervention_request_context, _placement_proposal_from_result_payload, _proposal_request_is_rapid_ingress
    from warhammer40k_core.engine.stratagems_ingress import _apply_rapid_ingress_placement, _strategic_reserve_rule_for_ingress_request, _proposal_request_marks_movement_phase_arrival, _request_rapid_ingress_placement_retry
    from warhammer40k_core.engine.stratagems_core_handlers import _stratagem_use_from_proposal_context, _apply_supported_stratagem_handler, _validate_supported_stratagem_handler_available, _validate_supported_stratagem_handler_preflight, _generic_rule_ir_from_stratagem_payload, _apply_generic_rule_ir_stratagem_handler, _apply_command_reroll_handler, is_command_reroll_decision_request, invalid_command_reroll_decision_status, apply_command_reroll_decision, _command_reroll_request_context, _apply_insane_bravery_handler, _apply_rapid_ingress_handler, _apply_ingress_move_handler, _ingress_move_effect_payload, _apply_force_desperate_escape_handler
    from warhammer40k_core.engine.stratagems_tactical_secondaries import _apply_new_orders_handler
    from warhammer40k_core.engine.stratagems_fire_overwatch import _apply_fire_overwatch_handler
    from warhammer40k_core.engine.stratagems_effect_handlers import _apply_go_to_ground_handler, _apply_smokescreen_handler, _apply_explosives_handler, apply_explosives_mortal_wound_feel_no_pain_decision, _emit_explosives_resolved, _apply_counteroffensive_handler, _apply_crushing_impact_handler, _apply_epic_challenge_handler, _apply_heroic_intervention_handler, _apply_stratagem_mortal_wounds, _heroic_intervention_reachable_target_distances, _enemy_unit_ids_for_player, _closest_unit_distance_inches, _unit_made_charge_move
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY",
    "COMMAND_REROLL_DICE_CONTEXT_KEY",
    "CONTROLLED_OBJECTIVE_UNIT_TARGET_POLICY_ID",
    "CORE_COMMAND_REROLL_HANDLER_ID",
    "CORE_COUNTEROFFENSIVE_HANDLER_ID",
    "CORE_CRUSHING_IMPACT_HANDLER_ID",
    "CORE_EPIC_CHALLENGE_HANDLER_ID",
    "CORE_EXPLOSIVES_HANDLER_ID",
    "CORE_FIRE_OVERWATCH_HANDLER_ID",
    "CORE_GO_TO_GROUND_HANDLER_ID",
    "CORE_HEROIC_INTERVENTION_HANDLER_ID",
    "CORE_INSANE_BRAVERY_HANDLER_ID",
    "CORE_NEW_ORDERS_HANDLER_ID",
    "CORE_RAPID_INGRESS_HANDLER_ID",
    "CORE_SMOKESCREEN_HANDLER_ID",
    "COUNTEROFFENSIVE_TARGET_POLICY_ID",
    "CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY",
    "CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT",
    "CRUSHING_IMPACT_MODEL_CONTEXT_KEY",
    "CRUSHING_IMPACT_TARGET_POLICY_ID",
    "DECLINE_STRATAGEM_WINDOW_OPTION_ID",
    "DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND",
    "DEEP_STRIKE_ARRIVING_TARGET_POLICY_ID",
    "DESTROYED_ENEMY_UNIT_CONTEXT_KEY",
    "DESTROYED_TARGET_BY_JUST_SHOT_UNIT_TARGET_POLICY_ID",
    "DESTROYED_TARGET_UNIT_CONTEXT_KEY",
    "ENEMY_UNIT_TARGET_POLICY_ID",
    "ENGAGED_ENEMY_UNIT_CONTEXT_KEY",
    "ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND",
    "ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY",
    "ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID",
    "EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY",
    "EPIC_CHALLENGE_TARGET_POLICY_ID",
    "EXPLOSIVES_TARGET_CONTEXT_KEY",
    "EXPLOSIVES_TARGET_POLICY_ID",
    "FALL_BACK_MODE_CONTEXT_KEY",
    "FALL_BACK_UNIT_CONTEXT_KEY",
    "FIRE_OVERWATCH_MAX_RANGE_INCHES",
    "FIRE_OVERWATCH_TARGET_POLICY_ID",
    "FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY",
    "FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND",
    "GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID",
    "GENERIC_INGRESS_MOVE_HANDLER_ID",
    "GENERIC_RULE_IR_STRATAGEM_HANDLER_ID",
    "GO_TO_GROUND_TARGET_POLICY_ID",
    "HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES",
    "HEROIC_INTERVENTION_MODE_CONTEXT_KEY",
    "HEROIC_INTERVENTION_MODE_INTO_THE_FRAY",
    "HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND",
    "HEROIC_INTERVENTION_TARGET_POLICY_ID",
    "HEROIC_INTERVENTION_TARGET_RANGE_INCHES",
    "HIT_ENEMY_UNIT_CONTEXT_KEY",
    "HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND",
    "HIT_TARGET_UNIT_CONTEXT_KEY",
    "INSANE_BRAVERY_TARGET_POLICY_ID",
    "JUST_FELL_BACK_UNIT_CONTEXT_KEY",
    "JUST_FELL_BACK_UNIT_TARGET_POLICY_ID",
    "JUST_SHOT_UNIT_CONTEXT_KEY",
    "JUST_SHOT_UNIT_TARGET_POLICY_ID",
    "NEW_ORDERS_TARGET_POLICY_ID",
    "NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID",
    "NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID",
    "RAPID_INGRESS_TARGET_POLICY_ID",
    "SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID",
    "SELECTED_TARGET_UNIT_CONTEXT_KEY",
    "SELECTED_TARGET_UNIT_TARGET_POLICY_ID",
    "SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID",
    "SELECTED_TO_FIGHT_TARGET_POLICY_ID",
    "SELECTED_TO_FIGHT_UNIT_CONTEXT_KEY",
    "SELECTED_TO_MOVE_TARGET_POLICY_ID",
    "SELECTED_TO_MOVE_UNIT_CONTEXT_KEY",
    "SELECTED_TO_SHOOT_TARGET_POLICY_ID",
    "SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY",
    "SMOKESCREEN_TARGET_POLICY_ID",
    "STRATAGEM_DECISION_TYPE",
    "STRATAGEM_PROPOSAL_PAYLOAD_KIND",
    "STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE",
    "STRATAGEM_WINDOW_DECLINED_EVENT_TYPE",
    "STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID",
    "TARGET_BINDING_UNIT_CONTEXT_KEY",
    "UNSUPPORTED_STRATAGEM_HANDLER_PREFIX",
    "VISIBLE_ENEMY_RANGE_INCHES_KEY",
    "VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY",
    "VISIBLE_ENEMY_UNIT_CONTEXT_KEY",
    "VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND",
    "StratagemAvailabilityKind",
    "StratagemCatalogIndex",
    "StratagemCatalogRecord",
    "StratagemCatalogRecordPayload",
    "StratagemCategory",
    "StratagemDefinition",
    "StratagemDefinitionPayload",
    "StratagemEligibilityContext",
    "StratagemEligibilityContextPayload",
    "StratagemRestrictionPolicy",
    "StratagemRestrictionPolicyPayload",
    "StratagemTargetBinding",
    "StratagemTargetBindingPayload",
    "StratagemTargetKind",
    "StratagemTargetProposal",
    "StratagemTargetProposalPayload",
    "StratagemTargetSpec",
    "StratagemTargetSpecPayload",
    "StratagemTimingDescriptor",
    "StratagemTimingDescriptorPayload",
    "StratagemUseRecord",
    "StratagemUseRecordPayload",
    "StratagemUseRequest",
)

STRATAGEM_DECISION_TYPE = "use_stratagem"
STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE = "submit_stratagem_target_proposal"
STRATAGEM_PROPOSAL_PAYLOAD_KIND = "stratagem_target_binding"
DECLINE_STRATAGEM_WINDOW_OPTION_ID = "decline_stratagem_window"
DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND = "decline_stratagem_window"
STRATAGEM_WINDOW_DECLINED_EVENT_TYPE = "stratagem_window_declined"
UNSUPPORTED_STRATAGEM_HANDLER_PREFIX = "unsupported:"
CORE_COMMAND_REROLL_HANDLER_ID = "core:command-reroll"
CORE_INSANE_BRAVERY_HANDLER_ID = "core:insane-bravery"
CORE_RAPID_INGRESS_HANDLER_ID = "core:rapid-ingress"
CORE_NEW_ORDERS_HANDLER_ID = "core:new-orders"
CORE_FIRE_OVERWATCH_HANDLER_ID = FIRE_OVERWATCH_RULE_ID
CORE_GO_TO_GROUND_HANDLER_ID = "core:go-to-ground"
CORE_EXPLOSIVES_HANDLER_ID = "core:explosives"
CORE_SMOKESCREEN_HANDLER_ID = "core:smokescreen"
CORE_HEROIC_INTERVENTION_HANDLER_ID = "core:heroic-intervention"
CORE_COUNTEROFFENSIVE_HANDLER_ID = "core:counteroffensive"
CORE_CRUSHING_IMPACT_HANDLER_ID = "core:crushing-impact"
CORE_EPIC_CHALLENGE_HANDLER_ID = "core:epic-challenge"
GENERIC_INGRESS_MOVE_HANDLER_ID = "generic:ingress-move"
GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID = "generic:force-desperate-escape"
GENERIC_RULE_IR_STRATAGEM_HANDLER_ID = "generic:rule-ir"
COMMAND_REROLL_DICE_CONTEXT_KEY = "dice_roll_state"
COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY = "affected_unit_instance_id"
INSANE_BRAVERY_TARGET_POLICY_ID = "battle_shock_test_unit"
RAPID_INGRESS_TARGET_POLICY_ID = "reserves_unit"
STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID = "strategic_reserves_ingress_unit"
NEW_ORDERS_TARGET_POLICY_ID = "active_tactical_secondary_card"
FIRE_OVERWATCH_TARGET_POLICY_ID = "out_of_phase_shooting_unit"
GO_TO_GROUND_TARGET_POLICY_ID = "selected_target_infantry_unit"
CONTROLLED_OBJECTIVE_UNIT_TARGET_POLICY_ID = "controlled_objective_unit"
DEEP_STRIKE_ARRIVING_TARGET_POLICY_ID = "deep_strike_arriving_unit"
SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID = (
    "selected_target_controlled_objective_infantry_unit"
)
EXPLOSIVES_TARGET_POLICY_ID = "explosives_unit_and_enemy_target"
SMOKESCREEN_TARGET_POLICY_ID = "selected_target_smoke_unit"
HEROIC_INTERVENTION_TARGET_POLICY_ID = "heroic_intervention_unit"
COUNTEROFFENSIVE_TARGET_POLICY_ID = "counteroffensive_unit"
CRUSHING_IMPACT_TARGET_POLICY_ID = "crushing_impact_unit"
EPIC_CHALLENGE_TARGET_POLICY_ID = "epic_challenge_unit"
SELECTED_TO_MOVE_TARGET_POLICY_ID = "selected_to_move_unit"
SELECTED_TO_SHOOT_TARGET_POLICY_ID = "selected_to_shoot_unit"
SELECTED_TO_FIGHT_TARGET_POLICY_ID = "selected_to_fight_unit"
SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID = "selected_to_fight_charged_unit"
JUST_FELL_BACK_UNIT_TARGET_POLICY_ID = "just_fell_back_unit"
JUST_SHOT_UNIT_TARGET_POLICY_ID = "just_shot_unit"
DESTROYED_TARGET_BY_JUST_SHOT_UNIT_TARGET_POLICY_ID = "destroyed_target_by_just_shot_unit"
ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID = "engaged_with_fall_back_unit"
ENEMY_UNIT_TARGET_POLICY_ID = "enemy_unit"
SELECTED_TARGET_UNIT_TARGET_POLICY_ID = "selected_target_unit"
NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID = "not_selected_to_shoot_unit"
NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID = "not_selected_to_fight_unit"
EXPLOSIVES_TARGET_CONTEXT_KEY = "enemy_target_unit_instance_id"
CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY = "enemy_target_unit_instance_id"
CRUSHING_IMPACT_MODEL_CONTEXT_KEY = "model_instance_id"
EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY = "character_model_instance_id"
HEROIC_INTERVENTION_MODE_CONTEXT_KEY = "mode"
HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND = "leap_to_defend"
HEROIC_INTERVENTION_MODE_INTO_THE_FRAY = "into_the_fray"
SELECTED_TO_MOVE_UNIT_CONTEXT_KEY = "selected_to_move_unit_instance_id"
SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY = "selected_to_shoot_unit_instance_id"
SELECTED_TO_FIGHT_UNIT_CONTEXT_KEY = "selected_to_fight_unit_instance_id"
JUST_FELL_BACK_UNIT_CONTEXT_KEY = "fell_back_unit_instance_id"
JUST_SHOT_UNIT_CONTEXT_KEY = "shot_unit_instance_id"
HIT_TARGET_UNIT_CONTEXT_KEY = "hit_target_unit_instance_ids"
DESTROYED_TARGET_UNIT_CONTEXT_KEY = "destroyed_target_unit_instance_ids"
DESTROYED_ENEMY_UNIT_CONTEXT_KEY = "destroyed_enemy_unit_instance_ids"
HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND = "hit_enemy_unit"
HIT_ENEMY_UNIT_CONTEXT_KEY = "hit_enemy_unit_instance_id"
ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND = "engaged_enemy_unit"
ENGAGED_ENEMY_UNIT_CONTEXT_KEY = "engaged_enemy_unit_instance_id"
ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY = "engaged_enemy_unit_instance_ids"
VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND = "visible_enemy_unit"
VISIBLE_ENEMY_UNIT_CONTEXT_KEY = "visible_enemy_unit_instance_id"
VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY = "visible_enemy_source_unit_context_key"
VISIBLE_ENEMY_RANGE_INCHES_KEY = "visible_enemy_range_inches"
TARGET_BINDING_UNIT_CONTEXT_KEY = "target_binding_unit"
FALL_BACK_UNIT_CONTEXT_KEY = "fall_back_unit_instance_id"
FALL_BACK_MODE_CONTEXT_KEY = "fall_back_mode"
FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND = "forced_fall_back_desperate_escape"
FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY = "moved_unit_instance_id"
FIRE_OVERWATCH_MAX_RANGE_INCHES = 24.0
HEROIC_INTERVENTION_TARGET_RANGE_INCHES = 12.0
HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES = 6.0
CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT = 6


class StratagemAvailabilityKind(StrEnum):
    CORE = "core"
    DETACHMENT = "detachment"


class StratagemCategory(StrEnum):
    BATTLE_TACTIC = "battle_tactic"
    EPIC_DEED = "epic_deed"
    STRATEGIC_PLOY = "strategic_ploy"
    WARGEAR = "wargear"


class StratagemTargetKind(StrEnum):
    NONE = "none"
    FRIENDLY_UNIT = "friendly_unit"
    ANY_UNIT = "any_unit"
    TACTICAL_SECONDARY_CARD = "tactical_secondary_card"


class StratagemUseRecordPayload(TypedDict):
    use_id: str
    player_id: str
    stratagem_id: str
    source_id: str
    battle_round: int
    phase: str
    active_player_id: str | None
    timing_window_id: str | None
    request_id: str
    result_id: str
    selected_option_id: str
    target_binding: StratagemTargetBindingPayload
    targeted_unit_instance_ids: list[str]
    affected_unit_instance_ids: list[str]
    command_point_cost: int
    command_point_modifier_ids: NotRequired[list[str]]
    command_point_modifier_source_ids: NotRequired[list[str]]
    command_point_transaction_id: str | None
    handler_id: str
    effects_resolved: bool
    unresolved_reason: str | None
    effect_selection: JsonValue
    effect_payload: JsonValue


class StratagemTimingDescriptorPayload(TypedDict):
    trigger_kind: str
    phase: str | None
    timing_window_id: str | None


class StratagemRestrictionPolicyPayload(TypedDict):
    same_stratagem_per_phase: bool
    same_unit_target_per_phase: bool
    once_per_turn: bool
    once_per_battle: bool
    once_per_target_per_phase: bool
    allow_battle_shocked_targets: bool


class StratagemTargetSpecPayload(TypedDict):
    target_kind: str
    enumerable: bool
    target_policy_id: str
    required_keywords: list[str]
    required_keywords_any: list[str]
    required_faction_keywords: list[str]
    excluded_keywords: NotRequired[list[str]]
    excluded_faction_keywords: NotRequired[list[str]]


class StratagemDefinitionPayload(TypedDict):
    stratagem_id: str
    name: str
    source_id: str
    command_point_cost: int
    category: str
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    timing: StratagemTimingDescriptorPayload
    restriction_policy: StratagemRestrictionPolicyPayload
    target_spec: StratagemTargetSpecPayload
    handler_id: str
    eligible_roll_types: list[str]
    effect_payload: JsonValue


class StratagemCatalogRecordPayload(TypedDict):
    record_id: str
    definition: StratagemDefinitionPayload
    availability_kind: str
    detachment_id: str | None
    disabled: bool


class StratagemEligibilityContextPayload(TypedDict):
    game_id: str
    player_id: str
    battle_round: int
    phase: str
    active_player_id: str | None
    trigger_kind: str
    timing_window_id: str | None
    trigger_payload: NotRequired[JsonValue]


class StratagemTargetBindingPayload(TypedDict):
    target_kind: str
    target_player_id: str | None
    target_unit_instance_id: str | None
    target_secondary_mission_id: NotRequired[str | None]


class StratagemTargetProposalPayload(TypedDict):
    request_id: NotRequired[str]
    decision_type: NotRequired[str]
    actor_id: NotRequired[str]
    proposal_kind: str
    context: StratagemEligibilityContextPayload
    catalog_record: StratagemCatalogRecordPayload
    target_binding: StratagemTargetBindingPayload | None
    effect_selection: JsonValue


@dataclass(frozen=True, slots=True)
class StratagemTimingDescriptor:
    trigger_kind: TimingTriggerKind
    phase: BattlePhaseKind | None = None
    timing_window_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "phase",
            _validate_optional_phase("StratagemTimingDescriptor phase", self.phase),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "StratagemTimingDescriptor timing_window_id",
                self.timing_window_id,
            ),
        )

    def matches(self, context: StratagemEligibilityContext) -> bool:
        if type(context) is not StratagemEligibilityContext:
            raise GameLifecycleError("Stratagem timing requires a StratagemEligibilityContext.")
        if self.trigger_kind is not context.trigger_kind:
            return False
        if self.phase is not None and self.phase is not context.phase:
            return False
        return not (
            self.timing_window_id is not None and self.timing_window_id != context.timing_window_id
        )

    def to_payload(self) -> StratagemTimingDescriptorPayload:
        return {
            "trigger_kind": self.trigger_kind.value,
            "phase": None if self.phase is None else self.phase.value,
            "timing_window_id": self.timing_window_id,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTimingDescriptorPayload) -> Self:
        phase_token = payload["phase"]
        return cls(
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            phase=None if phase_token is None else battle_phase_kind_from_token(phase_token),
            timing_window_id=payload["timing_window_id"],
        )


@dataclass(frozen=True, slots=True)
class StratagemRestrictionPolicy:
    same_stratagem_per_phase: bool = True
    same_unit_target_per_phase: bool = True
    once_per_turn: bool = False
    once_per_battle: bool = False
    once_per_target_per_phase: bool = False
    allow_battle_shocked_targets: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "same_stratagem_per_phase",
            _validate_bool(
                "StratagemRestrictionPolicy same_stratagem_per_phase",
                self.same_stratagem_per_phase,
            ),
        )
        object.__setattr__(
            self,
            "same_unit_target_per_phase",
            _validate_bool(
                "StratagemRestrictionPolicy same_unit_target_per_phase",
                self.same_unit_target_per_phase,
            ),
        )
        object.__setattr__(
            self,
            "once_per_turn",
            _validate_bool("StratagemRestrictionPolicy once_per_turn", self.once_per_turn),
        )
        object.__setattr__(
            self,
            "once_per_battle",
            _validate_bool("StratagemRestrictionPolicy once_per_battle", self.once_per_battle),
        )
        object.__setattr__(
            self,
            "once_per_target_per_phase",
            _validate_bool(
                "StratagemRestrictionPolicy once_per_target_per_phase",
                self.once_per_target_per_phase,
            ),
        )
        object.__setattr__(
            self,
            "allow_battle_shocked_targets",
            _validate_bool(
                "StratagemRestrictionPolicy allow_battle_shocked_targets",
                self.allow_battle_shocked_targets,
            ),
        )

    def to_payload(self) -> StratagemRestrictionPolicyPayload:
        return {
            "same_stratagem_per_phase": self.same_stratagem_per_phase,
            "same_unit_target_per_phase": self.same_unit_target_per_phase,
            "once_per_turn": self.once_per_turn,
            "once_per_battle": self.once_per_battle,
            "once_per_target_per_phase": self.once_per_target_per_phase,
            "allow_battle_shocked_targets": self.allow_battle_shocked_targets,
        }

    @classmethod
    def from_payload(cls, payload: StratagemRestrictionPolicyPayload) -> Self:
        return cls(
            same_stratagem_per_phase=payload["same_stratagem_per_phase"],
            same_unit_target_per_phase=payload["same_unit_target_per_phase"],
            once_per_turn=payload["once_per_turn"],
            once_per_battle=payload["once_per_battle"],
            once_per_target_per_phase=payload["once_per_target_per_phase"],
            allow_battle_shocked_targets=payload["allow_battle_shocked_targets"],
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetSpec:
    target_kind: StratagemTargetKind = StratagemTargetKind.NONE
    enumerable: bool = True
    target_policy_id: str = ""
    required_keywords: tuple[str, ...] = ()
    required_keywords_any: tuple[str, ...] = ()
    required_faction_keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    excluded_faction_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_kind",
            stratagem_target_kind_from_token(self.target_kind),
        )
        object.__setattr__(
            self,
            "enumerable",
            _validate_bool("StratagemTargetSpec enumerable", self.enumerable),
        )
        object.__setattr__(
            self,
            "target_policy_id",
            _validate_target_policy_id(
                target_kind=self.target_kind,
                target_policy_id=self.target_policy_id,
            ),
        )
        object.__setattr__(
            self,
            "required_keywords",
            _validate_identifier_tuple(
                "StratagemTargetSpec required_keywords",
                self.required_keywords,
            ),
        )
        object.__setattr__(
            self,
            "required_faction_keywords",
            _validate_identifier_tuple(
                "StratagemTargetSpec required_faction_keywords",
                self.required_faction_keywords,
            ),
        )
        object.__setattr__(
            self,
            "required_keywords_any",
            _validate_identifier_tuple(
                "StratagemTargetSpec required_keywords_any",
                self.required_keywords_any,
            ),
        )
        object.__setattr__(
            self,
            "excluded_keywords",
            _validate_identifier_tuple(
                "StratagemTargetSpec excluded_keywords",
                self.excluded_keywords,
            ),
        )
        object.__setattr__(
            self,
            "excluded_faction_keywords",
            _validate_identifier_tuple(
                "StratagemTargetSpec excluded_faction_keywords",
                self.excluded_faction_keywords,
            ),
        )
        if self.target_kind is StratagemTargetKind.NONE and not self.enumerable:
            raise GameLifecycleError("Targetless StratagemTargetSpec must be enumerable.")
        if self.target_kind is StratagemTargetKind.NONE and (
            self.required_keywords
            or self.required_keywords_any
            or self.required_faction_keywords
            or self.excluded_keywords
            or self.excluded_faction_keywords
        ):
            raise GameLifecycleError("Targetless StratagemTargetSpec cannot require keywords.")

    @property
    def requires_target(self) -> bool:
        return self.target_kind is not StratagemTargetKind.NONE

    def to_payload(self) -> StratagemTargetSpecPayload:
        return {
            "target_kind": self.target_kind.value,
            "enumerable": self.enumerable,
            "target_policy_id": self.target_policy_id,
            "required_keywords": list(self.required_keywords),
            "required_keywords_any": list(self.required_keywords_any),
            "required_faction_keywords": list(self.required_faction_keywords),
            "excluded_keywords": list(self.excluded_keywords),
            "excluded_faction_keywords": list(self.excluded_faction_keywords),
        }

    @classmethod
    def from_payload(cls, payload: StratagemTargetSpecPayload) -> Self:
        return cls(
            target_kind=stratagem_target_kind_from_token(payload["target_kind"]),
            enumerable=payload["enumerable"],
            target_policy_id=payload["target_policy_id"],
            required_keywords=tuple(payload["required_keywords"]),
            required_keywords_any=tuple(payload["required_keywords_any"]),
            required_faction_keywords=tuple(payload["required_faction_keywords"]),
            excluded_keywords=tuple(payload.get("excluded_keywords", ())),
            excluded_faction_keywords=tuple(payload.get("excluded_faction_keywords", ())),
        )


@dataclass(frozen=True, slots=True)
class StratagemDefinition:
    stratagem_id: str
    name: str
    source_id: str
    command_point_cost: int
    category: StratagemCategory
    when_descriptor: str
    target_descriptor: str
    effect_descriptor: str
    restrictions_descriptor: str
    timing: StratagemTimingDescriptor
    restriction_policy: StratagemRestrictionPolicy = field(
        default_factory=StratagemRestrictionPolicy
    )
    target_spec: StratagemTargetSpec = field(default_factory=StratagemTargetSpec)
    handler_id: str = "record_only"
    eligible_roll_types: tuple[str, ...] = ()
    effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stratagem_id",
            _validate_identifier("StratagemDefinition stratagem_id", self.stratagem_id),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("StratagemDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StratagemDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "command_point_cost",
            _validate_non_negative_int(
                "StratagemDefinition command_point_cost",
                self.command_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "category",
            stratagem_category_from_token(self.category),
        )
        object.__setattr__(
            self,
            "when_descriptor",
            _validate_identifier("StratagemDefinition when_descriptor", self.when_descriptor),
        )
        object.__setattr__(
            self,
            "target_descriptor",
            _validate_identifier("StratagemDefinition target_descriptor", self.target_descriptor),
        )
        object.__setattr__(
            self,
            "effect_descriptor",
            _validate_identifier("StratagemDefinition effect_descriptor", self.effect_descriptor),
        )
        object.__setattr__(
            self,
            "restrictions_descriptor",
            _validate_identifier(
                "StratagemDefinition restrictions_descriptor",
                self.restrictions_descriptor,
            ),
        )
        if type(self.timing) is not StratagemTimingDescriptor:
            raise GameLifecycleError("StratagemDefinition timing must be a descriptor.")
        if type(self.restriction_policy) is not StratagemRestrictionPolicy:
            raise GameLifecycleError("StratagemDefinition restriction_policy must be a policy.")
        if type(self.target_spec) is not StratagemTargetSpec:
            raise GameLifecycleError("StratagemDefinition target_spec must be a target spec.")
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("StratagemDefinition handler_id", self.handler_id),
        )
        object.__setattr__(
            self,
            "eligible_roll_types",
            _validate_identifier_tuple(
                "StratagemDefinition eligible_roll_types",
                self.eligible_roll_types,
            ),
        )
        object.__setattr__(self, "effect_payload", validate_json_value(self.effect_payload))

    def to_payload(self) -> StratagemDefinitionPayload:
        return {
            "stratagem_id": self.stratagem_id,
            "name": self.name,
            "source_id": self.source_id,
            "command_point_cost": self.command_point_cost,
            "category": self.category.value,
            "when_descriptor": self.when_descriptor,
            "target_descriptor": self.target_descriptor,
            "effect_descriptor": self.effect_descriptor,
            "restrictions_descriptor": self.restrictions_descriptor,
            "timing": self.timing.to_payload(),
            "restriction_policy": self.restriction_policy.to_payload(),
            "target_spec": self.target_spec.to_payload(),
            "handler_id": self.handler_id,
            "eligible_roll_types": list(self.eligible_roll_types),
            "effect_payload": self.effect_payload,
        }

    @classmethod
    def from_payload(cls, payload: StratagemDefinitionPayload) -> Self:
        return cls(
            stratagem_id=payload["stratagem_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            command_point_cost=payload["command_point_cost"],
            category=stratagem_category_from_token(payload["category"]),
            when_descriptor=payload["when_descriptor"],
            target_descriptor=payload["target_descriptor"],
            effect_descriptor=payload["effect_descriptor"],
            restrictions_descriptor=payload["restrictions_descriptor"],
            timing=StratagemTimingDescriptor.from_payload(payload["timing"]),
            restriction_policy=StratagemRestrictionPolicy.from_payload(
                payload["restriction_policy"]
            ),
            target_spec=StratagemTargetSpec.from_payload(payload["target_spec"]),
            handler_id=payload["handler_id"],
            eligible_roll_types=tuple(payload["eligible_roll_types"]),
            effect_payload=payload["effect_payload"],
        )


@dataclass(frozen=True, slots=True)
class StratagemCatalogRecord:
    record_id: str
    definition: StratagemDefinition
    availability_kind: StratagemAvailabilityKind = StratagemAvailabilityKind.CORE
    detachment_id: str | None = None
    disabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "record_id",
            _validate_identifier("StratagemCatalogRecord record_id", self.record_id),
        )
        if type(self.definition) is not StratagemDefinition:
            raise GameLifecycleError("StratagemCatalogRecord definition must be a definition.")
        object.__setattr__(
            self,
            "availability_kind",
            stratagem_availability_kind_from_token(self.availability_kind),
        )
        object.__setattr__(
            self,
            "detachment_id",
            _validate_optional_identifier(
                "StratagemCatalogRecord detachment_id",
                self.detachment_id,
            ),
        )
        object.__setattr__(
            self,
            "disabled",
            _validate_bool("StratagemCatalogRecord disabled", self.disabled),
        )
        if self.availability_kind is StratagemAvailabilityKind.CORE and self.detachment_id:
            raise GameLifecycleError("Core StratagemCatalogRecord cannot require detachment_id.")
        if (
            self.availability_kind is StratagemAvailabilityKind.DETACHMENT
            and not self.detachment_id
        ):
            raise GameLifecycleError("Detachment StratagemCatalogRecord requires detachment_id.")

    def to_payload(self) -> StratagemCatalogRecordPayload:
        return {
            "record_id": self.record_id,
            "definition": self.definition.to_payload(),
            "availability_kind": self.availability_kind.value,
            "detachment_id": self.detachment_id,
            "disabled": self.disabled,
        }

    @classmethod
    def from_payload(cls, payload: StratagemCatalogRecordPayload) -> Self:
        return cls(
            record_id=payload["record_id"],
            definition=StratagemDefinition.from_payload(payload["definition"]),
            availability_kind=stratagem_availability_kind_from_token(payload["availability_kind"]),
            detachment_id=payload["detachment_id"],
            disabled=payload["disabled"],
        )


@dataclass(frozen=True, slots=True)
class StratagemCatalogIndex:
    _records_by_trigger: Mapping[TimingTriggerKind, tuple[StratagemCatalogRecord, ...]]
    _records: tuple[StratagemCatalogRecord, ...]

    @classmethod
    def from_records(cls, records: tuple[StratagemCatalogRecord, ...]) -> Self:
        validated = _validate_catalog_records(records)
        grouped: dict[TimingTriggerKind, list[StratagemCatalogRecord]] = {}
        for record in validated:
            grouped.setdefault(record.definition.timing.trigger_kind, []).append(record)
        records_by_trigger = {
            trigger_kind: tuple(records_for_trigger)
            for trigger_kind, records_for_trigger in grouped.items()
        }
        return cls(
            _records_by_trigger=MappingProxyType(records_by_trigger),
            _records=validated,
        )

    def records_for(
        self,
        trigger_kind: TimingTriggerKind,
    ) -> tuple[StratagemCatalogRecord, ...]:
        if type(trigger_kind) is not TimingTriggerKind:
            raise GameLifecycleError("StratagemCatalogIndex lookup requires a TimingTriggerKind.")
        return self._records_by_trigger.get(trigger_kind, ())

    def all_records(self) -> tuple[StratagemCatalogRecord, ...]:
        return self._records


@dataclass(frozen=True, slots=True)
class StratagemEligibilityContext:
    game_id: str
    player_id: str
    battle_round: int
    phase: BattlePhaseKind
    active_player_id: str | None
    trigger_kind: TimingTriggerKind
    timing_window_id: str | None = None
    trigger_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("StratagemEligibilityContext game_id", self.game_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StratagemEligibilityContext player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int(
                "StratagemEligibilityContext battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "phase",
            battle_phase_kind_from_token(self.phase),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "StratagemEligibilityContext active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "trigger_kind",
            timing_trigger_kind_from_token(self.trigger_kind),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "StratagemEligibilityContext timing_window_id",
                self.timing_window_id,
            ),
        )
        object.__setattr__(self, "trigger_payload", validate_json_value(self.trigger_payload))

    @classmethod
    def from_state(
        cls,
        *,
        state: GameState,
        player_id: str,
        trigger_kind: TimingTriggerKind,
        timing_window_id: str | None = None,
        trigger_payload: JsonValue = None,
    ) -> Self:
        if state.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("StratagemEligibilityContext requires battle stage.")
        current_phase = state.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("StratagemEligibilityContext requires a battle phase.")
        return cls(
            game_id=state.game_id,
            player_id=player_id,
            battle_round=state.battle_round,
            phase=current_phase,
            active_player_id=state.active_player_id,
            trigger_kind=trigger_kind,
            timing_window_id=timing_window_id,
            trigger_payload=trigger_payload,
        )

    def to_payload(self) -> StratagemEligibilityContextPayload:
        payload: StratagemEligibilityContextPayload = {
            "game_id": self.game_id,
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "active_player_id": self.active_player_id,
            "trigger_kind": self.trigger_kind.value,
            "timing_window_id": self.timing_window_id,
        }
        if self.trigger_payload is not None:
            payload["trigger_payload"] = self.trigger_payload
        return payload

    @classmethod
    def from_payload(cls, payload: StratagemEligibilityContextPayload) -> Self:
        trigger_payload: JsonValue = None
        if "trigger_payload" in payload:
            trigger_payload = payload["trigger_payload"]
        return cls(
            game_id=payload["game_id"],
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            phase=battle_phase_kind_from_token(payload["phase"]),
            active_player_id=payload["active_player_id"],
            trigger_kind=timing_trigger_kind_from_token(payload["trigger_kind"]),
            timing_window_id=payload["timing_window_id"],
            trigger_payload=trigger_payload,
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetBinding:
    target_kind: StratagemTargetKind
    target_player_id: str | None = None
    target_unit_instance_id: str | None = None
    target_secondary_mission_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_kind",
            stratagem_target_kind_from_token(self.target_kind),
        )
        object.__setattr__(
            self,
            "target_player_id",
            _validate_optional_identifier(
                "StratagemTargetBinding target_player_id",
                self.target_player_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_optional_identifier(
                "StratagemTargetBinding target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_secondary_mission_id",
            _validate_optional_identifier(
                "StratagemTargetBinding target_secondary_mission_id",
                self.target_secondary_mission_id,
            ),
        )
        if self.target_kind is StratagemTargetKind.NONE:
            if (
                self.target_player_id is not None
                or self.target_unit_instance_id is not None
                or self.target_secondary_mission_id is not None
            ):
                raise GameLifecycleError("Targetless StratagemTargetBinding cannot name a target.")
            return
        if self.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
            if self.target_player_id is None or self.target_secondary_mission_id is None:
                raise GameLifecycleError(
                    "Tactical secondary StratagemTargetBinding requires target card fields."
                )
            if self.target_unit_instance_id is not None:
                raise GameLifecycleError(
                    "Tactical secondary StratagemTargetBinding cannot name a unit."
                )
            return
        if self.target_player_id is None or self.target_unit_instance_id is None:
            raise GameLifecycleError("Unit StratagemTargetBinding requires target unit fields.")
        if self.target_secondary_mission_id is not None:
            raise GameLifecycleError("Unit StratagemTargetBinding cannot name a secondary card.")

    @classmethod
    def none(cls) -> Self:
        return cls(target_kind=StratagemTargetKind.NONE)

    def to_payload(self) -> StratagemTargetBindingPayload:
        payload: StratagemTargetBindingPayload = {
            "target_kind": self.target_kind.value,
            "target_player_id": self.target_player_id,
            "target_unit_instance_id": self.target_unit_instance_id,
        }
        if self.target_secondary_mission_id is not None:
            payload["target_secondary_mission_id"] = self.target_secondary_mission_id
        return payload

    @classmethod
    def from_payload(cls, payload: StratagemTargetBindingPayload) -> Self:
        target_secondary_mission_id = None
        if "target_secondary_mission_id" in payload:
            target_secondary_mission_id = payload["target_secondary_mission_id"]
        return cls(
            target_kind=stratagem_target_kind_from_token(payload["target_kind"]),
            target_player_id=payload["target_player_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            target_secondary_mission_id=target_secondary_mission_id,
        )


@dataclass(frozen=True, slots=True)
class StratagemTargetProposal:
    proposal_kind: str
    context: StratagemEligibilityContext
    catalog_record: StratagemCatalogRecord
    target_binding: StratagemTargetBinding | None = None
    effect_selection: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "proposal_kind",
            _validate_identifier("StratagemTargetProposal proposal_kind", self.proposal_kind),
        )
        if self.proposal_kind != STRATAGEM_PROPOSAL_PAYLOAD_KIND:
            raise GameLifecycleError("StratagemTargetProposal proposal_kind is unsupported.")
        if type(self.context) is not StratagemEligibilityContext:
            raise GameLifecycleError(
                "StratagemTargetProposal context must be an eligibility context."
            )
        if type(self.catalog_record) is not StratagemCatalogRecord:
            raise GameLifecycleError(
                "StratagemTargetProposal catalog_record must be a catalog record."
            )
        if self.catalog_record.definition.target_spec.enumerable:
            raise GameLifecycleError(
                "StratagemTargetProposal catalog_record must require parameterized targets."
            )
        if (
            self.target_binding is not None
            and type(self.target_binding) is not StratagemTargetBinding
        ):
            raise GameLifecycleError(
                "StratagemTargetProposal target_binding must be a target binding."
            )
        object.__setattr__(self, "effect_selection", validate_json_value(self.effect_selection))

    @property
    def game_id(self) -> str:
        return self.context.game_id

    @property
    def player_id(self) -> str:
        return self.context.player_id

    @property
    def battle_round(self) -> int:
        return self.context.battle_round

    @property
    def phase(self) -> BattlePhaseKind:
        return self.context.phase

    @property
    def stratagem_id(self) -> str:
        return self.catalog_record.definition.stratagem_id

    @property
    def target_spec(self) -> StratagemTargetSpec:
        return self.catalog_record.definition.target_spec

    @classmethod
    def for_request(
        cls,
        *,
        context: StratagemEligibilityContext,
        catalog_record: StratagemCatalogRecord,
    ) -> Self:
        return cls(
            proposal_kind=STRATAGEM_PROPOSAL_PAYLOAD_KIND,
            context=context,
            catalog_record=catalog_record,
        )

    def with_binding(
        self,
        binding: StratagemTargetBinding,
        *,
        effect_selection: JsonValue = None,
    ) -> Self:
        return type(self)(
            proposal_kind=self.proposal_kind,
            context=self.context,
            catalog_record=self.catalog_record,
            target_binding=binding,
            effect_selection=effect_selection,
        )

    def with_effect_selection(self, effect_selection: JsonValue) -> Self:
        return type(self)(
            proposal_kind=self.proposal_kind,
            context=self.context,
            catalog_record=self.catalog_record,
            target_binding=self.target_binding,
            effect_selection=effect_selection,
        )

    def to_payload(self) -> StratagemTargetProposalPayload:
        return {
            "proposal_kind": self.proposal_kind,
            "context": self.context.to_payload(),
            "catalog_record": self.catalog_record.to_payload(),
            "target_binding": (
                None if self.target_binding is None else self.target_binding.to_payload()
            ),
            "effect_selection": self.effect_selection,
        }

    @classmethod
    def from_payload(cls, payload: StratagemTargetProposalPayload) -> Self:
        binding_payload = payload["target_binding"]
        return cls(
            proposal_kind=payload["proposal_kind"],
            context=StratagemEligibilityContext.from_payload(payload["context"]),
            catalog_record=StratagemCatalogRecord.from_payload(payload["catalog_record"]),
            target_binding=(
                None
                if binding_payload is None
                else StratagemTargetBinding.from_payload(binding_payload)
            ),
            effect_selection=payload["effect_selection"],
        )


@dataclass(frozen=True, slots=True)
class StratagemUseRequest:
    context: StratagemEligibilityContext
    request: DecisionRequest

    def __post_init__(self) -> None:
        if type(self.context) is not StratagemEligibilityContext:
            raise GameLifecycleError("StratagemUseRequest context must be an eligibility context.")
        if type(self.request) is not DecisionRequest:
            raise GameLifecycleError("StratagemUseRequest request must be a DecisionRequest.")
        if self.request.decision_type != STRATAGEM_DECISION_TYPE:
            raise GameLifecycleError("StratagemUseRequest request decision_type drift.")


@dataclass(frozen=True, slots=True)
class StratagemUseRecord:
    use_id: str
    player_id: str
    stratagem_id: str
    source_id: str
    battle_round: int
    phase: BattlePhaseKind
    active_player_id: str | None
    timing_window_id: str | None
    request_id: str
    result_id: str
    selected_option_id: str
    target_binding: StratagemTargetBinding
    targeted_unit_instance_ids: tuple[str, ...]
    affected_unit_instance_ids: tuple[str, ...]
    command_point_cost: int
    command_point_transaction_id: str | None
    handler_id: str
    command_point_modifier_ids: tuple[str, ...] = ()
    command_point_modifier_source_ids: tuple[str, ...] = ()
    effects_resolved: bool = True
    unresolved_reason: str | None = None
    effect_selection: JsonValue = None
    effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "use_id",
            _validate_identifier("StratagemUseRecord use_id", self.use_id),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StratagemUseRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "stratagem_id",
            _validate_identifier("StratagemUseRecord stratagem_id", self.stratagem_id),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("StratagemUseRecord source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("StratagemUseRecord battle_round", self.battle_round),
        )
        object.__setattr__(self, "phase", battle_phase_kind_from_token(self.phase))
        object.__setattr__(
            self,
            "active_player_id",
            _validate_optional_identifier(
                "StratagemUseRecord active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(
            self,
            "timing_window_id",
            _validate_optional_identifier(
                "StratagemUseRecord timing_window_id",
                self.timing_window_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("StratagemUseRecord request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("StratagemUseRecord result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "selected_option_id",
            _validate_identifier(
                "StratagemUseRecord selected_option_id",
                self.selected_option_id,
            ),
        )
        if type(self.target_binding) is not StratagemTargetBinding:
            raise GameLifecycleError("StratagemUseRecord target_binding must be a binding.")
        targeted_unit_ids = _validate_stratagem_affected_unit_ids(self.targeted_unit_instance_ids)
        object.__setattr__(self, "targeted_unit_instance_ids", targeted_unit_ids)
        affected_unit_ids = _validate_stratagem_affected_unit_ids(self.affected_unit_instance_ids)
        object.__setattr__(self, "affected_unit_instance_ids", affected_unit_ids)
        object.__setattr__(
            self,
            "command_point_cost",
            _validate_non_negative_int(
                "StratagemUseRecord command_point_cost",
                self.command_point_cost,
            ),
        )
        object.__setattr__(
            self,
            "command_point_modifier_ids",
            _validate_identifier_tuple(
                "StratagemUseRecord command_point_modifier_ids",
                self.command_point_modifier_ids,
            ),
        )
        object.__setattr__(
            self,
            "command_point_modifier_source_ids",
            _validate_identifier_tuple(
                "StratagemUseRecord command_point_modifier_source_ids",
                self.command_point_modifier_source_ids,
            ),
        )
        object.__setattr__(
            self,
            "command_point_transaction_id",
            _validate_optional_identifier(
                "StratagemUseRecord command_point_transaction_id",
                self.command_point_transaction_id,
            ),
        )
        object.__setattr__(
            self,
            "handler_id",
            _validate_identifier("StratagemUseRecord handler_id", self.handler_id),
        )
        object.__setattr__(
            self,
            "effects_resolved",
            _validate_bool("StratagemUseRecord effects_resolved", self.effects_resolved),
        )
        object.__setattr__(
            self,
            "unresolved_reason",
            _validate_optional_identifier(
                "StratagemUseRecord unresolved_reason",
                self.unresolved_reason,
            ),
        )
        if self.effects_resolved and self.unresolved_reason is not None:
            raise GameLifecycleError("Resolved Stratagem use cannot have unresolved_reason.")
        if not self.effects_resolved and self.unresolved_reason is None:
            raise GameLifecycleError("Unresolved Stratagem use requires unresolved_reason.")
        if not self.effects_resolved and self.command_point_transaction_id is not None:
            raise GameLifecycleError("Unresolved Stratagem use cannot spend Command points.")
        object.__setattr__(self, "effect_selection", validate_json_value(self.effect_selection))
        object.__setattr__(self, "effect_payload", validate_json_value(self.effect_payload))

    def to_payload(self) -> StratagemUseRecordPayload:
        return {
            "use_id": self.use_id,
            "player_id": self.player_id,
            "stratagem_id": self.stratagem_id,
            "source_id": self.source_id,
            "battle_round": self.battle_round,
            "phase": self.phase.value,
            "active_player_id": self.active_player_id,
            "timing_window_id": self.timing_window_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "selected_option_id": self.selected_option_id,
            "target_binding": self.target_binding.to_payload(),
            "targeted_unit_instance_ids": list(self.targeted_unit_instance_ids),
            "affected_unit_instance_ids": list(self.affected_unit_instance_ids),
            "command_point_cost": self.command_point_cost,
            "command_point_modifier_ids": list(self.command_point_modifier_ids),
            "command_point_modifier_source_ids": list(self.command_point_modifier_source_ids),
            "command_point_transaction_id": self.command_point_transaction_id,
            "handler_id": self.handler_id,
            "effects_resolved": self.effects_resolved,
            "unresolved_reason": self.unresolved_reason,
            "effect_selection": self.effect_selection,
            "effect_payload": self.effect_payload,
        }

    @classmethod
    def from_payload(cls, payload: StratagemUseRecordPayload) -> Self:
        return cls(
            use_id=payload["use_id"],
            player_id=payload["player_id"],
            stratagem_id=payload["stratagem_id"],
            source_id=payload["source_id"],
            battle_round=payload["battle_round"],
            phase=battle_phase_kind_from_token(payload["phase"]),
            active_player_id=payload["active_player_id"],
            timing_window_id=payload["timing_window_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            selected_option_id=payload["selected_option_id"],
            target_binding=StratagemTargetBinding.from_payload(payload["target_binding"]),
            targeted_unit_instance_ids=tuple(payload["targeted_unit_instance_ids"]),
            affected_unit_instance_ids=tuple(payload["affected_unit_instance_ids"]),
            command_point_cost=payload["command_point_cost"],
            command_point_modifier_ids=tuple(payload.get("command_point_modifier_ids", ())),
            command_point_modifier_source_ids=tuple(
                payload.get("command_point_modifier_source_ids", ())
            ),
            command_point_transaction_id=payload["command_point_transaction_id"],
            handler_id=payload["handler_id"],
            effects_resolved=payload["effects_resolved"],
            unresolved_reason=payload["unresolved_reason"],
            effect_selection=payload["effect_selection"],
            effect_payload=payload["effect_payload"],
        )
