from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
)
from tests.setup_completion_helpers import enter_battle_for_fixture

from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.deployment_zones import (
    DeploymentZoneCircleCutout,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.weapon_profiles import DamageProfile
from warhammer40k_core.engine import (
    primary_destruction_timeline_integrity as destruction_timeline_integrity,
)
from warhammer40k_core.engine import (
    primary_historical_event_integrity as historical_event_integrity,
)
from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatus,
    interrupt_mission_action_for_battlefield_departure,
    interrupt_mission_action_for_displacement,
    mission_action_interruption_reason_for_displacement,
    mission_action_status_from_token,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_model import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelPlacement,
    ModelRemovalRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import (
    CommandPointGainStatus,
    CommandPointSourceKind,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_action_eligibility import (
    MISSION_ACTION_UNIT_ALREADY_STARTED_ACTION,
    mission_action_unit_ineligibility_reason,
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    START_MISSION_ACTION_DECISION_TYPE,
    TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
    TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    request_mission_action_start,
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
)
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    PlayerPrimaryMissionAssignment,
)
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    logical_terrain_area_within_player_deployment_zone,
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PlaceholderPhaseHandler,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_event_integrity import (
    validate_primary_historical_event_integrity,
)
from warhammer40k_core.engine.primary_historical_events import (
    primary_reserve_entry_source_terminal_bindings_payload,
    record_new_primary_battlefield_departure_events,
    record_new_primary_turn_start_evidence_events,
    record_primary_battlefield_departure_event,
    record_primary_reserve_entry_mutation_event,
    record_primary_reserve_entry_provider_terminal_event,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
    reserve_entry_evidence_payload,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
    cross_turn_destruction_comparison_evidence,
    opponent_home_control_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    primary_unit_destruction_id,
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
)
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    apply_return_on_death_placement_decision,
    build_return_on_death_placement_request,
)
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryObjectiveTurnStartStatePayload,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    PrimaryUnitDestructionStatePayload,
    SecondaryDestroyedModelState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionScoringRule,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    TacticalSecondaryAchievementContext,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    objective_control_timing_from_token,
    secondary_mission_card_mode_from_token,
    secondary_mission_card_status_from_token,
    victory_point_source_kind_from_token,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.transports import (
    TransportCapacityProfile,
    TransportCargoState,
)
from warhammer40k_core.engine.turn_cleanup import (
    CoherencyCleanupRemoval,
    EndTurnCleanupState,
    battlefield_removal_kind_from_token,
    resolve_end_turn_cleanup,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    ATTACHED_UNIT_DESTRUCTION_SOURCE_RULE_ID,
    ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256,
    unit_destruction_completion_events_for_interval,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext, StartingStrengthRecord
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.engine.weapon_abilities import (
    FIRE_OVERWATCH_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.interfaces.cli import render_pending_decision_for_cli
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)

SEEDED_TACTICAL_DRAW_REQUEST_ID = "phase11e-seeded-tactical-draw-request"
SEEDED_TACTICAL_DRAW_RESULT_ID = "phase11e-seeded-tactical-draw"
SCORING_TERRAIN_FEATURE_ID = "phase11e-scoring-terrain"


@pytest.fixture(scope="module")
def authentic_primary_destruction_lifecycle_payload() -> GameLifecyclePayload:
    return _authentic_primary_destruction_lifecycle_payload()


@pytest.fixture(scope="module")
def authentic_reserve_deadline_lifecycle_payload() -> GameLifecyclePayload:
    return _authentic_reserve_deadline_lifecycle_payload()


@pytest.fixture(scope="module")
def authentic_attached_unit_lifecycle_payload() -> GameLifecyclePayload:
    return _authentic_attached_unit_lifecycle_payload()


def test_attached_unit_destruction_source_pin_matches_official_core_rules_page_66() -> None:
    source_pdf = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "source_rules"
        / "eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf"
    )

    assert sha256(source_pdf.read_bytes()).hexdigest() == (ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256)
    assert ATTACHED_UNIT_DESTRUCTION_SOURCE_RULE_ID.endswith("19.02-attached-units")


def test_immovable_object_scores_central_and_non_home_objectives_by_round() -> None:
    turn_end_state = _battle_state_for_primary("primary-immovable-object")
    _place_unit_near_objective(
        turn_end_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    turn_end_state.battle_phase_index = turn_end_state.battle_phase_sequence.index(
        BattlePhase.FIGHT
    )

    turn_end_state.advance_to_next_battle_phase()

    assert turn_end_state.victory_point_total("player-a") == 3
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in turn_end_state.victory_point_ledger_for_player("player-a").transactions
    ] == ["immovable-object-central-turn-end"]

    command_state = _battle_state_for_primary("primary-immovable-object")
    command_state.battle_round = 2
    _place_unit_near_objective(
        command_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    command_state.advance_to_next_battle_phase()

    assert command_state.victory_point_total("player-a") == 5
    command_transaction = command_state.victory_point_ledger_for_player("player-a").transactions[0]
    command_metadata = _transaction_metadata(command_transaction)
    assert command_metadata["scoring_rule_id"] == ("immovable-object-rounds-two-to-four-command")
    assert command_metadata["controlled_objective_ids"] == [
        "take-and-hold-vs-purge-the-foe-layout-3-center-central"
    ]

    fifth_round_state = _battle_state_for_primary("primary-immovable-object")
    fifth_round_state.battle_round = 5
    _place_unit_near_objective(
        fifth_round_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    fifth_round_state.battle_phase_index = fifth_round_state.battle_phase_sequence.index(
        BattlePhase.FIGHT
    )

    fifth_round_state.advance_to_next_battle_phase()

    assert fifth_round_state.victory_point_total("player-a") == 8
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in fifth_round_state.victory_point_ledger_for_player(
            "player-a"
        ).transactions
    ] == [
        "immovable-object-central-turn-end",
        "immovable-object-round-five-turn-end",
    ]


def test_unstoppable_force_scores_kills_new_objectives_and_end_battle_central_control() -> None:
    turn_state = _battle_state_for_primary("primary-unstoppable-force")
    _place_unit_near_objective(
        turn_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    _remove_unit_for_primary_destruction(
        turn_state,
        unit_instance_id="army-beta:intercessor-unit-3",
    )
    _record_test_primary_unit_destruction(
        turn_state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id="army-beta:intercessor-unit-3",
        source_id="phase16:unstoppable-force:enemy-destroyed",
    )
    turn_state.battle_phase_index = turn_state.battle_phase_sequence.index(BattlePhase.FIGHT)

    turn_state.advance_to_next_battle_phase()

    assert turn_state.victory_point_total("player-a") == 6
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"]
        for transaction in turn_state.victory_point_ledger_for_player("player-a").transactions
    ] == [
        "unstoppable-force-enemy-destroyed-turn-end",
        "unstoppable-force-new-objective-turn-end",
    ]

    command_state = _battle_state_for_primary("primary-unstoppable-force")
    command_state.battle_round = 2
    _place_unit_near_objective(
        command_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    command_state.advance_to_next_battle_phase()

    assert command_state.victory_point_total("player-a") == 4
    assert (
        _transaction_metadata(
            command_state.victory_point_ledger_for_player("player-a").transactions[0]
        )["scoring_rule_id"]
        == "unstoppable-force-objectives"
    )

    end_state = _battle_state_for_primary("primary-unstoppable-force")
    end_state.battle_round = 5
    end_state.active_player_id = "player-b"
    record_primary_turn_start_evidence(state=end_state)
    _place_unit_near_objective(
        end_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    end_state.battle_phase_index = end_state.battle_phase_sequence.index(BattlePhase.FIGHT)

    end_state.advance_to_next_battle_phase()

    assert end_state.stage is GameLifecycleStage.COMPLETE
    assert end_state.victory_point_total("player-a") == 5
    assert (
        _transaction_metadata(
            end_state.victory_point_ledger_for_player("player-a").transactions[0]
        )["scoring_rule_id"]
        == "unstoppable-force-central-end-battle"
    )


def test_death_trap_booby_trap_action_tracks_exact_logical_objective_terrain() -> None:
    config = _config_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    mission_setup = cast(MissionSetup, config.mission_setup)
    area = _objective_logical_terrain_area(
        mission_setup,
        objective_role=ObjectiveMarkerRole.CENTRAL,
    )
    area_id = area.logical_terrain_area_id
    central_marker = next(
        marker
        for marker in mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    assert not any(
        shapely_backend.point_intersects_polygon(
            central_marker.x_inches,
            central_marker.y_inches,
            feature.rules_footprint_points(),
        )
        for feature in mission_setup.terrain_features
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    target_member = area.members[0]
    target_point = target_member.footprint_polygon[0]
    _place_unit_near_point(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=target_point.x_inches,
        y_inches=target_point.y_inches,
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="booby-trap-terrain",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["target_id"] == area_id
    )
    assert cast(dict[str, JsonValue], option.payload)["target_kind"] == "terrain_area"
    lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id,
            selected_option_id=option.option_id,
            result_id="phase16-start-booby-trap",
        ).to_result(request)
    )
    action = state.mission_action_state_by_id("mission-action:phase16-start-booby-trap")
    trap_state = state.primary_terrain_trap_states[0]

    assert action.status is MissionActionStatus.COMPLETED
    assert action.score_transaction_id is None
    assert trap_state.terrain_feature_id == area_id
    assert trap_state.is_objective is True


@pytest.mark.parametrize(
    "starts_inside",
    [
        pytest.param(True, id="start-inside-move-out"),
        pytest.param(False, id="start-outside-move-in"),
    ],
)
def test_death_trap_scores_authoritative_turn_start_terrain_membership(
    starts_inside: bool,
) -> None:
    config = _config_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    area = _objective_logical_terrain_area(
        cast(MissionSetup, config.mission_setup),
        objective_role=ObjectiveMarkerRole.CENTRAL,
    )
    area_id = area.logical_terrain_area_id
    enemy_unit_id = "army-beta:intercessor-unit-3"
    inside = _logical_terrain_area_test_point(area)
    outside = (5.0, 5.0)
    start = inside if starts_inside else outside
    state = _battle_state_from_config(
        config,
        turn_start_unit_positions=((enemy_unit_id, *start),),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    trap_action_id = f"mission-action:death-trap-turn-start-{starts_inside}"
    trap_source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="booby-trap-terrain",
        action_id=trap_action_id,
        target_id=area_id,
    )
    state.record_primary_terrain_trap(
        player_id="player-a",
        terrain_feature_id=area_id,
        action_id=trap_action_id,
        phase=BattlePhase.SHOOTING,
        source_id=trap_source_id,
    )

    end = outside if starts_inside else inside
    _place_unit_near_point(
        state,
        unit_instance_id=enemy_unit_id,
        x_inches=end[0],
        y_inches=end[1],
    )
    enemy_unit = state.army_definitions[1].unit_by_id(enemy_unit_id)
    destroyed_model_ids = tuple(model.model_instance_id for model in enemy_unit.own_models)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    (destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=destroyed_model_ids,
        destroying_player_id="player-a",
        source_id="phase17n:death-trap:runtime-destruction",
    )
    assert destruction.started_turn_terrain_feature_ids == ((area_id,) if starts_inside else ())


def test_turn_start_position_snapshot_groups_attached_unit_without_collapsing_components() -> None:
    mission_setup = _mission_setup_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    config = _config_with_player_a_attached_unit(
        mission_setup=mission_setup,
    )
    area = _objective_logical_terrain_area(
        mission_setup,
        objective_role=ObjectiveMarkerRole.CENTRAL,
    )
    central_marker = next(
        marker
        for marker in mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    area_id = area.logical_terrain_area_id
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    state = _battle_state_from_config(
        config,
        turn_start_unit_positions=(
            (
                bodyguard_id,
                central_marker.x_inches,
                central_marker.y_inches,
            ),
            (leader_id, 5.0, 5.0),
        ),
    )

    snapshot = state.primary_rules_unit_turn_start_snapshots[0]
    (starting_attached_record,) = state.starting_attached_unit_records
    membership = snapshot.membership_for_rules_unit(
        starting_attached_record.attached_unit_instance_id
    )
    assert membership.component_unit_instance_ids == tuple(sorted((bodyguard_id, leader_id)))
    assert membership.component_membership_for_unit(bodyguard_id).logical_terrain_area_ids == (
        area_id,
    )
    assert membership.component_membership_for_unit(leader_id).logical_terrain_area_ids == ()
    assert membership.terrain_feature_ids == (area_id,)
    bodyguard_model_ids = {
        model.model_instance_id
        for model in state.army_definitions[0].unit_by_id(bodyguard_id).own_models
    }
    assert set(membership.evaluated_model_instance_ids) == {
        model.model_instance_id
        for component_id in (bodyguard_id, leader_id)
        for model in state.army_definitions[0].unit_by_id(component_id).own_models
    }
    assert membership.objective_marker_ids == (central_marker.objective_marker_id,)
    (outer_witness,) = membership.objective_marker_witnesses
    assert outer_witness.objective_marker_id == central_marker.objective_marker_id
    assert set(outer_witness.model_instance_ids) == bodyguard_model_ids
    (bodyguard_witness,) = membership.component_membership_for_unit(
        bodyguard_id
    ).objective_marker_witnesses
    assert bodyguard_witness == outer_witness
    assert membership.component_membership_for_unit(leader_id).objective_marker_witnesses == ()

    bodyguard = state.army_definitions[0].unit_by_id(bodyguard_id)
    destroyed_model_ids = tuple(model.model_instance_id for model in bodyguard.own_models)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )
    assert not _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=destroyed_model_ids,
        destroying_player_id="player-b",
        source_id="phase17n:death-trap:attached-bodyguard-destruction",
    )
    assert not state.primary_unit_destruction_states

    leader = state.army_definitions[0].unit_by_id(leader_id)
    leader_model_ids = leader.own_model_ids()
    state.replace_battlefield_state(state.battlefield_state.with_removed_models(leader_model_ids))
    (destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=leader_model_ids,
        destroying_player_id="player-b",
        source_id="phase17n:death-trap:attached-leader-destruction",
    )

    assert destruction.destroyed_unit_instance_id == (
        starting_attached_record.attached_unit_instance_id
    )
    assert destruction.started_turn_terrain_feature_ids == (area_id,)


def test_turn_start_position_snapshot_is_public_for_unplaced_opponent_unit() -> None:
    config = _config_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    reserve_unit_id = "army-beta:intercessor-unit-3"
    state = _battle_state_from_config(
        config,
        turn_start_unplaced_unit_ids=(reserve_unit_id,),
    )
    snapshot = state.primary_rules_unit_turn_start_snapshots[0]
    session = LocalGameSession()
    session.start(config)
    session.lifecycle.state = state

    player_payload = session.view(viewer_player_id="player-a")
    opponent_payload = session.view(viewer_player_id="player-b")
    administrator_payload = session.view_for_context(
        viewer=AuthenticatedPrincipal(
            principal_id="phase17n-turn-start-administrator",
            role=PrincipalRole.ADMINISTRATOR,
        ).bind_to_session(player_ids=state.player_ids)
    )
    assert snapshot.membership_for_rules_unit(reserve_unit_id).evaluated_model_instance_ids == ()
    player_snapshot = player_payload["primary_rules_unit_turn_start_snapshots"][0]
    opponent_snapshot = opponent_payload["primary_rules_unit_turn_start_snapshots"][0]
    administrator_snapshot = administrator_payload["primary_rules_unit_turn_start_snapshots"][0]
    player_memberships = player_snapshot["rules_unit_memberships"]
    opponent_memberships = opponent_snapshot["rules_unit_memberships"]
    assert any(
        membership["rules_unit_instance_id"] == reserve_unit_id for membership in player_memberships
    )
    assert player_memberships == opponent_memberships
    assert reserve_unit_id in player_payload["unit_display_by_id"]
    assert reserve_unit_id in opponent_payload["unit_display_by_id"]
    assert player_snapshot == snapshot.to_payload()
    assert opponent_snapshot == snapshot.to_payload()
    assert administrator_snapshot == snapshot.to_payload()
    assert json.loads(json.dumps(player_payload, sort_keys=True)) == player_payload


def test_turn_start_position_snapshot_projects_complete_attached_group_to_both_players() -> None:
    state = _battle_state_from_config(_config_with_player_a_attached_unit())
    (starting_attached_record,) = state.starting_attached_unit_records
    bodyguard_id = starting_attached_record.bodyguard_unit_instance_id
    (leader_id,) = starting_attached_record.leader_unit_instance_ids
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.without_unit_placement(leader_id))
    session = LocalGameSession()
    session.start(_config_with_player_a_attached_unit())
    session.lifecycle.state = state

    opponent_view = session.view(viewer_player_id="player-b")
    owner_view = session.view(viewer_player_id="player-a")
    opponent_memberships = opponent_view["primary_rules_unit_turn_start_snapshots"][0][
        "rules_unit_memberships"
    ]
    owner_memberships = owner_view["primary_rules_unit_turn_start_snapshots"][0][
        "rules_unit_memberships"
    ]

    assert bodyguard_id in opponent_view["unit_display_by_id"]
    assert leader_id in opponent_view["unit_display_by_id"]
    assert opponent_memberships == owner_memberships
    (attached_membership,) = tuple(
        membership
        for membership in opponent_memberships
        if membership["rules_unit_instance_id"]
        == starting_attached_record.attached_unit_instance_id
    )
    assert {
        component["unit_instance_id"] for component in attached_membership["component_memberships"]
    } == {bodyguard_id, leader_id}


def test_turn_start_position_snapshot_participates_in_projection_hash() -> None:
    config = _config_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    area = _objective_logical_terrain_area(
        cast(MissionSetup, config.mission_setup),
        objective_role=ObjectiveMarkerRole.CENTRAL,
    )
    unit_id = "army-beta:intercessor-unit-3"
    outside = (5.0, 5.0)
    started_inside = _battle_state_from_config(
        config,
        turn_start_unit_positions=(
            (
                unit_id,
                *_logical_terrain_area_test_point(area),
            ),
        ),
    )
    _place_unit_near_point(
        started_inside,
        unit_instance_id=unit_id,
        x_inches=outside[0],
        y_inches=outside[1],
    )
    started_outside = _battle_state_from_config(
        config,
        turn_start_unit_positions=((unit_id, *outside),),
    )
    assert started_inside.battlefield_state == started_outside.battlefield_state

    inside_session = LocalGameSession()
    inside_session.start(config)
    inside_session.lifecycle.state = started_inside
    outside_session = LocalGameSession()
    outside_session.start(config)
    outside_session.lifecycle.state = started_outside
    inside_view = inside_session.view(viewer_player_id="player-a")
    outside_view = outside_session.view(viewer_player_id="player-a")

    assert (
        inside_view["primary_rules_unit_turn_start_snapshots"]
        != outside_view["primary_rules_unit_turn_start_snapshots"]
    )
    assert inside_view["projection_state_hash"] != outside_view["projection_state_hash"]


def test_meatgrinder_real_attack_destruction_is_captured_and_scores_current_turn() -> None:
    config = _config_with_player_b_character(
        mission_setup=_event_companion_meatgrinder_mission_setup()
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_state_from_config(config, decisions=lifecycle.decision_controller)
    lifecycle.state = state
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    assert state.active_player_id == "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    assert state.battle_round == 2
    assert state.active_player_id == "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attacker = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-alpha:intercessor-unit-1"
    )
    defender = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-beta:character-unit-3"
    )
    (defender_model,) = defender.own_models
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence_id = "phase17n-meatgrinder-runtime-attack"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    remaining, _allocated_model_ids, attack_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    assert remaining is None
    assert attack_status is None
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        }
    )
    flow.advance(state=state, decisions=lifecycle.decision_controller)
    (destruction,) = state.primary_unit_destruction_states
    assert destruction.destroyed_unit_instance_id == defender.unit_instance_id
    assert destruction.started_turn_terrain_feature_ids == ()
    capture_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "primary_unit_destruction_recorded"
    )
    assert len(capture_events) == 1

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="defender_home",
    )

    flow.advance(state=state, decisions=lifecycle.decision_controller)

    transactions = state.victory_point_ledger_for_player("player-a").transactions
    current_turn_destruction_metadata = _transaction_metadata(transactions[0])
    comparison_metadata = _transaction_metadata(transactions[1])
    home_metadata = _transaction_metadata(transactions[2])
    assert state.victory_point_total("player-a") == 13
    assert [
        metadata["scoring_rule_id"] for metadata in map(_transaction_metadata, transactions)
    ] == [
        "meatgrinder-enemy-destroyed-turn-end",
        "meatgrinder-more-destroyed-turn-end",
        "meatgrinder-opponent-home-turn-end",
    ]
    assert current_turn_destruction_metadata["destroyed_unit_instance_ids"] == [
        "army-beta:character-unit-3"
    ]
    assert comparison_metadata["previous_turn_battle_round"] == 1
    assert comparison_metadata["previous_turn_active_player_id"] == "player-b"
    assert comparison_metadata["current_turn_battle_round"] == 2
    assert comparison_metadata["current_turn_active_player_id"] == "player-a"
    assert comparison_metadata["enemy_units_destroyed"] == 1
    assert comparison_metadata["friendly_units_destroyed"] == 0
    assert comparison_metadata["enemy_destroyed_unit_instance_ids"] == [
        "army-beta:character-unit-3"
    ]
    assert comparison_metadata["friendly_destroyed_unit_instance_ids"] == []
    assert home_metadata["controlled_objective_ids"] == [
        "purge-the-foe-vs-purge-the-foe-layout-1-defender-home"
    ]
    assert home_metadata["opponent_home_objective_ids"] == [
        "purge-the-foe-vs-purge-the-foe-layout-1-defender-home"
    ]
    assert str(comparison_metadata["scoring_rule_source_id"]).startswith(
        "gw-11e-warhammer-event-companion-v1-1-2026-07:primary:primary-meatgrinder:"
    )
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()

    forged_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    forged_events = forged_payload["decisions"]["event_log"]
    forged_events.append(
        {
            "event_id": f"event-{len(forged_events) + 1:06d}",
            "event_type": "healing_step_resolved",
            "payload": {
                "effect_id": "phase17n:forged-restoration",
                "target_unit_instance_id": defender.unit_instance_id,
                "amount": 1,
                "source_rule_id": "phase17n:forged-restoration:rule",
                "source_context": None,
                "step": {
                    "step_index": 1,
                    "step_kind": "revive_model_embarked",
                    "model_instance_id": defender_model.model_instance_id,
                    "starting_wounds_remaining": 0,
                    "final_wounds_remaining": 1,
                    "request_id": "phase17n:forged-restoration:request",
                    "result_id": "phase17n:forged-restoration:result",
                    "transition_batch": None,
                },
            },
        }
    )
    with pytest.raises(
        GameLifecycleError,
        match="requires one authoritative decision event",
    ):
        GameLifecycle.from_payload(forged_payload)


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("game-id", "game_id drift", id="destruction-game-id"),
        pytest.param("player-id", "player_id is not in this game", id="destroyed-player-id"),
        pytest.param(
            "unknown-destroyed-unit",
            "references an unknown destroyed unit",
            id="unknown-destroyed-unit",
        ),
        pytest.param("duplicate-state", "states must be unique", id="duplicate-state"),
        pytest.param(
            "unknown-source-rules-unit",
            "source witness references an unknown rules unit",
            id="unknown-source-rules-unit",
        ),
        pytest.param(
            "source-model-outside-unit",
            "source model is not in the source rules unit",
            id="source-model-outside-unit",
        ),
        pytest.param(
            "witness-model-outside-unit",
            "source witness references a model outside its rules unit",
            id="witness-model-outside-unit",
        ),
    ],
)
def test_primary_destruction_lifecycle_restore_rejects_identity_corruption(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(authentic_primary_destruction_lifecycle_payload, sort_keys=True)),
    )
    state_payload = payload["state"]
    (destruction,) = state_payload["primary_unit_destruction_states"]
    attribution = destruction["destruction_attribution"]
    witness = destruction["source_rules_unit_objective_proximity_witness"]
    assert attribution is not None
    assert witness is not None

    if corruption == "game-id":
        destruction["game_id"] = "phase17n-corrupted-game"
    elif corruption == "player-id":
        destruction["destroyed_player_id"] = "player-unknown"
    elif corruption == "unknown-destroyed-unit":
        destruction["destroyed_unit_instance_id"] = "army-beta:unknown-unit"
    elif corruption == "duplicate-state":
        state_payload["primary_unit_destruction_states"].append(
            cast(
                PrimaryUnitDestructionStatePayload,
                json.loads(json.dumps(destruction, sort_keys=True)),
            )
        )
    elif corruption == "unknown-source-rules-unit":
        attribution["source_rules_unit_instance_id"] = "army-alpha:unknown-unit"
        attribution["attacking_unit_instance_id"] = "army-alpha:unknown-unit"
        witness["rules_unit_instance_id"] = "army-alpha:unknown-unit"
    elif corruption == "source-model-outside-unit":
        outside_model_id = destruction["destroyed_unit_instance_id"] + ":model-001"
        attribution["source_model_instance_id"] = outside_model_id
        attribution["attacking_model_instance_id"] = outside_model_id
    elif corruption == "witness-model-outside-unit":
        mission_setup = state_payload["mission_setup"]
        assert mission_setup is not None
        witness["objective_marker_witnesses"] = [
            {
                "objective_marker_id": mission_setup["objective_markers"][0]["objective_marker_id"],
                "model_instance_ids": [destruction["destroyed_unit_instance_id"] + ":model-001"],
            }
        ]
    else:
        raise AssertionError(f"unsupported destruction corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param(
            "scoring-source",
            "Reserve-deadline Primary destruction source drift",
            id="scoring-source",
        ),
        pytest.param(
            "destroyed-round",
            "requires one destroyed ReserveState route",
            id="destroyed-reserve-round",
        ),
    ],
)
def test_reserve_deadline_lifecycle_restore_rejects_timeline_corruption(
    authentic_reserve_deadline_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(authentic_reserve_deadline_lifecycle_payload, sort_keys=True)),
    )
    (destruction,) = payload["state"]["primary_unit_destruction_states"]
    if corruption == "scoring-source":
        original_destruction_id = destruction["destruction_id"]
        destruction["source_id"] = "phase17n-corrupted-reserve-source"
        destruction["destruction_id"] = primary_unit_destruction_id(
            game_id=destruction["game_id"],
            source_id=destruction["source_id"],
            destroyed_unit_instance_id=destruction["destroyed_unit_instance_id"],
        )
        recorded_event = next(
            event
            for event in payload["decisions"]["event_log"]
            if event["event_type"] == "primary_unit_destruction_recorded"
        )
        recorded_payload = cast(dict[str, JsonValue], recorded_event["payload"])
        recorded_destruction = cast(
            dict[str, JsonValue],
            recorded_payload["primary_unit_destruction_state"],
        )
        assert recorded_destruction["destruction_id"] == original_destruction_id
        recorded_payload["primary_unit_destruction_state"] = cast(
            JsonValue,
            json.loads(json.dumps(destruction, sort_keys=True)),
        )
    elif corruption == "destroyed-round":
        payload["state"]["reserve_states"][0]["destroyed_battle_round"] = 2
    else:
        raise AssertionError(f"unsupported reserve timeline corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    "preexisting_cargo_casualty",
    [
        pytest.param(False, id="complete-cargo"),
        pytest.param(True, id="preexisting-cargo-casualty"),
    ],
)
def test_reserve_deadline_retires_current_transport_cargo_and_round_trips(
    preexisting_cargo_casualty: bool,
) -> None:
    lifecycle, _cargo_state, route_model_ids = _transport_reserve_deadline_lifecycle(
        preexisting_cargo_casualty=preexisting_cargo_casualty
    )

    _resolve_transport_reserve_at_round_boundary(lifecycle)

    state = cast(GameState, lifecycle.state)
    reserve_state = state.reserve_state_for_unit("army-alpha:transport-unit-2")
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.DESTROYED
    assert reserve_state.embarked_unit_instance_ids == ("army-alpha:intercessor-unit-1",)
    assert state.transport_cargo_state_for_transport("army-alpha:transport-unit-2") is None
    assert state.battlefield_state is not None
    assert set(route_model_ids) <= set(state.battlefield_state.removed_model_ids)
    assert set(route_model_ids).isdisjoint(state.battlefield_state.placed_model_ids())

    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.to_payload() == lifecycle.to_payload()


def test_end_of_battle_reserve_destruction_retires_current_transport_cargo() -> None:
    core_policy = ReserveDestructionTimingPolicy.core_rules_default()
    lifecycle, _cargo_state, route_model_ids = _transport_reserve_deadline_lifecycle(
        destruction_deadline_policy=core_policy
    )
    state = cast(GameState, lifecycle.state)
    assert state.battlefield_state is not None
    state.battle_round = 5
    record_primary_turn_start_evidence(state=state)
    destruction = resolve_unarrived_reserve_destruction(
        reserve_states=tuple(state.reserve_states),
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
        policy=core_policy,
        battle_round=5,
        end_of_battle=True,
    )

    state._apply_unarrived_reserve_destruction(  # pyright: ignore[reportPrivateUsage]
        destruction=destruction
    )

    reserve_state = state.reserve_state_for_unit("army-alpha:transport-unit-2")
    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.DESTROYED
    assert reserve_state.embarked_unit_instance_ids == ("army-alpha:intercessor-unit-1",)
    assert state.transport_cargo_state_for_transport("army-alpha:transport-unit-2") is None
    assert state.battlefield_state is not None
    assert set(route_model_ids) <= set(state.battlefield_state.removed_model_ids)
    assert set(route_model_ids).isdisjoint(state.battlefield_state.placed_model_ids())
    state_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    assert GameState.from_payload(state_payload).to_payload() == state.to_payload()


@pytest.mark.parametrize(
    "terminal_cargo_kind",
    [
        pytest.param("stale", id="stale-exact-row"),
        pytest.param("mismatched", id="mismatched-row"),
    ],
)
def test_restore_rejects_current_cargo_row_for_destroyed_reserve_transport(
    terminal_cargo_kind: str,
) -> None:
    lifecycle, cargo_state, _route_model_ids = _transport_reserve_deadline_lifecycle()
    _resolve_transport_reserve_at_round_boundary(lifecycle)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    cargo_payload = cargo_state.to_payload()
    if terminal_cargo_kind == "mismatched":
        cargo_payload["embarked_unit_instance_ids"] = []
    payload["state"]["transport_cargo_states"].append(cargo_payload)

    with pytest.raises(
        GameLifecycleError,
        match="destroyed reserve route must not retain current cargo",
    ):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    "active_cargo_drift",
    [
        pytest.param("missing", id="missing-current-cargo"),
        pytest.param("mismatched", id="mismatched-current-cargo"),
    ],
)
def test_reserve_deadline_rejects_active_cargo_drift_before_atomic_mutation(
    active_cargo_drift: str,
) -> None:
    lifecycle, cargo_state, _route_model_ids = _transport_reserve_deadline_lifecycle()
    state = cast(GameState, lifecycle.state)
    if active_cargo_drift == "missing":
        state.remove_transport_cargo_state(cargo_state.transport_unit_instance_id)
    else:
        state.replace_transport_cargo_state(replace(cargo_state, embarked_unit_instance_ids=()))
    state.battle_round = 3
    before_payload = state.to_payload()

    with pytest.raises(
        GameLifecycleError,
        match="transport_cargo_states unarrived reserve route cargo drift",
    ):
        state._resolve_unarrived_reserve_destruction_boundary(  # pyright: ignore[reportPrivateUsage]
            end_of_battle=False
        )

    assert state.to_payload() == before_payload


def test_primary_historical_event_recorders_fail_closed_at_typed_boundaries(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
) -> None:
    state, _event_records, _decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    (departure,) = state.primary_battlefield_departure_states
    (destruction,) = state.primary_unit_destruction_states
    objective_state = state.primary_objective_turn_start_states[0]
    position_snapshot = next(
        snapshot
        for snapshot in state.primary_rules_unit_turn_start_snapshots
        if (
            snapshot.game_id,
            snapshot.active_player_id,
            snapshot.battle_round,
        )
        == (
            objective_state.game_id,
            objective_state.active_player_id,
            objective_state.battle_round,
        )
    )

    with pytest.raises(GameLifecycleError, match="requires EventLog"):
        record_primary_battlefield_departure_event(
            event_log=cast(EventLog, object()),
            departure=departure,
        )
    with pytest.raises(GameLifecycleError, match="requires typed departure evidence"):
        record_primary_battlefield_departure_event(
            event_log=EventLog(),
            departure=cast(PrimaryBattlefieldDepartureState, object()),
        )
    with pytest.raises(GameLifecycleError, match="requires typed objective evidence"):
        record_primary_turn_start_evidence_event(
            event_log=EventLog(),
            objective_state=cast(PrimaryObjectiveTurnStartState, object()),
            position_snapshot=position_snapshot,
        )
    with pytest.raises(GameLifecycleError, match="requires a typed position snapshot"):
        record_primary_turn_start_evidence_event(
            event_log=EventLog(),
            objective_state=objective_state,
            position_snapshot=cast(PrimaryRulesUnitTurnStartSnapshot, object()),
        )
    with pytest.raises(
        GameLifecycleError, match="objective and position evidence occurrence drift"
    ):
        record_primary_turn_start_evidence_event(
            event_log=EventLog(),
            objective_state=objective_state,
            position_snapshot=replace(
                position_snapshot,
                active_player_id="player-b"
                if position_snapshot.active_player_id == "player-a"
                else "player-a",
            ),
        )
    with pytest.raises(GameLifecycleError, match="requires typed destruction evidence"):
        record_primary_unit_destruction_event(
            event_log=EventLog(),
            destruction=cast(PrimaryUnitDestructionState, object()),
        )
    departure_event = record_primary_battlefield_departure_event(
        event_log=EventLog(),
        departure=departure,
    )
    destruction_event = record_primary_unit_destruction_event(
        event_log=EventLog(),
        destruction=destruction,
    )
    assert isinstance(departure_event.payload, dict)
    assert isinstance(destruction_event.payload, dict)
    assert departure_event.payload["primary_battlefield_departure_state"] == departure.to_payload()
    assert destruction_event.payload["primary_unit_destruction_state"] == destruction.to_payload()


def test_primary_reserve_entry_event_helpers_reject_evidence_drift() -> None:
    provider, reserve_state, departure, transition_batch = _typed_primary_reserve_entry_evidence()
    declared_state = ReserveState.declared_before_battle(
        player_id=reserve_state.player_id,
        unit_instance_id=reserve_state.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
    )

    with pytest.raises(GameLifecycleError, match="requires typed ReserveState"):
        reserve_entry_evidence_payload(cast(ReserveState, object()))
    with pytest.raises(GameLifecycleError, match="during-battle Strategic Reserves state"):
        reserve_entry_evidence_payload(declared_state)
    with pytest.raises(GameLifecycleError, match="typed INTO_RESERVES departure evidence"):
        record_primary_reserve_entry_mutation_event(
            event_log=EventLog(),
            departure=replace(departure, removal_kind=BattlefieldRemovalKind.DESTROYED),
            reserve_state=reserve_state,
            provider=provider,
            transition_batch=None,
        )
    with pytest.raises(GameLifecycleError, match="identity drifted from its departure"):
        record_primary_reserve_entry_mutation_event(
            event_log=EventLog(),
            departure=replace(departure, battle_round=departure.battle_round + 1),
            reserve_state=reserve_state,
            provider=provider,
            transition_batch=None,
        )
    with pytest.raises(GameLifecycleError, match="provider identity drift"):
        record_primary_reserve_entry_mutation_event(
            event_log=EventLog(),
            departure=departure,
            reserve_state=reserve_state,
            provider=replace(provider, source_rule_id="phase17n:other-reserve-rule"),
            transition_batch=None,
        )
    with pytest.raises(GameLifecycleError, match="cannot name an ability provider"):
        record_primary_reserve_entry_mutation_event(
            event_log=EventLog(),
            departure=departure,
            reserve_state=reserve_state,
            provider=provider,
            transition_batch=transition_batch,
        )
    with pytest.raises(GameLifecycleError, match="transition must be typed"):
        record_primary_reserve_entry_mutation_event(
            event_log=EventLog(),
            departure=departure,
            reserve_state=reserve_state,
            transition_batch=cast(BattlefieldTransitionBatch, object()),
        )
    with pytest.raises(GameLifecycleError, match="transition drifted from its departure"):
        record_primary_reserve_entry_mutation_event(
            event_log=EventLog(),
            departure=departure,
            reserve_state=reserve_state,
            transition_batch=BattlefieldTransitionBatch(),
        )

    provider_event = record_primary_reserve_entry_mutation_event(
        event_log=EventLog(),
        departure=departure,
        reserve_state=reserve_state,
        provider=provider,
        transition_batch=None,
    )
    transition_event = record_primary_reserve_entry_mutation_event(
        event_log=EventLog(),
        departure=departure,
        reserve_state=reserve_state,
        transition_batch=transition_batch,
    )
    assert isinstance(provider_event.payload, dict)
    assert isinstance(transition_event.payload, dict)
    assert provider_event.payload["provider"] == provider.to_payload()
    assert transition_event.payload["transition_batch"] == transition_batch.to_payload()


