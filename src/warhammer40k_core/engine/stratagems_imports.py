# ruff: noqa: F401,RUF022
# pyright: reportUnusedImport=false
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import (
    DiceExpression,
    DiceRollSpec,
    DiceRollSpecError,
    DiceRollState,
    DiceRollStatePayload,
    RerollComponentSelectionPolicy,
    RerollPermission,
)
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfile,
    WeaponProfile,
)
from warhammer40k_core.engine.battle_shock import (
    collect_battle_shock_test_requests,
    friendly_stratagem_target_permission,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointRefundStatus,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandPointSpendStatus,
)
from warhammer40k_core.engine.core_stratagem_effects import (
    GO_TO_GROUND_EFFECT_KIND,
    GO_TO_GROUND_INVULNERABLE_SAVE,
    SMOKESCREEN_EFFECT_KIND,
    SMOKESCREEN_HIT_ROLL_MODIFIER,
)
from warhammer40k_core.engine.cult_ambush import reserve_state_is_cult_ambush
from warhammer40k_core.engine.damage_allocation import (
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    MortalWoundApplication,
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    is_mortal_wound_feel_no_pain_request,
    mortal_wound_feel_no_pain_source_context,
    resolve_mortal_wound_feel_no_pain_decision,
    unit_owner_player_id,
)
from warhammer40k_core.engine.decision import (
    DICE_REROLL_DECISION_TYPE,
    DecisionError,
    DiceRollManager,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    FIGHTS_FIRST_EFFECT_KIND,
    FightActivationSelection,
    eligible_fight_contexts_for_player,
    legal_fight_types_for_context,
)
from warhammer40k_core.engine.movement_proposals import (
    MOVEMENT_PROPOSAL_DECISION_TYPE,
    PLACEMENT_PROPOSAL_DECISION_TYPE,
    MovementProposalRequest,
    PlacementProposalPayload,
    PlacementProposalPayloadPayload,
    ProposalKind,
    ProposalValidationResult,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.charge import (
    CHARGE_MOVE_ACTION,
    ChargeMoveProposal,
    ChargeMoveProposalPayload,
    charge_move_invalid_message,
    charge_move_violation_code,
    charge_move_violation_field,
    resolve_charge_move,
)
from warhammer40k_core.engine.phases.shooting import (
    request_out_of_phase_shooting_declaration,
    shooting_unit_can_select_to_shoot,
    shooting_unit_has_legal_declaration_against_targets,
)
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalRestrictionHookRegistry,
)
from warhammer40k_core.engine.reserve_arrival_restriction_resolution import (
    reserve_arrival_restriction_violations,
)
from warhammer40k_core.engine.reserves import (
    ReserveKind,
    ReserveState,
    ReserveStatus,
    StrategicReserveRule,
    apply_reinforcement_placement_to_battlefield,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_by_id
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
)
from warhammer40k_core.engine.shooting_targets import shooting_target_candidate_for_model
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    ShootingUnitSelectedGrantRegistry,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import (
    StratagemCostModificationResult,
    StratagemCostModifierContext,
    StratagemCostModifierRegistry,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    timing_trigger_kind_from_token,
)
from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_rule_effects import fire_overwatch_forbidden_by_effects
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import (
        StratagemHandlerRegistry,
    )
    from warhammer40k_core.engine.game_state import GameState

