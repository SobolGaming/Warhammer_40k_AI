from __future__ import annotations

from typing import TypedDict

from warhammer40k_core.core.army_catalog import ArmyCatalogPayload
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptorPayload
from warhammer40k_core.engine.actions import MissionActionStatePayload
from warhammer40k_core.engine.aircraft import HoverModeStatePayload
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinitionPayload,
    ArmyMusterRequestPayload,
)
from warhammer40k_core.engine.battle_shock import BattleShockedUnitStatePayload
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeStatePayload
from warhammer40k_core.engine.command_points import (
    CommandPointLedgerPayload,
    CommandStepStatePayload,
)
from warhammer40k_core.engine.cult_ambush import CultAmbushMarkerPayload
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionSourcePayload,
    FeelNoPainSourcePayload,
)
from warhammer40k_core.engine.effects import PersistingEffectPayload
from warhammer40k_core.engine.faction_resources import FactionResourceLedgerPayload
from warhammer40k_core.engine.faction_rule_states import FactionRuleStatePayload
from warhammer40k_core.engine.fight_order import FightPhaseStatePayload
from warhammer40k_core.engine.mission_setup import MissionSetupPayload
from warhammer40k_core.engine.objective_control import ObjectiveControlRecordPayload
from warhammer40k_core.engine.phases.charge import ChargePhaseStatePayload
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitStatePayload,
    FellBackUnitStatePayload,
    MovementPhaseStatePayload,
)
from warhammer40k_core.engine.phases.shooting import (
    OutOfPhaseShootingStatePayload,
    ShootingPhaseStatePayload,
)
from warhammer40k_core.engine.prebattle_records import PreBattleActionRecordPayload
from warhammer40k_core.engine.reserves import (
    ReserveStatePayload,
    ReserveUnitPointValuePayload,
)
from warhammer40k_core.engine.return_on_death import PendingReturnOnDeathPayload
from warhammer40k_core.engine.scoring import (
    PrimaryObjectiveTurnStartStatePayload,
    PrimaryTerrainTrapStatePayload,
    PrimaryUnitDestructionStatePayload,
    ScoringWindowStatePayload,
    SecondaryMissionCardStatePayload,
    SecondaryObjectiveCleanseStatePayload,
    SecondaryTerrainPlunderStatePayload,
    SecondaryUnitDestructionStatePayload,
    TacticalSecondaryAchievementContextPayload,
    VictoryPointLedgerPayload,
)
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlStatePayload,
)
from warhammer40k_core.engine.stratagems import StratagemUseRecordPayload
from warhammer40k_core.engine.tracked_targets import TrackedTargetRecordPayload
from warhammer40k_core.engine.transports import (
    DisembarkedUnitStatePayload,
    TransportCargoStatePayload,
)
from warhammer40k_core.engine.triggered_movement import SurgeMoveStatePayload
from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupStatePayload
from warhammer40k_core.engine.unit_resources import UnitResourceLedgerPayload
from warhammer40k_core.engine.unit_state import StartingStrengthRecordPayload


class GameConfigPayload(TypedDict):
    game_id: str
    ruleset_descriptor: RulesetDescriptorPayload
    army_catalog: ArmyCatalogPayload
    army_muster_requests: list[ArmyMusterRequestPayload]
    allow_legacy_non_strict_rosters: bool
    player_ids: list[str]
    turn_order: list[str]
    fixed_secondary_mission_ids: list[str]
    tactical_secondary_draw_count: int
    max_lifecycle_transitions: int
    mission_setup: MissionSetupPayload | None
    reserve_unit_points: list[ReserveUnitPointValuePayload]


class SecondaryMissionChoicePayload(TypedDict):
    player_id: str
    mode: str
    fixed_mission_ids: list[str]


class TacticalSecondaryDrawPayload(TypedDict):
    player_id: str
    battle_round: int
    request_id: str
    result_id: str
    draw_count: int


class DedicatedTransportSetupConsequencePayload(TypedDict):
    player_id: str
    transport_unit_instance_id: str
    consequence_kind: str
    destroyed_battle_round: int
    source_id: str


class OneShotWeaponUseRecordPayload(TypedDict):
    model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    battle_round: int
    source_phase: str
    selection_id: str


class RangedAttackHistoryRecordPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    battle_round: int
    active_player_id: str
    phase: str
    request_id: str
    result_id: str