def test_primary_reserve_entry_terminal_bindings_fail_closed() -> None:
    provider, reserve_state, _departure, _transition_batch = _typed_primary_reserve_entry_evidence()
    expected_payload = primary_reserve_entry_source_terminal_bindings_payload(
        ((provider, reserve_state),)
    )

    with pytest.raises(GameLifecycleError, match="requires provider entries"):
        primary_reserve_entry_source_terminal_bindings_payload(())
    with pytest.raises(GameLifecycleError, match="requires provider entries"):
        primary_reserve_entry_source_terminal_bindings_payload(
            cast(tuple[tuple[PrimaryReserveEntryProvider, ReserveState], ...], [])
        )
    with pytest.raises(GameLifecycleError, match="entries must be typed"):
        primary_reserve_entry_source_terminal_bindings_payload(
            ((cast(PrimaryReserveEntryProvider, object()), reserve_state),)
        )
    with pytest.raises(GameLifecycleError, match="binding identity drift"):
        primary_reserve_entry_source_terminal_bindings_payload(
            ((replace(provider, player_id="player-b"), reserve_state),)
        )
    with pytest.raises(GameLifecycleError, match="occurrence is duplicated"):
        primary_reserve_entry_source_terminal_bindings_payload(
            ((provider, reserve_state), (provider, reserve_state))
        )

    with pytest.raises(GameLifecycleError, match="requires typed evidence"):
        record_primary_reserve_entry_provider_terminal_event(
            event_log=EventLog(),
            provider=cast(PrimaryReserveEntryProvider, object()),
            reserve_state=reserve_state,
            source_terminal_event=cast(EventRecord, object()),
        )
    wrong_type_log = EventLog()
    wrong_type_event = wrong_type_log.append("phase17n:wrong-terminal", expected_payload)
    with pytest.raises(GameLifecycleError, match="event type drift"):
        record_primary_reserve_entry_provider_terminal_event(
            event_log=wrong_type_log,
            provider=provider,
            reserve_state=reserve_state,
            source_terminal_event=wrong_type_event,
        )
    external_event = EventLog().append(provider.source_terminal_event_type, expected_payload)
    with pytest.raises(GameLifecycleError, match="is not in the event log"):
        record_primary_reserve_entry_provider_terminal_event(
            event_log=EventLog(),
            provider=provider,
            reserve_state=reserve_state,
            source_terminal_event=external_event,
        )
    non_object_log = EventLog()
    non_object_event = non_object_log.append(provider.source_terminal_event_type, [])
    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        record_primary_reserve_entry_provider_terminal_event(
            event_log=non_object_log,
            provider=provider,
            reserve_state=reserve_state,
            source_terminal_event=non_object_event,
        )
    missing_binding_log = EventLog()
    missing_binding_event = missing_binding_log.append(provider.source_terminal_event_type, {})
    with pytest.raises(GameLifecycleError, match="lacks its exact provider binding"):
        record_primary_reserve_entry_provider_terminal_event(
            event_log=missing_binding_log,
            provider=provider,
            reserve_state=reserve_state,
            source_terminal_event=missing_binding_event,
        )

    valid_log = EventLog()
    valid_terminal = valid_log.append(provider.source_terminal_event_type, expected_payload)
    resolved = record_primary_reserve_entry_provider_terminal_event(
        event_log=valid_log,
        provider=provider,
        reserve_state=reserve_state,
        source_terminal_event=valid_terminal,
    )
    assert isinstance(resolved.payload, dict)
    assert resolved.payload["source_terminal_event_id"] == valid_terminal.event_id


@pytest.mark.parametrize(
    ("prior_ids", "error_match"),
    [
        pytest.param([], "must be an identifier tuple", id="list"),
        pytest.param(("",), "must be an identifier tuple", id="blank"),
        pytest.param(("duplicate", "duplicate"), "must be unique", id="duplicate"),
    ],
)
def test_primary_historical_new_event_helpers_reject_prior_id_corruption(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    prior_ids: object,
    error_match: str,
) -> None:
    state, _event_records, _decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )

    with pytest.raises(GameLifecycleError, match=error_match):
        record_new_primary_battlefield_departure_events(
            state=state,
            event_log=EventLog(),
            departure_ids_before=cast(tuple[str, ...], prior_ids),
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("unpaired-count", "unpaired objective and position", id="unpaired-count"),
        pytest.param(
            "duplicate-snapshot", "duplicate position occurrences", id="duplicate-snapshot"
        ),
        pytest.param("mismatched-occurrence", "mismatched objective and position", id="mismatch"),
    ],
)
def test_primary_turn_start_new_event_helper_rejects_occurrence_corruption(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    state, _event_records, _decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    objective_state = state.primary_objective_turn_start_states[0]
    position_snapshot = next(
        snapshot
        for snapshot in state.primary_rules_unit_turn_start_snapshots
        if snapshot.active_player_id == objective_state.active_player_id
        and snapshot.battle_round == objective_state.battle_round
    )
    objective_ids_before: tuple[str, ...] = ()
    snapshot_ids_before: tuple[str, ...] = ()
    if corruption == "unpaired-count":
        snapshot_ids_before = tuple(
            snapshot.snapshot_id for snapshot in state.primary_rules_unit_turn_start_snapshots
        )
    elif corruption == "duplicate-snapshot":
        state.primary_objective_turn_start_states.append(
            replace(objective_state, state_id=f"{objective_state.state_id}:duplicate")
        )
        state.primary_rules_unit_turn_start_snapshots.append(
            replace(position_snapshot, snapshot_id=f"{position_snapshot.snapshot_id}:duplicate")
        )
    elif corruption == "mismatched-occurrence":
        state.primary_rules_unit_turn_start_snapshots = [
            replace(
                snapshot,
                battle_round=snapshot.battle_round + 1,
            )
            if snapshot.snapshot_id == position_snapshot.snapshot_id
            else snapshot
            for snapshot in state.primary_rules_unit_turn_start_snapshots
        ]
    else:
        raise AssertionError(f"unsupported turn-start corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        record_new_primary_turn_start_evidence_events(
            state=state,
            event_log=EventLog(),
            objective_state_ids_before=objective_ids_before,
            snapshot_ids_before=snapshot_ids_before,
        )


def test_primary_historical_integrity_rejects_untyped_or_duplicate_graph_records(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
) -> None:
    state, event_records, decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )

    with pytest.raises(GameLifecycleError, match="requires typed event records"):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=cast(tuple[EventRecord, ...], list(event_records)),
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )
    with pytest.raises(GameLifecycleError, match="requires typed event records"):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=(*event_records, cast(EventRecord, object())),
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )
    with pytest.raises(GameLifecycleError, match="requires typed decision records"):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=cast(tuple[DecisionRecord, ...], list(decision_records)),
            require_muster_event_provenance=True,
        )
    with pytest.raises(GameLifecycleError, match="requires typed decision records"):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=(*decision_records, cast(DecisionRecord, object())),
            require_muster_event_provenance=True,
        )
    with pytest.raises(GameLifecycleError, match="event IDs must be unique"):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=(*event_records, event_records[-1]),
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("duplicate-state", "evidence occurrence is duplicated", id="duplicate-state"),
        pytest.param("unpaired-state", "evidence occurrences are unpaired", id="unpaired-state"),
        pytest.param("malformed-event", "occurrence identity is malformed", id="malformed-event"),
        pytest.param(
            "missing-event", "requires one authoritative recorded event", id="missing-event"
        ),
        pytest.param(
            "duplicate-event", "requires exactly one recorded event", id="duplicate-event"
        ),
    ],
)
def test_primary_historical_integrity_rejects_turn_start_graph_corruption(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    state, event_records, decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    objective_state = state.primary_objective_turn_start_states[0]
    turn_start_event = next(
        event
        for event in event_records
        if event.event_type == "primary_turn_start_evidence_recorded"
        and isinstance(event.payload, dict)
        and event.payload.get("active_player_id") == objective_state.active_player_id
        and event.payload.get("battle_round") == objective_state.battle_round
    )
    if corruption == "duplicate-state":
        state.primary_objective_turn_start_states.append(
            replace(objective_state, state_id=f"{objective_state.state_id}:duplicate")
        )
    elif corruption == "unpaired-state":
        state.primary_rules_unit_turn_start_snapshots = [
            snapshot
            for snapshot in state.primary_rules_unit_turn_start_snapshots
            if not (
                snapshot.active_player_id == objective_state.active_player_id
                and snapshot.battle_round == objective_state.battle_round
            )
        ]
    elif corruption == "malformed-event":
        event_records = _replace_historical_event(
            event_records,
            original=turn_start_event,
            payload={**cast(dict[str, JsonValue], turn_start_event.payload), "game_id": None},
        )
    elif corruption == "missing-event":
        event_records = tuple(
            event for event in event_records if event.event_id != turn_start_event.event_id
        )
    elif corruption == "duplicate-event":
        event_records = (
            *event_records,
            replace(turn_start_event, event_id="phase17n-duplicate-turn-start-event"),
        )
    else:
        raise AssertionError(f"unsupported historical turn-start corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )


def test_primary_historical_integrity_rejects_missing_departure_record(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
) -> None:
    state, event_records, decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    event_records = tuple(
        event
        for event in event_records
        if event.event_type != "primary_battlefield_departure_recorded"
    )

    with pytest.raises(GameLifecycleError, match="departure requires one authoritative"):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("non-object-payload", "event payload must be an object", id="non-object"),
        pytest.param("unexpected-event", "requires one authoritative recorded event", id="extra"),
    ],
)
def test_primary_historical_integrity_rejects_unbacked_destruction_events(
    authentic_attached_unit_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    state, event_records, decision_records = _authentic_integrity_graph(
        authentic_attached_unit_lifecycle_payload
    )
    assert not state.primary_unit_destruction_states
    if corruption == "non-object-payload":
        payload: JsonValue = []
    elif corruption == "unexpected-event":
        payload = {
            "primary_unit_destruction_state": {"destruction_id": "phase17n-invented-destruction"}
        }
    else:
        raise AssertionError(f"unsupported destruction event corruption: {corruption}")
    event_records = (
        *event_records,
        EventRecord(
            event_id="phase17n-invented-destruction-event",
            event_type="primary_unit_destruction_recorded",
            payload=payload,
        ),
    )

    with pytest.raises(GameLifecycleError, match=error_match):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("game", "muster event game drift", id="game"),
        pytest.param("player", "muster event payload is malformed", id="player"),
        pytest.param("records", "muster event payload is malformed", id="records"),
        pytest.param("record", "muster event record is malformed", id="record"),
        pytest.param("attached-id", "lacks an attached-unit ID", id="attached-id"),
        pytest.param("duplicate", "duplicate army_mustered provenance", id="duplicate"),
        pytest.param("missing", "requires exact army_mustered provenance", id="missing"),
        pytest.param("owner", "muster owner drift", id="owner"),
        pytest.param("mapping", "muster mapping drift", id="mapping"),
    ],
)
def test_primary_historical_integrity_rejects_attached_muster_corruption(
    authentic_attached_unit_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    state, event_records, decision_records = _authentic_integrity_graph(
        authentic_attached_unit_lifecycle_payload
    )
    muster_event = next(
        event
        for event in event_records
        if event.event_type == "army_mustered"
        and isinstance(event.payload, dict)
        and bool(event.payload.get("starting_attached_unit_records"))
    )
    muster_payload = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(muster_event.payload, sort_keys=True)),
    )
    records = cast(list[JsonValue], muster_payload["starting_attached_unit_records"])
    record = cast(dict[str, JsonValue], records[0])
    if corruption == "game":
        muster_payload["game_id"] = "phase17n-other-game"
    elif corruption == "player":
        muster_payload["player_id"] = None
    elif corruption == "records":
        muster_payload["starting_attached_unit_records"] = {}
    elif corruption == "record":
        records[0] = "not-a-record"
    elif corruption == "attached-id":
        record["attached_unit_instance_id"] = None
    elif corruption == "duplicate":
        records.append(cast(JsonValue, json.loads(json.dumps(record, sort_keys=True))))
    elif corruption == "missing":
        records.clear()
    elif corruption == "owner":
        muster_payload["player_id"] = "player-b"
    elif corruption == "mapping":
        record["leader_unit_instance_ids"] = []
    else:
        raise AssertionError(f"unsupported attached muster corruption: {corruption}")
    event_records = _replace_historical_event(
        event_records,
        original=muster_event,
        payload=muster_payload,
    )

    with pytest.raises(GameLifecycleError, match=error_match):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("missing-event-id", "requires a model_destroyed event ID", id="event-id"),
        pytest.param("missing-source-witness", "lacks a source witness", id="source-missing"),
        pytest.param("source-witness-drift", "source witness drifted", id="source-drift"),
        pytest.param("missing-destroyed-witness", "lacks a destroyed witness", id="target-missing"),
        pytest.param(
            "destroyed-rules-unit",
            "destroyed witness rules-unit identity drift",
            id="target-unit",
        ),
        pytest.param(
            "destroyed-model", "destroyed witness model identity drift", id="target-model"
        ),
        pytest.param(
            "destroyed-objective",
            "destroyed witness objective identity drift",
            id="target-objective",
        ),
        pytest.param("tracking-source", "tracking source identity drift", id="source-id"),
    ],
)
def test_primary_historical_integrity_rejects_attributed_event_drift(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    state, event_records, decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    (destruction,) = state.primary_unit_destruction_states
    model_destroyed_event = next(
        event
        for event in event_records
        if event.event_id == destruction.source_model_destroyed_event_id
    )
    model_payload = cast(
        dict[str, JsonValue],
        json.loads(json.dumps(model_destroyed_event.payload, sort_keys=True)),
    )
    if corruption == "missing-event-id":
        object.__setattr__(destruction, "source_model_destroyed_event_id", None)
    elif corruption == "missing-source-witness":
        del model_payload["source_rules_unit_objective_proximity_witness"]
    elif corruption == "source-witness-drift":
        model_payload["source_rules_unit_objective_proximity_witness"] = None
    elif corruption == "missing-destroyed-witness":
        del model_payload["destroyed_rules_unit_objective_proximity_witness"]
    elif corruption in {"destroyed-rules-unit", "destroyed-model", "destroyed-objective"}:
        witness = cast(
            dict[str, JsonValue],
            model_payload["destroyed_rules_unit_objective_proximity_witness"],
        )
        if corruption == "destroyed-rules-unit":
            witness["rules_unit_instance_id"] = "army-beta:invented-rules-unit"
        else:
            model_id = cast(str, model_payload["model_instance_id"])
            mission_setup = cast(MissionSetup, state.mission_setup)
            witness["objective_marker_witnesses"] = [
                {
                    "objective_marker_id": (
                        "phase17n-invented-objective"
                        if corruption == "destroyed-objective"
                        else mission_setup.objective_markers[0].objective_marker_id
                    ),
                    "model_instance_ids": (
                        ["army-beta:invented-model"]
                        if corruption == "destroyed-model"
                        else [model_id]
                    ),
                }
            ]
    elif corruption == "tracking-source":
        state.primary_unit_destruction_states = [
            replace(destruction, source_id="phase17n:invented-tracking-source")
        ]
    else:
        raise AssertionError(f"unsupported attributed event corruption: {corruption}")
    if model_payload != model_destroyed_event.payload:
        event_records = _replace_historical_event(
            event_records,
            original=model_destroyed_event,
            payload=model_payload,
        )

    with pytest.raises(GameLifecycleError, match=error_match):
        validate_primary_historical_event_integrity(
            state=state,
            event_records=event_records,
            decision_records=decision_records,
            require_muster_event_provenance=True,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("missing-source", "lacks validated source provenance", id="source"),
        pytest.param("missing-occurrence", "occurrences drifted", id="occurrence"),
    ],
)
def test_primary_destruction_timeline_rejects_source_or_occurrence_drift(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_primary_destruction_lifecycle_payload)
    if corruption == "missing-source":
        departure_sources.pop(departures[0].departure_id)
    elif corruption == "missing-occurrence":
        destructions = ()
    else:
        raise AssertionError(f"unsupported timeline corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        destruction_timeline_integrity.validate_full_destruction_transition_timeline(
            state=state,
            destructions=destructions,
            departures=departures,
            departure_sources=departure_sources,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            identities_by_id=identities_by_id,
            decision_records=decision_records,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("non-object", "event payload must be an object", id="non-object"),
        pytest.param("missing-state", "recorded event state is malformed", id="state"),
        pytest.param("duplicate-id", "event identity is ambiguous", id="duplicate-id"),
    ],
)
def test_primary_destruction_timeline_rejects_recorded_event_corruption(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        _event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_primary_destruction_lifecycle_payload)
    recorded_event = next(
        event for event in event_records if event.event_type == "primary_unit_destruction_recorded"
    )
    if corruption == "non-object":
        event_records = _replace_historical_event(
            event_records,
            original=recorded_event,
            payload=[],
        )
    elif corruption == "missing-state":
        event_records = _replace_historical_event(
            event_records,
            original=recorded_event,
            payload={"primary_unit_destruction_state": None},
        )
    elif corruption == "duplicate-id":
        event_records = (
            *event_records,
            replace(
                recorded_event,
                event_id=f"event-{len(event_records) + 1:06d}",
            ),
        )
    else:
        raise AssertionError(f"unsupported recorded-event corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        destruction_timeline_integrity.validate_full_destruction_transition_timeline(
            state=state,
            destructions=destructions,
            departures=departures,
            departure_sources=departure_sources,
            event_records=event_records,
            event_index_by_id=_historical_event_index(event_records),
            identities_by_id=identities_by_id,
            decision_records=decision_records,
        )


def test_primary_reserve_deadline_timeline_requires_recorded_boundary_event(
    authentic_reserve_deadline_lifecycle_payload: GameLifecyclePayload,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        _event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_reserve_deadline_lifecycle_payload)
    event_records = _resequence_historical_events(
        tuple(
            event
            for event in event_records
            if event.event_type != "primary_unit_destruction_recorded"
        )
    )

    with pytest.raises(GameLifecycleError, match="lacks a recorded boundary event"):
        destruction_timeline_integrity.validate_full_destruction_transition_timeline(
            state=state,
            destructions=destructions,
            departures=departures,
            departure_sources=departure_sources,
            event_records=event_records,
            event_index_by_id=_historical_event_index(event_records),
            identities_by_id=identities_by_id,
            decision_records=decision_records,
        )


def test_primary_destruction_timeline_rejects_ambiguous_structured_order(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
) -> None:
    state, _event_records, _decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    model_id = state.army_definitions[0].units[0].own_models[0].model_instance_id
    transition_order = (3, 1)
    transition_rows: tuple[destruction_timeline_integrity._TransitionRow, ...] = (  # pyright: ignore[reportPrivateUsage]
        (
            transition_order,
            "phase17n:typed-timeline-transition",
            {
                "game_id": state.game_id,
                "model_instance_id": model_id,
                "target_unit_instance_id": state.army_definitions[0].units[0].unit_instance_id,
            },
            "phase17n:typed-timeline-completion",
        ),
    )

    with pytest.raises(GameLifecycleError, match="transition ordering is ambiguous"):
        destruction_timeline_integrity._completion_timeline_inputs(  # pyright: ignore[reportPrivateUsage]
            transition_rows=transition_rows,
            restorations=(
                (
                    transition_order,
                    "phase17n:typed-timeline-restoration",
                    (model_id,),
                ),
            ),
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("repeat-absent", "repeats an absent model", id="absent"),
        pytest.param("repeat-present", "repeats a present model", id="present"),
    ],
)
def test_primary_destruction_alive_model_replay_rejects_repeat_transition(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    state, _event_records, _decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    unit = state.army_definitions[0].units[0]
    model_id = unit.own_models[0].model_instance_id
    transition_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "model_instance_id": model_id,
        "target_unit_instance_id": unit.unit_instance_id,
    }
    transition_rows: tuple[destruction_timeline_integrity._TransitionRow, ...] = (  # pyright: ignore[reportPrivateUsage]
        ((1, 1), "phase17n:timeline-death-one", transition_payload, "phase17n:completion-one"),
        ((2, 1), "phase17n:timeline-death-two", transition_payload, "phase17n:completion-two"),
    )
    restorations: tuple[destruction_timeline_integrity._RestorationRow, ...] = ()  # pyright: ignore[reportPrivateUsage]
    if corruption == "repeat-present":
        transition_rows = ()
        restorations = (((1, 0), "phase17n:timeline-restoration", (model_id,)),)
    elif corruption != "repeat-absent":
        raise AssertionError(f"unsupported alive-model corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        destruction_timeline_integrity._alive_model_ids_before_order(  # pyright: ignore[reportPrivateUsage]
            starting_model_ids=unit.own_model_ids(),
            transition_rows=transition_rows,
            restorations=restorations,
            before_order=(3, 0),
        )


def test_primary_destruction_alive_model_replay_ignores_non_lineage_model(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
) -> None:
    state, _event_records, _decision_records = _authentic_integrity_graph(
        authentic_primary_destruction_lifecycle_payload
    )
    unit = state.army_definitions[0].units[0]
    transition_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "model_instance_id": "phase17n:non-lineage-model",
        "target_unit_instance_id": unit.unit_instance_id,
    }

    assert (
        destruction_timeline_integrity._alive_model_ids_before_order(  # pyright: ignore[reportPrivateUsage]
            starting_model_ids=unit.own_model_ids(),
            transition_rows=(
                (
                    (1, 1),
                    "phase17n:non-lineage-transition",
                    transition_payload,
                    "phase17n:non-lineage-completion",
                ),
            ),
            restorations=(),
            before_order=(2, 0),
        )
        == unit.own_model_ids()
    )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("source", "source drift", id="source"),
        pytest.param("route", "requires one destroyed ReserveState route", id="route"),
    ],
)
def test_primary_reserve_deadline_timeline_rejects_source_or_route_drift(
    authentic_reserve_deadline_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_reserve_deadline_lifecycle_payload)
    (destruction,) = destructions
    if corruption == "source":
        destructions = (replace(destruction, source_id="phase17n:reserve-source-drift"),)
    elif corruption == "route":
        (reserve_state,) = state.reserve_states
        state.reserve_states = [
            replace(
                reserve_state,
                destroyed_battle_round=cast(int, reserve_state.destroyed_battle_round) + 1,
            )
        ]
    else:
        raise AssertionError(f"unsupported reserve timeline corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        destruction_timeline_integrity.validate_full_destruction_transition_timeline(
            state=state,
            destructions=destructions,
            departures=departures,
            departure_sources=departure_sources,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            identities_by_id=identities_by_id,
            decision_records=decision_records,
        )


def test_primary_reserve_deadline_route_preserves_unknown_embarked_component(
    authentic_reserve_deadline_lifecycle_payload: GameLifecyclePayload,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_reserve_deadline_lifecycle_payload)
    (reserve_state,) = state.reserve_states
    state.reserve_states = [
        replace(
            reserve_state,
            embarked_unit_instance_ids=("phase17n:unknown-embarked-component",),
        )
    ]

    destruction_timeline_integrity.validate_full_destruction_transition_timeline(
        state=state,
        destructions=destructions,
        departures=departures,
        departure_sources=departure_sources,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
        identities_by_id=identities_by_id,
        decision_records=decision_records,
    )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("no-living-models", "has no living starting models", id="no-living"),
        pytest.param("model-lineage", "model lineage drift", id="lineage"),
    ],
)
def test_primary_reserve_deadline_transition_rows_reject_lineage_drift(
    authentic_reserve_deadline_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    (
        state,
        destructions,
        _departures,
        _departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        _decision_records,
    ) = _authentic_timeline_graph(authentic_reserve_deadline_lifecycle_payload)
    (destruction,) = destructions
    identity = identities_by_id[destruction.destroyed_unit_instance_id]
    prior_transition_rows: tuple[destruction_timeline_integrity._TransitionRow, ...] = ()  # pyright: ignore[reportPrivateUsage]
    if corruption == "no-living-models":
        prior_transition_rows = tuple(
            (
                (0, offset),
                f"phase17n:prior-reserve-transition:{model_id}",
                {
                    "game_id": state.game_id,
                    "model_instance_id": model_id,
                    "target_unit_instance_id": identity.rules_unit_instance_id,
                },
                f"phase17n:prior-reserve-completion:{model_id}",
            )
            for offset, model_id in enumerate(identity.starting_model_instance_ids, start=1)
        )
    elif corruption == "model-lineage":
        component_id = identity.component_unit_instance_ids[0]
        identities_by_id[identity.rules_unit_instance_id] = replace(
            identity,
            starting_model_instance_ids_by_component=(
                (component_id, ("phase17n:unknown-reserve-lineage-model",)),
            ),
        )
    else:
        raise AssertionError(f"unsupported reserve lineage corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=error_match):
        destruction_timeline_integrity._validated_reserve_deadline_transition_rows(  # pyright: ignore[reportPrivateUsage]
            state=state,
            destructions=destructions,
            identities_by_id=identities_by_id,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            prior_transition_rows=prior_transition_rows,
            restorations=(),
        )


@pytest.mark.parametrize(
    ("cause", "source_prefix"),
    [
        pytest.param(
            PrimaryUnattributedDestructionCause.DESPERATE_ESCAPE,
            "core-rules:desperate-escape:",
            id="desperate-escape",
        ),
        pytest.param(
            PrimaryUnattributedDestructionCause.EMERGENCY_DISEMBARK,
            "core-rules:emergency-disembark:",
            id="emergency-disembark",
        ),
        pytest.param(
            PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
            "",
            id="unit-coherency",
        ),
    ],
)
def test_primary_destruction_timeline_resolves_unattributed_completion_family(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    cause: PrimaryUnattributedDestructionCause,
    source_prefix: str,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_primary_destruction_lifecycle_payload)
    (destruction,) = destructions
    mutation_id = f"phase17n:{cause.value}:mutation"
    unattributed = _unattributed_timeline_destruction(
        destruction,
        cause=cause,
        mutation_id=mutation_id,
        source_id=f"{source_prefix}{mutation_id}:{destruction.destroyed_unit_instance_id}",
    )

    with pytest.raises(GameLifecycleError, match="occurrences drifted"):
        destruction_timeline_integrity.validate_full_destruction_transition_timeline(
            state=state,
            destructions=(unattributed,),
            departures=departures,
            departure_sources=departure_sources,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            identities_by_id=identities_by_id,
            decision_records=decision_records,
        )


@pytest.mark.parametrize(
    ("corruption", "error_match"),
    [
        pytest.param("attributed-event", "lacks a completion event ID", id="attributed"),
        pytest.param("unattributed-mutation", "lacks mutation provenance", id="unattributed"),
        pytest.param("unattributed-source", "source identity drift", id="source"),
    ],
)
def test_primary_destruction_completion_key_rejects_provenance_drift(
    authentic_primary_destruction_lifecycle_payload: GameLifecyclePayload,
    corruption: str,
    error_match: str,
) -> None:
    (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    ) = _authentic_timeline_graph(authentic_primary_destruction_lifecycle_payload)
    (destruction,) = destructions
    if corruption == "attributed-event":
        object.__setattr__(destruction, "source_model_destroyed_event_id", None)
        corrupted = destruction
    else:
        corrupted = _unattributed_timeline_destruction(
            destruction,
            cause=PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
            mutation_id="phase17n:completion-key-cleanup",
            source_id=(
                "phase17n:wrong-cleanup-source"
                if corruption == "unattributed-source"
                else (f"phase17n:completion-key-cleanup:{destruction.destroyed_unit_instance_id}")
            ),
        )
        if corruption == "unattributed-mutation":
            object.__setattr__(corrupted, "source_mutation_id", None)

    with pytest.raises(GameLifecycleError, match=error_match):
        destruction_timeline_integrity.validate_full_destruction_transition_timeline(
            state=state,
            destructions=(corrupted,),
            departures=departures,
            departure_sources=departure_sources,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            identities_by_id=identities_by_id,
            decision_records=decision_records,
        )


def test_purge_and_secure_real_attack_from_objective_scores_through_lifecycle() -> None:
    setup = _event_companion_purge_and_secure_mission_setup()
    config = _config_with_player_b_character(mission_setup=setup)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_state_from_config(
        config,
        turn_start_unit_positions=(("army-beta:character-unit-3", 43.0, 30.0),),
    )
    lifecycle.state = state
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=lifecycle.decision_controller.event_log,
        objective_state_ids_before=(),
        snapshot_ids_before=(),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attacker = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    defender = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    central_marker = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    _place_unit_near_point(
        state,
        unit_instance_id=attacker.unit_instance_id,
        x_inches=central_marker.x_inches,
        y_inches=central_marker.y_inches,
    )
    (defender_model,) = defender.own_models
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence_id = "phase17n-purge-and-secure-runtime-attack"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"

    remaining, _allocated_model_ids, attack_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    assert remaining is None
    assert attack_status is None
    destroyed_payload = cast(
        dict[str, JsonValue],
        next(
            event.payload
            for event in lifecycle.decision_controller.event_log.records
            if event.event_type == "model_destroyed"
        ),
    )
    source_witness = RulesUnitObjectiveProximityWitness.from_payload(
        destroyed_payload["source_rules_unit_objective_proximity_witness"]
    )
    assert source_witness.objective_marker_ids == (central_marker.objective_marker_id,)

    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
            BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT),
        }
    )
    flow.advance(state=state, decisions=lifecycle.decision_controller)
    (destruction,) = state.primary_unit_destruction_states
    assert destruction.source_rules_unit_objective_proximity_witness == source_witness
    assert destruction.started_turn_objective_marker_ids == ()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    flow.advance(state=state, decisions=lifecycle.decision_controller)

    (transaction,) = state.victory_point_ledger_for_player("player-a").transactions
    metadata = _transaction_metadata(transaction)
    assert transaction.amount == 3
    assert transaction.source_id == "primary-purge-and-secure"
    assert metadata["scoring_rule_id"] == ("purge-and-secure-destroyed-by-objective-unit-turn-end")
    assert metadata["primary_scoring_achieved_rule_ids"] == [
        "purge-and-secure-destroyed-by-objective-unit-turn-end"
    ]
    session = LocalGameSession(lifecycle=lifecycle)
    projected_ledgers = session.view(viewer_player_id="player-a")["public_victory_point_ledgers"]
    assert (
        next(
            cast(dict[str, JsonValue], ledger)["victory_points"]
            for ledger in projected_ledgers
            if cast(dict[str, JsonValue], ledger)["player_id"] == "player-a"
        )
        == 3
    )
    evidence_event_types = (
        "primary_battlefield_departure_recorded",
        "primary_turn_start_evidence_recorded",
        "primary_unit_destruction_recorded",
    )
    player_a_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    player_b_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    administrator_events = EventStreamCursor().events_since_for_context(
        lifecycle.decision_controller.event_log,
        viewer=AuthenticatedPrincipal(
            principal_id="phase17n-public-evidence-administrator",
            role=PrincipalRole.ADMINISTRATOR,
        ).bind_to_session(player_ids=("player-a", "player-b")),
    )

    def canonical_evidence_payloads(
        delta: dict[str, JsonValue],
    ) -> dict[str, tuple[str, ...]]:
        public_events = cast(list[JsonValue], delta["events"])
        return {
            event_type: tuple(
                json.dumps(
                    cast(dict[str, JsonValue], event)["payload"],
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                for event in public_events
                if cast(dict[str, JsonValue], event)["event_type"] == event_type
            )
            for event_type in evidence_event_types
        }

    player_a_evidence = canonical_evidence_payloads(cast(dict[str, JsonValue], player_a_events))
    player_b_evidence = canonical_evidence_payloads(cast(dict[str, JsonValue], player_b_events))
    administrator_evidence = canonical_evidence_payloads(
        cast(dict[str, JsonValue], administrator_events)
    )
    assert all(player_a_evidence[event_type] for event_type in evidence_event_types)
    assert player_a_evidence == player_b_evidence == administrator_evidence

    restored_lifecycle = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored_lifecycle.state is not None
    assert restored_lifecycle.state.to_payload() == state.to_payload()


def test_meatgrinder_captures_overwatch_destruction_before_return_on_death() -> None:
    config = replace(
        _config_with_player_b_character(mission_setup=_event_companion_meatgrinder_mission_setup()),
        game_id="phase11e-meatgrinder-overwatch-return-auth-0",
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_state_from_config(config, decisions=lifecycle.decision_controller)
    lifecycle.state = state
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    assert state.active_player_id == "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.battlefield_state is not None

    attacker = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    defender = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    original_placement = state.battlefield_state.unit_placement_by_id(defender.unit_instance_id)
    (defender_model,) = defender.own_models
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence_id = "phase17n-meatgrinder-overwatch-return-on-death"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    overwatch_pool = replace(
        _attack_pool_for_test(
            attacker=attacker,
            defender=defender,
            weapon_profile=weapon_profile,
            attacks=1,
        ),
        shooting_type=ShootingType.SNAP,
        targeting_rule_ids=(FIRE_OVERWATCH_RULE_ID,),
    )
    remaining, _allocated_model_ids, attack_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(overwatch_pool,),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                        reroll_forbidden_rule_ids=(SNAP_SHOOTING_RULE_ID,),
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    assert remaining is None
    assert attack_status is None
    (destroyed_event,) = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "model_destroyed"
    )
    destroyed_payload = cast(dict[str, JsonValue], destroyed_event.payload)
    assert destroyed_payload["phase"] == BattlePhase.SHOOTING.value
    assert state.current_battle_phase is BattlePhase.MOVEMENT

    pending = PendingReturnOnDeath(
        pending_id="phase17n-meatgrinder-overwatch-return-on-death:pending",
        source_rule_id="phase17n-meatgrinder-overwatch-return-on-death:rule",
        source_ability_id="phase17n-meatgrinder-overwatch-return-on-death:ability",
        source_clause_id="phase17n-meatgrinder-overwatch-return-on-death:clause",
        source_effect_index=0,
        owner_player_id="player-b",
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
        destroyed_unit_instance_id=defender.unit_instance_id,
        destroyed_model_instance_id=None,
        destroyed_position_payload=cast(
            JsonValue,
            {
                "source": "model_destroyed_event",
                "model_destroyed_event_id": destroyed_event.event_id,
                "model_destroyed_payload": destroyed_payload,
            },
        ),
        trigger_battle_round=state.battle_round,
        trigger_phase=BattlePhase.MOVEMENT.value,
        resolution_timing="phase_end",
        roll_expression="D6",
        roll_count=1,
        success_threshold=2,
        placement_anchor="destroyed_position",
        placement_preference="as_close_as_possible",
        engagement_range_restriction=True,
        restore_wounds_mode=ReturnRestoreWoundsMode.FULL_HEALTH,
        wounds_remaining=None,
        resolved=False,
    )
    state.record_pending_return_on_death(pending)
    lifecycle.decision_controller.event_log.append(
        RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "model_destroyed_event_id": destroyed_event.event_id,
            "pending": pending.to_payload(),
        },
    )
    flow = BattleRoundFlow(
        phase_handlers={
            BattlePhase.MOVEMENT: PlaceholderPhaseHandler(BattlePhase.MOVEMENT),
        }
    )
    waiting = flow.advance(state=state, decisions=lifecycle.decision_controller)

    assert waiting.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE
    (destruction,) = state.primary_unit_destruction_states
    assert destruction.destroyed_unit_instance_id == defender.unit_instance_id
    assert destruction.phase == BattlePhase.MOVEMENT.value
    capture_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "primary_unit_destruction_recorded"
    )
    assert len(capture_events) == 1

    result = DecisionResult(
        result_id="phase17n-meatgrinder-overwatch-return-on-death:placement-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=cast(
            JsonValue,
            {
                "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                "attempted_placement": original_placement.to_payload(),
            },
        ),
    )
    lifecycle.decision_controller.submit_result(result)
    apply_return_on_death_placement_decision(
        state=state,
        decisions=lifecycle.decision_controller,
        request=request,
        result=result,
        ruleset_descriptor=config.ruleset_descriptor,
    )
    assert all(model.is_alive for model in defender.own_models)
    assert state.battlefield_state.unit_placement_by_id(defender.unit_instance_id) == (
        original_placement
    )

    advanced = flow.advance(state=state, decisions=lifecycle.decision_controller)
    assert advanced.status_kind is LifecycleStatusKind.UNSUPPORTED
    assert state.battle_phase_index == state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    assert len(state.primary_unit_destruction_states) == 1
    assert (
        len(
            tuple(
                event
                for event in lifecycle.decision_controller.event_log.records
                if event.event_type == "primary_unit_destruction_recorded"
            )
        )
        == 1
    )
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()
    restored = GameLifecycle.from_payload(lifecycle.to_payload())
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()


