from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.support.catalog_package_fixtures import (
    bloodcrushers_army,
    bloodcrushers_package,
    bloodcrushers_unit,
)
from tests.support.catalog_runtime_fixtures import (
    battle_state_with_army,
    bloodcrushers_battlefield_state,
)
from tests.support.selected_to_fight_risk_fixtures import attached_selected_to_fight_risk_fixture
from warhammer40k_core.core.missions import (
    MissionPackError,
    MissionScoringResolutionMode,
    MissionScoringRuleDefinition,
    PrimaryMissionDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import BattlefieldRuntimeState, ModelPlacement
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup, PlayerPrimaryMissionAssignment
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_destruction_evidence import (
    ObjectiveMarkerModelWitness,
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryMissionProgressState
from warhammer40k_core.engine.primary_scoring_resolution import (
    PrimaryScoringResolutionCandidate,
    PrimaryScoringResolutionMode,
    ResolvedPrimaryScoringCandidate,
    primary_scoring_resolution_mode_from_token,
    resolve_primary_scoring_candidates,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import objective_control_record_hash
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
)
from warhammer40k_core.engine.primary_scoring_timing import (
    SUPPORTED_PRIMARY_SCORING_TIMINGS,
    primary_scoring_timing_applies,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryComponentTurnStartMembership,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
    PrimaryRulesUnitTurnStartSnapshot,
    build_primary_rules_unit_turn_start_snapshot,
    current_primary_component_turn_start_membership,
    current_primary_rules_unit_turn_start_membership,
    primary_rules_unit_turn_start_membership_for_lineage,
    primary_rules_unit_turn_start_snapshots_from_payload,
    primary_rules_unit_turn_start_snapshots_with_created_unit,
    record_primary_rules_unit_turn_start_snapshot,
    record_primary_turn_start_evidence,
    validate_primary_objective_turn_start_states,
    validate_primary_rules_unit_turn_start_snapshots,
    validate_primary_unit_destruction_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    build_primary_unit_destruction_state,
    primary_unit_destruction_id,
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
    record_primary_unit_destructions_for_end_turn_cleanup,
    validate_primary_unit_destruction_source_witness_identity,
    validate_primary_unit_destruction_states,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)


def _minimal_evidence_game_state(
    *,
    battlefield: BattlefieldRuntimeState | None = None,
) -> GameState:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    return GameState(
        game_id="primary-evidence-game",
        ruleset_descriptor_hash=descriptor.descriptor_hash,
        stage=GameLifecycleStage.BATTLE,
        setup_sequence=tuple(descriptor.setup_sequence.steps),
        battle_phase_sequence=tuple(descriptor.battle_phase_sequence.phases),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        tactical_secondary_draw_count=2,
        setup_step_index=None,
        battle_phase_index=0,
        battle_round=1,
        active_player_id="player-a",
        battlefield_state=battlefield,
    )


def _catalog_tracking_state() -> tuple[GameState, UnitInstance]:
    package = bloodcrushers_package()
    unit = bloodcrushers_unit(
        package=package,
        selected_wargear_id="000001115:instrument-of-chaos",
    )
    army = bloodcrushers_army(package=package, unit=unit)
    initial_battlefield = bloodcrushers_battlefield_state(army=army, unit=unit)
    state = battle_state_with_army(army=army, battlefield=initial_battlefield)
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id=army.player_id,
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-opponent",
        defender_force_disposition_id="take-and-hold",
    )
    state.mission_setup = mission_setup
    state.battlefield_state = replace(
        initial_battlefield,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    return state, unit


def _evidence_model_placement() -> ModelPlacement:
    return ModelPlacement(
        army_id="army-source",
        player_id="player-a",
        unit_instance_id="army-source:unit-source",
        model_instance_id="army-source:unit-source:model-source",
        pose=Pose.at(12.0, 12.0),
    )


def _deadly_demise_attribution(
    *,
    source_model_instance_id: str | None = "army-source:unit-source:model-source",
) -> ModelDestructionAttribution:
    return ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.DEADLY_DEMISE,
        source_rules_unit_instance_id="army-source:unit-source",
        source_model_instance_id=source_model_instance_id,
    )


def _source_objective_witness() -> RulesUnitObjectiveProximityWitness:
    return RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="army-source:unit-source",
        component_unit_instance_ids=("army-source:unit-source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id="objective-a",
                model_instance_ids=("army-source:unit-source:model-source",),
            ),
        ),
    )