class GameStatePayload(TypedDict):
    game_id: str
    ruleset_descriptor_hash: str
    stage: str
    setup_sequence: list[str]
    battle_phase_sequence: list[str]
    setup_step_index: int | None
    battle_phase_index: int | None
    battle_round: int
    active_player_id: str | None
    player_ids: list[str]
    turn_order: list[str]
    decision_request_count: int
    tactical_secondary_draw_count: int
    command_step_state: CommandStepStatePayload | None
    command_point_ledgers: list[CommandPointLedgerPayload]
    victory_point_ledgers: list[VictoryPointLedgerPayload]
    faction_resource_ledgers: list[FactionResourceLedgerPayload]
    unit_resource_ledgers: list[UnitResourceLedgerPayload]
    stratagem_use_records: list[StratagemUseRecordPayload]
    faction_rule_states: list[FactionRuleStatePayload]
    army_definitions: list[ArmyDefinitionPayload]
    starting_strength_records: list[StartingStrengthRecordPayload]
    starting_attached_unit_records: list[StartingAttachedUnitRecordPayload]
    battlefield_state: BattlefieldRuntimeStatePayload | None
    mission_setup: MissionSetupPayload | None
    movement_phase_state: MovementPhaseStatePayload | None
    charge_phase_state: ChargePhaseStatePayload | None
    fight_phase_state: FightPhaseStatePayload | None
    shooting_phase_state: ShootingPhaseStatePayload | None
    out_of_phase_shooting_state: OutOfPhaseShootingStatePayload | None
    feel_no_pain_sources_by_model_id: dict[str, list[FeelNoPainSourcePayload]]
    feel_no_pain_decline_allowed_model_ids: list[str]
    destruction_reaction_sources_by_model_id: dict[str, list[DestructionReactionSourcePayload]]
    one_shot_weapon_use_records: list[OneShotWeaponUseRecordPayload]
    ranged_attack_history_records: list[RangedAttackHistoryRecordPayload]
    reserve_states: list[ReserveStatePayload]
    cult_ambush_markers: list[CultAmbushMarkerPayload]
    hover_mode_states: list[HoverModeStatePayload]
    transport_cargo_states: list[TransportCargoStatePayload]
    dedicated_transport_setup_consequences: list[DedicatedTransportSetupConsequencePayload]
    disembarked_unit_states: list[DisembarkedUnitStatePayload]
    advanced_unit_states: list[AdvancedUnitStatePayload]
    fell_back_unit_states: list[FellBackUnitStatePayload]
    surge_move_states: list[SurgeMoveStatePayload]
    battle_shocked_unit_ids: list[str]
    battle_shocked_unit_states: list[BattleShockedUnitStatePayload]
    objective_control_records: list[ObjectiveControlRecordPayload]
    sticky_objective_control_states: list[StickyObjectiveControlStatePayload]
    primary_objective_turn_start_states: list[PrimaryObjectiveTurnStartStatePayload]
    primary_terrain_trap_states: list[PrimaryTerrainTrapStatePayload]
    primary_unit_destruction_states: list[PrimaryUnitDestructionStatePayload]
    secondary_unit_destruction_states: list[SecondaryUnitDestructionStatePayload]
    secondary_objective_cleanse_states: list[SecondaryObjectiveCleanseStatePayload]
    secondary_terrain_plunder_states: list[SecondaryTerrainPlunderStatePayload]
    mission_action_states: list[MissionActionStatePayload]
    end_turn_cleanup_states: list[EndTurnCleanupStatePayload]
    scoring_window_states: list[ScoringWindowStatePayload]
    persisting_effects: list[PersistingEffectPayload]
    tracked_target_records: list[TrackedTargetRecordPayload]
    pending_return_on_death: list[PendingReturnOnDeathPayload]
    return_on_death_consumed_keys: list[str]
    secondary_mission_choices: list[SecondaryMissionChoicePayload]
    tactical_secondary_draws: list[TacticalSecondaryDrawPayload]
    prebattle_action_records: list[PreBattleActionRecordPayload]
    secondary_mission_card_states: list[SecondaryMissionCardStatePayload]
    tactical_secondary_achievement_contexts: list[TacticalSecondaryAchievementContextPayload]
    tactical_secondary_discard_cp_reward_window_ids: list[str]
    tactical_secondary_replacement_player_ids: list[str]


class StartingAttachedUnitRecordPayload(TypedDict):
    player_id: str
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: list[str]
    support_unit_instance_ids: list[str]
    component_unit_instance_ids: list[str]
    source_id: str