def test_meatgrinder_round_five_objective_control_scores_only_at_turn_end() -> None:
    config = _config_with_player_b_character(
        mission_setup=_event_companion_meatgrinder_mission_setup()
    )
    state = _battle_state_from_config(config)
    state.battle_round = 5
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="central-north",
    )

    completed_phase = state.advance_to_next_battle_phase()

    assert completed_phase is BattlePhase.COMMAND
    assert state.victory_point_total("player-a") == 0

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()

    transactions = state.victory_point_ledger_for_player("player-a").transactions
    assert state.victory_point_total("player-a") == 4
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"] for transaction in transactions
    ] == ["meatgrinder-objective-control"]


def test_return_on_death_same_unit_id_records_a_second_destruction_occurrence() -> None:
    config = _config_with_player_b_character(
        mission_setup=_event_companion_meatgrinder_mission_setup()
    )
    state = _battle_state_from_config(config)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    assert state.battle_round == 2
    assert state.active_player_id == "player-a"
    assert state.battlefield_state is not None
    unit = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    original_placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    (original_model_placement,) = original_placement.model_placements

    _set_unit_wounds_remaining(
        state,
        unit_instance_id=unit.unit_instance_id,
        wounds_remaining=0,
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(unit.own_model_ids())
    )
    (first_destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=unit.own_model_ids(),
        destroying_player_id="player-a",
        source_id="phase17n:return-on-death:first-destruction",
    )
    current_phase = state.current_battle_phase
    assert current_phase is BattlePhase.COMMAND
    pending = PendingReturnOnDeath(
        pending_id="phase17n:return-on-death:pending",
        source_rule_id="phase17n:return-on-death:rule",
        source_ability_id="phase17n:return-on-death:ability",
        source_clause_id="phase17n:return-on-death:clause",
        source_effect_index=0,
        owner_player_id="player-b",
        target_scope=ReturnDestroyedTargetScope.DESTROYED_UNIT,
        destroyed_unit_instance_id=unit.unit_instance_id,
        destroyed_model_instance_id=None,
        destroyed_position_payload=cast(
            JsonValue,
            {
                "source": "model_destroyed_event",
                "model_destroyed_event_id": "phase17n:return-on-death:first-event",
                "model_destroyed_payload": {
                    "model_instance_id": original_model_placement.model_instance_id,
                    "destroyed_model_placement": original_model_placement.to_payload(),
                },
            },
        ),
        trigger_battle_round=state.battle_round,
        trigger_phase=current_phase.value,
        resolution_timing="phase_end",
        roll_expression="D6",
        roll_count=1,
        success_threshold=2,
        placement_anchor="destroyed_position",
        placement_preference="as_close_as_possible",
        engagement_range_restriction=True,
        restore_wounds_mode=ReturnRestoreWoundsMode.FULL_HEALTH,
        wounds_remaining=None,
        resolved=False,
    )
    state.record_pending_return_on_death(pending)
    request = build_return_on_death_placement_request(state=state, pending=pending)
    decisions = DecisionController()
    decisions.request_decision(request)
    result = DecisionResult(
        result_id="phase17n:return-on-death:placement-result",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=cast(
            JsonValue,
            {
                "submission_kind": SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
                "attempted_placement": original_placement.to_payload(),
            },
        ),
    )
    decisions.submit_result(result)
    apply_return_on_death_placement_decision(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
        ruleset_descriptor=config.ruleset_descriptor,
    )
    returned_unit = state.army_definitions[1].unit_by_id(unit.unit_instance_id)
    assert all(model.is_alive for model in returned_unit.own_models)
    assert state.battlefield_state.unit_placement_by_id(unit.unit_instance_id) == (
        original_placement
    )

    _set_unit_wounds_remaining(
        state,
        unit_instance_id=unit.unit_instance_id,
        wounds_remaining=0,
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(unit.own_model_ids())
    )
    (second_destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=unit.own_model_ids(),
        destroying_player_id="player-a",
        source_id="phase17n:return-on-death:second-destruction",
    )

    assert first_destruction.destroyed_unit_instance_id == (
        second_destruction.destroyed_unit_instance_id
    )
    assert first_destruction.destruction_id != second_destruction.destruction_id
    assert len(state.primary_unit_destruction_states) == 2
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()

    transactions = state.victory_point_ledger_for_player("player-a").transactions
    comparison_metadata = next(
        _transaction_metadata(transaction)
        for transaction in transactions
        if _transaction_metadata(transaction)["scoring_rule_id"]
        == "meatgrinder-more-destroyed-turn-end"
    )
    assert comparison_metadata["enemy_units_destroyed"] == 2
    assert comparison_metadata["enemy_destroyed_unit_instance_ids"] == [unit.unit_instance_id]
    assert comparison_metadata["enemy_destruction_ids"] == sorted(
        [first_destruction.destruction_id, second_destruction.destruction_id]
    )


def test_primary_destruction_capture_does_not_complete_attached_unit_for_bodyguard_only() -> None:
    config = _config_with_player_a_attached_unit(
        mission_setup=_event_companion_meatgrinder_mission_setup(),
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    state = _battle_state_from_config(config)
    lifecycle.state = state
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    assert state.active_player_id == "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attacker = state.army_definitions[1].unit_by_id("army-beta:intercessor-unit-3")
    source_objective_id = next(
        marker.objective_marker_id
        for marker in cast(MissionSetup, state.mission_setup).objective_markers
        if _objective_marker_matches_suffix(marker.objective_marker_id, "central-north")
    )
    _place_unit_near_objective(
        state,
        unit_instance_id=attacker.unit_instance_id,
        target_suffix="central-north",
    )
    bodyguard = state.army_definitions[0].unit_by_id("army-alpha:bodyguard-unit")
    surviving_model_id = bodyguard.own_models[-1].model_instance_id
    pre_destroyed_model_ids = tuple(
        model.model_instance_id
        for model in bodyguard.own_models
        if model.model_instance_id != surviving_model_id
    )
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(
                        unit,
                        own_models=tuple(
                            replace(model, wounds_remaining=0)
                            if model.model_instance_id in pre_destroyed_model_ids
                            else model
                            for model in unit.own_models
                        ),
                    )
                    if unit.unit_instance_id == bodyguard.unit_instance_id
                    else unit
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ]
    )
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(pre_destroyed_model_ids)
    )
    bodyguard = state.army_definitions[0].unit_by_id("army-alpha:bodyguard-unit")
    surviving_model = next(
        model for model in bodyguard.own_models if model.model_instance_id == surviving_model_id
    )
    attack_target = replace(bodyguard, own_models=(surviving_model,))
    attached_unit_id = "attached-unit:army-alpha:bodyguard-unit"
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(surviving_model.wounds_remaining),
    )
    sequence_id = "phase17n-attached-component-runtime-attack"
    attack_models = ((1, surviving_model),)
    injected_results = (
        *(
            result
            for attack_index, _model in attack_models
            for result in (
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit:{attack_index}",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=f"{sequence_id}:pool-001:attack-{attack_index:03d}",
                        attacker_player_id="player-b",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound:{attack_index}",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=f"{sequence_id}:pool-001:attack-{attack_index:03d}",
                        attacker_player_id="player-b",
                    ),
                    value=6,
                ),
            )
        ),
        *(
            _fixed_roll_result(
                roll_id=f"{sequence_id}:save:{attack_index}",
                spec=saving_throw_roll_spec(
                    save_kind=SaveKind.ARMOUR,
                    player_id="player-a",
                    allocated_model_id=surviving_model.model_instance_id,
                    attack_context_id=f"{sequence_id}:pool-001:attack-{attack_index:03d}",
                ),
                value=1,
            )
            for attack_index, _model in attack_models
        ),
    )

    remaining, _allocated_model_ids, attack_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-b",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=attack_target,
                    weapon_profile=weapon_profile,
                    attacks=1,
                    target_unit_instance_id=attached_unit_id,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=injected_results,
        ),
    )
    assert remaining is None, attack_status
    assert attack_status is None
    (destroyed_event,) = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "model_destroyed"
    )
    destroyed_payload = cast(dict[str, JsonValue], destroyed_event.payload)
    source_witness = RulesUnitObjectiveProximityWitness.from_payload(
        destroyed_payload["source_rules_unit_objective_proximity_witness"]
    )
    destroyed_witness = RulesUnitObjectiveProximityWitness.from_payload(
        destroyed_payload["destroyed_rules_unit_objective_proximity_witness"]
    )
    assert source_witness.rules_unit_instance_id == attacker.unit_instance_id
    assert source_witness.objective_marker_ids == (source_objective_id,)
    assert destroyed_witness.rules_unit_instance_id == attached_unit_id
    source_owner_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    destroyed_owner_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    source_owner_payload = cast(
        dict[str, JsonValue],
        next(
            event["payload"]
            for event in source_owner_events["events"]
            if event["event_type"] == "model_destroyed"
        ),
    )
    destroyed_owner_payload = cast(
        dict[str, JsonValue],
        next(
            event["payload"]
            for event in destroyed_owner_events["events"]
            if event["event_type"] == "model_destroyed"
        ),
    )
    assert source_owner_payload["source_rules_unit_objective_proximity_witness"] == (
        source_witness.to_payload()
    )
    assert destroyed_owner_payload["source_rules_unit_objective_proximity_witness"] == (
        source_witness.to_payload()
    )
    assert (
        source_owner_payload["destroyed_rules_unit_objective_proximity_witness"]
        == (destroyed_owner_payload["destroyed_rules_unit_objective_proximity_witness"])
    )

    _place_unit_near_point(
        state,
        unit_instance_id=attacker.unit_instance_id,
        x_inches=5.0,
        y_inches=5.0,
    )

    BattleRoundFlow(
        phase_handlers={BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING)}
    ).advance(state=state, decisions=lifecycle.decision_controller)

    source_owner_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    destroyed_owner_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    administrator_events = EventStreamCursor().events_since_for_context(
        lifecycle.decision_controller.event_log,
        viewer=AuthenticatedPrincipal(
            principal_id="phase17n-test-administrator",
            role=PrincipalRole.ADMINISTRATOR,
        ).bind_to_session(player_ids=("player-a", "player-b")),
    )
    administrator_destroyed_payload = cast(
        dict[str, JsonValue],
        next(
            event["payload"]
            for event in administrator_events["events"]
            if event["event_type"] == "model_destroyed"
        ),
    )
    assert source_owner_payload == destroyed_owner_payload
    assert source_owner_payload == administrator_destroyed_payload
    assert not any(
        event["event_type"] == "primary_unit_destruction_recorded"
        for stream in (source_owner_events, destroyed_owner_events, administrator_events)
        for event in stream["events"]
    )
    assert not state.primary_unit_destruction_states
    assert all(
        not model.is_alive
        for model in state.army_definitions[0].unit_by_id(bodyguard.unit_instance_id).own_models
    )
    assert all(
        model.is_alive
        for model in state.army_definitions[0].unit_by_id("army-alpha:leader-unit").own_models
    )
    (departure,) = state.primary_battlefield_departure_states
    attached_record = next(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == attached_unit_id
    )
    assert departure.rules_unit_instance_id == attached_unit_id
    assert departure.component_unit_instance_ids == tuple(
        sorted(attached_record.component_unit_instance_ids)
    )
    assert departure.affected_component_unit_instance_ids == (bodyguard.unit_instance_id,)
    assert departure.departed_component_unit_instance_ids == (bodyguard.unit_instance_id,)
    assert departure.removed_model_instance_ids == (surviving_model_id,)
    assert departure.removal_kind is BattlefieldRemovalKind.DESTROYED
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()

    departure_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    leader = state.army_definitions[0].unit_by_id("army-alpha:leader-unit")
    departure_drift_payload["primary_battlefield_departure_states"][0][
        "removed_model_instance_ids"
    ] = [leader.own_models[0].model_instance_id]
    with pytest.raises(GameLifecycleError, match="outside its affected components"):
        GameState.from_payload(departure_drift_payload)


def test_public_model_destroyed_event_evidence_is_validated_for_every_viewer() -> None:
    malformed = EventLog()
    malformed.append(
        "model_destroyed",
        {
            "destroying_player_id": "player-a",
        },
    )

    for viewer_player_id in ("player-a", "player-b"):
        with pytest.raises(
            GameLifecycleError,
            match="missing source_rules_unit_objective_proximity_witness",
        ):
            EventStreamCursor().events_since(
                malformed,
                viewer_player_id=viewer_player_id,
            )


def test_primary_battlefield_departure_rejects_models_still_on_battlefield() -> None:
    state = _battle_state_for_primary("primary-unstoppable-force")
    unit = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")

    with pytest.raises(GameLifecycleError, match="must have left the battlefield"):
        record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=unit.unit_instance_id,
            affected_component_unit_instance_ids=(unit.unit_instance_id,),
            departed_component_unit_instance_ids=(unit.unit_instance_id,),
            removed_model_instance_ids=unit.own_model_ids(),
            removal_kind=BattlefieldRemovalKind.DESTROYED,
            occurrence_id="phase17n:test:still-placed-departure:occurrence",
            source_id="phase17n:test:still-placed-departure",
        )


def test_primary_departure_leave_return_leave_uses_fresh_occurrence_identity() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_character(mission_setup=_event_companion_meatgrinder_mission_setup())
    )
    unit = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    (model_id,) = unit.own_model_ids()
    assert state.battlefield_state is not None
    original_placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.replace_battlefield_state(state.battlefield_state.with_removed_models((model_id,)))
    (first,) = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=(model_id,),
        source_id="phase17n:test:repeat-departure",
        occurrence_id="phase17n:test:repeat-departure:first",
    )

    returned = state.battlefield_state.with_returned_unplaced_model(model_id)
    state.replace_battlefield_state(returned.with_added_unit_placement(original_placement))
    state.replace_battlefield_state(state.battlefield_state.with_removed_models((model_id,)))
    (second,) = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=(model_id,),
        source_id="phase17n:test:repeat-departure",
        occurrence_id="phase17n:test:repeat-departure:second",
    )

    assert first.departure_id != second.departure_id
    assert first.source_id == second.source_id
    assert first.removed_model_instance_ids == second.removed_model_instance_ids == (model_id,)
    assert first.departed_component_unit_instance_ids == (unit.unit_instance_id,)
    assert second.departed_component_unit_instance_ids == (unit.unit_instance_id,)


def test_unit_completion_rejects_duplicate_destruction_without_restoration() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_character(mission_setup=_event_companion_meatgrinder_mission_setup())
    )
    unit = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    (model_id,) = unit.own_model_ids()
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.with_removed_models((model_id,)))
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "target_unit_instance_id": unit.unit_instance_id,
        "model_instance_id": model_id,
    }

    with pytest.raises(GameLifecycleError, match="requires a living model transition"):
        unit_destruction_completion_events_for_interval(
            state=state,
            model_destroyed_events=(
                (0, "event:model-destroyed:first", payload),
                (1, "event:model-destroyed:forged-duplicate", payload),
            ),
        )


def test_attached_frozen_completion_does_not_claim_materialized_survivor_departed() -> None:
    state = _battle_state_from_config(
        _config_with_player_a_attached_unit(
            mission_setup=_event_companion_meatgrinder_mission_setup()
        )
    )
    (starting_record,) = state.starting_attached_unit_records
    bodyguard = state.army_definitions[0].unit_by_id(starting_record.bodyguard_unit_instance_id)
    survivor_model_id = bodyguard.own_model_ids()[-1]
    frozen_mapping = tuple(
        (
            component_id,
            tuple(model_id for model_id in model_ids if model_id != survivor_model_id),
        )
        for component_id, model_ids in starting_record.starting_model_instance_ids_by_component
    )
    materialized_shape_record = replace(
        starting_record,
        starting_model_instance_ids_by_component=frozen_mapping,
        starting_model_count=starting_record.starting_model_count - 1,
    )
    state.starting_attached_unit_records = [materialized_shape_record]
    frozen_model_ids = materialized_shape_record.starting_model_instance_ids()
    assert state.battlefield_state is not None
    state.replace_battlefield_state(state.battlefield_state.with_removed_models(frozen_model_ids))

    (destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=frozen_model_ids,
        destroying_player_id="player-b",
        source_id="phase17n:test:materialized-survivor:frozen-completion",
    )

    bodyguard_departure = next(
        departure
        for departure in state.primary_battlefield_departure_states
        if departure.affected_component_unit_instance_ids == (bodyguard.unit_instance_id,)
    )
    assert bodyguard_departure.departed_component_unit_instance_ids == ()
    assert bodyguard_departure.removed_model_instance_ids == (
        materialized_shape_record.starting_model_instance_ids_for_component(
            bodyguard.unit_instance_id
        )
    )
    assert destruction.destroyed_unit_instance_id == (
        materialized_shape_record.attached_unit_instance_id
    )

    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models((survivor_model_id,))
    )
    assert not _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=(survivor_model_id,),
        destroying_player_id="player-b",
        source_id="phase17n:test:materialized-survivor:later-added-model",
    )
    assert len(state.primary_unit_destruction_states) == 1


def test_hazardous_source_witness_keeps_destroyed_model_pre_removal_position() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_character(mission_setup=_event_companion_meatgrinder_mission_setup())
    )
    source_unit = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    (source_model,) = source_unit.own_models
    _place_unit_near_objective(
        state,
        unit_instance_id=source_unit.unit_instance_id,
        target_suffix="central-north",
    )
    assert state.battlefield_state is not None
    source_placement = state.battlefield_state.model_placement_by_id(source_model.model_instance_id)
    source_objective_id = next(
        marker.objective_marker_id
        for marker in cast(MissionSetup, state.mission_setup).objective_markers
        if _objective_marker_matches_suffix(marker.objective_marker_id, "central-north")
    )
    _set_unit_wounds_remaining(
        state,
        unit_instance_id=source_unit.unit_instance_id,
        wounds_remaining=0,
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models((source_model.model_instance_id,))
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-b",
        source_kind=DestructionSourceKind.HAZARDOUS,
        source_rules_unit_instance_id=source_unit.unit_instance_id,
        source_model_instance_id=source_model.model_instance_id,
    )

    witness = destruction_source_objective_proximity_witness(
        state=state,
        event_log=EventLog(),
        attribution=attribution,
        destroyed_model_placement=source_placement,
    )

    assert witness is not None
    assert witness.rules_unit_instance_id == source_unit.unit_instance_id
    assert witness.objective_marker_ids == (source_objective_id,)
    assert witness.objective_marker_witnesses[0].model_instance_ids == (
        source_model.model_instance_id,
    )


def test_meatgrinder_current_turn_enemy_destruction_changes_comparison_result() -> None:
    evidence = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=2,
        active_player_id="player-a",
        scoring_player_id="player-a",
        destruction_evidence=(
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:current-turn-loss",
                battle_round=2,
                active_player_id="player-a",
                destroying_player_id=None,
                destroyed_player_id="player-b",
                destroyed_unit_instance_id="army-beta:current-turn-loss",
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
        ),
    )

    assert evidence["score_count"] == 1
    assert evidence["enemy_units_destroyed"] == 1
    assert evidence["enemy_destroyed_unit_instance_ids"] == ["army-beta:current-turn-loss"]


def test_meatgrinder_counts_repeated_destruction_occurrences_for_the_same_unit() -> None:
    repeated_unit_id = "army-beta:returning-unit"
    evidence = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=2,
        active_player_id="player-a",
        scoring_player_id="player-a",
        destruction_evidence=(
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:returning-unit:first",
                battle_round=2,
                active_player_id="player-a",
                destroying_player_id=None,
                destroyed_player_id="player-b",
                destroyed_unit_instance_id=repeated_unit_id,
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:returning-unit:second",
                battle_round=2,
                active_player_id="player-a",
                destroying_player_id=None,
                destroyed_player_id="player-b",
                destroyed_unit_instance_id=repeated_unit_id,
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
        ),
    )

    assert evidence["score_count"] == 1
    assert evidence["enemy_units_destroyed"] == 2
    assert evidence["enemy_destroyed_unit_instance_ids"] == [repeated_unit_id]
    assert evidence["enemy_destruction_ids"] == [
        "destruction:returning-unit:first",
        "destruction:returning-unit:second",
    ]


def test_meatgrinder_enemy_self_loss_in_previous_turn_is_not_current_enemy_loss() -> None:
    evidence = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=2,
        active_player_id="player-a",
        scoring_player_id="player-a",
        destruction_evidence=(
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:previous-turn-self-loss",
                battle_round=1,
                active_player_id="player-b",
                destroying_player_id=None,
                destroyed_player_id="player-b",
                destroyed_unit_instance_id="army-beta:previous-turn-self-loss",
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
        ),
    )

    assert evidence["score_count"] == 0
    assert evidence["enemy_units_destroyed"] == 0
    assert evidence["friendly_units_destroyed"] == 0
    assert evidence["enemy_destroyed_unit_instance_ids"] == []


def test_meatgrinder_previous_opponent_turn_friendly_loss_prevents_tie_score() -> None:
    evidence = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=2,
        active_player_id="player-a",
        scoring_player_id="player-a",
        destruction_evidence=(
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:previous-turn-friendly-loss",
                battle_round=1,
                active_player_id="player-b",
                destroying_player_id=None,
                destroyed_player_id="player-a",
                destroyed_unit_instance_id="army-alpha:previous-turn-loss",
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:current-turn-enemy-loss",
                battle_round=2,
                active_player_id="player-a",
                destroying_player_id=None,
                destroyed_player_id="player-b",
                destroyed_unit_instance_id="army-beta:current-turn-loss",
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
        ),
    )

    assert evidence["score_count"] == 0
    assert evidence["enemy_units_destroyed"] == 1
    assert evidence["friendly_units_destroyed"] == 1
    assert evidence["friendly_destroyed_unit_instance_ids"] == ["army-alpha:previous-turn-loss"]


def test_meatgrinder_round_boundary_uses_prior_round_player_b_turn_for_player_a() -> None:
    evidence = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=3,
        active_player_id="player-a",
        scoring_player_id="player-a",
        destruction_evidence=(
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:round-two-player-b-loss",
                battle_round=2,
                active_player_id="player-b",
                destroying_player_id=None,
                destroyed_player_id="player-a",
                destroyed_unit_instance_id="army-alpha:round-two-player-b-loss",
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
            PrimaryUnitDestructionEvidence(
                destruction_id="destruction:round-three-player-a-loss",
                battle_round=3,
                active_player_id="player-a",
                destroying_player_id=None,
                destroyed_player_id="player-b",
                destroyed_unit_instance_id="army-beta:round-three-player-a-loss",
                destruction_attribution=None,
                source_rules_unit_objective_proximity_witness=None,
                started_turn_terrain_feature_ids=(),
                started_turn_objective_marker_ids=(),
            ),
        ),
    )

    assert evidence["current_turn_battle_round"] == 3
    assert evidence["current_turn_active_player_id"] == "player-a"
    assert evidence["previous_turn_battle_round"] == 2
    assert evidence["previous_turn_active_player_id"] == "player-b"


def test_meatgrinder_opponent_home_uses_typed_role_not_deployment_zone_geometry() -> None:
    setup = _event_companion_meatgrinder_mission_setup()
    defender_home = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.DEFENDER_HOME
    )
    non_home_inside_defender_zone = replace(
        defender_home,
        objective_marker_id="expansion-inside-defender-deployment-zone",
        name="Expansion Inside Defender Deployment Zone",
        objective_role=ObjectiveMarkerRole.EXPANSION,
        source_id="phase17n:test:typed-home-objective-role",
    )
    setup_with_non_home_marker = replace(
        setup,
        objective_markers=(*setup.objective_markers, non_home_inside_defender_zone),
    )

    non_home_only = opponent_home_control_evidence(
        mission_setup=setup_with_non_home_marker,
        player_id="player-a",
        controlled_objective_ids=(non_home_inside_defender_zone.objective_marker_id,),
    )
    typed_home = opponent_home_control_evidence(
        mission_setup=setup_with_non_home_marker,
        player_id="player-a",
        controlled_objective_ids=(
            non_home_inside_defender_zone.objective_marker_id,
            defender_home.objective_marker_id,
        ),
    )

    assert non_home_only["score_count"] == 0
    assert non_home_only["controlled_objective_ids"] == []
    assert non_home_only["opponent_home_objective_ids"] == [defender_home.objective_marker_id]
    assert typed_home["score_count"] == 1
    assert typed_home["controlled_objective_ids"] == [defender_home.objective_marker_id]


def test_primary_destruction_tracking_counts_transition_only_enemy_loss() -> None:
    state = _battle_state_for_primary("primary-unstoppable-force")
    unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-beta:intercessor-unit-3"
    )
    destroyed_model_ids = tuple(model.model_instance_id for model in unit.own_models)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(destroyed_model_ids)
    )

    (destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=destroyed_model_ids,
        destroying_player_id=None,
        source_id="core-rules:test-transition-only-destruction",
    )

    assert destruction.destroying_player_id is None
    assert destruction.destroyed_player_id == "player-b"
    assert destruction.destroyed_unit_instance_id == unit.unit_instance_id
    assert destruction.started_turn_terrain_feature_ids == ()
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()

    transactions = state.victory_point_ledger_for_player("player-a").transactions
    assert [
        _transaction_metadata(transaction)["scoring_rule_id"] for transaction in transactions
    ] == ["unstoppable-force-enemy-destroyed-turn-end"]


def test_runtime_added_unit_backfills_turn_start_evidence_and_can_be_destroyed_same_turn() -> None:
    config = _config_with_player_b_character(
        mission_setup=_event_companion_meatgrinder_mission_setup()
    )
    state = _battle_state_from_config(config)
    template = state.army_definitions[1].unit_by_id("army-beta:character-unit-3")
    added_unit_id = "army-beta:created-unit-4"
    added_unit = replace(
        template,
        unit_instance_id=added_unit_id,
        own_models=tuple(
            replace(
                model,
                model_instance_id=f"{added_unit_id}:model-{index:03d}",
            )
            for index, model in enumerate(template.own_models, start=1)
        ),
    )

    state.add_unit_to_army(
        player_id="player-b",
        unit=added_unit,
        source_id="phase17n:test:created-unit",
    )

    assert state.primary_rules_unit_turn_start_snapshots
    assert all(
        snapshot.membership_for_rules_unit(added_unit_id).evaluated_model_instance_ids == ()
        for snapshot in state.primary_rules_unit_turn_start_snapshots
    )
    assert state.battlefield_state is not None
    added_placement = UnitPlacement(
        army_id="army-beta",
        player_id="player-b",
        unit_instance_id=added_unit_id,
        model_placements=tuple(
            ModelPlacement(
                army_id="army-beta",
                player_id="player-b",
                unit_instance_id=added_unit_id,
                model_instance_id=model.model_instance_id,
                pose=Pose.at(40.0 + index, 30.0),
            )
            for index, model in enumerate(added_unit.own_models)
        ),
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_added_unit_placement(added_placement)
    )
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()

    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(added_unit.own_model_ids())
    )
    (destruction,) = _record_test_completed_primary_unit_destruction(
        state,
        destroyed_model_instance_ids=added_unit.own_model_ids(),
        destroying_player_id="player-a",
        source_id="phase17n:test:created-unit-destruction",
    )

    assert destruction.destroyed_unit_instance_id == added_unit_id
    assert destruction.started_turn_terrain_feature_ids == ()
    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_phase16_primary_scoring_states_round_trip_and_fail_fast() -> None:
    config = _config_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    area = _objective_logical_terrain_area(
        cast(MissionSetup, config.mission_setup),
        objective_role=ObjectiveMarkerRole.CENTRAL,
    )
    area_id = area.logical_terrain_area_id
    state = _battle_state_from_config(
        config,
        turn_start_unit_positions=(
            (
                "army-beta:intercessor-unit-3",
                *_logical_terrain_area_test_point(area),
            ),
        ),
    )
    first_turn_start = state.primary_objective_turn_start_states[0]
    first_position_snapshot = state.primary_rules_unit_turn_start_snapshots[0]
    trap_action_id = "mission-action:phase16-booby-trap-round-trip"
    trap_source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="booby-trap-terrain",
        action_id=trap_action_id,
        target_id=area_id,
    )

    attribution, source_witness = _test_primary_destruction_attribution(
        state,
        destroying_player_id="player-a",
    )
    with pytest.raises(GameLifecycleError, match="destroyed rules unit"):
        state.record_primary_unit_destruction(
            destruction_attribution=attribution,
            source_model_destroyed_event_id=(
                "phase16:death-trap:alive-unit-rejected:model-destroyed-event"
            ),
            source_rules_unit_objective_proximity_witness=source_witness,
            source_battlefield_departure_ids=(),
            unattributed_cause=None,
            source_mutation_id=None,
            destroyed_unit_instance_id="army-alpha:intercessor-unit-1",
            source_id="phase16:death-trap:alive-unit-rejected",
        )
    _remove_unit_for_primary_destruction(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    friendly_destruction = _record_test_primary_unit_destruction(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id="army-alpha:intercessor-unit-1",
        source_id="phase16:death-trap:friendly-unit",
    )
    assert friendly_destruction.destroying_player_id == friendly_destruction.destroyed_player_id

    trap = state.record_primary_terrain_trap(
        player_id="player-a",
        terrain_feature_id=area_id,
        action_id=trap_action_id,
        phase=BattlePhase.SHOOTING,
        source_id=trap_source_id,
    )
    _remove_unit_for_primary_destruction(
        state,
        unit_instance_id="army-beta:intercessor-unit-3",
    )
    attribution, source_witness = _test_primary_destruction_attribution(
        state,
        destroying_player_id="player-a",
    )
    with pytest.raises(
        GameLifecycleError,
        match="source witness component identity drift",
    ):
        state.record_primary_unit_destruction(
            destruction_attribution=attribution,
            source_model_destroyed_event_id="event:model-destroyed:forged-witness",
            source_rules_unit_objective_proximity_witness=replace(
                source_witness,
                component_unit_instance_ids=("army-beta:intercessor-unit-3",),
            ),
            source_battlefield_departure_ids=("departure:forged-witness",),
            unattributed_cause=None,
            source_mutation_id=None,
            destroyed_unit_instance_id="army-beta:intercessor-unit-3",
            source_id="phase17n:death-trap:forged-witness",
        )
    destruction = _record_test_primary_unit_destruction(
        state,
        destroying_player_id="player-a",
        destroyed_unit_instance_id="army-beta:intercessor-unit-3",
        source_id="phase16:death-trap:enemy-destroyed",
    )
    payload = cast(GameStatePayload, json.loads(json.dumps(state.to_payload(), sort_keys=True)))

    assert PrimaryObjectiveTurnStartState.from_payload(first_turn_start.to_payload()) == (
        first_turn_start
    )
    assert (
        PrimaryRulesUnitTurnStartSnapshot.from_payload(first_position_snapshot.to_payload())
        == first_position_snapshot
    )
    assert PrimaryTerrainTrapState.from_payload(trap.to_payload()) == trap
    assert PrimaryUnitDestructionState.from_payload(destruction.to_payload()) == destruction
    assert (
        PrimaryUnitDestructionState.from_payload(friendly_destruction.to_payload())
        == friendly_destruction
    )
    assert GameState.from_payload(payload).to_payload() == state.to_payload()

    missing_objective_history_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    missing_objective_history_payload["primary_objective_turn_start_states"].pop()
    with pytest.raises(GameLifecycleError, match="turn keys must match exactly"):
        GameState.from_payload(missing_objective_history_payload)

    missing_position_history_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    missing_position_history_payload["primary_rules_unit_turn_start_snapshots"].pop()
    with pytest.raises(GameLifecycleError, match="turn keys must match exactly"):
        GameState.from_payload(missing_position_history_payload)

    unknown_controlled_objective_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    unknown_controlled_objective_payload["primary_objective_turn_start_states"][0][
        "controlled_objective_ids"
    ] = ["objective:unknown"]
    controlled_objective_source = unknown_controlled_objective_payload[
        "primary_objective_turn_start_states"
    ][0]["source_objective_control_record"]
    controlled_objective_result = next(
        result
        for result in controlled_objective_source["results"]
        if result["controlled_by_player_id"] == "player-a"
    )
    controlled_objective_result["objective_id"] = "objective:unknown"
    with pytest.raises(GameLifecycleError, match="unknown objective marker"):
        GameState.from_payload(unknown_controlled_objective_payload)

    objective_identity_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    objective_identity_drift_payload["primary_objective_turn_start_states"][0]["state_id"] = (
        "primary-turn-start:tampered"
    )
    with pytest.raises(GameLifecycleError, match="state_id drift"):
        GameState.from_payload(objective_identity_drift_payload)

    objective_source_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    objective_source_drift_payload["primary_objective_turn_start_states"][0]["source_id"] = (
        "primary-turn-start-source:tampered"
    )
    with pytest.raises(GameLifecycleError, match="source_id drift"):
        GameState.from_payload(objective_source_drift_payload)

    position_identity_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    position_identity_drift_payload["primary_rules_unit_turn_start_snapshots"][0]["snapshot_id"] = (
        "primary-rules-unit-turn-start:tampered"
    )
    with pytest.raises(GameLifecycleError, match="snapshot_id drift"):
        GameState.from_payload(position_identity_drift_payload)

    unexpected_objective_history_payload = cast(
        dict[str, object],
        json.loads(json.dumps(first_turn_start.to_payload(), sort_keys=True)),
    )
    unexpected_objective_history_payload["unexpected_step3_field"] = True
    with pytest.raises(GameLifecycleError, match="payload fields are invalid"):
        PrimaryObjectiveTurnStartState.from_payload(
            cast(PrimaryObjectiveTurnStartStatePayload, unexpected_objective_history_payload)
        )

    invalid_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    snapshot_payload = invalid_payload["primary_rules_unit_turn_start_snapshots"][0]
    snapshot_payload["rules_unit_memberships"][0]["component_memberships"][0][
        "logical_terrain_area_ids"
    ] = ["missing-terrain"]
    with pytest.raises(GameLifecycleError, match="unknown logical terrain area"):
        GameState.from_payload(invalid_payload)

    incomplete_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    incomplete_payload["primary_rules_unit_turn_start_snapshots"][0]["rules_unit_memberships"].pop()
    with pytest.raises(GameLifecycleError, match="every physical unit"):
        GameState.from_payload(incomplete_payload)

    drifted_destruction_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    enemy_destruction_payload = next(
        row
        for row in drifted_destruction_payload["primary_unit_destruction_states"]
        if row["destroyed_unit_instance_id"] == "army-beta:intercessor-unit-3"
    )
    enemy_destruction_payload["started_turn_terrain_feature_ids"] = []
    with pytest.raises(GameLifecycleError, match="does not match its turn snapshot"):
        GameState.from_payload(drifted_destruction_payload)

    owner_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    owner_drift_row = next(
        row
        for row in owner_drift_payload["primary_unit_destruction_states"]
        if row["destroyed_unit_instance_id"] == "army-beta:intercessor-unit-3"
    )
    owner_drift_row["destroyed_player_id"] = "player-a"
    with pytest.raises(GameLifecycleError, match="destroyed player drift"):
        GameState.from_payload(owner_drift_payload)

    source_component_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    source_component_drift_row = next(
        row
        for row in source_component_drift_payload["primary_unit_destruction_states"]
        if row["destroyed_unit_instance_id"] == "army-beta:intercessor-unit-3"
    )
    source_witness_payload = source_component_drift_row[
        "source_rules_unit_objective_proximity_witness"
    ]
    assert source_witness_payload is not None
    source_witness_payload["component_unit_instance_ids"] = ["army-beta:intercessor-unit-3"]
    with pytest.raises(GameLifecycleError, match="source witness component identity drift"):
        GameState.from_payload(source_component_drift_payload)

    source_marker_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    source_marker_drift_row = next(
        row
        for row in source_marker_drift_payload["primary_unit_destruction_states"]
        if row["destroyed_unit_instance_id"] == "army-beta:intercessor-unit-3"
    )
    source_marker_witness = source_marker_drift_row["source_rules_unit_objective_proximity_witness"]
    assert source_marker_witness is not None
    source_marker_witness["objective_marker_witnesses"] = [
        {
            "objective_marker_id": "objective:unknown",
            "model_instance_ids": ["army-alpha:intercessor-unit-1:model-001"],
        }
    ]
    with pytest.raises(GameLifecycleError, match="unknown objective marker"):
        GameState.from_payload(source_marker_drift_payload)

    source_owner_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    source_owner_drift_row = next(
        row
        for row in source_owner_drift_payload["primary_unit_destruction_states"]
        if row["destroyed_unit_instance_id"] == "army-beta:intercessor-unit-3"
    )
    source_owner_drift_row["destroying_player_id"] = "player-b"
    source_attribution = source_owner_drift_row["destruction_attribution"]
    assert source_attribution is not None
    source_attribution["destroying_player_id"] = "player-b"
    with pytest.raises(
        GameLifecycleError,
        match="source rules unit must belong to the destroying player",
    ):
        GameState.from_payload(source_owner_drift_payload)

    identity_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    identity_drift_payload["primary_unit_destruction_states"][0]["destruction_id"] = (
        "primary-unit-destruction:tampered"
    )
    with pytest.raises(GameLifecycleError, match="destruction_id drift"):
        GameState.from_payload(identity_drift_payload)

    trap_objective_drift_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    trap_objective_drift_payload["primary_terrain_trap_states"][0]["is_objective"] = False
    with pytest.raises(GameLifecycleError, match="objective association drifted"):
        GameState.from_payload(trap_objective_drift_payload)

    trap_component_id_payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    trap_component_id_payload["primary_terrain_trap_states"][0]["terrain_feature_id"] = (
        area.members[0].terrain_area_id
    )
    with pytest.raises(GameLifecycleError, match="unknown logical terrain area"):
        GameState.from_payload(trap_component_id_payload)

    nullable_destruction_payload = cast(
        dict[str, object],
        json.loads(json.dumps(destruction.to_payload(), sort_keys=True)),
    )
    nullable_destruction_payload["started_turn_terrain_feature_ids"] = None
    with pytest.raises(GameLifecycleError, match="must be a list"):
        PrimaryUnitDestructionState.from_payload(
            cast(PrimaryUnitDestructionStatePayload, nullable_destruction_payload)
        )
    unexpected_destruction_payload = cast(
        dict[str, object],
        json.loads(json.dumps(destruction.to_payload(), sort_keys=True)),
    )
    unexpected_destruction_payload["unexpected_step3_field"] = True
    with pytest.raises(GameLifecycleError, match="payload fields are invalid"):
        PrimaryUnitDestructionState.from_payload(
            cast(PrimaryUnitDestructionStatePayload, unexpected_destruction_payload)
        )

    with pytest.raises(GameLifecycleError, match="terrain trap already exists"):
        state.record_primary_terrain_trap(
            player_id="player-a",
            terrain_feature_id=area_id,
            action_id="mission-action:phase16-booby-trap-duplicate",
            phase=BattlePhase.SHOOTING,
            source_id="phase16:death-trap:booby-trap-duplicate",
        )
    with pytest.raises(GameLifecycleError, match="destruction already exists"):
        _record_test_primary_unit_destruction(
            state,
            destroying_player_id="player-a",
            destroyed_unit_instance_id="army-beta:intercessor-unit-3",
            source_id="phase16:death-trap:enemy-destroyed",
        )
    with pytest.raises(GameLifecycleError, match="owner's turn"):
        replace(trap, active_player_id="player-b")
    with pytest.raises(GameLifecycleError):
        replace(destruction, destroying_player_id="")
    with pytest.raises(GameLifecycleError, match="must be a tuple"):
        replace(
            destruction,
            started_turn_terrain_feature_ids=cast(tuple[str, ...], None),
        )


def test_booby_trap_action_is_primary_scoped_and_immediate_zero_vp() -> None:
    lifecycle = _battle_lifecycle_for_primary("primary-immovable-object")
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)

    unsupported = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="booby-trap-terrain",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    unsupported_payload = cast(dict[str, JsonValue], unsupported.payload)

    assert unsupported.status_kind.value == "unsupported"
    assert unsupported.decision_request is None
    assert unsupported_payload["mission_id"] == "primary-death-trap"
    assert unsupported_payload["active_primary_mission_id"] == "primary-immovable-object"

    zero_vp_action = MissionActionState.start(
        action_id="mission-action:phase16-zero-vp-complete",
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id=SCORING_TERRAIN_FEATURE_ID,
        mission_id="primary-death-trap",
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        start_timing="shooting_phase",
        completion_timing="immediate",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=(),
        scoring_source_id="booby-trap-terrain",
        victory_points=0,
    )
    completed = zero_vp_action.complete_without_award(
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        completion_timing="immediate",
    )

    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.score_transaction_id is None

    with pytest.raises(GameLifecycleError, match="Only started mission Actions can complete"):
        completed.complete_without_award(
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="immediate",
        )
    with pytest.raises(GameLifecycleError, match="Only zero-VP mission Actions"):
        _mission_action_state(action_id="phase16-positive-vp-no-award").complete_without_award(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
        )
    with pytest.raises(GameLifecycleError, match="completion timing drift"):
        zero_vp_action.complete_without_award(
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="turn_end",
        )
    with pytest.raises(GameLifecycleError, match="cannot complete actions"):
        zero_vp_action.complete_without_award(
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            completion_timing="immediate",
            battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
        )
    with pytest.raises(GameLifecycleError, match="zero-VP mission Action must not score"):
        replace(
            completed,
            score_transaction_id="victory-point:player-a:round-01:000001",
        )