__all__ = (
    "ArmyCatalog",
    "AttackProfile",
    "BattlePhase",
    "BattlePhaseKind",
    "BattlefieldPlacementKind",
    "BattlefieldScenario",
    "CHARGE_MOVE_ACTION",
    "Characteristic",
    "CharacteristicValue",
    "ChargeMoveProposal",
    "ChargeMoveProposalPayload",
    "CommandPointGainStatus",
    "CommandPointRefundStatus",
    "CommandPointSourceKind",
    "CommandPointSpendResult",
    "CommandPointSpendStatus",
    "DICE_REROLL_DECISION_TYPE",
    "DamageProfile",
    "DecisionController",
    "DecisionError",
    "DecisionOption",
    "DecisionRequest",
    "DecisionResult",
    "DiceExpression",
    "DiceRollManager",
    "DiceRollSpec",
    "DiceRollSpecError",
    "DiceRollState",
    "DiceRollStatePayload",
    "EffectExpiration",
    "FIGHTS_FIRST_EFFECT_KIND",
    "FIRE_OVERWATCH_RULE_ID",
    "FightActivationSelection",
    "GO_TO_GROUND_EFFECT_KIND",
    "GO_TO_GROUND_INVULNERABLE_SAVE",
    "GameLifecycleError",
    "GameLifecycleStage",
    "IdentifierValidator",
    "JsonValue",
    "LifecycleStatus",
    "MOVEMENT_PROPOSAL_DECISION_TYPE",
    "Mapping",
    "MappingProxyType",
    "Model",
    "MortalWoundApplication",
    "MortalWoundApplicationProgress",
    "MovementMode",
    "MovementProposalRequest",
    "NotRequired",
    "ObjectiveControlContext",
    "ObjectiveControlResult",
    "ObjectiveControlTiming",
    "PARAMETERIZED_DECISION_OPTION_ID",
    "PLACEMENT_PROPOSAL_DECISION_TYPE",
    "PersistingEffect",
    "PlacementError",
    "PlacementProposalPayload",
    "PlacementProposalPayloadPayload",
    "ProposalKind",
    "ProposalValidationResult",
    "RangeProfile",
    "RerollComponentSelectionPolicy",
    "RerollPermission",
    "ReserveKind",
    "ReserveArrivalRestrictionHookRegistry",
    "ReserveState",
    "ReserveStatus",
    "RulesUnitPlacement",
    "RulesUnitView",
    "rules_unit_view_by_id",
    "RulesetDescriptor",
    "SELECT_FEEL_NO_PAIN_DECISION_TYPE",
    "SMOKESCREEN_EFFECT_KIND",
    "SMOKESCREEN_HIT_ROLL_MODIFIER",
    "SecondaryMissionCardMode",
    "SecondaryMissionCardState",
    "SecondaryMissionCardStatus",
    "Self",
    "ShootingUnitSelectedGrantRegistry",
    "StrEnum",
    "StratagemCostModificationResult",
    "StratagemCostModifierContext",
    "StratagemCostModifierRegistry",
    "StrategicReserveRule",
    "TYPE_CHECKING",
    "TerrainFeatureDefinition",
    "TimingTriggerKind",
    "TypedDict",
    "UnitInstance",
    "WeaponProfile",
    "annotations",
    "apply_reinforcement_placement_to_battlefield",
    "battle_phase_kind_from_token",
    "cast",
    "charge_move_invalid_message",
    "charge_move_violation_code",
    "charge_move_violation_field",
    "collect_battle_shock_test_requests",
    "continue_mortal_wound_application",
    "dataclass",
    "eligible_fight_contexts_for_player",
    "field",
    "fire_overwatch_forbidden_by_effects",
    "friendly_stratagem_target_permission",
    "geometry_model_for_placement",
    "is_mortal_wound_feel_no_pain_request",
    "legal_fight_types_for_context",
    "mortal_wound_feel_no_pain_source_context",
    "parameterized_decision_option",
    "replace",
    "request_out_of_phase_shooting_declaration",
    "reserve_state_is_cult_ambush",
    "reserve_arrival_restriction_violations",
    "resolve_charge_move",
    "resolve_mortal_wound_feel_no_pain_decision",
    "resolve_objective_control",
    "resolve_reserve_arrival",
    "shooting_target_candidate_for_model",
    "shooting_unit_can_select_to_shoot",
    "shooting_unit_has_legal_declaration_against_targets",
    "timing_trigger_kind_from_token",
    "unit_has_deep_strike",
    "unit_owner_player_id",
    "validate_json_value",
)
