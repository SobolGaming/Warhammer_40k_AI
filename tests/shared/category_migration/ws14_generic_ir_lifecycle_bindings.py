from __future__ import annotations

import json
from dataclasses import replace

import pytest

from tests.setup_completion_helpers import enter_battle_for_fixture
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import DatasheetKeywordSet
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword, WeaponProfile
from warhammer40k_core.engine.army_mustering import (
    ArmyMusterRequest,
    EnhancementAssignment,
    muster_army,
)
from warhammer40k_core.engine.battle_formation_hooks import BattleFormationRequestContext
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
from warhammer40k_core.engine.faction_content.warhammer_40000_11th.emperors_children import (
    july_2026 as emperors_children_july,
)
from warhammer40k_core.engine.faction_rule_execution import (
    FactionRuleExecutionContext,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
)
from warhammer40k_core.engine.fight_order import (
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    FightPhaseState,
    FightsFirstRegistry,
)
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    SecondaryMissionChoice,
    SecondaryMissionMode,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_legality import MovementCapabilitySet
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.runtime_modifiers import (
    HitRollModifierContext,
    MovementBudgetModifierContext,
    ObjectiveControlModifierContext,
    UnitCharacteristicModifierContext,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.source_backed_rerolls import (
    source_backed_reroll_permission_context_for_unit,
)
from warhammer40k_core.engine.stratagems import (
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    FALL_BACK_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    STRATAGEM_DECISION_TYPE,
    StratagemEligibilityContext,
    StratagemUseRecord,
    apply_stratagem_decision,
    request_stratagem_use_from_index,
)
from warhammer40k_core.engine.target_restriction_hooks import ShootingTargetRestrictionContext
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.triggered_movement import SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
from warhammer40k_core.engine.unit_rule_effects import (
    charge_transit_through_non_vehicle_monster_models_allowed,
    movement_transit_through_terrain_features_allowed,
)
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_court_of_the_phoenician_ir_support_2026_27 as court_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import july_faction_packs_2026_07
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_execution_2026_27 import (
    Phase17FExecutionStatus,
)

_MORE_DAKKA_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:orks:more-dakka:rule",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991002",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991003",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991004",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991005",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992002",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992003",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992004",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992005",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992006",
    "phase17f:phase17e:stratagem:orks:more-dakka:000009992007",
)


_MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS = (
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991002",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991003",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991004",
    "phase17f:phase17e:enhancement:orks:more-dakka:000009991005",
)


_SPECTACLE_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:emperors-children:spectacle-of-slaughter:rule",
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"),
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003"),
    ("phase17f:phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901002"),
    ("phase17f:phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901003"),
    ("phase17f:phase17e:stratagem:emperors-children:spectacle-of-slaughter:000010901004"),
)


_SPECTACLE_ENHANCEMENT_EXECUTION_IDS = (
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900002"),
    ("phase17f:phase17e:enhancement:emperors-children:spectacle-of-slaughter:000010900003"),
)


_COURT_GENERIC_EXECUTION_IDS = (
    "phase17f:phase17e:emperors-children:court-of-the-phoenician:rule",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655002",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655003",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655004",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655005",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655006",
    "phase17f:phase17e:stratagem:emperors-children:court-of-the-phoenician:000010655007",
)


_COURT_ENHANCEMENT_EXECUTION_IDS = (
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654002",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654003",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654004",
    "phase17f:phase17e:enhancement:emperors-children:court-of-the-phoenician:000010654005",
)


__all__: list[str] = []
__all__ += ["AbilityKind", "ArmyCatalog", "ArmyMusterRequest", "BattleFormationRequestContext"]
__all__ += ["CHARGE_FIGHTS_FIRST_EFFECT_KIND", "BattlePhase", "BattlePhaseKind", "Characteristic"]
__all__ += ["CharacteristicValue", "CommandPointGainStatus", "CommandPointSourceKind"]
__all__ += ["DESTROYED_TARGET_UNIT_CONTEXT_KEY", "DatasheetKeywordSet", "DecisionResult"]
__all__ += ["ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["EffectExpiration", "EnhancementAssignment", "EnhancementDefinition"]
__all__ += ["FALL_BACK_UNIT_CONTEXT_KEY", "FactionDefinition", "FactionRuleExecutionContext"]
__all__ += ["FactionRuleExecutionResult", "FactionRuleExecutionStatus", "FightPhaseState"]
__all__ += ["FightsFirstRegistry", "GameConfig", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecycleStage", "GameState", "HitRollModifierContext"]
__all__ += ["JUST_SHOT_UNIT_CONTEXT_KEY", "JsonValue", "LifecycleStatus", "LifecycleStatusKind"]
__all__ += ["MissionSetup", "ModelProfileSelection", "MovementBudgetModifierContext"]
__all__ += ["MovementCapabilitySet", "MovementMode", "ObjectiveControlModifierContext"]
__all__ += ["PersistingEffect", "Phase17FExecutionStatus", "Pose", "ReactionQueue"]
__all__ += ["RulesetDescriptor", "RuntimeContentBundle"]
__all__ += ["SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupStep", "ShootingPhaseState"]
__all__ += ["ShootingTargetRestrictionContext", "ShootingType", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemUseRecord", "TimingTriggerKind"]
__all__ += ["UnitCharacteristicModifierContext", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["WeaponProfile", "WeaponProfileModifierContext", "WoundRollModifierContext"]
__all__ += ["_COURT_ENHANCEMENT_EXECUTION_IDS", "_COURT_GENERIC_EXECUTION_IDS"]
__all__ += ["_MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS", "_MORE_DAKKA_GENERIC_EXECUTION_IDS"]
__all__ += ["_SPECTACLE_ENHANCEMENT_EXECUTION_IDS", "_SPECTACLE_GENERIC_EXECUTION_IDS"]
__all__ += ["apply_stratagem_decision", "chapter_approved_2026_27_mission_pack"]
__all__ += ["charge_transit_through_non_vehicle_monster_models_allowed", "court_ir"]
__all__ += ["create_deterministic_battlefield_scenario", "emperors_children_july"]
__all__ += ["enter_battle_for_fixture", "json", "july_faction_packs_2026_07"]
__all__ += ["movement_transit_through_terrain_features_allowed", "muster_army", "pytest"]
__all__ += ["replace", "request_stratagem_use_from_index"]
__all__ += ["source_backed_reroll_permission_context_for_unit"]