def test_fixed_secondary_scoring_is_public_after_secondary_reveal() -> None:
    state = _battle_state()

    scored = state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="assassination",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.COMMAND,
    )
    own_payload = state.to_public_payload(viewer_player_id="player-a")
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert scored.status is SecondaryMissionCardStatus.ACTIVE
    assert (
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.FIXED,
        )
        is not None
    )
    assert state.victory_point_total("player-a") == 4
    own_ledger = _public_ledger(own_payload, player_id="player-a")
    opponent_ledger = _public_ledger(opponent_payload, player_id="player-a")
    own_transactions = cast(list[JsonValue], own_ledger["transactions"])
    own_transaction = cast(dict[str, JsonValue], own_transactions[0])
    opponent_transactions = cast(list[JsonValue], opponent_ledger["transactions"])
    assert own_transaction["source_id"] == "assassination"
    assert opponent_transactions[0] == {
        "transaction_id": "victory-point:player-a:round-01:000001",
        "player_id": "player-a",
        "battle_round": 1,
        "phase": "command",
        "amount": 4,
        "source_kind": "fixed_secondary",
        "source_id": "assassination",
        "scoring_timing": "secondary_mission_score",
        "hidden": False,
        "metadata": {
            "secondary_mission_id": "assassination",
            "scoring_rule_id": "assassination-fixed",
            "scoring_rule_condition": "fixed_secondary_condition",
            "scoring_rule_source_id": (
                "gw-11e-chapter-approved-2026-27:secondary:assassination:"
                "scoring-rule:assassination-fixed"
            ),
        },
    }
    assert any(
        card_payload["player_id"] == "player-a"
        and card_payload["secondary_mission_id"] == "assassination"
        and card_payload["mode"] == "fixed"
        and card_payload["status"] == "active"
        and card_payload["hidden"] is False
        for card_payload in _public_card_states(opponent_payload)
    )


def test_fixed_secondary_cards_remain_active_and_cap_at_twenty_vp_per_mission() -> None:
    state = _battle_state()
    scored_cards = [
        state.score_secondary_mission(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.FIXED,
            phase=BattlePhase.COMMAND,
        )
        for _index in range(6)
    ]
    transactions = state.victory_point_ledger_for_player("player-a").transactions
    final_transaction_metadata = _transaction_metadata(transactions[-1])
    cap_audit = final_transaction_metadata["vp_cap_audit"]
    assert isinstance(cap_audit, dict)

    assert {card.status for card in scored_cards} == {SecondaryMissionCardStatus.ACTIVE}
    assert [transaction.amount for transaction in transactions] == [4, 4, 4, 4, 4, 0]
    assert state.victory_point_total("player-a") == 20
    assert cap_audit["capped_reasons"] == ["fixed_secondary_mission_vp_cap"]
    assert cap_audit["fixed_secondary_mission_cap"] == 20
    assert cap_audit["fixed_secondary_mission_points_before"] == 20
    assert cap_audit["fixed_secondary_mission_points_after"] == 20


def test_secondary_scoring_uses_source_backed_fixed_and_tactical_card_values() -> None:
    fixed_state = _battle_state()

    fixed_state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.COMMAND,
    )

    tactical_state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    tactical_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=1,
            source_result_id="phase11e-test-draw",
        )
    )
    tactical_state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )

    assert fixed_state.victory_point_total("player-a") == 4
    assert tactical_state.victory_point_total("player-a") == 5
    fixed_transaction = fixed_state.victory_point_ledger_for_player("player-a").transactions[0]
    tactical_transaction = tactical_state.victory_point_ledger_for_player("player-a").transactions[
        0
    ]
    assert fixed_transaction.metadata == {
        "secondary_mission_id": "bring-it-down",
        "scoring_rule_id": "bring-it-down-fixed",
        "scoring_rule_condition": "each_enemy_model_w10_or_more_destroyed_this_turn",
        "scoring_rule_source_id": (
            "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
            "scoring-rule:bring-it-down-fixed"
        ),
    }
    assert tactical_transaction.metadata == {
        "secondary_mission_id": "bring-it-down",
        "scoring_rule_id": "bring-it-down-tactical",
        "scoring_rule_condition": "each_enemy_model_w10_or_more_destroyed_this_turn",
        "scoring_rule_source_id": (
            "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
            "scoring-rule:bring-it-down-tactical"
        ),
    }


def test_bring_it_down_scores_each_destroyed_w10_model_and_caps_tactical() -> None:
    fixed_state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4"))
    )
    fixed_state.battle_phase_index = fixed_state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _record_secondary_vehicle_destruction(fixed_state, "army-beta:vehicle-unit-3")
    _record_secondary_vehicle_destruction(fixed_state, "army-beta:vehicle-unit-4")

    fixed_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.FIGHT,
    )

    tactical_state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4")),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    tactical_state.battle_phase_index = tactical_state.battle_phase_sequence.index(
        BattlePhase.FIGHT
    )
    tactical_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="bring-it-down",
            battle_round=1,
            source_result_id="phase16-bring-it-down-draw",
        )
    )
    _record_secondary_vehicle_destruction(tactical_state, "army-beta:vehicle-unit-3")
    _record_secondary_vehicle_destruction(tactical_state, "army-beta:vehicle-unit-4")

    tactical_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="bring-it-down",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    assert fixed_state.victory_point_total("player-a") == 5
    assert tactical_state.victory_point_total("player-a") == 5
    fixed_metadata = _transaction_metadata(
        fixed_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    tactical_metadata = _transaction_metadata(
        tactical_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert fixed_metadata["score_count_by_rule"] == {"bring-it-down-fixed": 2}
    assert fixed_metadata["victory_points_by_rule"] == {"bring-it-down-fixed": 5}
    assert tactical_metadata["score_count_by_rule"] == {"bring-it-down-tactical": 2}
    assert tactical_metadata["victory_points_by_rule"] == {"bring-it-down-tactical": 5}


def test_overwhelming_force_scores_destroyed_units_that_started_on_objectives_with_cap() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4")),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="overwhelming-force",
            battle_round=1,
            source_result_id="phase16-overwhelming-force-draw",
        )
    )
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-3",
        started_turn_objective_marker_ids=(
            "take-and-hold-vs-purge-the-foe-layout-3-center-central",
        ),
    )
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-4",
        started_turn_objective_marker_ids=(
            "take-and-hold-vs-purge-the-foe-layout-3-upper-central",
        ),
    )

    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="overwhelming-force",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    metadata = _transaction_metadata(
        state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert state.victory_point_total("player-a") == 5
    assert metadata["score_count_by_rule"] == {"overwhelming-force-tactical": 2}
    assert metadata["victory_points_by_rule"] == {"overwhelming-force-tactical": 5}


def test_no_prisoners_scores_each_destroyed_enemy_unit_with_cap() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_vehicles(("vehicle-unit-3", "vehicle-unit-4", "vehicle-unit-5")),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="no-prisoners",
            battle_round=1,
            source_result_id="phase17-secondary-no-prisoners-draw",
        )
    )
    _record_secondary_vehicle_destruction(state, "army-beta:vehicle-unit-3")
    _record_secondary_vehicle_destruction(state, "army-beta:vehicle-unit-4")
    _record_secondary_vehicle_destruction(state, "army-beta:vehicle-unit-5")

    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="no-prisoners",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    metadata = _transaction_metadata(
        state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert state.victory_point_total("player-a") == 5
    assert metadata["score_count_by_rule"] == {"no-prisoners-tactical": 3}
    assert metadata["victory_points_by_rule"] == {"no-prisoners-tactical": 5}


def test_a_grievous_blow_scores_destroyed_starting_strength_thirteen_units() -> None:
    state = _battle_state_from_config(
        _config_with_player_b_horde_units(("horde-unit-3", "horde-unit-4")),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="a-grievous-blow",
            battle_round=1,
            source_result_id="phase17-secondary-grievous-blow-draw",
        )
    )
    _record_secondary_unit_destruction(state, "army-beta:horde-unit-3")
    _record_secondary_unit_destruction(state, "army-beta:horde-unit-4")

    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="a-grievous-blow",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    metadata = _transaction_metadata(
        state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert state.victory_point_total("player-a") == 5
    assert metadata["score_count_by_rule"] == {"a-grievous-blow-tactical": 2}
    assert metadata["victory_points_by_rule"] == {"a-grievous-blow-tactical": 5}


def test_secure_no_mans_land_scores_two_central_objectives_from_control_record() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    assert state.mission_setup is not None
    policy = mission_scoring_policies_from_setup(state.mission_setup).policy_for_player("player-a")
    home_objective_id = "take-and-hold-vs-purge-the-foe-layout-3-left-home"
    controlled_central_ids = (
        "take-and-hold-vs-purge-the-foe-layout-3-center-central",
        "take-and-hold-vs-purge-the-foe-layout-3-upper-central",
    )
    record = ObjectiveControlRecord(
        record_id="phase17-secondary-secure-no-mans-land-record",
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="phase17-secondary-secure-no-mans-land-battlefield",
        results=(
            _controlled_objective_result(home_objective_id, player_id="player-a"),
            *(
                _controlled_objective_result(objective_id, player_id="player-a")
                for objective_id in controlled_central_ids
            ),
        ),
    )

    award = policy.secondary_award_from_mission_state(
        player_id="player-a",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        secondary_mission_id="secure-no-mans-land",
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
        record=record,
        mission_setup=state.mission_setup,
        unit_destruction_states=(),
        objective_cleanse_states=(),
        terrain_plunder_states=(),
        enemy_unit_ids_in_player_deployment_zone=(),
        starting_strength_records=tuple(state.starting_strength_records),
    )

    assert award is not None
    metadata = cast(dict[str, JsonValue], award.metadata)
    evidence = cast(dict[str, JsonValue], metadata["evidence_by_rule"])
    assert award.amount == 5
    assert metadata["score_count_by_rule"] == {"secure-no-mans-land-tactical": 1}
    assert evidence["secure-no-mans-land-tactical"] == {
        "score_count": 1,
        "controlled_objective_ids": list(controlled_central_ids),
        "home_objective_ids": [home_objective_id],
        "objective_marker_ids": [],
        "terrain_feature_ids": [],
        "destroyed_unit_instance_ids": [],
        "destroyed_model_instance_ids": [],
        "enemy_unit_instance_ids": [],
    }


def test_secure_no_mans_land_does_not_score_opponent_home_as_no_mans_land() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    assert state.mission_setup is not None
    policy = mission_scoring_policies_from_setup(state.mission_setup).policy_for_player("player-a")
    central_objective_id = "take-and-hold-vs-purge-the-foe-layout-3-center-central"
    opponent_home_objective_id = "take-and-hold-vs-purge-the-foe-layout-3-right-home"
    objective_marker_ids = {
        marker.objective_marker_id for marker in state.mission_setup.objective_markers
    }
    assert central_objective_id in objective_marker_ids
    assert opponent_home_objective_id in objective_marker_ids
    record = ObjectiveControlRecord(
        record_id="phase17-secondary-secure-no-mans-land-opponent-home-record",
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="phase17-secondary-secure-no-mans-land-opponent-home-battlefield",
        results=(
            _controlled_objective_result(central_objective_id, player_id="player-a"),
            _controlled_objective_result(opponent_home_objective_id, player_id="player-a"),
        ),
    )

    award = policy.secondary_award_from_mission_state(
        player_id="player-a",
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        secondary_mission_id="secure-no-mans-land",
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
        record=record,
        mission_setup=state.mission_setup,
        unit_destruction_states=(),
        objective_cleanse_states=(),
        terrain_plunder_states=(),
        enemy_unit_ids_in_player_deployment_zone=(),
        starting_strength_records=tuple(state.starting_strength_records),
    )

    assert award is None


def test_cleanse_and_plunder_score_from_recorded_action_evidence() -> None:
    cleanse_state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    cleanse_state.battle_phase_index = cleanse_state.battle_phase_sequence.index(BattlePhase.FIGHT)
    cleanse_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="cleanse",
            battle_round=1,
            source_result_id="phase16-cleanse-draw",
        )
    )
    center_cleanse_action_id = "phase16-cleanse-center"
    center_cleanse_source_id = _record_completed_zero_vp_mission_action(
        cleanse_state,
        mission_action_id="cleanse-objective",
        action_id=center_cleanse_action_id,
        target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
    )
    cleanse_state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
        action_id=center_cleanse_action_id,
        phase=BattlePhase.FIGHT,
        source_id=center_cleanse_source_id,
    )
    upper_cleanse_action_id = "phase16-cleanse-northwest"
    upper_cleanse_source_id = _record_completed_zero_vp_mission_action(
        cleanse_state,
        mission_action_id="cleanse-objective",
        action_id=upper_cleanse_action_id,
        target_id="take-and-hold-vs-purge-the-foe-layout-3-upper-central",
    )
    cleanse_state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id="take-and-hold-vs-purge-the-foe-layout-3-upper-central",
        action_id=upper_cleanse_action_id,
        phase=BattlePhase.FIGHT,
        source_id=upper_cleanse_source_id,
    )

    cleanse_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="cleanse",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    plunder_state = _battle_state(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        mission_setup=_event_companion_mission_setup_with_scoring_terrain_feature(),
    )
    plunder_state.battle_phase_index = plunder_state.battle_phase_sequence.index(BattlePhase.FIGHT)
    plunder_state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="plunder",
            battle_round=1,
            source_result_id="phase16-plunder-draw",
        )
    )
    assert plunder_state.mission_setup is not None
    plunder_area = _first_plunderable_logical_terrain_area(
        plunder_state,
        player_id="player-a",
    )
    plunder_action_id = "phase16-plunder-terrain"
    plunder_source_id = _record_completed_zero_vp_mission_action(
        plunder_state,
        mission_action_id="plunder-terrain",
        action_id=plunder_action_id,
        target_id=plunder_area.logical_terrain_area_id,
    )
    plunder_state.record_secondary_terrain_plunder(
        player_id="player-a",
        terrain_feature_id=plunder_area.logical_terrain_area_id,
        action_id=plunder_action_id,
        phase=BattlePhase.SHOOTING,
        source_id=plunder_source_id,
    )

    plunder_state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="plunder",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    cleanse_metadata = _transaction_metadata(
        cleanse_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    plunder_metadata = _transaction_metadata(
        plunder_state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert cleanse_state.victory_point_total("player-a") == 5
    assert cleanse_metadata["victory_points_by_rule"] == {
        "cleanse-tactical-one-objective": 2,
        "cleanse-tactical-two-objectives": 3,
    }
    assert plunder_state.victory_point_total("player-a") == 5
    assert plunder_metadata["victory_points_by_rule"] == {"plunder-tactical": 5}


def test_defend_stronghold_scores_at_opponent_turn_end_with_deployment_zone_bonus() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state.battle_round = 2
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="defend-stronghold",
            battle_round=2,
            source_result_id="phase16-defend-stronghold-draw",
        )
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="left-home",
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-beta:intercessor-unit-3",
        target_suffix="southwest",
    )

    state.score_secondary_mission_from_state(
        player_id="player-a",
        secondary_mission_id="defend-stronghold",
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.FIGHT,
    )

    metadata = _transaction_metadata(
        state.victory_point_ledger_for_player("player-a").transactions[0]
    )
    assert state.victory_point_total("player-a") == 5
    assert metadata["victory_points_by_rule"] == {
        "defend-stronghold-home-objective": 3,
        "defend-stronghold-no-enemy-in-deployment-zone": 2,
    }


def test_secondary_scoring_evidence_payloads_round_trip_and_fail_fast() -> None:
    model = SecondaryDestroyedModelState(
        model_instance_id="army-beta:vehicle-unit-3:model-1",
        starting_wounds=10,
    )
    destruction = SecondaryUnitDestructionState(
        destruction_id="secondary-unit-destruction:phase11e-game:round-01:vehicle-unit-3",
        game_id="phase11e-game",
        destroying_player_id="player-a",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        destroyed_unit_instance_id="army-beta:vehicle-unit-3",
        destroyed_models=(model,),
        started_turn_objective_marker_ids=(
            "take-and-hold-vs-purge-the-foe-layout-3-center-central",
        ),
        source_id="phase16:test-destruction",
    )
    cleanse = SecondaryObjectiveCleanseState(
        cleanse_id="secondary-objective-cleanse:phase11e-game:round-01:player-a:center",
        game_id="phase11e-game",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        objective_marker_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
        action_id="mission-action:phase16-cleanse-center",
        source_id="cleanse",
    )
    plunder = SecondaryTerrainPlunderState(
        plunder_id="secondary-terrain-plunder:phase11e-game:round-01:player-a:ruin-1",
        game_id="phase11e-game",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=1,
        phase=BattlePhase.SHOOTING.value,
        terrain_feature_id="ruin-1",
        action_id="mission-action:phase16-plunder-ruin-1",
        source_id="plunder",
    )
    rule = SecondaryMissionScoringRule(
        secondary_mission_id="plunder",
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        timing="your_turn_end",
        victory_points=5,
        cap=None,
        condition="one_or_more_terrain_areas_plundered_this_turn",
        rule_id="plunder-tactical",
        source_id="phase16:plunder-rule",
    )

    assert SecondaryDestroyedModelState.from_payload(model.to_payload()) == model
    assert SecondaryUnitDestructionState.from_payload(destruction.to_payload()) == destruction
    assert SecondaryObjectiveCleanseState.from_payload(cleanse.to_payload()) == cleanse
    assert SecondaryTerrainPlunderState.from_payload(plunder.to_payload()) == plunder
    assert SecondaryMissionScoringRule.from_payload(rule.to_payload()) == rule
    with pytest.raises(GameLifecycleError, match="enemy unit"):
        SecondaryUnitDestructionState(
            destruction_id="secondary-unit-destruction:phase11e-game:round-01:friendly",
            game_id="phase11e-game",
            destroying_player_id="player-a",
            destroyed_player_id="player-a",
            active_player_id="player-a",
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            destroyed_unit_instance_id="army-alpha:intercessor-unit-1",
            destroyed_models=(model,),
            started_turn_objective_marker_ids=(),
            source_id="phase16:test-friendly-destruction",
        )
    with pytest.raises(GameLifecycleError, match="owner's turn"):
        SecondaryObjectiveCleanseState(
            cleanse_id="secondary-objective-cleanse:phase11e-game:round-01:player-a:bad",
            game_id="phase11e-game",
            player_id="player-a",
            active_player_id="player-b",
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            objective_marker_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            action_id="mission-action:phase16-cleanse-bad",
            source_id="cleanse",
        )
    with pytest.raises(GameLifecycleError, match="owner's turn"):
        SecondaryTerrainPlunderState(
            plunder_id="secondary-terrain-plunder:phase11e-game:round-01:player-a:bad",
            game_id="phase11e-game",
            player_id="player-a",
            active_player_id="player-b",
            battle_round=1,
            phase=BattlePhase.SHOOTING.value,
            terrain_feature_id="ruin-1",
            action_id="mission-action:phase16-plunder-bad",
            source_id="plunder",
        )
    with pytest.raises(GameLifecycleError, match="secondary source kind"):
        SecondaryMissionScoringRule(
            secondary_mission_id="plunder",
            source_kind=VictoryPointSourceKind.PRIMARY,
            timing="your_turn_end",
            victory_points=5,
            cap=None,
            condition="terrain_area_plundered_this_turn",
            rule_id="plunder-primary-invalid",
            source_id="phase16:plunder-rule-invalid",
        )
    with pytest.raises(GameLifecycleError, match="Unsupported secondary scoring rule condition"):
        SecondaryMissionScoringRule(
            secondary_mission_id="plunder",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            timing="your_turn_end",
            victory_points=5,
            cap=None,
            condition="unsupported_condition",
            rule_id="plunder-condition-invalid",
            source_id="phase16:plunder-rule-invalid",
        )


def test_state_backed_secondary_scoring_rejects_invalid_contexts_and_zero_evidence() -> None:
    state = _battle_state(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    assert state.mission_setup is not None
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    )
    policy = mission_scoring_policies_from_setup(state.mission_setup).policy_for_player("player-a")
    empty_destructions: tuple[SecondaryUnitDestructionState, ...] = ()
    empty_cleanses: tuple[SecondaryObjectiveCleanseState, ...] = ()
    empty_plunders: tuple[SecondaryTerrainPlunderState, ...] = ()
    empty_enemy_zone_units: tuple[str, ...] = ()

    assert (
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
        is None
    )
    with pytest.raises(GameLifecycleError, match="requires objective record"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=cast(ObjectiveControlRecord, object()),
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="requires MissionSetup"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=cast(MissionSetup, object()),
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="requires secondary kind"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.PRIMARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="record timing drift"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round + 1,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="bring-it-down",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )
    with pytest.raises(GameLifecycleError, match="not source-backed"):
        policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="not-source-backed",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )

    unsupported_timing_policy = replace(
        policy,
        secondary_scoring_rules=(
            SecondaryMissionScoringRule(
                secondary_mission_id="phase16-test-secondary",
                source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
                timing="unsupported-timing",
                victory_points=1,
                cap=None,
                condition="one_or_more_terrain_areas_plundered_this_turn",
                rule_id="phase16-test-secondary-unsupported-timing",
                source_id="phase16:test-secondary-unsupported-timing",
            ),
        ),
    )
    with pytest.raises(GameLifecycleError, match="Unsupported secondary scoring rule timing"):
        unsupported_timing_policy.secondary_award_from_mission_state(
            player_id="player-a",
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            secondary_mission_id="phase16-test-secondary",
            source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
            hidden=False,
            record=record,
            mission_setup=state.mission_setup,
            unit_destruction_states=empty_destructions,
            objective_cleanse_states=empty_cleanses,
            terrain_plunder_states=empty_plunders,
            enemy_unit_ids_in_player_deployment_zone=empty_enemy_zone_units,
        )


def test_game_state_secondary_scoring_evidence_round_trips_and_rejects_duplicates() -> None:
    state = _battle_state_from_config(
        replace(
            _config_with_player_b_vehicles(("vehicle-unit-3",)),
            mission_setup=_event_companion_mission_setup_with_scoring_terrain_feature(),
        ),
        player_a_secondary=SecondaryMissionMode.TACTICAL,
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    assert state.mission_setup is not None
    center_objective_id = _center_marker_definition_for_setup(
        state.mission_setup
    ).objective_marker_id
    _record_secondary_vehicle_destruction(
        state,
        "army-beta:vehicle-unit-3",
        started_turn_objective_marker_ids=(center_objective_id,),
    )
    cleanse_action_id = "phase16-cleanse-center"
    cleanse_source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="cleanse-objective",
        action_id=cleanse_action_id,
        target_id=center_objective_id,
    )
    state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id=center_objective_id,
        action_id=cleanse_action_id,
        phase=BattlePhase.FIGHT,
        source_id=cleanse_source_id,
    )
    plunder_area = _first_plunderable_logical_terrain_area(state, player_id="player-a")
    plunder_action_id = "phase16-plunder-terrain"
    plunder_source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="plunder-terrain",
        action_id=plunder_action_id,
        target_id=plunder_area.logical_terrain_area_id,
    )
    state.record_secondary_terrain_plunder(
        player_id="player-a",
        terrain_feature_id=plunder_area.logical_terrain_area_id,
        action_id=plunder_action_id,
        phase=BattlePhase.SHOOTING,
        source_id=plunder_source_id,
    )

    payload = state.to_payload()
    restored = GameState.from_payload(payload)

    assert restored.secondary_unit_destruction_states == state.secondary_unit_destruction_states
    assert restored.secondary_objective_cleanse_states == state.secondary_objective_cleanse_states
    assert restored.secondary_terrain_plunder_states == state.secondary_terrain_plunder_states
    duplicate_unit_state = replace(
        state.secondary_unit_destruction_states[0],
        destruction_id=f"{state.secondary_unit_destruction_states[0].destruction_id}:duplicate",
    )
    duplicate_cleanse_state = replace(
        state.secondary_objective_cleanse_states[0],
        cleanse_id=f"{state.secondary_objective_cleanse_states[0].cleanse_id}:duplicate",
        action_id="phase16-cleanse-center-duplicate",
    )
    duplicate_plunder_state = replace(
        state.secondary_terrain_plunder_states[0],
        plunder_id=f"{state.secondary_terrain_plunder_states[0].plunder_id}:duplicate",
        action_id="phase16-plunder-terrain-duplicate",
    )
    with pytest.raises(GameLifecycleError, match="unique per destroyed unit"):
        replace(
            state,
            secondary_unit_destruction_states=[
                *state.secondary_unit_destruction_states,
                duplicate_unit_state,
            ],
        )
    with pytest.raises(GameLifecycleError, match="unique per objective turn"):
        replace(
            state,
            secondary_objective_cleanse_states=[
                *state.secondary_objective_cleanse_states,
                duplicate_cleanse_state,
            ],
        )
    with pytest.raises(GameLifecycleError, match="unique per player turn"):
        replace(
            state,
            secondary_terrain_plunder_states=[
                *state.secondary_terrain_plunder_states,
                duplicate_plunder_state,
            ],
        )


def test_secondary_choices_remain_secret_until_all_players_select() -> None:
    state = GameState.from_config(_config())
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-a", mode=SecondaryMissionMode.FIXED)
    )

    player_b_payload = state.to_public_payload(viewer_player_id="player-b")
    player_a_choice = _public_secondary_choice(player_b_payload, player_id="player-a")

    assert state.secondary_mission_choices_are_revealed() is False
    assert player_a_choice == {
        "player_id": "player-a",
        "selected": True,
        "hidden": True,
    }
    assert "assassination" not in json.dumps(player_b_payload, sort_keys=True)
    assert "bring-it-down" not in json.dumps(player_b_payload, sort_keys=True)
    assert player_b_payload["secondary_mission_card_states"] == []


def test_secondary_choices_are_public_after_all_players_select() -> None:
    state = _battle_state(
        player_a_secondary=SecondaryMissionMode.FIXED,
        player_b_secondary=SecondaryMissionMode.TACTICAL,
    )

    player_a_payload = state.to_public_payload(viewer_player_id="player-a")
    player_b_payload = state.to_public_payload(viewer_player_id="player-b")

    assert state.secondary_mission_choices_are_revealed() is True
    assert _public_secondary_choice(player_a_payload, player_id="player-b") == {
        "player_id": "player-b",
        "selected": True,
        "hidden": False,
        "mode": "tactical",
        "fixed_mission_ids": [],
    }
    assert _public_secondary_choice(player_b_payload, player_id="player-a") == {
        "player_id": "player-a",
        "selected": True,
        "hidden": False,
        "mode": "fixed",
        "fixed_mission_ids": ["assassination", "bring-it-down"],
    }


def test_secondary_reveal_event_emits_after_both_choices_without_pre_reveal_leak() -> None:
    lifecycle = GameLifecycle()
    lifecycle.start(_config())
    first_status = _advance_to_secondary_request(lifecycle)
    first_request = first_status.decision_request
    assert first_request is not None
    assert first_request.actor_id == "player-a"

    lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=first_request.request_id,
            selected_option_id="fixed:assassination:bring-it-down",
            result_id="phase11e-first-secondary",
        ).to_result(first_request)
    )
    player_b_before_reveal = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    assert not any(
        event["event_type"] == "secondary_missions_revealed"
        for event in player_b_before_reveal["events"]
    )
    assert not any(
        event["event_type"] == "secondary_mission_choice_recorded"
        for event in player_b_before_reveal["events"]
    )
    player_a_before_second_submit = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    assert not any(
        event["event_type"] == "decision_requested"
        for event in player_a_before_second_submit["events"]
        if isinstance(event["payload"], dict)
        and event["payload"].get("decision_type") == "hidden_decision"
    )

    second_status = lifecycle.advance_until_decision_or_terminal()
    second_request = second_status.decision_request
    assert second_request is not None
    assert second_request.actor_id == "player-b"
    lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=second_request.request_id,
            selected_option_id="tactical",
            result_id="phase11e-second-secondary",
        ).to_result(second_request)
    )

    player_a_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-a",
    )
    reveal_event = next(
        event
        for event in player_a_events["events"]
        if event["event_type"] == "secondary_missions_revealed"
    )
    reveal_payload = cast(dict[str, JsonValue], reveal_event["payload"])
    assert reveal_payload["choices"] == [
        {
            "player_id": "player-a",
            "mode": "fixed",
            "fixed_mission_ids": ["assassination", "bring-it-down"],
        },
        {
            "player_id": "player-b",
            "mode": "tactical",
            "fixed_mission_ids": [],
        },
    ]


def test_secondary_reveal_event_does_not_perturb_later_dice_history() -> None:
    spec = DiceRollSpec(
        expression=DiceExpression(quantity=2, sides=6),
        reason="Post secondary reveal roll",
        roll_type="phase11e_regression_roll",
        actor_id="player-a",
    )
    baseline_history = EventLog()
    baseline_history.append(
        "phase11e_post_reveal_marker",
        {
            "game_id": "phase11e-game",
            "marker": "after-secondary-selection",
        },
    )
    reveal_history = EventLog()
    reveal_history.append(
        "secondary_missions_revealed",
        {
            "game_id": "phase11e-game",
            "setup_step": "select_secondary_missions",
            "choices": [
                {
                    "player_id": "player-a",
                    "mode": "fixed",
                    "fixed_mission_ids": ["assassination", "bring-it-down"],
                },
                {
                    "player_id": "player-b",
                    "mode": "tactical",
                    "fixed_mission_ids": list[str](),
                },
            ],
        },
    )
    reveal_history.append(
        "phase11e_post_reveal_marker",
        {
            "game_id": "phase11e-game",
            "marker": "after-secondary-selection",
        },
    )

    baseline_roll = DiceRollManager(
        "phase11e-reveal-neutral",
        event_log=baseline_history,
    ).roll(spec)
    reveal_roll = DiceRollManager(
        "phase11e-reveal-neutral",
        event_log=reveal_history,
    ).roll(spec)

    assert reveal_roll.to_payload() == baseline_roll.to_payload()