def _turn_start_component(
    unit_instance_id: str,
    model_instance_id: str,
) -> PrimaryComponentTurnStartMembership:
    return PrimaryComponentTurnStartMembership(
        unit_instance_id=unit_instance_id,
        evaluated_model_instance_ids=(model_instance_id,),
        logical_terrain_area_ids=("area-a",),
        objective_marker_witnesses=(
            PrimaryObjectiveMarkerWitness(
                objective_marker_id="objective-a",
                model_instance_ids=(model_instance_id,),
            ),
        ),
    )


def _turn_start_snapshot(
    *,
    memberships: tuple[PrimaryRulesUnitTurnStartMembership, ...] | None = None,
) -> PrimaryRulesUnitTurnStartSnapshot:
    if memberships is None:
        component = _turn_start_component("unit-a", "model-a")
        memberships = (
            PrimaryRulesUnitTurnStartMembership(
                rules_unit_instance_id="unit-a",
                component_memberships=(component,),
            ),
        )
    return PrimaryRulesUnitTurnStartSnapshot(
        snapshot_id="primary-rules-unit-turn-start:game-a:round-01:player-a",
        game_id="game-a",
        active_player_id="player-a",
        battle_round=1,
        rules_unit_memberships=memberships,
        source_id="game-a:primary-rules-unit-turn-start:round-01:player-a",
    )


def _validate_turn_start_snapshots(
    snapshots: object,
    *,
    known_models: object = (("unit-a", ("model-a",)),),
    known_attached: object = (),
) -> list[PrimaryRulesUnitTurnStartSnapshot]:
    return validate_primary_rules_unit_turn_start_snapshots(
        snapshots,
        game_id="game-a",
        player_ids=("player-a", "player-b"),
        known_component_model_ids_by_unit=cast(
            tuple[tuple[str, tuple[str, ...]], ...],
            known_models,
        ),
        known_attached_component_ids_by_rules_unit=cast(
            tuple[tuple[str, tuple[str, ...]], ...],
            known_attached,
        ),
        known_logical_terrain_area_ids=("area-a",),
        known_objective_marker_ids=("objective-a",),
    )


def _validate_destruction_states(
    states: object,
    *,
    owner_by_unit_id: dict[str, str] | None = None,
) -> list[PrimaryUnitDestructionState]:
    if owner_by_unit_id is None:
        owner_by_unit_id = {"unit-destroyed": "player-b"}
    return validate_primary_unit_destruction_states(
        states,
        game_id="game-a",
        player_ids=("player-a", "player-b"),
        owner_by_unit_id=owner_by_unit_id,
        model_ids_by_unit_id={"unit-destroyed": ("model-destroyed",)},
        known_rules_unit_components_by_id={"unit-destroyed": ("unit-destroyed",)},
        known_objective_marker_ids=("objective-a",),
    )


def _build_tracking_destruction(
    *,
    state: GameState,
    unit: UnitInstance,
    attribution: ModelDestructionAttribution | None = None,
) -> PrimaryUnitDestructionState:
    return build_primary_unit_destruction_state(
        state=state,
        destruction_attribution=attribution,
        source_model_destroyed_event_id=(None if attribution is None else "event-model-destroyed"),
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=(),
        unattributed_cause=(
            PrimaryUnattributedDestructionCause.RESERVE_DEADLINE if attribution is None else None
        ),
        source_mutation_id=("mutation-reserve-deadline" if attribution is None else None),
        destroyed_unit_instance_id=unit.unit_instance_id,
        source_id="source-destruction-build",
    )


