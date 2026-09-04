from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Self, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.model_geometry_catalog import ModelGeometryCatalogRecord
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    RulesetDescriptor,
    SetupStepKind,
    battle_phase_kind_from_token,
    setup_step_kind_from_token,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine import game_config_validation as _config_validation
from warhammer40k_core.engine import game_state_phase_validation as _phase_validation
from warhammer40k_core.engine import game_state_queries as _queries
from warhammer40k_core.engine import mission_action_history as _action_history
from warhammer40k_core.engine import (
    mission_scoring_evidence_validation as _scoring_evidence_validation,
)
from warhammer40k_core.engine import mission_terrain as _mission_terrain
from warhammer40k_core.engine import model_destruction_cause_authority as _mdca
from warhammer40k_core.engine import objective_control_record_authority as _oc_authority
from warhammer40k_core.engine import physical_proposal_context as _physical_context
from warhammer40k_core.engine import primary_scoring_transaction_integrity as _primary_vp_integrity
from warhammer40k_core.engine import reserve_arrival_requirements as _arrival
from warhammer40k_core.engine import victory_point_award_service as _vp_awards
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.aircraft import HoverModeState
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyDefinitionPayload,
    ArmyMusteringError,
    ArmyMusterRequest,
    ArmyMusterRequestPayload,
)
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_shock import (
    BattleShockedUnitState,
    BattleShockResult,
)
from warhammer40k_core.engine.battle_shock_state import (
    record_battle_shock_result,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldRuntimeStatePayload,
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.catalog_rule_consumption import (
    record_core_deadly_demise_sources_for_unit,
    record_core_feel_no_pain_sources_for_unit,
    record_core_fights_first_source_for_unit,
)
from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
    PendingCatalogSelectedTargetBattleShockContinuation,
)
from warhammer40k_core.engine.command_battle_shock_history import (
    validate_command_battle_shock_state_snapshot,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainResult,
    CommandPointLedger,
    CommandPointRefundResult,
    CommandPointSourceKind,
    CommandPointSpendResult,
    CommandStepState,
    initial_command_point_ledgers,
)
from warhammer40k_core.engine.cult_ambush import (
    CultAmbushMarker,
)
from warhammer40k_core.engine.damage_allocation import (
    DestructionReactionSource,
    FeelNoPainSource,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.destruction_provenance import ModelDestructionAttribution
from warhammer40k_core.engine.effects import (
    EffectExpirationBoundary,
    PersistingEffect,
)
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.faction_resources import (
    FactionResourceLedger,
    FactionResourceResult,
    initial_faction_resource_ledgers,
    validate_faction_resource_ledgers,
)
from warhammer40k_core.engine.faction_rule_states import (
    FactionRuleState,
)
from warhammer40k_core.engine.fight_order import FightPhaseState
from warhammer40k_core.engine.final_scoring import FinalScoringResult
from warhammer40k_core.engine.game_config_geometry import (
    game_config_model_geometries_from_payload,
    validate_optional_game_config_model_geometries,
)
from warhammer40k_core.engine.game_state_payloads import (
    DedicatedTransportSetupConsequencePayload as DedicatedTransportSetupConsequencePayload,
)
from warhammer40k_core.engine.game_state_payloads import (
    GameConfigPayload as GameConfigPayload,
)
from warhammer40k_core.engine.game_state_payloads import (
    GameStatePayload as GameStatePayload,
)
from warhammer40k_core.engine.game_state_payloads import (
    OneShotWeaponUseRecordPayload as OneShotWeaponUseRecordPayload,
)
from warhammer40k_core.engine.game_state_payloads import (
    RangedAttackHistoryRecordPayload as RangedAttackHistoryRecordPayload,
)
from warhammer40k_core.engine.game_state_payloads import (
    SecondaryMissionChoicePayload as SecondaryMissionChoicePayload,
)
from warhammer40k_core.engine.game_state_payloads import (
    TacticalSecondaryDrawPayload as TacticalSecondaryDrawPayload,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_state_validation import (
    runtime_ruleset_descriptor_for_mission_setup,
    validate_battlefield_state_matches_mission_setup,
    validate_game_config_mission_setup,
    validate_game_state_mission_setup,
    validate_recorded_mission_setup,
)
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_scoring_policies_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.normal_move_history import NormalMoveState
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    SetupStep,
    game_lifecycle_stage_from_token,
)
from warhammer40k_core.engine.phases.charge import (
    ChargePhaseState,
)
from warhammer40k_core.engine.phases.movement import (
    AdvancedUnitState,
    FellBackUnitState,
    MovementPhaseState,
)
from warhammer40k_core.engine.phases.shooting import (
    OutOfPhaseShootingState,
    ShootingPhaseState,
)
from warhammer40k_core.engine.prebattle_records import (
    PreBattleActionRecord,
    PreBattleAlternationCursor,
)
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    prepare_primary_battlefield_departure,
    primary_battlefield_departure_states_from_payload,
    record_prepared_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_primary_battlefield_departure_event,
    record_primary_reserve_entry_mutation_event,
)
from warhammer40k_core.engine.primary_historical_evidence import (
    validate_primary_historical_evidence_state,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionProgressState
from warhammer40k_core.engine.primary_mission_state_runtime import (
    record_consecration_designation_for_destruction,
)
from warhammer40k_core.engine.primary_mission_state_validation import (
    validate_primary_mission_progress_state,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
    primary_reserve_entry_requirements,
    validate_accepted_primary_reserve_entry_provider,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PrimaryScoringBoundaryLifecycle,
    validate_primary_scoring_boundary_lifecycles,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringStateEvidence,
    validate_primary_scoring_state_evidence_records,
    validate_primary_scoring_state_evidence_records_authority,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    primary_rules_unit_turn_start_snapshots_from_payload,
    primary_rules_unit_turn_start_snapshots_with_created_unit,
    record_primary_rules_unit_turn_start_snapshot,
    record_primary_turn_start_evidence,
    validate_primary_objective_turn_start_states,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    build_primary_unit_destruction_state,
    record_primary_unit_destructions_for_end_turn_cleanup,
)
from warhammer40k_core.engine.ranged_attack_history_lineage import (
    ranged_attack_history_source_unit_ids as _ranged_attack_history_source_unit_ids,
)
from warhammer40k_core.engine.ranged_attack_history_lineage import (
    ranged_attack_history_unit_owner_ids as _ranged_attack_history_unit_owner_ids,
)
from warhammer40k_core.engine.reserve_state_queries import (
    reserve_state_for_rules_unit,
    unarrived_reserve_model_ids,
    validate_reserve_state_rules_unit,
)
from warhammer40k_core.engine.reserves import (
    ReserveDestructionResult,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
    ReserveUnitPointValue,
    StrategicReserveDeclaration,
    apply_reserve_destruction_to_battlefield,
    reserve_origin_from_token,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.return_on_death import (
    PendingReturnOnDeath,
)
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    ScoringWindowKind,
    ScoringWindowState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    TacticalSecondaryAchievementContext,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    initial_victory_point_ledgers,
    secondary_mission_card_mode_from_token,
)
from warhammer40k_core.engine.secondary_scoring_state_evidence import (
    SecondaryScoringStateEvidence,
    validate_secondary_scoring_state_evidence_records,
)
from warhammer40k_core.engine.secondary_unit_destruction_tracking import (
    secondary_unit_destruction_from_primary,
    validate_secondary_unit_destruction_states,
)
from warhammer40k_core.engine.starting_attached_units import (
    StartingAttachedUnitRecord,
)
from warhammer40k_core.engine.starting_attached_units import (
    starting_attached_unit_records_for_army as _starting_attached_unit_records_for_army,
)
from warhammer40k_core.engine.starting_attached_units import (
    validate_starting_attached_unit_records as _validate_starting_attached_unit_records,
)
from warhammer40k_core.engine.sticky_objective_control import (
    StickyObjectiveControlState,
    sticky_objective_control_state_is_expired,
)
from warhammer40k_core.engine.stratagems import StratagemUseRecord
from warhammer40k_core.engine.tracked_target_state import (
    active_tracked_target_for as _active_tracked_target_for,
)
from warhammer40k_core.engine.tracked_target_state import (
    attached_rules_unit_ids,
    attached_rules_unit_owner_ids,
    destroyed_attached_rules_unit_ids,
    validate_canonical_tracked_target_record,
)
from warhammer40k_core.engine.tracked_target_state import (
    tracked_targets_for_destroyed_unit as _tracked_targets_for_destroyed_unit,
)
from warhammer40k_core.engine.tracked_targets import (
    TrackedTargetOwnerScope,
    TrackedTargetRecord,
    TrackedTargetRole,
)
from warhammer40k_core.engine.transports import (
    DisembarkedUnitState,
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.turn_cleanup import (
    EndTurnCleanupState,
    resolve_end_turn_cleanup,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_keyword_queries import (
    unit_has_aircraft_hover_keywords as _unit_has_aircraft_hover_keywords,
)
from warhammer40k_core.engine.unit_keyword_queries import (
    unit_has_keyword as _unit_has_keyword,
)
from warhammer40k_core.engine.unit_resource_state import (
    seed_unit_resources,
    unit_resource_initializations_for_army,
    validate_unit_resource_ledgers,
)
from warhammer40k_core.engine.unit_resources import UnitResourceLedger
from warhammer40k_core.engine.unit_state import (
    StartingStrengthRecord,
)
from warhammer40k_core.engine.victory_point_policy_validation import (
    validate_victory_point_ledger_policy_sources,
    validate_victory_point_ledgers,
)
from warhammer40k_core.engine.weapon_instances import equipped_weapon_instance_by_id


class SecondaryMissionMode(StrEnum):
    FIXED = "fixed"
    TACTICAL = "tactical"


DEDICATED_TRANSPORT_EMPTY_STARTING_CARGO_CONSEQUENCE = (
    "empty_starting_cargo_destroyed_first_battle_round"
)
DEFAULT_MAX_LIFECYCLE_TRANSITIONS = 128


def _new_starting_attached_unit_records() -> list[StartingAttachedUnitRecord]:
    return []


def _new_secondary_mission_choices() -> list[SecondaryMissionChoice]:
    return []


def _new_tactical_secondary_draws() -> list[TacticalSecondaryDraw]:
    return []


def _new_prebattle_action_records() -> list[PreBattleActionRecord]:
    return []


def _new_advanced_unit_states() -> list[AdvancedUnitState]:
    return []


def _new_fell_back_unit_states() -> list[FellBackUnitState]:
    return []


def _new_normal_move_states() -> list[NormalMoveState]:
    return []


def _new_command_point_ledgers() -> list[CommandPointLedger]:
    return []


def _new_victory_point_ledgers() -> list[VictoryPointLedger]:
    return []


def _new_faction_resource_ledgers() -> list[FactionResourceLedger]:
    return []


def _new_unit_resource_ledgers() -> list[UnitResourceLedger]:
    return []


def _new_stratagem_use_records() -> list[StratagemUseRecord]:
    return []


def _new_faction_rule_states() -> list[FactionRuleState]:
    return []


def _new_starting_strength_records() -> list[StartingStrengthRecord]:
    return []


def _new_reserve_states() -> list[ReserveState]:
    return []


def _new_cult_ambush_markers() -> list[CultAmbushMarker]:
    return []


def _new_hover_mode_states() -> list[HoverModeState]:
    return []


def _new_transport_cargo_states() -> list[TransportCargoState]:
    return []


def _new_dedicated_transport_setup_consequences() -> list[DedicatedTransportSetupConsequence]:
    return []


def _new_disembarked_unit_states() -> list[DisembarkedUnitState]:
    return []


def _new_battle_shocked_unit_ids() -> list[str]:
    return []


def _new_battle_shocked_unit_states() -> list[BattleShockedUnitState]:
    return []


def _new_objective_control_records() -> list[ObjectiveControlRecord]:
    return []


def _new_sticky_objective_control_states() -> list[StickyObjectiveControlState]:
    return []


def _new_primary_objective_turn_start_states() -> list[PrimaryObjectiveTurnStartState]:
    return []


def _new_primary_rules_unit_turn_start_snapshots() -> list[PrimaryRulesUnitTurnStartSnapshot]:
    return []


def _new_primary_terrain_trap_states() -> list[PrimaryTerrainTrapState]:
    return []


def _new_primary_unit_destruction_states() -> list[PrimaryUnitDestructionState]:
    return []


def _new_primary_battlefield_departure_states() -> list[PrimaryBattlefieldDepartureState]:
    return []


def _new_secondary_unit_destruction_states() -> list[SecondaryUnitDestructionState]:
    return []


def _new_secondary_objective_cleanse_states() -> list[SecondaryObjectiveCleanseState]:
    return []


def _new_secondary_terrain_plunder_states() -> list[SecondaryTerrainPlunderState]:
    return []


def _new_mission_action_states() -> list[MissionActionState]:
    return []


def _new_end_turn_cleanup_states() -> list[EndTurnCleanupState]:
    return []


def _new_scoring_window_states() -> list[ScoringWindowState]:
    return []


def _new_army_definitions() -> list[ArmyDefinition]:
    return []


def _new_secondary_mission_card_states() -> list[SecondaryMissionCardState]:
    return []


def _new_tactical_secondary_achievement_contexts() -> list[TacticalSecondaryAchievementContext]:
    return []


def _new_tactical_secondary_discard_cp_reward_window_ids() -> list[str]:
    return []


def _new_tactical_secondary_replacement_player_ids() -> list[str]:
    return []


def _new_persisting_effects() -> list[PersistingEffect]:
    return []


def _new_tracked_target_records() -> list[TrackedTargetRecord]:
    return []


def _new_pending_return_on_death() -> list[PendingReturnOnDeath]:
    return []


def _new_return_on_death_consumed_keys() -> list[str]:
    return []


def _new_feel_no_pain_sources_by_model_id() -> dict[str, tuple[FeelNoPainSource, ...]]:
    return {}


def _new_feel_no_pain_decline_allowed_model_ids() -> list[str]:
    return []


def _new_destruction_reaction_sources_by_model_id() -> dict[
    str,
    tuple[DestructionReactionSource, ...],
]:
    return {}


def _new_one_shot_weapon_use_records() -> list[OneShotWeaponUseRecord]:
    return []


def _new_ranged_attack_history_records() -> list[RangedAttackHistoryRecord]:
    return []


@dataclass(frozen=True, slots=True)
class GameConfig:
    game_id: str
    ruleset_descriptor: RulesetDescriptor
    army_catalog: ArmyCatalog
    army_muster_requests: tuple[ArmyMusterRequest, ...]
    player_ids: tuple[str, ...]
    turn_order: tuple[str, ...]
    fixed_secondary_mission_ids: tuple[str, ...]
    tactical_secondary_draw_count: int = 2
    max_lifecycle_transitions: int = DEFAULT_MAX_LIFECYCLE_TRANSITIONS
    mission_setup: MissionSetup | None = None
    reserve_unit_points: tuple[ReserveUnitPointValue, ...] = ()
    allow_legacy_non_strict_rosters: bool = False
    model_geometries: tuple[ModelGeometryCatalogRecord, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_id",
            _validate_identifier("GameConfig game_id", self.game_id),
        )
        if type(self.ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("GameConfig ruleset_descriptor must be a RulesetDescriptor.")
        if type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("GameConfig army_catalog must be an ArmyCatalog.")
        object.__setattr__(
            self,
            "player_ids",
            _validate_identifier_tuple(
                "GameConfig player_ids",
                self.player_ids,
                min_length=2,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "army_muster_requests",
            _config_validation.validate_army_muster_requests(
                self.army_muster_requests,
                player_ids=self.player_ids,
            ),
        )
        object.__setattr__(
            self,
            "allow_legacy_non_strict_rosters",
            _validate_bool(
                "GameConfig allow_legacy_non_strict_rosters",
                self.allow_legacy_non_strict_rosters,
            ),
        )
        if not self.allow_legacy_non_strict_rosters:
            _config_validation.validate_strict_roster_legality_requests(self.army_muster_requests)
        object.__setattr__(
            self,
            "turn_order",
            _validate_turn_order(self.turn_order, player_ids=self.player_ids),
        )
        object.__setattr__(
            self,
            "fixed_secondary_mission_ids",
            _validate_identifier_tuple(
                "GameConfig fixed_secondary_mission_ids",
                self.fixed_secondary_mission_ids,
                min_length=2,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "tactical_secondary_draw_count",
            _validate_positive_int(
                "GameConfig tactical_secondary_draw_count",
                self.tactical_secondary_draw_count,
            ),
        )
        object.__setattr__(
            self,
            "max_lifecycle_transitions",
            _validate_positive_int(
                "GameConfig max_lifecycle_transitions",
                self.max_lifecycle_transitions,
            ),
        )
        mission_setup = _validate_optional_mission_setup(
            self.mission_setup,
            player_ids=self.player_ids,
        )
        validate_game_config_mission_setup(
            mission_setup,
            ruleset_descriptor=self.ruleset_descriptor,
        )
        _config_validation.validate_mission_setup_muster_dispositions(
            mission_setup,
            army_muster_requests=self.army_muster_requests,
        )
        object.__setattr__(self, "mission_setup", mission_setup)
        object.__setattr__(
            self,
            "reserve_unit_points",
            _validate_reserve_unit_points(
                self.reserve_unit_points,
                army_muster_requests=self.army_muster_requests,
            ),
        )
        object.__setattr__(
            self,
            "model_geometries",
            validate_optional_game_config_model_geometries(
                self.model_geometries,
                catalog=self.army_catalog,
            ),
        )
        _validate_lifecycle_sequences(self.ruleset_descriptor)

    def to_payload(self) -> GameConfigPayload:
        payload: GameConfigPayload = {
            "game_id": self.game_id,
            "ruleset_descriptor": self.ruleset_descriptor.to_payload(),
            "army_catalog": self.army_catalog.to_payload(),
            "army_muster_requests": [request.to_payload() for request in self.army_muster_requests],
            "allow_legacy_non_strict_rosters": self.allow_legacy_non_strict_rosters,
            "player_ids": list(self.player_ids),
            "turn_order": list(self.turn_order),
            "fixed_secondary_mission_ids": list(self.fixed_secondary_mission_ids),
            "tactical_secondary_draw_count": self.tactical_secondary_draw_count,
            "max_lifecycle_transitions": self.max_lifecycle_transitions,
            "mission_setup": (
                None if self.mission_setup is None else self.mission_setup.to_payload()
            ),
            "reserve_unit_points": [entry.to_payload() for entry in self.reserve_unit_points],
        }
        if self.model_geometries is not None:
            payload["model_geometries"] = [record.to_payload() for record in self.model_geometries]
        return payload

    @classmethod
    def from_payload(cls, payload: GameConfigPayload) -> Self:
        return cls(
            game_id=payload["game_id"],
            ruleset_descriptor=RulesetDescriptor.from_payload(payload["ruleset_descriptor"]),
            army_catalog=ArmyCatalog.from_payload(payload["army_catalog"]),
            army_muster_requests=tuple(
                _army_muster_request_from_payload(request)
                for request in payload["army_muster_requests"]
            ),
            allow_legacy_non_strict_rosters=payload["allow_legacy_non_strict_rosters"],
            player_ids=tuple(payload["player_ids"]),
            turn_order=tuple(payload["turn_order"]),
            fixed_secondary_mission_ids=tuple(payload["fixed_secondary_mission_ids"]),
            tactical_secondary_draw_count=payload["tactical_secondary_draw_count"],
            max_lifecycle_transitions=payload["max_lifecycle_transitions"],
            mission_setup=(
                None
                if payload["mission_setup"] is None
                else MissionSetup.from_payload(payload["mission_setup"])
            ),
            reserve_unit_points=tuple(
                ReserveUnitPointValue.from_payload(entry)
                for entry in payload["reserve_unit_points"]
            ),
            model_geometries=(
                None
                if "model_geometries" not in payload
                else game_config_model_geometries_from_payload(payload["model_geometries"])
            ),
        )


@dataclass(frozen=True, slots=True)
class SecondaryMissionChoice:
    player_id: str
    mode: SecondaryMissionMode
    fixed_mission_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("SecondaryMissionChoice player_id", self.player_id),
        )
        object.__setattr__(self, "mode", secondary_mission_mode_from_token(self.mode))
        fixed_mission_ids = _validate_identifier_tuple(
            "SecondaryMissionChoice fixed_mission_ids",
            self.fixed_mission_ids,
            min_length=0,
            sort_values=True,
        )
        if self.mode is SecondaryMissionMode.FIXED and len(fixed_mission_ids) != 2:
            raise GameLifecycleError(
                "SecondaryMissionChoice fixed mode requires exactly two fixed missions."
            )
        if self.mode is SecondaryMissionMode.TACTICAL and fixed_mission_ids:
            raise GameLifecycleError(
                "SecondaryMissionChoice tactical mode must not include fixed missions."
            )
        object.__setattr__(self, "fixed_mission_ids", fixed_mission_ids)

    def to_payload(self) -> SecondaryMissionChoicePayload:
        return {
            "player_id": self.player_id,
            "mode": self.mode.value,
            "fixed_mission_ids": list(self.fixed_mission_ids),
        }

    @classmethod
    def from_payload(cls, payload: SecondaryMissionChoicePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            mode=secondary_mission_mode_from_token(payload["mode"]),
            fixed_mission_ids=tuple(payload["fixed_mission_ids"]),
        )

    def to_public_payload(
        self,
        *,
        viewer_player_id: str,
        secondary_mission_choices_revealed: bool,
    ) -> dict[str, JsonValue]:
        if self.player_id != viewer_player_id and not secondary_mission_choices_revealed:
            return {
                "player_id": self.player_id,
                "selected": True,
                "hidden": True,
            }
        return {
            "player_id": self.player_id,
            "selected": True,
            "hidden": False,
            "mode": self.mode.value,
            "fixed_mission_ids": list(self.fixed_mission_ids),
        }


@dataclass(frozen=True, slots=True)
class TacticalSecondaryDraw:
    player_id: str
    battle_round: int
    request_id: str
    result_id: str
    draw_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("TacticalSecondaryDraw player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("TacticalSecondaryDraw battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("TacticalSecondaryDraw request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("TacticalSecondaryDraw result_id", self.result_id),
        )
        object.__setattr__(
            self,
            "draw_count",
            _validate_positive_int("TacticalSecondaryDraw draw_count", self.draw_count),
        )

    def to_payload(self) -> TacticalSecondaryDrawPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "draw_count": self.draw_count,
        }

    @classmethod
    def from_payload(cls, payload: TacticalSecondaryDrawPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
            draw_count=payload["draw_count"],
        )


@dataclass(frozen=True, slots=True)
class DedicatedTransportSetupConsequence:
    player_id: str
    transport_unit_instance_id: str
    consequence_kind: str
    destroyed_battle_round: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DedicatedTransportSetupConsequence player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DedicatedTransportSetupConsequence transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "consequence_kind",
            _validate_identifier(
                "DedicatedTransportSetupConsequence consequence_kind",
                self.consequence_kind,
            ),
        )
        if self.consequence_kind != DEDICATED_TRANSPORT_EMPTY_STARTING_CARGO_CONSEQUENCE:
            raise GameLifecycleError("DedicatedTransportSetupConsequence kind is unsupported.")
        object.__setattr__(
            self,
            "destroyed_battle_round",
            _validate_positive_int(
                "DedicatedTransportSetupConsequence destroyed_battle_round",
                self.destroyed_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DedicatedTransportSetupConsequence source_id", self.source_id),
        )

    @classmethod
    def empty_dedicated_transport(
        cls,
        *,
        player_id: str,
        transport_unit_instance_id: str,
        source_id: str,
    ) -> Self:
        return cls(
            player_id=player_id,
            transport_unit_instance_id=transport_unit_instance_id,
            consequence_kind=DEDICATED_TRANSPORT_EMPTY_STARTING_CARGO_CONSEQUENCE,
            destroyed_battle_round=1,
            source_id=source_id,
        )

    def to_payload(self) -> DedicatedTransportSetupConsequencePayload:
        return {
            "player_id": self.player_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "consequence_kind": self.consequence_kind,
            "destroyed_battle_round": self.destroyed_battle_round,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: DedicatedTransportSetupConsequencePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            consequence_kind=payload["consequence_kind"],
            destroyed_battle_round=payload["destroyed_battle_round"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class OneShotWeaponUseRecord:
    weapon_instance_id: str
    model_instance_id: str
    wargear_id: str
    weapon_profile_id: str
    battle_round: int
    source_phase: BattlePhase
    selection_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "weapon_instance_id",
            _validate_identifier(
                "OneShotWeaponUseRecord weapon_instance_id",
                self.weapon_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "OneShotWeaponUseRecord model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("OneShotWeaponUseRecord wargear_id", self.wargear_id),
        )
        object.__setattr__(
            self,
            "weapon_profile_id",
            _validate_identifier(
                "OneShotWeaponUseRecord weapon_profile_id",
                self.weapon_profile_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("OneShotWeaponUseRecord battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "source_phase",
            battle_phase_kind_from_token(self.source_phase),
        )
        object.__setattr__(
            self,
            "selection_id",
            _validate_identifier("OneShotWeaponUseRecord selection_id", self.selection_id),
        )

    @property
    def weapon_key(self) -> tuple[str, str, str, str]:
        return (
            self.model_instance_id,
            self.wargear_id,
            self.weapon_profile_id,
            self.weapon_instance_id,
        )

    def to_payload(self) -> OneShotWeaponUseRecordPayload:
        return {
            "weapon_instance_id": self.weapon_instance_id,
            "model_instance_id": self.model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile_id": self.weapon_profile_id,
            "battle_round": self.battle_round,
            "source_phase": self.source_phase.value,
            "selection_id": self.selection_id,
        }

    @classmethod
    def from_payload(cls, payload: OneShotWeaponUseRecordPayload) -> Self:
        return cls(
            weapon_instance_id=payload["weapon_instance_id"],
            model_instance_id=payload["model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile_id=payload["weapon_profile_id"],
            battle_round=payload["battle_round"],
            source_phase=battle_phase_kind_from_token(payload["source_phase"]),
            selection_id=payload["selection_id"],
        )


@dataclass(frozen=True, slots=True)
class RangedAttackHistoryRecord:
    player_id: str
    unit_instance_id: str
    battle_round: int
    active_player_id: str
    phase: BattlePhase
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("RangedAttackHistoryRecord player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "RangedAttackHistoryRecord unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("RangedAttackHistoryRecord battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier(
                "RangedAttackHistoryRecord active_player_id",
                self.active_player_id,
            ),
        )
        object.__setattr__(self, "phase", battle_phase_kind_from_token(self.phase))
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("RangedAttackHistoryRecord request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("RangedAttackHistoryRecord result_id", self.result_id),
        )

    @property
    def turn_key(self) -> tuple[int, str]:
        return (self.battle_round, self.active_player_id)

    def to_payload(self) -> RangedAttackHistoryRecordPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase": self.phase.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: RangedAttackHistoryRecordPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase=battle_phase_kind_from_token(payload["phase"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(slots=True)
class GameState:
    game_id: str
    ruleset_descriptor_hash: str
    stage: GameLifecycleStage
    setup_sequence: tuple[SetupStep, ...]
    battle_phase_sequence: tuple[BattlePhase, ...]
    player_ids: tuple[str, ...]
    turn_order: tuple[str, ...]
    tactical_secondary_draw_count: int
    rules_overlay_ids: tuple[str, ...] = ()
    setup_step_index: int | None = 0
    battle_phase_index: int | None = None
    battle_round: int = 0
    active_player_id: str | None = None
    decision_request_count: int = 0
    command_step_state: CommandStepState | None = None
    command_point_ledgers: list[CommandPointLedger] = field(
        default_factory=_new_command_point_ledgers
    )
    victory_point_ledgers: list[VictoryPointLedger] = field(
        default_factory=_new_victory_point_ledgers
    )
    faction_resource_ledgers: list[FactionResourceLedger] = field(
        default_factory=_new_faction_resource_ledgers
    )
    unit_resource_ledgers: list[UnitResourceLedger] = field(
        default_factory=_new_unit_resource_ledgers
    )
    stratagem_use_records: list[StratagemUseRecord] = field(
        default_factory=_new_stratagem_use_records
    )
    faction_rule_states: list[FactionRuleState] = field(default_factory=_new_faction_rule_states)
    army_definitions: list[ArmyDefinition] = field(default_factory=_new_army_definitions)
    starting_strength_records: list[StartingStrengthRecord] = field(
        default_factory=_new_starting_strength_records
    )
    starting_attached_unit_records: list[StartingAttachedUnitRecord] = field(
        default_factory=_new_starting_attached_unit_records
    )
    battlefield_state: BattlefieldRuntimeState | None = None
    mission_setup: MissionSetup | None = None
    movement_phase_state: MovementPhaseState | None = None
    pending_catalog_selected_target_battle_shock_continuation: (
        PendingCatalogSelectedTargetBattleShockContinuation | None
    ) = None
    charge_phase_state: ChargePhaseState | None = None
    fight_phase_state: FightPhaseState | None = None
    shooting_phase_state: ShootingPhaseState | None = None
    out_of_phase_shooting_state: OutOfPhaseShootingState | None = None
    feel_no_pain_sources_by_model_id: dict[str, tuple[FeelNoPainSource, ...]] = field(
        default_factory=_new_feel_no_pain_sources_by_model_id
    )
    feel_no_pain_decline_allowed_model_ids: list[str] = field(
        default_factory=_new_feel_no_pain_decline_allowed_model_ids
    )
    destruction_reaction_sources_by_model_id: dict[
        str,
        tuple[DestructionReactionSource, ...],
    ] = field(default_factory=_new_destruction_reaction_sources_by_model_id)
    one_shot_weapon_use_records: list[OneShotWeaponUseRecord] = field(
        default_factory=_new_one_shot_weapon_use_records
    )
    ranged_attack_history_records: list[RangedAttackHistoryRecord] = field(
        default_factory=_new_ranged_attack_history_records
    )
    model_destruction_cause_authorities: list[_mdca.ModelDestructionCauseAuthority] = field(
        default_factory=lambda: list[_mdca.ModelDestructionCauseAuthority]()
    )
    reserve_states: list[ReserveState] = field(default_factory=_new_reserve_states)
    cult_ambush_markers: list[CultAmbushMarker] = field(default_factory=_new_cult_ambush_markers)
    hover_mode_states: list[HoverModeState] = field(default_factory=_new_hover_mode_states)
    transport_cargo_states: list[TransportCargoState] = field(
        default_factory=_new_transport_cargo_states
    )
    dedicated_transport_setup_consequences: list[DedicatedTransportSetupConsequence] = field(
        default_factory=_new_dedicated_transport_setup_consequences
    )
    disembarked_unit_states: list[DisembarkedUnitState] = field(
        default_factory=_new_disembarked_unit_states
    )
    advanced_unit_states: list[AdvancedUnitState] = field(default_factory=_new_advanced_unit_states)
    fell_back_unit_states: list[FellBackUnitState] = field(
        default_factory=_new_fell_back_unit_states
    )
    normal_move_states: list[NormalMoveState] = field(default_factory=_new_normal_move_states)
    battle_shocked_unit_ids: list[str] = field(default_factory=_new_battle_shocked_unit_ids)
    battle_shocked_unit_states: list[BattleShockedUnitState] = field(
        default_factory=_new_battle_shocked_unit_states
    )
    objective_control_records: list[ObjectiveControlRecord] = field(
        default_factory=_new_objective_control_records
    )
    objective_control_record_authorities: list[_oc_authority.ObjectiveControlRecordAuthority] = (
        field(default_factory=lambda: list[_oc_authority.ObjectiveControlRecordAuthority]())
    )
    primary_scoring_state_evidence_records: list[PrimaryScoringStateEvidence] = field(
        default_factory=lambda: list[PrimaryScoringStateEvidence]()
    )
    secondary_scoring_state_evidence_records: list[SecondaryScoringStateEvidence] = field(
        default_factory=lambda: list[SecondaryScoringStateEvidence]()
    )
    primary_scoring_boundary_lifecycles: list[PrimaryScoringBoundaryLifecycle] = field(
        default_factory=lambda: list[PrimaryScoringBoundaryLifecycle]()
    )
    sticky_objective_control_states: list[StickyObjectiveControlState] = field(
        default_factory=_new_sticky_objective_control_states
    )
    primary_objective_turn_start_states: list[PrimaryObjectiveTurnStartState] = field(
        default_factory=_new_primary_objective_turn_start_states
    )
    primary_rules_unit_turn_start_snapshots: list[PrimaryRulesUnitTurnStartSnapshot] = field(
        default_factory=_new_primary_rules_unit_turn_start_snapshots
    )
    primary_terrain_trap_states: list[PrimaryTerrainTrapState] = field(
        default_factory=_new_primary_terrain_trap_states
    )
    primary_unit_destruction_states: list[PrimaryUnitDestructionState] = field(
        default_factory=_new_primary_unit_destruction_states
    )
    primary_battlefield_departure_states: list[PrimaryBattlefieldDepartureState] = field(
        default_factory=_new_primary_battlefield_departure_states
    )
    secondary_unit_destruction_states: list[SecondaryUnitDestructionState] = field(
        default_factory=_new_secondary_unit_destruction_states
    )
    secondary_objective_cleanse_states: list[SecondaryObjectiveCleanseState] = field(
        default_factory=_new_secondary_objective_cleanse_states
    )
    secondary_terrain_plunder_states: list[SecondaryTerrainPlunderState] = field(
        default_factory=_new_secondary_terrain_plunder_states
    )
    mission_action_states: list[MissionActionState] = field(
        default_factory=_new_mission_action_states
    )
    primary_mission_progress_state: PrimaryMissionProgressState = field(
        default_factory=PrimaryMissionProgressState.empty
    )
    end_turn_cleanup_states: list[EndTurnCleanupState] = field(
        default_factory=_new_end_turn_cleanup_states
    )
    scoring_window_states: list[ScoringWindowState] = field(
        default_factory=_new_scoring_window_states
    )
    persisting_effects: list[PersistingEffect] = field(default_factory=_new_persisting_effects)
    tracked_target_records: list[TrackedTargetRecord] = field(
        default_factory=_new_tracked_target_records
    )
    pending_return_on_death: list[PendingReturnOnDeath] = field(
        default_factory=_new_pending_return_on_death
    )
    return_on_death_consumed_keys: list[str] = field(
        default_factory=_new_return_on_death_consumed_keys
    )
    secondary_mission_choices: list[SecondaryMissionChoice] = field(
        default_factory=_new_secondary_mission_choices
    )
    tactical_secondary_draws: list[TacticalSecondaryDraw] = field(
        default_factory=_new_tactical_secondary_draws
    )
    prebattle_action_records: list[PreBattleActionRecord] = field(
        default_factory=_new_prebattle_action_records
    )
    prebattle_alternation_cursor: PreBattleAlternationCursor | None = None
    secondary_mission_card_states: list[SecondaryMissionCardState] = field(
        default_factory=_new_secondary_mission_card_states
    )
    tactical_secondary_achievement_contexts: list[TacticalSecondaryAchievementContext] = field(
        default_factory=_new_tactical_secondary_achievement_contexts
    )
    tactical_secondary_discard_cp_reward_window_ids: list[str] = field(
        default_factory=_new_tactical_secondary_discard_cp_reward_window_ids
    )
    tactical_secondary_replacement_player_ids: list[str] = field(
        default_factory=_new_tactical_secondary_replacement_player_ids
    )

    def __post_init__(self) -> None:
        self.game_id = _validate_identifier("GameState game_id", self.game_id)
        self.ruleset_descriptor_hash = _validate_descriptor_hash(
            "GameState ruleset_descriptor_hash",
            self.ruleset_descriptor_hash,
        )
        self.rules_overlay_ids = _validate_identifier_tuple(
            "GameState rules_overlay_ids", self.rules_overlay_ids, min_length=0, sort_values=True
        )
        self.stage = game_lifecycle_stage_from_token(self.stage)
        self.setup_sequence = _validate_setup_sequence(self.setup_sequence)
        self.battle_phase_sequence = _validate_battle_phase_sequence(self.battle_phase_sequence)
        self.player_ids = _validate_identifier_tuple(
            "GameState player_ids",
            self.player_ids,
            min_length=2,
            sort_values=False,
        )
        self.turn_order = _validate_turn_order(self.turn_order, player_ids=self.player_ids)
        self.tactical_secondary_draw_count = _validate_positive_int(
            "GameState tactical_secondary_draw_count",
            self.tactical_secondary_draw_count,
        )
        self.setup_step_index = _validate_optional_index(
            "GameState setup_step_index",
            self.setup_step_index,
            length=len(self.setup_sequence),
        )
        self.battle_phase_index = _validate_optional_index(
            "GameState battle_phase_index",
            self.battle_phase_index,
            length=len(self.battle_phase_sequence),
        )
        self.battle_round = _validate_non_negative_int(
            "GameState battle_round",
            self.battle_round,
        )
        self.active_player_id = _validate_optional_player_id(
            "GameState active_player_id",
            self.active_player_id,
            player_ids=self.player_ids,
        )
        self.decision_request_count = _validate_non_negative_int(
            "GameState decision_request_count",
            self.decision_request_count,
        )
        self.command_step_state = _validate_optional_command_step_state(self.command_step_state)
        self.command_point_ledgers = _validate_command_point_ledgers(
            self.command_point_ledgers,
            player_ids=self.player_ids,
        )
        self.victory_point_ledgers = validate_victory_point_ledgers(
            self.victory_point_ledgers,
            player_ids=self.player_ids,
        )
        self.faction_resource_ledgers = validate_faction_resource_ledgers(
            self.faction_resource_ledgers,
            player_ids=self.player_ids,
        )
        self.stratagem_use_records = _validate_stratagem_use_records(
            self.stratagem_use_records,
            player_ids=self.player_ids,
        )
        self.faction_rule_states = _validate_faction_rule_states(
            self.faction_rule_states,
            player_ids=self.player_ids,
        )
        self.army_definitions = _config_validation.validate_army_definitions(
            self.army_definitions,
            player_ids=self.player_ids,
        )
        self.unit_resource_ledgers = validate_unit_resource_ledgers(
            self.unit_resource_ledgers,
            player_ids=self.player_ids,
            army_definitions=self.army_definitions,
        )
        self.starting_strength_records = _validate_starting_strength_records(
            self.starting_strength_records,
            army_definitions=self.army_definitions,
            player_ids=self.player_ids,
        )
        self.starting_attached_unit_records = _validate_starting_attached_unit_records(
            self.starting_attached_unit_records,
            army_definitions=self.army_definitions,
            player_ids=self.player_ids,
            starting_strength_records=self.starting_strength_records,
        )
        self.battlefield_state = _validate_optional_battlefield_state(self.battlefield_state)
        self.mission_setup = _validate_optional_mission_setup(
            self.mission_setup,
            player_ids=self.player_ids,
        )
        validate_game_state_mission_setup(
            self.mission_setup,
            battlefield_state=self.battlefield_state,
        )
        _config_validation.validate_mission_setup_army_dispositions(
            self.mission_setup,
            army_definitions=self.army_definitions,
        )
        self.movement_phase_state = _phase_validation.validate_optional_movement_phase_state(
            self.movement_phase_state
        )
        self.pending_catalog_selected_target_battle_shock_continuation = (
            _phase_validation.validate_optional_catalog_selected_target_battle_shock_continuation(
                self.pending_catalog_selected_target_battle_shock_continuation
            )
        )
        self.charge_phase_state = _phase_validation.validate_optional_charge_phase_state(
            self.charge_phase_state
        )
        self.fight_phase_state = _phase_validation.validate_optional_fight_phase_state(
            self.fight_phase_state
        )
        self.shooting_phase_state = _phase_validation.validate_optional_shooting_phase_state(
            self.shooting_phase_state
        )
        self.out_of_phase_shooting_state = _validate_optional_out_of_phase_shooting_state(
            self.out_of_phase_shooting_state
        )
        self.feel_no_pain_sources_by_model_id = _validate_feel_no_pain_sources_by_model_id(
            self.feel_no_pain_sources_by_model_id,
            army_definitions=self.army_definitions,
        )
        self.feel_no_pain_decline_allowed_model_ids = list(
            _validate_feel_no_pain_decline_allowed_model_ids(
                self.feel_no_pain_decline_allowed_model_ids,
                source_model_ids=tuple(self.feel_no_pain_sources_by_model_id),
            )
        )
        self.destruction_reaction_sources_by_model_id = (
            _validate_destruction_reaction_sources_by_model_id(
                self.destruction_reaction_sources_by_model_id,
                army_definitions=self.army_definitions,
            )
        )
        self.one_shot_weapon_use_records = _validate_one_shot_weapon_use_records(
            self.one_shot_weapon_use_records,
            army_definitions=self.army_definitions,
        )
        self.ranged_attack_history_records = _validate_ranged_attack_history_records(
            self.ranged_attack_history_records,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            starting_attached_unit_records=self.starting_attached_unit_records,
            player_ids=self.player_ids,
        )
        self.model_destruction_cause_authorities = (
            _mdca.validate_model_destruction_cause_authorities(
                self.model_destruction_cause_authorities,
                game_id=self.game_id,
            )
        )
        self.reserve_states = _validate_reserve_states(
            self.reserve_states,
            player_ids=self.player_ids,
        )
        self.cult_ambush_markers = _validate_cult_ambush_markers(
            self.cult_ambush_markers,
            player_ids=self.player_ids,
        )
        self.hover_mode_states = _validate_hover_mode_states(
            self.hover_mode_states,
            player_ids=self.player_ids,
        )
        self.transport_cargo_states = _validate_transport_cargo_states(
            self.transport_cargo_states,
            player_ids=self.player_ids,
        )
        self.dedicated_transport_setup_consequences = (
            _validate_dedicated_transport_setup_consequences(
                self.dedicated_transport_setup_consequences,
                army_definitions=self.army_definitions,
                player_ids=self.player_ids,
            )
        )
        self.disembarked_unit_states = _validate_disembarked_unit_states(
            self.disembarked_unit_states,
            player_ids=self.player_ids,
        )
        self.advanced_unit_states = _validate_advanced_unit_states(
            self.advanced_unit_states,
            player_ids=self.player_ids,
        )
        self.fell_back_unit_states = _validate_fell_back_unit_states(
            self.fell_back_unit_states,
            player_ids=self.player_ids,
        )
        self.normal_move_states = _validate_normal_move_states(
            self.normal_move_states,
            player_ids=self.player_ids,
        )
        self.battle_shocked_unit_ids = list(
            _validate_identifier_tuple(
                "GameState battle_shocked_unit_ids",
                tuple(self.battle_shocked_unit_ids),
                min_length=0,
                sort_values=True,
            )
        )
        self.battle_shocked_unit_states = _validate_battle_shocked_unit_states(
            self.battle_shocked_unit_states,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            battle_shocked_unit_ids=tuple(self.battle_shocked_unit_ids),
            player_ids=self.player_ids,
        )
        self.objective_control_records = _validate_objective_control_records(
            self.objective_control_records,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.primary_scoring_state_evidence_records = (
            validate_primary_scoring_state_evidence_records(
                self.primary_scoring_state_evidence_records,
                game_id=self.game_id,
                mission_setup=self.mission_setup,
                turn_order=self.turn_order,
                objective_control_records=tuple(self.objective_control_records),
            )
        )
        self.secondary_scoring_state_evidence_records = (
            validate_secondary_scoring_state_evidence_records(
                self.secondary_scoring_state_evidence_records,
                game_id=self.game_id,
            )
        )
        validate_victory_point_ledger_policy_sources(
            self.victory_point_ledgers,
            mission_setup=self.mission_setup,
            objective_control_records=tuple(self.objective_control_records),
            primary_scoring_state_evidence_records=tuple(
                self.primary_scoring_state_evidence_records
            ),
            turn_order=self.turn_order,
            current_battle_round=self.battle_round,
            policies=(
                None
                if self.mission_setup is None
                else mission_scoring_policies_from_setup(self.mission_setup)
            ),
        )
        self.sticky_objective_control_states = _validate_sticky_objective_control_states(
            self.sticky_objective_control_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.objective_control_record_authorities = (
            _oc_authority.validate_objective_control_record_authorities(
                self.objective_control_record_authorities,
                state=self,
                records=tuple(self.objective_control_records),
            )
        )
        self.primary_objective_turn_start_states = validate_primary_objective_turn_start_states(
            self.primary_objective_turn_start_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
            known_objective_marker_ids=tuple(
                marker.objective_marker_id
                for marker in (
                    () if self.mission_setup is None else self.mission_setup.objective_markers
                )
            ),
        )
        self.mission_action_states = _validate_mission_action_states(
            self.mission_action_states,
            player_ids=self.player_ids,
        )
        if type(self.primary_mission_progress_state) is not PrimaryMissionProgressState:
            raise GameLifecycleError("GameState requires typed primary mission progress state.")
        self.primary_terrain_trap_states = (
            _scoring_evidence_validation.validate_primary_terrain_trap_states(
                self.primary_terrain_trap_states,
                game_id=self.game_id,
                player_ids=self.player_ids,
                mission_setup=self.mission_setup,
                mission_action_states=self.mission_action_states,
            )
        )
        (
            self.primary_rules_unit_turn_start_snapshots,
            self.primary_unit_destruction_states,
            self.primary_battlefield_departure_states,
        ) = validate_primary_historical_evidence_state(self)
        self.primary_mission_progress_state = validate_primary_mission_progress_state(self)
        validate_primary_scoring_state_evidence_records_authority(
            self.primary_scoring_state_evidence_records,
            state=self,
        )
        validate_primary_scoring_boundary_lifecycles(state=self)
        _primary_vp_integrity.validate_primary_transaction_semantics(state=self)
        self.secondary_unit_destruction_states = validate_secondary_unit_destruction_states(
            self.secondary_unit_destruction_states,
            state=self,
        )
        self.secondary_objective_cleanse_states = (
            _scoring_evidence_validation.validate_secondary_objective_cleanse_states(
                self.secondary_objective_cleanse_states,
                game_id=self.game_id,
                player_ids=self.player_ids,
                mission_setup=self.mission_setup,
                mission_action_states=self.mission_action_states,
            )
        )
        self.secondary_terrain_plunder_states = (
            _scoring_evidence_validation.validate_secondary_terrain_plunder_states(
                self.secondary_terrain_plunder_states,
                game_id=self.game_id,
                player_ids=self.player_ids,
                mission_setup=self.mission_setup,
                mission_action_states=self.mission_action_states,
            )
        )
        self.end_turn_cleanup_states = _validate_end_turn_cleanup_states(
            self.end_turn_cleanup_states,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.scoring_window_states = _validate_scoring_window_states(
            self.scoring_window_states,
            game_id=self.game_id,
        )
        self.persisting_effects = _validate_persisting_effects(
            self.persisting_effects,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        self.tracked_target_records = _validate_tracked_target_records(
            self.tracked_target_records,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        self.pending_return_on_death = _validate_pending_return_on_death(
            self.pending_return_on_death,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        self.return_on_death_consumed_keys = list(
            _validate_identifier_tuple(
                "GameState return_on_death_consumed_keys",
                tuple(self.return_on_death_consumed_keys),
                min_length=0,
                sort_values=True,
            )
        )
        self.secondary_mission_choices = _validate_secondary_choices(
            self.secondary_mission_choices,
            player_ids=self.player_ids,
        )
        self.tactical_secondary_draws = _validate_tactical_draws(
            self.tactical_secondary_draws,
            player_ids=self.player_ids,
        )
        self.prebattle_action_records = _validate_prebattle_action_records(
            self.prebattle_action_records,
            game_id=self.game_id,
            player_ids=self.player_ids,
        )
        self.prebattle_alternation_cursor = _validate_prebattle_alternation_cursor(
            self.prebattle_alternation_cursor,
            records=self.prebattle_action_records,
            game_id=self.game_id,
            turn_order=self.turn_order,
        )
        self.secondary_mission_card_states = _validate_secondary_mission_card_states(
            self.secondary_mission_card_states,
            player_ids=self.player_ids,
        )
        from warhammer40k_core.engine.secondary_scoring_state_evidence_authority import (
            validate_secondary_scoring_state_evidence_records_authority,
        )

        validate_secondary_scoring_state_evidence_records_authority(
            self.secondary_scoring_state_evidence_records,
            state=self,
        )
        _vp_awards.validate_secondary_transaction_semantics(state=self)
        self.tactical_secondary_achievement_contexts = (
            _validate_tactical_secondary_achievement_contexts(
                self.tactical_secondary_achievement_contexts,
                game_id=self.game_id,
                player_ids=self.player_ids,
            )
        )
        self.tactical_secondary_discard_cp_reward_window_ids = list(
            _validate_identifier_tuple(
                "GameState tactical_secondary_discard_cp_reward_window_ids",
                tuple(self.tactical_secondary_discard_cp_reward_window_ids),
                min_length=0,
                sort_values=True,
            )
        )
        self.tactical_secondary_replacement_player_ids = list(
            _validate_identifier_tuple(
                "GameState tactical_secondary_replacement_player_ids",
                tuple(self.tactical_secondary_replacement_player_ids),
                min_length=0,
                sort_values=True,
            )
        )
        for player_id in self.tactical_secondary_replacement_player_ids:
            if player_id not in self.player_ids:
                raise GameLifecycleError(
                    "GameState tactical_secondary_replacement_player_ids must be player IDs."
                )
        _validate_hover_mode_state_references(self)
        _validate_state_stage_indexes(self)
        validate_command_battle_shock_state_snapshot(state=self)

    @classmethod
    def from_config(cls, config: GameConfig) -> Self:
        return cls(
            game_id=config.game_id,
            ruleset_descriptor_hash=config.ruleset_descriptor.descriptor_hash,
            rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids,
            stage=GameLifecycleStage.SETUP,
            setup_sequence=tuple(config.ruleset_descriptor.setup_sequence.steps),
            battle_phase_sequence=tuple(config.ruleset_descriptor.battle_phase_sequence.phases),
            player_ids=config.player_ids,
            turn_order=config.turn_order,
            tactical_secondary_draw_count=config.tactical_secondary_draw_count,
            command_point_ledgers=initial_command_point_ledgers(config.player_ids),
            victory_point_ledgers=initial_victory_point_ledgers(config.player_ids),
            faction_resource_ledgers=initial_faction_resource_ledgers(config.player_ids),
            unit_resource_ledgers=[],
            mission_setup=config.mission_setup,
        )

    @property
    def current_setup_step(self) -> SetupStep | None:
        if self.setup_step_index is None:
            return None
        return self.setup_sequence[self.setup_step_index]

    @property
    def current_battle_phase(self) -> BattlePhase | None:
        if self.battle_phase_index is None:
            return None
        return self.battle_phase_sequence[self.battle_phase_index]

    def effective_active_player_id(self) -> str | None:
        out_of_phase_shooting = self.out_of_phase_shooting_state
        if out_of_phase_shooting is not None:
            return out_of_phase_shooting.player_id
        shooting_state = self.shooting_phase_state
        if shooting_state is not None and shooting_state.active_selection is not None:
            return shooting_state.active_selection.player_id
        charge_state = self.charge_phase_state
        if charge_state is not None and charge_state.active_selection is not None:
            return charge_state.active_selection.player_id
        movement_state = self.movement_phase_state
        if movement_state is not None and movement_state.active_selection is not None:
            return movement_state.active_selection.player_id
        return self.active_player_id

    def effective_opposing_player_ids(self) -> tuple[str, ...]:
        return _queries.effective_opposing_player_ids(self)

    def next_decision_request_id(self) -> str:
        self.decision_request_count += 1
        return f"decision-request-{self.decision_request_count:06d}"

    def physical_proposal_context_hash(self) -> str:
        return _physical_context.physical_proposal_context_hash_for_state(self)

    def record_model_feel_no_pain_sources(
        self,
        *,
        model_instance_id: str,
        sources: tuple[FeelNoPainSource, ...],
        decline_allowed: bool = False,
    ) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        source_tuple = _validate_feel_no_pain_source_tuple(
            "Feel No Pain sources",
            sources,
        )
        if type(decline_allowed) is not bool:
            raise GameLifecycleError("Feel No Pain decline_allowed must be a bool.")
        updated_sources = dict(self.feel_no_pain_sources_by_model_id)
        updated_sources[model_id] = source_tuple
        self.feel_no_pain_sources_by_model_id = _validate_feel_no_pain_sources_by_model_id(
            updated_sources,
            army_definitions=self.army_definitions,
        )
        decline_ids = set(self.feel_no_pain_decline_allowed_model_ids)
        if decline_allowed:
            decline_ids.add(model_id)
        else:
            decline_ids.discard(model_id)
        self.feel_no_pain_decline_allowed_model_ids = list(
            _validate_feel_no_pain_decline_allowed_model_ids(
                tuple(decline_ids),
                source_model_ids=tuple(self.feel_no_pain_sources_by_model_id),
            )
        )

    def clear_model_feel_no_pain_sources(self, *, model_instance_id: str) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        updated_sources = dict(self.feel_no_pain_sources_by_model_id)
        updated_sources.pop(model_id, None)
        self.feel_no_pain_sources_by_model_id = _validate_feel_no_pain_sources_by_model_id(
            updated_sources,
            army_definitions=self.army_definitions,
        )
        self.feel_no_pain_decline_allowed_model_ids = list(
            _validate_feel_no_pain_decline_allowed_model_ids(
                tuple(
                    model_id_value
                    for model_id_value in self.feel_no_pain_decline_allowed_model_ids
                    if model_id_value != model_id
                ),
                source_model_ids=tuple(self.feel_no_pain_sources_by_model_id),
            )
        )

    def feel_no_pain_sources_for_model(
        self,
        *,
        model_instance_id: str,
    ) -> tuple[FeelNoPainSource, ...]:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        return self.feel_no_pain_sources_by_model_id.get(model_id, ())

    def feel_no_pain_decline_allowed_for_model(
        self,
        *,
        model_instance_id: str,
    ) -> bool:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        return model_id in self.feel_no_pain_decline_allowed_model_ids

    def one_shot_weapon_available(
        self,
        *,
        weapon_instance_id: str,
        model_instance_id: str,
        wargear_id: str,
        weapon_profile_id: str,
    ) -> bool:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        key = (
            model_id,
            _validate_identifier("wargear_id", wargear_id),
            _validate_identifier("weapon_profile_id", weapon_profile_id),
            _validate_identifier("weapon_instance_id", weapon_instance_id),
        )
        return key not in {record.weapon_key for record in self.one_shot_weapon_use_records}

    def one_shot_weapon_use_record(
        self,
        *,
        weapon_instance_id: str,
        model_instance_id: str,
        wargear_id: str,
        weapon_profile_id: str,
    ) -> OneShotWeaponUseRecord | None:
        key = (
            _validate_identifier("model_instance_id", model_instance_id),
            _validate_identifier("wargear_id", wargear_id),
            _validate_identifier("weapon_profile_id", weapon_profile_id),
            _validate_identifier("weapon_instance_id", weapon_instance_id),
        )
        for record in self.one_shot_weapon_use_records:
            if record.weapon_key == key:
                return record
        return None

    def record_one_shot_weapon_selected(
        self,
        *,
        weapon_instance_id: str,
        model_instance_id: str,
        wargear_id: str,
        weapon_profile_id: str,
        source_phase: BattlePhase,
        selection_id: str,
    ) -> OneShotWeaponUseRecord:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        record = OneShotWeaponUseRecord(
            weapon_instance_id=weapon_instance_id,
            model_instance_id=model_id,
            wargear_id=wargear_id,
            weapon_profile_id=weapon_profile_id,
            battle_round=self.battle_round,
            source_phase=source_phase,
            selection_id=selection_id,
        )
        if (
            self.one_shot_weapon_use_record(
                weapon_instance_id=record.weapon_instance_id,
                model_instance_id=record.model_instance_id,
                wargear_id=record.wargear_id,
                weapon_profile_id=record.weapon_profile_id,
            )
            is not None
        ):
            raise GameLifecycleError("One Shot weapon has already been selected this battle.")
        self.one_shot_weapon_use_records = _validate_one_shot_weapon_use_records(
            [*self.one_shot_weapon_use_records, record],
            army_definitions=self.army_definitions,
        )
        return record

    def record_ranged_attack_history(self, record: RangedAttackHistoryRecord) -> None:
        if type(record) is not RangedAttackHistoryRecord:
            raise GameLifecycleError(
                "GameState ranged attack history requires RangedAttackHistoryRecord."
            )
        self.ranged_attack_history_records = _validate_ranged_attack_history_records(
            [*self.ranged_attack_history_records, record],
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            starting_attached_unit_records=self.starting_attached_unit_records,
            player_ids=self.player_ids,
        )

    def unit_made_ranged_attacks_current_or_previous_turn(
        self,
        *,
        unit_instance_id: str,
    ) -> bool:
        requested_unit_id = _validate_identifier(
            "Ranged attack history unit_instance_id",
            unit_instance_id,
        )
        owner_ids_by_unit_id = _ranged_attack_history_unit_owner_ids(
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            starting_attached_unit_records=self.starting_attached_unit_records,
        )
        if owner_ids_by_unit_id and requested_unit_id not in owner_ids_by_unit_id:
            raise GameLifecycleError("Ranged attack history unit_instance_id is unknown.")
        relevant_turn_keys = set(self._current_and_previous_player_turn_keys())
        if not relevant_turn_keys:
            return False
        history_source_unit_ids = _ranged_attack_history_source_unit_ids(
            unit_instance_id=requested_unit_id,
            starting_attached_unit_records=self.starting_attached_unit_records,
        )
        return any(
            record.unit_instance_id in history_source_unit_ids
            and record.turn_key in relevant_turn_keys
            for record in self.ranged_attack_history_records
        )

    def _current_and_previous_player_turn_keys(self) -> tuple[tuple[int, str], ...]:
        if self.active_player_id is None:
            return ()
        if self.battle_round < 1:
            return ()
        current_key = (self.battle_round, self.active_player_id)
        active_index = self.turn_order.index(self.active_player_id)
        if active_index > 0:
            previous_key = (self.battle_round, self.turn_order[active_index - 1])
            return (current_key, previous_key)
        previous_round = self.battle_round - 1
        if previous_round < 1:
            return (current_key,)
        return (current_key, (previous_round, self.turn_order[-1]))

    def record_model_destruction_reaction_sources(
        self,
        *,
        model_instance_id: str,
        sources: tuple[DestructionReactionSource, ...],
    ) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        source_tuple = _validate_destruction_reaction_source_tuple(
            "Destruction reaction sources",
            sources,
        )
        if not source_tuple:
            raise GameLifecycleError("Destruction reaction registration requires sources.")
        updated_sources = dict(self.destruction_reaction_sources_by_model_id)
        updated_sources[model_id] = source_tuple
        self.destruction_reaction_sources_by_model_id = (
            _validate_destruction_reaction_sources_by_model_id(
                updated_sources,
                army_definitions=self.army_definitions,
            )
        )

    def clear_model_destruction_reaction_sources(self, *, model_instance_id: str) -> None:
        model_id = _validate_model_instance_id_for_state(
            state=self,
            model_instance_id=model_instance_id,
        )
        updated_sources = dict(self.destruction_reaction_sources_by_model_id)
        updated_sources.pop(model_id, None)
        self.destruction_reaction_sources_by_model_id = (
            _validate_destruction_reaction_sources_by_model_id(
                updated_sources,
                army_definitions=self.army_definitions,
            )
        )

    def destruction_reaction_sources_for_model(
        self,
        *,
        model_instance_id: str,
    ) -> tuple[DestructionReactionSource, ...]:
        model_id = _validate_identifier("model_instance_id", model_instance_id)
        return self.destruction_reaction_sources_by_model_id.get(model_id, ())

    def replace_model_destruction_cause_authorities(
        self, authorities: list[_mdca.ModelDestructionCauseAuthority]
    ) -> None:
        self.model_destruction_cause_authorities = (
            _mdca.validate_model_destruction_cause_authorities(authorities, game_id=self.game_id)
        )

    def complete_current_setup_step(self) -> SetupStep:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can complete setup steps only during setup.")
        current = self.current_setup_step
        if current is None or self.setup_step_index is None:
            raise GameLifecycleError("GameState has no current setup step.")
        if self.setup_step_index + 1 < len(self.setup_sequence):
            self.setup_step_index += 1
            return current
        raise GameLifecycleError("Final setup step completion requires the setup completion gate.")

    def complete_final_setup_step_before_battle(self) -> SetupStep:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can complete setup steps only during setup.")
        current = self.current_setup_step
        if current is None or self.setup_step_index is None:
            raise GameLifecycleError("GameState has no current setup step.")
        if self.setup_step_index + 1 < len(self.setup_sequence):
            raise GameLifecycleError("GameState final setup gate requires the final setup step.")
        self.setup_step_index = None
        return current

    def enter_battle(self) -> None:
        if self.stage is not GameLifecycleStage.SETUP:
            raise GameLifecycleError("GameState can enter battle only from setup.")
        self.stage = GameLifecycleStage.BATTLE
        self.battle_round = 1
        self.active_player_id = self.turn_order[0]
        self.battle_phase_index = 0
        self._expire_persisting_effects_at_current_battle_round_start()
        self._expire_persisting_effects_at_current_turn_start()
        self._record_primary_objective_turn_start_boundary_if_available()
        self._expire_persisting_effects_at_current_phase_start()

    def advance_to_next_battle_phase(
        self,
        *,
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
        event_log: EventLog | None = None,
    ) -> BattlePhase:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can advance battle phases only during battle.")
        if self.battle_phase_index is None:
            raise GameLifecycleError("GameState has no current battle phase.")
        completed_phase = self.battle_phase_sequence[self.battle_phase_index]
        completed_player_id = self.active_player_id
        if completed_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        phase_end_record = self.determine_current_phase_end_objective_control(
            runtime_modifier_registry=runtime_modifier_registry,
        )
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_end(
                battle_round=self.battle_round,
                phase=completed_phase,
                player_id=completed_player_id,
            )
        )
        self._score_objective_control_boundary(phase_end_record, event_log=event_log)
        if self.battle_phase_index + 1 < len(self.battle_phase_sequence):
            if completed_phase is BattlePhase.COMMAND:
                self.command_step_state = None
            if completed_phase is BattlePhase.MOVEMENT:
                self.movement_phase_state = None
            if completed_phase is BattlePhase.SHOOTING:
                self.shooting_phase_state = None
            if completed_phase is BattlePhase.CHARGE:
                self.charge_phase_state = None
            if completed_phase is BattlePhase.FIGHT:
                self.fight_phase_state = None
            self.out_of_phase_shooting_state = None
            self.battle_phase_index += 1
            self._expire_persisting_effects_at_current_phase_start()
            return completed_phase
        turn_end_record = self.prepare_current_turn_end_boundary(
            completed_phase=completed_phase,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        self._score_objective_control_boundary(turn_end_record, event_log=event_log)
        if completed_phase is BattlePhase.COMMAND:
            self.command_step_state = None
        if completed_phase is BattlePhase.MOVEMENT:
            self.movement_phase_state = None
        if completed_phase is BattlePhase.SHOOTING:
            self.shooting_phase_state = None
        if completed_phase is BattlePhase.CHARGE:
            self.charge_phase_state = None
        if completed_phase is BattlePhase.FIGHT:
            self.fight_phase_state = None
        self.out_of_phase_shooting_state = None
        completed_round = self.battle_round
        battle_round_ended = self._active_player_is_last_in_round(completed_player_id)
        if battle_round_ended:
            self.expire_persisting_effects_at_boundary(
                EffectExpirationBoundary.battle_round_end(battle_round=completed_round)
            )
            self._resolve_unarrived_reserve_destruction_boundary(end_of_battle=False)
            self._record_scoring_windows_boundary(ScoringWindowKind.END_OF_ROUND)
        if battle_round_ended and self._game_ends_after_completed_round(completed_round):
            self._resolve_unarrived_reserve_destruction_boundary(end_of_battle=True)
            self._record_scoring_windows_boundary(ScoringWindowKind.END_OF_GAME)
            self._score_end_of_battle_primary_boundary(turn_end_record, event_log=event_log)
            self.expire_persisting_effects_at_boundary(EffectExpirationBoundary.battle_end())
            self.stage = GameLifecycleStage.COMPLETE
            self.battle_phase_index = None
            self.active_player_id = None
            self.command_step_state = None
            self.movement_phase_state = None
            self.shooting_phase_state = None
            self.charge_phase_state = None
            self.fight_phase_state = None
            self.out_of_phase_shooting_state = None
            return completed_phase
        self.battle_phase_index = 0
        self._advance_active_player_after_completed_turn()
        if battle_round_ended:
            self._expire_persisting_effects_at_current_battle_round_start()
        self._expire_persisting_effects_at_current_turn_start()
        self._record_primary_objective_turn_start_boundary_if_available(
            runtime_modifier_registry=runtime_modifier_registry
        )
        self._expire_persisting_effects_at_current_phase_start()
        return completed_phase

    def determine_current_phase_end_objective_control(
        self,
        *,
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ) -> ObjectiveControlRecord:
        return _queries.determine_current_phase_end_objective_control(
            state=self,
            runtime_modifier_registry=runtime_modifier_registry,
        )

    def record_secondary_mission_choice(self, choice: SecondaryMissionChoice) -> None:
        if choice.player_id not in self.player_ids:
            raise GameLifecycleError("SecondaryMissionChoice player_id is not in this game.")
        if self.secondary_mission_choice_for_player(choice.player_id) is not None:
            raise GameLifecycleError("SecondaryMissionChoice already exists for player.")
        self.secondary_mission_choices.append(choice)
        self.secondary_mission_choices.sort(key=lambda stored: stored.player_id)
        self.record_fixed_secondary_cards_for_choice(choice)

    def secondary_mission_choice_for_player(
        self,
        player_id: str,
    ) -> SecondaryMissionChoice | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for choice in self.secondary_mission_choices:
            if choice.player_id == requested_player_id:
                return choice
        return None

    def secondary_mission_choices_are_revealed(self) -> bool:
        return not self.missing_secondary_mission_player_ids()

    def missing_secondary_mission_player_ids(self) -> tuple[str, ...]:
        selected = {choice.player_id for choice in self.secondary_mission_choices}
        return tuple(player_id for player_id in self.player_ids if player_id not in selected)

    def record_army_definition(self, army_definition: ArmyDefinition) -> None:
        if type(army_definition) is not ArmyDefinition:
            raise GameLifecycleError("GameState army_definition must be an ArmyDefinition.")
        if army_definition.player_id not in self.player_ids:
            raise GameLifecycleError("ArmyDefinition player_id is not in this game.")
        if self.army_definition_for_player(army_definition.player_id) is not None:
            raise GameLifecycleError("ArmyDefinition already exists for player.")
        _config_validation.validate_mission_setup_army_dispositions(
            self.mission_setup,
            army_definitions=(army_definition,),
        )
        resource_initializations = unit_resource_initializations_for_army(army_definition)
        self.army_definitions.append(army_definition)
        self.army_definitions.sort(key=lambda stored: stored.player_id)
        seed_unit_resources(
            state=self,
            player_id=army_definition.player_id,
            initializations=resource_initializations,
        )
        self._record_starting_strength_records_for_army(army_definition)
        self._record_starting_attached_unit_records_for_army(army_definition)
        self._record_static_core_ability_sources_for_army(army_definition)

    def replace_army_definitions(self, army_definitions: list[ArmyDefinition]) -> None:
        validated_armies = _config_validation.validate_army_definitions(
            army_definitions,
            player_ids=self.player_ids,
        )
        _config_validation.validate_mission_setup_army_dispositions(
            self.mission_setup,
            army_definitions=validated_armies,
        )
        self.army_definitions = validated_armies

    def replace_unit_resource_ledgers(self, ledgers: list[UnitResourceLedger]) -> None:
        self.unit_resource_ledgers = validate_unit_resource_ledgers(
            ledgers,
            player_ids=self.player_ids,
            army_definitions=self.army_definitions,
        )

    def replace_command_step_state(self, command_step_state: CommandStepState | None) -> None:
        self.command_step_state = _validate_optional_command_step_state(command_step_state)
        validate_command_battle_shock_state_snapshot(state=self)

    def replace_movement_phase_state(
        self,
        movement_phase_state: MovementPhaseState | None,
    ) -> None:
        self.movement_phase_state = _phase_validation.validate_optional_movement_phase_state(
            movement_phase_state
        )

    def replace_catalog_selected_target_battle_shock_continuation(
        self,
        continuation: PendingCatalogSelectedTargetBattleShockContinuation | None,
    ) -> None:
        self.pending_catalog_selected_target_battle_shock_continuation = (
            _phase_validation.validate_optional_catalog_selected_target_battle_shock_continuation(
                continuation
            )
        )

    def replace_charge_phase_state(self, charge_phase_state: ChargePhaseState | None) -> None:
        self.charge_phase_state = _phase_validation.validate_optional_charge_phase_state(
            charge_phase_state
        )

    def replace_fight_phase_state(self, fight_phase_state: FightPhaseState | None) -> None:
        self.fight_phase_state = _phase_validation.validate_optional_fight_phase_state(
            fight_phase_state
        )

    def replace_shooting_phase_state(
        self,
        shooting_phase_state: ShootingPhaseState | None,
    ) -> None:
        self.shooting_phase_state = _phase_validation.validate_optional_shooting_phase_state(
            shooting_phase_state
        )

    def replace_out_of_phase_shooting_state(
        self,
        out_of_phase_shooting_state: OutOfPhaseShootingState | None,
    ) -> None:
        self.out_of_phase_shooting_state = _validate_optional_out_of_phase_shooting_state(
            out_of_phase_shooting_state
        )

    def record_faction_rule_state(self, state: FactionRuleState) -> None:
        if type(state) is not FactionRuleState:
            raise GameLifecycleError("GameState faction rule state must be FactionRuleState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("FactionRuleState player_id is not in this game.")
        if any(stored.state_id == state.state_id for stored in self.faction_rule_states):
            raise GameLifecycleError("FactionRuleState already exists for state_id.")
        self.faction_rule_states.append(state)
        self.faction_rule_states = _validate_faction_rule_states(
            self.faction_rule_states,
            player_ids=self.player_ids,
        )

    def faction_rule_states_for_player(
        self,
        *,
        player_id: str,
        state_kind: str | None = None,
    ) -> tuple[FactionRuleState, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_kind = None
        if state_kind is not None:
            requested_kind = _validate_identifier("FactionRuleState state_kind", state_kind)
        return tuple(
            state
            for state in self.faction_rule_states
            if state.player_id == requested_player_id
            and (requested_kind is None or state.state_kind == requested_kind)
        )

    def add_unit_to_army(
        self,
        *,
        player_id: str,
        unit: UnitInstance,
        source_id: str,
    ) -> StartingStrengthRecord:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("GameState added unit must be a UnitInstance.")
        record_source_id = _validate_identifier("source_id", source_id)
        existing_unit_ids = {
            existing.unit_instance_id for army in self.army_definitions for existing in army.units
        }
        existing_record_ids = {record.unit_instance_id for record in self.starting_strength_records}
        if (
            unit.unit_instance_id in existing_unit_ids
            or unit.unit_instance_id in existing_record_ids
        ):
            raise GameLifecycleError("Added unit already exists in this game.")

        updated_armies: list[ArmyDefinition] = []
        added = False
        for army_definition in self.army_definitions:
            if army_definition.player_id != requested_player_id:
                updated_armies.append(army_definition)
                continue
            updated_armies.append(
                replace(
                    army_definition,
                    units=tuple(
                        sorted(
                            (*army_definition.units, unit),
                            key=lambda stored: stored.unit_instance_id,
                        )
                    ),
                )
            )
            added = True
        if not added:
            raise GameLifecycleError("Cannot add a unit before the player's army is mustered.")

        record = StartingStrengthRecord.from_unit(
            player_id=requested_player_id,
            unit=unit,
            source_id=record_source_id,
        )
        updated_primary_position_snapshots = (
            primary_rules_unit_turn_start_snapshots_with_created_unit(
                self.primary_rules_unit_turn_start_snapshots,
                unit_instance_id=unit.unit_instance_id,
            )
        )
        self.army_definitions = sorted(updated_armies, key=lambda stored: stored.player_id)
        self.primary_rules_unit_turn_start_snapshots = updated_primary_position_snapshots
        self.starting_strength_records.append(record)
        self.starting_strength_records.sort(key=lambda stored: stored.unit_instance_id)
        self._record_static_core_ability_sources_for_unit(unit)
        return record

    def _record_static_core_ability_sources_for_army(
        self,
        army_definition: ArmyDefinition,
    ) -> None:
        if type(army_definition) is not ArmyDefinition:
            raise GameLifecycleError(
                "Static core ability source registration requires an ArmyDefinition."
            )
        for unit in army_definition.units:
            self._record_static_core_ability_sources_for_unit(unit)

    def _record_static_core_ability_sources_for_unit(self, unit: UnitInstance) -> None:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError(
                "Static core ability source registration requires a UnitInstance."
            )
        record_core_deadly_demise_sources_for_unit(state=self, unit=unit)
        record_core_feel_no_pain_sources_for_unit(state=self, unit=unit)
        record_core_fights_first_source_for_unit(state=self, unit=unit)

    def apply_strategic_reserve_declarations(
        self,
        *,
        declarations: tuple[StrategicReserveDeclaration, ...],
        destruction_deadline_policy: ReserveDestructionTimingPolicy,
    ) -> tuple[ReserveState, ...]:
        if type(declarations) is not tuple:
            raise GameLifecycleError("strategic reserve declarations must be a tuple.")
        if not declarations:
            return ()
        if type(destruction_deadline_policy) is not ReserveDestructionTimingPolicy:
            raise GameLifecycleError(
                "strategic reserve destruction_deadline_policy must be "
                "ReserveDestructionTimingPolicy."
            )
        existing_reserved_ids = {
            state.unit_instance_id
            for state in self.reserve_states
            if state.status is ReserveStatus.IN_RESERVES
        }
        declared_unit_ids: set[str] = set()
        declared_embarked_ids: set[str] = set()
        points_by_player: dict[str, int] = {}
        cap_by_player: dict[str, int] = {}
        reserve_states: list[ReserveState] = []
        for declaration in declarations:
            if type(declaration) is not StrategicReserveDeclaration:
                raise GameLifecycleError(
                    "strategic reserve declarations must contain "
                    "StrategicReserveDeclaration values."
                )
            requested_player_id = _validate_player_id(
                declaration.player_id,
                player_ids=self.player_ids,
            )
            declaration_view = rules_unit_view_from_armies(
                armies=tuple(self.army_definitions),
                unit_instance_id=declaration.unit_instance_id,
            )
            if declaration_view.unit_instance_id != declaration.unit_instance_id:
                raise GameLifecycleError(
                    "Strategic Reserve declaration must use canonical rules-unit identity."
                )
            if declaration_view.owner_player_id != requested_player_id:
                raise GameLifecycleError("Strategic Reserve declaration player_id drift.")
            if declaration.unit_instance_id in existing_reserved_ids:
                raise GameLifecycleError("Strategic Reserve declaration unit is already reserved.")
            if declaration.unit_instance_id in declared_unit_ids:
                raise GameLifecycleError("Strategic Reserve declarations must not duplicate units.")
            declared_unit_ids.add(declaration.unit_instance_id)
            for embarked_unit_id in declaration.embarked_unit_instance_ids:
                embarked_view = rules_unit_view_from_armies(
                    armies=tuple(self.army_definitions),
                    unit_instance_id=embarked_unit_id,
                )
                if embarked_view.owner_player_id != requested_player_id:
                    raise GameLifecycleError(
                        "Strategic Reserve declaration embarked unit player_id drift."
                    )
                if embarked_unit_id in declared_embarked_ids:
                    raise GameLifecycleError(
                        "Strategic Reserve declarations must not duplicate embarked units."
                    )
                declared_embarked_ids.add(embarked_unit_id)
            previous_cap = cap_by_player.get(requested_player_id)
            if previous_cap is not None and previous_cap != declaration.points_limit:
                raise GameLifecycleError(
                    "Strategic Reserve declarations must use one points limit per player."
                )
            cap_by_player[requested_player_id] = declaration.points_limit
            points_by_player.setdefault(
                requested_player_id,
                sum(
                    state.points_contribution
                    for state in self.reserve_states
                    if state.player_id == requested_player_id
                    and state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
                    and state.status is ReserveStatus.IN_RESERVES
                ),
            )
            points_by_player[requested_player_id] += (
                declaration.unit_points + declaration.embarked_unit_points
            )
            reserve_states.append(
                declaration.to_reserve_state(
                    destruction_deadline_policy=destruction_deadline_policy
                )
            )
        overlap = declared_unit_ids & declared_embarked_ids
        if overlap:
            raise GameLifecycleError(
                "Strategic Reserve declarations must not also declare embarked units separately."
            )
        for player_id, points in points_by_player.items():
            if points > cap_by_player[player_id]:
                raise GameLifecycleError(
                    "Strategic Reserve declarations exceed the player's points limit."
                )
        self.reserve_states.extend(reserve_states)
        self.reserve_states.sort(key=lambda state: state.unit_instance_id)
        return tuple(sorted(reserve_states, key=lambda state: state.unit_instance_id))

    def declare_battle_formation_embarkation(
        self,
        *,
        player_id: str,
        transport_unit_instance_id: str,
        embarked_unit_instance_ids: tuple[str, ...],
        capacity_profile: TransportCapacityProfile,
    ) -> TransportCargoState:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        embarked_ids = _validate_identifier_tuple(
            "embarked_unit_instance_ids",
            embarked_unit_instance_ids,
            min_length=1,
            sort_values=True,
        )
        if type(capacity_profile) is not TransportCapacityProfile:
            raise GameLifecycleError(
                "battle formation embarkation capacity_profile must be TransportCapacityProfile."
            )
        if self.battlefield_state is not None and (
            self.battlefield_state.placed_armies or self.battlefield_state.removed_model_ids
        ):
            raise GameLifecycleError(
                "Battle formation embarkation must be declared before deployment."
            )
        if self.transport_cargo_state_for_transport(requested_transport_id) is not None:
            raise GameLifecycleError("Battle formation embarkation Transport already has cargo.")
        if (
            self.dedicated_transport_setup_consequence_for_transport(requested_transport_id)
            is not None
        ):
            raise GameLifecycleError(
                "Battle formation embarkation Transport already has a setup consequence."
            )
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        transport_owner = unit_owner_by_id.get(requested_transport_id)
        if transport_owner is None:
            raise GameLifecycleError("Battle formation embarkation Transport is unknown.")
        if transport_owner != requested_player_id:
            raise GameLifecycleError("Battle formation embarkation Transport player_id drift.")
        transport = self._unit_by_id(requested_transport_id)
        if not _unit_has_keyword(transport, "TRANSPORT"):
            raise GameLifecycleError("Battle formation embarkation requires a TRANSPORT unit.")
        if capacity_profile.transport_datasheet_id != transport.datasheet_id:
            raise GameLifecycleError(
                "Battle formation embarkation capacity profile datasheet drift."
            )
        embarked_units: list[UnitInstance] = []
        for unit_id in embarked_ids:
            if unit_id == requested_transport_id:
                raise GameLifecycleError("Battle formation embarkation cannot embark itself.")
            owner = unit_owner_by_id.get(unit_id)
            if owner is None:
                raise GameLifecycleError("Battle formation embarkation unit is unknown.")
            if owner != requested_player_id:
                raise GameLifecycleError("Battle formation embarkation unit player_id drift.")
            if any(
                unit_id in cargo.embarked_unit_instance_ids for cargo in self.transport_cargo_states
            ):
                raise GameLifecycleError("Battle formation embarkation unit is already embarked.")
            embarked_units.append(self._unit_by_id(unit_id))
        disallowed = tuple(
            unit.unit_instance_id
            for unit in embarked_units
            if not capacity_profile.allows_unit(unit)
        )
        if disallowed:
            raise GameLifecycleError(
                "Battle formation embarkation unit is not eligible for this Transport."
            )
        embarked_model_count = sum(len(unit.own_models) for unit in embarked_units)
        if embarked_model_count > capacity_profile.max_model_count:
            raise GameLifecycleError("Battle formation embarkation exceeds Transport capacity.")
        cargo_state = TransportCargoState(
            player_id=requested_player_id,
            transport_unit_instance_id=requested_transport_id,
            capacity_profile=capacity_profile,
            embarked_unit_instance_ids=embarked_ids,
            phase_battle_round=None,
            started_phase_embarked_unit_instance_ids=embarked_ids,
            disembarked_this_phase_unit_instance_ids=(),
        )
        self.transport_cargo_states.append(cargo_state)
        self.transport_cargo_states.sort(key=lambda state: state.transport_unit_instance_id)
        return cargo_state

    def army_definition_for_player(self, player_id: str) -> ArmyDefinition | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for army_definition in self.army_definitions:
            if army_definition.player_id == requested_player_id:
                return army_definition
        return None

    def missing_army_player_ids(self) -> tuple[str, ...]:
        mustered = {army_definition.player_id for army_definition in self.army_definitions}
        return tuple(player_id for player_id in self.player_ids if player_id not in mustered)

    def command_point_ledger_for_player(self, player_id: str) -> CommandPointLedger:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for ledger in self.command_point_ledgers:
            if ledger.player_id == requested_player_id:
                return ledger
        raise GameLifecycleError("CommandPointLedger player_id was not found.")

    def command_point_total(self, player_id: str) -> int:
        return self.command_point_ledger_for_player(player_id).command_points

    def faction_resource_ledger_for_player(self, player_id: str) -> FactionResourceLedger:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for ledger in self.faction_resource_ledgers:
            if ledger.player_id == requested_player_id:
                return ledger
        raise GameLifecycleError("FactionResourceLedger player_id was not found.")

    def faction_resource_total(self, *, player_id: str, resource_kind: str) -> int:
        return self.faction_resource_ledger_for_player(player_id).total(resource_kind)

    def gain_faction_resource(
        self,
        *,
        player_id: str,
        resource_kind: str,
        amount: int,
        source_id: str,
    ) -> FactionResourceResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.faction_resource_ledger_for_player(requested_player_id)
        updated, result = ledger.gain(
            battle_round=self.battle_round,
            resource_kind=resource_kind,
            amount=amount,
            source_id=source_id,
        )
        if updated is not ledger:
            self.faction_resource_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.faction_resource_ledgers
            ]
            self.faction_resource_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def gain_starting_faction_resource(
        self,
        *,
        player_id: str,
        resource_kind: str,
        amount: int,
        source_id: str,
    ) -> FactionResourceResult:
        if self.stage is not GameLifecycleStage.SETUP or self.battle_round != 0:
            raise GameLifecycleError(
                "Starting faction resources can only be granted during setup before battle."
            )
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.faction_resource_ledger_for_player(requested_player_id)
        updated, result = ledger.gain(
            battle_round=1,
            resource_kind=resource_kind,
            amount=amount,
            source_id=source_id,
        )
        if updated is not ledger:
            self.faction_resource_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.faction_resource_ledgers
            ]
            self.faction_resource_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def spend_faction_resource(
        self,
        *,
        player_id: str,
        resource_kind: str,
        amount: int,
        source_id: str,
    ) -> FactionResourceResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.faction_resource_ledger_for_player(requested_player_id)
        updated, result = ledger.spend(
            battle_round=self.battle_round,
            resource_kind=resource_kind,
            amount=amount,
            source_id=source_id,
        )
        if updated is not ledger:
            self.faction_resource_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.faction_resource_ledgers
            ]
            self.faction_resource_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def gain_command_points(
        self,
        *,
        player_id: str,
        amount: int,
        source_id: str,
        source_kind: CommandPointSourceKind,
        cap_exempt: bool = False,
    ) -> CommandPointGainResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.command_point_ledger_for_player(requested_player_id)
        updated, result = ledger.gain(
            battle_round=self.battle_round,
            amount=amount,
            source_id=source_id,
            source_kind=source_kind,
            cap_exempt=cap_exempt,
        )
        if updated is not ledger:
            self.command_point_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.command_point_ledgers
            ]
            self.command_point_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def spend_command_points(
        self,
        *,
        player_id: str,
        amount: int,
        source_id: str,
    ) -> CommandPointSpendResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.command_point_ledger_for_player(requested_player_id)
        updated, result = ledger.spend(
            battle_round=self.battle_round,
            amount=amount,
            source_id=source_id,
        )
        if updated is not ledger:
            self.command_point_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.command_point_ledgers
            ]
            self.command_point_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def refund_command_points(
        self,
        *,
        player_id: str,
        amount: int,
        source_id: str,
        cap_exempt: bool = False,
    ) -> CommandPointRefundResult:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        ledger = self.command_point_ledger_for_player(requested_player_id)
        updated, result = ledger.refund(
            battle_round=self.battle_round,
            amount=amount,
            source_id=source_id,
            cap_exempt=cap_exempt,
        )
        if updated is not ledger:
            self.command_point_ledgers = [
                updated if stored.player_id == requested_player_id else stored
                for stored in self.command_point_ledgers
            ]
            self.command_point_ledgers.sort(key=lambda stored: stored.player_id)
        return result

    def record_stratagem_use(self, use_record: StratagemUseRecord) -> None:
        if type(use_record) is not StratagemUseRecord:
            raise GameLifecycleError("GameState stratagem use must be a StratagemUseRecord.")
        if use_record.player_id not in self.player_ids:
            raise GameLifecycleError("StratagemUseRecord player_id is not in this game.")
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("StratagemUseRecord can be recorded only during battle.")
        if use_record.battle_round != self.battle_round:
            raise GameLifecycleError("StratagemUseRecord battle_round drift.")
        if use_record.phase is not self.current_battle_phase:
            raise GameLifecycleError("StratagemUseRecord phase drift.")
        if use_record.active_player_id != self.active_player_id:
            raise GameLifecycleError("StratagemUseRecord active_player_id drift.")
        if any(stored.use_id == use_record.use_id for stored in self.stratagem_use_records):
            raise GameLifecycleError("StratagemUseRecord use_id must be unique.")
        self.stratagem_use_records.append(use_record)
        self.stratagem_use_records.sort(key=lambda stored: stored.use_id)

    def stratagem_use_records_for_player(
        self,
        player_id: str,
    ) -> tuple[StratagemUseRecord, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return tuple(
            record
            for record in self.stratagem_use_records
            if record.player_id == requested_player_id
        )

    def victory_point_ledger_for_player(self, player_id: str) -> VictoryPointLedger:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        for ledger in self.victory_point_ledgers:
            if ledger.player_id == requested_player_id:
                return ledger
        raise GameLifecycleError("VictoryPointLedger player_id was not found.")

    def victory_point_total(self, player_id: str) -> int:
        return self.victory_point_ledger_for_player(player_id).victory_points

    def award_victory_points(self, award: VictoryPointAward) -> VictoryPointTransaction:
        self.victory_point_ledgers, transaction = (
            _vp_awards.resolve_victory_point_award_for_game_state(state=self, award=award)
        )
        return transaction

    def record_secondary_scoring_state_evidence(
        self,
        evidence: SecondaryScoringStateEvidence,
    ) -> None:
        if type(evidence) is not SecondaryScoringStateEvidence:
            raise GameLifecycleError(
                "Secondary scoring state evidence must be SecondaryScoringStateEvidence."
            )
        if evidence.game_id != self.game_id:
            raise GameLifecycleError("Secondary scoring state evidence game_id drift.")
        matches = tuple(
            stored
            for stored in self.secondary_scoring_state_evidence_records
            if stored.evidence_id == evidence.evidence_id
        )
        if matches:
            if matches == (evidence,):
                return
            raise GameLifecycleError("Secondary scoring state evidence identity is duplicated.")
        self.secondary_scoring_state_evidence_records.append(evidence)
        self.secondary_scoring_state_evidence_records.sort(key=lambda stored: stored.evidence_id)

    def replace_primary_scoring_boundary_lifecycles(
        self, rows: list[PrimaryScoringBoundaryLifecycle]
    ) -> None:
        self.primary_scoring_boundary_lifecycles = list(rows)

    def restore_mission_scoring_aggregate(self, snapshot: object) -> None:
        from warhammer40k_core.engine import mission_scoring_transaction as scoring_tx

        if type(snapshot) is not scoring_tx.MissionScoringAggregateSnapshot:
            raise GameLifecycleError("Mission scoring restore requires a typed aggregate snapshot.")
        self.objective_control_records = list(snapshot.objective_control_records)
        self.objective_control_record_authorities = list(
            snapshot.objective_control_record_authorities
        )
        self.sticky_objective_control_states = list(snapshot.sticky_objective_control_states)
        self.primary_scoring_state_evidence_records = list(
            snapshot.primary_scoring_state_evidence_records
        )
        self.secondary_scoring_state_evidence_records = list(
            snapshot.secondary_scoring_state_evidence_records
        )
        self.victory_point_ledgers = list(snapshot.victory_point_ledgers)
        self.secondary_mission_card_states = list(snapshot.secondary_mission_card_states)
        self.primary_scoring_boundary_lifecycles = list(
            snapshot.primary_scoring_boundary_lifecycles
        )

    def record_mission_action_state(self, action_state: MissionActionState) -> None:
        if type(action_state) is not MissionActionState:
            raise GameLifecycleError("mission_action_state must be a MissionActionState.")
        if action_state.player_id not in self.player_ids:
            raise GameLifecycleError("MissionActionState player_id is not in this game.")
        if any(stored.action_id == action_state.action_id for stored in self.mission_action_states):
            raise GameLifecycleError("MissionActionState already exists for action_id.")
        self.mission_action_states.append(action_state)
        self.mission_action_states.sort(key=lambda state: state.action_id)

    def mission_action_state_by_id(self, action_id: str) -> MissionActionState:
        requested_action_id = _validate_identifier("action_id", action_id)
        for action_state in self.mission_action_states:
            if action_state.action_id == requested_action_id:
                return action_state
        raise GameLifecycleError("MissionActionState action_id was not found.")

    def replace_mission_action_state(self, action_state: MissionActionState) -> None:
        if type(action_state) is not MissionActionState:
            raise GameLifecycleError("mission_action_state must be a MissionActionState.")
        if action_state.player_id not in self.player_ids:
            raise GameLifecycleError("MissionActionState player_id is not in this game.")
        for index, stored in enumerate(self.mission_action_states):
            if stored.action_id == action_state.action_id:
                self.mission_action_states[index] = action_state
                return
        raise GameLifecycleError("MissionActionState does not exist for action_id.")

    def replace_mission_action_state_with_primary_progress(
        self,
        action_state: MissionActionState,
        progress: PrimaryMissionProgressState,
    ) -> None:
        if type(progress) is not PrimaryMissionProgressState:
            raise GameLifecycleError("Primary mission progress replacement must be typed.")
        self.replace_mission_action_state(action_state)
        self.primary_mission_progress_state = progress

    def replace_primary_mission_progress_state(self, progress: PrimaryMissionProgressState) -> None:
        if type(progress) is not PrimaryMissionProgressState:
            raise GameLifecycleError("Primary mission progress replacement must be typed.")
        self.primary_mission_progress_state = progress

    def complete_mission_action(
        self,
        *,
        action_id: str,
        completion_phase: BattlePhase,
    ) -> MissionActionState:
        if self.mission_setup is None:
            raise GameLifecycleError("Mission Action scoring requires MissionSetup.")
        if type(completion_phase) is not BattlePhase:
            raise GameLifecycleError("completion_phase must be a BattlePhase.")
        action_state = self.mission_action_state_by_id(action_id)
        if _action_history.is_battle_shocked(self, action_state.unit_instance_id):
            raise GameLifecycleError("Battle-shocked units cannot complete actions.")
        if action_state.victory_points == 0:
            if action_state.scoring_source_id == "cleanse":
                self._validate_cleanse_action_completion(action_state, completion_phase)
            completed_without_award = action_state.complete_without_award(
                battle_round=self.battle_round,
                phase=completion_phase.value,
                completion_timing=action_state.completion_timing,
                battle_shocked_unit_ids=tuple(self.battle_shocked_unit_ids),
            )
            self.replace_mission_action_state(completed_without_award)
            if completed_without_award.scoring_source_id == "cleanse":
                cleanse_source = _scoring_evidence_validation.source_action_for_mission_identity(
                    mission_setup=self.mission_setup,
                    mission_id=completed_without_award.mission_id,
                    expected_target_policy="objective_marker",
                    expected_mission_kind="secondary",
                    evidence_kind="SecondaryObjectiveCleanseState",
                )
                self.record_secondary_objective_cleanse(
                    player_id=completed_without_award.player_id,
                    objective_marker_id=completed_without_award.target_id,
                    action_id=completed_without_award.action_id,
                    phase=completion_phase,
                    source_id=cleanse_source.source_id,
                )
            return completed_without_award
        policy = mission_scoring_policies_from_setup(self.mission_setup)
        award = policy.mission_action_award(
            player_id=action_state.player_id,
            battle_round=self.battle_round,
            phase=completion_phase.value,
            action_id=action_state.action_id,
            source_id=action_state.scoring_source_id,
            amount=action_state.victory_points,
        )
        transaction = self.award_victory_points(award)
        completed = action_state.complete(
            battle_round=self.battle_round,
            phase=completion_phase.value,
            completion_timing=action_state.completion_timing,
            award=award,
            transaction_id=transaction.transaction_id,
            battle_shocked_unit_ids=tuple(self.battle_shocked_unit_ids),
        )
        self.replace_mission_action_state(completed)
        return completed

    def interrupt_mission_action(self, *, action_id: str, reason: str) -> MissionActionState:
        action_state = self.mission_action_state_by_id(action_id)
        interrupted = action_state.interrupt(reason=reason)
        self.replace_mission_action_state(interrupted)
        return interrupted

    def _validate_cleanse_action_completion(
        self,
        action_state: MissionActionState,
        completion_phase: BattlePhase,
    ) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Cleanse completion requires MissionSetup.")
        if type(action_state) is not MissionActionState:
            raise GameLifecycleError("Cleanse completion requires MissionActionState.")
        if type(completion_phase) is not BattlePhase:
            raise GameLifecycleError("Cleanse completion requires BattlePhase.")
        record = resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                self,
                timing=ObjectiveControlTiming.TURN_END,
                phase=completion_phase,
                ruleset_descriptor=self.ruleset_descriptor_for_runtime_policy(),
            )
        )
        for result in record.results:
            if result.objective_id != action_state.target_id:
                continue
            if result.controlled_by_player_id != action_state.player_id:
                raise GameLifecycleError("Cleanse completion requires controlling the objective.")
            return
        raise GameLifecycleError("Cleanse completion objective is unknown.")

    def record_primary_objective_turn_start_state(
        self,
        state: PrimaryObjectiveTurnStartState,
    ) -> None:
        if type(state) is not PrimaryObjectiveTurnStartState:
            raise GameLifecycleError(
                "primary_objective_turn_start_state must be a PrimaryObjectiveTurnStartState."
            )
        if state.game_id != self.game_id:
            raise GameLifecycleError("PrimaryObjectiveTurnStartState game_id drift.")
        if state.player_id not in self.player_ids or state.active_player_id not in self.player_ids:
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState player_id is not in this game."
            )
        if any(
            stored.state_id == state.state_id for stored in self.primary_objective_turn_start_states
        ):
            raise GameLifecycleError("PrimaryObjectiveTurnStartState already exists.")
        if any(
            stored.player_id == state.player_id and stored.battle_round == state.battle_round
            for stored in self.primary_objective_turn_start_states
        ):
            raise GameLifecycleError(
                "PrimaryObjectiveTurnStartState already exists for this player turn."
            )
        self.primary_objective_turn_start_states = validate_primary_objective_turn_start_states(
            [*self.primary_objective_turn_start_states, state],
            game_id=self.game_id,
            player_ids=self.player_ids,
            known_objective_marker_ids=tuple(
                marker.objective_marker_id
                for marker in (
                    () if self.mission_setup is None else self.mission_setup.objective_markers
                )
            ),
        )

    def record_primary_rules_unit_turn_start_snapshot(
        self,
        snapshot: PrimaryRulesUnitTurnStartSnapshot,
    ) -> None:
        record_primary_rules_unit_turn_start_snapshot(
            state=self,
            snapshot=snapshot,
        )

    def record_primary_terrain_trap(
        self,
        *,
        player_id: str,
        terrain_feature_id: str,
        action_id: str,
        phase: BattlePhase,
        source_id: str,
    ) -> PrimaryTerrainTrapState:
        if self.mission_setup is None:
            raise GameLifecycleError("Primary terrain trap tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError("Primary terrain trap tracking requires an active player.")
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Primary terrain trap tracking requires a BattlePhase.")
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player_id != self.active_player_id:
            raise GameLifecycleError("Primary terrain trap must be recorded during owner's turn.")
        requested_area_id = _validate_identifier("terrain_feature_id", terrain_feature_id)
        logical_area = _mission_terrain.mission_logical_terrain_area_by_id(
            self.mission_setup, logical_terrain_area_id=requested_area_id
        )
        if any(
            state.player_id == requested_player_id and state.terrain_feature_id == requested_area_id
            for state in self.primary_terrain_trap_states
        ):
            raise GameLifecycleError("Primary terrain trap already exists for this player.")
        state = PrimaryTerrainTrapState(
            trap_id=(
                f"primary-terrain-trap:{self.game_id}:round-{self.battle_round:02d}:"
                f"{requested_player_id}:{requested_area_id}"
            ),
            game_id=self.game_id,
            player_id=requested_player_id,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            terrain_feature_id=requested_area_id,
            is_objective=_mission_terrain.logical_terrain_area_is_objective(
                logical_area, mission_setup=self.mission_setup
            ),
            action_id=_validate_identifier("action_id", action_id),
            source_id=_validate_identifier("source_id", source_id),
        )
        _scoring_evidence_validation.validate_primary_terrain_trap_action_link(
            state,
            mission_setup=self.mission_setup,
            mission_action_states=self.mission_action_states,
        )
        self.primary_terrain_trap_states.append(state)
        self.primary_terrain_trap_states.sort(key=lambda stored: stored.trap_id)
        return state

    def record_primary_unit_destruction(
        self,
        *,
        destruction_attribution: ModelDestructionAttribution | None,
        source_model_destroyed_event_id: str | None,
        source_rules_unit_objective_proximity_witness: (RulesUnitObjectiveProximityWitness | None),
        source_battlefield_departure_ids: tuple[str, ...],
        unattributed_cause: PrimaryUnattributedDestructionCause | None,
        source_mutation_id: str | None,
        destroyed_unit_instance_id: str,
        source_id: str,
    ) -> PrimaryUnitDestructionState:
        destruction = build_primary_unit_destruction_state(
            state=self,
            destruction_attribution=destruction_attribution,
            source_model_destroyed_event_id=source_model_destroyed_event_id,
            source_rules_unit_objective_proximity_witness=(
                source_rules_unit_objective_proximity_witness
            ),
            source_battlefield_departure_ids=source_battlefield_departure_ids,
            unattributed_cause=unattributed_cause,
            source_mutation_id=source_mutation_id,
            destroyed_unit_instance_id=destroyed_unit_instance_id,
            source_id=source_id,
        )
        secondary_destruction = secondary_unit_destruction_from_primary(
            state=self,
            primary_destruction=destruction,
        )
        self.primary_unit_destruction_states.append(destruction)
        self.primary_unit_destruction_states.sort(key=lambda stored: stored.destruction_id)
        self.record_secondary_unit_destruction_projection(secondary_destruction)
        record_consecration_designation_for_destruction(state=self, destruction=destruction)
        return destruction

    def record_secondary_unit_destruction_projection(
        self,
        destruction: SecondaryUnitDestructionState,
    ) -> None:
        """Store the authenticated Secondary projection of a Primary occurrence."""
        self.secondary_unit_destruction_states = validate_secondary_unit_destruction_states(
            [*self.secondary_unit_destruction_states, destruction],
            state=self,
        )

    def record_secondary_objective_cleanse(
        self,
        *,
        player_id: str,
        objective_marker_id: str,
        action_id: str,
        phase: BattlePhase,
        source_id: str,
    ) -> SecondaryObjectiveCleanseState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary objective cleanse tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError(
                "Secondary objective cleanse tracking requires an active player."
            )
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Secondary objective cleanse tracking requires a phase.")
        requested_player = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player != self.active_player_id:
            raise GameLifecycleError("Secondary objective cleanse must happen on owner's turn.")
        requested_objective = _validate_identifier("objective_marker_id", objective_marker_id)
        known_objective_ids = {
            marker.objective_marker_id for marker in self.mission_setup.objective_markers
        }
        if requested_objective not in known_objective_ids:
            raise GameLifecycleError("Secondary objective cleanse references an unknown objective.")
        requested_action = _validate_identifier("action_id", action_id)
        if any(
            state.player_id == requested_player
            and state.battle_round == self.battle_round
            and state.active_player_id == self.active_player_id
            and state.objective_marker_id == requested_objective
            for state in self.secondary_objective_cleanse_states
        ):
            raise GameLifecycleError(
                "Secondary objective cleanse already exists for this objective turn."
            )
        state = SecondaryObjectiveCleanseState(
            cleanse_id=(
                f"secondary-objective-cleanse:{self.game_id}:round-{self.battle_round:02d}:"
                f"{requested_player}:{requested_objective}"
            ),
            game_id=self.game_id,
            player_id=requested_player,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            objective_marker_id=requested_objective,
            action_id=requested_action,
            source_id=_validate_identifier("source_id", source_id),
        )
        _scoring_evidence_validation.validate_secondary_objective_cleanse_action_link(
            state,
            mission_setup=self.mission_setup,
            mission_action_states=self.mission_action_states,
        )
        self.secondary_objective_cleanse_states.append(state)
        self.secondary_objective_cleanse_states.sort(key=lambda stored: stored.cleanse_id)
        return state

    def record_secondary_terrain_plunder(
        self,
        *,
        player_id: str,
        terrain_feature_id: str,
        action_id: str,
        phase: BattlePhase,
        source_id: str,
    ) -> SecondaryTerrainPlunderState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary terrain plunder tracking requires MissionSetup.")
        if self.active_player_id is None:
            raise GameLifecycleError(
                "Secondary terrain plunder tracking requires an active player."
            )
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Secondary terrain plunder tracking requires a phase.")
        requested_player = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player != self.active_player_id:
            raise GameLifecycleError("Secondary terrain plunder must happen on owner's turn.")
        requested_area_id = _validate_identifier("terrain_feature_id", terrain_feature_id)
        _mission_terrain.mission_logical_terrain_area_by_id(
            self.mission_setup, logical_terrain_area_id=requested_area_id
        )
        if any(
            state.player_id == requested_player
            and state.battle_round == self.battle_round
            and state.active_player_id == self.active_player_id
            for state in self.secondary_terrain_plunder_states
        ):
            raise GameLifecycleError(
                "Secondary terrain plunder already exists for this player turn."
            )
        state = SecondaryTerrainPlunderState(
            plunder_id=(
                f"secondary-terrain-plunder:{self.game_id}:round-{self.battle_round:02d}:"
                f"{requested_player}:{requested_area_id}"
            ),
            game_id=self.game_id,
            player_id=requested_player,
            active_player_id=self.active_player_id,
            battle_round=self.battle_round,
            phase=phase.value,
            terrain_feature_id=requested_area_id,
            action_id=_validate_identifier("action_id", action_id),
            source_id=_validate_identifier("source_id", source_id),
        )
        _scoring_evidence_validation.validate_secondary_terrain_plunder_action_link(
            state,
            mission_setup=self.mission_setup,
            mission_action_states=self.mission_action_states,
        )
        self.secondary_terrain_plunder_states.append(state)
        self.secondary_terrain_plunder_states.sort(key=lambda stored: stored.plunder_id)
        return state

    def runtime_ruleset_descriptor(self) -> RulesetDescriptor:
        return self.ruleset_descriptor_for_runtime_policy()

    def record_persisting_effect(self, effect: PersistingEffect) -> None:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("persisting_effect must be a PersistingEffect.")
        if effect.owner_player_id not in self.player_ids:
            raise GameLifecycleError("PersistingEffect owner_player_id is not in this game.")
        unit_ids = _known_rules_unit_ids(
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
        )
        if not unit_ids:
            raise GameLifecycleError("PersistingEffect requires mustered army definitions.")
        if any(unit_id not in unit_ids for unit_id in effect.target_unit_instance_ids):
            raise GameLifecycleError("PersistingEffect target unit is unknown.")
        if any(stored.effect_id == effect.effect_id for stored in self.persisting_effects):
            raise GameLifecycleError("PersistingEffect already exists for effect_id.")
        self.persisting_effects.append(effect)
        self.persisting_effects.sort(key=lambda stored: stored.effect_id)

    def persisting_effects_for_unit(self, unit_instance_id: str) -> tuple[PersistingEffect, ...]:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return tuple(
            effect
            for effect in self.persisting_effects
            if effect.applies_to_unit(requested_unit_id)
        )

    def record_tracked_target(self, record: TrackedTargetRecord) -> None:
        if type(record) is not TrackedTargetRecord:
            raise GameLifecycleError("Tracked target record must be TrackedTargetRecord.")
        owner_by_unit_id = _known_rules_unit_owner_ids(
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
        )
        if record.owner_player_id not in self.player_ids:
            raise GameLifecycleError("Tracked target owner_player_id is not in this game.")
        validate_canonical_tracked_target_record(
            armies=tuple(self.army_definitions),
            record=record,
        )
        if record.source_unit_instance_id not in owner_by_unit_id:
            raise GameLifecycleError("Tracked target source unit is unknown.")
        if owner_by_unit_id[record.source_unit_instance_id] != record.owner_player_id:
            raise GameLifecycleError("Tracked target source unit owner drift.")
        if record.target_unit_instance_id not in owner_by_unit_id:
            raise GameLifecycleError("Tracked target unit is unknown.")
        if (
            record.target_allegiance == "enemy"
            and owner_by_unit_id[record.target_unit_instance_id] == record.owner_player_id
        ):
            raise GameLifecycleError("Tracked target enemy target is friendly.")
        if (
            record.target_allegiance == "friendly"
            and owner_by_unit_id[record.target_unit_instance_id] != record.owner_player_id
        ):
            raise GameLifecycleError("Tracked target friendly target is enemy.")
        if record.owner_scope is TrackedTargetOwnerScope.THIS_MODEL:
            source_model_ids = _model_ids_for_unit(
                army_definitions=self.army_definitions,
                unit_instance_id=record.source_unit_instance_id,
            )
            if record.source_model_instance_id not in source_model_ids:
                raise GameLifecycleError("Tracked target source model is not in source unit.")
        if record.target_unit_instance_id in self._destroyed_unit_instance_ids():
            raise GameLifecycleError("Tracked target cannot select a destroyed target.")
        if any(stored.record_id == record.record_id for stored in self.tracked_target_records):
            raise GameLifecycleError("Tracked target record_id already exists.")
        if record.active and any(
            stored.active and stored.active_key() == record.active_key()
            for stored in self.tracked_target_records
        ):
            raise GameLifecycleError("Tracked target active source key already exists.")
        self.tracked_target_records.append(record)
        self.tracked_target_records = _validate_tracked_target_records(
            self.tracked_target_records,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )

    def active_tracked_target_for(
        self,
        *,
        source_rule_id: str,
        source_unit_instance_id: str,
        source_model_instance_id: str | None,
        owner_scope: TrackedTargetOwnerScope,
        role: TrackedTargetRole,
    ) -> TrackedTargetRecord | None:
        return _active_tracked_target_for(
            armies=tuple(self.army_definitions),
            records=self.tracked_target_records,
            source_rule_id=source_rule_id,
            source_unit_instance_id=source_unit_instance_id,
            source_model_instance_id=source_model_instance_id,
            owner_scope=owner_scope,
            role=role,
        )

    def expire_tracked_target(self, record_id: str) -> TrackedTargetRecord:
        requested_id = _validate_identifier("record_id", record_id)
        updated: list[TrackedTargetRecord] = []
        expired: TrackedTargetRecord | None = None
        for record in self.tracked_target_records:
            if record.record_id != requested_id:
                updated.append(record)
                continue
            expired = record.inactive()
            updated.append(expired)
        if expired is None:
            raise GameLifecycleError("Tracked target record_id is unknown.")
        self.tracked_target_records = _validate_tracked_target_records(
            updated,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        return expired

    def tracked_targets_for_destroyed_unit(
        self,
        *,
        destroyed_unit_instance_id: str,
    ) -> tuple[TrackedTargetRecord, ...]:
        return _tracked_targets_for_destroyed_unit(
            armies=tuple(self.army_definitions),
            records=self.tracked_target_records,
            destroyed_unit_instance_id=destroyed_unit_instance_id,
            destroyed_rules_unit_instance_ids=self._destroyed_unit_instance_ids(),
        )

    def record_pending_return_on_death(self, pending: PendingReturnOnDeath) -> None:
        if type(pending) is not PendingReturnOnDeath:
            raise GameLifecycleError("pending return-on-death must be PendingReturnOnDeath.")
        owner_by_unit_id = _known_rules_unit_owner_ids(
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
        )
        if pending.owner_player_id not in self.player_ids:
            raise GameLifecycleError("Return-on-death owner_player_id is not in this game.")
        if pending.destroyed_unit_instance_id not in owner_by_unit_id:
            raise GameLifecycleError("Return-on-death destroyed unit is unknown.")
        if owner_by_unit_id[pending.destroyed_unit_instance_id] != pending.owner_player_id:
            raise GameLifecycleError("Return-on-death owner drift.")
        if any(stored.pending_id == pending.pending_id for stored in self.pending_return_on_death):
            raise GameLifecycleError("Return-on-death pending_id already exists.")
        if any(
            not stored.resolved and stored.consumed_key() == pending.consumed_key()
            for stored in self.pending_return_on_death
        ):
            raise GameLifecycleError("Return-on-death pending entry already exists.")
        if pending.consumed_key() in set(self.return_on_death_consumed_keys):
            raise GameLifecycleError("Return-on-death consumed key already exists.")
        self.pending_return_on_death.append(pending)
        self.pending_return_on_death = _validate_pending_return_on_death(
            self.pending_return_on_death,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        self.return_on_death_consumed_keys = list(
            _validate_identifier_tuple(
                "GameState return_on_death_consumed_keys",
                (*self.return_on_death_consumed_keys, pending.consumed_key()),
                min_length=0,
                sort_values=True,
            )
        )

    def pending_return_on_death_by_id(self, pending_id: str) -> PendingReturnOnDeath:
        requested_id = _validate_identifier("pending_id", pending_id)
        for pending in self.pending_return_on_death:
            if pending.pending_id == requested_id:
                return pending
        raise GameLifecycleError("Return-on-death pending_id is unknown.")

    def resolve_pending_return_on_death(self, pending_id: str) -> PendingReturnOnDeath:
        requested_id = _validate_identifier("pending_id", pending_id)
        updated: list[PendingReturnOnDeath] = []
        resolved: PendingReturnOnDeath | None = None
        for pending in self.pending_return_on_death:
            if pending.pending_id != requested_id:
                updated.append(pending)
                continue
            resolved = pending.mark_resolved()
            updated.append(resolved)
        if resolved is None:
            raise GameLifecycleError("Return-on-death pending_id is unknown.")
        self.pending_return_on_death = _validate_pending_return_on_death(
            updated,
            army_definitions=self.army_definitions,
            starting_strength_records=self.starting_strength_records,
            player_ids=self.player_ids,
        )
        return resolved

    def _destroyed_unit_instance_ids(self) -> set[str]:
        if self.battlefield_state is None:
            return set()
        removed_model_ids = set(self.battlefield_state.removed_model_ids)
        destroyed: set[str] = set()
        for army in self.army_definitions:
            for unit in army.units:
                model_ids = {model.model_instance_id for model in unit.own_models}
                if model_ids and model_ids <= removed_model_ids:
                    destroyed.add(unit.unit_instance_id)
        destroyed.update(
            destroyed_attached_rules_unit_ids(
                armies=tuple(self.army_definitions),
                removed_model_ids=removed_model_ids,
            )
        )
        return destroyed

    def remove_persisting_effects_by_id(
        self,
        effect_ids: tuple[str, ...],
    ) -> tuple[PersistingEffect, ...]:
        requested_effect_ids = _validate_identifier_tuple(
            "effect_ids",
            effect_ids,
            min_length=0,
            sort_values=True,
        )
        if not requested_effect_ids:
            return ()
        by_id = {effect.effect_id: effect for effect in self.persisting_effects}
        missing_ids = tuple(
            effect_id for effect_id in requested_effect_ids if effect_id not in by_id
        )
        if missing_ids:
            raise GameLifecycleError("Cannot remove unknown PersistingEffect IDs.")
        removed = tuple(by_id[effect_id] for effect_id in requested_effect_ids)
        removed_ids = {effect.effect_id for effect in removed}
        self.persisting_effects = [
            effect for effect in self.persisting_effects if effect.effect_id not in removed_ids
        ]
        return tuple(sorted(removed, key=lambda effect: effect.effect_id))

    def expire_persisting_effects_at_boundary(
        self,
        boundary: EffectExpirationBoundary,
    ) -> tuple[PersistingEffect, ...]:
        if type(boundary) is not EffectExpirationBoundary:
            raise GameLifecycleError("effect expiration boundary must be EffectExpirationBoundary.")
        expired = tuple(effect for effect in self.persisting_effects if effect.expires_at(boundary))
        if not expired:
            return ()
        expired_ids = {effect.effect_id for effect in expired}
        self.persisting_effects = [
            effect for effect in self.persisting_effects if effect.effect_id not in expired_ids
        ]
        return tuple(sorted(expired, key=lambda effect: effect.effect_id))

    def starting_strength_record_for_unit(self, unit_instance_id: str) -> StartingStrengthRecord:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for record in self.starting_strength_records:
            if record.unit_instance_id == requested_unit_id:
                return record
        raise GameLifecycleError("StartingStrengthRecord unit_instance_id was not found.")

    def unit_instance_id_for_model(self, model_instance_id: str) -> str:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        for army_definition in self.army_definitions:
            for unit in army_definition.units:
                if any(model.model_instance_id == requested_model_id for model in unit.own_models):
                    return unit.unit_instance_id
        raise GameLifecycleError("GameState model_instance_id was not found.")

    def unit_started_battle_as_attached_leader_or_support(
        self,
        unit_instance_id: str,
    ) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if requested_unit_id not in _physical_unit_ids(self.army_definitions):
            raise GameLifecycleError("Starting attached-unit query unit_instance_id is unknown.")
        return any(
            requested_unit_id in record.leader_or_support_unit_instance_ids()
            for record in self.starting_attached_unit_records
        )

    def record_battle_shock_result(self, result: BattleShockResult) -> None:
        record_battle_shock_result(state=self, result=result)

    def replace_battle_shock_state(
        self, state: tuple[list[str], list[BattleShockedUnitState]]
    ) -> None:
        self.battle_shocked_unit_ids, self.battle_shocked_unit_states = state

    def record_battlefield_state(self, battlefield_state: BattlefieldRuntimeState) -> None:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError(
                "GameState battlefield_state must be a BattlefieldRuntimeState."
            )
        if self.battlefield_state is not None:
            raise GameLifecycleError("GameState battlefield_state already exists.")
        validate_battlefield_state_matches_mission_setup(
            battlefield_state=battlefield_state,
            mission_setup=self.mission_setup,
        )
        self._assert_battlefield_state_clear_of_objective_markers(battlefield_state)
        self.battlefield_state = battlefield_state

    def replace_battlefield_state(self, battlefield_state: BattlefieldRuntimeState) -> None:
        if type(battlefield_state) is not BattlefieldRuntimeState:
            raise GameLifecycleError(
                "GameState battlefield_state must be a BattlefieldRuntimeState."
            )
        if self.battlefield_state is None:
            raise GameLifecycleError("GameState battlefield_state does not exist.")
        validate_battlefield_state_matches_mission_setup(
            battlefield_state=battlefield_state,
            mission_setup=self.mission_setup,
        )
        self._assert_battlefield_state_clear_of_objective_markers(battlefield_state)
        self.battlefield_state = battlefield_state

    def record_mission_setup(self, mission_setup: MissionSetup) -> None:
        if self.mission_setup is not None:
            raise GameLifecycleError("GameState mission_setup already exists.")
        validated_setup = _validate_optional_mission_setup(
            mission_setup,
            player_ids=self.player_ids,
        )
        if validated_setup is None:
            raise GameLifecycleError("GameState mission_setup is required.")
        validate_recorded_mission_setup(
            validated_setup,
            battlefield_state=self.battlefield_state,
        )
        _config_validation.validate_mission_setup_army_dispositions(
            validated_setup,
            army_definitions=self.army_definitions,
        )
        validate_victory_point_ledger_policy_sources(
            self.victory_point_ledgers,
            mission_setup=validated_setup,
            objective_control_records=tuple(self.objective_control_records),
            primary_scoring_state_evidence_records=tuple(
                self.primary_scoring_state_evidence_records
            ),
            turn_order=self.turn_order,
            current_battle_round=self.battle_round,
            policies=mission_scoring_policies_from_setup(validated_setup),
        )
        self.mission_setup = validated_setup

    def record_tactical_secondary_draw(self, draw: TacticalSecondaryDraw) -> None:
        if draw.player_id not in self.player_ids:
            raise GameLifecycleError("TacticalSecondaryDraw player_id is not in this game.")
        if self.has_tactical_secondary_draw(
            player_id=draw.player_id,
            battle_round=draw.battle_round,
        ):
            raise GameLifecycleError("TacticalSecondaryDraw already exists for player and round.")
        self.tactical_secondary_draws.append(draw)
        self.tactical_secondary_draws.sort(
            key=lambda stored: (stored.battle_round, stored.player_id)
        )

    def record_prebattle_action(self, record: PreBattleActionRecord) -> None:
        if type(record) is not PreBattleActionRecord:
            raise GameLifecycleError("prebattle action record must be a PreBattleActionRecord.")
        if record.game_id != self.game_id:
            raise GameLifecycleError("PreBattleActionRecord game_id drift.")
        if record.player_id not in self.player_ids:
            raise GameLifecycleError("PreBattleActionRecord player_id is not in this game.")
        if record.setup_step not in self.setup_sequence:
            raise GameLifecycleError("PreBattleActionRecord setup_step is not in this game.")
        if any(stored.action_id == record.action_id for stored in self.prebattle_action_records):
            raise GameLifecycleError("PreBattleActionRecord action_id already exists.")
        if record.setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS:
            if self.prebattle_alternation_cursor is None:
                raise GameLifecycleError(
                    "Pre-battle actions require an initialized alternation cursor."
                )
            self.prebattle_alternation_cursor = self.prebattle_alternation_cursor.after_action(
                record
            )
        self.prebattle_action_records.append(record)
        self.prebattle_action_records.sort(key=lambda stored: stored.action_id)

    def set_prebattle_alternation_cursor(
        self,
        cursor: PreBattleAlternationCursor,
    ) -> None:
        self.prebattle_alternation_cursor = _validate_prebattle_alternation_cursor(
            cursor,
            records=self.prebattle_action_records,
            game_id=self.game_id,
            turn_order=self.turn_order,
        )

    def prebattle_action_records_for_step(
        self,
        *,
        player_id: str,
        setup_step: SetupStep,
    ) -> tuple[PreBattleActionRecord, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if type(setup_step) is not SetupStep:
            raise GameLifecycleError("setup_step must be a SetupStep.")
        return tuple(
            record
            for record in self.prebattle_action_records
            if record.player_id == requested_player_id and record.setup_step is setup_step
        )

    def has_tactical_secondary_draw(self, *, player_id: str, battle_round: int) -> bool:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        return any(
            draw.player_id == requested_player_id and draw.battle_round == requested_round
            for draw in self.tactical_secondary_draws
        )

    def draw_tactical_secondary_cards(
        self,
        *,
        player_id: str,
        source_result_id: str,
        draw_count: int | None = None,
    ) -> tuple[SecondaryMissionCardState, ...]:
        if self.mission_setup is None:
            raise GameLifecycleError("Tactical secondary draw requires MissionSetup.")
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        result_id = _validate_identifier("source_result_id", source_result_id)
        requested_draw_count = (
            self.tactical_secondary_draw_count
            if draw_count is None
            else _validate_positive_int("draw_count", draw_count)
        )
        excluded_ids = tuple(
            state.secondary_mission_id
            for state in self.secondary_mission_card_states
            if state.player_id == requested_player_id
        )
        secondary_ids = deterministic_tactical_secondary_draw(
            mission_setup=self.mission_setup,
            player_id=requested_player_id,
            battle_round=self.battle_round,
            draw_count=requested_draw_count,
            excluded_secondary_mission_ids=excluded_ids,
        )
        card_states = tuple(
            SecondaryMissionCardState.active_tactical(
                player_id=requested_player_id,
                secondary_mission_id=secondary_id,
                battle_round=self.battle_round,
                source_result_id=result_id,
            )
            for secondary_id in secondary_ids
        )
        for card_state in card_states:
            self.record_secondary_mission_card_state(card_state)
        return card_states

    def record_fixed_secondary_cards_for_choice(self, choice: SecondaryMissionChoice) -> None:
        if type(choice) is not SecondaryMissionChoice:
            raise GameLifecycleError("choice must be a SecondaryMissionChoice.")
        if choice.mode is not SecondaryMissionMode.FIXED:
            return
        from warhammer40k_core.engine.secondary_scoring_inventory import (
            canonical_secondary_mission_id,
        )

        for secondary_id in choice.fixed_mission_ids:
            recorded_id = canonical_secondary_mission_id(secondary_id)
            if any(
                stored.player_id == choice.player_id
                and stored.mode is SecondaryMissionCardMode.FIXED
                and canonical_secondary_mission_id(stored.secondary_mission_id) == recorded_id
                for stored in self.secondary_mission_card_states
            ):
                continue
            self.record_secondary_mission_card_state(
                SecondaryMissionCardState.active_fixed(
                    player_id=choice.player_id,
                    secondary_mission_id=recorded_id,
                )
            )

    def record_secondary_mission_card_state(
        self,
        card_state: SecondaryMissionCardState,
    ) -> None:
        if type(card_state) is not SecondaryMissionCardState:
            raise GameLifecycleError("card_state must be a SecondaryMissionCardState.")
        if card_state.player_id not in self.player_ids:
            raise GameLifecycleError("SecondaryMissionCardState player_id is not in this game.")
        key = (
            card_state.player_id,
            card_state.secondary_mission_id,
            card_state.mode,
            card_state.battle_round,
        )
        matches = tuple(
            stored
            for stored in self.secondary_mission_card_states
            if (
                stored.player_id,
                stored.secondary_mission_id,
                stored.mode,
                stored.battle_round,
            )
            == key
        )
        if matches:
            if len(matches) != 1 or matches[0] != card_state:
                raise GameLifecycleError("SecondaryMissionCardState already exists.")
            return
        self.secondary_mission_card_states.append(card_state)
        self.secondary_mission_card_states.sort(
            key=lambda state: (
                state.player_id,
                state.battle_round,
                state.mode.value,
                state.secondary_mission_id,
            )
        )

    def secondary_mission_card_state(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        mode: SecondaryMissionCardMode,
    ) -> SecondaryMissionCardState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_secondary_id = _validate_identifier("secondary_mission_id", secondary_mission_id)
        requested_mode = secondary_mission_card_mode_from_token(mode)
        active_matches = [
            state
            for state in self.secondary_mission_card_states
            if state.player_id == requested_player_id
            and state.secondary_mission_id == requested_secondary_id
            and state.mode is requested_mode
            and state.status is SecondaryMissionCardStatus.ACTIVE
        ]
        if not active_matches:
            return None
        if len(active_matches) > 1:
            raise GameLifecycleError("Multiple active secondary card states found.")
        return active_matches[0]

    def score_secondary_mission(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        mode: SecondaryMissionCardMode,
        phase: BattlePhase,
    ) -> SecondaryMissionCardState:
        if self.mission_setup is None:
            raise GameLifecycleError("Secondary mission scoring requires MissionSetup.")
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Secondary mission scoring phase must be a BattlePhase.")
        requested_mode = secondary_mission_card_mode_from_token(mode)
        card_state = self.secondary_mission_card_state(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=requested_mode,
        )
        if card_state is None:
            raise GameLifecycleError("Secondary mission card is not active.")
        policy = mission_scoring_policies_from_setup(self.mission_setup)
        source_kind = (
            VictoryPointSourceKind.FIXED_SECONDARY
            if requested_mode is SecondaryMissionCardMode.FIXED
            else VictoryPointSourceKind.TACTICAL_SECONDARY
        )
        updated_ledgers, transaction = _vp_awards.resolve_victory_point_award_for_game_state(
            state=self,
            award=policy.secondary_award(
                player_id=card_state.player_id,
                battle_round=self.battle_round,
                phase=phase.value,
                secondary_mission_id=card_state.secondary_mission_id,
                source_kind=source_kind,
                hidden=False,
            ),
        )
        if requested_mode is SecondaryMissionCardMode.FIXED:
            self.victory_point_ledgers = updated_ledgers
            return card_state
        from warhammer40k_core.engine.secondary_tactical_achievement import (
            require_positive_tactical_secondary_score_transaction,
        )

        require_positive_tactical_secondary_score_transaction(transaction)
        self.victory_point_ledgers = updated_ledgers
        scored = card_state.score(transaction_id=transaction.transaction_id)
        self.replace_secondary_mission_card_state(scored)
        return scored

    def score_secondary_mission_from_state(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        mode: SecondaryMissionCardMode,
        phase: BattlePhase,
        event_log: EventLog,
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ) -> SecondaryMissionCardState:
        from warhammer40k_core.engine.mission_scoring_transaction import (
            score_secondary_mission_from_state as _score_secondary_mission_from_state,
        )

        return _score_secondary_mission_from_state(
            state=self,
            event_log=event_log,
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=mode,
            phase=phase,
            runtime_modifier_registry=runtime_modifier_registry,
        )

    def record_tactical_secondary_achievement_context(
        self,
        context: TacticalSecondaryAchievementContext,
    ) -> None:
        if type(context) is not TacticalSecondaryAchievementContext:
            raise GameLifecycleError("context must be a TacticalSecondaryAchievementContext.")
        self._validate_current_tactical_secondary_achievement_context(context)
        if any(
            stored.achievement_id == context.achievement_id
            for stored in self.tactical_secondary_achievement_contexts
        ):
            raise GameLifecycleError("Tactical secondary achievement context already exists.")
        if any(
            stored.player_id == context.player_id
            and stored.secondary_mission_id == context.secondary_mission_id
            and stored.card_battle_round == context.card_battle_round
            for stored in self.tactical_secondary_achievement_contexts
        ):
            raise GameLifecycleError(
                "Tactical secondary achievement context already exists for this card."
            )
        self.tactical_secondary_achievement_contexts.append(context)
        self.tactical_secondary_achievement_contexts.sort(
            key=lambda stored: (
                stored.player_id,
                stored.card_battle_round,
                stored.secondary_mission_id,
            )
        )

    def tactical_secondary_achievement_context(
        self,
        achievement_id: str,
    ) -> TacticalSecondaryAchievementContext | None:
        requested_achievement_id = _validate_identifier("achievement_id", achievement_id)
        matches = [
            context
            for context in self.tactical_secondary_achievement_contexts
            if context.achievement_id == requested_achievement_id
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise GameLifecycleError("Multiple Tactical secondary achievement contexts found.")
        return matches[0]

    def consume_tactical_secondary_achievement_context(
        self,
        achievement_id: str,
    ) -> TacticalSecondaryAchievementContext:
        requested_achievement_id = _validate_identifier("achievement_id", achievement_id)
        for index, context in enumerate(self.tactical_secondary_achievement_contexts):
            if context.achievement_id == requested_achievement_id:
                return self.tactical_secondary_achievement_contexts.pop(index)
        raise GameLifecycleError("Tactical secondary achievement context does not exist.")

    def _validate_current_tactical_secondary_achievement_context(
        self,
        context: TacticalSecondaryAchievementContext,
    ) -> None:
        from warhammer40k_core.engine.secondary_tactical_achievement import (
            validate_tactical_secondary_achievement_context,
        )

        validate_tactical_secondary_achievement_context(state=self, context=context)

    def discard_tactical_secondary(
        self,
        *,
        player_id: str,
        secondary_mission_id: str,
        result_id: str,
    ) -> SecondaryMissionCardState:
        card_state = self.secondary_mission_card_state(
            player_id=player_id,
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        if card_state is None:
            raise GameLifecycleError("Tactical secondary card is not active.")
        discarded = card_state.discard(result_id=result_id)
        self.replace_secondary_mission_card_state(discarded)
        return discarded

    def has_tactical_secondary_discard_cp_reward_window(self, window_id: str) -> bool:
        requested_window_id = _validate_identifier("window_id", window_id)
        return requested_window_id in self.tactical_secondary_discard_cp_reward_window_ids

    def record_tactical_secondary_discard_cp_reward_window(self, window_id: str) -> None:
        requested_window_id = _validate_identifier("window_id", window_id)
        if requested_window_id in self.tactical_secondary_discard_cp_reward_window_ids:
            raise GameLifecycleError("Tactical secondary discard CP reward window already used.")
        self.tactical_secondary_discard_cp_reward_window_ids.append(requested_window_id)
        self.tactical_secondary_discard_cp_reward_window_ids.sort()

    def has_tactical_secondary_replacement_use(self, player_id: str) -> bool:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return requested_player_id in self.tactical_secondary_replacement_player_ids

    def record_tactical_secondary_replacement_use(self, player_id: str) -> None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        if requested_player_id in self.tactical_secondary_replacement_player_ids:
            raise GameLifecycleError("Tactical secondary replacement was already used.")
        self.tactical_secondary_replacement_player_ids.append(requested_player_id)
        self.tactical_secondary_replacement_player_ids.sort()

    def replace_secondary_mission_card_state(
        self,
        card_state: SecondaryMissionCardState,
    ) -> None:
        if type(card_state) is not SecondaryMissionCardState:
            raise GameLifecycleError("card_state must be a SecondaryMissionCardState.")
        key = (
            card_state.player_id,
            card_state.secondary_mission_id,
            card_state.mode,
            card_state.battle_round,
        )
        for index, stored in enumerate(self.secondary_mission_card_states):
            stored_key = (
                stored.player_id,
                stored.secondary_mission_id,
                stored.mode,
                stored.battle_round,
            )
            if stored_key == key:
                self.secondary_mission_card_states[index] = card_state
                self.secondary_mission_card_states.sort(
                    key=lambda state: (
                        state.player_id,
                        state.battle_round,
                        state.mode.value,
                        state.secondary_mission_id,
                    )
                )
                return
        raise GameLifecycleError("SecondaryMissionCardState does not exist.")

    def forget_secondary_mission_card_state(self, card_state: SecondaryMissionCardState) -> None:
        if type(card_state) is not SecondaryMissionCardState:
            raise GameLifecycleError("card_state must be a SecondaryMissionCardState.")
        key = (
            card_state.player_id,
            card_state.secondary_mission_id,
            card_state.mode,
            card_state.battle_round,
        )
        for index, stored in enumerate(self.secondary_mission_card_states):
            stored_key = (
                stored.player_id,
                stored.secondary_mission_id,
                stored.mode,
                stored.battle_round,
            )
            if stored_key != key:
                continue
            if stored.status is not SecondaryMissionCardStatus.ACTIVE:
                raise GameLifecycleError("Only active secondary cards can be forgotten.")
            del self.secondary_mission_card_states[index]
            return
        raise GameLifecycleError("SecondaryMissionCardState does not exist.")

    def record_objective_control_record(
        self,
        record: ObjectiveControlRecord,
        *,
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ) -> None:
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "GameState objective_control_record must be an ObjectiveControlRecord."
            )
        if record.game_id != self.game_id:
            raise GameLifecycleError("ObjectiveControlRecord game_id drift.")
        if record.active_player_id not in self.player_ids:
            raise GameLifecycleError("ObjectiveControlRecord active_player_id is not in this game.")
        if record.battle_round != self.battle_round:
            raise GameLifecycleError("ObjectiveControlRecord battle_round drift.")
        if record.phase not in {phase.value for phase in self.battle_phase_sequence}:
            raise GameLifecycleError("ObjectiveControlRecord phase is not in this game.")
        if any(stored.record_id == record.record_id for stored in self.objective_control_records):
            raise GameLifecycleError("ObjectiveControlRecord already exists.")
        authority = _oc_authority.capture_objective_control_record_authority(
            state=self,
            record=record,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        self.objective_control_records.append(record)
        self.objective_control_record_authorities.append(authority)

    def record_sticky_objective_control_state(
        self,
        state: StickyObjectiveControlState,
    ) -> None:
        if type(state) is not StickyObjectiveControlState:
            raise GameLifecycleError(
                "GameState sticky_objective_control_state must be a sticky state."
            )
        if state.game_id != self.game_id:
            raise GameLifecycleError("StickyObjectiveControlState game_id drift.")
        if state.player_id not in self.player_ids or state.active_player_id not in self.player_ids:
            raise GameLifecycleError("StickyObjectiveControlState player_id is not in this game.")
        if any(
            stored.state_id == state.state_id for stored in self.sticky_objective_control_states
        ):
            raise GameLifecycleError("StickyObjectiveControlState already exists.")
        active_for_objective = tuple(
            stored
            for stored in self.sticky_objective_control_states
            if stored.objective_id == state.objective_id
        )
        if any(stored.player_id != state.player_id for stored in active_for_objective):
            raise GameLifecycleError("Sticky objective control cannot be held by multiple players.")
        self.sticky_objective_control_states.append(state)
        self.sticky_objective_control_states.sort(key=lambda stored: stored.state_id)

    def _record_objective_control_record_if_absent(
        self,
        record: ObjectiveControlRecord,
    ) -> None:
        if any(stored.record_id == record.record_id for stored in self.objective_control_records):
            return
        self.record_objective_control_record(record)

    def record_reserve_state(self, reserve_state: ReserveState) -> None:
        if type(reserve_state) is not ReserveState:
            raise GameLifecycleError("reserve_state must be a ReserveState.")
        if reserve_state.player_id not in self.player_ids:
            raise GameLifecycleError("ReserveState player_id is not in this game.")
        validate_reserve_state_rules_unit(
            armies=tuple(self.army_definitions),
            reserve_state=reserve_state,
        )
        if self.reserve_state_for_unit(reserve_state.unit_instance_id) is not None:
            raise GameLifecycleError("ReserveState already exists for unit.")
        self.reserve_states.append(reserve_state)
        self.reserve_states.sort(key=lambda state: state.unit_instance_id)

    def reserve_state_for_unit(self, unit_instance_id: str) -> ReserveState | None:
        return reserve_state_for_rules_unit(
            armies=tuple(self.army_definitions),
            reserve_states=tuple(self.reserve_states),
            unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
        )

    def replace_reserve_state(self, reserve_state: ReserveState) -> None:
        if type(reserve_state) is not ReserveState:
            raise GameLifecycleError("reserve_state must be a ReserveState.")
        validate_reserve_state_rules_unit(
            armies=tuple(self.army_definitions),
            reserve_state=reserve_state,
        )
        for index, stored in enumerate(self.reserve_states):
            if stored.unit_instance_id == reserve_state.unit_instance_id:
                self.reserve_states[index] = reserve_state
                self.reserve_states.sort(key=lambda state: state.unit_instance_id)
                return
        raise GameLifecycleError("ReserveState does not exist for unit.")

    def record_cult_ambush_marker(self, marker: CultAmbushMarker) -> None:
        if type(marker) is not CultAmbushMarker:
            raise GameLifecycleError("cult_ambush_marker must be a CultAmbushMarker.")
        if marker.player_id not in self.player_ids:
            raise GameLifecycleError("CultAmbushMarker player_id is not in this game.")
        if self.cult_ambush_marker_by_id(marker.marker_id) is not None:
            raise GameLifecycleError("CultAmbushMarker already exists.")
        self.cult_ambush_markers.append(marker)
        self.cult_ambush_markers.sort(key=lambda stored: stored.marker_id)

    def cult_ambush_marker_by_id(self, marker_id: str) -> CultAmbushMarker | None:
        requested_marker_id = _validate_identifier("cult_ambush_marker_id", marker_id)
        for marker in self.cult_ambush_markers:
            if marker.marker_id == requested_marker_id:
                return marker
        return None

    def replace_cult_ambush_marker(self, marker: CultAmbushMarker) -> None:
        if type(marker) is not CultAmbushMarker:
            raise GameLifecycleError("cult_ambush_marker must be a CultAmbushMarker.")
        for index, stored in enumerate(self.cult_ambush_markers):
            if stored.marker_id == marker.marker_id:
                self.cult_ambush_markers[index] = marker
                self.cult_ambush_markers.sort(key=lambda stored_marker: stored_marker.marker_id)
                return
        raise GameLifecycleError("CultAmbushMarker does not exist.")

    def remove_cult_ambush_marker(self, marker_id: str) -> CultAmbushMarker:
        requested_marker_id = _validate_identifier("cult_ambush_marker_id", marker_id)
        for index, marker in enumerate(self.cult_ambush_markers):
            if marker.marker_id == requested_marker_id:
                removed = self.cult_ambush_markers.pop(index)
                self.cult_ambush_markers.sort(key=lambda stored: stored.marker_id)
                return removed
        raise GameLifecycleError("CultAmbushMarker does not exist.")

    def reposition_unit_to_strategic_reserves(
        self,
        *,
        decisions: DecisionController,
        player_id: str,
        unit_instance_id: str,
        provider: PrimaryReserveEntryProvider,
        reserve_origin: ReserveOrigin,
        source_rule_ids: tuple[str, ...],
        required_arrival_battle_round: int | None = None,
        required_arrival_phase: BattlePhase | str | None = None,
        required_arrival_source_rule_id: str | None = None,
        required_arrival_placement_kind: str | None = None,
    ) -> ReserveState:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("Repositioned units can only enter reserves during battle.")
        current_phase = self.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("Repositioned units require a current battle phase.")
        if self.battlefield_state is None:
            raise GameLifecycleError("Repositioned units require battlefield_state.")
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        rules_unit_view = rules_unit_view_from_armies(
            armies=tuple(self.army_definitions),
            unit_instance_id=requested_unit_id,
        )
        rules_unit_id = rules_unit_view.unit_instance_id
        if type(provider) is not PrimaryReserveEntryProvider:
            raise GameLifecycleError("Repositioned units require a typed reserve provider.")
        if type(decisions) is not DecisionController:
            raise GameLifecycleError("Repositioned units require DecisionController authority.")
        validate_accepted_primary_reserve_entry_provider(
            state=self,
            decisions=decisions,
            provider=provider,
        )
        requirements = primary_reserve_entry_requirements(
            state=self,
            decisions=decisions,
            provider=provider,
        )
        requested_arrival_phase = (
            None if required_arrival_phase is None else BattlePhase(required_arrival_phase).value
        )
        if (
            required_arrival_battle_round != requirements.required_arrival_battle_round
            or requested_arrival_phase != requirements.required_arrival_phase
            or required_arrival_source_rule_id != requirements.required_arrival_source_rule_id
            or required_arrival_placement_kind != requirements.required_arrival_placement_kind
        ):
            raise GameLifecycleError("Repositioned unit required-arrival authority drift.")
        origin = reserve_origin_from_token(reserve_origin)
        if origin not in {
            ReserveOrigin.DURING_BATTLE_ABILITY,
            ReserveOrigin.DURING_BATTLE_STRATAGEM,
        }:
            raise GameLifecycleError(
                "Repositioned units require an ability or Stratagem reserve origin."
            )
        if (
            provider.reserve_origin is not origin
            or provider.player_id != requested_player_id
            or provider.target_rules_unit_instance_id != rules_unit_id
            or source_rule_ids != (provider.source_rule_id,)
        ):
            raise GameLifecycleError("Repositioned unit reserve provider context drift.")
        if rules_unit_view.owner_player_id != requested_player_id:
            raise GameLifecycleError("Repositioned unit player_id drift.")
        existing_reserve_state = self.reserve_state_for_unit(rules_unit_id)
        if existing_reserve_state is not None and existing_reserve_state.status in {
            ReserveStatus.IN_RESERVES,
            ReserveStatus.DESTROYED,
        }:
            raise GameLifecycleError("Repositioned unit has a non-terminal-arrival ReserveState.")
        rules_unit_placement = RulesUnitPlacement.from_battlefield(
            view=rules_unit_view,
            battlefield_state=self.battlefield_state,
        )
        embarked_unit_ids: set[str] = set()
        for component_unit_id in rules_unit_placement.component_unit_instance_ids:
            cargo_state = self.transport_cargo_state_for_transport(component_unit_id)
            if cargo_state is not None:
                embarked_unit_ids.update(cargo_state.embarked_unit_instance_ids)
        policy = _arrival.reposition_destruction_policy(
            mission_setup=self.mission_setup,
            destruction_deadline_policy=None,
        )
        reserve_state = ReserveState.entered_during_battle(
            player_id=requested_player_id,
            unit_instance_id=rules_unit_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            battle_round=self.battle_round,
            phase=current_phase,
            reserve_origin=origin,
            destruction_deadline_policy=policy,
            embarked_unit_instance_ids=tuple(sorted(embarked_unit_ids)),
            source_rule_ids=source_rule_ids,
            required_arrival_battle_round=required_arrival_battle_round,
            required_arrival_phase=required_arrival_phase,
            required_arrival_source_rule_id=required_arrival_source_rule_id,
            required_arrival_placement_kind=required_arrival_placement_kind,
        )
        updated_battlefield = rules_unit_placement.without_from_battlefield(self.battlefield_state)
        physical_component_ids = rules_unit_placement.component_unit_instance_ids
        departure = prepare_primary_battlefield_departure(
            state=self,
            battlefield_state=updated_battlefield,
            rules_unit_instance_id=rules_unit_id,
            affected_component_unit_instance_ids=physical_component_ids,
            departed_component_unit_instance_ids=physical_component_ids,
            removed_model_instance_ids=tuple(
                placement.model_instance_id for placement in rules_unit_placement.model_placements
            ),
            removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
            occurrence_id=provider.occurrence_id,
            source_id=provider.occurrence_id,
        )
        if existing_reserve_state is None:
            self.record_reserve_state(reserve_state)
        else:
            self.replace_reserve_state(reserve_state)
        self.battlefield_state = updated_battlefield
        record_prepared_primary_battlefield_departure(
            state=self,
            departure=departure,
        )
        if departure is not None:
            record_primary_reserve_entry_mutation_event(
                event_log=decisions.event_log,
                departure=departure,
                reserve_state=reserve_state,
                provider=provider,
                transition_batch=None,
            )
            record_primary_battlefield_departure_event(
                event_log=decisions.event_log,
                departure=departure,
            )
        return reserve_state

    def record_hover_mode_state(self, hover_mode_state: HoverModeState) -> None:
        if type(hover_mode_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_state must be a HoverModeState.")
        if hover_mode_state.player_id not in self.player_ids:
            raise GameLifecycleError("HoverModeState player_id is not in this game.")
        if self.hover_mode_state_for_unit(hover_mode_state.unit_instance_id) is not None:
            raise GameLifecycleError("HoverModeState already exists for unit.")
        _validate_hover_mode_state_reference(self, hover_mode_state)
        self.hover_mode_states.append(hover_mode_state)
        self.hover_mode_states.sort(key=lambda state: state.unit_instance_id)

    def hover_mode_state_for_unit(self, unit_instance_id: str) -> HoverModeState | None:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for hover_mode_state in self.hover_mode_states:
            if hover_mode_state.unit_instance_id == requested_unit_id:
                return hover_mode_state
        return None

    def unarrived_reserve_states_for_player(self, player_id: str) -> tuple[ReserveState, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return tuple(
            reserve_state
            for reserve_state in self.reserve_states
            if reserve_state.player_id == requested_player_id
            and reserve_state.status is ReserveStatus.IN_RESERVES
        )

    def unarrived_reserve_model_ids(self) -> tuple[str, ...]:
        return unarrived_reserve_model_ids(
            armies=tuple(self.army_definitions),
            reserve_states=tuple(self.reserve_states),
        )

    def embarked_model_ids(self) -> tuple[str, ...]:
        if not self.transport_cargo_states:
            return ()
        unit_by_id = {
            unit.unit_instance_id: unit for army in self.army_definitions for unit in army.units
        }
        model_ids: set[str] = set()
        for cargo_state in self.transport_cargo_states:
            for unit_id in cargo_state.embarked_unit_instance_ids:
                unit = unit_by_id.get(unit_id)
                if unit is None:
                    raise GameLifecycleError("TransportCargoState references an unknown unit.")
                model_ids.update(
                    model.model_instance_id for model in unit.own_models if model.is_alive
                )
        return tuple(sorted(model_ids))

    def unavailable_model_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    *self.unarrived_reserve_model_ids(),
                    *self.embarked_model_ids(),
                    *self.dedicated_transport_setup_consequence_model_ids(),
                }
            )
        )

    def dedicated_transport_setup_consequence_model_ids(self) -> tuple[str, ...]:
        if not self.dedicated_transport_setup_consequences:
            return ()
        unit_by_id = {
            unit.unit_instance_id: unit for army in self.army_definitions for unit in army.units
        }
        model_ids: list[str] = []
        for consequence in self.dedicated_transport_setup_consequences:
            unit = unit_by_id.get(consequence.transport_unit_instance_id)
            if unit is None:
                raise GameLifecycleError(
                    "DedicatedTransportSetupConsequence references an unknown Transport."
                )
            model_ids.extend(model.model_instance_id for model in unit.own_models)
        return tuple(sorted(model_ids))

    def record_dedicated_transport_setup_consequence(
        self,
        consequence: DedicatedTransportSetupConsequence,
    ) -> None:
        if type(consequence) is not DedicatedTransportSetupConsequence:
            raise GameLifecycleError("consequence must be a DedicatedTransportSetupConsequence.")
        if consequence.player_id not in self.player_ids:
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence player_id is not in this game."
            )
        if (
            self.dedicated_transport_setup_consequence_for_transport(
                consequence.transport_unit_instance_id
            )
            is not None
        ):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence already exists for Transport."
            )
        if self.transport_cargo_state_for_transport(consequence.transport_unit_instance_id):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence Transport already has cargo."
            )
        unit_owner_by_id = _unit_owner_by_id(self.army_definitions)
        owner = unit_owner_by_id.get(consequence.transport_unit_instance_id)
        if owner is None:
            raise GameLifecycleError("DedicatedTransportSetupConsequence Transport is unknown.")
        if owner != consequence.player_id:
            raise GameLifecycleError("DedicatedTransportSetupConsequence player_id drift.")
        transport = self._unit_by_id(consequence.transport_unit_instance_id)
        if not _unit_has_keyword(transport, "DEDICATED TRANSPORT"):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence requires a DEDICATED TRANSPORT unit."
            )
        self.dedicated_transport_setup_consequences.append(consequence)
        self.dedicated_transport_setup_consequences.sort(
            key=lambda record: record.transport_unit_instance_id
        )

    def dedicated_transport_setup_consequence_for_transport(
        self,
        transport_unit_instance_id: str,
    ) -> DedicatedTransportSetupConsequence | None:
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        for consequence in self.dedicated_transport_setup_consequences:
            if consequence.transport_unit_instance_id == requested_transport_id:
                return consequence
        return None

    def record_transport_cargo_state(self, cargo_state: TransportCargoState) -> None:
        if type(cargo_state) is not TransportCargoState:
            raise GameLifecycleError("cargo_state must be a TransportCargoState.")
        if cargo_state.player_id not in self.player_ids:
            raise GameLifecycleError("TransportCargoState player_id is not in this game.")
        if (
            self.transport_cargo_state_for_transport(cargo_state.transport_unit_instance_id)
            is not None
        ):
            raise GameLifecycleError("TransportCargoState already exists for transport.")
        if (
            self.dedicated_transport_setup_consequence_for_transport(
                cargo_state.transport_unit_instance_id
            )
            is not None
        ):
            raise GameLifecycleError("TransportCargoState Transport already has a consequence.")
        self.transport_cargo_states.append(cargo_state)
        self.transport_cargo_states.sort(key=lambda state: state.transport_unit_instance_id)

    def transport_cargo_state_for_transport(
        self,
        transport_unit_instance_id: str,
    ) -> TransportCargoState | None:
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        for cargo_state in self.transport_cargo_states:
            if cargo_state.transport_unit_instance_id == requested_transport_id:
                return cargo_state
        return None

    def transport_cargo_state_for_embarked_unit(
        self,
        embarked_unit_instance_id: str,
    ) -> TransportCargoState | None:
        return _queries.transport_cargo_state_for_embarked_unit(
            state=self,
            embarked_unit_instance_id=embarked_unit_instance_id,
        )

    def replace_transport_cargo_state(self, cargo_state: TransportCargoState) -> None:
        if type(cargo_state) is not TransportCargoState:
            raise GameLifecycleError("cargo_state must be a TransportCargoState.")
        for index, stored in enumerate(self.transport_cargo_states):
            if stored.transport_unit_instance_id == cargo_state.transport_unit_instance_id:
                self.transport_cargo_states[index] = cargo_state
                self.transport_cargo_states.sort(key=lambda state: state.transport_unit_instance_id)
                return
        raise GameLifecycleError("TransportCargoState does not exist for transport.")

    def remove_transport_cargo_state(self, transport_unit_instance_id: str) -> TransportCargoState:
        requested_transport_id = _validate_identifier(
            "transport_unit_instance_id",
            transport_unit_instance_id,
        )
        for index, stored in enumerate(self.transport_cargo_states):
            if stored.transport_unit_instance_id == requested_transport_id:
                return self.transport_cargo_states.pop(index)
        raise GameLifecycleError("TransportCargoState does not exist for transport.")

    def record_disembarked_unit_state(self, state: DisembarkedUnitState) -> None:
        if type(state) is not DisembarkedUnitState:
            raise GameLifecycleError("Disembarked unit state must be a DisembarkedUnitState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("DisembarkedUnitState player_id is not in this game.")
        if state.turn_player_id not in self.player_ids:
            raise GameLifecycleError("DisembarkedUnitState turn_player_id is not in this game.")
        if self.stage is not GameLifecycleStage.BATTLE or self.active_player_id is None:
            raise GameLifecycleError("DisembarkedUnitState requires an active battle turn.")
        if state.battle_round != self.battle_round:
            raise GameLifecycleError("DisembarkedUnitState battle round drift.")
        if state.turn_player_id != self.active_player_id:
            raise GameLifecycleError("DisembarkedUnitState turn player drift.")
        if (
            self.disembarked_unit_state_for_unit(
                player_id=state.player_id,
                battle_round=state.battle_round,
                unit_instance_id=state.unit_instance_id,
            )
            is not None
        ):
            raise GameLifecycleError("DisembarkedUnitState already exists for unit and turn.")
        self.disembarked_unit_states.append(state)
        self.disembarked_unit_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.turn_player_id,
                stored.player_id,
                stored.unit_instance_id,
            )
        )

    def disembarked_unit_state_for_unit(
        self,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
    ) -> DisembarkedUnitState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for state in self.disembarked_unit_states:
            if (
                state.player_id == requested_player_id
                and state.battle_round == requested_round
                and state.unit_instance_id == requested_unit_id
            ):
                return state
        return None

    def record_advanced_unit_state(self, state: AdvancedUnitState) -> None:
        if type(state) is not AdvancedUnitState:
            raise GameLifecycleError("Advanced unit state must be an AdvancedUnitState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("AdvancedUnitState player_id is not in this game.")
        if (
            self.advanced_unit_state_for_unit(
                player_id=state.player_id,
                battle_round=state.battle_round,
                unit_instance_id=state.unit_instance_id,
            )
            is not None
        ):
            raise GameLifecycleError("AdvancedUnitState already exists for unit and turn.")
        self.advanced_unit_states.append(state)
        self.advanced_unit_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.player_id,
                stored.unit_instance_id,
            )
        )

    def advanced_unit_state_for_unit(
        self,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
    ) -> AdvancedUnitState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for state in self.advanced_unit_states:
            if (
                state.player_id == requested_player_id
                and state.battle_round == requested_round
                and state.unit_instance_id == requested_unit_id
            ):
                return state
        return None

    def record_fell_back_unit_state(self, state: FellBackUnitState) -> None:
        if type(state) is not FellBackUnitState:
            raise GameLifecycleError("Fell Back unit state must be a FellBackUnitState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("FellBackUnitState player_id is not in this game.")
        if (
            self.fell_back_unit_state_for_unit(
                player_id=state.player_id,
                battle_round=state.battle_round,
                unit_instance_id=state.unit_instance_id,
            )
            is not None
        ):
            raise GameLifecycleError("FellBackUnitState already exists for unit and turn.")
        self.fell_back_unit_states.append(state)
        self.fell_back_unit_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.player_id,
                stored.unit_instance_id,
            )
        )

    def fell_back_unit_state_for_unit(
        self,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
    ) -> FellBackUnitState | None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for state in self.fell_back_unit_states:
            if (
                state.player_id == requested_player_id
                and state.battle_round == requested_round
                and state.unit_instance_id == requested_unit_id
            ):
                return state
        return None

    def record_normal_move_state(self, state: NormalMoveState) -> None:
        if type(state) is not NormalMoveState:
            raise GameLifecycleError("Normal move state must be a NormalMoveState.")
        if state.player_id not in self.player_ids:
            raise GameLifecycleError("NormalMoveState player_id is not in this game.")
        if any(stored.result_id == state.result_id for stored in self.normal_move_states):
            raise GameLifecycleError("NormalMoveState already exists for result_id.")
        if any(
            stored.same_phase_key() == state.same_phase_key() for stored in self.normal_move_states
        ):
            raise GameLifecycleError("NormalMoveState already exists for unit in this phase.")
        self.normal_move_states.append(state)
        self.normal_move_states.sort(
            key=lambda stored: (
                stored.battle_round,
                stored.phase,
                stored.player_id,
                stored.unit_instance_id,
                stored.result_id,
            )
        )

    def normal_move_states_for_unit_phase(
        self,
        *,
        player_id: str,
        battle_round: int,
        phase: BattlePhase,
        unit_instance_id: str,
    ) -> tuple[NormalMoveState, ...]:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        if type(phase) is not BattlePhase:
            raise GameLifecycleError("Normal move state query phase must be a BattlePhase.")
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return tuple(
            state
            for state in self.normal_move_states
            if state.player_id == requested_player_id
            and state.battle_round == requested_round
            and state.phase is phase
            and state.unit_instance_id == requested_unit_id
        )

    def to_payload(self) -> GameStatePayload:
        return {
            "game_id": self.game_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "rules_overlay_ids": list(self.rules_overlay_ids),
            "stage": self.stage.value,
            "setup_sequence": [step.value for step in self.setup_sequence],
            "battle_phase_sequence": [phase.value for phase in self.battle_phase_sequence],
            "setup_step_index": self.setup_step_index,
            "battle_phase_index": self.battle_phase_index,
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "player_ids": list(self.player_ids),
            "turn_order": list(self.turn_order),
            "decision_request_count": self.decision_request_count,
            "tactical_secondary_draw_count": self.tactical_secondary_draw_count,
            "command_step_state": (
                None if self.command_step_state is None else self.command_step_state.to_payload()
            ),
            "command_point_ledgers": [ledger.to_payload() for ledger in self.command_point_ledgers],
            "victory_point_ledgers": [ledger.to_payload() for ledger in self.victory_point_ledgers],
            "faction_resource_ledgers": [
                ledger.to_payload() for ledger in self.faction_resource_ledgers
            ],
            "unit_resource_ledgers": [ledger.to_payload() for ledger in self.unit_resource_ledgers],
            "stratagem_use_records": [record.to_payload() for record in self.stratagem_use_records],
            "faction_rule_states": [state.to_payload() for state in self.faction_rule_states],
            "army_definitions": [army.to_payload() for army in self.army_definitions],
            "starting_strength_records": [
                record.to_payload() for record in self.starting_strength_records
            ],
            "starting_attached_unit_records": [
                record.to_payload() for record in self.starting_attached_unit_records
            ],
            "battlefield_state": (
                None if self.battlefield_state is None else self.battlefield_state.to_payload()
            ),
            "mission_setup": None
            if self.mission_setup is None
            else self.mission_setup.to_payload(),
            "movement_phase_state": (
                None
                if self.movement_phase_state is None
                else self.movement_phase_state.to_payload()
            ),
            "pending_catalog_selected_target_battle_shock_continuation": (
                None
                if self.pending_catalog_selected_target_battle_shock_continuation is None
                else self.pending_catalog_selected_target_battle_shock_continuation.to_payload()
            ),
            "charge_phase_state": (
                None if self.charge_phase_state is None else self.charge_phase_state.to_payload()
            ),
            "fight_phase_state": (
                None if self.fight_phase_state is None else self.fight_phase_state.to_payload()
            ),
            "shooting_phase_state": (
                None
                if self.shooting_phase_state is None
                else self.shooting_phase_state.to_payload()
            ),
            "out_of_phase_shooting_state": (
                None
                if self.out_of_phase_shooting_state is None
                else self.out_of_phase_shooting_state.to_payload()
            ),
            "feel_no_pain_sources_by_model_id": {
                model_id: [source.to_payload() for source in sources]
                for model_id, sources in self.feel_no_pain_sources_by_model_id.items()
            },
            "feel_no_pain_decline_allowed_model_ids": list(
                self.feel_no_pain_decline_allowed_model_ids
            ),
            "destruction_reaction_sources_by_model_id": {
                model_id: [source.to_payload() for source in sources]
                for model_id, sources in self.destruction_reaction_sources_by_model_id.items()
            },
            "one_shot_weapon_use_records": [
                record.to_payload() for record in self.one_shot_weapon_use_records
            ],
            "ranged_attack_history_records": [
                record.to_payload() for record in self.ranged_attack_history_records
            ],
            "model_destruction_cause_authorities": [
                authority.to_payload() for authority in self.model_destruction_cause_authorities
            ],
            "reserve_states": [state.to_payload() for state in self.reserve_states],
            "cult_ambush_markers": [marker.to_payload() for marker in self.cult_ambush_markers],
            "hover_mode_states": [state.to_payload() for state in self.hover_mode_states],
            "transport_cargo_states": [state.to_payload() for state in self.transport_cargo_states],
            "dedicated_transport_setup_consequences": [
                consequence.to_payload()
                for consequence in self.dedicated_transport_setup_consequences
            ],
            "disembarked_unit_states": [
                state.to_payload() for state in self.disembarked_unit_states
            ],
            "advanced_unit_states": [state.to_payload() for state in self.advanced_unit_states],
            "fell_back_unit_states": [state.to_payload() for state in self.fell_back_unit_states],
            "normal_move_states": [state.to_payload() for state in self.normal_move_states],
            "battle_shocked_unit_ids": list(self.battle_shocked_unit_ids),
            "battle_shocked_unit_states": [
                state.to_payload() for state in self.battle_shocked_unit_states
            ],
            "objective_control_records": [
                record.to_payload() for record in self.objective_control_records
            ],
            "objective_control_record_authorities": [
                authority.to_payload() for authority in self.objective_control_record_authorities
            ],
            "primary_scoring_state_evidence_records": [
                evidence.to_payload() for evidence in self.primary_scoring_state_evidence_records
            ],
            "secondary_scoring_state_evidence_records": [
                evidence.to_payload() for evidence in self.secondary_scoring_state_evidence_records
            ],
            "primary_scoring_boundary_lifecycles": [
                row.to_payload() for row in self.primary_scoring_boundary_lifecycles
            ],
            "sticky_objective_control_states": [
                state.to_payload() for state in self.sticky_objective_control_states
            ],
            "primary_objective_turn_start_states": [
                state.to_payload() for state in self.primary_objective_turn_start_states
            ],
            "primary_rules_unit_turn_start_snapshots": [
                snapshot.to_payload() for snapshot in self.primary_rules_unit_turn_start_snapshots
            ],
            "primary_terrain_trap_states": [
                state.to_payload() for state in self.primary_terrain_trap_states
            ],
            "primary_unit_destruction_states": [
                state.to_payload() for state in self.primary_unit_destruction_states
            ],
            "primary_battlefield_departure_states": [
                state.to_payload() for state in self.primary_battlefield_departure_states
            ],
            "secondary_unit_destruction_states": [
                state.to_payload() for state in self.secondary_unit_destruction_states
            ],
            "secondary_objective_cleanse_states": [
                state.to_payload() for state in self.secondary_objective_cleanse_states
            ],
            "secondary_terrain_plunder_states": [
                state.to_payload() for state in self.secondary_terrain_plunder_states
            ],
            "mission_action_states": [state.to_payload() for state in self.mission_action_states],
            "primary_mission_progress_state": self.primary_mission_progress_state.to_payload(),
            "end_turn_cleanup_states": [
                state.to_payload() for state in self.end_turn_cleanup_states
            ],
            "scoring_window_states": [state.to_payload() for state in self.scoring_window_states],
            "persisting_effects": [effect.to_payload() for effect in self.persisting_effects],
            "tracked_target_records": [
                record.to_payload() for record in self.tracked_target_records
            ],
            "pending_return_on_death": [
                pending.to_payload() for pending in self.pending_return_on_death
            ],
            "return_on_death_consumed_keys": list(self.return_on_death_consumed_keys),
            "secondary_mission_choices": [
                choice.to_payload() for choice in self.secondary_mission_choices
            ],
            "tactical_secondary_draws": [
                draw.to_payload() for draw in self.tactical_secondary_draws
            ],
            "prebattle_action_records": [
                record.to_payload() for record in self.prebattle_action_records
            ],
            "prebattle_alternation_cursor": (
                None
                if self.prebattle_alternation_cursor is None
                else self.prebattle_alternation_cursor.to_payload()
            ),
            "secondary_mission_card_states": [
                state.to_payload() for state in self.secondary_mission_card_states
            ],
            "tactical_secondary_achievement_contexts": [
                context.to_payload() for context in self.tactical_secondary_achievement_contexts
            ],
            "tactical_secondary_discard_cp_reward_window_ids": list(
                self.tactical_secondary_discard_cp_reward_window_ids
            ),
            "tactical_secondary_replacement_player_ids": list(
                self.tactical_secondary_replacement_player_ids
            ),
        }

    def to_public_payload(self, *, viewer_player_id: str) -> dict[str, JsonValue]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        secondary_mission_choices_revealed = self.secondary_mission_choices_are_revealed()
        public_choices: list[dict[str, JsonValue]] = []
        for player_id in self.player_ids:
            choice = self.secondary_mission_choice_for_player(player_id)
            if choice is None:
                public_choices.append(
                    {
                        "player_id": player_id,
                        "selected": False,
                        "hidden": player_id != viewer,
                    }
                )
                continue
            public_choices.append(
                choice.to_public_payload(
                    viewer_player_id=viewer,
                    secondary_mission_choices_revealed=secondary_mission_choices_revealed,
                )
            )

        payload = cast(dict[str, JsonValue], self.to_payload())
        payload["objective_control_record_authorities"] = []
        payload["model_destruction_cause_authorities"] = []
        payload["primary_scoring_state_evidence_records"] = []
        payload["secondary_scoring_state_evidence_records"] = []
        payload["primary_scoring_boundary_lifecycles"] = []
        payload["secondary_mission_choices"] = cast(JsonValue, public_choices)
        payload["victory_point_ledgers"] = [
            ledger.to_public_payload(
                viewer_player_id=viewer,
                secondary_mission_choices_revealed=secondary_mission_choices_revealed,
            )
            for ledger in self.victory_point_ledgers
        ]
        payload["command_point_ledgers"] = [
            cast(JsonValue, ledger.to_payload()) for ledger in self.command_point_ledgers
        ]
        payload["faction_resource_ledgers"] = [
            cast(JsonValue, ledger.to_payload()) for ledger in self.faction_resource_ledgers
        ]
        payload["unit_resource_ledgers"] = []
        payload["stratagem_use_records"] = [
            cast(JsonValue, record.to_payload()) for record in self.stratagem_use_records
        ]
        payload["secondary_mission_card_states"] = cast(
            JsonValue,
            self.public_secondary_mission_card_states(viewer_player_id=viewer),
        )
        payload["tactical_secondary_draws"] = cast(
            JsonValue,
            self.public_tactical_secondary_draws(viewer_player_id=viewer),
        )
        payload["mission_action_states"] = cast(
            JsonValue,
            self.public_mission_action_states(viewer_player_id=viewer),
        )
        payload["prebattle_action_records"] = cast(
            JsonValue,
            [cast(JsonValue, record.to_payload()) for record in self.prebattle_action_records],
        )
        payload["secondary_unit_destruction_states"] = cast(
            JsonValue,
            [
                cast(JsonValue, state.to_payload())
                for state in self.secondary_unit_destruction_states
                if secondary_mission_choices_revealed or state.destroyed_player_id != viewer
            ],
        )
        payload["secondary_objective_cleanse_states"] = cast(
            JsonValue,
            [
                cast(JsonValue, state.to_payload())
                for state in self.secondary_objective_cleanse_states
                if secondary_mission_choices_revealed or state.player_id == viewer
            ],
        )
        payload["secondary_terrain_plunder_states"] = cast(
            JsonValue,
            [
                cast(JsonValue, state.to_payload())
                for state in self.secondary_terrain_plunder_states
                if secondary_mission_choices_revealed or state.player_id == viewer
            ],
        )
        payload["tactical_secondary_achievement_contexts"] = []
        validate_json_value(payload)
        return payload

    def public_secondary_mission_card_states(
        self,
        *,
        viewer_player_id: str,
    ) -> list[dict[str, JsonValue]]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        secondary_mission_choices_revealed = self.secondary_mission_choices_are_revealed()
        return [
            state.to_public_payload(
                viewer_player_id=viewer,
                secondary_mission_choices_revealed=secondary_mission_choices_revealed,
            )
            for state in self.secondary_mission_card_states
            if secondary_mission_choices_revealed or state.player_id == viewer
        ]

    def public_tactical_secondary_draws(
        self,
        *,
        viewer_player_id: str,
    ) -> list[dict[str, JsonValue]]:
        viewer = _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        secondary_mission_choices_revealed = self.secondary_mission_choices_are_revealed()
        return [
            cast(dict[str, JsonValue], draw.to_payload())
            for draw in self.tactical_secondary_draws
            if secondary_mission_choices_revealed or draw.player_id == viewer
        ]

    def public_mission_action_states(
        self,
        *,
        viewer_player_id: str,
    ) -> list[dict[str, JsonValue]]:
        _validate_player_id(viewer_player_id, player_ids=self.player_ids)
        return [
            cast(dict[str, JsonValue], action_state.to_payload())
            for action_state in self.mission_action_states
        ]

    @classmethod
    def from_payload(cls, payload: GameStatePayload) -> Self:
        return cls(
            game_id=payload["game_id"],
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            rules_overlay_ids=tuple(payload["rules_overlay_ids"]),
            stage=game_lifecycle_stage_from_token(payload["stage"]),
            setup_sequence=tuple(
                setup_step_kind_from_token(step) for step in payload["setup_sequence"]
            ),
            battle_phase_sequence=tuple(
                battle_phase_kind_from_token(phase) for phase in payload["battle_phase_sequence"]
            ),
            player_ids=tuple(payload["player_ids"]),
            turn_order=tuple(payload["turn_order"]),
            tactical_secondary_draw_count=payload["tactical_secondary_draw_count"],
            setup_step_index=payload["setup_step_index"],
            battle_phase_index=payload["battle_phase_index"],
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            decision_request_count=payload["decision_request_count"],
            command_step_state=(
                None
                if payload["command_step_state"] is None
                else CommandStepState.from_payload(payload["command_step_state"])
            ),
            command_point_ledgers=[
                CommandPointLedger.from_payload(ledger)
                for ledger in payload["command_point_ledgers"]
            ],
            victory_point_ledgers=[
                VictoryPointLedger.from_payload(ledger)
                for ledger in payload["victory_point_ledgers"]
            ],
            faction_resource_ledgers=[
                FactionResourceLedger.from_payload(ledger)
                for ledger in payload["faction_resource_ledgers"]
            ],
            unit_resource_ledgers=[
                UnitResourceLedger.from_payload(ledger)
                for ledger in payload["unit_resource_ledgers"]
            ],
            stratagem_use_records=[
                StratagemUseRecord.from_payload(record)
                for record in payload["stratagem_use_records"]
            ],
            faction_rule_states=[
                FactionRuleState.from_payload(state) for state in payload["faction_rule_states"]
            ],
            army_definitions=[
                _army_definition_from_payload(army) for army in payload["army_definitions"]
            ],
            starting_strength_records=[
                StartingStrengthRecord.from_payload(record)
                for record in payload["starting_strength_records"]
            ],
            starting_attached_unit_records=[
                StartingAttachedUnitRecord.from_payload(record)
                for record in payload["starting_attached_unit_records"]
            ],
            battlefield_state=(
                None
                if payload["battlefield_state"] is None
                else _battlefield_state_from_payload(payload["battlefield_state"])
            ),
            mission_setup=(
                None
                if payload["mission_setup"] is None
                else MissionSetup.from_payload(payload["mission_setup"])
            ),
            movement_phase_state=(
                None
                if payload["movement_phase_state"] is None
                else MovementPhaseState.from_payload(payload["movement_phase_state"])
            ),
            pending_catalog_selected_target_battle_shock_continuation=(
                None
                if payload["pending_catalog_selected_target_battle_shock_continuation"] is None
                else PendingCatalogSelectedTargetBattleShockContinuation.from_payload(
                    payload["pending_catalog_selected_target_battle_shock_continuation"]
                )
            ),
            charge_phase_state=(
                None
                if payload["charge_phase_state"] is None
                else ChargePhaseState.from_payload(payload["charge_phase_state"])
            ),
            fight_phase_state=(
                None
                if payload["fight_phase_state"] is None
                else FightPhaseState.from_payload(payload["fight_phase_state"])
            ),
            shooting_phase_state=(
                None
                if payload["shooting_phase_state"] is None
                else ShootingPhaseState.from_payload(payload["shooting_phase_state"])
            ),
            out_of_phase_shooting_state=(
                None
                if payload["out_of_phase_shooting_state"] is None
                else OutOfPhaseShootingState.from_payload(payload["out_of_phase_shooting_state"])
            ),
            feel_no_pain_sources_by_model_id={
                model_id: tuple(FeelNoPainSource.from_payload(source) for source in sources)
                for model_id, sources in payload["feel_no_pain_sources_by_model_id"].items()
            },
            feel_no_pain_decline_allowed_model_ids=list(
                payload["feel_no_pain_decline_allowed_model_ids"]
            ),
            destruction_reaction_sources_by_model_id={
                model_id: tuple(
                    DestructionReactionSource.from_payload(source) for source in sources
                )
                for model_id, sources in payload["destruction_reaction_sources_by_model_id"].items()
            },
            one_shot_weapon_use_records=[
                OneShotWeaponUseRecord.from_payload(record)
                for record in payload["one_shot_weapon_use_records"]
            ],
            ranged_attack_history_records=[
                RangedAttackHistoryRecord.from_payload(record)
                for record in payload["ranged_attack_history_records"]
            ],
            model_destruction_cause_authorities=[
                _mdca.ModelDestructionCauseAuthority.from_payload(authority)
                for authority in payload["model_destruction_cause_authorities"]
            ],
            reserve_states=[
                ReserveState.from_payload(state) for state in payload["reserve_states"]
            ],
            cult_ambush_markers=[
                CultAmbushMarker.from_payload(marker) for marker in payload["cult_ambush_markers"]
            ],
            hover_mode_states=[
                HoverModeState.from_payload(state) for state in payload["hover_mode_states"]
            ],
            transport_cargo_states=[
                TransportCargoState.from_payload(state)
                for state in payload["transport_cargo_states"]
            ],
            dedicated_transport_setup_consequences=[
                DedicatedTransportSetupConsequence.from_payload(consequence)
                for consequence in payload["dedicated_transport_setup_consequences"]
            ],
            disembarked_unit_states=[
                DisembarkedUnitState.from_payload(state)
                for state in payload["disembarked_unit_states"]
            ],
            advanced_unit_states=[
                AdvancedUnitState.from_payload(state) for state in payload["advanced_unit_states"]
            ],
            fell_back_unit_states=[
                FellBackUnitState.from_payload(state) for state in payload["fell_back_unit_states"]
            ],
            normal_move_states=[
                NormalMoveState.from_payload(state) for state in payload["normal_move_states"]
            ],
            battle_shocked_unit_ids=list(payload["battle_shocked_unit_ids"]),
            battle_shocked_unit_states=[
                BattleShockedUnitState.from_payload(state)
                for state in payload["battle_shocked_unit_states"]
            ],
            objective_control_records=[
                ObjectiveControlRecord.from_payload(record)
                for record in payload["objective_control_records"]
            ],
            objective_control_record_authorities=[
                _oc_authority.ObjectiveControlRecordAuthority.from_payload(authority)
                for authority in payload["objective_control_record_authorities"]
            ],
            primary_scoring_state_evidence_records=[
                PrimaryScoringStateEvidence.from_payload(evidence)
                for evidence in payload["primary_scoring_state_evidence_records"]
            ],
            secondary_scoring_state_evidence_records=[
                SecondaryScoringStateEvidence.from_payload(evidence)
                for evidence in payload["secondary_scoring_state_evidence_records"]
            ],
            primary_scoring_boundary_lifecycles=[
                PrimaryScoringBoundaryLifecycle.from_payload(row)
                for row in payload["primary_scoring_boundary_lifecycles"]
            ],
            sticky_objective_control_states=[
                StickyObjectiveControlState.from_payload(state)
                for state in payload["sticky_objective_control_states"]
            ],
            primary_objective_turn_start_states=[
                PrimaryObjectiveTurnStartState.from_payload(state)
                for state in payload["primary_objective_turn_start_states"]
            ],
            primary_rules_unit_turn_start_snapshots=(
                primary_rules_unit_turn_start_snapshots_from_payload(
                    payload["primary_rules_unit_turn_start_snapshots"]
                )
            ),
            primary_terrain_trap_states=[
                PrimaryTerrainTrapState.from_payload(state)
                for state in payload["primary_terrain_trap_states"]
            ],
            primary_unit_destruction_states=[
                PrimaryUnitDestructionState.from_payload(state)
                for state in payload["primary_unit_destruction_states"]
            ],
            primary_battlefield_departure_states=(
                primary_battlefield_departure_states_from_payload(
                    payload["primary_battlefield_departure_states"]
                )
            ),
            secondary_unit_destruction_states=[
                SecondaryUnitDestructionState.from_payload(state)
                for state in payload["secondary_unit_destruction_states"]
            ],
            secondary_objective_cleanse_states=[
                SecondaryObjectiveCleanseState.from_payload(state)
                for state in payload["secondary_objective_cleanse_states"]
            ],
            secondary_terrain_plunder_states=[
                SecondaryTerrainPlunderState.from_payload(state)
                for state in payload["secondary_terrain_plunder_states"]
            ],
            mission_action_states=[
                MissionActionState.from_payload(state) for state in payload["mission_action_states"]
            ],
            primary_mission_progress_state=PrimaryMissionProgressState.from_payload(
                payload["primary_mission_progress_state"]
            ),
            end_turn_cleanup_states=[
                EndTurnCleanupState.from_payload(state)
                for state in payload["end_turn_cleanup_states"]
            ],
            scoring_window_states=[
                ScoringWindowState.from_payload(state) for state in payload["scoring_window_states"]
            ],
            persisting_effects=[
                PersistingEffect.from_payload(effect) for effect in payload["persisting_effects"]
            ],
            tracked_target_records=[
                TrackedTargetRecord.from_payload(record)
                for record in payload["tracked_target_records"]
            ],
            pending_return_on_death=[
                PendingReturnOnDeath.from_payload(pending)
                for pending in payload["pending_return_on_death"]
            ],
            return_on_death_consumed_keys=list(payload["return_on_death_consumed_keys"]),
            secondary_mission_choices=[
                SecondaryMissionChoice.from_payload(choice)
                for choice in payload["secondary_mission_choices"]
            ],
            tactical_secondary_draws=[
                TacticalSecondaryDraw.from_payload(draw)
                for draw in payload["tactical_secondary_draws"]
            ],
            prebattle_action_records=[
                PreBattleActionRecord.from_payload(record)
                for record in payload["prebattle_action_records"]
            ],
            prebattle_alternation_cursor=(
                None
                if payload["prebattle_alternation_cursor"] is None
                else PreBattleAlternationCursor.from_payload(
                    payload["prebattle_alternation_cursor"]
                )
            ),
            secondary_mission_card_states=[
                SecondaryMissionCardState.from_payload(state)
                for state in payload["secondary_mission_card_states"]
            ],
            tactical_secondary_achievement_contexts=[
                TacticalSecondaryAchievementContext.from_payload(context)
                for context in payload["tactical_secondary_achievement_contexts"]
            ],
            tactical_secondary_discard_cp_reward_window_ids=list(
                payload["tactical_secondary_discard_cp_reward_window_ids"]
            ),
            tactical_secondary_replacement_player_ids=list(
                payload["tactical_secondary_replacement_player_ids"]
            ),
        )

    def _advance_active_player_after_completed_turn(self) -> None:
        if self.active_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        active_index = self.turn_order.index(self.active_player_id)
        if active_index + 1 < len(self.turn_order):
            self.active_player_id = self.turn_order[active_index + 1]
            return
        self.active_player_id = self.turn_order[0]
        self.battle_round += 1

    def _expire_persisting_effects_at_current_battle_round_start(self) -> None:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can expire battle-round effects only in battle.")
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.battle_round_start(battle_round=self.battle_round)
        )

    def _expire_persisting_effects_at_current_turn_start(self) -> None:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can expire turn effects only in battle.")
        if self.active_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.turn_start(
                battle_round=self.battle_round,
                player_id=self.active_player_id,
            )
        )

    def _expire_persisting_effects_at_current_phase_start(self) -> None:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("GameState can expire phase effects only in battle.")
        if self.active_player_id is None:
            raise GameLifecycleError("GameState active player is required during battle.")
        current_phase = self.current_battle_phase
        if current_phase is None:
            raise GameLifecycleError("GameState has no current battle phase.")
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.phase_start(
                battle_round=self.battle_round,
                phase=current_phase,
                player_id=self.active_player_id,
            )
        )

    def _record_starting_strength_records_for_army(
        self,
        army_definition: ArmyDefinition,
    ) -> None:
        records = _starting_strength_records_for_army(army_definition)
        existing_unit_ids = {record.unit_instance_id for record in self.starting_strength_records}
        for record in records:
            if record.unit_instance_id in existing_unit_ids:
                raise GameLifecycleError("StartingStrengthRecord already exists for unit.")
            self.starting_strength_records.append(record)
        self.starting_strength_records.sort(key=lambda record: record.unit_instance_id)

    def _record_starting_attached_unit_records_for_army(
        self,
        army_definition: ArmyDefinition,
    ) -> None:
        records = _starting_attached_unit_records_for_army(army_definition)
        existing_unit_ids = {
            record.attached_unit_instance_id for record in self.starting_attached_unit_records
        }
        for record in records:
            if record.attached_unit_instance_id in existing_unit_ids:
                raise GameLifecycleError("StartingAttachedUnitRecord already exists for unit.")
            existing_unit_ids.add(record.attached_unit_instance_id)
            self.starting_attached_unit_records.append(record)
        self.starting_attached_unit_records.sort(
            key=lambda record: record.attached_unit_instance_id
        )

    def _unit_by_id(self, unit_instance_id: str) -> UnitInstance:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        for army_definition in self.army_definitions:
            for unit in army_definition.units:
                if unit.unit_instance_id == requested_unit_id:
                    return unit
        raise GameLifecycleError("GameState unit_instance_id was not found.")

    def record_objective_control_boundary(
        self,
        *,
        completed_phase: BattlePhase,
        timing: ObjectiveControlTiming,
        runtime_modifier_registry: RuntimeModifierRegistry | None,
    ) -> ObjectiveControlRecord:
        return _queries.record_objective_control_boundary(
            state=self,
            completed_phase=completed_phase,
            timing=timing,
            runtime_modifier_registry=runtime_modifier_registry,
        )

    def prepare_current_turn_end_boundary(
        self,
        *,
        completed_phase: BattlePhase,
        runtime_modifier_registry: RuntimeModifierRegistry | None,
    ) -> ObjectiveControlRecord:
        if self.stage is not GameLifecycleStage.BATTLE:
            raise GameLifecycleError("Turn-end preparation requires battle stage.")
        if self.active_player_id is None or self.battle_phase_index is None:
            raise GameLifecycleError("Turn-end preparation requires an active battle turn.")
        if self.battle_phase_index + 1 != len(self.battle_phase_sequence):
            raise GameLifecycleError("Turn-end preparation requires the final battle phase.")
        if completed_phase is not self.current_battle_phase:
            raise GameLifecycleError("Turn-end preparation phase drifted.")
        existing = tuple(
            record
            for record in self.objective_control_records
            if record.timing is ObjectiveControlTiming.TURN_END
            and record.battle_round == self.battle_round
            and record.active_player_id == self.active_player_id
            and record.phase == completed_phase.value
        )
        if len(existing) > 1:
            raise GameLifecycleError("Turn-end preparation found duplicate objective records.")
        if existing:
            return existing[0]
        completed_player_id = self.active_player_id
        self._clear_turn_action_states(
            player_id=completed_player_id,
            battle_round=self.battle_round,
        )
        self._resolve_end_turn_cleanup_boundary(completed_phase=completed_phase)
        record = self.record_objective_control_boundary(
            completed_phase=completed_phase,
            timing=ObjectiveControlTiming.TURN_END,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        self.expire_persisting_effects_at_boundary(
            EffectExpirationBoundary.turn_end(
                battle_round=self.battle_round,
                player_id=completed_player_id,
            )
        )
        return record

    def expire_sticky_objective_control_states(
        self,
        record: ObjectiveControlRecord,
    ) -> None:
        retained: list[StickyObjectiveControlState] = []
        for state in self.sticky_objective_control_states:
            if sticky_objective_control_state_is_expired(
                state=state,
                record=record,
                player_ids=tuple(self.player_ids),
            ):
                continue
            retained.append(state)
        self.sticky_objective_control_states = sorted(
            retained,
            key=lambda state: state.state_id,
        )

    def _record_primary_objective_turn_start_boundary_if_available(
        self,
        *,
        runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ) -> None:
        record_primary_turn_start_evidence(
            state=self,
            runtime_modifier_registry=runtime_modifier_registry,
        )

    def _score_objective_control_boundary(
        self,
        record: ObjectiveControlRecord,
        *,
        event_log: EventLog | None = None,
    ) -> None:
        from warhammer40k_core.engine.secondary_scoring_boundary import (
            score_turn_end_mission_scoring_boundary,
        )

        score_turn_end_mission_scoring_boundary(
            state=self,
            record=record,
            end_of_battle=False,
            event_log=event_log,
        )

    def _score_end_of_battle_primary_boundary(
        self,
        record: ObjectiveControlRecord,
        *,
        event_log: EventLog | None = None,
    ) -> None:
        from warhammer40k_core.engine.secondary_scoring_boundary import (
            score_turn_end_mission_scoring_boundary,
        )

        score_turn_end_mission_scoring_boundary(
            state=self,
            record=record,
            end_of_battle=True,
            event_log=event_log,
        )

    def enemy_unit_ids_in_player_deployment_zone(self, player_id: str) -> tuple[str, ...]:
        from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
            enemy_unit_ids_in_player_deployment_zone_from_battlefield,
        )

        return enemy_unit_ids_in_player_deployment_zone_from_battlefield(
            state=self,
            player_id=player_id,
        )

    def _resolve_end_turn_cleanup_boundary(self, *, completed_phase: BattlePhase) -> None:
        if self.battlefield_state is None:
            raise GameLifecycleError("End-turn cleanup requires battlefield_state.")
        if self.active_player_id is None:
            raise GameLifecycleError("End-turn cleanup requires an active player.")
        scenario = BattlefieldScenario(
            armies=tuple(self.army_definitions),
            battlefield_state=self.battlefield_state,
        )
        cleanup, updated_battlefield = resolve_end_turn_cleanup(
            game_id=self.game_id,
            scenario=scenario,
            ruleset_descriptor=self.ruleset_descriptor_for_runtime_policy(),
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase=completed_phase,
        )
        self.battlefield_state = updated_battlefield
        record_primary_unit_destructions_for_end_turn_cleanup(state=self, cleanup=cleanup)
        self.end_turn_cleanup_states.append(cleanup)
        self.end_turn_cleanup_states.sort(key=lambda state: state.cleanup_id)

    def _resolve_unarrived_reserve_destruction_boundary(self, *, end_of_battle: bool) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Reserve destruction requires MissionSetup.")
        if self.battlefield_state is None:
            raise GameLifecycleError("Reserve destruction requires battlefield_state.")
        policy = reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(self.mission_setup).common_policy
        )
        destruction = resolve_unarrived_reserve_destruction(
            reserve_states=tuple(self.reserve_states),
            armies=tuple(self.army_definitions),
            battlefield_state=self.battlefield_state,
            policy=policy,
            battle_round=self.battle_round,
            end_of_battle=end_of_battle,
        )
        if not destruction.destroyed_model_instance_ids:
            return
        self._apply_unarrived_reserve_destruction(destruction=destruction)

    def _apply_unarrived_reserve_destruction(
        self,
        *,
        destruction: ReserveDestructionResult,
    ) -> None:
        from warhammer40k_core.engine.primary_destruction_evidence import (
            PrimaryUnattributedDestructionCause,
        )
        from warhammer40k_core.engine.primary_unit_destruction_tracking import (
            record_primary_unit_destructions_for_destroyed_models,
        )

        if self.battlefield_state is None:
            raise GameLifecycleError("Reserve destruction requires battlefield_state.")
        terminal_reserve_states = tuple(
            prior_state
            for prior_state, updated_state in zip(
                self.reserve_states,
                destruction.updated_reserve_states,
                strict=True,
            )
            if prior_state.status is ReserveStatus.IN_RESERVES
            and updated_state.status is ReserveStatus.DESTROYED
        )
        for reserve_state in terminal_reserve_states:
            cargo_state = self.transport_cargo_state_for_transport(reserve_state.unit_instance_id)
            if cargo_state is None:
                if reserve_state.embarked_unit_instance_ids:
                    raise GameLifecycleError(
                        "transport_cargo_states unarrived reserve route cargo drift."
                    )
                continue
            if cargo_state.embarked_unit_instance_ids != reserve_state.embarked_unit_instance_ids:
                raise GameLifecycleError(
                    "transport_cargo_states unarrived reserve route cargo drift."
                )
        terminal_transport_ids = {
            reserve_state.unit_instance_id for reserve_state in terminal_reserve_states
        }
        updated_battlefield_state = apply_reserve_destruction_to_battlefield(
            battlefield_state=self.battlefield_state,
            destruction=destruction,
        )
        updated_transport_cargo_states = [
            cargo_state
            for cargo_state in self.transport_cargo_states
            if cargo_state.transport_unit_instance_id not in terminal_transport_ids
        ]
        self.battlefield_state = updated_battlefield_state
        self.reserve_states = list(destruction.updated_reserve_states)
        self.transport_cargo_states = updated_transport_cargo_states
        record_primary_unit_destructions_for_destroyed_models(
            state=self,
            destroyed_model_instance_ids=destruction.destroyed_model_instance_ids,
            destruction_attribution=None,
            source_model_destroyed_event_id=None,
            source_rules_unit_objective_proximity_witness=None,
            destroyed_rules_unit_objective_proximity_witness=None,
            unattributed_cause=PrimaryUnattributedDestructionCause.RESERVE_DEADLINE,
            source_mutation_id=(
                f"{destruction.policy.source_id}:round-{destruction.battle_round:02d}:"
                f"{'end-of-battle' if destruction.end_of_battle else 'round-boundary'}"
            ),
            left_battlefield=False,
            source_id=(
                f"{destruction.policy.source_id}:round-{destruction.battle_round:02d}:"
                f"{'end-of-battle' if destruction.end_of_battle else 'round-boundary'}"
            ),
        )

    def ruleset_descriptor_for_runtime_policy(self) -> RulesetDescriptor:
        return runtime_ruleset_descriptor_for_mission_setup(
            self.mission_setup,
            rules_overlay_ids=self.rules_overlay_ids,
        )

    def _active_player_is_last_in_round(self, player_id: str) -> bool:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        return self.turn_order.index(requested_player_id) + 1 == len(self.turn_order)

    def _game_ends_after_completed_round(self, battle_round: int) -> bool:
        requested_round = _validate_positive_int("battle_round", battle_round)
        if self.mission_setup is None:
            raise GameLifecycleError("Game-end policy requires MissionSetup.")
        policy = mission_scoring_policies_from_setup(self.mission_setup)
        return requested_round >= policy.game_length_battle_rounds

    def game_result_payload(self) -> dict[str, JsonValue]:
        if self.stage is not GameLifecycleStage.COMPLETE:
            raise GameLifecycleError("Game result requires complete stage.")
        if self.mission_setup is None:
            raise GameLifecycleError("Game result requires MissionSetup.")
        policies = mission_scoring_policies_from_setup(self.mission_setup)
        result = FinalScoringResult.from_ledgers(
            game_id=self.game_id,
            battle_round=self.battle_round,
            policies=policies,
            ledgers=tuple(self.victory_point_ledgers),
            scoring_windows=tuple(
                window
                for window in self.scoring_window_states
                if window.battle_round == self.battle_round
            ),
        )
        return cast(dict[str, JsonValue], result.to_payload())

    def _record_scoring_windows_boundary(self, window_kind: ScoringWindowKind) -> None:
        if self.mission_setup is None:
            raise GameLifecycleError("Scoring windows require MissionSetup.")
        kind = ScoringWindowKind(window_kind)
        policy = mission_scoring_policies_from_setup(self.mission_setup)
        windows = (
            policy.end_of_round_scoring_windows
            if kind is ScoringWindowKind.END_OF_ROUND
            else policy.end_of_game_scoring_windows
        )
        for window in windows:
            state = ScoringWindowState(
                window_id=(
                    f"scoring-window:{self.game_id}:round-{self.battle_round:02d}:"
                    f"{kind.value}:{window}"
                ),
                game_id=self.game_id,
                battle_round=self.battle_round,
                window_kind=kind,
                window=window,
                source_id=f"{policy.source_id}:window:{kind.value}:{window}",
            )
            if self._has_scoring_window_state(state.window_id):
                continue
            self.scoring_window_states.append(state)
        self.scoring_window_states.sort(key=lambda state: state.window_id)

    def _has_scoring_window_state(self, window_id: str) -> bool:
        requested_id = _validate_identifier("window_id", window_id)
        return any(state.window_id == requested_id for state in self.scoring_window_states)

    def _assert_battlefield_state_clear_of_objective_markers(
        self,
        battlefield_state: BattlefieldRuntimeState,
    ) -> None:
        if self.mission_setup is None:
            return
        markers = tuple(
            marker.to_objective_marker() for marker in self.mission_setup.objective_markers
        )
        if not markers:
            return
        scenario = BattlefieldScenario(
            armies=tuple(self.army_definitions),
            battlefield_state=battlefield_state,
        )
        for placed_army in battlefield_state.placed_armies:
            for unit_placement in placed_army.unit_placements:
                for model_placement in unit_placement.model_placements:
                    model = geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(model_placement),
                        placement=model_placement,
                    )
                    violation = objective_marker_endpoint_placement_violation(
                        model=model,
                        objective_markers=markers,
                        violation_code="objective_marker_endpoint_overlap",
                        placement_label="Battlefield placement",
                    )
                    if violation is not None:
                        raise GameLifecycleError(
                            "Battlefield placement cannot end on an objective marker."
                        )

    def _clear_turn_action_states(self, *, player_id: str, battle_round: int) -> None:
        requested_player_id = _validate_player_id(player_id, player_ids=self.player_ids)
        requested_round = _validate_positive_int("battle_round", battle_round)
        self.advanced_unit_states = [
            state
            for state in self.advanced_unit_states
            if not (
                state.player_id == requested_player_id and state.battle_round == requested_round
            )
        ]
        self.fell_back_unit_states = [
            state
            for state in self.fell_back_unit_states
            if not (
                state.player_id == requested_player_id and state.battle_round == requested_round
            )
        ]
        self.disembarked_unit_states = [
            state
            for state in self.disembarked_unit_states
            if not (
                state.turn_player_id == requested_player_id
                and state.battle_round == requested_round
            )
        ]
        self.reserve_states = [
            state.clear_expired_post_arrival_restrictions(
                player_id=requested_player_id,
                battle_round=requested_round,
            )
            for state in self.reserve_states
        ]


def secondary_mission_mode_from_token(token: object) -> SecondaryMissionMode:
    if type(token) is SecondaryMissionMode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("SecondaryMissionMode token must be a string.")
    try:
        return SecondaryMissionMode(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported SecondaryMissionMode token: {token}.") from exc


def _army_muster_request_from_payload(payload: ArmyMusterRequestPayload) -> ArmyMusterRequest:
    try:
        return ArmyMusterRequest.from_payload(payload)
    except ArmyMusteringError as exc:
        raise GameLifecycleError("GameConfig army_muster_request payload is invalid.") from exc


def _army_definition_from_payload(payload: ArmyDefinitionPayload) -> ArmyDefinition:
    try:
        return ArmyDefinition.from_payload(payload)
    except ArmyMusteringError as exc:
        raise GameLifecycleError("GameState army_definition payload is invalid.") from exc


def _battlefield_state_from_payload(
    payload: BattlefieldRuntimeStatePayload,
) -> BattlefieldRuntimeState:
    try:
        return BattlefieldRuntimeState.from_payload(payload)
    except PlacementError as exc:
        raise GameLifecycleError("GameState battlefield_state payload is invalid.") from exc


def _validate_lifecycle_sequences(ruleset_descriptor: RulesetDescriptor) -> None:
    setup_steps = ruleset_descriptor.setup_sequence.steps
    phases = ruleset_descriptor.battle_phase_sequence.phases
    if SetupStepKind.MUSTER_ARMIES not in setup_steps:
        raise GameLifecycleError("GameConfig setup_sequence must include MUSTER_ARMIES.")
    if SetupStepKind.SELECT_SECONDARY_MISSIONS not in setup_steps:
        raise GameLifecycleError(
            "GameConfig setup_sequence must include SELECT_SECONDARY_MISSIONS."
        )
    if SetupStepKind.DETERMINE_FIRST_TURN not in setup_steps:
        raise GameLifecycleError("GameConfig setup_sequence must include DETERMINE_FIRST_TURN.")
    if phases[0] is not BattlePhaseKind.COMMAND:
        raise GameLifecycleError("GameConfig battle_phase_sequence must start with COMMAND.")
    if BattlePhaseKind.FIGHT not in phases:
        raise GameLifecycleError("GameConfig battle_phase_sequence must include FIGHT.")
    if phases[-1] is not BattlePhaseKind.FIGHT:
        raise GameLifecycleError("GameConfig battle_phase_sequence must end with FIGHT.")


def _validate_reserve_unit_points(
    values: object,
    *,
    army_muster_requests: tuple[ArmyMusterRequest, ...],
) -> tuple[ReserveUnitPointValue, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameConfig reserve_unit_points must be a tuple.")
    known_unit_ids = {
        f"{request.army_id}:{selection.unit_selection_id}"
        for request in army_muster_requests
        for selection in request.unit_selections
    }
    validated: list[ReserveUnitPointValue] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ReserveUnitPointValue:
            raise GameLifecycleError(
                "GameConfig reserve_unit_points must contain ReserveUnitPointValue values."
            )
        if value.unit_instance_id not in known_unit_ids:
            raise GameLifecycleError("ReserveUnitPointValue unit_instance_id is not mustered.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameConfig reserve_unit_points must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda entry: entry.unit_instance_id))


def _validate_optional_battlefield_state(
    value: object | None,
) -> BattlefieldRuntimeState | None:
    if value is None:
        return None
    if type(value) is not BattlefieldRuntimeState:
        raise GameLifecycleError("GameState battlefield_state must be a BattlefieldRuntimeState.")
    return value


def _validate_optional_mission_setup(
    value: object | None,
    *,
    player_ids: tuple[str, ...],
) -> MissionSetup | None:
    if value is None:
        return None
    if type(value) is not MissionSetup:
        raise GameLifecycleError("mission_setup must be a MissionSetup.")
    if value.attacker_player_id not in player_ids:
        raise GameLifecycleError("mission_setup attacker_player_id is not in this game.")
    if value.defender_player_id not in player_ids:
        raise GameLifecycleError("mission_setup defender_player_id is not in this game.")
    if {value.attacker_player_id, value.defender_player_id} != set(player_ids):
        raise GameLifecycleError(
            "mission_setup players must exactly match the players in this game."
        )
    return value


def _validate_optional_out_of_phase_shooting_state(
    value: object | None,
) -> OutOfPhaseShootingState | None:
    if value is None:
        return None
    if type(value) is not OutOfPhaseShootingState:
        raise GameLifecycleError(
            "GameState out_of_phase_shooting_state must be an OutOfPhaseShootingState."
        )
    return value


def _validate_feel_no_pain_sources_by_model_id(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
) -> dict[str, tuple[FeelNoPainSource, ...]]:
    if not isinstance(values, dict):
        raise GameLifecycleError("GameState Feel No Pain sources must be a dict.")
    known_model_ids = _model_instance_ids(army_definitions)
    validated: dict[str, tuple[FeelNoPainSource, ...]] = {}
    for raw_model_id, raw_sources in cast(dict[object, object], values).items():
        model_id = _validate_identifier("Feel No Pain model_instance_id", raw_model_id)
        if known_model_ids and model_id not in known_model_ids:
            raise GameLifecycleError("Feel No Pain source model is unknown.")
        source_tuple = _validate_feel_no_pain_source_tuple(
            "Feel No Pain sources",
            raw_sources,
        )
        if not source_tuple:
            raise GameLifecycleError("Feel No Pain source model requires at least one source.")
        validated[model_id] = source_tuple
    return dict(sorted(validated.items()))


def _validate_destruction_reaction_sources_by_model_id(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
) -> dict[str, tuple[DestructionReactionSource, ...]]:
    if not isinstance(values, dict):
        raise GameLifecycleError("GameState destruction reaction sources must be a dict.")
    known_model_ids = _model_instance_ids(army_definitions)
    validated: dict[str, tuple[DestructionReactionSource, ...]] = {}
    for raw_model_id, raw_sources in cast(dict[object, object], values).items():
        model_id = _validate_identifier("Destruction reaction model_instance_id", raw_model_id)
        if known_model_ids and model_id not in known_model_ids:
            raise GameLifecycleError("Destruction reaction source model is unknown.")
        source_tuple = _validate_destruction_reaction_source_tuple(
            "Destruction reaction sources",
            raw_sources,
        )
        if not source_tuple:
            raise GameLifecycleError(
                "Destruction reaction source model requires at least one source."
            )
        validated[model_id] = source_tuple
    return dict(sorted(validated.items()))


def _validate_one_shot_weapon_use_records(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
) -> list[OneShotWeaponUseRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState one-shot weapon use records must be a list.")
    model_by_id = {
        model.model_instance_id: model
        for army in army_definitions
        for unit in army.units
        for model in unit.own_models
    }
    records: list[OneShotWeaponUseRecord] = []
    seen: set[tuple[str, str, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not OneShotWeaponUseRecord:
            raise GameLifecycleError(
                "GameState one-shot weapon use records must contain OneShotWeaponUseRecord values."
            )
        model = model_by_id.get(value.model_instance_id)
        if model_by_id and model is None:
            raise GameLifecycleError("One-shot weapon use model is unknown.")
        if model is not None:
            weapon_instance = equipped_weapon_instance_by_id(
                model=model,
                weapon_instance_id=value.weapon_instance_id,
            )
            if weapon_instance is None or weapon_instance.wargear_id != value.wargear_id:
                raise GameLifecycleError("One-shot weapon instance is not equipped by its model.")
        if value.weapon_key in seen:
            raise GameLifecycleError("One-shot weapon use records must not duplicate weapons.")
        seen.add(value.weapon_key)
        records.append(value)
    return sorted(records, key=lambda record: record.weapon_key)


def _validate_ranged_attack_history_records(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
    starting_attached_unit_records: list[StartingAttachedUnitRecord],
    player_ids: tuple[str, ...],
) -> list[RangedAttackHistoryRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState ranged attack history records must be a list.")
    owner_ids_by_unit_id = _ranged_attack_history_unit_owner_ids(
        army_definitions=army_definitions,
        starting_strength_records=starting_strength_records,
        starting_attached_unit_records=starting_attached_unit_records,
    )
    known_unit_ids = set(owner_ids_by_unit_id)
    records: list[RangedAttackHistoryRecord] = []
    seen_result_ids: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not RangedAttackHistoryRecord:
            raise GameLifecycleError(
                "GameState ranged attack history records must contain "
                "RangedAttackHistoryRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("RangedAttackHistoryRecord player_id is not in this game.")
        if value.active_player_id not in player_ids:
            raise GameLifecycleError(
                "RangedAttackHistoryRecord active_player_id is not in this game."
            )
        if known_unit_ids and value.unit_instance_id not in known_unit_ids:
            raise GameLifecycleError("RangedAttackHistoryRecord unit_instance_id is unknown.")
        owner_id = owner_ids_by_unit_id.get(value.unit_instance_id)
        if owner_id is not None and value.player_id != owner_id:
            raise GameLifecycleError(
                "RangedAttackHistoryRecord player_id must control unit_instance_id."
            )
        if value.result_id in seen_result_ids:
            raise GameLifecycleError("RangedAttackHistoryRecord result_id must be unique.")
        seen_result_ids.add(value.result_id)
        records.append(value)
    return sorted(
        records,
        key=lambda record: (
            record.battle_round,
            record.active_player_id,
            record.player_id,
            record.unit_instance_id,
            record.result_id,
        ),
    )


def _validate_feel_no_pain_decline_allowed_model_ids(
    values: object,
    *,
    source_model_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if type(values) not in (list, tuple):
        raise GameLifecycleError("GameState Feel No Pain decline model IDs must be a list.")
    source_ids = set(source_model_ids)
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(list[object] | tuple[object, ...], values):
        model_id = _validate_identifier("Feel No Pain decline model_instance_id", value)
        if model_id not in source_ids:
            raise GameLifecycleError("Feel No Pain decline model requires sources.")
        if model_id in seen:
            raise GameLifecycleError("Feel No Pain decline model IDs must be unique.")
        seen.add(model_id)
        validated.append(model_id)
    return tuple(sorted(validated))


def _validate_feel_no_pain_source_tuple(
    field_name: str,
    values: object,
) -> tuple[FeelNoPainSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    sources: list[FeelNoPainSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not FeelNoPainSource:
            raise GameLifecycleError(f"{field_name} must contain FeelNoPainSource values.")
        if value.source_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _validate_destruction_reaction_source_tuple(
    field_name: str,
    values: object,
) -> tuple[DestructionReactionSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    sources: list[DestructionReactionSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestructionReactionSource:
            raise GameLifecycleError(f"{field_name} must contain DestructionReactionSource values.")
        if value.source_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _validate_model_instance_id_for_state(
    *,
    state: GameState,
    model_instance_id: str,
) -> str:
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    if model_id not in _model_instance_ids(state.army_definitions):
        raise GameLifecycleError("model_instance_id is unknown.")
    return model_id


def _validate_optional_command_step_state(
    value: object | None,
) -> CommandStepState | None:
    if value is None:
        return None
    if type(value) is not CommandStepState:
        raise GameLifecycleError("GameState command_step_state must be a CommandStepState.")
    return value


def _validate_command_point_ledgers(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[CommandPointLedger]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState command_point_ledgers must be a list.")
    if not values:
        return initial_command_point_ledgers(player_ids)
    validated: list[CommandPointLedger] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not CommandPointLedger:
            raise GameLifecycleError(
                "GameState command_point_ledgers must contain CommandPointLedger values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("CommandPointLedger player_id is not in this game.")
        if value.player_id in seen:
            raise GameLifecycleError("GameState command_point_ledgers must be unique.")
        seen.add(value.player_id)
        validated.append(value)
    if set(seen) != set(player_ids):
        raise GameLifecycleError("GameState command_point_ledgers must include every player.")
    return sorted(validated, key=lambda ledger: ledger.player_id)


def _validate_stratagem_use_records(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[StratagemUseRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState stratagem_use_records must be a list.")
    validated: list[StratagemUseRecord] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StratagemUseRecord:
            raise GameLifecycleError(
                "GameState stratagem_use_records must contain StratagemUseRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StratagemUseRecord player_id is not in this game.")
        if value.use_id in seen:
            raise GameLifecycleError("GameState stratagem_use_records must be unique.")
        seen.add(value.use_id)
        validated.append(value)
    return sorted(validated, key=lambda record: record.use_id)


def _validate_faction_rule_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[FactionRuleState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState faction_rule_states must be a list.")
    validated: list[FactionRuleState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not FactionRuleState:
            raise GameLifecycleError(
                "GameState faction_rule_states must contain FactionRuleState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("FactionRuleState player_id is not in this game.")
        if value.state_id in seen:
            raise GameLifecycleError("GameState faction_rule_states must be unique.")
        seen.add(value.state_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.state_id)


def _validate_starting_strength_records(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    player_ids: tuple[str, ...],
) -> list[StartingStrengthRecord]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState starting_strength_records must be a list.")
    if not values and army_definitions:
        derived: list[StartingStrengthRecord] = []
        for army_definition in army_definitions:
            derived.extend(_starting_strength_records_for_army(army_definition))
        return sorted(derived, key=lambda record: record.unit_instance_id)

    expected_record_owner_by_id = _starting_strength_record_owner_by_id(army_definitions)
    validated: list[StartingStrengthRecord] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not StartingStrengthRecord:
            raise GameLifecycleError(
                "GameState starting_strength_records must contain StartingStrengthRecord values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("StartingStrengthRecord player_id is not in this game.")
        owner = expected_record_owner_by_id.get(value.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("StartingStrengthRecord unit is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("StartingStrengthRecord player_id drift.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState starting_strength_records must be unique.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    if set(expected_record_owner_by_id) != seen:
        raise GameLifecycleError("GameState starting_strength_records must include every unit.")
    return sorted(validated, key=lambda record: record.unit_instance_id)


def _starting_strength_records_for_army(
    army_definition: ArmyDefinition,
) -> tuple[StartingStrengthRecord, ...]:
    if type(army_definition) is not ArmyDefinition:
        raise GameLifecycleError("StartingStrengthRecord derivation requires an ArmyDefinition.")
    attached_component_ids = {
        component_id
        for attached_unit in army_definition.attached_units
        for component_id in attached_unit.component_unit_instance_ids
    }
    records = [
        StartingStrengthRecord.from_unit(player_id=army_definition.player_id, unit=unit)
        for unit in army_definition.units
        if unit.unit_instance_id not in attached_component_ids
    ]
    unit_by_id = {unit.unit_instance_id: unit for unit in army_definition.units}
    for attached_unit in army_definition.attached_units:
        records.append(
            _starting_strength_record_for_attached_unit(
                player_id=army_definition.player_id,
                attached_unit=attached_unit,
                unit_by_id=unit_by_id,
            )
        )
    return tuple(sorted(records, key=lambda record: record.unit_instance_id))


def starting_strength_records_for_army(
    army_definition: ArmyDefinition,
) -> tuple[StartingStrengthRecord, ...]:
    """Build the canonical static Starting Strength inventory for one army."""

    return _starting_strength_records_for_army(army_definition)


def _starting_strength_record_for_attached_unit(
    *,
    player_id: str,
    attached_unit: AttachedUnitFormation,
    unit_by_id: dict[str, UnitInstance],
) -> StartingStrengthRecord:
    if type(attached_unit) is not AttachedUnitFormation:
        raise GameLifecycleError("Attached starting strength requires an AttachedUnitFormation.")
    starting_model_count = 0
    for unit_id in attached_unit.component_unit_instance_ids:
        unit = unit_by_id.get(unit_id)
        if unit is None:
            raise GameLifecycleError("Attached starting strength component unit is unknown.")
        starting_model_count += len(unit.own_models)
    return StartingStrengthRecord(
        player_id=player_id,
        unit_instance_id=attached_unit.attached_unit_instance_id,
        starting_model_count=starting_model_count,
        single_model_starting_wounds=None,
        source_id=attached_unit.source_id,
    )


def _starting_strength_record_owner_by_id(
    army_definitions: list[ArmyDefinition],
) -> dict[str, str]:
    owner_by_id: dict[str, str] = {}
    for army_definition in army_definitions:
        attached_component_ids = {
            component_id
            for attached_unit in army_definition.attached_units
            for component_id in attached_unit.component_unit_instance_ids
        }
        for unit in army_definition.units:
            if unit.unit_instance_id not in attached_component_ids:
                owner_by_id[unit.unit_instance_id] = army_definition.player_id
        for attached_unit in army_definition.attached_units:
            owner_by_id[attached_unit.attached_unit_instance_id] = army_definition.player_id
    return owner_by_id


def _validate_reserve_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[ReserveState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState reserve_states must be a list.")
    validated: list[ReserveState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not ReserveState:
            raise GameLifecycleError("GameState reserve_states must contain ReserveState values.")
        if value.player_id not in player_ids:
            raise GameLifecycleError("ReserveState player_id is not in this game.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState reserve_states must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.unit_instance_id)


def _validate_cult_ambush_markers(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[CultAmbushMarker]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState cult_ambush_markers must be a list.")
    validated: list[CultAmbushMarker] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not CultAmbushMarker:
            raise GameLifecycleError(
                "GameState cult_ambush_markers must contain CultAmbushMarker values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("CultAmbushMarker player_id is not in this game.")
        if value.marker_id in seen:
            raise GameLifecycleError("GameState cult_ambush_markers must be unique.")
        seen.add(value.marker_id)
        validated.append(value)
    return sorted(validated, key=lambda marker: marker.marker_id)


def _validate_hover_mode_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[HoverModeState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState hover_mode_states must be a list.")
    validated: list[HoverModeState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not HoverModeState:
            raise GameLifecycleError(
                "GameState hover_mode_states must contain HoverModeState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("HoverModeState player_id is not in this game.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState hover_mode_states must be unique by unit.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.unit_instance_id)


def _validate_hover_mode_state_references(state: GameState) -> None:
    if not state.hover_mode_states:
        return
    for hover_mode_state in state.hover_mode_states:
        _validate_hover_mode_state_reference(state, hover_mode_state)


def _validate_hover_mode_state_reference(
    state: GameState,
    hover_mode_state: HoverModeState,
) -> None:
    unit_owner_by_id = {
        unit.unit_instance_id: army.player_id
        for army in state.army_definitions
        for unit in army.units
    }
    unit_by_id = {
        unit.unit_instance_id: unit for army in state.army_definitions for unit in army.units
    }
    unit = unit_by_id.get(hover_mode_state.unit_instance_id)
    if unit is None:
        raise GameLifecycleError("hover_mode_states unit is unknown.")
    if unit_owner_by_id[hover_mode_state.unit_instance_id] != hover_mode_state.player_id:
        raise GameLifecycleError("hover_mode_states player_id does not match unit owner.")
    if hover_mode_state.source_id != "hover":
        raise GameLifecycleError("hover_mode_states source_id drift.")
    if hover_mode_state.active and not _unit_has_aircraft_hover_keywords(unit.keywords):
        raise GameLifecycleError("hover_mode_states active unit must have AIRCRAFT and HOVER.")


def _validate_transport_cargo_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[TransportCargoState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState transport_cargo_states must be a list.")
    validated: list[TransportCargoState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not TransportCargoState:
            raise GameLifecycleError(
                "GameState transport_cargo_states must contain TransportCargoState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("TransportCargoState player_id is not in this game.")
        if value.transport_unit_instance_id in seen:
            raise GameLifecycleError("GameState transport_cargo_states must be unique.")
        seen.add(value.transport_unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda state: state.transport_unit_instance_id)


def _validate_dedicated_transport_setup_consequences(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    player_ids: tuple[str, ...],
) -> list[DedicatedTransportSetupConsequence]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState dedicated_transport_setup_consequences must be a list.")
    unit_owner_by_id = _unit_owner_by_id(army_definitions)
    unit_by_id = {unit.unit_instance_id: unit for army in army_definitions for unit in army.units}
    validated: list[DedicatedTransportSetupConsequence] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not DedicatedTransportSetupConsequence:
            raise GameLifecycleError(
                "GameState dedicated_transport_setup_consequences must contain "
                "DedicatedTransportSetupConsequence values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence player_id is not in this game."
            )
        if value.transport_unit_instance_id in seen:
            raise GameLifecycleError(
                "GameState dedicated_transport_setup_consequences must be unique."
            )
        owner = unit_owner_by_id.get(value.transport_unit_instance_id)
        if owner is None:
            raise GameLifecycleError("DedicatedTransportSetupConsequence Transport is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("DedicatedTransportSetupConsequence player_id drift.")
        transport = unit_by_id[value.transport_unit_instance_id]
        if not _unit_has_keyword(transport, "DEDICATED TRANSPORT"):
            raise GameLifecycleError(
                "DedicatedTransportSetupConsequence requires a DEDICATED TRANSPORT unit."
            )
        seen.add(value.transport_unit_instance_id)
        validated.append(value)
    return sorted(validated, key=lambda consequence: consequence.transport_unit_instance_id)


def _validate_disembarked_unit_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[DisembarkedUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState disembarked_unit_states must be a list.")
    validated: list[DisembarkedUnitState] = []
    seen: set[tuple[int, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not DisembarkedUnitState:
            raise GameLifecycleError(
                "GameState disembarked_unit_states must contain DisembarkedUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("DisembarkedUnitState player_id is not in this game.")
        key = (value.battle_round, value.player_id, value.unit_instance_id)
        if key in seen:
            raise GameLifecycleError("GameState disembarked_unit_states must be unique.")
        seen.add(key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (state.battle_round, state.player_id, state.unit_instance_id),
    )


def _validate_advanced_unit_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[AdvancedUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState advanced_unit_states must be a list.")
    validated: list[AdvancedUnitState] = []
    seen: set[tuple[int, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not AdvancedUnitState:
            raise GameLifecycleError(
                "GameState advanced_unit_states must contain AdvancedUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("AdvancedUnitState player_id is not in this game.")
        key = (value.battle_round, value.player_id, value.unit_instance_id)
        if key in seen:
            raise GameLifecycleError("GameState advanced_unit_states must be unique.")
        seen.add(key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (state.battle_round, state.player_id, state.unit_instance_id),
    )


def _validate_fell_back_unit_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[FellBackUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState fell_back_unit_states must be a list.")
    validated: list[FellBackUnitState] = []
    seen: set[tuple[int, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not FellBackUnitState:
            raise GameLifecycleError(
                "GameState fell_back_unit_states must contain FellBackUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("FellBackUnitState player_id is not in this game.")
        key = (value.battle_round, value.player_id, value.unit_instance_id)
        if key in seen:
            raise GameLifecycleError("GameState fell_back_unit_states must be unique.")
        seen.add(key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (state.battle_round, state.player_id, state.unit_instance_id),
    )


def _validate_normal_move_states(
    values: object,
    *,
    player_ids: tuple[str, ...],
) -> list[NormalMoveState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState normal_move_states must be a list.")
    validated: list[NormalMoveState] = []
    seen_result_ids: set[str] = set()
    seen_same_phase_keys: set[tuple[int, str, str, str]] = set()
    for value in cast(list[object], values):
        if type(value) is not NormalMoveState:
            raise GameLifecycleError(
                "GameState normal_move_states must contain NormalMoveState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("NormalMoveState player_id is not in this game.")
        if value.result_id in seen_result_ids:
            raise GameLifecycleError("GameState normal_move_states must be unique by result.")
        seen_result_ids.add(value.result_id)
        same_phase_key = value.same_phase_key()
        if same_phase_key in seen_same_phase_keys:
            raise GameLifecycleError("GameState normal_move_states must be unique by unit phase.")
        seen_same_phase_keys.add(same_phase_key)
        validated.append(value)
    return sorted(
        validated,
        key=lambda state: (
            state.battle_round,
            state.phase,
            state.player_id,
            state.unit_instance_id,
            state.result_id,
        ),
    )


def _validate_battle_shocked_unit_states(
    values: object,
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
    battle_shocked_unit_ids: tuple[str, ...],
    player_ids: tuple[str, ...],
) -> list[BattleShockedUnitState]:
    if not isinstance(values, list):
        raise GameLifecycleError("GameState battle_shocked_unit_states must be a list.")
    unit_owner_by_id = _known_rules_unit_owner_ids(
        army_definitions=army_definitions,
        starting_strength_records=starting_strength_records,
    )
    shocked_ids = set(battle_shocked_unit_ids)
    validated: list[BattleShockedUnitState] = []
    seen: set[str] = set()
    for value in cast(list[object], values):
        if type(value) is not BattleShockedUnitState:
            raise GameLifecycleError(
                "GameState battle_shocked_unit_states must contain BattleShockedUnitState values."
            )
        if value.player_id not in player_ids:
            raise GameLifecycleError("BattleShockedUnitState player_id is not in this game.")
        owner = unit_owner_by_id.get(value.unit_instance_id)
        if owner is None:
            raise GameLifecycleError("BattleShockedUnitState unit is unknown.")
        if owner != value.player_id:
            raise GameLifecycleError("BattleShockedUnitState player_id drift.")
        if value.unit_instance_id not in shocked_ids:
            raise GameLifecycleError("BattleShockedUnitState missing battle_shocked_unit_id.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError("GameState battle_shocked_unit_states must be unique.")
        seen.add(value.unit_instance_id)
        validated.append(value)
    if seen != shocked_ids:
        raise GameLifecycleError(
            "GameState battle_shocked_unit_ids must match BattleShockedUnitState records."
        )
    return sorted(validated, key=lambda state: state.unit_instance_id)


def _validate_state_stage_indexes(state: GameState) -> None:
    if state.stage is GameLifecycleStage.SETUP:
        if state.setup_step_index is None:
            raise GameLifecycleError("GameState setup stage requires a setup_step_index.")
        if state.battle_phase_index is not None:
            raise GameLifecycleError("GameState setup stage must not have a battle_phase_index.")
        if state.battle_round != 0:
            raise GameLifecycleError("GameState setup stage must have battle_round 0.")
        if state.active_player_id is not None:
            raise GameLifecycleError("GameState setup stage must not have an active player.")
        return
    if state.stage is GameLifecycleStage.BATTLE:
        if state.setup_step_index is not None:
            raise GameLifecycleError("GameState battle stage must not have a setup_step_index.")
        if state.battle_phase_index is None:
            raise GameLifecycleError("GameState battle stage requires a battle_phase_index.")
        if state.battle_round < 1:
            raise GameLifecycleError("GameState battle stage requires battle_round >= 1.")
        if state.active_player_id is None:
            raise GameLifecycleError("GameState battle stage requires an active player.")
        if (
            state.command_step_state is not None
            and state.current_battle_phase is not BattlePhase.COMMAND
        ):
            raise GameLifecycleError("command_step_state requires COMMAND phase.")
        if state.command_step_state is not None:
            if state.command_step_state.active_player_id != state.active_player_id:
                raise GameLifecycleError("command_step_state active player drift.")
            if state.command_step_state.battle_round != state.battle_round:
                raise GameLifecycleError("command_step_state battle round drift.")
        return
    if state.setup_step_index is not None or state.battle_phase_index is not None:
        raise GameLifecycleError("GameState complete stage must not have active indexes.")


def _validate_setup_sequence(values: object) -> tuple[SetupStep, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameState setup_sequence must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    steps = tuple(setup_step_kind_from_token(step) for step in raw_values)
    if not steps:
        raise GameLifecycleError("GameState setup_sequence must not be empty.")
    return steps


def _validate_battle_phase_sequence(values: object) -> tuple[BattlePhase, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GameState battle_phase_sequence must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    phases = tuple(battle_phase_kind_from_token(phase) for phase in raw_values)
    if not phases:
        raise GameLifecycleError("GameState battle_phase_sequence must not be empty.")
    if phases[-1] is not BattlePhaseKind.FIGHT:
        raise GameLifecycleError("GameState battle_phase_sequence must end with FIGHT.")
    return phases


def _validate_turn_order(values: object, *, player_ids: tuple[str, ...]) -> tuple[str, ...]:
    turn_order = _validate_identifier_tuple(
        "turn_order",
        values,
        min_length=len(player_ids),
        sort_values=False,
    )
    if len(turn_order) != len(player_ids):
        raise GameLifecycleError("turn_order must include every player exactly once.")
    if set(turn_order) != set(player_ids):
        raise GameLifecycleError("turn_order must match player_ids.")
    return turn_order


def _validate_secondary_choices(
    choices: object,
    *,
    player_ids: tuple[str, ...],
) -> list[SecondaryMissionChoice]:
    if not isinstance(choices, list):
        raise GameLifecycleError("GameState secondary_mission_choices must be a list.")
    validated: list[SecondaryMissionChoice] = []
    seen: set[str] = set()
    for choice in cast(list[object], choices):
        if type(choice) is not SecondaryMissionChoice:
            raise GameLifecycleError(
                "GameState secondary_mission_choices must contain SecondaryMissionChoice values."
            )
        if choice.player_id not in player_ids:
            raise GameLifecycleError("SecondaryMissionChoice player_id is not in this game.")
        if choice.player_id in seen:
            raise GameLifecycleError("GameState secondary_mission_choices must be unique.")
        seen.add(choice.player_id)
        validated.append(choice)
    return sorted(validated, key=lambda stored: stored.player_id)


def _validate_tactical_draws(
    draws: object,
    *,
    player_ids: tuple[str, ...],
) -> list[TacticalSecondaryDraw]:
    if not isinstance(draws, list):
        raise GameLifecycleError("GameState tactical_secondary_draws must be a list.")
    validated: list[TacticalSecondaryDraw] = []
    seen: set[tuple[int, str]] = set()
    for draw in cast(list[object], draws):
        if type(draw) is not TacticalSecondaryDraw:
            raise GameLifecycleError(
                "GameState tactical_secondary_draws must contain TacticalSecondaryDraw values."
            )
        if draw.player_id not in player_ids:
            raise GameLifecycleError("TacticalSecondaryDraw player_id is not in this game.")
        key = (draw.battle_round, draw.player_id)
        if key in seen:
            raise GameLifecycleError("GameState tactical_secondary_draws must be unique.")
        seen.add(key)
        validated.append(draw)
    return sorted(validated, key=lambda stored: (stored.battle_round, stored.player_id))


def _validate_prebattle_action_records(
    records: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[PreBattleActionRecord]:
    if not isinstance(records, list):
        raise GameLifecycleError("GameState prebattle_action_records must be a list.")
    validated_game_id = _validate_identifier("game_id", game_id)
    validated: list[PreBattleActionRecord] = []
    seen: set[str] = set()
    for record in cast(list[object], records):
        if type(record) is not PreBattleActionRecord:
            raise GameLifecycleError(
                "GameState prebattle_action_records must contain PreBattleActionRecord values."
            )
        if record.game_id != validated_game_id:
            raise GameLifecycleError("PreBattleActionRecord game_id drift.")
        if record.player_id not in player_ids:
            raise GameLifecycleError("PreBattleActionRecord player_id is not in this game.")
        if record.action_id in seen:
            raise GameLifecycleError("GameState prebattle_action_records must be unique.")
        seen.add(record.action_id)
        validated.append(record)
    return sorted(validated, key=lambda stored: stored.action_id)


def _validate_prebattle_alternation_cursor(
    cursor: object | None,
    *,
    records: list[PreBattleActionRecord],
    game_id: str,
    turn_order: tuple[str, ...],
) -> PreBattleAlternationCursor | None:
    prebattle_records = tuple(
        record for record in records if record.setup_step is SetupStep.RESOLVE_PREBATTLE_ACTIONS
    )
    if cursor is None:
        if prebattle_records:
            raise GameLifecycleError(
                "GameState pre-battle action records require an alternation cursor."
            )
        return None
    if type(cursor) is not PreBattleAlternationCursor:
        raise GameLifecycleError(
            "GameState prebattle_alternation_cursor must be a PreBattleAlternationCursor."
        )
    if cursor.game_id != game_id:
        raise GameLifecycleError("PreBattleAlternationCursor game_id drift.")
    if cursor.ordered_player_ids != turn_order:
        raise GameLifecycleError("PreBattleAlternationCursor turn order drift.")
    if cursor.resolved_action_count != len(prebattle_records):
        raise GameLifecycleError("PreBattleAlternationCursor resolution count drift.")
    if prebattle_records:
        last_record = prebattle_records[-1]
        if (
            cursor.last_action_id != last_record.action_id
            or cursor.last_unit_instance_id != last_record.unit_instance_id
        ):
            raise GameLifecycleError("PreBattleAlternationCursor last action drift.")
    return cursor


def _unit_owner_by_id(army_definitions: list[ArmyDefinition]) -> dict[str, str]:
    return {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }


def _model_instance_ids(army_definitions: list[ArmyDefinition]) -> set[str]:
    return {
        model.model_instance_id
        for army in army_definitions
        for unit in army.units
        for model in unit.own_models
    }


def _validate_objective_control_records(
    records: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[ObjectiveControlRecord]:
    if not isinstance(records, list):
        raise GameLifecycleError("GameState objective_control_records must be a list.")
    validated: list[ObjectiveControlRecord] = []
    seen: set[str] = set()
    for record in cast(list[object], records):
        if type(record) is not ObjectiveControlRecord:
            raise GameLifecycleError(
                "GameState objective_control_records must contain ObjectiveControlRecord values."
            )
        if record.game_id != game_id:
            raise GameLifecycleError("ObjectiveControlRecord game_id drift.")
        if record.active_player_id not in player_ids:
            raise GameLifecycleError("ObjectiveControlRecord active_player_id is not in this game.")
        if record.record_id in seen:
            raise GameLifecycleError("GameState objective_control_records must be unique.")
        seen.add(record.record_id)
        validated.append(record)
    return validated


def _validate_sticky_objective_control_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[StickyObjectiveControlState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState sticky objective-control states must be a list.")
    player_id_set = set(player_ids)
    validated: list[StickyObjectiveControlState] = []
    seen_ids: set[str] = set()
    holder_by_objective: dict[str, str] = {}
    for state in cast(list[object], states):
        if type(state) is not StickyObjectiveControlState:
            raise GameLifecycleError(
                "GameState sticky objective-control states must contain sticky states."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("StickyObjectiveControlState game_id drift.")
        if state.player_id not in player_id_set or state.active_player_id not in player_id_set:
            raise GameLifecycleError("StickyObjectiveControlState player_id is not in this game.")
        if state.state_id in seen_ids:
            raise GameLifecycleError("GameState sticky objective-control states must be unique.")
        current_holder = holder_by_objective.get(state.objective_id)
        if current_holder is not None and current_holder != state.player_id:
            raise GameLifecycleError(
                "Sticky objective-control states cannot have multiple holders per objective."
            )
        seen_ids.add(state.state_id)
        holder_by_objective[state.objective_id] = state.player_id
        validated.append(state)
    return sorted(validated, key=lambda stored: stored.state_id)


def _validate_mission_action_states(
    states: object,
    *,
    player_ids: tuple[str, ...],
) -> list[MissionActionState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState mission_action_states must be a list.")
    validated: list[MissionActionState] = []
    seen: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not MissionActionState:
            raise GameLifecycleError(
                "GameState mission_action_states must contain MissionActionState values."
            )
        if state.player_id not in player_ids:
            raise GameLifecycleError("MissionActionState player_id is not in this game.")
        if state.action_id in seen:
            raise GameLifecycleError("GameState mission_action_states must be unique.")
        seen.add(state.action_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.action_id)


def _validate_end_turn_cleanup_states(
    states: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[EndTurnCleanupState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState end_turn_cleanup_states must be a list.")
    validated: list[EndTurnCleanupState] = []
    seen: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not EndTurnCleanupState:
            raise GameLifecycleError(
                "GameState end_turn_cleanup_states must contain EndTurnCleanupState values."
            )
        if state.game_id != game_id:
            raise GameLifecycleError("EndTurnCleanupState game_id drift.")
        if state.active_player_id not in player_ids:
            raise GameLifecycleError("EndTurnCleanupState active_player_id is not in this game.")
        if state.cleanup_id in seen:
            raise GameLifecycleError("GameState end_turn_cleanup_states must be unique.")
        seen.add(state.cleanup_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.cleanup_id)


def _validate_scoring_window_states(
    states: object,
    *,
    game_id: str,
) -> list[ScoringWindowState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState scoring_window_states must be a list.")
    requested_game_id = _validate_identifier("game_id", game_id)
    validated: list[ScoringWindowState] = []
    seen: set[str] = set()
    for state in cast(list[object], states):
        if type(state) is not ScoringWindowState:
            raise GameLifecycleError(
                "GameState scoring_window_states must contain ScoringWindowState values."
            )
        if state.game_id != requested_game_id:
            raise GameLifecycleError("ScoringWindowState game_id drift.")
        if state.window_id in seen:
            raise GameLifecycleError("GameState scoring_window_states must be unique.")
        seen.add(state.window_id)
        validated.append(state)
    return sorted(validated, key=lambda state: state.window_id)


def _validate_persisting_effects(
    effects: object,
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
    player_ids: tuple[str, ...],
) -> list[PersistingEffect]:
    if not isinstance(effects, list):
        raise GameLifecycleError("GameState persisting_effects must be a list.")
    unit_ids = _known_rules_unit_ids(
        army_definitions=army_definitions,
        starting_strength_records=starting_strength_records,
    )
    validated: list[PersistingEffect] = []
    seen: set[str] = set()
    for effect in cast(list[object], effects):
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError(
                "GameState persisting_effects must contain PersistingEffect values."
            )
        if effect.owner_player_id not in player_ids:
            raise GameLifecycleError("PersistingEffect owner_player_id is not in this game.")
        if not unit_ids:
            raise GameLifecycleError("PersistingEffect requires mustered army definitions.")
        if any(unit_id not in unit_ids for unit_id in effect.target_unit_instance_ids):
            raise GameLifecycleError("PersistingEffect target unit is unknown.")
        if effect.effect_id in seen:
            raise GameLifecycleError("GameState persisting_effects must be unique.")
        seen.add(effect.effect_id)
        validated.append(effect)
    return sorted(validated, key=lambda effect: effect.effect_id)


def _validate_tracked_target_records(
    records: object,
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
    player_ids: tuple[str, ...],
) -> list[TrackedTargetRecord]:
    if not isinstance(records, list):
        raise GameLifecycleError("GameState tracked_target_records must be a list.")
    owner_by_unit_id = _known_rules_unit_owner_ids(
        army_definitions=army_definitions,
        starting_strength_records=starting_strength_records,
    )
    validated: list[TrackedTargetRecord] = []
    seen_ids: set[str] = set()
    seen_active_keys: set[
        tuple[str, str, str | None, TrackedTargetOwnerScope, TrackedTargetRole]
    ] = set()
    for record in cast(list[object], records):
        if type(record) is not TrackedTargetRecord:
            raise GameLifecycleError(
                "GameState tracked_target_records must contain TrackedTargetRecord values."
            )
        if record.record_id in seen_ids:
            raise GameLifecycleError("GameState tracked_target_records must be unique.")
        seen_ids.add(record.record_id)
        if record.owner_player_id not in player_ids:
            raise GameLifecycleError("TrackedTargetRecord owner_player_id is not in this game.")
        if record.source_unit_instance_id not in owner_by_unit_id:
            raise GameLifecycleError("TrackedTargetRecord source unit is unknown.")
        if record.target_unit_instance_id not in owner_by_unit_id:
            raise GameLifecycleError("TrackedTargetRecord target unit is unknown.")
        validate_canonical_tracked_target_record(
            armies=tuple(army_definitions),
            record=record,
        )
        if record.owner_scope is TrackedTargetOwnerScope.THIS_MODEL:
            source_model_ids = _model_ids_for_unit(
                army_definitions=army_definitions,
                unit_instance_id=record.source_unit_instance_id,
            )
            if record.source_model_instance_id not in source_model_ids:
                raise GameLifecycleError("TrackedTargetRecord source model is unknown.")
        if record.active:
            active_key = record.active_key()
            if active_key in seen_active_keys:
                raise GameLifecycleError("GameState tracked_target_records active key duplicated.")
            seen_active_keys.add(active_key)
        validated.append(record)
    return sorted(validated, key=lambda record: record.record_id)


def _validate_pending_return_on_death(
    records: object,
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
    player_ids: tuple[str, ...],
) -> list[PendingReturnOnDeath]:
    if not isinstance(records, list):
        raise GameLifecycleError("GameState pending_return_on_death must be a list.")
    owner_by_unit_id = _known_rules_unit_owner_ids(
        army_definitions=army_definitions,
        starting_strength_records=starting_strength_records,
    )
    validated: list[PendingReturnOnDeath] = []
    seen_ids: set[str] = set()
    seen_open_consumed_keys: set[str] = set()
    for pending in cast(list[object], records):
        if type(pending) is not PendingReturnOnDeath:
            raise GameLifecycleError(
                "GameState pending_return_on_death must contain PendingReturnOnDeath values."
            )
        if pending.pending_id in seen_ids:
            raise GameLifecycleError("GameState pending_return_on_death must be unique.")
        seen_ids.add(pending.pending_id)
        if pending.owner_player_id not in player_ids:
            raise GameLifecycleError("PendingReturnOnDeath owner_player_id is not in this game.")
        if pending.destroyed_unit_instance_id not in owner_by_unit_id:
            raise GameLifecycleError("PendingReturnOnDeath destroyed unit is unknown.")
        if owner_by_unit_id[pending.destroyed_unit_instance_id] != pending.owner_player_id:
            raise GameLifecycleError("PendingReturnOnDeath owner drift.")
        if not pending.resolved:
            consumed_key = pending.consumed_key()
            if consumed_key in seen_open_consumed_keys:
                raise GameLifecycleError("PendingReturnOnDeath open key duplicated.")
            seen_open_consumed_keys.add(consumed_key)
        validated.append(pending)
    return sorted(validated, key=lambda pending: pending.pending_id)


def _known_rules_unit_ids(
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
) -> set[str]:
    return (
        {unit.unit_instance_id for army in army_definitions for unit in army.units}
        | attached_rules_unit_ids(tuple(army_definitions))
        | {record.unit_instance_id for record in starting_strength_records}
    )


def _model_ids_for_unit(
    *,
    army_definitions: list[ArmyDefinition],
    unit_instance_id: str,
) -> set[str]:
    requested_unit = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit:
                return {model.model_instance_id for model in unit.own_models}
    return set()


def _known_rules_unit_owner_ids(
    *,
    army_definitions: list[ArmyDefinition],
    starting_strength_records: list[StartingStrengthRecord],
) -> dict[str, str]:
    owner_ids = {
        unit.unit_instance_id: army.player_id for army in army_definitions for unit in army.units
    }
    owner_ids.update(attached_rules_unit_owner_ids(tuple(army_definitions)))
    for record in starting_strength_records:
        owner_ids[record.unit_instance_id] = record.player_id
    return owner_ids


def _physical_unit_ids(army_definitions: list[ArmyDefinition]) -> set[str]:
    return {unit.unit_instance_id for army in army_definitions for unit in army.units}


def _validate_secondary_mission_card_states(
    states: object,
    *,
    player_ids: tuple[str, ...],
) -> list[SecondaryMissionCardState]:
    if not isinstance(states, list):
        raise GameLifecycleError("GameState secondary_mission_card_states must be a list.")
    validated: list[SecondaryMissionCardState] = []
    seen: set[tuple[str, str, SecondaryMissionCardMode, int]] = set()
    for state in cast(list[object], states):
        if type(state) is not SecondaryMissionCardState:
            raise GameLifecycleError(
                "GameState secondary_mission_card_states must contain card states."
            )
        if state.player_id not in player_ids:
            raise GameLifecycleError("SecondaryMissionCardState player_id is not in this game.")
        key = (
            state.player_id,
            state.secondary_mission_id,
            state.mode,
            state.battle_round,
        )
        if key in seen:
            raise GameLifecycleError("GameState secondary_mission_card_states must be unique.")
        seen.add(key)
        validated.append(state)
    return sorted(
        validated,
        key=lambda state: (
            state.player_id,
            state.battle_round,
            state.mode.value,
            state.secondary_mission_id,
        ),
    )


def _validate_tactical_secondary_achievement_contexts(
    contexts: object,
    *,
    game_id: str,
    player_ids: tuple[str, ...],
) -> list[TacticalSecondaryAchievementContext]:
    if not isinstance(contexts, list):
        raise GameLifecycleError(
            "GameState tactical_secondary_achievement_contexts must be a list."
        )
    requested_game_id = _validate_identifier("game_id", game_id)
    validated: list[TacticalSecondaryAchievementContext] = []
    seen_ids: set[str] = set()
    seen_cards: set[tuple[str, str, int]] = set()
    for context in cast(list[object], contexts):
        if type(context) is not TacticalSecondaryAchievementContext:
            raise GameLifecycleError(
                "GameState tactical_secondary_achievement_contexts must contain contexts."
            )
        if context.game_id != requested_game_id:
            raise GameLifecycleError("TacticalSecondaryAchievementContext game_id drift.")
        if context.player_id not in player_ids:
            raise GameLifecycleError(
                "TacticalSecondaryAchievementContext player_id is not in this game."
            )
        if context.active_player_id not in player_ids:
            raise GameLifecycleError(
                "TacticalSecondaryAchievementContext active_player_id is not in this game."
            )
        if context.achievement_id in seen_ids:
            raise GameLifecycleError(
                "GameState tactical_secondary_achievement_contexts must not duplicate IDs."
            )
        card_key = (
            context.player_id,
            context.secondary_mission_id,
            context.card_battle_round,
        )
        if card_key in seen_cards:
            raise GameLifecycleError(
                "GameState tactical_secondary_achievement_contexts must not duplicate cards."
            )
        seen_ids.add(context.achievement_id)
        seen_cards.add(card_key)
        validated.append(context)
    return sorted(
        validated,
        key=lambda context: (
            context.player_id,
            context.card_battle_round,
            context.secondary_mission_id,
        ),
    )


def _validate_optional_index(field_name: str, value: object | None, *, length: int) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer or null.")
    if value < 0 or value >= length:
        raise GameLifecycleError(f"{field_name} is outside the sequence.")
    return value


def _validate_optional_player_id(
    field_name: str,
    value: object | None,
    *,
    player_ids: tuple[str, ...],
) -> str | None:
    if value is None:
        return None
    player_id = _validate_identifier(field_name, value)
    if player_id not in player_ids:
        raise GameLifecycleError(f"{field_name} must be in player_ids.")
    return player_id


def _validate_player_id(value: object, *, player_ids: tuple[str, ...]) -> str:
    player_id = _validate_identifier("player_id", value)
    if player_id not in player_ids:
        raise GameLifecycleError("player_id is not in this game.")
    return player_id


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_descriptor_hash(field_name: str, value: object) -> str:
    descriptor_hash = _validate_identifier(field_name, value)
    if len(descriptor_hash) != 64:
        raise GameLifecycleError(f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in descriptor_hash):
        raise GameLifecycleError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return descriptor_hash


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a boolean.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