def test_tactical_secondary_draw_score_discard_flow_is_public_after_reveal() -> None:
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    waiting = lifecycle.advance_until_decision_or_terminal()
    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_DRAW_DECISION_TYPE

    result = DecisionResult.for_request(
        result_id="phase11e-tactical-draw",
        request=request,
        selected_option_id="draw",
    )
    draw_status = lifecycle.submit_decision(result)
    draw_status = _decline_stratagem_window_if_pending(
        lifecycle,
        draw_status,
        result_id="phase11e-tactical-draw-decline-stratagem",
    )
    automatic_follow_up = draw_status.decision_request
    assert automatic_follow_up is not None
    assert automatic_follow_up.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    drawn_cards = [
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a" and card.mode is SecondaryMissionCardMode.TACTICAL
    ]
    assert len(drawn_cards) == state.tactical_secondary_draw_count
    draw_opponent_events = EventStreamCursor().events_since(
        decisions.event_log,
        viewer_player_id="player-b",
    )
    draw_event = next(
        event
        for event in draw_opponent_events["events"]
        if event["event_type"] == "tactical_secondary_missions_drawn"
    )
    draw_payload = cast(dict[str, JsonValue], draw_event["payload"])
    drawn_card_payloads = cast(list[JsonValue], draw_payload["secondary_mission_card_states"])
    assert draw_payload["player_id"] == "player-a"
    assert draw_payload["draw_count"] == 2
    assert {
        str(cast(dict[str, JsonValue], card)["secondary_mission_id"])
        for card in drawn_card_payloads
    } == {card.secondary_mission_id for card in drawn_cards}

    discard_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = discard_lifecycle.state
    assert state is not None
    decisions = discard_lifecycle.decision_controller
    active_cards = sorted(
        (
            card
            for card in state.secondary_mission_card_states
            if card.player_id == "player-a" and card.mode is SecondaryMissionCardMode.TACTICAL
        ),
        key=lambda card: card.secondary_mission_id,
    )
    assert len(active_cards) == state.tactical_secondary_draw_count
    scored = state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id=active_cards[0].secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=decisions,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    assert discard_request.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE
    discard_option_id = f"discard:{active_cards[1].secondary_mission_id}"
    discard_payload = cast(dict[str, JsonValue], discard_request.payload)
    assert [active_cards[1].secondary_mission_id] in cast(
        list[list[str]],
        discard_payload["legal_secondary_mission_id_sets"],
    )
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=discard_option_id,
        result_id="phase11e-discard-tactical",
    ).to_result(discard_request)
    discard_lifecycle.submit_decision(discard_result)
    discarded = state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=active_cards[1].secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    assert discarded is None
    discarded_record = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == active_cards[1].secondary_mission_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
    )
    discard_opponent_events = EventStreamCursor().events_since(
        decisions.event_log,
        viewer_player_id="player-b",
    )
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert scored.status is SecondaryMissionCardStatus.SCORED
    assert discarded_record.status is SecondaryMissionCardStatus.DISCARDED
    expected_score = state.victory_point_ledger_for_player("player-a").transactions[0].amount
    assert state.victory_point_total("player-a") == expected_score
    assert decisions.records[-1].request.decision_type == TACTICAL_SECONDARY_DISCARD_DECISION_TYPE
    assert decisions.records[-1].result.result_id == "phase11e-discard-tactical"
    discard_event = next(
        event
        for event in discard_opponent_events["events"]
        if event["event_type"] == "tactical_secondary_missions_discarded"
    )
    public_discard_payload = cast(dict[str, JsonValue], discard_event["payload"])
    assert public_discard_payload["player_id"] == "player-a"
    assert public_discard_payload["secondary_mission_ids"] == [active_cards[1].secondary_mission_id]
    assert opponent_payload["tactical_secondary_draws"] == [
        {
            "player_id": "player-a",
            "battle_round": 1,
            "request_id": SEEDED_TACTICAL_DRAW_REQUEST_ID,
            "result_id": SEEDED_TACTICAL_DRAW_RESULT_ID,
            "draw_count": 2,
        }
    ]
    assert any(
        card_payload["player_id"] == "player-a"
        and card_payload["secondary_mission_id"] == active_cards[0].secondary_mission_id
        and card_payload["mode"] == "tactical"
        and card_payload["status"] == "scored"
        for card_payload in _public_card_states(opponent_payload)
    )
    player_a_ledger = _public_ledger(opponent_payload, player_id="player-a")
    transactions = cast(list[JsonValue], player_a_ledger["transactions"])
    transaction = cast(dict[str, JsonValue], transactions[0])
    assert transaction["source_kind"] == "tactical_secondary"
    assert transaction["source_id"] == active_cards[0].secondary_mission_id
    assert transaction["metadata"] == {
        "secondary_mission_id": active_cards[0].secondary_mission_id,
        "scoring_rule_id": f"{active_cards[0].secondary_mission_id}-tactical",
        "scoring_rule_condition": "tactical_secondary_condition",
        "scoring_rule_source_id": (
            f"gw-11e-chapter-approved-2026-27:secondary:"
            f"{active_cards[0].secondary_mission_id}:scoring-rule:"
            f"{active_cards[0].secondary_mission_id}-tactical"
        ),
    }
    round_tripped = GameLifecycle.from_payload(discard_lifecycle.to_payload())
    encoded = json.dumps(round_tripped.to_payload(), sort_keys=True)
    assert "<" not in encoded
    assert "object at 0x" not in encoded


def test_tactical_secondary_discard_rejects_drifted_lifecycle_option() -> None:
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    waiting = lifecycle.advance_until_decision_or_terminal()
    draw_request = waiting.decision_request
    assert draw_request is not None
    draw_result = FiniteOptionSubmission(
        request_id=draw_request.request_id,
        selected_option_id="draw",
        result_id="phase11e-drift-draw",
    ).to_result(draw_request)
    draw_status = lifecycle.submit_decision(draw_result)
    draw_status = _decline_stratagem_window_if_pending(
        lifecycle,
        draw_status,
        result_id="phase11e-drift-draw-decline-stratagem",
    )
    automatic_follow_up = draw_status.decision_request
    assert automatic_follow_up is not None
    assert automatic_follow_up.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE

    discard_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = discard_lifecycle.state
    assert state is not None
    decisions = discard_lifecycle.decision_controller
    active_card = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=decisions,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card.secondary_mission_id}",
        result_id="phase11e-drift-discard",
    ).to_result(discard_request)
    state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id=active_card.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )

    status = discard_lifecycle.submit_decision(discard_result)

    assert status.status_kind.value == "invalid"
    assert not decisions.records
    assert decisions.queue.peek_next().request_id == discard_request.request_id


def test_phase14j_tactical_secondary_score_requires_engine_achievement_context() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    card = _active_tactical_card(state)
    unrecorded_context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-unrecorded-achievement",
    )

    unsupported = request_tactical_secondary_score(
        state=state,
        decisions=lifecycle.decision_controller,
        achievement_context=unrecorded_context,
    )

    assert unsupported.status_kind.value == "unsupported"
    assert unsupported.decision_request is None
    assert lifecycle.decision_controller.queue.pending_requests == ()


def test_phase14j_tactical_secondary_score_decision_can_score_or_retain_card() -> None:
    retain_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    retain_state = retain_lifecycle.state
    assert retain_state is not None
    retain_card = _active_tactical_card(retain_state)
    retain_context = _record_tactical_secondary_achievement_context(
        state=retain_state,
        card=retain_card,
        achievement_id="phase14j-retain-achievement",
    )
    retain_waiting = request_tactical_secondary_score(
        state=retain_state,
        decisions=retain_lifecycle.decision_controller,
        achievement_context=retain_context,
    )
    retain_request = retain_waiting.decision_request
    assert retain_request is not None
    assert retain_request.decision_type == TACTICAL_SECONDARY_SCORE_DECISION_TYPE
    assert retain_request.actor_id == "player-a"
    assert [option.option_id for option in retain_request.options] == [
        f"retain:{retain_card.secondary_mission_id}",
        f"score:{retain_card.secondary_mission_id}",
    ]
    retain_payload = cast(dict[str, JsonValue], retain_request.payload)
    assert retain_payload["achievement_id"] == retain_context.achievement_id
    assert retain_payload["victory_points"] == 5
    assert retain_payload["scoring_rule_id"] == f"{retain_card.secondary_mission_id}-tactical"
    assert retain_payload["scoring_rule_source_id"] == (
        f"gw-11e-chapter-approved-2026-27:secondary:{retain_card.secondary_mission_id}:"
        f"scoring-rule:{retain_card.secondary_mission_id}-tactical"
    )

    retain_lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=retain_request.request_id,
            selected_option_id=f"retain:{retain_card.secondary_mission_id}",
            result_id="phase14j-retain-tactical-score",
        ).to_result(retain_request)
    )

    retained = retain_state.secondary_mission_card_state(
        player_id="player-a",
        secondary_mission_id=retain_card.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
    )
    retain_event = next(
        event
        for event in retain_lifecycle.decision_controller.event_log.records
        if event.event_type == "tactical_secondary_mission_score_declined"
    )
    assert retained is not None
    assert retained.status is SecondaryMissionCardStatus.ACTIVE
    assert (
        retain_state.tactical_secondary_achievement_context(retain_context.achievement_id) is None
    )
    assert retain_state.victory_point_total("player-a") == 0
    assert cast(dict[str, JsonValue], retain_event.payload)["retained"] is True

    score_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    score_state = score_lifecycle.state
    assert score_state is not None
    score_card = _active_tactical_card(score_state)
    score_context = _record_tactical_secondary_achievement_context(
        state=score_state,
        card=score_card,
        achievement_id="phase14j-score-achievement",
    )
    score_waiting = request_tactical_secondary_score(
        state=score_state,
        decisions=score_lifecycle.decision_controller,
        achievement_context=score_context,
    )
    score_request = score_waiting.decision_request
    assert score_request is not None

    score_lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=score_request.request_id,
            selected_option_id=f"score:{score_card.secondary_mission_id}",
            result_id="phase14j-score-tactical",
        ).to_result(score_request)
    )

    assert (
        score_state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=score_card.secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
    )
    scored_record = next(
        card
        for card in score_state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == score_card.secondary_mission_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
    )
    score_event = next(
        event
        for event in score_lifecycle.decision_controller.event_log.records
        if event.event_type == "tactical_secondary_mission_scored"
    )
    score_payload = cast(dict[str, JsonValue], score_event.payload)
    assert scored_record.status is SecondaryMissionCardStatus.SCORED
    assert score_state.tactical_secondary_achievement_context(score_context.achievement_id) is None
    assert score_state.victory_point_total("player-a") == 5
    assert score_payload["discarded_after_score"] is True
    event_context = cast(dict[str, JsonValue], score_payload["achievement_context"])
    assert event_context["achievement_id"] == score_context.achievement_id
    transaction = cast(dict[str, JsonValue], score_payload["victory_point_transaction"])
    assert transaction["source_kind"] == "tactical_secondary"
    assert transaction["source_id"] == score_card.secondary_mission_id
    transaction_metadata = cast(dict[str, JsonValue], transaction["metadata"])
    assert transaction_metadata["scoring_rule_source_id"] == score_context.scoring_rule_source_id


def test_phase14j_tactical_secondary_score_rejects_drifted_lifecycle_option() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    card = _active_tactical_card(state)
    context = _record_tactical_secondary_achievement_context(
        state=state,
        card=card,
        achievement_id="phase14j-card-drift-achievement",
    )
    waiting = request_tactical_secondary_score(
        state=state,
        decisions=lifecycle.decision_controller,
        achievement_context=context,
    )
    request = waiting.decision_request
    assert request is not None
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"score:{card.secondary_mission_id}",
        result_id="phase14j-score-drift",
    ).to_result(request)
    state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id=card.secondary_mission_id,
        mode=SecondaryMissionCardMode.TACTICAL,
        phase=BattlePhase.COMMAND,
    )

    status = lifecycle.submit_decision(result)

    assert status.status_kind.value == "invalid"
    assert not lifecycle.decision_controller.records
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_phase14j_tactical_secondary_score_rejects_stale_achievement_context() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    card = _active_tactical_card(state)
    context = _record_tactical_secondary_achievement_context(
        state=state,
        card=card,
        achievement_id="phase14j-missing-achievement",
    )
    waiting = request_tactical_secondary_score(
        state=state,
        decisions=lifecycle.decision_controller,
        achievement_context=context,
    )
    request = waiting.decision_request
    assert request is not None
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"score:{card.secondary_mission_id}",
        result_id="phase14j-score-missing-achievement",
    ).to_result(request)
    state.consume_tactical_secondary_achievement_context(context.achievement_id)

    status = lifecycle.submit_decision(result)

    assert status.status_kind.value == "invalid"
    invalid_payload = cast(dict[str, JsonValue], status.payload)
    assert invalid_payload["invalid_reason"] == "achievement_context_missing"
    assert not lifecycle.decision_controller.records
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_phase14j_tactical_secondary_score_rejects_round_phase_and_rule_drift() -> None:
    round_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    round_state = round_lifecycle.state
    assert round_state is not None
    round_card = _active_tactical_card(round_state)
    round_context = _record_tactical_secondary_achievement_context(
        state=round_state,
        card=round_card,
        achievement_id="phase14j-round-drift-achievement",
    )
    round_waiting = request_tactical_secondary_score(
        state=round_state,
        decisions=round_lifecycle.decision_controller,
        achievement_context=round_context,
    )
    round_request = round_waiting.decision_request
    assert round_request is not None
    round_result = FiniteOptionSubmission(
        request_id=round_request.request_id,
        selected_option_id=f"score:{round_card.secondary_mission_id}",
        result_id="phase14j-round-drift",
    ).to_result(round_request)
    round_state.battle_round += 1

    round_status = round_lifecycle.submit_decision(round_result)

    assert round_status.status_kind.value == "invalid"
    round_payload = cast(dict[str, JsonValue], round_status.payload)
    assert round_payload["invalid_reason"] == "battle_round_drift"

    phase_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    phase_state = phase_lifecycle.state
    assert phase_state is not None
    phase_card = _active_tactical_card(phase_state)
    phase_context = _record_tactical_secondary_achievement_context(
        state=phase_state,
        card=phase_card,
        achievement_id="phase14j-phase-drift-achievement",
    )
    phase_waiting = request_tactical_secondary_score(
        state=phase_state,
        decisions=phase_lifecycle.decision_controller,
        achievement_context=phase_context,
    )
    phase_request = phase_waiting.decision_request
    assert phase_request is not None
    phase_result = FiniteOptionSubmission(
        request_id=phase_request.request_id,
        selected_option_id=f"score:{phase_card.secondary_mission_id}",
        result_id="phase14j-phase-drift",
    ).to_result(phase_request)
    phase_state.battle_phase_index = phase_state.battle_phase_sequence.index(BattlePhase.MOVEMENT)

    phase_status = phase_lifecycle.submit_decision(phase_result)

    assert phase_status.status_kind.value == "invalid"
    phase_payload = cast(dict[str, JsonValue], phase_status.payload)
    assert phase_payload["invalid_reason"] == "phase_drift"

    rule_lifecycle = _battle_lifecycle_with_active_tactical_cards()
    rule_state = rule_lifecycle.state
    assert rule_state is not None
    rule_card = _active_tactical_card(rule_state)
    rule_context = _record_tactical_secondary_achievement_context(
        state=rule_state,
        card=rule_card,
        achievement_id="phase14j-rule-drift-achievement",
    )
    rule_waiting = request_tactical_secondary_score(
        state=rule_state,
        decisions=rule_lifecycle.decision_controller,
        achievement_context=rule_context,
    )
    rule_request = rule_waiting.decision_request
    assert rule_request is not None
    rule_result = FiniteOptionSubmission(
        request_id=rule_request.request_id,
        selected_option_id=f"score:{rule_card.secondary_mission_id}",
        result_id="phase14j-rule-drift",
    ).to_result(rule_request)
    rule_state.tactical_secondary_achievement_contexts[0] = replace(
        rule_context,
        victory_points=rule_context.victory_points + 1,
    )

    rule_status = rule_lifecycle.submit_decision(rule_result)

    assert rule_status.status_kind.value == "invalid"
    rule_payload = cast(dict[str, JsonValue], rule_status.payload)
    assert rule_payload["invalid_reason"] == "victory_points_drift"


def test_phase14j_tactical_secondary_achievement_context_is_source_validated() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-invalid-achievement",
    )

    with pytest.raises(GameLifecycleError, match="VP drift"):
        state.record_tactical_secondary_achievement_context(
            replace(context, victory_points=context.victory_points + 1)
        )


def test_phase14j_tactical_secondary_achievement_context_round_trips_and_is_redacted() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _record_tactical_secondary_achievement_context(
        state=state,
        card=card,
        achievement_id="phase14j-round-trip-achievement",
    )

    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_tactical_secondary_achievement_context(context)
    with pytest.raises(GameLifecycleError, match="already exists for this card"):
        state.record_tactical_secondary_achievement_context(
            replace(context, achievement_id="phase14j-duplicate-card-achievement")
        )

    payload = state.to_payload()
    assert payload["tactical_secondary_achievement_contexts"] == [context.to_payload()]
    restored = GameState.from_payload(payload)
    assert restored.tactical_secondary_achievement_context(context.achievement_id) == context
    public_payload = restored.to_public_payload(viewer_player_id="player-a")
    assert public_payload["tactical_secondary_achievement_contexts"] == []


def test_phase14j_tactical_secondary_achievement_context_state_validation_rejects_drift() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-state-validation-achievement",
    )

    with pytest.raises(GameLifecycleError, match="game_id drift"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                replace(context, game_id="phase14j-other-game")
            ],
        )
    with pytest.raises(GameLifecycleError, match="player_id is not in this game"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                replace(context, player_id="phase14j-missing-player")
            ],
        )
    with pytest.raises(GameLifecycleError, match="active_player_id is not in this game"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                replace(context, active_player_id="phase14j-missing-active-player")
            ],
        )
    with pytest.raises(GameLifecycleError, match="must not duplicate IDs"):
        replace(state, tactical_secondary_achievement_contexts=[context, context])
    with pytest.raises(GameLifecycleError, match="must not duplicate cards"):
        replace(
            state,
            tactical_secondary_achievement_contexts=[
                context,
                replace(context, achievement_id="phase14j-state-duplicate-card"),
            ],
        )
    with pytest.raises(GameLifecycleError, match="does not exist"):
        state.consume_tactical_secondary_achievement_context("phase14j-missing-achievement")


def test_phase14j_tactical_secondary_achievement_context_rejects_non_tactical_mode() -> None:
    state = _battle_lifecycle_with_active_tactical_cards().state
    assert state is not None
    card = _active_tactical_card(state)
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id="phase14j-invalid-mode-achievement",
    )

    with pytest.raises(GameLifecycleError, match="Tactical mode"):
        replace(context, mode=SecondaryMissionCardMode.FIXED)


def test_event_companion_tactical_secondary_replacement_spends_cp_and_draws_one() -> None:
    lifecycle = _event_companion_battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    active_cards = sorted(
        (
            card
            for card in state.secondary_mission_card_states
            if card.player_id == "player-a"
            and card.mode is SecondaryMissionCardMode.TACTICAL
            and card.status is SecondaryMissionCardStatus.ACTIVE
        ),
        key=lambda card: card.secondary_mission_id,
    )
    replaced_card = active_cards[0]
    retained_card = active_cards[1]

    status = lifecycle.advance_until_decision_or_terminal()
    status = _decline_stratagem_window_if_pending(
        lifecycle,
        status,
        result_id="phase17j-replacement-decline-new-orders",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE
    request_payload = cast(dict[str, JsonValue], request.payload)
    assert request_payload["timing"] == "end_of_command_phase"
    assert request_payload["replacement_cost_cp"] == 1
    assert request_payload["replacement_discard_count"] == 1
    assert request_payload["replacement_draw_count"] == 1
    assert request_payload["legal_secondary_mission_ids"] == [
        card.secondary_mission_id for card in active_cards
    ]
    assert DecisionRequest.from_payload(request.to_payload()).to_payload() == request.to_payload()

    result_id = "phase17j-replace-tactical-secondary"
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"replace:{replaced_card.secondary_mission_id}",
        result_id=result_id,
    ).to_result(request)
    assert DecisionResult.from_payload(result.to_payload()).to_payload() == result.to_payload()
    status = lifecycle.submit_decision(result)

    assert status.decision_request is not None
    assert status.decision_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    assert state.command_point_total("player-a") == 0
    assert state.tactical_secondary_replacement_player_ids == ["player-a"]
    discarded = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.secondary_mission_id == replaced_card.secondary_mission_id
        and card.mode is SecondaryMissionCardMode.TACTICAL
    )
    active_after = sorted(
        (
            card
            for card in state.secondary_mission_card_states
            if card.player_id == "player-a"
            and card.mode is SecondaryMissionCardMode.TACTICAL
            and card.status is SecondaryMissionCardStatus.ACTIVE
        ),
        key=lambda card: card.secondary_mission_id,
    )
    replacement_events = [
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "tactical_secondary_mission_replaced"
    ]
    spend_events = [
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "command_points_spent"
    ]
    spend_payload = cast(dict[str, JsonValue], spend_events[-1].payload)

    assert discarded.status is SecondaryMissionCardStatus.DISCARDED
    assert discarded.discarded_result_id == result_id
    assert len(active_after) == 2
    assert retained_card.secondary_mission_id in {
        card.secondary_mission_id for card in active_after
    }
    assert replaced_card.secondary_mission_id not in {
        card.secondary_mission_id for card in active_after
    }
    assert any(card.source_result_id == result_id for card in active_after)
    assert spend_payload["source_id"] == (
        "gw-11e-warhammer-event-companion-v1-1-2026-07:secondary:"
        f"tactical-procedure:replacement:{result_id}:cp-spend"
    )
    assert cast(dict[str, JsonValue], replacement_events[-1].payload)["source_id"] == (
        "gw-11e-warhammer-event-companion-v1-1-2026-07:secondary:tactical-procedure"
    )
    payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    assert GameState.from_payload(payload).to_payload() == state.to_payload()


def test_event_companion_tactical_secondary_replacement_rejects_malformed_submission() -> None:
    lifecycle = _event_companion_battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    status = lifecycle.advance_until_decision_or_terminal()
    status = _decline_stratagem_window_if_pending(
        lifecycle,
        status,
        result_id="phase17j-replacement-malformed-decline-new-orders",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE
    replacement_option = next(
        option for option in request.options if option.option_id.startswith("replace:")
    )
    malformed = DecisionResult(
        result_id="phase17j-replacement-malformed",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=replacement_option.option_id,
        payload={"malformed": True},
    )
    record_count = len(lifecycle.decision_controller.records)

    invalid_status = lifecycle.submit_decision(malformed)

    assert invalid_status.status_kind.value == "invalid"
    invalid_payload = cast(dict[str, JsonValue], invalid_status.payload)
    assert invalid_payload == {
        "invalid_reason": "invalid_command_phase_decision_result",
        "field": "payload",
    }
    assert len(lifecycle.decision_controller.records) == record_count
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_event_companion_tactical_secondary_replacement_rejects_used_ledger_drift() -> None:
    lifecycle = _event_companion_battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    status = lifecycle.advance_until_decision_or_terminal()
    status = _decline_stratagem_window_if_pending(
        lifecycle,
        status,
        result_id="phase17j-replacement-drift-decline-new-orders",
    )
    request = status.decision_request
    assert request is not None
    assert request.decision_type == TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE
    active_card = _active_tactical_card(state)
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=f"replace:{active_card.secondary_mission_id}",
        result_id="phase17j-replacement-used-drift",
    ).to_result(request)
    record_count = len(lifecycle.decision_controller.records)
    state.record_tactical_secondary_replacement_use("player-a")

    invalid_status = lifecycle.submit_decision(result)

    assert invalid_status.status_kind.value == "invalid"
    invalid_payload = cast(dict[str, JsonValue], invalid_status.payload)
    assert invalid_payload["invalid_reason"] == "replacement_already_used"
    assert len(lifecycle.decision_controller.records) == record_count
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_event_companion_tactical_secondary_discard_cp_reward_uses_event_source_id() -> None:
    lifecycle = _event_companion_battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    active_card = _active_tactical_card(state)
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    result_id = "phase17j-event-own-turn-discard"
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card.secondary_mission_id}",
        result_id=result_id,
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    command_point_events = [
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "command_points_gained"
    ]
    command_point_gain = cast(dict[str, JsonValue], command_point_events[-1].payload)
    assert command_point_gain["source_id"] == (
        "gw-11e-warhammer-event-companion-v1-1-2026-07:secondary:"
        f"tactical-procedure:discard:{result_id}:cp-reward"
    )


def test_tactical_secondary_discard_cp_reward_shares_the_non_core_round_cap() -> None:
    lifecycle = _event_companion_battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    prior_gain = state.gain_command_points(
        player_id="player-a",
        amount=1,
        source_id="phase17j-prior-ability-cp-gain",
        source_kind=CommandPointSourceKind.OTHER,
    )
    assert prior_gain.status is CommandPointGainStatus.APPLIED
    active_card = _active_tactical_card(state)
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card.secondary_mission_id}",
        result_id="phase17j-capped-own-turn-discard",
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    assert state.command_point_total("player-a") == 1
    capped_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in reversed(lifecycle.decision_controller.event_log.records)
            if record.event_type == "command_points_gain_capped"
        ),
    )
    assert capped_payload["requested_amount"] == 1
    assert capped_payload["applied_amount"] == 0
    assert capped_payload["status"] == "capped"
    discard_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "tactical_secondary_missions_discarded"
        ),
    )
    assert discard_payload["command_point_gain"] == capped_payload


def test_tactical_secondary_discard_awards_source_backed_cp_in_own_turn() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    active_card = next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    result_id = "phase11e-own-turn-discard"
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card.secondary_mission_id}",
        result_id=result_id,
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    expected_source_id = (
        "gw-11e-chapter-approved-2026-27:secondary:"
        f"tactical-procedure:discard:{result_id}:cp-reward"
    )
    ledger = state.command_point_ledger_for_player("player-a")
    reward_transactions = [
        transaction
        for transaction in ledger.transactions
        if transaction.source_id == expected_source_id
    ]
    assert state.command_point_total("player-a") == 1
    assert len(reward_transactions) == 1
    assert reward_transactions[0].amount == 1
    assert reward_transactions[0].source_kind.value == "other"
    discard_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "tactical_secondary_missions_discarded"
        ),
    )
    command_point_gain = cast(dict[str, JsonValue], discard_payload["command_point_gain"])
    assert discard_payload["active_player_id"] == "player-a"
    assert discard_payload["secondary_mission_ids"] == [active_card.secondary_mission_id]
    assert discard_payload["command_point_reward_eligible"] is True
    assert discard_payload["command_point_reward_reason"] == "discarding_players_turn"
    assert command_point_gain["source_id"] == expected_source_id
    assert command_point_gain["status"] == "applied"

    second_discard_status = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
    )
    assert second_discard_status.status_kind.value == "unsupported"
    assert second_discard_status.decision_request is None
    assert (
        cast(
            dict[str, JsonValue],
            second_discard_status.payload,
        )["discard_cp_reward_window_id"]
        == state.tactical_secondary_discard_cp_reward_window_ids[0]
    )


def test_tactical_secondary_discard_set_awards_one_source_backed_cp_window() -> None:
    lifecycle = _battle_lifecycle_with_active_tactical_cards()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    active_cards = sorted(
        (
            card
            for card in state.secondary_mission_card_states
            if card.player_id == "player-a"
            and card.mode is SecondaryMissionCardMode.TACTICAL
            and card.status is SecondaryMissionCardStatus.ACTIVE
        ),
        key=lambda card: card.secondary_mission_id,
    )
    active_card_ids = tuple(card.secondary_mission_id for card in active_cards)
    assert len(active_card_ids) == state.tactical_secondary_draw_count
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    request_payload = cast(dict[str, JsonValue], discard_request.payload)
    assert request_payload["legal_secondary_mission_id_sets"] == [
        [active_card_ids[0]],
        [active_card_ids[1]],
        [active_card_ids[0], active_card_ids[1]],
    ]
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_card_ids[0]}+{active_card_ids[1]}",
        result_id="phase11e-own-turn-discard-set",
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    assert state.command_point_total("player-a") == 1
    assert len(state.tactical_secondary_discard_cp_reward_window_ids) == 1
    assert all(
        state.secondary_mission_card_state(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            mode=SecondaryMissionCardMode.TACTICAL,
        )
        is None
        for secondary_mission_id in active_card_ids
    )
    command_point_events = [
        record
        for record in lifecycle.decision_controller.event_log.records
        if record.event_type == "command_points_gained"
    ]
    assert len(command_point_events) == 1
    command_point_gain = cast(dict[str, JsonValue], command_point_events[0].payload)
    assert command_point_gain["requested_amount"] == 1
    assert command_point_gain["applied_amount"] == 1

    discard_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "tactical_secondary_missions_discarded"
        ),
    )
    assert discard_payload["secondary_mission_ids"] == list(active_card_ids)
    assert len(cast(list[JsonValue], discard_payload["secondary_mission_card_states"])) == len(
        active_card_ids
    )
    assert cast(dict[str, JsonValue], discard_payload["command_point_gain"]) == command_point_gain


def test_tactical_secondary_discard_in_opponents_turn_has_no_source_backed_cp_reward() -> None:
    lifecycle = _battle_lifecycle(player_b_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-b",
            battle_round=state.battle_round,
            request_id="phase11e-opponent-turn-tactical-draw-request",
            result_id="phase11e-opponent-turn-tactical-draw",
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    active_cards = state.draw_tactical_secondary_cards(
        player_id="player-b",
        source_result_id="phase11e-opponent-turn-tactical-draw",
    )
    discard_waiting = request_tactical_secondary_discard(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-b",
    )
    discard_request = discard_waiting.decision_request
    assert discard_request is not None
    assert discard_request.actor_id == "player-b"
    request_payload = cast(dict[str, JsonValue], discard_request.payload)
    assert request_payload["active_player_id"] == "player-a"
    discard_result = FiniteOptionSubmission(
        request_id=discard_request.request_id,
        selected_option_id=f"discard:{active_cards[0].secondary_mission_id}",
        result_id="phase11e-opponent-turn-discard",
    ).to_result(discard_request)

    lifecycle.submit_decision(discard_result)

    assert state.command_point_total("player-b") == 0
    assert all(
        not transaction.source_id.endswith(":cp-reward")
        for transaction in state.command_point_ledger_for_player("player-b").transactions
    )
    discard_payload = cast(
        dict[str, JsonValue],
        next(
            record.payload
            for record in lifecycle.decision_controller.event_log.records
            if record.event_type == "tactical_secondary_missions_discarded"
        ),
    )
    assert discard_payload["player_id"] == "player-b"
    assert discard_payload["secondary_mission_ids"] == [active_cards[0].secondary_mission_id]
    assert discard_payload["active_player_id"] == "player-a"
    assert discard_payload["command_point_reward_eligible"] is False
    assert discard_payload["command_point_reward_reason"] == "not_discarding_players_turn"
    assert discard_payload["command_point_gain"] is None


def test_local_session_exposes_held_mission_action_and_decline_continues_shooting() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    session = LocalGameSession(lifecycle=lifecycle)

    waiting = session.advance_until_decision_or_terminal()

    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    assert request.payload == {
        "game_id": state.game_id,
        "player_id": "player-a",
        "battle_round": 1,
        "phase": BattlePhase.SHOOTING.value,
        "mission_action_opportunity": True,
        "legal_mission_action_ids": ["cleanse-objective"],
        "legal_action_option_ids": [
            (
                "start:cleanse-objective:army-alpha:intercessor-unit-1:"
                "take-and-hold-vs-purge-the-foe-layout-3-center-central"
            )
        ],
        "legal_option_ids": [
            DECLINE_MISSION_ACTION_START_OPTION_ID,
            (
                "start:cleanse-objective:army-alpha:intercessor-unit-1:"
                "take-and-hold-vs-purge-the-foe-layout-3-center-central"
            ),
        ],
    }
    assert DECLINE_MISSION_ACTION_START_OPTION_ID in {
        option.option_id for option in request.options
    }
    actor_view = session.view(viewer_player_id="player-a")
    pending_view = cast(dict[str, JsonValue], actor_view["pending_decision"])
    assert pending_view["decision_type"] == START_MISSION_ACTION_DECISION_TYPE
    assert [
        cast(dict[str, JsonValue], option)["option_id"]
        for option in cast(list[JsonValue], pending_view["options"])
    ] == [option.option_id for option in request.options]

    action_session = session.fork()
    action_option = next(
        option
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    )
    action_session.submit_option(
        request_id=request.request_id,
        option_id=action_option.option_id,
        result_id="phase11e-local-session-start-cleanse",
    )
    action_state = action_session.lifecycle.state
    assert action_state is not None
    started = action_state.mission_action_state_by_id(
        "mission-action:phase11e-local-session-start-cleanse"
    )
    assert started.unit_instance_id == "army-alpha:intercessor-unit-1"
    assert not any(
        event.event_type == "shooting_unit_selected"
        and cast(dict[str, JsonValue], event.payload).get("unit_instance_id")
        == started.unit_instance_id
        for event in action_session.lifecycle.decision_controller.event_log.records
    )

    shooting_status = session.submit_option(
        request_id=request.request_id,
        option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
        result_id="phase11e-decline-mission-action",
    )

    shooting_request = shooting_status.decision_request
    assert shooting_request is not None
    assert shooting_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.mission_action_opportunity_declined is True
    round_tripped = GameLifecycle.from_payload(session.lifecycle.to_payload())
    assert round_tripped.state is not None
    assert round_tripped.state.shooting_phase_state is not None
    assert round_tripped.state.shooting_phase_state.mission_action_opportunity_declined is True


def test_started_action_excludes_that_unit_from_shooting() -> None:
    config = _config_with_player_a_vehicle()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    infantry_id = "army-alpha:intercessor-unit-1"
    vehicle_id = "army-alpha:vehicle-unit-2"
    for unit_id in (infantry_id, vehicle_id):
        _place_unit_near_objective(
            state,
            unit_instance_id=unit_id,
            target_suffix="center",
        )
    session = LocalGameSession(lifecycle=lifecycle)
    initial_status = session.advance_until_decision_or_terminal()
    initial_request = initial_status.decision_request
    assert initial_request is not None
    cleanse_option = next(
        option
        for option in initial_request.options
        if option.option_id.startswith(f"start:cleanse-objective:{infantry_id}:")
    )

    shooting_status = session.submit_option(
        request_id=initial_request.request_id,
        option_id=cleanse_option.option_id,
        result_id="phase11e-start-cleanse-before-shooting",
    )

    shooting_request = shooting_status.decision_request
    assert shooting_request is not None
    assert shooting_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert infantry_id not in {option.option_id for option in shooting_request.options}
    assert vehicle_id in {option.option_id for option in shooting_request.options}


@pytest.mark.parametrize(
    ("restriction", "expected_reason"),
    [
        pytest.param("aircraft", "mission_action_unit_aircraft", id="aircraft"),
        pytest.param("fortification", "mission_action_unit_fortification", id="fortification"),
        pytest.param(
            "objective_control_zero",
            "mission_action_unit_zero_objective_control",
            id="objective-control-zero",
        ),
        pytest.param(
            "objective_control_dash",
            "mission_action_unit_zero_objective_control",
            id="objective-control-dash",
        ),
        pytest.param("engaged", "mission_action_unit_engaged", id="engaged"),
        pytest.param("advanced", "mission_action_unit_advanced", id="advanced"),
        pytest.param("fell_back", "mission_action_unit_fell_back", id="fell-back"),
    ],
)
def test_mission_action_opportunity_enforces_each_core_action_restriction(
    restriction: str,
    expected_reason: str,
) -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_id,
        target_suffix="center",
    )
    if restriction == "aircraft":
        _replace_unit(
            state,
            unit_instance_id=unit_id,
            keywords=("Infantry", "Battleline", "Aircraft"),
        )
    elif restriction == "fortification":
        _replace_unit(
            state,
            unit_instance_id=unit_id,
            keywords=("Infantry", "Battleline", "Fortification"),
        )
    elif restriction == "objective_control_zero":
        _replace_unit_objective_control(
            state,
            unit_instance_id=unit_id,
            objective_control=0,
        )
    elif restriction == "objective_control_dash":
        _replace_unit_objective_control(
            state,
            unit_instance_id=unit_id,
            objective_control="-",
        )
    elif restriction == "engaged":
        assert state.mission_setup is not None
        center = next(
            marker
            for marker in state.mission_setup.objective_markers
            if _objective_marker_matches_suffix(marker.objective_marker_id, "center")
        )
        _place_unit_near_point(
            state,
            unit_instance_id="army-beta:intercessor-unit-3",
            x_inches=center.x_inches + 2.5,
            y_inches=center.y_inches,
        )
    elif restriction == "advanced":
        state.record_advanced_unit_state(_advanced_unit_state(unit_instance_id=unit_id))
    elif restriction == "fell_back":
        state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id="player-a",
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
        )
    else:
        raise AssertionError("unsupported Action restriction fixture")

    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="player-a",
            unit_instance_id=unit_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        == expected_reason
    )
    waiting = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()

    assert (
        waiting.decision_request is None
        or waiting.decision_request.decision_type != START_MISSION_ACTION_DECISION_TYPE
    )


