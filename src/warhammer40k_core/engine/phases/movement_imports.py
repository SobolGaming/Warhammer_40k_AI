# ruff: noqa: F401,RUF022
# pyright: reportUnusedImport=false
from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from itertools import combinations
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecPayload,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
    RerollPermissionPayload,
)
from warhammer40k_core.core.modifiers import (
    RollModifier,
    RollModifierPayload,
    apply_roll_modifiers,
)
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MissionDeploymentZoneSource,
    MovementMode,
    RulesetDescriptor,
    RulesetDescriptorError,
    movement_mode_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatus,
    interrupt_mission_action_for_battlefield_departure,
    interrupt_mission_action_for_displacement,
)
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityHookRegistry,
)
from warhammer40k_core.engine.advance_hooks import (
    DECLINE_ADVANCE_MOVE_GRANT_OPTION_ID,
    SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveGrantPayload,
    AdvanceMoveHookRegistry,
)
from warhammer40k_core.engine.aircraft import (
    AircraftMovementPolicy,
    AircraftMovementPolicyPayload,
    AircraftMovementViolation,
    AircraftReserveTransitionReason,
    HoverModeState,
    aircraft_model_ids_for_scenario,
    apply_aircraft_reserve_transition_to_battlefield,
    resolve_aircraft_reserve_transition,
)
from warhammer40k_core.engine.army_mustering import ArmyMusteringError
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ModelPlacement,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
    geometry_model_for_placement,
    model_displacement_kind_from_token,
)
from warhammer40k_core.engine.catalog_desperate_escape import (
    catalog_forced_desperate_escape_sources_for_unit,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    catalog_advance_roll_reroll_permission_for_unit,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE, DiceRollManager
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import (
    apply_faction_resource_spend_effect,
    faction_resource_result_enriched_payload,
)
from warhammer40k_core.engine.fall_back_hooks import (
    FallBackEligibilityContext,
    FallBackEligibilityGrant,
    FallBackEligibilityHookRegistry,
)
from warhammer40k_core.engine.movement_end_surge_hooks import (
    MovementEndSurgeContext,
    MovementEndSurgeGrant,
    MovementEndSurgeHookRegistry,
)
from warhammer40k_core.engine.movement_keyword_effects import (
    movement_keywords_granted_by_effects,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalPayload,
    MovementProposalPayloadPayload,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindow as TriggeredReactionWindow,
)
from warhammer40k_core.engine.reaction_windows import (
    ReactionWindowKind,
)
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceHookRegistry,
)
from warhammer40k_core.engine.reserves import (
    DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES,
    LargeModelReservePlacementException,
    ReinforcementPlacement,
    ReserveKind,
    ReserveState,
    apply_reinforcement_placement_to_battlefield,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.runtime_modifiers import (
    MovementBudgetModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_for_unit,
)
from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagems import (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    CORE_RAPID_INGRESS_HANDLER_ID,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    FALL_BACK_MODE_CONTEXT_KEY,
    FALL_BACK_UNIT_CONTEXT_KEY,
    FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND,
    GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
    GENERIC_INGRESS_MOVE_HANDLER_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    JUST_FELL_BACK_UNIT_CONTEXT_KEY,
    SELECTED_TO_MOVE_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    StratagemTargetProposal,
    create_stratagem_use_decision_request,
    stratagem_decline_option,
    stratagem_target_proposal_from_index,
    stratagem_target_proposal_request_payload,
    stratagem_use_options_for_handler_from_index,
    stratagem_use_options_from_index,
    stratagem_window_declined_for_context,
)
from warhammer40k_core.engine.target_restriction_hooks import ChargeTargetRestrictionHookRegistry
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.transports import (
    CombatDisembark,
    DisembarkedUnitState,
    DisembarkModeKind,
    DisembarkResolution,
    DisembarkSelection,
    EmbarkResolution,
    EmbarkSelection,
    EmbarkSelectionPayload,
    TransportCargoState,
    TransportMovementStatus,
    TransportOperationViolation,
    TransportOperationViolationCode,
    TransportRestrictionOverride,
    TransportRestrictionOverridePayload,
    apply_combat_disembark_to_battlefield,
    apply_disembark_to_battlefield,
    apply_embark_to_battlefield,
    apply_transport_hazard_mortal_wounds,
    disembark_mode_kind_from_token,
    resolve_combat_disembark,
    resolve_disembark,
    resolve_embark,
    transport_movement_status_from_token,
)
from warhammer40k_core.engine.triggered_movement import (
    TriggeredMovementDescriptor,
    TriggeredMovementEligibleUnit,
    TriggeredMovementKind,
    triggered_movement_unit_selection_request,
)
from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike
from warhammer40k_core.engine.unit_coherency import (
    MovementRollbackRecord,
    MovementRollbackRecordPayload,
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    resolve_unit_movement_endpoint_coherency,
    unit_placement_coherency_result,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_move_completed_hooks import (
    UnitMoveCompletedMortalWoundHookRegistry,
    resolve_unit_move_completed_mortal_wound_hooks,
)
from warhammer40k_core.engine.unit_rule_effects import movement_bonus_inches_from_effects
from warhammer40k_core.geometry.pathing import (
    PathConstraintViolation,
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
    PathWitnessPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup

__all__ = (
    "AbilityCatalogIndex",
    "AdvanceEligibilityContext",
    "AdvanceEligibilityHookRegistry",
    "AdvanceMoveContext",
    "AdvanceMoveGrant",
    "AdvanceMoveGrantPayload",
    "AdvanceMoveHookRegistry",
    "AircraftMovementPolicy",
    "AircraftMovementPolicyPayload",
    "AircraftMovementViolation",
    "AircraftReserveTransitionReason",
    "ArmyCatalog",
    "ArmyMusteringError",
    "BattlePhase",
    "BattlePhaseKind",
    "BattlefieldPlacementKind",
    "BattlefieldRemovalKind",
    "BattlefieldScenario",
    "BattlefieldTransitionBatch",
    "BattlefieldTransitionBatchPayload",
    "CORE_FIRE_OVERWATCH_HANDLER_ID",
    "CORE_RAPID_INGRESS_HANDLER_ID",
    "Callable",
    "Characteristic",
    "ChargeTargetRestrictionHookRegistry",
    "CombatDisembark",
    "DECLINE_ADVANCE_MOVE_GRANT_OPTION_ID",
    "DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES",
    "DICE_REROLL_DECISION_TYPE",
    "DecisionController",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResult",
    "DeploymentZone",
    "DiceExpression",
    "DiceRollManager",
    "DiceRollSpec",
    "DiceRollSpecPayload",
    "DiceRollState",
    "DiceRollStatePayload",
    "DisembarkModeKind",
    "DisembarkResolution",
    "DisembarkSelection",
    "DisembarkedUnitState",
    "ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY",
    "EffectExpiration",
    "EmbarkResolution",
    "EmbarkSelection",
    "EmbarkSelectionPayload",
    "FALL_BACK_MODE_CONTEXT_KEY",
    "FALL_BACK_UNIT_CONTEXT_KEY",
    "FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND",
    "FallBackEligibilityContext",
    "FallBackEligibilityGrant",
    "FallBackEligibilityHookRegistry",
    "GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID",
    "GENERIC_INGRESS_MOVE_HANDLER_ID",
    "GENERIC_RULE_IR_STRATAGEM_HANDLER_ID",
    "GameLifecycleError",
    "GameLifecycleStage",
    "GeometryError",
    "HoverModeState",
    "IdentifierValidator",
    "JUST_FELL_BACK_UNIT_CONTEXT_KEY",
    "JsonValue",
    "LargeModelReservePlacementException",
    "LifecycleStatus",
    "LifecycleStatusKind",
    "MOVEMENT_PROPOSAL_DECISION_TYPE",
    "Mapping",
    "MappingProxyType",
    "MissionActionState",
    "MissionActionStatus",
    "MissionDeploymentZoneSource",
    "Model",
    "ModelDisplacementKind",
    "ModelDisplacementRecord",
    "ModelInstance",
    "ModelPlacement",
    "ModelRemovalRecord",
    "MovementBudgetModifierContext",
    "MovementEndSurgeContext",
    "MovementEndSurgeGrant",
    "MovementEndSurgeHookRegistry",
    "MovementLegalityContext",
    "MovementMode",
    "MovementProposalPayload",
    "MovementProposalPayloadPayload",
    "MovementProposalRequest",
    "MovementRollbackRecord",
    "MovementRollbackRecordPayload",
    "NotRequired",
    "ObjectiveMarker",
    "PLACEMENT_PROPOSAL_DECISION_TYPE",
    "PathConstraintViolation",
    "PathValidationResult",
    "PathValidationResultPayload",
    "PathWitness",
    "PathWitnessPayload",
    "PersistingEffect",
    "PlacementError",
    "PlacementProposalPayload",
    "PlacementProposalPayloadPayload",
    "Pose",
    "ProposalKind",
    "ProposalValidationResult",
    "ReactionQueue",
    "ReactionWindow",
    "ReactionWindowKind",
    "ReinforcementPlacement",
    "RerollComponentSelectionPolicy",
    "RerollPermission",
    "RerollPermissionPayload",
    "ReserveArrivalDistanceContext",
    "ReserveArrivalDistanceHookRegistry",
    "ReserveKind",
    "ReserveState",
    "RollModifier",
    "RollModifierPayload",
    "RulesetDescriptor",
    "RulesetDescriptorError",
    "RuntimeModifierRegistry",
    "SELECTED_TO_MOVE_UNIT_CONTEXT_KEY",
    "SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE",
    "STRATAGEM_DECISION_TYPE",
    "STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE",
    "Self",
    "StrEnum",
    "StratagemCatalogIndex",
    "StratagemCostModifierRegistry",
    "StratagemEligibilityContext",
    "StratagemTargetProposal",
    "TYPE_CHECKING",
    "TerrainFeatureDefinition",
    "TerrainPathLegalityResult",
    "TerrainPathLegalityResultPayload",
    "TerrainVolume",
    "TimingTriggerKind",
    "TimingWindow",
    "TimingWindowDescriptor",
    "TransportCargoState",
    "TransportMovementStatus",
    "TransportOperationViolation",
    "TransportOperationViolationCode",
    "TransportRestrictionOverride",
    "TransportRestrictionOverridePayload",
    "TriggeredMovementDescriptor",
    "TriggeredMovementEligibleUnit",
    "TriggeredMovementKind",
    "TriggeredReactionWindow",
    "TypedDict",
    "UnitCoherencyResult",
    "UnitCoherencyResultPayload",
    "UnitInstance",
    "UnitMoveCompletedMortalWoundHookRegistry",
    "UnitPlacement",
    "UnitPlacementPayload",
    "WeaponKeyword",
    "aircraft_model_ids_for_scenario",
    "annotations",
    "apply_aircraft_reserve_transition_to_battlefield",
    "apply_combat_disembark_to_battlefield",
    "apply_disembark_to_battlefield",
    "apply_embark_to_battlefield",
    "apply_faction_resource_spend_effect",
    "apply_reinforcement_placement_to_battlefield",
    "apply_roll_modifiers",
    "apply_transport_hazard_mortal_wounds",
    "cast",
    "catalog_advance_roll_reroll_permission_for_unit",
    "catalog_forced_desperate_escape_sources_for_unit",
    "combinations",
    "create_stratagem_use_decision_request",
    "dataclass",
    "disembark_mode_kind_from_token",
    "eleventh_edition_stratagem_index",
    "faction_resource_result_enriched_payload",
    "field",
    "geometry_model_for_placement",
    "interrupt_mission_action_for_battlefield_departure",
    "interrupt_mission_action_for_displacement",
    "math",
    "model_displacement_kind_from_token",
    "movement_bonus_inches_from_effects",
    "movement_keywords_granted_by_effects",
    "movement_mode_from_token",
    "objective_marker_endpoint_placement_violation",
    "parameterized_decision_option",
    "replace",
    "resolve_aircraft_reserve_transition",
    "resolve_combat_disembark",
    "resolve_disembark",
    "resolve_embark",
    "resolve_reserve_arrival",
    "resolve_unit_move_completed_mortal_wound_hooks",
    "resolve_unit_movement_endpoint_coherency",
    "source_backed_reroll_permission_for_unit",
    "stratagem_decline_option",
    "stratagem_target_proposal_from_index",
    "stratagem_target_proposal_request_payload",
    "stratagem_use_options_for_handler_from_index",
    "stratagem_use_options_from_index",
    "stratagem_window_declined_for_context",
    "transport_movement_status_from_token",
    "triggered_movement_unit_selection_request",
    "unit_has_deep_strike",
    "unit_placement_coherency_result",
    "validate_json_value",
)