def _record_tracking_destruction_models(
    *,
    state: GameState,
    destroyed_model_instance_ids: tuple[str, ...],
    left_battlefield: bool = False,
    attribution: ModelDestructionAttribution | None = None,
    destroyed_witness: RulesUnitObjectiveProximityWitness | None = None,
) -> tuple[PrimaryUnitDestructionState, ...]:
    return record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=destroyed_model_instance_ids,
        destruction_attribution=attribution,
        source_model_destroyed_event_id=(None if attribution is None else "event-model-destroyed"),
        source_rules_unit_objective_proximity_witness=None,
        destroyed_rules_unit_objective_proximity_witness=destroyed_witness,
        unattributed_cause=(
            PrimaryUnattributedDestructionCause.RESERVE_DEADLINE if attribution is None else None
        ),
        source_mutation_id=("mutation-destruction" if attribution is None else None),
        left_battlefield=left_battlefield,
        source_id="source-destruction-mutation",
    )


def _unattributed_destruction_state() -> PrimaryUnitDestructionState:
    source_id = "source-destruction-a"
    return PrimaryUnitDestructionState(
        destruction_id=primary_unit_destruction_id(
            game_id="game-a",
            source_id=source_id,
            destroyed_unit_instance_id="unit-destroyed",
        ),
        game_id="game-a",
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=(),
        unattributed_cause=PrimaryUnattributedDestructionCause.RESERVE_DEADLINE,
        source_mutation_id="mutation-reserve-deadline-a",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=1,
        phase="command",
        destroyed_unit_instance_id="unit-destroyed",
        started_turn_terrain_feature_ids=("area-a",),
        started_turn_objective_marker_ids=("objective-a",),
        source_id=source_id,
    )


def _attributed_destruction_state(
    *,
    destroying_player_id: str = "player-a",
    witness_component_id: str = "unit-source",
    witness_model_id: str = "model-source",
) -> PrimaryUnitDestructionState:
    source_id = "source-destruction-attributed-a"
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=destroying_player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id="rules-unit-source",
        source_model_instance_id="model-source",
    )
    witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="rules-unit-source",
        component_unit_instance_ids=(witness_component_id,),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id="objective-a",
                model_instance_ids=(witness_model_id,),
            ),
        ),
    )
    return PrimaryUnitDestructionState(
        destruction_id=primary_unit_destruction_id(
            game_id="game-a",
            source_id=source_id,
            destroyed_unit_instance_id="unit-destroyed",
        ),
        game_id="game-a",
        destroying_player_id=destroying_player_id,
        destruction_attribution=attribution,
        source_model_destroyed_event_id="event-model-destroyed-a",
        source_rules_unit_objective_proximity_witness=witness,
        source_battlefield_departure_ids=("departure-a",),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=1,
        phase="shooting",
        destroyed_unit_instance_id="unit-destroyed",
        started_turn_terrain_feature_ids=("area-a",),
        started_turn_objective_marker_ids=("objective-a",),
        source_id=source_id,
    )


def _source_rule(
    *,
    rule_id: str,
    timing: str = "turn_end",
    source_kind: str = "primary",
    mode: MissionScoringResolutionMode = MissionScoringResolutionMode.CUMULATIVE,
    group_id: str | None = "shared-group",
) -> MissionScoringRuleDefinition:
    return MissionScoringRuleDefinition(
        rule_id=rule_id,
        timing=timing,
        source_kind=source_kind,
        victory_points=2,
        cap=None,
        condition="each-controlled-objective",
        resolution_mode=mode,
        resolution_group_id=group_id,
        source_id=f"source:{rule_id}",
    )


def _source_primary_mission(
    rules: tuple[MissionScoringRuleDefinition, ...],
) -> PrimaryMissionDefinition:
    return PrimaryMissionDefinition(
        primary_mission_id="primary-resolution-test",
        name="Resolution Test",
        source_id="source:primary-resolution-test",
        scoring_kind="structured-primary",
        scoring_rules=rules,
    )