def test_titanic_unit_can_start_action_while_engaged() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _replace_unit(
        state,
        unit_instance_id=unit_id,
        keywords=("Infantry", "Battleline", "Titanic"),
    )
    _place_unit_near_objective(state, unit_instance_id=unit_id, target_suffix="center")
    center = next(
        marker
        for marker in state.mission_setup.objective_markers
        if _objective_marker_matches_suffix(marker.objective_marker_id, "center")
    )
    _place_unit_near_point(
        state,
        unit_instance_id="army-beta:intercessor-unit-3",
        x_inches=center.x_inches + 2.5,
        y_inches=center.y_inches,
    )

    request = (
        LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal().decision_request
    )

    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    assert any(
        option.option_id.startswith(f"start:cleanse-objective:{unit_id}:")
        for option in request.options
    )


def test_titanic_action_unit_remains_eligible_to_shoot() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _replace_unit(
        state,
        unit_instance_id=unit_id,
        keywords=("Infantry", "Battleline", "Titanic"),
    )
    _place_unit_near_objective(state, unit_instance_id=unit_id, target_suffix="center")
    session = LocalGameSession(lifecycle=lifecycle)
    initial_request = session.advance_until_decision_or_terminal().decision_request
    assert initial_request is not None
    action_option = next(
        option
        for option in initial_request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    )

    shooting_status = session.submit_option(
        request_id=initial_request.request_id,
        option_id=action_option.option_id,
        result_id="phase11e-titanic-start-action",
    )

    shooting_request = shooting_status.decision_request
    assert shooting_request is not None
    assert shooting_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert unit_id in {option.option_id for option in shooting_request.options}


def test_attached_rules_unit_has_one_canonical_action_option_and_state_identity() -> None:
    config = _config_with_player_a_attached_unit()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    for component_id in (bodyguard_id, leader_id):
        _place_unit_near_objective(
            state,
            unit_instance_id=component_id,
            target_suffix="center",
        )
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request

    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    action_options = tuple(
        option
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    )
    assert len(action_options) == 1
    payload = cast(dict[str, JsonValue], action_options[0].payload)
    assert payload["unit_instance_id"] == attached_id
    assert payload["eligible_unit_instance_ids"] == [attached_id]

    session.submit_option(
        request_id=request.request_id,
        option_id=action_options[0].option_id,
        result_id="phase11e-attached-start-cleanse",
    )

    action_state = state.mission_action_state_by_id(
        "mission-action:phase11e-attached-start-cleanse"
    )
    assert action_state.unit_instance_id == attached_id
    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="player-a",
            unit_instance_id=leader_id,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        == MISSION_ACTION_UNIT_ALREADY_STARTED_ACTION
    )


def test_attached_rules_unit_canonical_shot_state_blocks_all_component_action_options() -> None:
    config = _config_with_player_a_attached_unit()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    for component_id in ("army-alpha:bodyguard-unit", "army-alpha:leader-unit"):
        _place_unit_near_objective(
            state,
            unit_instance_id=component_id,
            target_suffix="center",
        )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(attached_id,),
        shot_unit_ids=(attached_id,),
    )

    waiting = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()

    assert (
        waiting.decision_request is None
        or waiting.decision_request.decision_type != START_MISSION_ACTION_DECISION_TYPE
    )


def test_attached_action_history_survives_split_payload_round_trip_and_terminal_replay() -> None:
    config = _config_with_player_a_attached_unit(include_independent_unit=True)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    bodyguard_id = "army-alpha:bodyguard-unit"
    leader_id = "army-alpha:leader-unit"
    independent_id = "army-alpha:intercessor-unit-2"
    enemy_id = "army-beta:intercessor-unit-3"
    for unit_id, x_inches, y_inches in (
        (leader_id, 20.0, 20.0),
        (independent_id, 20.0, 30.0),
        (enemy_id, 27.0, 25.0),
    ):
        _place_unit_near_point(
            state,
            unit_instance_id=unit_id,
            x_inches=x_inches,
            y_inches=y_inches,
        )
    action = _attached_cleanse_action(state=state, action_id="phase11e-attached-before-split")
    state.record_mission_action_state(action)
    bodyguard_model_ids = state.army_definitions[0].unit_by_id(bodyguard_id).own_model_ids()
    state.battlefield_state = state.battlefield_state.with_removed_models(bodyguard_model_ids)
    source_session = LocalGameSession(lifecycle=lifecycle)
    event_cursor = EventStreamCursor(source_session.event_record_count())

    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-a",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(leader_id,),
        event_log=lifecycle.decision_controller.event_log,
    )

    interrupted = state.mission_action_state_by_id(action.action_id)
    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert interrupted.interrupted_reason == "unit_destroyed"
    assert rules_unit_started_mission_action_this_turn(
        state=state,
        player_id="player-a",
        unit_instance_id=leader_id,
    )
    for viewer_player_id in ("player-a", "player-b"):
        event_delta = source_session.events_since(
            event_cursor,
            viewer_player_id=viewer_player_id,
        )
        assert len(event_delta["events"]) == 1
        interruption_event = event_delta["events"][0]
        assert interruption_event["event_type"] == "mission_action_interrupted"
        event_payload = cast(dict[str, JsonValue], interruption_event["payload"])
        assert event_payload["action_id"] == action.action_id
        assert event_payload["unit_instance_id"] == attached_id
        assert event_payload["surviving_unit_instance_ids"] == [leader_id]
        assert event_payload["interrupted_reason"] == "unit_destroyed"
        assert event_payload["battle_round"] == state.battle_round
        assert event_payload["phase"] == BattlePhase.COMMAND.value

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    lifecycle_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    round_tripped = GameLifecycle.from_payload(lifecycle_payload)
    round_tripped_state = round_tripped.state
    assert round_tripped_state is not None
    assert rules_unit_started_mission_action_this_turn(
        state=round_tripped_state,
        player_id="player-a",
        unit_instance_id=leader_id,
    )
    session = LocalGameSession(lifecycle=round_tripped)

    charge_request = session.advance_until_decision_or_terminal().decision_request

    assert charge_request is not None
    assert charge_request.decision_type == "select_charging_unit"
    charge_option_ids = {option.option_id for option in charge_request.options}
    assert leader_id not in charge_option_ids
    assert independent_id in charge_option_ids
    session.submit_option(
        request_id=charge_request.request_id,
        option_id="complete_charge_phase",
        result_id="phase11e-complete-charge-after-attached-split",
    )
    replay_result = ReplayRunner.from_payload(
        session.replay_artifact(artifact_id="phase11e-attached-split-action-history")
    ).run()
    assert replay_result.status is ReplayRunStatus.REPRODUCED

    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.advance_to_next_battle_phase()
    assert state.stage is GameLifecycleStage.COMPLETE
    terminal_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    terminal_lifecycle = GameLifecycle.from_payload(terminal_payload)
    assert terminal_lifecycle.state is not None
    assert terminal_lifecycle.state.stage is GameLifecycleStage.COMPLETE
    terminal_session = LocalGameSession(lifecycle=terminal_lifecycle)
    terminal_artifact = ReplayArtifact.from_payload(
        terminal_session.replay_artifact(
            artifact_id="phase11e-terminal-attached-split-action-history"
        )
    )
    replay_snapshot = GameLifecycle.from_payload(terminal_artifact.initial_lifecycle_payload)
    replay_events = tuple(
        event
        for event in replay_snapshot.decision_controller.event_log.records
        if event.event_type == "mission_action_interrupted"
    )
    assert len(replay_events) == 1
    assert cast(dict[str, JsonValue], replay_events[0].payload)["action_id"] == action.action_id
    terminal_replay_result = ReplayRunner(terminal_artifact).run()
    assert terminal_replay_result.status is ReplayRunStatus.REPRODUCED
    assert terminal_replay_result.reproduced_event_count == 4


def test_attached_action_cannot_complete_after_component_fails_battle_shock() -> None:
    config = _config_with_player_a_attached_unit()
    state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attached_id = "attached-unit:army-alpha:bodyguard-unit"
    bodyguard_id = "army-alpha:bodyguard-unit"
    for component_id in (bodyguard_id, "army-alpha:leader-unit"):
        _place_unit_near_objective(
            state,
            unit_instance_id=component_id,
            target_suffix="center",
        )
    action = _attached_cleanse_action(
        state=state,
        action_id="phase11e-attached-battle-shocked",
    )
    state.record_mission_action_state(action)
    bodyguard = state.army_definitions[0].unit_by_id(bodyguard_id)
    starting_strength = StartingStrengthRecord.from_unit(
        player_id="player-a",
        unit=bodyguard,
    )
    request = BattleShockTestRequest.for_unit(
        request_id="phase11e-attached-component-battle-shock",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id="player-a",
        unit_instance_id=bodyguard_id,
        reason=BattleShockTestReason.BELOW_HALF_STRENGTH,
        leadership_target=6,
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id="player-a",
            unit=bodyguard,
            starting_strength=starting_strength,
            current_model_ids=bodyguard.own_model_ids(),
        ),
    )
    state.record_battle_shock_result(
        BattleShockResult.from_roll_state(
            result_id="phase11e-attached-component-battle-shock-result",
            request=request,
            roll_state=DiceRollManager("phase11e-attached-battle-shock").roll_fixed(
                request.spec,
                [1, 1],
            ),
        )
    )

    assert state.battle_shocked_unit_ids == [bodyguard_id]
    assert rules_unit_is_battle_shocked(state=state, unit_instance_id=attached_id)
    with pytest.raises(GameLifecycleError, match="cannot complete actions"):
        state.complete_mission_action(
            action_id=action.action_id,
            completion_phase=BattlePhase.FIGHT,
        )
    assert state.mission_action_state_by_id(action.action_id).status is MissionActionStatus.STARTED


@pytest.mark.parametrize(
    ("base_objective_control", "modified_objective_control", "expected_reason", "expects_action"),
    [
        pytest.param(
            2,
            0,
            "mission_action_unit_zero_objective_control",
            False,
            id="runtime-reduction-to-zero",
        ),
        pytest.param(0, 1, None, True, id="runtime-increase-from-zero"),
    ],
)
def test_mission_action_eligibility_uses_runtime_modified_objective_control(
    base_objective_control: int,
    modified_objective_control: int,
    expected_reason: str | None,
    expects_action: bool,
) -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _replace_unit_objective_control(
        state,
        unit_instance_id=unit_id,
        objective_control=base_objective_control,
    )
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_id,
        target_suffix="center",
    )
    modified_contexts: list[ObjectiveControlModifierContext] = []

    def modify_objective_control(context: ObjectiveControlModifierContext) -> int:
        if context.unit_instance_id != unit_id:
            return context.current_objective_control
        modified_contexts.append(context)
        return modified_objective_control

    registry = RuntimeModifierRegistry.from_bindings(
        objective_control_modifier_bindings=(
            ObjectiveControlModifierBinding(
                modifier_id="phase11e:mission-action-objective-control",
                source_id="phase11e:mission-action-objective-control-source",
                handler=modify_objective_control,
            ),
        )
    )

    assert (
        mission_action_unit_ineligibility_reason(
            state=state,
            player_id="player-a",
            unit_instance_id=unit_id,
            runtime_modifier_registry=registry,
        )
        == expected_reason
    )
    runtime_config = lifecycle.config
    status = ShootingPhaseHandler(
        ruleset_descriptor=runtime_config.ruleset_descriptor,
        army_catalog=runtime_config.army_catalog,
        runtime_modifier_registry=registry,
    ).begin_phase(
        state=state,
        decisions=DecisionController(),
    )

    request = status.decision_request
    action_requested = (
        request is not None and request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    )
    assert action_requested is expects_action
    assert modified_contexts
    assert {context.unit_instance_id for context in modified_contexts} == {unit_id}


def test_cli_and_projection_expose_unique_human_action_option_labels() -> None:
    config = _config_with_two_player_a_infantry_units()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    for unit_id in ("army-alpha:intercessor-unit-1", "army-alpha:intercessor-unit-2"):
        _place_unit_near_objective(state, unit_instance_id=unit_id, target_suffix="center")
    session = LocalGameSession(lifecycle=lifecycle)
    request = session.advance_until_decision_or_terminal().decision_request
    assert request is not None
    action_options = tuple(
        option
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    )

    labels = tuple(option.label for option in action_options)
    assert len(labels) == len(set(labels))
    assert all("Cleanse" in label for label in labels)
    assert all("CORE Intercessor-like Infantry" in label for label in labels)
    assert all("Central Objective" in label for label in labels)

    actor_view = session.view(viewer_player_id="player-a")
    pending_view = cast(dict[str, JsonValue], actor_view["pending_decision"])
    projected_options = tuple(
        cast(dict[str, JsonValue], option)
        for option in cast(list[JsonValue], pending_view["options"])
        if cast(dict[str, JsonValue], option)["option_id"] != DECLINE_MISSION_ACTION_START_OPTION_ID
    )
    projected_labels = tuple(cast(str, option["label"]) for option in projected_options)
    cli_prompt = render_pending_decision_for_cli(
        session=session,
        viewer_player_id="player-a",
    )
    cli_labels = tuple(
        option["label"]
        for option in cli_prompt["options"]
        if option["option_id"] != DECLINE_MISSION_ACTION_START_OPTION_ID
    )
    assert projected_labels == labels
    assert cli_labels == labels
    assert len(cli_labels) == len(set(cli_labels))


def test_shooting_lifecycle_offers_action_even_without_a_legal_shooting_attack() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        "army-beta:intercessor-unit-3"
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    session = LocalGameSession(lifecycle=lifecycle)

    waiting = session.advance_until_decision_or_terminal()

    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    assert any(
        option.option_id.startswith("start:cleanse-objective:") for option in request.options
    )


def test_shooting_lifecycle_filters_mission_actions_by_primary_and_secondary_ownership() -> None:
    unheld_lifecycle = _battle_lifecycle()
    unheld_state = unheld_lifecycle.state
    assert unheld_state is not None
    unheld_state.battle_phase_index = unheld_state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_objective(
        unheld_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    unheld_status = LocalGameSession(
        lifecycle=unheld_lifecycle
    ).advance_until_decision_or_terminal()
    direct_unheld_status = request_mission_action_start(
        state=unheld_state,
        decisions=GameLifecycle().decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert unheld_status.decision_request is not None
    assert unheld_status.decision_request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE
    assert direct_unheld_status.status_kind is LifecycleStatusKind.UNSUPPORTED

    cleanse_lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )
    cleanse_state = cleanse_lifecycle.state
    assert cleanse_state is not None
    cleanse_state.battle_phase_index = cleanse_state.battle_phase_sequence.index(
        BattlePhase.SHOOTING
    )
    _place_unit_near_objective(
        cleanse_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    cleanse_status = LocalGameSession(
        lifecycle=cleanse_lifecycle
    ).advance_until_decision_or_terminal()

    cleanse_request = cleanse_status.decision_request
    assert cleanse_request is not None
    assert cleanse_request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    assert cast(dict[str, JsonValue], cleanse_request.payload)["legal_mission_action_ids"] == [
        "cleanse-objective"
    ]

    death_trap_lifecycle = _battle_lifecycle_for_primary(
        "primary-death-trap",
        objective_terrain_feature_id=SCORING_TERRAIN_FEATURE_ID,
    )
    death_trap_state = death_trap_lifecycle.state
    assert death_trap_state is not None
    death_trap_state.battle_phase_index = death_trap_state.battle_phase_sequence.index(
        BattlePhase.SHOOTING
    )
    assert death_trap_state.mission_setup is not None
    death_trap_area = _objective_logical_terrain_area(
        death_trap_state.mission_setup,
        objective_role=ObjectiveMarkerRole.CENTRAL,
    )
    _place_unit_near_point(
        death_trap_state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=_logical_terrain_area_test_point(death_trap_area)[0],
        y_inches=_logical_terrain_area_test_point(death_trap_area)[1],
    )

    death_trap_status = LocalGameSession(
        lifecycle=death_trap_lifecycle
    ).advance_until_decision_or_terminal()

    death_trap_request = death_trap_status.decision_request
    assert death_trap_request is not None
    assert death_trap_request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    assert cast(dict[str, JsonValue], death_trap_request.payload)["legal_mission_action_ids"] == [
        "booby-trap-terrain"
    ]


def test_shooting_lifecycle_exposes_held_tactical_plunder() -> None:
    lifecycle = _battle_lifecycle(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        mission_setup=_event_companion_mission_setup_with_scoring_terrain_feature(),
    )
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    _record_active_tactical_secondary(state, secondary_mission_id="plunder")
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    terrain_area = _first_plunderable_logical_terrain_area(
        state,
        player_id="player-a",
    )
    target_member = terrain_area.members[0]
    target_point = target_member.footprint_polygon[0]
    _place_unit_near_point(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=target_point.x_inches,
        y_inches=target_point.y_inches,
    )

    waiting = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()

    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    assert cast(dict[str, JsonValue], request.payload)["legal_mission_action_ids"] == [
        "plunder-terrain"
    ]


def test_mission_action_can_complete_interrupt_and_score() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    completed_action = _start_mission_action_via_lifecycle(
        lifecycle=lifecycle,
        target_suffix="center",
        result_id="phase11e-start-cleanse-center",
    )
    interrupted_action = _mission_action_state(
        action_id="mission-action:phase11e-start-cleanse-northwest",
        target_id="take-and-hold-vs-purge-the-foe-layout-3-upper-central",
    )
    state.record_mission_action_state(interrupted_action)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )

    completed = state.complete_mission_action(
        action_id=completed_action.action_id,
        completion_phase=BattlePhase.FIGHT,
    )
    interrupted = state.interrupt_mission_action(
        action_id=interrupted_action.action_id,
        reason="unit_moved",
    )

    assert completed.status is MissionActionStatus.COMPLETED
    assert completed.score_transaction_id is None
    assert _objective_marker_matches_suffix(completed.target_id, "center")
    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert _objective_marker_matches_suffix(interrupted.target_id, "northwest")
    assert interrupted.interrupted_reason == "unit_moved"
    assert state.victory_point_total("player-a") == 0
    assert [
        cleanse.objective_marker_id for cleanse in state.secondary_objective_cleanse_states
    ] == [completed.target_id]
    assert lifecycle.decision_controller.records[-1].request.decision_type == (
        START_MISSION_ACTION_DECISION_TYPE
    )
    opponent_events = EventStreamCursor().events_since(
        lifecycle.decision_controller.event_log,
        viewer_player_id="player-b",
    )
    action_events = [
        event
        for event in opponent_events["events"]
        if event["event_type"] == "mission_action_started"
    ]
    assert len(action_events) == 1
    assert cast(dict[str, JsonValue], action_events[0]["payload"])["mission_action_id"] == (
        "cleanse-objective"
    )
    round_tripped = GameLifecycle.from_payload(lifecycle.to_payload())
    round_tripped_state = round_tripped.state
    assert round_tripped_state is not None
    assert (
        round_tripped_state.mission_action_state_by_id(completed.action_id).target_id
        == completed.target_id
    )


def test_plunder_mission_action_completes_immediately_and_records_secondary_evidence() -> None:
    lifecycle = _battle_lifecycle(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        mission_setup=_event_companion_mission_setup_with_scoring_terrain_feature(),
    )
    state = lifecycle.state
    assert state is not None
    assert state.mission_setup is not None
    _record_active_tactical_secondary(state, secondary_mission_id="plunder")
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    terrain_area = _first_plunderable_logical_terrain_area(state, player_id="player-a")
    target_member = terrain_area.members[0]
    target_point = target_member.footprint_polygon[0]
    _place_unit_near_point(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=target_point.x_inches,
        y_inches=target_point.y_inches,
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="plunder-terrain",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["target_id"]
        == terrain_area.logical_terrain_area_id
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id="phase16-start-plunder",
    ).to_result(request)

    lifecycle.submit_decision(result)

    action = state.mission_action_state_by_id("mission-action:phase16-start-plunder")
    assert action.status is MissionActionStatus.COMPLETED
    assert action.score_transaction_id is None
    assert state.victory_point_total("player-a") == 0
    assert [plunder.terrain_feature_id for plunder in state.secondary_terrain_plunder_states] == [
        terrain_area.logical_terrain_area_id
    ]
    assert (
        request_mission_action_start(
            state=state,
            decisions=lifecycle.decision_controller,
            player_id="player-a",
            mission_action_id="plunder-terrain",
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        ).status_kind
        is LifecycleStatusKind.UNSUPPORTED
    )
    assert any(
        record.event_type == "secondary_terrain_area_plundered"
        for record in lifecycle.decision_controller.event_log.records
    )


def test_plunder_excludes_terrain_area_in_player_territory_outside_deployment_zone() -> None:
    mission_setup = _event_companion_mission_setup_with_scoring_terrain_feature()
    territory_area = next(
        area
        for area in mission_logical_terrain_areas(mission_setup)
        if len(area.members) > 1
        and logical_terrain_area_within_player_territory(
            area,
            mission_setup=mission_setup,
            player_id="player-a",
        )
        and not logical_terrain_area_within_player_deployment_zone(
            area,
            mission_setup=mission_setup,
            player_id="player-a",
        )
    )
    lifecycle = _battle_lifecycle(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        mission_setup=mission_setup,
    )
    state = lifecycle.state
    assert state is not None
    _record_active_tactical_secondary(state, secondary_mission_id="plunder")
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    target_member = territory_area.members[0]
    target_point = target_member.footprint_polygon[0]
    _place_unit_near_point(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        x_inches=target_point.x_inches,
        y_inches=target_point.y_inches,
    )

    status = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="plunder-terrain",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert status.status_kind is LifecycleStatusKind.UNSUPPORTED


def test_logical_terrain_area_exclusions_require_every_physical_member() -> None:
    mission_setup = _event_companion_mission_setup_with_scoring_terrain_feature()
    area = next(
        area for area in mission_logical_terrain_areas(mission_setup) if len(area.members) > 1
    )
    first_member = area.members[0]
    first_member_shape = DeploymentZoneShape(
        polygons=(
            DeploymentZonePolygon(
                vertices=tuple(
                    DeploymentZonePoint(x=point.x_inches, y=point.y_inches)
                    for point in first_member.footprint_polygon
                )
            ),
        )
    )
    attacker_territory = next(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == "attacker"
    )
    partial_setup = replace(
        mission_setup,
        deployment_zones=tuple(
            replace(zone, shape=first_member_shape) if zone.player_id == "player-a" else zone
            for zone in mission_setup.deployment_zones
        ),
        battlefield_regions=tuple(
            replace(region, shape=first_member_shape)
            if region.region_id == attacker_territory.region_id
            else region
            for region in mission_setup.battlefield_regions
        ),
    )

    assert shapely_backend.deployment_zone_shapes_cover_polygon(
        shapes=(first_member_shape,),
        polygon=tuple((point.x_inches, point.y_inches) for point in first_member.footprint_polygon),
    )
    assert not logical_terrain_area_within_player_deployment_zone(
        area,
        mission_setup=partial_setup,
        player_id="player-a",
    )
    assert not logical_terrain_area_within_player_territory(
        area,
        mission_setup=partial_setup,
        player_id="player-a",
    )


def test_plunder_territory_containment_rejects_footprint_crossing_cutout() -> None:
    mission_setup = _event_companion_mission_setup_with_scoring_terrain_feature()
    area = next(
        area for area in mission_logical_terrain_areas(mission_setup) if len(area.members) == 1
    )
    territory = next(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == "attacker"
    )
    min_x, min_y, max_x, max_y = area.bounds()
    member_polygon = area.members[0].footprint_polygon
    cutout_x = sum(point.x_inches for point in member_polygon) / len(member_polygon)
    cutout_y = sum(point.y_inches for point in member_polygon) / len(member_polygon)
    shape = DeploymentZoneShape(
        polygons=DeploymentZoneShape.rectangle(
            min_x=max(0.0, min_x - 1.0),
            min_y=max(0.0, min_y - 1.0),
            max_x=min(mission_setup.battlefield_width_inches, max_x + 1.0),
            max_y=min(mission_setup.battlefield_depth_inches, max_y + 1.0),
        ).polygons,
        cutouts=(
            DeploymentZoneCircleCutout(
                center_x=cutout_x,
                center_y=cutout_y,
                radius=0.5,
            ),
        ),
    )
    mission_setup = replace(
        mission_setup,
        battlefield_regions=tuple(
            replace(region, shape=shape) if region.region_id == territory.region_id else region
            for region in mission_setup.battlefield_regions
        ),
    )
    assert all(
        shape.contains_point(x, y)
        for x, y in (
            (min_x, min_y),
            (min_x, max_y),
            (max_x, min_y),
            (max_x, max_y),
        )
    )
    assert not logical_terrain_area_within_player_territory(
        area,
        mission_setup=mission_setup,
        player_id="player-a",
    )


def test_plunder_territory_containment_rejects_footprint_crossing_polygon_gap() -> None:
    mission_setup = _event_companion_mission_setup_with_scoring_terrain_feature()
    area = next(
        area for area in mission_logical_terrain_areas(mission_setup) if len(area.members) == 1
    )
    territory = next(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == "attacker"
    )
    min_x, min_y, max_x, max_y = area.bounds()
    middle_x = (min_x + max_x) / 2.0
    left = DeploymentZoneShape.rectangle(
        min_x=max(0.0, min_x - 1.0),
        min_y=max(0.0, min_y - 1.0),
        max_x=middle_x - 0.1,
        max_y=min(mission_setup.battlefield_depth_inches, max_y + 1.0),
    )
    right = DeploymentZoneShape.rectangle(
        min_x=middle_x + 0.1,
        min_y=max(0.0, min_y - 1.0),
        max_x=min(mission_setup.battlefield_width_inches, max_x + 1.0),
        max_y=min(mission_setup.battlefield_depth_inches, max_y + 1.0),
    )
    shape = DeploymentZoneShape(polygons=(*left.polygons, *right.polygons))
    mission_setup = replace(
        mission_setup,
        battlefield_regions=tuple(
            replace(region, shape=shape) if region.region_id == territory.region_id else region
            for region in mission_setup.battlefield_regions
        ),
    )
    assert all(
        shape.contains_point(x, y)
        for x, y in (
            (min_x, min_y),
            (min_x, max_y),
            (max_x, min_y),
            (max_x, max_y),
        )
    )
    assert not logical_terrain_area_within_player_territory(
        area,
        mission_setup=mission_setup,
        player_id="player-a",
    )


def test_terrain_area_membership_queries_fail_fast_on_missing_source_context() -> None:
    mission_setup = _event_companion_mission_setup_with_scoring_terrain_feature()
    area = next(
        area
        for area in mission_logical_terrain_areas(mission_setup)
        if logical_terrain_area_within_player_territory(
            area,
            mission_setup=mission_setup,
            player_id="player-b",
        )
    )

    assert logical_terrain_area_within_player_territory(
        area,
        mission_setup=mission_setup,
        player_id="player-b",
    )
    with pytest.raises(GameLifecycleError, match="requires MissionLogicalTerrainArea"):
        logical_terrain_area_within_player_deployment_zone(
            cast(MissionLogicalTerrainArea, object()),
            mission_setup=mission_setup,
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="requires MissionSetup"):
        logical_terrain_area_within_player_territory(
            area,
            mission_setup=cast(MissionSetup, object()),
            player_id="player-a",
        )
    with pytest.raises(GameLifecycleError, match="requires player zone"):
        logical_terrain_area_within_player_deployment_zone(
            area,
            mission_setup=mission_setup,
            player_id="player-without-zone",
        )
    with pytest.raises(GameLifecycleError, match="has no mission role"):
        logical_terrain_area_within_player_territory(
            area,
            mission_setup=mission_setup,
            player_id="player-without-role",
        )
    setup_without_territories = replace(
        mission_setup,
        battlefield_regions=tuple(
            region
            for region in mission_setup.battlefield_regions
            if region.region_kind is not BattlefieldRegionKind.TERRITORY
        ),
    )
    with pytest.raises(GameLifecycleError, match="requires one player territory"):
        logical_terrain_area_within_player_territory(
            area,
            mission_setup=setup_without_territories,
            player_id="player-a",
        )


def test_public_payload_redacts_hidden_secondary_scoring_evidence() -> None:
    state = _battle_state_from_config(
        replace(
            _config_with_player_b_vehicles(("vehicle-unit-3",)),
            mission_setup=_event_companion_mission_setup_with_scoring_terrain_feature(),
        )
    )
    state.secondary_mission_choices = [
        choice for choice in state.secondary_mission_choices if choice.player_id == "player-a"
    ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    _record_secondary_vehicle_destruction(state, "army-beta:vehicle-unit-3")
    assert state.mission_setup is not None
    cleanse_target_id = _center_marker_definition_for_setup(state.mission_setup).objective_marker_id
    cleanse_action_id = "phase16-public-cleanse"
    cleanse_source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="cleanse-objective",
        action_id=cleanse_action_id,
        target_id=cleanse_target_id,
    )
    state.record_secondary_objective_cleanse(
        player_id="player-a",
        objective_marker_id=cleanse_target_id,
        action_id=cleanse_action_id,
        phase=BattlePhase.FIGHT,
        source_id=cleanse_source_id,
    )
    terrain_area = _first_plunderable_logical_terrain_area(state, player_id="player-a")
    plunder_action_id = "phase16-public-plunder"
    plunder_source_id = _record_completed_zero_vp_mission_action(
        state,
        mission_action_id="plunder-terrain",
        action_id=plunder_action_id,
        target_id=terrain_area.logical_terrain_area_id,
    )
    state.record_secondary_terrain_plunder(
        player_id="player-a",
        terrain_feature_id=terrain_area.logical_terrain_area_id,
        action_id=plunder_action_id,
        phase=BattlePhase.SHOOTING,
        source_id=plunder_source_id,
    )

    player_payload = state.to_public_payload(viewer_player_id="player-a")
    opponent_payload = state.to_public_payload(viewer_player_id="player-b")

    assert len(cast(list[JsonValue], player_payload["secondary_unit_destruction_states"])) == 1
    assert len(cast(list[JsonValue], player_payload["secondary_objective_cleanse_states"])) == 1
    assert len(cast(list[JsonValue], player_payload["secondary_terrain_plunder_states"])) == 1
    assert opponent_payload["secondary_unit_destruction_states"] == []
    assert opponent_payload["secondary_objective_cleanse_states"] == []
    assert opponent_payload["secondary_terrain_plunder_states"] == []


def test_mission_action_cancellation_maps_displacements_and_battlefield_departure() -> None:
    action = replace(
        _mission_action_state(action_id="phase14d-cancel-action"),
        interruption_conditions=("unit_moved", "unit_left_battlefield"),
    )

    interrupted_by_move = interrupt_mission_action_for_displacement(
        action,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    pile_in_result = interrupt_mission_action_for_displacement(
        action,
        displacement_kind=ModelDisplacementKind.PILE_IN,
    )
    consolidate_result = interrupt_mission_action_for_displacement(
        action,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )
    interrupted_by_departure = interrupt_mission_action_for_battlefield_departure(action)

    assert (
        mission_action_interruption_reason_for_displacement(ModelDisplacementKind.ADVANCE)
        == "unit_moved"
    )
    assert (
        mission_action_interruption_reason_for_displacement(ModelDisplacementKind.PILE_IN) is None
    )
    assert interrupted_by_move is not None
    assert interrupted_by_move.status is MissionActionStatus.INTERRUPTED
    assert interrupted_by_move.interrupted_reason == "unit_moved"
    assert pile_in_result is None
    assert consolidate_result is None
    assert interrupted_by_departure.status is MissionActionStatus.INTERRUPTED
    assert interrupted_by_departure.interrupted_reason == "unit_left_battlefield"

    with pytest.raises(GameLifecycleError, match="interruption reason is not configured"):
        interrupt_mission_action_for_battlefield_departure(
            _mission_action_state(action_id="phase14d-unconfigured-departure")
        )


def test_started_mission_action_is_interrupted_by_runtime_normal_move() -> None:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    action = replace(
        _mission_action_state(action_id="phase14d-runtime-cancel-action"),
        interruption_conditions=("unit_moved", "unit_left_battlefield"),
    )
    state.record_mission_action_state(action)
    movement_status = lifecycle.advance_until_decision_or_terminal()
    movement_request = movement_status.decision_request
    assert movement_request is not None
    assert movement_request.decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    action_status = lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id="phase14d-runtime-cancel-select-unit",
            request=movement_request,
            selected_option_id=action.unit_instance_id,
        )
    )
    action_request = action_status.decision_request
    assert action_request is not None
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE

    status = submit_action_and_movement_proposal(
        lifecycle,
        request=action_request,
        option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        action_result_id="phase14d-runtime-cancel-normal-move",
        proposal_result_id="phase14d-runtime-cancel-normal-move-proposal",
        unit_instance_id=action.unit_instance_id,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        movement_mode=MovementMode.NORMAL,
        witness=straight_line_witness_for_unit(
            lifecycle,
            unit_instance_id=action.unit_instance_id,
            dx=6.0,
        ),
    )
    _decline_stratagem_window_if_pending(
        lifecycle,
        status,
        result_id="phase14d-runtime-cancel-decline-stratagem",
    )
    interrupted = state.mission_action_state_by_id(action.action_id)
    interruption_event = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "mission_action_interrupted"
    )
    event_payload = cast(dict[str, JsonValue], interruption_event.payload)

    assert interrupted.status is MissionActionStatus.INTERRUPTED
    assert interrupted.interrupted_reason == "unit_moved"
    assert event_payload["interrupted_reason"] == "unit_moved"
    assert event_payload["unit_instance_id"] == action.unit_instance_id


def test_mission_action_terminal_state_validation_is_fail_fast() -> None:
    action = _mission_action_state(action_id="phase14d-terminal-validation")

    with pytest.raises(GameLifecycleError, match="Started mission Action must not have terminal"):
        replace(action, score_transaction_id="victory-point:player-a:round-01:000001")
    with pytest.raises(
        GameLifecycleError, match="Completed scoring mission Action requires transaction"
    ):
        replace(
            action,
            status=MissionActionStatus.COMPLETED,
            completed_battle_round=1,
            completed_phase=BattlePhase.FIGHT.value,
        )
    with pytest.raises(GameLifecycleError, match="Completed mission Action cannot be interrupted"):
        replace(
            action,
            status=MissionActionStatus.COMPLETED,
            completed_battle_round=1,
            completed_phase=BattlePhase.FIGHT.value,
            interrupted_reason="unit_moved",
            score_transaction_id="victory-point:player-a:round-01:000002",
        )
    with pytest.raises(GameLifecycleError, match="Interrupted mission Action requires a reason"):
        replace(action, status=MissionActionStatus.INTERRUPTED)
    with pytest.raises(
        GameLifecycleError,
        match="Interrupted mission Action cannot have completion fields",
    ):
        replace(
            action,
            status=MissionActionStatus.INTERRUPTED,
            completed_battle_round=1,
            interrupted_reason="unit_moved",
        )


