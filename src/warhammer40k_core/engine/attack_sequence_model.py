# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_imports import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence, FastDiceGroup, attack_sequence_step_from_token, _runtime_modifier_registry, wound_roll_target_number
    from warhammer40k_core.engine.attack_sequence_dispatch import apply_resolve_target_unit_decision, apply_attack_weapon_group_decision, resolve_attack_sequence_until_blocked
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import is_destroyed_transport_disembark_proposal_request, invalid_destroyed_transport_disembark_proposal_status, apply_destroyed_transport_disembark_proposal_decision, _continue_pending_destroyed_transport_disembark, _remove_resolved_destroyed_transport_cargo_state, _begin_destroyed_transport_disembark_if_needed, _request_destroyed_transport_disembark_placement, _parse_destroyed_transport_disembark_submission_or_invalid, _destroyed_transport_proposal_parse_failure, _key_error_field, _missing_destroyed_transport_disembark_field, _destroyed_transport_proposal_invalid_status, _destroyed_transport_placement_invalid_status, _request_destroyed_transport_disembark_placement_retry, _resolve_destroyed_transport_disembark_submission, _apply_valid_destroyed_transport_disembark, _destroyed_transport_cargo_state_for_damage, _destroyed_transport_placement, _battlefield_scenario_for_attack_sequence, _objective_markers_for_attack_sequence
    from warhammer40k_core.engine.attack_sequence_group_selection import _select_or_request_next_gathered_group, _record_auto_attack_sequence_selection, apply_allocation_order_decision, apply_damage_allocation_model_decision, current_legal_damage_allocation_model_ids, apply_precision_allocation_decision, apply_feel_no_pain_decision, apply_destruction_reaction_decision, _continue_grouped_damage_after_interruption, _apply_deferred_mortal_wounds, _emit_deferred_mortal_wounds_applied, _apply_deferred_mortal_wound_feel_no_pain_decision, _continue_hazardous_after_mortal_wound_feel_no_pain, _continue_deadly_demise_after_mortal_wound_feel_no_pain, _grouped_precision_request_if_available, _precision_grouped_allocation_context_and_groups, _build_precision_allocation_request, _precision_pool_selection, _resolve_grouped_current_pool, _grouped_wounded_contexts_for_pool, _defer_grouped_devastating_wounds
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import _continue_grouped_allocation_for_wound_contexts, _continue_after_grouped_allocation_order, _resolve_grouped_damage_from, _alive_allocated_model_ids, _alive_allocated_model_ids_for_target_unit, _advance_after_current_pool, _attack_sequence_for_context, _grouped_attack_context_payload, _emit_grouped_allocation_event, _roll_grouped_saves, _emit_grouped_save_die_event
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _unit_has_model_within_deadly_demise_range, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "ATTACK_ALLOCATION_DECISION_TYPES",
    "ATTACK_RESOLUTION_SELECTION_DECISION_TYPES",
    "DAMAGE_ALLOCATION_RULE_ID",
    "DEADLY_DEMISE_SOURCE_KIND",
    "HAZARDOUS_SOURCE_KIND",
    "IGNORE_ALL_MODIFIERS_OPTION_ID",
    "IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID",
    "IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID",
    "KEEP_ALL_MODIFIERS_OPTION_ID",
    "SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE",
    "SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE",
    "SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE",
    "SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS",
    "_PRECISION_CHARACTER_GROUP_ROLES",
    "AttackModifierStackSet",
    "AttackModifierStackSetPayload",
    "AttackResolutionContextPayload",
    "AttackSequenceEvent",
    "AttackSequenceEventHandler",
    "AttackSequenceEventPayload",
    "AttackSequenceHooks",
    "AttackSequencePayload",
    "AttackSequenceStep",
    "DeferredMortalWounds",
    "DeferredMortalWoundsPayload",
    "DestroyedModelEmission",
    "DestructionReactionContextPayload",
    "FastDiceGroupPayload",
    "GatheredAttackContribution",
    "GatheredAttackContributionPayload",
    "GatheredAttackGroup",
    "GatheredAttackGroupPayload",
    "HazardousMortalWoundSourceContextPayload",
    "HitRoll",
    "HitRollPayload",
    "IdenticalAttackSignature",
    "IdenticalAttackSignaturePayload",
    "LostWoundContextPayload",
    "PendingDestroyedTransportDisembark",
    "PendingDestroyedTransportDisembarkPayload",
    "PendingGroupedDamage",
    "PendingGroupedDamagePayload",
    "PrecisionPoolSelection",
    "PsychicAttackModifierIgnoreSelection",
    "SaveDieEntryPayload",
    "WoundRoll",
    "WoundRollPayload",
    "attack_sequence_hit_roll_spec",
    "attack_sequence_wound_roll_spec",
    "deadly_demise_mortal_wounds_roll_spec",
    "deadly_demise_trigger_roll_spec",
)

ATTACK_ALLOCATION_DECISION_TYPES = frozenset(
    (
        "select_psychic_attack_modifier_ignores",
        SELECT_ALLOCATION_ORDER_DECISION_TYPE,
        SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
        SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    )
)
SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE = "select_resolve_target_unit"
SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE = "select_attack_weapon_group"
SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE = "select_psychic_attack_modifier_ignores"
KEEP_ALL_MODIFIERS_OPTION_ID = "keep-all-modifiers"
IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID = "ignore-detrimental-modifiers"
IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID = "ignore-beneficial-modifiers"
IGNORE_ALL_MODIFIERS_OPTION_ID = "ignore-all-modifiers"
ATTACK_RESOLUTION_SELECTION_DECISION_TYPES = frozenset(
    (
        SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    )
)
SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS = {
    "attack_sequence.hit": "hit_roll_state",
    "attack_sequence.wound": "wound_roll_state",
}
DAMAGE_ALLOCATION_RULE_ID = "core_rules_damage_allocation"
DEADLY_DEMISE_SOURCE_KIND = "deadly_demise"
HAZARDOUS_SOURCE_KIND = "hazardous"
_PRECISION_CHARACTER_GROUP_ROLES = frozenset(
    (
        AllocationGroupRole.CHARACTER,
        AllocationGroupRole.LEADER,
        AllocationGroupRole.SUPPORT,
    )
)