def _runtime_rule(
    *,
    rule_id: str,
    timing: str = "turn_end",
    mode: MissionScoringResolutionMode = MissionScoringResolutionMode.CUMULATIVE,
    group_id: str | None = "shared-group",
) -> PrimaryMissionScoringRule:
    return PrimaryMissionScoringRule(
        rule_id=rule_id,
        timing=timing,
        source_kind=VictoryPointSourceKind.PRIMARY,
        victory_points=2,
        cap=None,
        condition="each-controlled-objective",
        resolution_mode=mode,
        resolution_group_id=group_id,
        source_id=f"source:{rule_id}",
    )


def _runtime_policy(
    rules: tuple[PrimaryMissionScoringRule, ...],
    *,
    player_id: str = "player-a",
    primary_mission_id: str = "primary-resolution-test",
) -> MissionScoringPolicy:
    return MissionScoringPolicy(
        player_id=player_id,
        force_disposition_id="force-a",
        mission_pack_id="mission-pack",
        primary_mission_id=primary_mission_id,
        primary_scoring_supported=True,
        game_length_battle_rounds=5,
        primary_scoring_phase="command",
        primary_scoring_timing=ObjectiveControlTiming.PHASE_END,
        primary_scoring_rule_id=None,
        primary_scoring_rule_condition=None,
        primary_scoring_rule_source_id=None,
        primary_vp_per_controlled_objective=None,
        primary_max_vp_per_turn=15,
        primary_scoring_rules=rules,
        secondary_vp_per_score=5,
        secondary_scoring_rules=(),
        mission_action_scoring_rules=(),
        mission_action_vp=3,
        reserve_destruction_timing="battle-round-end",
        reserve_destruction_battle_round=None,
        reserve_destruction_excludes_during_battle_strategic_reserves=True,
        reserve_destruction_only_declare_battle_formations=True,
        primary_vp_cap=50,
        secondary_vp_cap=40,
        battle_ready_vp=10,
        total_vp_cap=100,
        secondary_max_vp_per_turn=15,
        end_of_round_scoring_windows=("end-of-round",),
        end_of_game_scoring_windows=("end-of-game",),
        source_id="source:mission-policy",
    )


def _test_primary_state_evidence(
    *,
    record: ObjectiveControlRecord,
    end_of_battle: bool,
) -> PrimaryScoringStateEvidence:
    return PrimaryScoringStateEvidence.create(
        scoring_player_id=record.active_player_id,
        game_id=record.game_id,
        battlefield_id=record.battlefield_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        scoring_boundary_kind=(
            PrimaryScoringBoundaryKind.END_OF_BATTLE
            if end_of_battle
            else PrimaryScoringBoundaryKind.ORDINARY
        ),
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        scoring_commit_checkpoint_id="primary-mission-boundary:" + "0" * 64,
        scoring_commit_checkpoint_hash="0" * 64,
        primary_mission_progress_state=PrimaryMissionProgressState.empty(),
        primary_mission_action_states=(),
        primary_battlefield_departure_states=(),
        primary_unit_destruction_state_ids=(),
        current_rules_unit_position_witnesses=(),
        primary_scoring_spatial_evidence_by_player_id=(),
    )


def _candidate(
    *,
    rule_id: str,
    amount: int,
    mode: PrimaryScoringResolutionMode = PrimaryScoringResolutionMode.INDEPENDENT,
    group_id: str | None = None,
) -> PrimaryScoringResolutionCandidate:
    return PrimaryScoringResolutionCandidate(
        rule_id=rule_id,
        amount=amount,
        resolution_mode=mode,
        resolution_group_id=group_id,
    )