def test_mission_action_interruption_helpers_reject_malformed_state() -> None:
    not_an_action = cast(MissionActionState, object())

    with pytest.raises(GameLifecycleError, match="action_state must be a MissionActionState"):
        interrupt_mission_action_for_displacement(
            not_an_action,
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        )
    with pytest.raises(GameLifecycleError, match="action_state must be a MissionActionState"):
        interrupt_mission_action_for_battlefield_departure(not_an_action)


def test_mission_action_start_rejects_drifted_lifecycle_option() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    waiting = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()
    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE
    option = next(
        candidate
        for candidate in request.options
        if candidate.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id="phase11e-drift-start-action",
    ).to_result(request)
    unit_id = cast(dict[str, JsonValue], option.payload)["unit_instance_id"]
    assert isinstance(unit_id, str)
    state.battlefield_state = state.battlefield_state.without_unit_placement(unit_id)

    status = lifecycle.submit_decision(result)

    assert status.status_kind.value == "invalid"
    assert not lifecycle.decision_controller.records
    assert lifecycle.decision_controller.queue.peek_next().request_id == request.request_id


def test_cleanse_mission_action_filters_ineligible_vehicle_units() -> None:
    lifecycle = _battle_lifecycle_with_player_a_vehicle()
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_suffix="center",
    )
    _place_unit_near_objective(
        state,
        unit_instance_id="army-alpha:vehicle-unit-2",
        target_suffix="center",
    )

    waiting = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()
    request = waiting.decision_request
    assert request is not None
    assert request.decision_type == START_MISSION_ACTION_DECISION_TYPE

    option_payloads = [
        cast(dict[str, JsonValue], option.payload)
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
    ]
    assert option_payloads
    assert {
        cast(str, option_payload["unit_instance_id"]) for option_payload in option_payloads
    } == {"army-alpha:intercessor-unit-1"}
    assert all(
        "army-alpha:vehicle-unit-2"
        not in cast(list[JsonValue], option_payload["eligible_unit_instance_ids"])
        for option_payload in option_payloads
    )


def test_mission_action_start_excludes_units_that_shot_this_shooting_phase() -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_id,
        target_suffix="center",
    )
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id="player-a",
        selected_unit_ids=(unit_id,),
        shot_unit_ids=(unit_id,),
    )

    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert waiting.status_kind.value == "unsupported"
    assert waiting.decision_request is None
    waiting_payload = cast(dict[str, JsonValue], waiting.payload)
    assert waiting_payload["mission_action_id"] == "cleanse-objective"


@pytest.mark.parametrize(
    "ineligible_state",
    [
        pytest.param("battle_shocked"),
        pytest.param("already_shot"),
        pytest.param("destroyed"),
        pytest.param("reserve"),
    ],
)
def test_automatic_mission_action_opportunity_excludes_unavailable_units(
    ineligible_state: str,
) -> None:
    lifecycle = _battle_lifecycle(
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    unit_id = "army-alpha:intercessor-unit-1"
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_id,
        target_suffix="center",
    )
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_id)
    if ineligible_state == "battle_shocked":
        state.battle_shocked_unit_ids = [unit_id]
    elif ineligible_state == "already_shot":
        state.shooting_phase_state = ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-a",
            selected_unit_ids=(unit_id,),
            shot_unit_ids=(unit_id,),
        )
    elif ineligible_state == "destroyed":
        state.battlefield_state = state.battlefield_state.with_removed_models(
            tuple(
                model_placement.model_instance_id
                for model_placement in unit_placement.model_placements
            )
        )
    elif ineligible_state == "reserve":
        state.battlefield_state = state.battlefield_state.without_unit_placement(unit_id)
        state.record_reserve_state(
            ReserveState.declared_before_battle(
                player_id="player-a",
                unit_instance_id=unit_id,
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                    mission_scoring_policies_from_setup(_mission_setup()).policy_for_player(
                        "player-a"
                    )
                ),
            )
        )
    else:
        raise AssertionError("unsupported ineligible-state fixture")

    status = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is None or request.decision_type != START_MISSION_ACTION_DECISION_TYPE


def test_automatic_mission_action_opportunity_excludes_embarked_units() -> None:
    config = _config_with_player_a_transport()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    passenger_id = "army-alpha:intercessor-unit-1"
    transport_id = "army-alpha:transport-unit-2"
    _place_unit_near_objective(
        state,
        unit_instance_id=passenger_id,
        target_suffix="center",
    )
    transport = state.army_definitions[0].unit_by_id(transport_id)
    state.battlefield_state = state.battlefield_state.without_unit_placement(passenger_id)
    state.record_transport_cargo_state(
        TransportCargoState(
            player_id="player-a",
            transport_unit_instance_id=transport_id,
            capacity_profile=TransportCapacityProfile(
                transport_datasheet_id=transport.datasheet_id,
                max_model_count=10,
                allowed_keywords=("INFANTRY",),
            ),
            embarked_unit_instance_ids=(passenger_id,),
        )
    )

    status = LocalGameSession(lifecycle=lifecycle).advance_until_decision_or_terminal()

    request = status.decision_request
    assert request is None or request.decision_type != START_MISSION_ACTION_DECISION_TYPE


def test_end_turn_coherency_cleanup_removes_models_without_destroyed_triggers() -> None:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    broken = _with_model_offsets(
        unit_placement,
        _center_marker_definition(state),
        offsets=((2.0, 0.0), (4.0, 0.0), (6.0, 0.0), (8.0, 0.0), (30.0, 0.0)),
    )
    removed_model_id = broken.model_placements[-1].model_instance_id
    state.battlefield_state = state.battlefield_state.with_unit_placement(broken)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    status = lifecycle.advance_until_decision_or_terminal()
    status = _decline_stratagem_window_if_pending(
        lifecycle,
        status,
        result_id="phase17n-coherency-cleanup-decline-stratagem",
    )
    if state.current_battle_phase is BattlePhase.FIGHT:
        status = lifecycle.advance_until_decision_or_terminal()
    assert status.status_kind in {
        LifecycleStatusKind.WAITING_FOR_DECISION,
        LifecycleStatusKind.TERMINAL,
    }
    assert state.current_battle_phase is not BattlePhase.FIGHT
    cleanup = state.end_turn_cleanup_states[-1]

    assert removed_model_id in state.battlefield_state.removed_model_ids
    assert cleanup.removed_model_instance_ids == (removed_model_id,)
    assert cleanup.removals[0].removal_kind.value == "destroyed"
    assert cleanup.removals[0].destroyed_model_rules_triggered is False
    (departure,) = state.primary_battlefield_departure_states
    assert departure.source_id == f"{cleanup.cleanup_id}:army-alpha:intercessor-unit-1"
    assert not state.primary_unit_destruction_states
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    event_records = lifecycle.decision_controller.event_log.records
    departure_event_order = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "primary_battlefield_departure_recorded"
    )
    phase_completed_order = next(
        index
        for index, event in enumerate(event_records)
        if event.event_type == "battle_phase_completed" and index > departure_event_order
    )
    assert departure_event_order < phase_completed_order
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()

    forged_payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(payload, sort_keys=True)),
    )
    forged_events = forged_payload["decisions"]["event_log"]
    for index, event in enumerate(forged_events):
        if index > departure_event_order and event["event_type"] == "battle_phase_completed":
            event["event_type"] = "battle_phase_boundary_tampered"
    with pytest.raises(
        GameLifecycleError,
        match="Unit Coherency departure requires an authoritative phase-boundary event",
    ):
        GameLifecycle.from_payload(forged_payload)


def test_turn_end_control_and_primary_scoring_use_post_cleanup_battlefield() -> None:
    state = _battle_state_for_primary("primary-immovable-object")
    assert state.battlefield_state is not None
    marker = _center_marker_definition(state)
    unit_placement = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    broken = _with_model_offsets(
        unit_placement,
        marker,
        offsets=((16.0, 8.0), (17.5, 8.0), (16.0, 9.5), (17.5, 9.5), (0.0, 0.0)),
    )
    isolated_objective_model_id = broken.model_placements[-1].model_instance_id
    state.battlefield_state = state.battlefield_state.with_unit_placement(broken)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    state.advance_to_next_battle_phase()

    assert isolated_objective_model_id in state.battlefield_state.removed_model_ids
    turn_end_record = next(
        record
        for record in reversed(state.objective_control_records)
        if record.timing is ObjectiveControlTiming.TURN_END
    )
    central_result = turn_end_record.result_by_objective_id(marker.objective_marker_id)
    assert central_result.controlled_by_player_id is None
    assert not any(
        _transaction_metadata(transaction)["scoring_rule_id"] == "immovable-object-central-turn-end"
        for transaction in state.victory_point_ledger_for_player("player-a").transactions
    )


def test_unarrived_reserves_are_destroyed_at_mission_deadline() -> None:
    state, reserve_unit_id = _battle_state_with_unarrived_reserve_at_round_three_deadline()
    reserve_model_ids = tuple(
        model.model_instance_id
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == reserve_unit_id
        for model in unit.own_models
    )

    state.advance_to_next_battle_phase()
    reserve_state = state.reserve_state_for_unit(reserve_unit_id)

    assert reserve_state is not None
    assert reserve_state.status is ReserveStatus.DESTROYED
    assert state.battlefield_state is not None
    assert set(reserve_model_ids) <= set(state.battlefield_state.removed_model_ids)
    (destruction,) = tuple(
        row
        for row in state.primary_unit_destruction_states
        if row.destroyed_unit_instance_id == reserve_unit_id
    )
    assert destruction.unattributed_cause is (PrimaryUnattributedDestructionCause.RESERVE_DEADLINE)
    assert all(
        reserve_unit_id not in departure.departed_component_unit_instance_ids
        for departure in state.primary_battlefield_departure_states
    )


def test_victory_point_ledger_round_trips_without_object_reprs() -> None:
    state = _battle_state()
    state.score_secondary_mission(
        player_id="player-a",
        secondary_mission_id="assassination",
        mode=SecondaryMissionCardMode.FIXED,
        phase=BattlePhase.COMMAND,
    )
    payload = cast(
        GameStatePayload,
        json.loads(json.dumps(state.to_payload(), sort_keys=True)),
    )
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert GameState.from_payload(payload).to_payload() == state.to_payload()
    assert (
        VictoryPointLedger.from_payload(payload["victory_point_ledgers"][0]).to_payload()
        == state.victory_point_ledgers[0].to_payload()
    )


def test_game_ends_after_configured_battle_rounds_with_draw_result() -> None:
    state = _battle_state()
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)

    completed_phase = state.advance_to_next_battle_phase()
    result = state.game_result_payload()

    assert completed_phase is BattlePhase.FIGHT
    assert state.stage is GameLifecycleStage.COMPLETE
    assert state.current_battle_phase is None
    assert result["winner_player_ids"] == ["player-a", "player-b"]
    assert result["is_draw"] is True


def test_scoring_policy_ledger_and_card_state_fail_fast_paths() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    primary = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "primary-unstoppable-force"
    )
    policy = mission_scoring_policies_from_setup(
        _mission_setup_for_primary("primary-unstoppable-force")
    ).policy_for_player("player-a")
    primary_rule = policy.primary_scoring_rules[0]
    award = policy.mission_action_award(
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.COMMAND.value,
        action_id="cleanse:center:player-a",
        source_id="cleanse",
        amount=4,
    )

    ledger, transaction = VictoryPointLedger.initial(player_id="player-a").award(award)
    fixed_card = SecondaryMissionCardState.active_fixed(
        player_id="player-a",
        secondary_mission_id="assassination",
    )
    scored_card = fixed_card.score(transaction_id=transaction.transaction_id)

    assert MissionScoringPolicy.from_payload(policy.to_payload()) == policy
    assert policy.mission_pack_id == mission_pack.mission_pack_id
    assert policy.game_length_battle_rounds == mission_pack.scoring.game_length_battle_rounds
    assert policy.primary_max_vp_per_turn == primary.max_vp_per_turn
    assert policy.primary_vp_per_controlled_objective == primary.vp_per_controlled_objective
    assert policy.primary_scoring_rule_id is None
    assert policy.primary_scoring_rule_condition is None
    assert PrimaryMissionScoringRule.from_payload(primary_rule.to_payload()) == primary_rule
    assert policy.primary_vp_cap == mission_pack.scoring.primary_vp_cap
    assert policy.total_vp_cap == mission_pack.scoring.total_vp_cap
    assert award.to_payload()["source_kind"] == "mission_action"
    assert VictoryPointTransaction.from_payload(transaction.to_payload()) == transaction
    assert ledger.points_from_source_kind(VictoryPointSourceKind.MISSION_ACTION) == 4
    assert SecondaryMissionCardState.from_payload(scored_card.to_payload()) == scored_card
    assert fixed_card.to_public_payload(
        viewer_player_id="player-b",
        secondary_mission_choices_revealed=False,
    ) == {
        "player_id": "player-a",
        "hidden": True,
    }
    assert fixed_card.to_public_payload(
        viewer_player_id="player-b",
        secondary_mission_choices_revealed=True,
    ) == {
        "player_id": "player-a",
        "secondary_mission_id": "assassination",
        "mode": "fixed",
        "battle_round": 1,
        "status": "active",
        "source_result_id": None,
        "scored_transaction_id": None,
        "discarded_result_id": None,
        "hidden": False,
    }

    with pytest.raises(GameLifecycleError):
        policy.secondary_award(
            player_id="player-a",
            battle_round=1,
            phase=BattlePhase.COMMAND.value,
            secondary_mission_id="assassination",
            source_kind=VictoryPointSourceKind.PRIMARY,
            hidden=True,
        )
    with pytest.raises(GameLifecycleError, match="source_kind must be primary"):
        replace(primary_rule, source_kind=VictoryPointSourceKind.MISSION_ACTION)
    with pytest.raises(GameLifecycleError, match="primary_scoring_rules must contain"):
        replace(
            policy,
            primary_scoring_rules=cast(
                tuple[PrimaryMissionScoringRule, ...],
                ("not-a-rule",),
            ),
        )
    with pytest.raises(GameLifecycleError, match="primary_scoring_rules must not contain"):
        replace(policy, primary_scoring_rules=(primary_rule, primary_rule))
    with pytest.raises(GameLifecycleError, match="Primary support status"):
        replace(policy, primary_scoring_rules=())
    scoring_state = _battle_state()
    assert scoring_state.mission_setup is not None
    assert scoring_state.battlefield_state is not None
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            scoring_state,
            timing=ObjectiveControlTiming.TURN_END,
            phase=BattlePhase.FIGHT,
        )
    )
    with pytest.raises(GameLifecycleError, match="ObjectiveControlRecord"):
        policy.primary_awards_from_objective_control(
            record=cast(ObjectiveControlRecord, object()),
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="MissionSetup"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=cast(MissionSetup, object()),
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring rule timing"):
        replace(
            policy,
            primary_scoring_rules=(replace(primary_rule, timing="unsupported-timing"),),
        ).primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    turn_start = scoring_state.primary_objective_turn_start_states[0]
    with pytest.raises(GameLifecycleError, match="turn-start states must be a tuple"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=cast(tuple[PrimaryObjectiveTurnStartState, ...], []),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="turn-start states must contain"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=cast(
                tuple[PrimaryObjectiveTurnStartState, ...],
                ("not-a-turn-start-state",),
            ),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="turn-start states must not duplicate"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=(turn_start, turn_start),
            terrain_trap_states=(),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="terrain trap states must be a tuple"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=cast(tuple[PrimaryTerrainTrapState, ...], []),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="terrain trap states must contain"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=cast(tuple[PrimaryTerrainTrapState, ...], ("not-a-trap",)),
            unit_destruction_states=(),
        )
    with pytest.raises(GameLifecycleError, match="unit destruction states must be a tuple"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=cast(tuple[PrimaryUnitDestructionState, ...], []),
        )
    with pytest.raises(GameLifecycleError, match="unit destruction states must contain"):
        policy.primary_awards_from_objective_control(
            record=record,
            mission_setup=scoring_state.mission_setup,
            turn_order=scoring_state.turn_order,
            turn_start_states=tuple(scoring_state.primary_objective_turn_start_states),
            terrain_trap_states=(),
            unit_destruction_states=cast(
                tuple[PrimaryUnitDestructionState, ...],
                ("not-a-destruction",),
            ),
        )
    drifted_setup = _with_player_primary_mission(
        _event_companion_mission_setup(),
        player_id="player-a",
        primary_mission_id="primary-vital-link",
    )
    with pytest.raises(GameLifecycleError, match="directional matrix"):
        mission_scoring_policies_from_setup(drifted_setup)
    with pytest.raises(GameLifecycleError):
        ledger.award(cast(VictoryPointAward, "not-an-award"))
    with pytest.raises(GameLifecycleError):
        ledger.award(replace(award, player_id="player-b"))
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=99,
            transactions=ledger.transactions,
        )
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=transaction.amount,
            transactions=cast(tuple[VictoryPointTransaction, ...], ("not-a-transaction",)),
        )
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=transaction.amount,
            transactions=(replace(transaction, player_id="player-b"),),
        )
    with pytest.raises(GameLifecycleError):
        VictoryPointLedger(
            player_id="player-a",
            victory_points=transaction.amount * 2,
            transactions=(transaction, transaction),
        )
    with pytest.raises(GameLifecycleError):
        fixed_card.discard(result_id="discard-fixed")
    with pytest.raises(GameLifecycleError):
        scored_card.score(transaction_id="another-transaction")
    with pytest.raises(GameLifecycleError):
        scored_card.discard(result_id="discard-scored")
    with pytest.raises(GameLifecycleError):
        SecondaryMissionCardState(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.FIXED,
            battle_round=1,
            status=SecondaryMissionCardStatus.SCORED,
        )
    with pytest.raises(GameLifecycleError):
        SecondaryMissionCardState(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.TACTICAL,
            battle_round=1,
            status=SecondaryMissionCardStatus.DISCARDED,
        )
    with pytest.raises(GameLifecycleError):
        SecondaryMissionCardState(
            player_id="player-a",
            secondary_mission_id="assassination",
            mode=SecondaryMissionCardMode.TACTICAL,
            battle_round=1,
            scored_transaction_id="victory-point:player-a:round-01:000001",
        )


def test_phase11e_token_parsers_reject_malformed_values() -> None:
    with pytest.raises(GameLifecycleError):
        victory_point_source_kind_from_token(1)
    with pytest.raises(GameLifecycleError):
        victory_point_source_kind_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_status_from_token(1)
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_status_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_mode_from_token(1)
    with pytest.raises(GameLifecycleError):
        secondary_mission_card_mode_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        objective_control_timing_from_token(1)
    with pytest.raises(GameLifecycleError):
        objective_control_timing_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        mission_action_status_from_token(1)
    with pytest.raises(GameLifecycleError):
        mission_action_status_from_token("unsupported")
    with pytest.raises(GameLifecycleError):
        battlefield_removal_kind_from_token(1)
    with pytest.raises(GameLifecycleError):
        battlefield_removal_kind_from_token("unsupported")


def test_mission_action_state_rejects_drifted_completion_and_status_fields() -> None:
    action = _mission_action_state(action_id="cleanse:center:player-a")
    award = VictoryPointAward(
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        amount=5,
        source_kind=VictoryPointSourceKind.MISSION_ACTION,
        source_id="cleanse",
        scoring_timing="mission_action_complete",
        metadata={"action_id": action.action_id},
    )

    completed = action.complete(
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        completion_timing="turn_end",
        award=award,
        transaction_id="victory-point:player-a:round-01:000001",
    )

    assert MissionActionState.from_payload(action.to_payload()) == action
    assert completed.status is MissionActionStatus.COMPLETED

    with pytest.raises(GameLifecycleError):
        completed.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=award,
            transaction_id="victory-point:player-a:round-01:000002",
        )
    with pytest.raises(GameLifecycleError):
        completed.interrupt(reason="unit_moved")
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="wrong_timing",
            award=award,
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=cast(VictoryPointAward, "not-an-award"),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=replace(award, player_id="player-b"),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=replace(award, source_id="behind-enemy-lines"),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=replace(award, amount=10),
            transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError):
        action.interrupt(reason="unit_destroyed")
    with pytest.raises(GameLifecycleError):
        MissionActionState.start(
            action_id="cleanse:invalid:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-2",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:started-with-completion:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round_started=1,
            phase_started=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            completed_battle_round=1,
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:completed-without-round:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round_started=1,
            phase_started=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            status=MissionActionStatus.COMPLETED,
            score_transaction_id="victory-point:player-a:round-01:000001",
        )
    with pytest.raises(GameLifecycleError, match="eligible_unit_instance_ids must be a tuple"):
        MissionActionState.start(
            action_id="cleanse:eligible-not-tuple:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=cast(tuple[str, ...], []),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="eligible_unit_instance_ids must not contain"):
        MissionActionState.start(
            action_id="cleanse:duplicate-eligible:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=(
                "army-alpha:intercessor-unit-1",
                "army-alpha:intercessor-unit-1",
            ),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="eligible_unit_instance_ids must contain"):
        MissionActionState.start(
            action_id="cleanse:no-eligible:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=(),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id must be a string"):
        MissionActionState.start(
            action_id="cleanse:non-string-unit:player-a",
            player_id="player-a",
            unit_instance_id=cast(str, 1),
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="unit_instance_id must not be empty"):
        MissionActionState.start(
            action_id="cleanse:empty-unit:player-a",
            player_id="player-a",
            unit_instance_id=" ",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="battle_round_started must be an integer"):
        MissionActionState.start(
            action_id="cleanse:round-not-int:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=cast(int, "1"),
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="battle_round_started must be at least 1"):
        MissionActionState.start(
            action_id="cleanse:round-zero:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=0,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
        )
    with pytest.raises(GameLifecycleError, match="victory_points must be an integer"):
        MissionActionState.start(
            action_id="cleanse:vp-not-int:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=cast(int, "5"),
        )
    with pytest.raises(GameLifecycleError, match="victory_points must not be negative"):
        MissionActionState.start(
            action_id="cleanse:vp-negative:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=-1,
        )
    with pytest.raises(GameLifecycleError):
        MissionActionState(
            action_id="cleanse:interrupted-with-score:player-a",
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round_started=1,
            phase_started=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            status=MissionActionStatus.INTERRUPTED,
            interrupted_reason="unit_moved",
            score_transaction_id="victory-point:player-a:round-01:000001",
        )


def test_mission_policy_and_tactical_draw_are_fail_fast() -> None:
    setup = _mission_setup()

    assert deterministic_tactical_secondary_draw(
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        draw_count=1,
    )

    with pytest.raises(GameLifecycleError):
        mission_scoring_policies_from_setup(cast(MissionSetup, object()))
    with pytest.raises(GameLifecycleError):
        mission_scoring_policies_from_setup(replace(setup, mission_pack_id="unsupported-pack"))
    with pytest.raises(GameLifecycleError):
        mission_scoring_policies_from_setup(
            _with_player_primary_mission(
                setup,
                player_id="player-a",
                primary_mission_id="unsupported-primary",
            )
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=cast(MissionSetup, object()),
            player_id="player-a",
            battle_round=1,
            draw_count=1,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=replace(setup, mission_pack_id="unsupported-pack"),
            player_id="player-a",
            battle_round=1,
            draw_count=1,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            draw_count=999,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            player_id="player-a",
            battle_round=0,
            draw_count=1,
        )
    with pytest.raises(GameLifecycleError):
        deterministic_tactical_secondary_draw(
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            draw_count=1,
            excluded_secondary_mission_ids=("cleanse", "cleanse"),
        )


def test_turn_cleanup_payloads_and_resolver_reject_invalid_contexts() -> None:
    removal = CoherencyCleanupRemoval(
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        model_instance_id="army-alpha:intercessor-unit-1:model-1",
    )
    cleanup = EndTurnCleanupState(
        cleanup_id="end-turn-cleanup:phase11e-game:round-01:player-a",
        game_id="phase11e-game",
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removals=(removal,),
        coherency_results=(),
        transition_batch=BattlefieldTransitionBatch(),
    )
    state = _battle_state()
    assert state.battlefield_state is not None
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )

    assert CoherencyCleanupRemoval.from_payload(removal.to_payload()) == removal
    assert EndTurnCleanupState.from_payload(cleanup.to_payload()) == cleanup

    with pytest.raises(GameLifecycleError):
        CoherencyCleanupRemoval(
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:model-1",
            removal_kind=BattlefieldRemovalKind.EMBARK,
        )
    with pytest.raises(GameLifecycleError):
        CoherencyCleanupRemoval(
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:model-1",
            destroyed_model_rules_triggered=True,
        )
    with pytest.raises(GameLifecycleError):
        EndTurnCleanupState(
            cleanup_id="end-turn-cleanup:phase11e-game:round-01:player-a",
            game_id="phase11e-game",
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT.value,
            removals=(removal, removal),
            coherency_results=(),
            transition_batch=BattlefieldTransitionBatch(),
        )
    with pytest.raises(GameLifecycleError):
        EndTurnCleanupState(
            cleanup_id="end-turn-cleanup:phase11e-game:round-01:player-a",
            game_id="phase11e-game",
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT.value,
            removals=(removal,),
            coherency_results=(),
            transition_batch=cast(BattlefieldTransitionBatch, object()),
        )
    with pytest.raises(GameLifecycleError):
        resolve_end_turn_cleanup(
            game_id="phase11e-game",
            scenario=cast(BattlefieldScenario, object()),
            ruleset_descriptor=_ruleset(),
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError):
        resolve_end_turn_cleanup(
            game_id="phase11e-game",
            scenario=scenario,
            ruleset_descriptor=cast(RulesetDescriptor, object()),
            battle_round=1,
            active_player_id="player-a",
            phase=BattlePhase.FIGHT,
        )
    with pytest.raises(GameLifecycleError):
        resolve_end_turn_cleanup(
            game_id="phase11e-game",
            scenario=scenario,
            ruleset_descriptor=_ruleset(),
            battle_round=1,
            active_player_id="player-a",
            phase=cast(BattlePhase, "fight"),
        )


def _with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
    start_index: int = 0,
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement_index = start_index + index
        placement = placements[placement_index]
        placements[placement_index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def _first_plunderable_logical_terrain_area(
    state: GameState,
    *,
    player_id: str,
) -> MissionLogicalTerrainArea:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    return next(
        area
        for area in mission_logical_terrain_areas(state.mission_setup)
        if not logical_terrain_area_within_player_territory(
            area,
            mission_setup=state.mission_setup,
            player_id=player_id,
        )
    )


def _record_completed_zero_vp_mission_action(
    state: GameState,
    *,
    mission_action_id: str,
    action_id: str,
    target_id: str,
    player_id: str = "player-a",
) -> str:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    mission_action = mission_pack_for_id(state.mission_setup.mission_pack_id).mission_action(
        mission_action_id
    )
    army = next(army for army in state.army_definitions if army.player_id == player_id)
    unit_instance_id = army.units[0].unit_instance_id
    started = MissionActionState.start(
        action_id=action_id,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        mission_id=mission_action.mission_id,
        battle_round=state.battle_round,
        phase=mission_action.start_phase,
        start_timing=mission_action.start_timing,
        completion_timing=mission_action.completion_timing,
        eligible_unit_instance_ids=(unit_instance_id,),
        interruption_conditions=mission_action.interruption_conditions,
        scoring_source_id=mission_action.scoring_source_id,
        victory_points=mission_action.victory_points,
    )
    completion_phase = (
        BattlePhase.FIGHT.value
        if mission_action.completion_timing == "turn_end"
        else mission_action.start_phase
    )
    completed = started.complete_without_award(
        battle_round=state.battle_round,
        phase=completion_phase,
        completion_timing=mission_action.completion_timing,
    )
    state.record_mission_action_state(completed)
    return mission_action.source_id


def _objective_logical_terrain_area(
    mission_setup: MissionSetup,
    *,
    objective_role: ObjectiveMarkerRole,
) -> MissionLogicalTerrainArea:
    marker = next(
        marker
        for marker in mission_setup.objective_markers
        if marker.objective_role is objective_role
    )
    association = next(
        association
        for association in mission_setup.objective_terrain_areas
        if association.objective_marker_id == marker.objective_marker_id
    )
    physical_areas_by_id = {area.terrain_area_id: area for area in mission_setup.terrain_areas}
    logical_ids = {
        physical_areas_by_id[area_id].logical_terrain_area_id
        for area_id in association.terrain_area_ids
    }
    assert len(logical_ids) == 1
    (logical_id,) = logical_ids
    return next(
        area
        for area in mission_logical_terrain_areas(mission_setup)
        if area.logical_terrain_area_id == logical_id
    )


def _logical_terrain_area_test_point(
    area: MissionLogicalTerrainArea,
) -> tuple[float, float]:
    point = area.members[0].footprint_polygon[0]
    return point.x_inches, point.y_inches


def _battle_state_with_unarrived_reserve_at_round_three_deadline() -> tuple[GameState, str]:
    state = _battle_state()
    assert state.battlefield_state is not None
    reserve_unit = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-a",
            unit_instance_id=reserve_unit.unit_instance_id,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                mission_scoring_policies_from_setup(_mission_setup()).policy_for_player("player-a")
            ),
        )
    )
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record_primary_turn_start_evidence(state=state)
    return state, reserve_unit.unit_instance_id


def test_phase14c_battle_shocked_units_cannot_start_or_complete_mission_actions() -> None:
    unit_id = "army-alpha:intercessor-unit-1"
    action = _mission_action_state(action_id="cleanse:center:player-a")
    award = VictoryPointAward(
        player_id="player-a",
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        amount=5,
        source_kind=VictoryPointSourceKind.MISSION_ACTION,
        source_id="cleanse",
        scoring_timing="mission_action_complete",
        metadata={"action_id": action.action_id},
    )

    with pytest.raises(GameLifecycleError, match="cannot start actions"):
        MissionActionState.start(
            action_id="cleanse:center:player-a",
            player_id="player-a",
            unit_instance_id=unit_id,
            target_id="take-and-hold-vs-purge-the-foe-layout-3-center-central",
            mission_id="cleanse",
            battle_round=1,
            phase=BattlePhase.MOVEMENT.value,
            start_timing="movement_phase_unit_selected",
            completion_timing="turn_end",
            eligible_unit_instance_ids=(unit_id,),
            interruption_conditions=("unit_moved",),
            scoring_source_id="cleanse",
            victory_points=5,
            battle_shocked_unit_ids=(unit_id,),
        )
    with pytest.raises(GameLifecycleError, match="cannot complete actions"):
        action.complete(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            completion_timing="turn_end",
            award=award,
            transaction_id="victory-point:player-a:round-01:000001",
            battle_shocked_unit_ids=(unit_id,),
        )


def _mission_action_state(
    *,
    action_id: str,
    target_id: str = "take-and-hold-vs-purge-the-foe-layout-3-center-central",
) -> MissionActionState:
    return MissionActionState.start(
        action_id=action_id,
        player_id="player-a",
        unit_instance_id="army-alpha:intercessor-unit-1",
        target_id=target_id,
        mission_id="cleanse",
        battle_round=1,
        phase=BattlePhase.MOVEMENT.value,
        start_timing="movement_phase_unit_selected",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("army-alpha:intercessor-unit-1",),
        interruption_conditions=("unit_moved",),
        scoring_source_id="cleanse",
        victory_points=5,
    )


def _attached_cleanse_action(
    *,
    state: GameState,
    action_id: str,
) -> MissionActionState:
    return MissionActionState.start(
        action_id=action_id,
        player_id="player-a",
        unit_instance_id="attached-unit:army-alpha:bodyguard-unit",
        target_id=_center_marker_definition(state).objective_marker_id,
        mission_id="cleanse",
        battle_round=state.battle_round,
        phase=BattlePhase.SHOOTING.value,
        start_timing="shooting_phase",
        completion_timing="turn_end",
        eligible_unit_instance_ids=("attached-unit:army-alpha:bodyguard-unit",),
        interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
        scoring_source_id="cleanse",
        victory_points=0,
    )


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    return _objective_marker_definition(state, "center")


def _objective_marker_definition(
    state: GameState,
    target_suffix: str,
) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if _objective_marker_matches_suffix(marker.objective_marker_id, target_suffix):
            return marker
    raise AssertionError(f"missing {target_suffix} objective marker")


def _public_ledger(payload: dict[str, JsonValue], *, player_id: str) -> dict[str, JsonValue]:
    ledgers = payload["victory_point_ledgers"]
    assert isinstance(ledgers, list)
    for ledger_value in ledgers:
        assert isinstance(ledger_value, dict)
        ledger = ledger_value
        if ledger["player_id"] == player_id:
            return ledger
    raise AssertionError(f"missing public ledger for {player_id}")


def _transaction_metadata(transaction: VictoryPointTransaction) -> dict[str, JsonValue]:
    metadata = transaction.metadata
    assert isinstance(metadata, dict)
    return metadata


def _public_card_states(payload: dict[str, JsonValue]) -> list[dict[str, JsonValue]]:
    card_states = payload["secondary_mission_card_states"]
    assert isinstance(card_states, list)
    public_states: list[dict[str, JsonValue]] = []
    for card_state_value in card_states:
        assert isinstance(card_state_value, dict)
        public_states.append(card_state_value)
    return public_states


def _public_secondary_choice(
    payload: dict[str, JsonValue],
    *,
    player_id: str,
) -> dict[str, JsonValue]:
    choices = payload["secondary_mission_choices"]
    assert isinstance(choices, list)
    for choice_value in choices:
        assert isinstance(choice_value, dict)
        if choice_value["player_id"] == player_id:
            return choice_value
    raise AssertionError(f"missing public secondary choice for {player_id}")


def _advance_to_secondary_request(lifecycle: GameLifecycle) -> LifecycleStatus:
    for _index in range(32):
        status = lifecycle.advance_until_decision_or_terminal()
        request = status.decision_request
        if request is not None and request.decision_type == SECONDARY_MISSION_DECISION_TYPE:
            return status
    raise AssertionError("lifecycle did not reach secondary mission selection")


def _start_mission_action_via_lifecycle(
    *,
    lifecycle: GameLifecycle,
    target_suffix: str,
    result_id: str,
    unit_instance_id: str = "army-alpha:intercessor-unit-1",
) -> MissionActionState:
    state = lifecycle.state
    assert state is not None
    _place_unit_near_objective(
        state,
        unit_instance_id=unit_instance_id,
        target_suffix=target_suffix,
    )
    waiting = request_mission_action_start(
        state=state,
        decisions=lifecycle.decision_controller,
        player_id="player-a",
        mission_action_id="cleanse-objective",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = waiting.decision_request
    assert request is not None
    option = next(
        option
        for option in request.options
        if _objective_marker_matches_suffix(
            str(cast(dict[str, JsonValue], option.payload)["target_id"]),
            target_suffix,
        )
    )
    result = FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option.option_id,
        result_id=result_id,
    ).to_result(request)
    lifecycle.submit_decision(result)
    action_id = f"mission-action:{result_id}"
    return state.mission_action_state_by_id(action_id)


def _place_unit_near_objective(
    state: GameState,
    *,
    unit_instance_id: str,
    target_suffix: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if _objective_marker_matches_suffix(marker.objective_marker_id, target_suffix)
    )
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    offsets = tuple(
        (2.0 + float(index), 0.0) for index in range(len(unit_placement.model_placements))
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit_placement, marker, offsets=offsets)
    )