def attack_sequence_hit_roll_spec(
    *,
    weapon_profile_id: str,
    attack_context_id: str,
    attacker_player_id: str,
    reroll_forbidden_rule_ids: tuple[str, ...] = (),
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Hit roll for {weapon_profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.hit",
        actor_id=attacker_player_id,
        reroll_forbidden_rule_ids=reroll_forbidden_rule_ids,
    )


def attack_sequence_wound_roll_spec(
    *,
    weapon_profile_id: str,
    attack_context_id: str,
    attacker_player_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Wound roll for {weapon_profile_id} attack {attack_context_id}",
        roll_type="attack_sequence.wound",
        actor_id=attacker_player_id,
    )


def deadly_demise_trigger_roll_spec(
    *,
    source: DestructionReactionSource,
    player_id: str,
    model_instance_id: str,
) -> DiceRollSpec:
    if type(source) is not DestructionReactionSource:
        raise GameLifecycleError("Deadly Demise trigger roll requires a source.")
    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE:
        raise GameLifecycleError("Deadly Demise trigger roll requires a Deadly Demise source.")
    actor_id = _validate_identifier("player_id", player_id)
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=f"Deadly Demise trigger for {source.source_id} on {model_id}",
        roll_type="destruction_reaction.deadly_demise.trigger",
        actor_id=actor_id,
    )


def deadly_demise_mortal_wounds_roll_spec(
    *,
    source: DestructionReactionSource,
    player_id: str,
    target_unit_instance_id: str,
    sides: int,
) -> DiceRollSpec:
    if type(source) is not DestructionReactionSource:
        raise GameLifecycleError("Deadly Demise mortal-wound roll requires a source.")
    actor_id = _validate_identifier("player_id", player_id)
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=sides),
        reason=f"Deadly Demise mortal wounds for {source.source_id} into {target_unit_id}",
        roll_type="destruction_reaction.deadly_demise.mortal_wounds",
        actor_id=actor_id,
    )


class AttackSequenceStep(StrEnum):
    HIT = "hit"
    CRITICAL_HIT = "critical_hit"
    WOUND = "wound"
    CRITICAL_WOUND = "critical_wound"
    ALLOCATE = "allocate"
    SAVE = "save"
    DAMAGE = "damage"


class AttackSequenceEventPayload(TypedDict):
    step: str
    sequence_id: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    payload: JsonValue


class HitRollPayload(TypedDict):
    target_number: int
    roll_state: DiceRollStatePayload | None
    unmodified_roll: int | None
    minimum_unmodified_success: int
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    skipped: bool
    generated_hits: int


class WoundRollPayload(TypedDict):
    strength: int
    toughness: int
    target_number: int
    roll_state: DiceRollStatePayload | None
    unmodified_roll: int | None
    critical_threshold: int
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    skipped: bool


@dataclass(frozen=True, slots=True)
class PsychicAttackModifierIgnoreSelection:
    option_id: str
    skill_modifier: int
    hit_roll_modifier: int
    effective_skill_modifier: int
    effective_hit_roll_modifier: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_identifier("Psychic modifier option_id", self.option_id),
        )
        object.__setattr__(
            self,
            "skill_modifier",
            _validate_int("Psychic modifier skill_modifier", self.skill_modifier),
        )
        object.__setattr__(
            self,
            "hit_roll_modifier",
            _validate_int("Psychic modifier hit_roll_modifier", self.hit_roll_modifier),
        )
        object.__setattr__(
            self,
            "effective_skill_modifier",
            _validate_int(
                "Psychic modifier effective_skill_modifier",
                self.effective_skill_modifier,
            ),
        )
        object.__setattr__(
            self,
            "effective_hit_roll_modifier",
            _validate_int(
                "Psychic modifier effective_hit_roll_modifier",
                self.effective_hit_roll_modifier,
            ),
        )


class AttackSequencePayload(TypedDict):
    sequence_id: str
    source_phase: NotRequired[str]
    attacker_player_id: str
    attacking_unit_instance_id: str
    attack_pools: list[RangedAttackPoolPayload]
    used_pool_indices: list[int]
    selected_target_unit_instance_id: str | None
    current_gathered_group: GatheredAttackGroupPayload | None
    pool_index: int
    attack_index: int
    generated_hit_index: int
    current_hit_roll: HitRollPayload | None
    deferred_mortal_wounds: list[DeferredMortalWoundsPayload]
    pending_grouped_damage: PendingGroupedDamagePayload | None
    pending_destroyed_transport_disembark: PendingDestroyedTransportDisembarkPayload | None


class AttackResolutionContextPayload(TypedDict):
    sequence_id: str
    source_phase: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    generated_hit_index: int
    attacker_player_id: str
    defender_player_id: str
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    weapon_profile_id: str
    is_psychic_attack: bool
    selected_weapon_ability_ids: list[str]
    damage_profile: DamageProfilePayload
    hit_roll: HitRollPayload
    wound_roll: WoundRollPayload
    allocation: AttackAllocationPayload | None
    save_options: list[SaveOptionPayload]


class SaveDieEntryPayload(TypedDict):
    roll_state: DiceRollStatePayload
    value: int
    attack_context: AttackResolutionContextPayload


class PendingGroupedDamagePayload(TypedDict):
    sorted_save_dice: list[SaveDieEntryPayload]
    ordered_allocation_group_payloads: list[AllocationGroupPayload]
    allocation_context_payload: AttackAllocationRuleContextPayload
    allocated_model_ids: list[str]
    next_index: int


