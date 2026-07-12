# ruff: noqa: F401,RUF022
# pyright: reportUnusedImport=false
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.attack_sequence import (
    ATTACK_ALLOCATION_DECISION_TYPES,
    ATTACK_RESOLUTION_SELECTION_DECISION_TYPES,
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackSequence,
    AttackSequencePayload,
    apply_allocation_order_decision,
    apply_attack_weapon_group_decision,
    apply_damage_allocation_model_decision,
    apply_destroyed_transport_disembark_proposal_decision,
    apply_destruction_reaction_decision,
    apply_feel_no_pain_decision,
    apply_precision_allocation_decision,
    apply_resolve_target_unit_decision,
    apply_source_backed_attack_dice_reroll_decision,
    build_select_attack_weapon_group_request,
    build_select_resolve_target_unit_request,
    gathered_attack_groups_for_target,
    is_destroyed_transport_disembark_proposal_request,
    resolve_attack_sequence_until_blocked,
    selected_attack_weapon_group_from_result,
    selected_resolve_target_from_result,
    unresolved_target_unit_ids,
    validate_psychic_attack_modifier_ignore_decision,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
    successful_hit_target_unit_ids_for_sequence,
)
from warhammer40k_core.engine.battle_shock_hooks import BattleShockHookRegistry
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE,
    apply_catalog_post_shoot_hit_target_status_result,
    invalid_catalog_post_shoot_hit_target_status_status,
)
from warhammer40k_core.engine.catalog_selected_target_effects import (
    SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE,
    apply_catalog_post_shoot_hit_target_effect_result,
    invalid_catalog_post_shoot_hit_target_effect_status,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
)
from warhammer40k_core.engine.damaged_effects import (
    CatalogDamagedShootingWeaponSelectionLimit,
    catalog_damaged_shooting_weapon_selection_limit_for_profile,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
)
from warhammer40k_core.engine.movement_proposals import PLACEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.ranged_rule_effects import (
    detection_range_bonus_inches_for_effects,
    hidden_unit_effect_ids,
    ranged_attacks_keep_hidden_by_effects,
    unit_is_hidden_by_effects,
    weapon_profile_with_character_target_ap_effects,
)
from warhammer40k_core.engine.ranged_weapon_keyword_effects import (
    weapon_profile_with_ranged_keyword_effects,
)
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindow as TriggeredReactionWindow,
)
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindowKind,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    rules_unit_id_for_unit_id,
    rules_unit_view_by_id,
    rules_unit_view_from_armies,
)
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    WeaponProfileModifierContext,
)
from warhammer40k_core.engine.shooting_end_surge_hooks import (
    ShootingEndSurgeContext,
    ShootingEndSurgeGrant,
    ShootingEndSurgeHookRegistry,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
    ShootingPhaseStartHookRegistry,
    ShootingPhaseStartRequestContext,
    ShootingPhaseStartResultContext,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
    shooting_target_candidates_for_unit,
    shooting_visibility_cache_key,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_types import ShootingType, shooting_type_from_token
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
    ShootingUnitSelectedContext,
    ShootingUnitSelectedGrant,
    ShootingUnitSelectedGrantPayload,
    ShootingUnitSelectedGrantRegistry,
    ShootingUnitSelectedHookRegistry,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookRegistry,
)
from warhammer40k_core.engine.transports import (
    FiringDeckWeaponSelection,
    resolve_firing_deck_selection,
)
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_abilities import (
    firing_deck_value_for_unit as unit_firing_deck_value,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    ASSAULT_RULE_ID,
    CLOSE_QUARTERS_RULE_ID,
    FIRE_OVERWATCH_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
    blast_attack_bonus,
    blast_rule_id,
    has_close_quarters_weapon_keyword,
    has_weapon_keyword,
    heavy_rule_id,
    melta_damage_bonus,
    melta_rule_id,
    rapid_fire_attack_bonus,
    rapid_fire_rule_id,
    weapon_ability_selection_request,
)
from warhammer40k_core.engine.weapon_declaration import (
    SHOOTING_DECLARATION_PROPOSAL_KIND,
    AvailableWeaponPayload,
    RangedAttackPool,
    RangedAttackPoolPayload,
    ShootingDeclarationProposal,
    ShootingDeclarationProposalRequest,
    ShootingProposalValidationResult,
    WeaponDeclaration,
    attacks_for_profile,
    shooting_declaration_missing_field,
    shooting_declaration_proposal_from_json,
    unresolved_attacks_for_validation,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import (
        GameState,
        OneShotWeaponUseRecord,
        RangedAttackHistoryRecord,
    )
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import (
        StratagemCatalogIndex,
        StratagemEligibilityContext,
    )

__all__ = (
    "ASSAULT_RULE_ID",
    "ATTACK_ALLOCATION_DECISION_TYPES",
    "ATTACK_RESOLUTION_SELECTION_DECISION_TYPES",
    "AbilityDescriptor",
    "AbilityKind",
    "AbilityCatalogIndex",
    "ArmyCatalog",
    "AttackSequence",
    "AttackSequenceCompletedContext",
    "AttackSequenceCompletedHookRegistry",
    "AttackSequencePayload",
    "AvailableWeaponPayload",
    "BattlePhase",
    "BattlePhaseKind",
    "BattleShockHookRegistry",
    "BattlefieldScenario",
    "CLOSE_QUARTERS_RULE_ID",
    "CatalogDamagedShootingWeaponSelectionLimit",
    "DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID",
    "DICE_REROLL_DECISION_TYPE",
    "DecisionController",
    "DecisionError",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResult",
    "DiceExpression",
    "DiceRollManager",
    "DiceRollSpec",
    "DistanceMeasurementContext",
    "EffectExpiration",
    "FIRE_OVERWATCH_RULE_ID",
    "FiringDeckWeaponSelection",
    "GameLifecycleError",
    "GameLifecycleStage",
    "INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID",
    "INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID",
    "INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID",
    "IdentifierValidator",
    "JsonValue",
    "LifecycleStatus",
    "Mapping",
    "MappingProxyType",
    "ModelInstance",
    "MovementMode",
    "NotRequired",
    "PLACEMENT_PROPOSAL_DECISION_TYPE",
    "PersistingEffect",
    "PlacementError",
    "RangeProfileKind",
    "RangedAttackPool",
    "RangedAttackPoolPayload",
    "ReactionWindowKind",
    "RulesUnitView",
    "RulesetDescriptor",
    "RuntimeModifierRegistry",
    "SELECT_ALLOCATION_ORDER_DECISION_TYPE",
    "SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE",
    "SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE",
    "SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE",
    "invalid_catalog_post_shoot_hit_target_status_status",
    "invalid_catalog_post_shoot_hit_target_effect_status",
    "SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE",
    "SELECT_DESTRUCTION_REACTION_DECISION_TYPE",
    "SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE",
    "SELECT_FEEL_NO_PAIN_DECISION_TYPE",
    "SELECT_PRECISION_ALLOCATION_DECISION_TYPE",
    "SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE",
    "SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE",
    "SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE",
    "SHOOTING_DECLARATION_PROPOSAL_KIND",
    "SNAP_SHOOTING_RULE_ID",
    "Self",
    "ShootingDeclarationProposal",
    "ShootingDeclarationProposalRequest",
    "ShootingEndSurgeContext",
    "ShootingEndSurgeGrant",
    "ShootingEndSurgeHookRegistry",
    "ShootingPhaseStartHookRegistry",
    "ShootingPhaseStartRequestContext",
    "ShootingPhaseStartResultContext",
    "ShootingProposalValidationResult",
    "ShootingTargetCandidate",
    "ShootingTargetRestrictionContext",
    "ShootingTargetRestrictionHookRegistry",
    "ShootingTargetViolationCode",
    "ShootingType",
    "ShootingUnitSelectedContext",
    "ShootingUnitSelectedGrant",
    "ShootingUnitSelectedGrantPayload",
    "ShootingUnitSelectedGrantRegistry",
    "ShootingUnitSelectedHookRegistry",
    "StratagemCostModifierRegistry",
    "TYPE_CHECKING",
    "TerrainFeatureDefinition",
    "TriggeredMovementDescriptor",
    "TriggeredMovementEligibleUnit",
    "TriggeredMovementKind",
    "TriggeredReactionWindow",
    "TypedDict",
    "UnitInstance",
    "UnitPlacement",
    "Wargear",
    "WeaponDeclaration",
    "WeaponKeyword",
    "WeaponProfile",
    "WeaponProfileModifierContext",
    "annotations",
    "apply_allocation_order_decision",
    "apply_attack_weapon_group_decision",
    "apply_catalog_post_shoot_hit_target_status_result",
    "apply_catalog_post_shoot_hit_target_effect_result",
    "apply_damage_allocation_model_decision",
    "apply_destroyed_transport_disembark_proposal_decision",
    "apply_destruction_reaction_decision",
    "apply_faction_resource_spend_effect",
    "apply_feel_no_pain_decision",
    "apply_precision_allocation_decision",
    "apply_resolve_target_unit_decision",
    "apply_source_backed_attack_dice_reroll_decision",
    "attack_sequence_completed_event_id",
    "attacks_for_profile",
    "battle_phase_kind_from_token",
    "blast_attack_bonus",
    "blast_rule_id",
    "build_select_attack_weapon_group_request",
    "build_select_resolve_target_unit_request",
    "canonical_json",
    "catalog_damaged_shooting_weapon_selection_limit_for_profile",
    "cast",
    "dataclass",
    "detection_range_bonus_inches_for_effects",
    "faction_resource_result_enriched_payload",
    "field",
    "gathered_attack_groups_for_target",
    "geometry_model_for_placement",
    "has_close_quarters_weapon_keyword",
    "has_weapon_keyword",
    "heavy_rule_id",
    "hidden_unit_effect_ids",
    "is_destroyed_transport_disembark_proposal_request",
    "melta_damage_bonus",
    "melta_rule_id",
    "parameterized_decision_option",
    "ranged_attacks_keep_hidden_by_effects",
    "rapid_fire_attack_bonus",
    "rapid_fire_rule_id",
    "resolve_attack_sequence_until_blocked",
    "resolve_firing_deck_selection",
    "rules_unit_id_for_unit_id",
    "rules_unit_view_by_id",
    "rules_unit_view_from_armies",
    "selected_attack_weapon_group_from_result",
    "selected_resolve_target_from_result",
    "shooting_declaration_missing_field",
    "shooting_declaration_proposal_from_json",
    "shooting_target_candidate_for_model",
    "shooting_target_candidates_for_unit",
    "shooting_type_from_token",
    "shooting_visibility_cache_key",
    "successful_hit_target_unit_ids_for_sequence",
    "triggered_movement_unit_selection_request",
    "unit_firing_deck_value",
    "unit_has_line_of_sight_to_target",
    "unit_is_hidden_by_effects",
    "unresolved_attacks_for_validation",
    "unresolved_target_unit_ids",
    "validate_json_value",
    "validate_psychic_attack_modifier_ignore_decision",
    "weapon_ability_selection_request",
    "weapon_profile_with_character_target_ap_effects",
    "weapon_profile_with_ranged_keyword_effects",
)