__all__: list[str] = []
__all__ += ["BattlefieldRuntimeState", "DestructionSourceKind", "EndTurnCleanupState", "EventLog"]
__all__ += ["GameLifecycleError", "GameLifecycleStage", "GameState", "MissionPackError"]
__all__ += ["MissionScoringPolicies", "MissionScoringPolicy", "MissionScoringResolutionMode"]
__all__ += ["MissionScoringRuleDefinition", "MissionSetup", "ModelDestructionAttribution"]
__all__ += ["ModelPlacement", "ObjectiveControlRecord", "ObjectiveControlResult"]
__all__ += ["ObjectiveControlStatus", "ObjectiveControlTiming", "ObjectiveMarkerModelWitness"]
__all__ += ["PlayerPrimaryMissionAssignment", "Pose", "PrimaryComponentTurnStartMembership"]
__all__ += ["PrimaryMissionDefinition", "PrimaryMissionProgressState"]
__all__ += ["PrimaryMissionScoringRule", "PrimaryObjectiveMarkerWitness"]
__all__ += ["PrimaryRulesUnitTurnStartMembership", "PrimaryRulesUnitTurnStartSnapshot"]
__all__ += ["PrimaryScoringBoundaryKind", "PrimaryScoringResolutionCandidate"]
__all__ += ["PrimaryScoringResolutionMode", "PrimaryScoringStateEvidence"]
__all__ += ["PrimaryUnattributedDestructionCause", "PrimaryUnitDestructionState"]
__all__ += ["ResolvedPrimaryScoringCandidate", "RulesUnitObjectiveProximityWitness"]
__all__ += ["SUPPORTED_PRIMARY_SCORING_TIMINGS", "RulesetDescriptor", "UnitInstance"]
__all__ += ["VictoryPointAward", "VictoryPointLedger", "VictoryPointSourceKind"]
__all__ += ["VictoryPointTransaction", "_attributed_destruction_state"]
__all__ += ["_build_tracking_destruction", "_candidate", "_catalog_tracking_state"]
__all__ += ["_deadly_demise_attribution", "_evidence_model_placement"]
__all__ += ["_minimal_evidence_game_state", "_record_tracking_destruction_models"]
__all__ += ["_runtime_policy", "_runtime_rule", "_source_objective_witness"]
__all__ += ["_source_primary_mission", "_source_rule", "_test_primary_state_evidence"]
__all__ += ["_turn_start_component", "_turn_start_snapshot", "_unattributed_destruction_state"]
__all__ += ["_validate_destruction_states", "_validate_turn_start_snapshots"]
__all__ += ["attached_selected_to_fight_risk_fixture", "battle_state_with_army"]
__all__ += ["bloodcrushers_army", "bloodcrushers_battlefield_state", "bloodcrushers_package"]
__all__ += ["bloodcrushers_unit", "build_primary_rules_unit_turn_start_snapshot"]
__all__ += ["build_primary_unit_destruction_state", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack"]
__all__ += ["current_primary_component_turn_start_membership"]
__all__ += ["current_primary_rules_unit_turn_start_membership"]
__all__ += ["destruction_source_objective_proximity_witness", "objective_control_record_hash"]
__all__ += ["primary_rules_unit_turn_start_membership_for_lineage"]
__all__ += ["primary_rules_unit_turn_start_snapshots_from_payload"]
__all__ += ["primary_rules_unit_turn_start_snapshots_with_created_unit"]
__all__ += ["primary_scoring_resolution_mode_from_token", "primary_scoring_timing_applies"]
__all__ += ["primary_unit_destruction_id", "pytest", "record_primary_destroyed_model_departures"]
__all__ += ["record_primary_rules_unit_turn_start_snapshot", "record_primary_turn_start_evidence"]
__all__ += ["record_primary_unit_destructions_for_destroyed_models"]
__all__ += ["record_primary_unit_destructions_for_end_turn_cleanup", "replace"]
__all__ += ["resolve_primary_scoring_candidates", "rules_unit_objective_proximity_witness"]
__all__ += ["validate_primary_objective_turn_start_states"]
__all__ += ["validate_primary_rules_unit_turn_start_snapshots"]
__all__ += ["validate_primary_unit_destruction_source_witness_identity"]
__all__ += ["validate_primary_unit_destruction_states"]
__all__ += ["validate_primary_unit_destruction_turn_start_evidence"]
__all__ += ["validate_victory_point_ledger_policy"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