class PendingDestroyedTransportDisembarkPayload(TypedDict):
    attack_context: AttackResolutionContextPayload
    damage_application: DamageApplicationPayload
    saving_throw: JsonValue
    feel_no_pain: FeelNoPainResolutionPayload
    destroyed_model_controller_player_id: str
    transport_unit_instance_id: str
    pending_unit_instance_ids: list[str]
    resolved_disembarks: list[DestroyedTransportDisembarkPayload]
    pending_sources: list[DestructionReactionSourcePayload]


class LostWoundContextPayload(TypedDict):
    attack_context: AttackResolutionContextPayload
    allocated_model_id: str
    damage_kind: str
    requested_wounds: int
    saving_throw: JsonValue


class DestructionReactionContextPayload(TypedDict):
    context_kind: str
    attack_context: AttackResolutionContextPayload
    damage_application: JsonValue
    model_destroyed_event_id: str
    damage_event_id: str
    target_unit_instance_id: str
    model_instance_id: str
    destroyed_model_controller_player_id: str
    source_phase: str
    source_step: str
    removal_record: JsonValue
    transition_batch: JsonValue
    destroyed_model_rules_triggered: bool
    continuation: JsonValue


class DeferredMortalWoundsPayload(TypedDict):
    source_rule_id: str
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int


class HazardousMortalWoundSourceContextPayload(TypedDict):
    source_kind: str
    sequence_id: str
    attacking_unit_instance_id: str
    hazardous_weapon_profile_ids: list[str]
    hazardous_roll_state: DiceRollStatePayload
    mortal_wounds: int


class FastDiceGroupPayload(TypedDict):
    group_id: str
    attack_pool_ids: list[str]
    allowed: bool
    reason: str | None
    attacks: int


class AttackModifierStackSetPayload(TypedDict):
    attacks: ModifierStackPayload | None
    strength: ModifierStackPayload | None
    armor_penetration: ModifierStackPayload | None
    damage: ModifierStackPayload | None
    hit_roll_modifiers: list[RollModifierPayload]
    wound_roll_modifiers: list[RollModifierPayload]


class IdenticalAttackSignaturePayload(TypedDict):
    attacker_model_instance_id: str
    target_visible_model_ids: list[str]
    target_in_range_model_ids: list[str]
    hit_basis: str
    hit_roll_modifier: int
    wound_roll_modifiers: list[str]
    strength: str
    armor_penetration: str
    damage: str
    weapon_rule_tokens: list[str]
    targeting_rule_ids: list[str]
    shooting_type: str
    firing_deck_source_unit_instance_id: str | None
    firing_deck_source_model_instance_id: str | None


class GatheredAttackContributionPayload(TypedDict):
    pool_index: int
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    attacks: int
    firing_deck_source_unit_instance_id: str | None
    firing_deck_source_model_instance_id: str | None


class GatheredAttackGroupPayload(TypedDict):
    group_id: str
    target_unit_instance_id: str
    signature: IdenticalAttackSignaturePayload
    pool_indices: list[int]
    total_attacks: int
    contributions: list[GatheredAttackContributionPayload]


@dataclass(frozen=True, slots=True)
class HitRoll:
    target_number: int
    roll_state: DiceRollState | None
    unmodified_roll: int | None
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    minimum_unmodified_success: int = 2
    skipped: bool = False
    generated_hits: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "target_number",
            _validate_d6_target("HitRoll target_number", self.target_number),
        )
        object.__setattr__(
            self,
            "minimum_unmodified_success",
            _validate_d6_minimum_success(
                "HitRoll minimum_unmodified_success",
                self.minimum_unmodified_success,
            ),
        )
        if type(self.modifier) is not int:
            raise GameLifecycleError("HitRoll modifier must be an integer.")
        if type(self.capped_modifier) is not int:
            raise GameLifecycleError("HitRoll capped_modifier must be an integer.")
        if self.capped_modifier != _cap_roll_modifier(self.modifier):
            raise GameLifecycleError("HitRoll capped_modifier does not match modifier cap.")
        if type(self.successful) is not bool:
            raise GameLifecycleError("HitRoll successful must be a bool.")
        if type(self.critical) is not bool:
            raise GameLifecycleError("HitRoll critical must be a bool.")
        if type(self.skipped) is not bool:
            raise GameLifecycleError("HitRoll skipped must be a bool.")
        object.__setattr__(
            self,
            "generated_hits",
            _validate_positive_int("HitRoll generated_hits", self.generated_hits),
        )
        if self.skipped:
            if self.roll_state is not None or self.unmodified_roll is not None:
                raise GameLifecycleError("Skipped HitRoll must not include a roll.")
            if self.final_roll is not None:
                raise GameLifecycleError("Skipped HitRoll must not include a final roll.")
            if not self.successful:
                raise GameLifecycleError("Skipped HitRoll must generate successful hits.")
            if self.critical:
                raise GameLifecycleError("Skipped HitRoll cannot be a Critical Hit.")
            return
        if self.roll_state is None:
            raise GameLifecycleError("HitRoll requires a roll_state unless skipped.")
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("HitRoll roll_state must be DiceRollState.")
        if type(self.unmodified_roll) is not int or not 1 <= self.unmodified_roll <= 6:
            raise GameLifecycleError("HitRoll unmodified_roll must be a D6 value.")
        if type(self.final_roll) is not int:
            raise GameLifecycleError("HitRoll final_roll must be an integer.")
        expected_success = self.unmodified_roll == 6 or (
            self.unmodified_roll >= self.minimum_unmodified_success
            and self.final_roll >= self.target_number
        )
        if self.successful != expected_success:
            raise GameLifecycleError("HitRoll success flag does not match roll semantics.")
        if self.critical != (self.unmodified_roll == 6):
            raise GameLifecycleError("HitRoll critical flag must track unmodified 6.")

    @classmethod
    def auto_hit(cls, *, target_number: int, generated_hits: int = 1) -> Self:
        return cls(
            target_number=target_number,
            roll_state=None,
            unmodified_roll=None,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=False,
            skipped=True,
            generated_hits=generated_hits,
        )

    def to_payload(self) -> HitRollPayload:
        return {
            "target_number": self.target_number,
            "roll_state": None if self.roll_state is None else self.roll_state.to_payload(),
            "unmodified_roll": self.unmodified_roll,
            "minimum_unmodified_success": self.minimum_unmodified_success,
            "modifier": self.modifier,
            "capped_modifier": self.capped_modifier,
            "final_roll": self.final_roll,
            "successful": self.successful,
            "critical": self.critical,
            "skipped": self.skipped,
            "generated_hits": self.generated_hits,
        }

    @classmethod
    def from_payload(cls, payload: HitRollPayload) -> Self:
        roll_state_payload = payload["roll_state"]
        return cls(
            target_number=payload["target_number"],
            roll_state=(
                None
                if roll_state_payload is None
                else DiceRollState.from_payload(roll_state_payload)
            ),
            unmodified_roll=payload["unmodified_roll"],
            modifier=payload["modifier"],
            capped_modifier=payload["capped_modifier"],
            final_roll=payload["final_roll"],
            successful=payload["successful"],
            critical=payload["critical"],
            minimum_unmodified_success=payload["minimum_unmodified_success"],
            skipped=payload["skipped"],
            generated_hits=payload["generated_hits"],
        )