def _place_unit_near_point(
    state: GameState,
    *,
    unit_instance_id: str,
    x_inches: float,
    y_inches: float,
) -> None:
    if state.mission_setup is None or not state.mission_setup.objective_markers:
        raise AssertionError("test state requires an objective marker")
    marker = replace(
        state.mission_setup.objective_markers[0],
        x_inches=x_inches,
        y_inches=y_inches,
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    unit_placement = state.battlefield_state.unit_placement_by_id(unit_instance_id)
    offsets = tuple(
        (float(index) * 0.75, 0.0) for index in range(len(unit_placement.model_placements))
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        _with_model_offsets(unit_placement, marker, offsets=offsets)
    )


def _remove_unit_for_primary_destruction(
    state: GameState,
    *,
    unit_instance_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == unit_instance_id
    )
    state.replace_battlefield_state(
        state.battlefield_state.with_removed_models(unit.own_model_ids())
    )


def _record_test_primary_unit_destruction(
    state: GameState,
    *,
    destroying_player_id: str,
    destroyed_unit_instance_id: str,
    source_id: str,
) -> PrimaryUnitDestructionState:
    attribution, witness = _test_primary_destruction_attribution(
        state,
        destroying_player_id=destroying_player_id,
    )
    destroyed_unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == destroyed_unit_instance_id
    )
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=destroyed_unit.own_model_ids(),
        source_id=source_id,
    )
    return state.record_primary_unit_destruction(
        destruction_attribution=attribution,
        source_model_destroyed_event_id=f"{source_id}:model-destroyed-event",
        source_rules_unit_objective_proximity_witness=witness,
        source_battlefield_departure_ids=tuple(departure.departure_id for departure in departures),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        source_id=source_id,
    )


def _authentic_primary_destruction_lifecycle_payload() -> GameLifecyclePayload:
    config = _config_with_player_b_character(
        mission_setup=_event_companion_meatgrinder_mission_setup()
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attacker = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-alpha:intercessor-unit-1"
    )
    defender = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-beta:character-unit-3"
    )
    (defender_model,) = defender.own_models
    weapon_profile = replace(
        _first_weapon_profile(lifecycle, attacker),
        damage_profile=DamageProfile.fixed(defender_model.wounds_remaining),
    )
    sequence_id = "phase17n-destruction-integrity-runtime-attack"
    attack_context_id = f"{sequence_id}:pool-001:attack-001"
    remaining, _allocated_model_ids, attack_status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=config.ruleset_descriptor,
        attack_sequence=AttackSequence.start(
            sequence_id=sequence_id,
            attacker_player_id="player-a",
            attacking_unit_instance_id=attacker.unit_instance_id,
            attack_pools=(
                _attack_pool_for_test(
                    attacker=attacker,
                    defender=defender,
                    weapon_profile=weapon_profile,
                    attacks=1,
                ),
            ),
        ),
        already_allocated_model_ids=(),
        dice_manager=DiceRollManager(
            sequence_id,
            event_log=lifecycle.decision_controller.event_log,
            injected_results=(
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:hit",
                    spec=attack_sequence_hit_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:wound",
                    spec=attack_sequence_wound_roll_spec(
                        weapon_profile_id=weapon_profile.profile_id,
                        attack_context_id=attack_context_id,
                        attacker_player_id="player-a",
                    ),
                    value=6,
                ),
                _fixed_roll_result(
                    roll_id=f"{sequence_id}:save",
                    spec=saving_throw_roll_spec(
                        save_kind=SaveKind.ARMOUR,
                        player_id="player-b",
                        allocated_model_id=defender_model.model_instance_id,
                        attack_context_id=attack_context_id,
                    ),
                    value=1,
                ),
            ),
        ),
    )
    assert remaining is None
    assert attack_status is None
    BattleRoundFlow(
        phase_handlers={
            BattlePhase.SHOOTING: PlaceholderPhaseHandler(BattlePhase.SHOOTING),
        }
    ).advance(state=state, decisions=lifecycle.decision_controller)
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    assert len(state.primary_unit_destruction_states) == 1
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    return payload


def _transport_reserve_deadline_lifecycle(
    *,
    preexisting_cargo_casualty: bool = False,
    destruction_deadline_policy: ReserveDestructionTimingPolicy | None = None,
) -> tuple[GameLifecycle, TransportCargoState, tuple[str, ...]]:
    config = _config_with_player_a_transport()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    lifecycle = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
        )
    )
    state = cast(GameState, lifecycle.state)
    assert state.battlefield_state is not None
    owner_army = state.army_definition_for_player("player-a")
    assert owner_army is not None
    transport = owner_army.unit_by_id("army-alpha:transport-unit-2")
    passenger = owner_army.unit_by_id("army-alpha:intercessor-unit-1")
    route_model_ids = tuple(
        sorted(
            model.model_instance_id for unit in (transport, passenger) for model in unit.own_models
        )
    )
    battlefield = state.battlefield_state
    if preexisting_cargo_casualty:
        casualty_id = passenger.own_models[0].model_instance_id
        _set_model_wounds_remaining(
            state,
            model_instance_id=casualty_id,
            wounds_remaining=0,
        )
        battlefield = battlefield.with_removed_models((casualty_id,))
    state.replace_battlefield_state(
        battlefield.without_unit_placement(passenger.unit_instance_id).without_unit_placement(
            transport.unit_instance_id
        )
    )
    cargo_state = TransportCargoState(
        player_id="player-a",
        transport_unit_instance_id=transport.unit_instance_id,
        capacity_profile=TransportCapacityProfile(
            transport_datasheet_id=transport.datasheet_id,
            max_model_count=10,
            allowed_keywords=("INFANTRY",),
            source_id="phase17n-reserve-deadline-transport-capacity",
        ),
        embarked_unit_instance_ids=(passenger.unit_instance_id,),
    )
    state.record_transport_cargo_state(cargo_state)
    resolved_policy = destruction_deadline_policy
    if resolved_policy is None:
        assert state.mission_setup is not None
        resolved_policy = reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(state.mission_setup).policy_for_player("player-a")
        )
    declared_reserve = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=transport.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=resolved_policy,
        embarked_unit_instance_ids=(passenger.unit_instance_id,),
    )
    state.record_reserve_state(declared_reserve)
    lifecycle.decision_controller.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": declared_reserve.player_id,
            "unit_instance_id": declared_reserve.unit_instance_id,
            "reserve_state": declared_reserve.to_payload(),
        },
    )
    return lifecycle, cargo_state, route_model_ids


def _resolve_transport_reserve_at_round_boundary(lifecycle: GameLifecycle) -> None:
    state = cast(GameState, lifecycle.state)
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record_primary_turn_start_evidence(state=state)
    BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT)}
    ).advance(state=state, decisions=lifecycle.decision_controller)
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )


def _authentic_reserve_deadline_lifecycle_payload() -> GameLifecyclePayload:
    lifecycle = _battle_lifecycle()
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    reserve_unit = state.army_definitions[0].unit_by_id("army-alpha:intercessor-unit-1")
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(reserve_unit.unit_instance_id)
    )
    declared_reserve = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
            mission_scoring_policies_from_setup(
                cast(MissionSetup, state.mission_setup)
            ).policy_for_player("player-a")
        ),
    )
    state.record_reserve_state(declared_reserve)
    lifecycle.decision_controller.event_log.append(
        "reserve_unit_declared",
        {
            "game_id": state.game_id,
            "player_id": declared_reserve.player_id,
            "unit_instance_id": declared_reserve.unit_instance_id,
            "reserve_state": declared_reserve.to_payload(),
        },
    )
    state.battle_round = 3
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record_primary_turn_start_evidence(state=state)
    BattleRoundFlow(
        phase_handlers={BattlePhase.FIGHT: PlaceholderPhaseHandler(BattlePhase.FIGHT)}
    ).advance(state=state, decisions=lifecycle.decision_controller)
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    reserve_destructions = tuple(
        destruction
        for destruction in state.primary_unit_destruction_states
        if destruction.unattributed_cause is PrimaryUnattributedDestructionCause.RESERVE_DEADLINE
    )
    assert len(reserve_destructions) == 1
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    return payload


def _authentic_attached_unit_lifecycle_payload() -> GameLifecyclePayload:
    config = _config_with_player_a_attached_unit()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    state = lifecycle.state
    assert state is not None
    _record_missing_turn_start_evidence_events(
        state=state,
        decisions=lifecycle.decision_controller,
    )
    assert len(state.starting_attached_unit_records) == 1
    assert not state.primary_unit_destruction_states
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    restored = GameLifecycle.from_payload(payload)
    assert restored.state is not None
    assert restored.state.to_payload() == state.to_payload()
    return payload


def _authentic_integrity_graph(
    payload: GameLifecyclePayload,
) -> tuple[GameState, tuple[EventRecord, ...], tuple[DecisionRecord, ...]]:
    restored = GameLifecycle.from_payload(
        cast(
            GameLifecyclePayload,
            json.loads(json.dumps(payload, sort_keys=True)),
        )
    )
    state = restored.state
    assert state is not None
    return (
        state,
        restored.decision_controller.event_log.records,
        restored.decision_controller.records,
    )


def _authentic_timeline_graph(
    payload: GameLifecyclePayload,
) -> tuple[
    GameState,
    tuple[PrimaryUnitDestructionState, ...],
    tuple[PrimaryBattlefieldDepartureState, ...],
    dict[str, historical_event_integrity._DestroyedDepartureSource],  # pyright: ignore[reportPrivateUsage]
    tuple[EventRecord, ...],
    dict[str, int],
    dict[str, historical_event_integrity._ScoringRulesUnitIdentity],  # pyright: ignore[reportPrivateUsage]
    tuple[DecisionRecord, ...],
]:
    state, event_records, decision_records = _authentic_integrity_graph(payload)
    model_ids_by_unit_id = {
        unit.unit_instance_id: tuple(sorted(unit.own_model_ids()))
        for army in state.army_definitions
        for unit in army.units
    }
    rules_unit_components_by_id = historical_event_integrity._rules_unit_components_by_id(  # pyright: ignore[reportPrivateUsage]
        state=state
    )
    identities_by_id = historical_event_integrity._scoring_identities_by_id(  # pyright: ignore[reportPrivateUsage]
        state=state,
        model_ids_by_unit_id=model_ids_by_unit_id,
    )
    events_by_id = {event.event_id: event for event in event_records}
    event_index_by_id = _historical_event_index(event_records)
    destructions = tuple(state.primary_unit_destruction_states)
    departures = tuple(state.primary_battlefield_departure_states)
    departure_sources = historical_event_integrity._validate_destroyed_departure_provenance(  # pyright: ignore[reportPrivateUsage]
        state=state,
        destructions=destructions,
        departures=departures,
        identities_by_id=identities_by_id,
        model_ids_by_unit_id=model_ids_by_unit_id,
        rules_unit_components_by_id=rules_unit_components_by_id,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
        decision_records=decision_records,
    )
    return (
        state,
        destructions,
        departures,
        departure_sources,
        event_records,
        event_index_by_id,
        identities_by_id,
        decision_records,
    )


def _historical_event_index(records: tuple[EventRecord, ...]) -> dict[str, int]:
    return {record.event_id: index for index, record in enumerate(records)}


def _resequence_historical_events(records: tuple[EventRecord, ...]) -> tuple[EventRecord, ...]:
    return tuple(
        replace(record, event_id=f"event-{index:06d}")
        for index, record in enumerate(records, start=1)
    )


def _unattributed_timeline_destruction(
    destruction: PrimaryUnitDestructionState,
    *,
    cause: PrimaryUnattributedDestructionCause,
    mutation_id: str,
    source_id: str,
) -> PrimaryUnitDestructionState:
    return replace(
        destruction,
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        unattributed_cause=cause,
        source_mutation_id=mutation_id,
        source_id=source_id,
    )


def _replace_historical_event(
    records: tuple[EventRecord, ...],
    *,
    original: EventRecord,
    payload: JsonValue,
) -> tuple[EventRecord, ...]:
    return tuple(
        replace(record, payload=payload) if record.event_id == original.event_id else record
        for record in records
    )


def _typed_primary_reserve_entry_evidence() -> tuple[
    PrimaryReserveEntryProvider,
    ReserveState,
    PrimaryBattlefieldDepartureState,
    BattlefieldTransitionBatch,
]:
    unit_id = "army-alpha:intercessor-unit-1"
    model_id = f"{unit_id}:model-001"
    provider = PrimaryReserveEntryProvider(
        provider_kind=PrimaryReserveEntryProviderKind.TURN_END_ABILITY,
        provider_id="phase17n:typed-reserve-entry-provider",
        player_id="player-a",
        source_rule_id="phase17n:typed-reserve-entry-rule",
        target_rules_unit_instance_id=unit_id,
        decision_record_id="phase17n:typed-reserve-entry-decision-record",
        decision_request_id="phase17n:typed-reserve-entry-decision-request",
        decision_result_id="phase17n:typed-reserve-entry-decision-result",
        stratagem_use_id=None,
        source_terminal_event_type="phase17n:typed-reserve-entry-terminal",
    )
    reserve_state = ReserveState.entered_during_battle(
        player_id=provider.player_id,
        unit_instance_id=unit_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=2,
        phase=BattlePhase.FIGHT,
        reserve_origin=ReserveOrigin.DURING_BATTLE_ABILITY,
        source_rule_ids=(provider.source_rule_id,),
    )
    affected_component_ids = (unit_id,)
    departed_component_ids: tuple[str, ...] = ()
    removed_model_ids = (model_id,)
    departure_id = primary_battlefield_departure_id(
        game_id="phase11e-game",
        rules_unit_instance_id=unit_id,
        affected_component_unit_instance_ids=affected_component_ids,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=2,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
        occurrence_id=provider.occurrence_id,
        source_id=provider.occurrence_id,
    )
    departure = PrimaryBattlefieldDepartureState(
        departure_id=departure_id,
        game_id="phase11e-game",
        owner_player_id=provider.player_id,
        rules_unit_instance_id=unit_id,
        component_unit_instance_ids=(unit_id,),
        affected_component_unit_instance_ids=affected_component_ids,
        departed_component_unit_instance_ids=departed_component_ids,
        removed_model_instance_ids=removed_model_ids,
        battle_round=2,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
        occurrence_id=provider.occurrence_id,
        source_id=provider.occurrence_id,
    )
    transition_batch = BattlefieldTransitionBatch(
        removals=(
            ModelRemovalRecord(
                model_instance_id=model_id,
                removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
                source_phase=BattlePhase.FIGHT.value,
                source_rule_id=provider.source_rule_id,
            ),
        )
    )
    return provider, reserve_state, departure, transition_batch


def _record_missing_turn_start_evidence_events(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    recorded_occurrences = {
        (
            event.payload.get("game_id"),
            event.payload.get("active_player_id"),
            event.payload.get("battle_round"),
        )
        for event in decisions.event_log.records
        if event.event_type == "primary_turn_start_evidence_recorded"
        and isinstance(event.payload, dict)
    }
    record_new_primary_turn_start_evidence_events(
        state=state,
        event_log=decisions.event_log,
        objective_state_ids_before=tuple(
            value.state_id
            for value in state.primary_objective_turn_start_states
            if (value.game_id, value.active_player_id, value.battle_round) in recorded_occurrences
        ),
        snapshot_ids_before=tuple(
            value.snapshot_id
            for value in state.primary_rules_unit_turn_start_snapshots
            if (value.game_id, value.active_player_id, value.battle_round) in recorded_occurrences
        ),
    )


def _record_test_completed_primary_unit_destruction(
    state: GameState,
    *,
    destroyed_model_instance_ids: tuple[str, ...],
    destroying_player_id: str | None,
    source_id: str,
    left_battlefield: bool = True,
) -> tuple[PrimaryUnitDestructionState, ...]:
    if destroying_player_id is None:
        attribution = None
        event_id = None
        source_witness = None
        cause = PrimaryUnattributedDestructionCause.UNIT_COHERENCY
        source_mutation_id = source_id
    else:
        attribution, source_witness = _test_primary_destruction_attribution(
            state,
            destroying_player_id=destroying_player_id,
        )
        event_id = f"{source_id}:model-destroyed-event"
        cause = None
        source_mutation_id = None
    return record_primary_unit_destructions_for_destroyed_models(
        state=state,
        destroyed_model_instance_ids=destroyed_model_instance_ids,
        destruction_attribution=attribution,
        source_model_destroyed_event_id=event_id,
        source_rules_unit_objective_proximity_witness=source_witness,
        destroyed_rules_unit_objective_proximity_witness=None,
        unattributed_cause=cause,
        source_mutation_id=source_mutation_id,
        left_battlefield=left_battlefield,
        source_id=source_id,
    )


def _test_primary_destruction_attribution(
    state: GameState,
    *,
    destroying_player_id: str,
) -> tuple[ModelDestructionAttribution, RulesUnitObjectiveProximityWitness]:
    source_army = next(
        army for army in state.army_definitions if army.player_id == destroying_player_id
    )
    source_rules_unit_id = rules_unit_view_by_id(
        state=state,
        unit_instance_id=source_army.units[0].unit_instance_id,
    ).unit_instance_id
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id=destroying_player_id,
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id=None,
    )
    return (
        attribution,
        rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=source_rules_unit_id,
        ),
    )


def _set_unit_wounds_remaining(
    state: GameState,
    *,
    unit_instance_id: str,
    wounds_remaining: int,
) -> None:
    state.replace_army_definitions(
        [
            replace(
                army,
                units=tuple(
                    replace(
                        unit,
                        own_models=tuple(
                            replace(model, wounds_remaining=wounds_remaining)
                            for model in unit.own_models
                        ),
                    )
                    if unit.unit_instance_id == unit_instance_id
                    else unit
                    for unit in army.units
                ),
            )
            for army in state.army_definitions
        ]
    )


def _set_model_wounds_remaining(
    state: GameState,
    *,
    model_instance_id: str,
    wounds_remaining: int,
) -> None:
    matched = False
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            updated_models = tuple(
                replace(model, wounds_remaining=wounds_remaining)
                if model.model_instance_id == model_instance_id
                else model
                for model in unit.own_models
            )
            if updated_models != unit.own_models:
                matched = True
                updated_units.append(replace(unit, own_models=updated_models))
            else:
                updated_units.append(unit)
        updated_armies.append(replace(army, units=tuple(updated_units)))
    if not matched:
        raise AssertionError(f"Missing model {model_instance_id}.")
    state.replace_army_definitions(updated_armies)


def _decline_stratagem_window_if_pending(
    lifecycle: GameLifecycle,
    status: LifecycleStatus,
    *,
    result_id: str,
) -> LifecycleStatus:
    request = status.decision_request
    if request is None or request.decision_type != STRATAGEM_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        )
    )


def _battle_lifecycle(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
    mission_setup: MissionSetup | None = None,
) -> GameLifecycle:
    config = _config(mission_setup=mission_setup)
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state(
        player_a_secondary=player_a_secondary,
        player_b_secondary=player_b_secondary,
        player_a_fixed_mission_ids=player_a_fixed_mission_ids,
        mission_setup=mission_setup,
        decisions=lifecycle.decision_controller,
    )
    return lifecycle


def _battle_lifecycle_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> GameLifecycle:
    config = _config_for_primary(
        primary_mission_id,
        objective_terrain_feature_id=objective_terrain_feature_id,
    )
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        decisions=lifecycle.decision_controller,
    )
    return lifecycle


def _battle_lifecycle_with_active_tactical_cards() -> GameLifecycle:
    lifecycle = _battle_lifecycle(player_a_secondary=SecondaryMissionMode.TACTICAL)
    state = lifecycle.state
    assert state is not None
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id=SEEDED_TACTICAL_DRAW_REQUEST_ID,
            result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
    )
    return lifecycle


def _event_companion_battle_lifecycle_with_active_tactical_cards() -> GameLifecycle:
    lifecycle = _battle_lifecycle(
        player_a_secondary=SecondaryMissionMode.TACTICAL,
        mission_setup=_event_companion_mission_setup(),
    )
    state = lifecycle.state
    assert state is not None
    state.record_tactical_secondary_draw(
        TacticalSecondaryDraw(
            player_id="player-a",
            battle_round=state.battle_round,
            request_id=SEEDED_TACTICAL_DRAW_REQUEST_ID,
            result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
            draw_count=state.tactical_secondary_draw_count,
        )
    )
    state.draw_tactical_secondary_cards(
        player_id="player-a",
        source_result_id=SEEDED_TACTICAL_DRAW_RESULT_ID,
    )
    return lifecycle


def _active_tactical_card(state: GameState) -> SecondaryMissionCardState:
    return next(
        card
        for card in state.secondary_mission_card_states
        if card.player_id == "player-a"
        and card.mode is SecondaryMissionCardMode.TACTICAL
        and card.status is SecondaryMissionCardStatus.ACTIVE
    )


def _record_active_tactical_secondary(
    state: GameState,
    *,
    secondary_mission_id: str,
) -> None:
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id=secondary_mission_id,
            battle_round=state.battle_round,
            source_result_id=f"phase11e-hold-{secondary_mission_id}",
        )
    )


def _record_tactical_secondary_achievement_context(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    achievement_id: str,
) -> TacticalSecondaryAchievementContext:
    context = _tactical_secondary_achievement_context_for_card(
        state=state,
        card=card,
        achievement_id=achievement_id,
    )
    state.record_tactical_secondary_achievement_context(context)
    return context


def _tactical_secondary_achievement_context_for_card(
    *,
    state: GameState,
    card: SecondaryMissionCardState,
    achievement_id: str,
) -> TacticalSecondaryAchievementContext:
    assert state.mission_setup is not None
    assert state.active_player_id is not None
    phase = state.current_battle_phase
    assert phase is not None
    policy = mission_scoring_policies_from_setup(state.mission_setup).policy_for_player(
        card.player_id
    )
    award = policy.secondary_award(
        player_id=card.player_id,
        battle_round=state.battle_round,
        phase=phase.value,
        secondary_mission_id=card.secondary_mission_id,
        source_kind=VictoryPointSourceKind.TACTICAL_SECONDARY,
        hidden=False,
    )
    metadata = cast(dict[str, JsonValue], award.metadata)
    return TacticalSecondaryAchievementContext(
        achievement_id=achievement_id,
        game_id=state.game_id,
        player_id=card.player_id,
        active_player_id=state.active_player_id,
        secondary_mission_id=card.secondary_mission_id,
        battle_round=state.battle_round,
        phase=phase.value,
        card_battle_round=card.battle_round,
        victory_points=award.amount,
        scoring_rule_id=cast(str, metadata["scoring_rule_id"]),
        scoring_rule_condition=cast(str, metadata["scoring_rule_condition"]),
        scoring_rule_source_id=cast(str, metadata["scoring_rule_source_id"]),
        scoring_timing=award.scoring_timing,
        source_id=f"phase14j:{card.secondary_mission_id}:requirements-achieved",
        evidence={
            "evidence_kind": "source_backed_requirement_result",
            "requirements_met": True,
            "secondary_mission_id": card.secondary_mission_id,
        },
    )


def _battle_lifecycle_with_player_a_vehicle() -> GameLifecycle:
    config = _config_with_player_a_vehicle()
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    lifecycle.state = _battle_state_from_config(
        config,
        player_a_fixed_mission_ids=("bring-it-down", "cleanse"),
        decisions=lifecycle.decision_controller,
    )
    return lifecycle


def _battle_state(
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
    mission_setup: MissionSetup | None = None,
    decisions: DecisionController | None = None,
) -> GameState:
    config = _config(mission_setup=mission_setup)
    return _battle_state_from_config(
        config,
        player_a_secondary=player_a_secondary,
        player_b_secondary=player_b_secondary,
        player_a_fixed_mission_ids=player_a_fixed_mission_ids,
        decisions=decisions,
    )


def _battle_state_for_primary(primary_mission_id: str) -> GameState:
    return _battle_state_from_config(_config_for_primary(primary_mission_id))


def _battle_state_from_config(
    config: GameConfig,
    *,
    player_a_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_b_secondary: SecondaryMissionMode = SecondaryMissionMode.FIXED,
    player_a_fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
    turn_start_unit_positions: tuple[tuple[str, float, float], ...] = (),
    turn_start_unplaced_unit_ids: tuple[str, ...] = (),
    decisions: DecisionController | None = None,
) -> GameState:
    state = GameState.from_config(config)
    for army in _mustered_armies(config):
        state.record_army_definition(army)
    assert config.mission_setup is not None
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11e-battlefield",
        armies=tuple(state.army_definitions),
        battlefield_width_inches=config.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=config.mission_setup.battlefield_depth_inches,
        terrain_features=config.mission_setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    for unit_instance_id, x_inches, y_inches in turn_start_unit_positions:
        _place_unit_near_point(
            state,
            unit_instance_id=unit_instance_id,
            x_inches=x_inches,
            y_inches=y_inches,
        )
    for unit_instance_id in turn_start_unplaced_unit_ids:
        assert state.battlefield_state is not None
        state.replace_battlefield_state(
            state.battlefield_state.without_unit_placement(unit_instance_id)
        )
        owner = next(
            army.player_id
            for army in state.army_definitions
            if any(unit.unit_instance_id == unit_instance_id for unit in army.units)
        )
        state.record_reserve_state(
            ReserveState.declared_before_battle(
                player_id=owner,
                unit_instance_id=unit_instance_id,
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                destruction_deadline_policy=reserve_destruction_policy_from_scoring_policy(
                    mission_scoring_policies_from_setup(config.mission_setup).policy_for_player(
                        owner
                    )
                ),
            )
        )
    state.record_secondary_mission_choice(
        _secondary_choice(
            player_id="player-a",
            mode=player_a_secondary,
            fixed_mission_ids=player_a_fixed_mission_ids,
        )
    )
    state.record_secondary_mission_choice(
        _secondary_choice(player_id="player-b", mode=player_b_secondary)
    )
    enter_battle_for_fixture(state, decisions=decisions)
    assert state.stage is GameLifecycleStage.BATTLE
    assert state.current_battle_phase is BattlePhase.COMMAND
    return state


def _secondary_choice(
    *,
    player_id: str,
    mode: SecondaryMissionMode,
    fixed_mission_ids: tuple[str, str] = ("assassination", "bring-it-down"),
) -> SecondaryMissionChoice:
    if mode is SecondaryMissionMode.TACTICAL:
        return SecondaryMissionChoice(player_id=player_id, mode=mode)
    return SecondaryMissionChoice(
        player_id=player_id,
        mode=mode,
        fixed_mission_ids=fixed_mission_ids,
    )


def _config(*, mission_setup: MissionSetup | None = None) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    resolved_mission_setup = _mission_setup() if mission_setup is None else mission_setup
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _config_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> GameConfig:
    return _config(
        mission_setup=_mission_setup_for_primary(
            primary_mission_id,
            objective_terrain_feature_id=objective_terrain_feature_id,
        ),
    )


def _config_with_player_a_vehicle() -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="vehicle-unit-2",
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_two_player_a_infantry_units() -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_player_a_attached_unit(
    *,
    include_independent_unit: bool = False,
    mission_setup: MissionSetup | None = None,
) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    resolved_mission_setup = _mission_setup() if mission_setup is None else mission_setup
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-a"
                ),
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="bodyguard-unit",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="leader-unit",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                    *(
                        (
                            _unit_muster_selection(
                                unit_selection_id="intercessor-unit-2",
                                datasheet_id="core-intercessor-like-infantry",
                                model_profile_id="core-intercessor-like",
                                model_count=5,
                            ),
                        )
                        if include_independent_unit
                        else ()
                    ),
                ),
                attachment_declarations=(
                    AttachmentDeclaration(
                        source_unit_selection_id="leader-unit",
                        bodyguard_unit_selection_id="bodyguard-unit",
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=resolved_mission_setup.force_disposition_id_for_player(
                    "player-b"
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=resolved_mission_setup,
    )


def _config_with_player_a_transport() -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            ArmyMusterRequest(
                army_id="army-alpha",
                player_id="player-a",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="intercessor-unit-1",
                        datasheet_id="core-intercessor-like-infantry",
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                    _unit_muster_selection(
                        unit_selection_id="transport-unit-2",
                        datasheet_id="core-transport",
                        model_profile_id="core-transport",
                        model_count=1,
                    ),
                ),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_player_b_character(*, mission_setup: MissionSetup) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                force_disposition_id=mission_setup.force_disposition_id_for_player("player-a"),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id=mission_setup.force_disposition_id_for_player("player-b"),
                unit_selections=(
                    _unit_muster_selection(
                        unit_selection_id="character-unit-3",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=mission_setup,
    )


def _config_with_player_b_vehicles(vehicle_unit_ids: tuple[str, ...]) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=tuple(
                    _unit_muster_selection(
                        unit_selection_id=unit_id,
                        datasheet_id="core-vehicle-monster",
                        model_profile_id="core-vehicle-monster",
                        model_count=1,
                    )
                    for unit_id in vehicle_unit_ids
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _config_with_player_b_horde_units(unit_ids: tuple[str, ...]) -> GameConfig:
    catalog = _catalog_with_directional_force_dispositions()
    return GameConfig(
        game_id="phase11e-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
            ),
            ArmyMusterRequest(
                army_id="army-beta",
                player_id="player-b",
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="core-marine-force",
                    detachment_ids=("core-combined-arms",),
                ),
                force_disposition_id="take-and-hold",
                unit_selections=tuple(
                    _unit_muster_selection(
                        unit_selection_id=unit_id,
                        datasheet_id="core-boyz-like-infantry",
                        model_profile_id="core-boyz-like",
                        model_count=13,
                    )
                    for unit_id in unit_ids
                ),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring-it-down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _record_secondary_vehicle_destruction(
    state: GameState,
    destroyed_unit_instance_id: str,
    *,
    started_turn_objective_marker_ids: tuple[str, ...] = (),
) -> None:
    _record_secondary_unit_destruction(
        state,
        destroyed_unit_instance_id,
        started_turn_objective_marker_ids=started_turn_objective_marker_ids,
    )


def _record_secondary_unit_destruction(
    state: GameState,
    destroyed_unit_instance_id: str,
    *,
    started_turn_objective_marker_ids: tuple[str, ...] = (),
) -> None:
    unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == destroyed_unit_instance_id
    )
    state.record_secondary_unit_destruction(
        destroying_player_id="player-a",
        destroyed_unit_instance_id=destroyed_unit_instance_id,
        destroyed_model_instance_ids=tuple(model.model_instance_id for model in unit.own_models),
        started_turn_objective_marker_ids=started_turn_objective_marker_ids,
        source_id=f"phase16:{destroyed_unit_instance_id}:destroyed",
    )


def _controlled_objective_result(
    objective_id: str,
    *,
    player_id: str,
) -> ObjectiveControlResult:
    return ObjectiveControlResult(
        objective_id=objective_id,
        status=ObjectiveControlStatus.CONTROLLED,
        controlled_by_player_id=player_id,
        scores=(ObjectiveControlScore(player_id=player_id, score=1),),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


def _event_companion_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


def _event_companion_meatgrinder_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _event_companion_purge_and_secure_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
        terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="reconnaissance",
    )


def _event_companion_death_trap_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
        terrain_layout_id="take-and-hold-vs-disruption-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="disruption",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


def _chapter_approved_immovable_object_mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _mission_setup_for_primary(
    primary_mission_id: str,
    *,
    objective_terrain_feature_id: str | None = None,
) -> MissionSetup:
    if primary_mission_id == "primary-death-trap":
        return _event_companion_death_trap_mission_setup()
    if objective_terrain_feature_id is not None:
        raise AssertionError("Only Death Trap accepts a terrain target fixture.")
    if primary_mission_id == "primary-immovable-object":
        return _chapter_approved_immovable_object_mission_setup()
    if primary_mission_id == "primary-meatgrinder":
        return _event_companion_meatgrinder_mission_setup()
    if primary_mission_id == "primary-unstoppable-force":
        return _mission_setup()
    raise AssertionError("Primary mission fixture requires an engine-implemented mission.")


def _event_companion_mission_setup_with_scoring_terrain_feature(
    *,
    feature_id: str = SCORING_TERRAIN_FEATURE_ID,
) -> MissionSetup:
    del feature_id
    return _event_companion_mission_setup()


def _center_marker_definition_for_setup(
    mission_setup: MissionSetup,
) -> ObjectiveMarkerDefinition:
    for marker in mission_setup.objective_markers:
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL:
            return marker
    raise AssertionError("missing center objective marker")


def _objective_marker_matches_suffix(objective_marker_id: str, target_suffix: str) -> bool:
    return any(
        objective_marker_id.endswith(suffix)
        for suffix in _objective_marker_suffix_aliases(target_suffix)
    )


def _objective_marker_suffix_aliases(target_suffix: str) -> tuple[str, ...]:
    if target_suffix == "center":
        return (
            "-center",
            "-center-central",
            "-central-north",
            "-central-south",
            "-central-west",
            "-central-east",
        )
    if target_suffix in {"northeast", "northwest"}:
        return (f"-{target_suffix}", "-upper-central")
    if target_suffix in {"southeast", "southwest"}:
        return (f"-{target_suffix}", "-lower-central")
    return (target_suffix, f"-{target_suffix.replace('_', '-')}")


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11e-test"
    )


def _catalog_with_directional_force_dispositions() -> ArmyCatalog:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=(
                    "disruption",
                    "purge-the-foe",
                    "reconnaissance",
                    "take-and-hold",
                ),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )


def _with_player_primary_mission(
    mission_setup: MissionSetup,
    *,
    player_id: str,
    primary_mission_id: str,
) -> MissionSetup:
    return replace(
        mission_setup,
        primary_mission_assignments=tuple(
            (
                PlayerPrimaryMissionAssignment(
                    player_id=assignment.player_id,
                    force_disposition_id=assignment.force_disposition_id,
                    primary_mission_id=primary_mission_id,
                )
                if assignment.player_id == player_id
                else assignment
            )
            for assignment in mission_setup.primary_mission_assignments
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    force_disposition_id: str | None = None,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=(
            ("purge-the-foe" if player_id == "player-a" else "take-and-hold")
            if force_disposition_id is None
            else force_disposition_id
        ),
        unit_selections=tuple(
            _unit_muster_selection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _unit_muster_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


def _replace_unit(
    state: GameState,
    *,
    unit_instance_id: str,
    keywords: tuple[str, ...],
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    replace(unit, keywords=keywords)
                    if unit.unit_instance_id == unit_instance_id
                    else unit
                    for unit in army.units
                ),
            )
        )
    state.replace_army_definitions(updated_armies)


def _replace_unit_objective_control(
    state: GameState,
    *,
    unit_instance_id: str,
    objective_control: int | str,
) -> None:
    updated_armies: list[ArmyDefinition] = []
    for army in state.army_definitions:
        updated_units: list[UnitInstance] = []
        for unit in army.units:
            if unit.unit_instance_id != unit_instance_id:
                updated_units.append(unit)
                continue
            updated_models: list[ModelInstance] = []
            for model in unit.own_models:
                replacement = (
                    CharacteristicValue.source_dash(Characteristic.OBJECTIVE_CONTROL)
                    if objective_control == "-"
                    else CharacteristicValue.from_raw(
                        Characteristic.OBJECTIVE_CONTROL,
                        cast(int, objective_control),
                    )
                )
                updated_models.append(
                    replace(
                        model,
                        characteristics=tuple(
                            replacement
                            if value.characteristic is Characteristic.OBJECTIVE_CONTROL
                            else value
                            for value in model.characteristics
                        ),
                    )
                )
            updated_units.append(replace(unit, own_models=tuple(updated_models)))
        updated_armies.append(replace(army, units=tuple(updated_units)))
    state.replace_army_definitions(updated_armies)


def _advanced_unit_state(*, unit_instance_id: str) -> AdvancedUnitState:
    request = AdvanceRollRequest.for_unit(
        request_id=f"{unit_instance_id}:action-eligibility-advance",
        game_id="phase11e-game",
        battle_round=1,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
    )
    roll_state = DiceRollManager("phase11e-action-eligibility-advance").roll_fixed(
        request.spec,
        [3],
    )
    return AdvancedUnitState(
        player_id="player-a",
        battle_round=1,
        unit_instance_id=unit_instance_id,
        movement_dice_record=MovementDiceRecord(
            player_id="player-a",
            battle_round=1,
            unit_instance_id=unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=request,
                roll_state=roll_state,
            ),
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