@dataclass(frozen=True, slots=True)
class WoundRoll:
    strength: int
    toughness: int
    target_number: int
    roll_state: DiceRollState | None
    unmodified_roll: int | None
    modifier: int
    capped_modifier: int
    final_roll: int | None
    successful: bool
    critical: bool
    critical_threshold: int = 6
    skipped: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "strength",
            _validate_positive_int("WoundRoll strength", self.strength),
        )
        object.__setattr__(
            self,
            "toughness",
            _validate_positive_int("WoundRoll toughness", self.toughness),
        )
        expected_target = wound_roll_target_number(strength=self.strength, toughness=self.toughness)
        if self.target_number != expected_target:
            raise GameLifecycleError("WoundRoll target_number does not match Strength/Toughness.")
        object.__setattr__(
            self,
            "critical_threshold",
            _validate_d6_target("WoundRoll critical_threshold", self.critical_threshold),
        )
        if type(self.modifier) is not int:
            raise GameLifecycleError("WoundRoll modifier must be an integer.")
        if self.capped_modifier != _cap_roll_modifier(self.modifier):
            raise GameLifecycleError("WoundRoll capped_modifier does not match modifier cap.")
        if type(self.successful) is not bool:
            raise GameLifecycleError("WoundRoll successful must be a bool.")
        if type(self.critical) is not bool:
            raise GameLifecycleError("WoundRoll critical must be a bool.")
        if type(self.skipped) is not bool:
            raise GameLifecycleError("WoundRoll skipped must be a bool.")
        if self.skipped:
            if self.roll_state is not None or self.unmodified_roll is not None:
                raise GameLifecycleError("Skipped WoundRoll must not include a roll.")
            if self.final_roll is not None:
                raise GameLifecycleError("Skipped WoundRoll must not include a final roll.")
            if not self.successful:
                raise GameLifecycleError("Skipped WoundRoll must be successful.")
            if self.critical:
                raise GameLifecycleError("Skipped WoundRoll cannot be a Critical Wound.")
            return
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError("WoundRoll roll_state must be DiceRollState.")
        if type(self.unmodified_roll) is not int or not 1 <= self.unmodified_roll <= 6:
            raise GameLifecycleError("WoundRoll unmodified_roll must be a D6 value.")
        if type(self.final_roll) is not int:
            raise GameLifecycleError("WoundRoll final_roll must be an integer.")
        expected_critical = self.unmodified_roll >= self.critical_threshold
        expected_success = expected_critical or (
            self.unmodified_roll != 1 and self.final_roll >= self.target_number
        )
        if self.successful != expected_success:
            raise GameLifecycleError("WoundRoll success flag does not match roll semantics.")
        if self.critical != expected_critical:
            raise GameLifecycleError("WoundRoll critical flag must track critical threshold.")

    @classmethod
    def auto_wound(
        cls,
        *,
        strength: int,
        toughness: int,
        target_number: int,
    ) -> Self:
        return cls(
            strength=strength,
            toughness=toughness,
            target_number=target_number,
            roll_state=None,
            unmodified_roll=None,
            critical_threshold=6,
            modifier=0,
            capped_modifier=0,
            final_roll=None,
            successful=True,
            critical=False,
            skipped=True,
        )

    def to_payload(self) -> WoundRollPayload:
        return {
            "strength": self.strength,
            "toughness": self.toughness,
            "target_number": self.target_number,
            "roll_state": None if self.roll_state is None else self.roll_state.to_payload(),
            "unmodified_roll": self.unmodified_roll,
            "critical_threshold": self.critical_threshold,
            "modifier": self.modifier,
            "capped_modifier": self.capped_modifier,
            "final_roll": self.final_roll,
            "successful": self.successful,
            "critical": self.critical,
            "skipped": self.skipped,
        }


@dataclass(frozen=True, slots=True)
class AttackSequenceEvent:
    step: AttackSequenceStep
    sequence_id: str
    attack_context_id: str
    pool_index: int
    attack_index: int
    payload: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "step", attack_sequence_step_from_token(self.step))
        object.__setattr__(
            self,
            "sequence_id",
            _validate_identifier("AttackSequenceEvent sequence_id", self.sequence_id),
        )
        object.__setattr__(
            self,
            "attack_context_id",
            _validate_identifier(
                "AttackSequenceEvent attack_context_id",
                self.attack_context_id,
            ),
        )
        object.__setattr__(
            self,
            "pool_index",
            _validate_non_negative_int("AttackSequenceEvent pool_index", self.pool_index),
        )
        object.__setattr__(
            self,
            "attack_index",
            _validate_non_negative_int("AttackSequenceEvent attack_index", self.attack_index),
        )
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def to_payload(self) -> AttackSequenceEventPayload:
        return {
            "step": self.step.value,
            "sequence_id": self.sequence_id,
            "attack_context_id": self.attack_context_id,
            "pool_index": self.pool_index,
            "attack_index": self.attack_index,
            "payload": self.payload,
        }


AttackSequenceEventHandler = Callable[[AttackSequenceEvent], AttackSequenceEvent]


@dataclass(frozen=True, slots=True)
class AttackSequenceHooks:
    handlers: tuple[AttackSequenceEventHandler, ...] = ()

    def __post_init__(self) -> None:
        if type(self.handlers) is not tuple:
            raise GameLifecycleError("AttackSequenceHooks handlers must be a tuple.")
        for handler in self.handlers:
            if not callable(handler):
                raise GameLifecycleError("AttackSequenceHooks handlers must be callable.")

    @classmethod
    def empty(cls) -> Self:
        return cls()

    def emit(self, event: AttackSequenceEvent) -> AttackSequenceEvent:
        if type(event) is not AttackSequenceEvent:
            raise GameLifecycleError("AttackSequenceHooks emit requires an event.")
        current = event
        for handler in self.handlers:
            updated = handler(current)
            if type(updated) is not AttackSequenceEvent:
                raise GameLifecycleError("Attack sequence hook must return a typed event.")
            if updated.step is not current.step:
                raise GameLifecycleError("Attack sequence hook cannot move timing windows.")
            current = updated
        return current


@dataclass(frozen=True, slots=True)
class DestroyedModelEmission:
    damage_event_id: str
    model_destroyed_event_id: str
    removal_record: ModelRemovalRecord
    transition_batch: BattlefieldTransitionBatch

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "damage_event_id",
            _validate_identifier("DestroyedModelEmission damage_event_id", self.damage_event_id),
        )
        object.__setattr__(
            self,
            "model_destroyed_event_id",
            _validate_identifier(
                "DestroyedModelEmission model_destroyed_event_id",
                self.model_destroyed_event_id,
            ),
        )
        if type(self.removal_record) is not ModelRemovalRecord:
            raise GameLifecycleError("DestroyedModelEmission requires a removal record.")
        if type(self.transition_batch) is not BattlefieldTransitionBatch:
            raise GameLifecycleError("DestroyedModelEmission requires a transition batch.")


@dataclass(frozen=True, slots=True)
class PrecisionPoolSelection:
    selected_group_id: str | None
    selected_model_ids: tuple[str, ...]
    selection_recorded: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_group_id",
            _validate_optional_identifier(
                "PrecisionPoolSelection selected_group_id",
                self.selected_group_id,
            ),
        )
        object.__setattr__(
            self,
            "selected_model_ids",
            _validate_identifier_tuple(
                "PrecisionPoolSelection selected_model_ids",
                self.selected_model_ids,
            ),
        )
        if type(self.selection_recorded) is not bool:
            raise GameLifecycleError("PrecisionPoolSelection selection_recorded must be a bool.")
        if self.selected_group_id is not None and not self.selection_recorded:
            raise GameLifecycleError("Precision selected group requires a recorded selection.")
        if self.selected_model_ids and self.selected_group_id is None:
            raise GameLifecycleError("Precision selected models require a selected group.")


@dataclass(frozen=True, slots=True)
class PendingGroupedDamage:
    sorted_save_dice: tuple[SaveDieEntryPayload, ...]
    ordered_allocation_group_payloads: tuple[AllocationGroupPayload, ...]
    allocation_context_payload: AttackAllocationRuleContextPayload
    allocated_model_ids: tuple[str, ...]
    next_index: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sorted_save_dice",
            _validate_save_die_entry_tuple(self.sorted_save_dice),
        )
        object.__setattr__(
            self,
            "ordered_allocation_group_payloads",
            _validate_allocation_group_payload_tuple(self.ordered_allocation_group_payloads),
        )
        AttackAllocationRuleContext.from_payload(self.allocation_context_payload)
        object.__setattr__(
            self,
            "allocation_context_payload",
            validate_json_value(self.allocation_context_payload),
        )
        object.__setattr__(
            self,
            "allocated_model_ids",
            _validate_identifier_tuple(
                "PendingGroupedDamage allocated_model_ids",
                self.allocated_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "next_index",
            _validate_non_negative_int("PendingGroupedDamage next_index", self.next_index),
        )
        if self.next_index > len(self.sorted_save_dice):
            raise GameLifecycleError("PendingGroupedDamage next_index is outside save dice.")

    def to_payload(self) -> PendingGroupedDamagePayload:
        return {
            "sorted_save_dice": list(self.sorted_save_dice),
            "ordered_allocation_group_payloads": list(self.ordered_allocation_group_payloads),
            "allocation_context_payload": self.allocation_context_payload,
            "allocated_model_ids": list(self.allocated_model_ids),
            "next_index": self.next_index,
        }

    @classmethod
    def from_payload(cls, payload: PendingGroupedDamagePayload) -> Self:
        return cls(
            sorted_save_dice=tuple(payload["sorted_save_dice"]),
            ordered_allocation_group_payloads=tuple(payload["ordered_allocation_group_payloads"]),
            allocation_context_payload=payload["allocation_context_payload"],
            allocated_model_ids=tuple(payload["allocated_model_ids"]),
            next_index=payload["next_index"],
        )

    def allocation_context(self) -> AttackAllocationRuleContext:
        return AttackAllocationRuleContext.from_payload(self.allocation_context_payload)

    def ordered_allocation_groups(self) -> tuple[AllocationGroup, ...]:
        return tuple(
            AllocationGroup.from_payload(group_payload)
            for group_payload in self.ordered_allocation_group_payloads
        )

    def with_next_index(self, next_index: int) -> Self:
        return type(self)(
            sorted_save_dice=self.sorted_save_dice,
            ordered_allocation_group_payloads=self.ordered_allocation_group_payloads,
            allocation_context_payload=self.allocation_context_payload,
            allocated_model_ids=self.allocated_model_ids,
            next_index=next_index,
        )

    def with_allocated_model_ids(self, allocated_model_ids: tuple[str, ...]) -> Self:
        return type(self)(
            sorted_save_dice=self.sorted_save_dice,
            ordered_allocation_group_payloads=self.ordered_allocation_group_payloads,
            allocation_context_payload=self.allocation_context_payload,
            allocated_model_ids=allocated_model_ids,
            next_index=self.next_index,
        )

    def advanced_after_current_die(self) -> Self:
        return self.with_next_index(self.next_index + 1)


@dataclass(frozen=True, slots=True)
class PendingDestroyedTransportDisembark:
    attack_context: AttackResolutionContextPayload
    damage_application: DamageApplication
    saving_throw_payload: JsonValue
    feel_no_pain: FeelNoPainResolution
    destroyed_model_controller_player_id: str
    transport_unit_instance_id: str
    pending_unit_instance_ids: tuple[str, ...]
    resolved_disembarks: tuple[DestroyedTransportDisembark, ...] = ()
    pending_sources: tuple[DestructionReactionSource, ...] = ()

    def __post_init__(self) -> None:
        attack_context = validate_json_value(self.attack_context)
        if not isinstance(attack_context, dict):
            raise GameLifecycleError(
                "Pending destroyed Transport attack_context must be an object."
            )
        object.__setattr__(
            self,
            "attack_context",
            cast(AttackResolutionContextPayload, attack_context),
        )
        if type(self.damage_application) is not DamageApplication:
            raise GameLifecycleError(
                "Pending destroyed Transport damage_application must be DamageApplication."
            )
        if not self.damage_application.destroyed:
            raise GameLifecycleError("Pending destroyed Transport requires destroyed damage.")
        if (
            self.damage_application.target_unit_instance_id
            != self.attack_context["target_unit_instance_id"]
        ):
            raise GameLifecycleError("Pending destroyed Transport damage target drift.")
        object.__setattr__(
            self,
            "saving_throw_payload",
            validate_json_value(self.saving_throw_payload),
        )
        if type(self.feel_no_pain) is not FeelNoPainResolution:
            raise GameLifecycleError(
                "Pending destroyed Transport feel_no_pain must be FeelNoPainResolution."
            )
        object.__setattr__(
            self,
            "destroyed_model_controller_player_id",
            _validate_identifier(
                "Pending destroyed Transport controller",
                self.destroyed_model_controller_player_id,
            ),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "Pending destroyed Transport transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "pending_unit_instance_ids",
            _validate_identifier_tuple(
                "Pending destroyed Transport unit ids",
                self.pending_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "resolved_disembarks",
            _validate_destroyed_transport_disembark_tuple(self.resolved_disembarks),
        )
        object.__setattr__(
            self,
            "pending_sources",
            _validate_destruction_reaction_source_tuple(
                "Pending destroyed Transport pending_sources",
                self.pending_sources,
            ),
        )
        resolved_unit_ids = {disembark.unit_instance_id for disembark in self.resolved_disembarks}
        if resolved_unit_ids & set(self.pending_unit_instance_ids):
            raise GameLifecycleError("Pending destroyed Transport unit appears in both states.")
        for disembark in self.resolved_disembarks:
            if disembark.transport_unit_instance_id != self.transport_unit_instance_id:
                raise GameLifecycleError("Pending destroyed Transport disembark transport drift.")
            if disembark.battle_round < 1:
                raise GameLifecycleError("Pending destroyed Transport disembark round drift.")

    @property
    def next_unit_instance_id(self) -> str | None:
        if not self.pending_unit_instance_ids:
            return None
        return self.pending_unit_instance_ids[0]

    def with_resolved_disembark(self, disembark: DestroyedTransportDisembark) -> Self:
        if type(disembark) is not DestroyedTransportDisembark:
            raise GameLifecycleError("Resolved destroyed Transport disembark is invalid.")
        if self.next_unit_instance_id != disembark.unit_instance_id:
            raise GameLifecycleError("Resolved destroyed Transport disembark unit drift.")
        return type(self)(
            attack_context=self.attack_context,
            damage_application=self.damage_application,
            saving_throw_payload=self.saving_throw_payload,
            feel_no_pain=self.feel_no_pain,
            destroyed_model_controller_player_id=self.destroyed_model_controller_player_id,
            transport_unit_instance_id=self.transport_unit_instance_id,
            pending_unit_instance_ids=self.pending_unit_instance_ids[1:],
            resolved_disembarks=(*self.resolved_disembarks, disembark),
            pending_sources=self.pending_sources,
        )

    def to_payload(self) -> PendingDestroyedTransportDisembarkPayload:
        return {
            "attack_context": self.attack_context,
            "damage_application": self.damage_application.to_payload(),
            "saving_throw": self.saving_throw_payload,
            "feel_no_pain": self.feel_no_pain.to_payload(),
            "destroyed_model_controller_player_id": self.destroyed_model_controller_player_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "pending_unit_instance_ids": list(self.pending_unit_instance_ids),
            "resolved_disembarks": [
                disembark.to_payload() for disembark in self.resolved_disembarks
            ],
            "pending_sources": [source.to_payload() for source in self.pending_sources],
        }

    @classmethod
    def from_payload(cls, payload: PendingDestroyedTransportDisembarkPayload) -> Self:
        return cls(
            attack_context=payload["attack_context"],
            damage_application=DamageApplication.from_payload(payload["damage_application"]),
            saving_throw_payload=payload["saving_throw"],
            feel_no_pain=FeelNoPainResolution.from_payload(payload["feel_no_pain"]),
            destroyed_model_controller_player_id=payload["destroyed_model_controller_player_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            pending_unit_instance_ids=tuple(payload["pending_unit_instance_ids"]),
            resolved_disembarks=tuple(
                DestroyedTransportDisembark.from_payload(disembark)
                for disembark in payload["resolved_disembarks"]
            ),
            pending_sources=tuple(
                DestructionReactionSource.from_payload(source)
                for source in payload["pending_sources"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AttackModifierStackSet:
    attacks: ModifierStack | None = None
    strength: ModifierStack | None = None
    armor_penetration: ModifierStack | None = None
    damage: ModifierStack | None = None
    hit_roll_modifiers: tuple[RollModifier, ...] = ()
    wound_roll_modifiers: tuple[RollModifier, ...] = ()

    def __post_init__(self) -> None:
        for stack in (self.attacks, self.strength, self.armor_penetration, self.damage):
            if stack is not None and type(stack) is not ModifierStack:
                raise GameLifecycleError("AttackModifierStackSet stacks must be ModifierStack.")
        object.__setattr__(
            self,
            "hit_roll_modifiers",
            _validate_roll_modifier_tuple(
                "AttackModifierStackSet hit_roll_modifiers",
                self.hit_roll_modifiers,
            ),
        )
        object.__setattr__(
            self,
            "wound_roll_modifiers",
            _validate_roll_modifier_tuple(
                "AttackModifierStackSet wound_roll_modifiers",
                self.wound_roll_modifiers,
            ),
        )

    def to_payload(self) -> AttackModifierStackSetPayload:
        return {
            "attacks": None if self.attacks is None else self.attacks.to_payload(),
            "strength": None if self.strength is None else self.strength.to_payload(),
            "armor_penetration": (
                None if self.armor_penetration is None else self.armor_penetration.to_payload()
            ),
            "damage": None if self.damage is None else self.damage.to_payload(),
            "hit_roll_modifiers": [modifier.to_payload() for modifier in self.hit_roll_modifiers],
            "wound_roll_modifiers": [
                modifier.to_payload() for modifier in self.wound_roll_modifiers
            ],
        }


@dataclass(frozen=True, slots=True)
class DeferredMortalWounds:
    source_rule_id: str
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DeferredMortalWounds source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "DeferredMortalWounds target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attack_context_id",
            _validate_identifier(
                "DeferredMortalWounds attack_context_id",
                self.attack_context_id,
            ),
        )
        object.__setattr__(
            self,
            "mortal_wounds",
            _validate_positive_int("DeferredMortalWounds mortal_wounds", self.mortal_wounds),
        )

    def to_payload(self) -> DeferredMortalWoundsPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "attack_context_id": self.attack_context_id,
            "mortal_wounds": self.mortal_wounds,
        }

    @classmethod
    def from_payload(cls, payload: DeferredMortalWoundsPayload) -> Self:
        return cls(
            source_rule_id=payload["source_rule_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            attack_context_id=payload["attack_context_id"],
            mortal_wounds=payload["mortal_wounds"],
        )


@dataclass(frozen=True, slots=True)
class IdenticalAttackSignature:
    attacker_model_instance_id: str
    target_visible_model_ids: tuple[str, ...]
    target_in_range_model_ids: tuple[str, ...]
    hit_basis: str
    hit_roll_modifier: int
    wound_roll_modifiers: tuple[str, ...]
    strength: str
    armor_penetration: str
    damage: str
    weapon_rule_tokens: tuple[str, ...]
    targeting_rule_ids: tuple[str, ...]
    shooting_type: str
    firing_deck_source_unit_instance_id: str | None = None
    firing_deck_source_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "IdenticalAttackSignature attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "target_visible_model_ids",
            _validate_ordered_identifier_tuple(
                "IdenticalAttackSignature target_visible_model_ids",
                self.target_visible_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "target_in_range_model_ids",
            _validate_ordered_identifier_tuple(
                "IdenticalAttackSignature target_in_range_model_ids",
                self.target_in_range_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "hit_basis",
            _validate_identifier("IdenticalAttackSignature hit_basis", self.hit_basis),
        )
        if type(self.hit_roll_modifier) is not int:
            raise GameLifecycleError("IdenticalAttackSignature hit_roll_modifier must be an int.")
        object.__setattr__(
            self,
            "wound_roll_modifiers",
            _validate_identifier_tuple(
                "IdenticalAttackSignature wound_roll_modifiers",
                self.wound_roll_modifiers,
            ),
        )
        object.__setattr__(
            self,
            "strength",
            _validate_identifier("IdenticalAttackSignature strength", self.strength),
        )
        object.__setattr__(
            self,
            "armor_penetration",
            _validate_identifier(
                "IdenticalAttackSignature armor_penetration",
                self.armor_penetration,
            ),
        )
        object.__setattr__(
            self,
            "damage",
            _validate_identifier("IdenticalAttackSignature damage", self.damage),
        )
        object.__setattr__(
            self,
            "weapon_rule_tokens",
            _validate_identifier_tuple(
                "IdenticalAttackSignature weapon_rule_tokens",
                self.weapon_rule_tokens,
            ),
        )
        object.__setattr__(
            self,
            "targeting_rule_ids",
            _validate_identifier_tuple(
                "IdenticalAttackSignature targeting_rule_ids",
                self.targeting_rule_ids,
            ),
        )
        object.__setattr__(
            self,
            "shooting_type",
            _validate_identifier("IdenticalAttackSignature shooting_type", self.shooting_type),
        )
        object.__setattr__(
            self,
            "firing_deck_source_unit_instance_id",
            _validate_optional_identifier(
                "IdenticalAttackSignature firing_deck_source_unit_instance_id",
                self.firing_deck_source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_model_instance_id",
            _validate_optional_identifier(
                "IdenticalAttackSignature firing_deck_source_model_instance_id",
                self.firing_deck_source_model_instance_id,
            ),
        )
        if (self.firing_deck_source_unit_instance_id is None) != (
            self.firing_deck_source_model_instance_id is None
        ):
            raise GameLifecycleError(
                "IdenticalAttackSignature Firing Deck source unit and model must be supplied "
                "together."
            )

    def stable_hash(self) -> str:
        encoded = canonical_json(self.to_payload()).encode("utf-8")
        return sha256(encoded).hexdigest()[:16]

    def to_payload(self) -> IdenticalAttackSignaturePayload:
        return {
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "target_visible_model_ids": list(self.target_visible_model_ids),
            "target_in_range_model_ids": list(self.target_in_range_model_ids),
            "hit_basis": self.hit_basis,
            "hit_roll_modifier": self.hit_roll_modifier,
            "wound_roll_modifiers": list(self.wound_roll_modifiers),
            "strength": self.strength,
            "armor_penetration": self.armor_penetration,
            "damage": self.damage,
            "weapon_rule_tokens": list(self.weapon_rule_tokens),
            "targeting_rule_ids": list(self.targeting_rule_ids),
            "shooting_type": self.shooting_type,
            "firing_deck_source_unit_instance_id": self.firing_deck_source_unit_instance_id,
            "firing_deck_source_model_instance_id": self.firing_deck_source_model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: IdenticalAttackSignaturePayload) -> Self:
        return cls(
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            target_visible_model_ids=tuple(payload["target_visible_model_ids"]),
            target_in_range_model_ids=tuple(payload["target_in_range_model_ids"]),
            hit_basis=payload["hit_basis"],
            hit_roll_modifier=payload["hit_roll_modifier"],
            wound_roll_modifiers=tuple(payload["wound_roll_modifiers"]),
            strength=payload["strength"],
            armor_penetration=payload["armor_penetration"],
            damage=payload["damage"],
            weapon_rule_tokens=tuple(payload["weapon_rule_tokens"]),
            targeting_rule_ids=tuple(payload["targeting_rule_ids"]),
            shooting_type=payload["shooting_type"],
            firing_deck_source_unit_instance_id=payload["firing_deck_source_unit_instance_id"],
            firing_deck_source_model_instance_id=payload["firing_deck_source_model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class GatheredAttackContribution:
    pool_index: int
    attacker_model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    target_unit_instance_id: str
    attacks: int
    firing_deck_source_unit_instance_id: str | None = None
    firing_deck_source_model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pool_index",
            _validate_non_negative_int("GatheredAttackContribution pool_index", self.pool_index),
        )
        object.__setattr__(
            self,
            "attacker_model_instance_id",
            _validate_identifier(
                "GatheredAttackContribution attacker_model_instance_id",
                self.attacker_model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("GatheredAttackContribution wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "GatheredAttackContribution weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "GatheredAttackContribution target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attacks",
            _validate_positive_int("GatheredAttackContribution attacks", self.attacks),
        )
        object.__setattr__(
            self,
            "firing_deck_source_unit_instance_id",
            _validate_optional_identifier(
                "GatheredAttackContribution firing_deck_source_unit_instance_id",
                self.firing_deck_source_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_source_model_instance_id",
            _validate_optional_identifier(
                "GatheredAttackContribution firing_deck_source_model_instance_id",
                self.firing_deck_source_model_instance_id,
            ),
        )
        if (self.firing_deck_source_unit_instance_id is None) != (
            self.firing_deck_source_model_instance_id is None
        ):
            raise GameLifecycleError(
                "GatheredAttackContribution Firing Deck source unit and model must be supplied "
                "together."
            )

    def to_payload(self) -> GatheredAttackContributionPayload:
        return {
            "pool_index": self.pool_index,
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "attacks": self.attacks,
            "firing_deck_source_unit_instance_id": self.firing_deck_source_unit_instance_id,
            "firing_deck_source_model_instance_id": self.firing_deck_source_model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: GatheredAttackContributionPayload) -> Self:
        return cls(
            pool_index=payload["pool_index"],
            attacker_model_instance_id=payload["attacker_model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            attacks=payload["attacks"],
            firing_deck_source_unit_instance_id=payload["firing_deck_source_unit_instance_id"],
            firing_deck_source_model_instance_id=payload["firing_deck_source_model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class GatheredAttackGroup:
    group_id: str
    target_unit_instance_id: str
    signature: IdenticalAttackSignature
    pool_indices: tuple[int, ...]
    total_attacks: int
    contributions: tuple[GatheredAttackContribution, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "group_id",
            _validate_identifier("GatheredAttackGroup group_id", self.group_id),
        )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "GatheredAttackGroup target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        if type(self.signature) is not IdenticalAttackSignature:
            raise GameLifecycleError(
                "GatheredAttackGroup signature must be an IdenticalAttackSignature."
            )
        object.__setattr__(
            self,
            "pool_indices",
            _validate_pool_index_tuple("GatheredAttackGroup pool_indices", self.pool_indices),
        )
        object.__setattr__(
            self,
            "total_attacks",
            _validate_positive_int("GatheredAttackGroup total_attacks", self.total_attacks),
        )
        object.__setattr__(
            self,
            "contributions",
            _validate_gathered_attack_contributions(self.contributions),
        )
        if tuple(contribution.pool_index for contribution in self.contributions) != (
            self.pool_indices
        ):
            raise GameLifecycleError("GatheredAttackGroup contribution pool indices drift.")
        if sum(contribution.attacks for contribution in self.contributions) != self.total_attacks:
            raise GameLifecycleError("GatheredAttackGroup total attacks drift.")
        if any(
            contribution.target_unit_instance_id != self.target_unit_instance_id
            for contribution in self.contributions
        ):
            raise GameLifecycleError("GatheredAttackGroup contribution target drift.")

    @property
    def primary_pool_index(self) -> int:
        return self.pool_indices[0]

    def to_payload(self) -> GatheredAttackGroupPayload:
        return {
            "group_id": self.group_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "signature": self.signature.to_payload(),
            "pool_indices": list(self.pool_indices),
            "total_attacks": self.total_attacks,
            "contributions": [contribution.to_payload() for contribution in self.contributions],
        }

    @classmethod
    def from_payload(cls, payload: GatheredAttackGroupPayload) -> Self:
        return cls(
            group_id=payload["group_id"],
            target_unit_instance_id=payload["target_unit_instance_id"],
            signature=IdenticalAttackSignature.from_payload(payload["signature"]),
            pool_indices=tuple(payload["pool_indices"]),
            total_attacks=payload["total_attacks"],
            contributions=tuple(
                GatheredAttackContribution.from_payload(contribution)
                for contribution in payload["contributions"]
            ),
        )
