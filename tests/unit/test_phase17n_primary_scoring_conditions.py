from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from math import comb
from typing import Any, cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    default_unit_selection,
    phase11c_config,
    with_model_offsets,
)
from tests.phase15a_charge_declaration_helpers import charge_lifecycle
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_action_turn_end_record as shared_action_turn_end_record,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_started_primary_action_fixture as shared_started_primary_action_fixture,
)

from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_options import mission_action_for_state
from warhammer40k_core.engine.mission_action_policies import (
    mission_action_policy_for_id,
    primary_mission_choice_rule_for_id,
    primary_mission_state_rule_for_id,
)
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    request_mission_action_start,
)
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlContribution,
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
)
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.primary_battlefield_departure import (
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    ObjectiveMarkerModelWitness,
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    primary_unattributed_destruction_cause_from_token,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
)
from warhammer40k_core.engine.primary_mission_action_integrity import (
    validate_primary_mission_action_integrity,
)
from warhammer40k_core.engine.primary_mission_action_interruptions import (
    reconcile_primary_mission_action_interruptions,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY,
    MissionActionPriorUseEvidence,
    MissionActionStartAuthorityOptionEvidence,
    PrimaryMissionActionCompletionEvidence,
    PrimaryMissionActionStartEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
    validate_primary_mission_action_start_evidence,
    validate_primary_mission_action_use_limits,
)
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import PrimaryMissionChoiceData
from warhammer40k_core.engine.primary_mission_choices import (
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    PRIMARY_OPERATION_MARKER_KIND,
    SENSOR_SWEEP_EXTRACT_ACTION_ID,
    SENSOR_SWEEP_LOCATE_ACTION_ID,
    apply_primary_mission_choice,
    consecrate_choice_request,
    invalid_primary_mission_choice_request_status,
    locate_and_deny_setup_choice_request,
    primary_mission_choice_option_id,
    punishment_choice_request,
    sensor_sweep_marker_removal_choice_request,
)
from warhammer40k_core.engine.primary_mission_decision_integrity import (
    validate_primary_mission_decision_integrity,
)
from warhammer40k_core.engine.primary_mission_marker_integrity import (
    validate_surveil_marker_removal_events,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    primary_condemned_selection_id,
    primary_mission_marker_id,
)
from warhammer40k_core.engine.primary_mission_state_runtime import (
    resolve_surveil_marker_removal_for_completed_moves,
)
from warhammer40k_core.engine.primary_mission_state_validation import (
    validate_primary_mission_progress_state,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
    cross_turn_destruction_comparison_evidence,
    home_objective_ids,
    opponent_home_control_evidence,
    primary_score_count_evidence,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    TABLE_QUARTER_IDS,
    PrimaryScoringSpatialEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerritoryUnitWitness,
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringStateEvidence,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    build_primary_rules_unit_turn_start_snapshot,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_primary_victory_point_award,
    validate_primary_victory_point_transaction,
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


@pytest.fixture(scope="module")
def battlefield_dominance_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-1",
        terrain_layout_id="take-and-hold-vs-take-and-hold-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )


@pytest.fixture(scope="module")
def purge_and_secure_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-reconnaissance-layout-1",
        terrain_layout_id="take-and-hold-vs-reconnaissance-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="reconnaissance",
    )


def test_promoted_objective_conditions_use_exact_control_and_directed_geometry(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    ids_by_suffix = {
        marker.objective_marker_id.rsplit("-", maxsplit=1)[-1]: marker.objective_marker_id
        for marker in setup.objective_markers
    }
    attacker_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("attacker-home")
    )
    defender_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("defender-home")
    )
    controlled_by_a = (
        attacker_home_id,
        ids_by_suffix["central"],
        ids_by_suffix["east"],
        defender_home_id,
    )
    controlled_by_b = (ids_by_suffix["west"],)
    record = _control_record(
        setup,
        battle_round=2,
        controlled_by_a=controlled_by_a,
        controlled_by_b=controlled_by_b,
    )
    opponent_territory_ids = _territory_objective_ids(
        setup,
        owner_role="defender",
    )
    spatial = _spatial_evidence(
        record=record,
        opponent_territory_ids=opponent_territory_ids,
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        turn_start_controlled_objective_ids=(attacker_home_id, ids_by_suffix["central"]),
        spatial_evidence=spatial,
    )

    expected_counts = {
        "control_more_objectives_than_opponent_first_and_second_battle_round": 1,
        "each_objective_controlled_from_battle_round_two": 4,
        "each_controlled_objective_from_battle_round_two": 4,
        "each_non_home_objective_controlled_if_home_objective_controlled": 3,
        "control_one_or_more_non_home_objectives_from_battle_round_two": 1,
        "control_central_and_expansion_objectives": 1,
        "each_newly_controlled_non_home_objective_this_turn": 2,
        "each_controlled_objective_in_opponent_territory": len(
            set(controlled_by_a).intersection(opponent_territory_ids)
        ),
        "control_three_or_more_objectives": 1,
        "control_two_or_more_objectives_from_battle_round_two": 1,
        "control_more_objectives_than_opponent_from_battle_round_two": 1,
        "control_enemy_home_objective": 1,
        "each_non_home_objective_controlled_battle_rounds_two_and_three": 3,
        "control_one_or_more_central_objectives": 1,
        "each_non_home_objective_controlled_from_battle_round_two": 3,
    }
    for condition, expected_count in expected_counts.items():
        evidence = evaluate_primary_scoring_condition(
            condition=condition,
            context=context,
        )
        assert evidence["score_count"] == expected_count, condition

    territory_evidence = evaluate_primary_scoring_condition(
        condition="each_controlled_objective_in_opponent_territory",
        context=context,
    )
    assert territory_evidence["opponent_player_id"] == "player-b"
    assert territory_evidence["opponent_territory_objective_ids"] == list(opponent_territory_ids)


def test_battlefield_dominance_cumulative_grammar_scores_through_policy(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    attacker_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("attacker-home")
    )
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("central")
    )
    east_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("east")
    )
    west_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("west")
    )
    record = _control_record(
        setup,
        battle_round=2,
        controlled_by_a=(attacker_home_id, central_id, east_id),
        controlled_by_b=(west_id,),
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
    )
    policies = mission_scoring_policies_from_setup(setup)
    assert MissionScoringPolicies.from_payload(policies.to_payload()) == policies
    round_one_record = replace(record, battle_round=1)
    round_one_state, round_one_record, _ = _primary_scoring_state_evidence(
        mission_setup=setup,
        record=round_one_record,
    )

    round_one_awards = policies.primary_awards_from_objective_control(
        record=round_one_record,
        authoritative_state=round_one_state,
    )
    assert round_one_awards == ()
    state, record, state_evidence = _primary_scoring_state_evidence(
        mission_setup=setup,
        record=record,
    )

    awards = policies.primary_awards_from_objective_control(
        record=record,
        authoritative_state=state,
    )

    assert {
        cast(dict[str, object], award.metadata)["scoring_rule_id"]: award.amount for award in awards
    } == {
        "battlefield-dominance-each-objective": 9,
        "battlefield-dominance-home-controlled-non-home-bonus": 4,
    }
    assert all(
        cast(dict[str, object], award.metadata)["primary_scoring_selected_rule_ids"]
        == [
            "battlefield-dominance-each-objective",
            "battlefield-dominance-home-controlled-non-home-bonus",
        ]
        for award in awards
    )
    assert all(
        cast(dict[str, object], award.metadata)["primary_scoring_state_evidence_id"]
        == state_evidence.evidence_id
        and cast(dict[str, object], award.metadata)["primary_scoring_state_evidence_hash"]
        == state_evidence.evidence_hash
        for award in awards
    )


def test_primary_policy_rejects_forged_end_of_battle_and_foreign_evidence(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    policies = mission_scoring_policies_from_setup(setup)
    policy = policies.policy_for_player("player-a")
    command_record = _control_record(
        setup,
        battle_round=2,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
    )
    _, command_record, command_state_evidence = _primary_scoring_state_evidence(
        mission_setup=setup,
        record=command_record,
    )
    forged_end_record = _control_record(setup, battle_round=5)
    forged_end_state, forged_end_record, _ = _primary_scoring_state_evidence(
        mission_setup=setup,
        record=forged_end_record,
    )

    with pytest.raises(GameLifecycleError, match="last player's turn-end record"):
        policies.primary_awards_from_objective_control(
            record=forged_end_record,
            authoritative_state=forged_end_state,
            end_of_battle=True,
        )

    foreign_turn_start = PrimaryObjectiveTurnStartState(
        state_id="primary-turn-start:foreign",
        game_id="primary-game:foreign",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        source_objective_control_record=replace(
            command_record,
            record_id="primary-turn-start-control:foreign",
            game_id="primary-game:foreign",
            timing=ObjectiveControlTiming.TURN_START,
        ),
        controlled_objective_ids=(),
        source_id="primary-turn-start:foreign",
    )
    foreign_trap = PrimaryTerrainTrapState(
        trap_id="primary-terrain-trap:foreign",
        game_id="primary-game:foreign",
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.SHOOTING.value,
        terrain_feature_id="terrain-area:foreign",
        is_objective=False,
        action_id="primary-action:foreign",
        source_id="primary-terrain-trap:foreign",
    )
    foreign_destruction = PrimaryUnitDestructionState(
        destruction_id="primary-destruction:foreign",
        game_id="primary-game:foreign",
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=("primary-departure:foreign",),
        unattributed_cause=PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
        source_mutation_id="end-turn-cleanup:foreign",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.SHOOTING.value,
        destroyed_unit_instance_id="enemy-unit:foreign",
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
        source_id="primary-destruction:foreign",
    )

    with pytest.raises(GameLifecycleError, match="turn-start evidence game_id drift"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(foreign_turn_start,),
            terrain_trap_states=(),
            unit_destruction_states=(),
            state_evidence=command_state_evidence,
        )
    with pytest.raises(GameLifecycleError, match="terrain-trap evidence game_id drift"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(foreign_trap,),
            unit_destruction_states=(),
            state_evidence=command_state_evidence,
        )
    with pytest.raises(GameLifecycleError, match="destruction evidence game_id drift"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(),
            unit_destruction_states=(foreign_destruction,),
            state_evidence=command_state_evidence,
        )

    with pytest.raises(GameLifecycleError, match="cannot come from a future battle round"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(
                replace(
                    foreign_turn_start,
                    game_id=command_record.game_id,
                    battle_round=3,
                    source_objective_control_record=replace(
                        foreign_turn_start.source_objective_control_record,
                        game_id=command_record.game_id,
                        battle_round=3,
                    ),
                ),
            ),
            terrain_trap_states=(),
            unit_destruction_states=(),
            state_evidence=command_state_evidence,
        )
    with pytest.raises(GameLifecycleError, match="references an unknown player"):
        policy.primary_awards_from_objective_control(
            record=command_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            turn_start_states=(),
            terrain_trap_states=(),
            unit_destruction_states=(
                replace(
                    foreign_destruction,
                    game_id=command_record.game_id,
                    destroyed_player_id="player-unknown",
                ),
            ),
            state_evidence=command_state_evidence,
        )


def test_exact_twenty_implemented_primaries_build_typed_runtime_rules() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    implemented_ids = {
        "primary-battlefield-dominance",
        "primary-consecrate",
        "primary-death-trap",
        "primary-delaying-action",
        "primary-destroyers-wrath",
        "primary-determined-acquisition",
        "primary-immovable-object",
        "primary-inescapable-dominion",
        "primary-meatgrinder",
        "primary-outmaneuver",
        "primary-punishment",
        "primary-purge-and-secure",
        "primary-reconnaissance-sweep",
        "primary-sabotage",
        "primary-search-and-scour",
        "primary-secure-asset",
        "primary-smoke-and-mirrors",
        "primary-triangulation",
        "primary-unstoppable-force",
        "primary-vanguard-operation",
    }
    primary_by_id = {
        primary.primary_mission_id: primary for primary in mission_pack.primary_missions
    }

    for primary_mission_id in sorted(implemented_ids):
        rules = primary_scoring_rules_from_definition(primary_by_id[primary_mission_id])
        assert rules
        assert (
            tuple(PrimaryMissionScoringRule.from_payload(rule.to_payload()) for rule in rules)
            == rules
        )

    assert {
        primary.primary_mission_id
        for primary in mission_pack.primary_missions
        if primary_scoring_rules_from_definition(primary, require_supported=False)
    } == implemented_ids


def test_promoted_destruction_and_table_quarter_conditions_emit_witnesses(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    record = _control_record(setup, battle_round=2)
    destruction_evidence = (
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:enemy-one",
            battle_round=2,
            active_player_id="player-a",
            destroying_player_id=None,
            destroyed_player_id="player-b",
            destroyed_unit_instance_id="enemy-unit:one",
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
            started_turn_terrain_feature_ids=("terrain-area:alpha",),
            started_turn_objective_marker_ids=(),
        ),
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:enemy-two",
            battle_round=2,
            active_player_id="player-a",
            destroying_player_id=None,
            destroyed_player_id="player-b",
            destroyed_unit_instance_id="enemy-unit:two",
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
            started_turn_terrain_feature_ids=(),
            started_turn_objective_marker_ids=(),
        ),
        PrimaryUnitDestructionEvidence(
            destruction_id="destruction:friendly-previous",
            battle_round=1,
            active_player_id="player-b",
            destroying_player_id=None,
            destroyed_player_id="player-a",
            destroyed_unit_instance_id="friendly-unit:previous",
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
            started_turn_terrain_feature_ids=(),
            started_turn_objective_marker_ids=(),
        ),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        destruction_evidence=destruction_evidence,
        spatial_evidence=_spatial_evidence(
            record=record,
            opponent_territory_ids=_territory_objective_ids(
                setup,
                owner_role="defender",
            ),
        ),
    )

    each_destroyed = evaluate_primary_scoring_condition(
        condition="each_enemy_unit_destroyed_this_turn",
        context=context,
    )
    comparison = evaluate_primary_scoring_condition(
        condition="more_enemy_units_destroyed_than_friendly_previous_turn",
        context=context,
    )
    terrain_destruction = evaluate_primary_scoring_condition(
        condition="one_or_more_enemy_units_started_turn_in_terrain_area_destroyed_this_turn",
        context=context,
    )
    three_quarters = evaluate_primary_scoring_condition(
        condition=(
            "three_or_more_friendly_units_wholly_within_three_different_table_quarters_"
            "not_within_six_of_center"
        ),
        context=context,
    )
    four_quarters = evaluate_primary_scoring_condition(
        condition=(
            "four_or_more_friendly_units_wholly_within_four_different_table_quarters_"
            "not_within_six_of_center"
        ),
        context=context,
    )

    assert each_destroyed["score_count"] == 2
    assert each_destroyed["destruction_ids"] == [
        "destruction:enemy-one",
        "destruction:enemy-two",
    ]
    assert comparison["score_count"] == 1
    assert comparison["enemy_units_destroyed"] == 2
    assert comparison["friendly_units_destroyed"] == 1
    assert terrain_destruction["score_count"] == 1
    assert terrain_destruction["started_turn_terrain_feature_ids"] == ["terrain-area:alpha"]
    assert three_quarters["score_count"] == 1
    assert four_quarters["score_count"] == 1
    assert four_quarters["qualifying_table_quarter_ids"] == sorted(TABLE_QUARTER_IDS)
    assert len(cast(list[object], four_quarters["table_quarter_unit_witnesses"])) == 4


def test_friendly_attributed_source_on_objective_requires_exact_typed_witness(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    record = _control_record(setup, battle_round=2)
    source_rules_unit_id = "friendly-rules-unit:source"
    source_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id="friendly-model:source",
    )
    source_on_objective = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=source_rules_unit_id,
        component_unit_instance_ids=("friendly-unit:source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id=central_id,
                model_instance_ids=("friendly-model:source",),
            ),
        ),
    )
    qualifying = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:attributed-on-objective",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id="player-a",
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="enemy-unit:qualifying",
        destruction_attribution=source_attribution,
        source_rules_unit_objective_proximity_witness=source_on_objective,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        destruction_evidence=(qualifying,),
    )

    evidence = evaluate_primary_scoring_condition(
        condition=("one_or_more_enemy_units_destroyed_by_friendly_unit_on_objective_this_turn"),
        context=context,
    )

    assert evidence["score_count"] == 1
    assert evidence["destruction_ids"] == ["destruction:attributed-on-objective"]
    assert evidence["destroyed_unit_instance_ids"] == ["enemy-unit:qualifying"]
    assert evidence["source_rules_unit_objective_marker_ids"] == [central_id]

    empty_source_witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=source_rules_unit_id,
        component_unit_instance_ids=("friendly-unit:source",),
        objective_marker_witnesses=(),
    )
    player_only_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=None,
        source_model_instance_id=None,
    )
    non_qualifying = {
        "typed-empty-witness": replace(
            qualifying,
            destruction_id="destruction:typed-empty-witness",
            source_rules_unit_objective_proximity_witness=empty_source_witness,
        ),
        "player-only-attribution": replace(
            qualifying,
            destruction_id="destruction:player-only-attribution",
            destruction_attribution=player_only_attribution,
            source_rules_unit_objective_proximity_witness=None,
        ),
        "unattributed": replace(
            qualifying,
            destruction_id="destruction:unattributed",
            destroying_player_id=None,
            destruction_attribution=None,
            source_rules_unit_objective_proximity_witness=None,
        ),
        "self-owned-target": replace(
            qualifying,
            destruction_id="destruction:self-owned-target",
            destroyed_player_id="player-a",
        ),
    }
    for case_id, row in non_qualifying.items():
        rejected = evaluate_primary_scoring_condition(
            condition=("one_or_more_enemy_units_destroyed_by_friendly_unit_on_objective_this_turn"),
            context=replace(context, destruction_evidence=(row,)),
        )
        assert rejected["score_count"] == 0, case_id
        assert rejected["destruction_ids"] == [], case_id


def test_started_turn_objective_destruction_is_attribution_independent_and_central_filtered(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    non_central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is not ObjectiveMarkerRole.CENTRAL
    )
    record = _control_record(setup, battle_round=2)
    central_destruction = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:started-central",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id=None,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="enemy-unit:started-central",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(central_id,),
    )
    non_central_destruction = replace(
        central_destruction,
        destruction_id="destruction:started-non-central",
        destroyed_unit_instance_id="enemy-unit:started-non-central",
        started_turn_objective_marker_ids=(non_central_id,),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        destruction_evidence=(central_destruction, non_central_destruction),
    )

    any_objective = evaluate_primary_scoring_condition(
        condition=("one_or_more_enemy_units_started_turn_within_objective_destroyed_this_turn"),
        context=context,
    )
    central_only = evaluate_primary_scoring_condition(
        condition=(
            "one_or_more_enemy_units_started_turn_within_central_objective_range_"
            "destroyed_this_turn"
        ),
        context=context,
    )

    assert any_objective["score_count"] == 1
    assert any_objective["destruction_ids"] == [
        "destruction:started-central",
        "destruction:started-non-central",
    ]
    assert any_objective["started_turn_objective_marker_ids"] == sorted(
        (central_id, non_central_id)
    )
    assert central_only["score_count"] == 1
    assert central_only["destruction_ids"] == ["destruction:started-central"]
    assert central_only["started_turn_objective_marker_ids"] == [central_id]
    assert central_only["central_objective_marker_ids"] == [central_id]


def test_purge_and_secure_equal_destruction_branches_award_one_three_vp_result(
    purge_and_secure_setup: MissionSetup,
) -> None:
    setup = purge_and_secure_setup
    central_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    record = _control_record(setup, battle_round=2)
    state, record, _ = _primary_scoring_state_evidence(
        mission_setup=setup,
        record=record,
    )
    source_rules_unit_id = "friendly-rules-unit:purge-source"
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=source_rules_unit_id,
        source_model_instance_id="friendly-model:purge-source",
    )
    source_witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id=source_rules_unit_id,
        component_unit_instance_ids=("friendly-unit:purge-source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id=central_id,
                model_instance_ids=("friendly-model:purge-source",),
            ),
        ),
    )
    destruction = PrimaryUnitDestructionState(
        destruction_id="primary-destruction:purge-both-branches",
        game_id=record.game_id,
        destroying_player_id="player-a",
        destruction_attribution=attribution,
        source_model_destroyed_event_id="event:model-destroyed:purge-both-branches",
        source_rules_unit_objective_proximity_witness=source_witness,
        source_battlefield_departure_ids=("primary-departure:purge-both-branches",),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.FIGHT.value,
        destroyed_unit_instance_id="enemy-unit:purge-target",
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(central_id,),
        source_id="primary-destruction:purge-both-branches",
    )
    turn_start = PrimaryObjectiveTurnStartState(
        state_id="primary-turn-start:purge-player-a:round-2",
        game_id=record.game_id,
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        source_objective_control_record=replace(
            record,
            record_id="primary-turn-start-control:purge-player-a:round-2",
            timing=ObjectiveControlTiming.TURN_START,
        ),
        controlled_objective_ids=(),
        source_id="primary-turn-start:purge-player-a:round-2",
    )
    policies = mission_scoring_policies_from_setup(setup)
    state.primary_objective_turn_start_states = [turn_start]
    state.primary_unit_destruction_states = [destruction]

    awards = policies.primary_awards_from_objective_control(
        record=record,
        authoritative_state=state,
    )

    assert len(awards) == 1
    (award,) = awards
    assert award.amount == 3
    assert award.source_id == "primary-purge-and-secure"
    metadata = cast(dict[str, object], award.metadata)
    assert metadata["scoring_rule_id"] == ("purge-and-secure-destroyed-by-objective-unit-turn-end")
    assert metadata["primary_scoring_achieved_rule_ids"] == [
        "purge-and-secure-destroyed-by-objective-unit-turn-end",
        "purge-and-secure-started-objective-destroyed-turn-end",
    ]
    assert metadata["primary_scoring_selected_rule_ids"] == [
        "purge-and-secure-destroyed-by-objective-unit-turn-end"
    ]
    assert metadata["primary_scoring_suppressed_rule_ids"] == [
        "purge-and-secure-started-objective-destroyed-turn-end"
    ]


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("source_kind", "Primary VP policy validation requires a Primary source row"),
        ("player", "Primary VP policy player_id drift"),
        (
            "source_id",
            "Primary VP source does not match the player's assigned Primary mission",
        ),
        ("metadata", "Primary VP metadata must be an object"),
        (
            "missing_state_evidence_id",
            "Primary VP metadata requires primary_scoring_state_evidence_id",
        ),
        (
            "missing_state_evidence_hash",
            "Primary VP metadata requires primary_scoring_state_evidence_hash",
        ),
        (
            "malformed_state_evidence_hash",
            "Primary VP primary_scoring_state_evidence_hash must be a SHA-256 hex digest",
        ),
        (
            "state_evidence_identity",
            "Primary VP scoring-state evidence identity drifted",
        ),
        ("missing_rule_id", "Primary VP metadata requires scoring_rule_id"),
        (
            "unknown_rule_id",
            "Primary VP scoring_rule_id does not identify an assigned Primary scoring rule",
        ),
        (
            "rule_source",
            "Primary VP scoring_rule_source_id drifted from policy",
        ),
        (
            "rule_condition",
            "Primary VP scoring_rule_condition drifted from policy",
        ),
        ("score_count", "Primary VP metadata requires positive score_count"),
        (
            "points_per_count_missing",
            "Primary VP metadata requires positive victory_points_per_count",
        ),
        (
            "points_per_count_drift",
            "Primary VP victory_points_per_count drifted from policy",
        ),
        ("amount", "Primary VP amount drifted from scoring-rule arithmetic"),
        ("capped_amount", "Primary VP amount drifted from scoring-rule arithmetic"),
        (
            "boundary_missing",
            "Primary VP objective_control_record_id does not identify an authoritative boundary",
        ),
        (
            "boundary_identity",
            "Primary VP objective-control boundary identity drifted",
        ),
        ("row_boundary", "Primary VP row drifted from its objective-control boundary"),
        ("active_player", "Primary VP boundary drifted from the active player"),
        ("source_timing", "Primary VP scoring_timing drifted from its source rule"),
        (
            "boundary_timing",
            "Primary VP scoring_timing drifted from its objective-control boundary",
        ),
        (
            "other_player_boundary",
            "Ordinary Primary VP scoring requires the assigned player's boundary",
        ),
        (
            "round_one_boundary",
            "Primary VP scoring rule does not apply at its objective-control boundary",
        ),
        ("cap_audit", "Primary VP awards must not contain a VP cap audit"),
    ],
)
def test_primary_victory_point_award_validation_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    corruption: str,
    expected_error: str,
) -> None:
    _state, policy, boundary, state_evidence, award = _primary_vp_policy_fixture(
        battlefield_dominance_setup
    )
    metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    boundaries = (boundary,)
    expected_active_player = boundary.active_player_id

    if corruption == "source_kind":
        award = replace(award, source_kind=VictoryPointSourceKind.FIXED_SECONDARY)
    elif corruption == "player":
        award = replace(award, player_id="player-b")
    elif corruption == "source_id":
        award = replace(award, source_id="primary:forged")
    elif corruption == "metadata":
        award = replace(award, metadata=None)
    elif corruption == "missing_state_evidence_id":
        metadata.pop("primary_scoring_state_evidence_id")
    elif corruption == "missing_state_evidence_hash":
        metadata.pop("primary_scoring_state_evidence_hash")
    elif corruption == "malformed_state_evidence_hash":
        metadata["primary_scoring_state_evidence_hash"] = "not-a-digest"
    elif corruption == "state_evidence_identity":
        metadata["primary_scoring_state_evidence_id"] = "primary-scoring-state-evidence:" + "0" * 64
    elif corruption == "missing_rule_id":
        metadata.pop("scoring_rule_id")
    elif corruption == "unknown_rule_id":
        metadata["scoring_rule_id"] = "rule:forged"
    elif corruption == "rule_source":
        metadata["scoring_rule_source_id"] = "source:forged"
    elif corruption == "rule_condition":
        metadata["scoring_rule_condition"] = "condition:forged"
    elif corruption == "score_count":
        metadata["score_count"] = 0
    elif corruption == "points_per_count_missing":
        metadata["victory_points_per_count"] = None
    elif corruption == "points_per_count_drift":
        metadata["victory_points_per_count"] = 99
    elif corruption == "amount":
        award = replace(award, amount=award.amount + 1)
    elif corruption == "capped_amount":
        policy = replace(
            policy,
            primary_scoring_rules=tuple(
                replace(rule, cap=award.amount - 1)
                if rule.rule_id == metadata["scoring_rule_id"]
                else rule
                for rule in policy.primary_scoring_rules
            ),
        )
    elif corruption == "boundary_missing":
        metadata["objective_control_record_id"] = "boundary:missing"
    elif corruption == "boundary_identity":
        boundary = replace(boundary, record_id="boundary:forged")
        boundaries = (boundary,)
        metadata["objective_control_record_id"] = boundary.record_id
    elif corruption == "row_boundary":
        award = replace(award, phase=BattlePhase.FIGHT.value)
    elif corruption == "active_player":
        expected_active_player = "player-b"
    elif corruption == "source_timing":
        award = replace(award, scoring_timing="end_of_battle")
    elif corruption == "boundary_timing":
        award = replace(award, scoring_timing=ObjectiveControlTiming.TURN_END.value)
    elif corruption == "other_player_boundary":
        boundary = replace(
            boundary,
            record_id=(
                f"objective-control:round-{boundary.battle_round:02d}:player-b:"
                f"{boundary.phase}:{boundary.timing.value}"
            ),
            active_player_id="player-b",
        )
        boundaries = (boundary,)
        metadata["objective_control_record_id"] = boundary.record_id
        expected_active_player = "player-b"
    elif corruption == "round_one_boundary":
        boundary = replace(
            boundary,
            record_id=(
                f"objective-control:round-01:{boundary.active_player_id}:"
                f"{boundary.phase}:{boundary.timing.value}"
            ),
            battle_round=1,
        )
        boundaries = (boundary,)
        metadata["objective_control_record_id"] = boundary.record_id
        award = replace(award, battle_round=1)
    elif corruption == "cap_audit":
        metadata["vp_cap_audit"] = {
            "requested_amount": award.amount,
            "applied_amount": award.amount,
        }
    else:
        raise AssertionError(f"unsupported Primary VP corruption: {corruption}")
    if corruption not in {"metadata", "source_kind", "player", "source_id"}:
        award = replace(award, metadata=metadata)

    with pytest.raises(GameLifecycleError, match=expected_error):
        validate_primary_victory_point_award(
            policy=policy,
            award=award,
            objective_control_records=boundaries,
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
            expected_boundary_active_player_id=expected_active_player,
        )


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("witnesses_not_list", "objective_marker_witnesses must be a list"),
        ("payload_not_object", "payload must be an object"),
        ("non_string_key", "payload must be an object"),
        ("empty_model_ids", "model_instance_ids must not be empty"),
        ("duplicate_model_ids", "model_instance_ids must not contain duplicates"),
        ("components_not_list", "component_unit_instance_ids must be a list"),
        ("empty_component_ids", "component_unit_instance_ids must not be empty"),
        (
            "duplicate_objective",
            "objective_marker_witnesses must be unique per objective marker",
        ),
        ("payload_fields", "RulesUnitObjectiveProximityWitness payload fields are invalid"),
    ],
)
def test_objective_proximity_witness_payload_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="rules-unit:source",
        component_unit_instance_ids=("unit:source",),
        objective_marker_witnesses=(
            ObjectiveMarkerModelWitness(
                objective_marker_id="objective:source",
                model_instance_ids=("model:source",),
            ),
        ),
    )
    payload = deepcopy(cast(dict[str, JsonValue], witness.to_payload()))
    assert RulesUnitObjectiveProximityWitness.from_payload(payload) == witness
    raw_witnesses = cast(list[dict[str, JsonValue]], payload["objective_marker_witnesses"])
    if corruption == "witnesses_not_list":
        payload["objective_marker_witnesses"] = None
    elif corruption == "payload_not_object":
        payload = cast(dict[str, JsonValue], None)
    elif corruption == "non_string_key":
        cast(dict[object, JsonValue], payload)[1] = True
    elif corruption == "empty_model_ids":
        raw_witnesses[0]["model_instance_ids"] = []
    elif corruption == "duplicate_model_ids":
        raw_witnesses[0]["model_instance_ids"] = ["model:source", "model:source"]
    elif corruption == "components_not_list":
        payload["component_unit_instance_ids"] = None
    elif corruption == "empty_component_ids":
        payload["component_unit_instance_ids"] = []
    elif corruption == "duplicate_objective":
        raw_witnesses.append(deepcopy(raw_witnesses[0]))
    elif corruption == "payload_fields":
        payload["forged"] = True
    else:
        raise AssertionError(f"unsupported proximity witness corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        RulesUnitObjectiveProximityWitness.from_payload(payload)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("component_ids_not_tuple", "component_unit_instance_ids must be a tuple"),
        ("witnesses_not_tuple", "objective_marker_witnesses must be a tuple"),
        ("untyped_witness", "objective_marker_witnesses must contain typed witnesses"),
    ],
)
def test_objective_proximity_witness_constructor_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    objective_witnesses: object = []
    component_ids: object = ("unit:source",)
    if corruption == "untyped_witness":
        objective_witnesses = (object(),)
    elif corruption == "component_ids_not_tuple":
        component_ids = []

    with pytest.raises(GameLifecycleError, match=expected_error):
        RulesUnitObjectiveProximityWitness(
            rules_unit_instance_id="rules-unit:source",
            component_unit_instance_ids=cast(tuple[str, ...], component_ids),
            objective_marker_witnesses=cast(
                tuple[ObjectiveMarkerModelWitness, ...],
                objective_witnesses,
            ),
        )


@pytest.mark.parametrize(
    ("token", "expected_error"),
    [
        (None, "Primary unattributed destruction cause must be a string"),
        ("forged", "Primary unattributed destruction cause is unsupported"),
    ],
)
def test_primary_unattributed_destruction_cause_token_fails_closed(
    token: object,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        primary_unattributed_destruction_cause_from_token(token)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("unattributed_destroyer", "cannot identify a destroyer"),
        ("destroyer_drift", "destroying-player attribution drift"),
        ("player_only_witness", "cannot carry a source-unit objective witness"),
        ("source_witness_missing", "requires its exact objective proximity witness"),
        ("terrain_ids_not_tuple", "started_turn_terrain_feature_ids must be a tuple"),
        ("terrain_ids_duplicate", "started_turn_terrain_feature_ids must not contain duplicates"),
        ("untyped_attribution", "attribution must be ModelDestructionAttribution"),
        ("untyped_witness", "source objective witness must be typed"),
        ("battle_round", "battle_round must be a positive integer"),
    ],
)
def test_primary_unit_destruction_evidence_constructor_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    player_only = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=None,
        source_model_instance_id=None,
    )
    source_attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id="rules-unit:source",
        source_model_instance_id="model:source",
    )
    witness = RulesUnitObjectiveProximityWitness(
        rules_unit_instance_id="rules-unit:source",
        component_unit_instance_ids=("unit:source",),
        objective_marker_witnesses=(),
    )
    parameters: dict[str, Any] = {
        "destruction_id": "destruction:validation",
        "battle_round": 2,
        "active_player_id": "player-a",
        "destroying_player_id": None,
        "destroyed_player_id": "player-b",
        "destroyed_unit_instance_id": "unit:destroyed",
        "destruction_attribution": None,
        "source_rules_unit_objective_proximity_witness": None,
        "started_turn_terrain_feature_ids": (),
        "started_turn_objective_marker_ids": (),
    }
    if corruption == "unattributed_destroyer":
        parameters["destroying_player_id"] = "player-a"
    elif corruption == "destroyer_drift":
        parameters["destroying_player_id"] = "player-b"
        parameters["destruction_attribution"] = player_only
    elif corruption == "player_only_witness":
        parameters["destroying_player_id"] = "player-a"
        parameters["destruction_attribution"] = player_only
        parameters["source_rules_unit_objective_proximity_witness"] = witness
    elif corruption == "source_witness_missing":
        parameters["destroying_player_id"] = "player-a"
        parameters["destruction_attribution"] = source_attribution
    elif corruption == "terrain_ids_not_tuple":
        parameters["started_turn_terrain_feature_ids"] = []
    elif corruption == "terrain_ids_duplicate":
        parameters["started_turn_terrain_feature_ids"] = ("terrain:a", "terrain:a")
    elif corruption == "untyped_attribution":
        parameters["destruction_attribution"] = object()
    elif corruption == "untyped_witness":
        parameters["source_rules_unit_objective_proximity_witness"] = object()
    elif corruption == "battle_round":
        parameters["battle_round"] = 0
    else:
        raise AssertionError(f"unsupported destruction evidence corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        PrimaryUnitDestructionEvidence(**parameters)


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("turn_order_not_tuple", "turn_order must be a tuple"),
        ("turn_order_duplicate", "turn_order must not contain duplicates"),
        ("turn_order_short", "turn_order must contain at least 2 values"),
        ("active_unknown", "active player is not in turn_order"),
        ("scorer_unknown", "scoring player is not in turn_order"),
        ("scorer_not_active", "scoring player must be the active player"),
        ("evidence_not_tuple", "Primary destruction evidence must be a tuple"),
        ("evidence_untyped", "must contain typed evidence rows"),
        ("evidence_duplicate", "must not duplicate destruction occurrences"),
        ("evidence_unknown_player", "destruction player is not in turn_order"),
        ("no_previous_turn", "Previous player turn does not exist"),
    ],
)
def test_cross_turn_destruction_comparison_fails_closed(
    corruption: str,
    expected_error: str,
) -> None:
    evidence = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:comparison",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id=None,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="unit:destroyed",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    turn_order: object = ("player-a", "player-b")
    battle_round = 2
    active_player_id = "player-a"
    scoring_player_id = "player-a"
    rows: object = (evidence,)
    if corruption == "turn_order_not_tuple":
        turn_order = ["player-a", "player-b"]
    elif corruption == "turn_order_duplicate":
        turn_order = ("player-a", "player-a")
    elif corruption == "turn_order_short":
        turn_order = ("player-a",)
    elif corruption == "active_unknown":
        active_player_id = "player-c"
    elif corruption == "scorer_unknown":
        scoring_player_id = "player-c"
    elif corruption == "scorer_not_active":
        scoring_player_id = "player-b"
    elif corruption == "evidence_not_tuple":
        rows = [evidence]
    elif corruption == "evidence_untyped":
        rows = (object(),)
    elif corruption == "evidence_duplicate":
        rows = (evidence, evidence)
    elif corruption == "evidence_unknown_player":
        rows = (replace(evidence, destroyed_player_id="player-c"),)
    elif corruption == "no_previous_turn":
        battle_round = 1
    else:
        raise AssertionError(f"unsupported cross-turn corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        cross_turn_destruction_comparison_evidence(
            turn_order=cast(tuple[str, ...], turn_order),
            battle_round=battle_round,
            active_player_id=active_player_id,
            scoring_player_id=scoring_player_id,
            destruction_evidence=cast(tuple[PrimaryUnitDestructionEvidence, ...], rows),
        )


@pytest.mark.parametrize(
    ("operation", "expected_error"),
    [
        ("negative_score", "score_count must be a non-negative integer"),
        ("opponent_setup", "Opponent-home scoring requires MissionSetup"),
        ("opponent_player", "Opponent-home scoring player is not in MissionSetup"),
        ("home_setup", "Home objective lookup requires MissionSetup"),
        ("home_player", "Home objective player is not in MissionSetup"),
    ],
)
def test_primary_scoring_condition_input_validation_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    operation: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_invalid_primary_scoring_operation(
            mission_setup=battlefield_dominance_setup,
            operation=operation,
        )


def _run_invalid_primary_scoring_operation(
    *,
    mission_setup: MissionSetup,
    operation: str,
) -> object:
    if operation == "negative_score":
        return primary_score_count_evidence(score_count=-1)
    if operation == "opponent_setup":
        return opponent_home_control_evidence(
            mission_setup=cast(MissionSetup, object()),
            player_id="player-a",
            controlled_objective_ids=(),
        )
    if operation == "opponent_player":
        return opponent_home_control_evidence(
            mission_setup=mission_setup,
            player_id="player-c",
            controlled_objective_ids=(),
        )
    if operation == "home_setup":
        return home_objective_ids(cast(MissionSetup, object()), player_id="player-a")
    if operation == "home_player":
        return home_objective_ids(mission_setup, player_id="player-c")
    raise AssertionError(f"unsupported Primary scoring validation operation: {operation}")


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("record", "requires an ObjectiveControlRecord"),
        ("mission_setup", "requires MissionSetup"),
        ("turn_order_not_tuple", "turn_order must be a tuple"),
        ("turn_order_duplicate", "turn_order must not contain duplicates"),
        ("turn_order_count", "turn_order must contain exactly two players"),
        ("turn_order_setup", "turn_order must match MissionSetup players"),
        ("player", "player is missing from turn_order"),
        ("active_player", "active player is missing from turn_order"),
        ("end_of_battle", "end_of_battle must be a bool"),
        ("inactive_player", "must evaluate for the active player"),
        ("destruction_not_tuple", "destruction evidence must be a tuple"),
        ("destruction_untyped", "destruction evidence must contain typed rows"),
        ("destruction_duplicate", "must not duplicate occurrences"),
        ("destruction_player", "destruction evidence references an unknown player"),
        ("destruction_future", "cannot come from a future battle round"),
        ("spatial_untyped", "spatial evidence must be typed evidence"),
        ("spatial_player", "spatial evidence belongs to another player"),
        ("turn_start_objective", "turn-start evidence references an unknown objective"),
        ("destruction_objective", "destruction evidence references an unknown objective"),
        ("control_player", "objective control references an unknown controlling player"),
        ("score_player", "objective control score references an unknown player"),
        ("contribution_player", "objective contribution references an unknown player"),
    ],
)
def test_primary_scoring_condition_context_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    corruption: str,
    expected_error: str,
) -> None:
    with pytest.raises(GameLifecycleError, match=expected_error):
        _run_primary_scoring_context_corruption(
            mission_setup=battlefield_dominance_setup,
            corruption=corruption,
        )


def _run_primary_scoring_context_corruption(
    *,
    mission_setup: MissionSetup,
    corruption: str,
) -> None:
    typed_record = _control_record(mission_setup, battle_round=2)
    evidence = PrimaryUnitDestructionEvidence(
        destruction_id="destruction:context-validation",
        battle_round=2,
        active_player_id="player-a",
        destroying_player_id=None,
        destroyed_player_id="player-b",
        destroyed_unit_instance_id="unit:context-validation",
        destruction_attribution=None,
        source_rules_unit_objective_proximity_witness=None,
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
    )
    parameters: dict[str, Any] = {
        "record": typed_record,
        "mission_setup": mission_setup,
        "turn_order": ("player-a", "player-b"),
        "player_id": "player-a",
        "turn_start_controlled_objective_ids": None,
        "destruction_evidence": (),
        "spatial_evidence": None,
        "end_of_battle": False,
    }
    if corruption == "record":
        parameters["record"] = object()
    elif corruption == "mission_setup":
        parameters["mission_setup"] = object()
    elif corruption == "turn_order_not_tuple":
        parameters["turn_order"] = ["player-a", "player-b"]
    elif corruption == "turn_order_duplicate":
        parameters["turn_order"] = ("player-a", "player-a")
    elif corruption == "turn_order_count":
        parameters["turn_order"] = ("player-a",)
    elif corruption == "turn_order_setup":
        parameters["turn_order"] = ("player-a", "player-c")
    elif corruption == "player":
        parameters["player_id"] = "player-c"
    elif corruption == "active_player":
        parameters["record"] = replace(typed_record, active_player_id="player-c")
    elif corruption == "end_of_battle":
        parameters["end_of_battle"] = 1
    elif corruption == "inactive_player":
        parameters["player_id"] = "player-b"
    elif corruption == "destruction_not_tuple":
        parameters["destruction_evidence"] = [evidence]
    elif corruption == "destruction_untyped":
        parameters["destruction_evidence"] = (object(),)
    elif corruption == "destruction_duplicate":
        parameters["destruction_evidence"] = (evidence, evidence)
    elif corruption == "destruction_player":
        parameters["destruction_evidence"] = (replace(evidence, destroyed_player_id="player-c"),)
    elif corruption == "destruction_future":
        parameters["destruction_evidence"] = (replace(evidence, battle_round=3),)
    elif corruption == "spatial_untyped":
        parameters["spatial_evidence"] = object()
    elif corruption == "spatial_player":
        parameters["spatial_evidence"] = replace(
            _spatial_evidence(
                record=typed_record,
                opponent_territory_ids=_territory_objective_ids(
                    mission_setup,
                    owner_role="defender",
                ),
            ),
            player_id="player-b",
        )
    elif corruption == "turn_start_objective":
        parameters["turn_start_controlled_objective_ids"] = ("objective:forged",)
    elif corruption == "destruction_objective":
        parameters["destruction_evidence"] = (
            replace(evidence, started_turn_objective_marker_ids=("objective:forged",)),
        )
    elif corruption in {"control_player", "score_player", "contribution_player"}:
        result = typed_record.results[0]
        if corruption == "control_player":
            result = replace(
                result,
                status=ObjectiveControlStatus.CONTROLLED,
                controlled_by_player_id="player-c",
                scores=(ObjectiveControlScore(player_id="player-c", score=1),),
            )
        elif corruption == "score_player":
            result = replace(
                result,
                status=ObjectiveControlStatus.CONTROLLED,
                controlled_by_player_id="player-a",
                scores=(
                    ObjectiveControlScore(player_id="player-a", score=1),
                    ObjectiveControlScore(player_id="player-c", score=0),
                ),
            )
        else:
            result = replace(
                result,
                contributors=(
                    ObjectiveControlContribution(
                        player_id="player-c",
                        unit_instance_id="unit:forged",
                        model_instance_id="model:forged",
                        objective_control=1,
                        effective_objective_control=1,
                        battle_shocked=False,
                        horizontal_distance_inches=0.0,
                        vertical_gap_inches=0.0,
                    ),
                ),
            )
        parameters["record"] = replace(
            typed_record,
            results=(result, *typed_record.results[1:]),
        )
    else:
        raise AssertionError(f"unsupported Primary scoring context corruption: {corruption}")
    context = PrimaryScoringConditionContext(**parameters)
    if corruption == "inactive_player":
        evaluate_primary_scoring_condition(
            condition="control_one_or_more_central_objectives",
            context=context,
        )


def test_primary_scoring_condition_evaluation_fails_closed_on_typed_context_drift(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    record = _control_record(battlefield_dominance_setup, battle_round=2)
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=battlefield_dominance_setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )
    with pytest.raises(GameLifecycleError, match="requires a typed context"):
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective",
            context=cast(PrimaryScoringConditionContext, object()),
        )
    no_territory_setup = replace(
        battlefield_dominance_setup,
        battlefield_regions=tuple(
            region
            for region in battlefield_dominance_setup.battlefield_regions
            if region.region_kind is not BattlefieldRegionKind.TERRITORY
        ),
    )
    no_territory_context = replace(context, mission_setup=no_territory_setup)
    with pytest.raises(GameLifecycleError, match="exactly one directed territory"):
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective_in_opponent_territory",
            context=replace(
                no_territory_context,
                spatial_evidence=_spatial_evidence(
                    record=record,
                    opponent_territory_ids=(),
                ),
            ),
        )
    spatial = _spatial_evidence(
        record=record,
        opponent_territory_ids=("objective:forged",),
    )
    with pytest.raises(GameLifecycleError, match="opponent-territory objectives drifted"):
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective_in_opponent_territory",
            context=replace(context, spatial_evidence=spatial),
        )


def test_primary_scoring_condition_direct_count_and_same_round_previous_turn(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    mission_setup = battlefield_dominance_setup
    controlled_id = mission_setup.objective_markers[0].objective_marker_id
    record = _control_record(
        mission_setup,
        battle_round=2,
        controlled_by_a=(controlled_id,),
    )
    context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=mission_setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )

    assert (
        evaluate_primary_scoring_condition(
            condition="each_controlled_objective",
            context=context,
        )["score_count"]
        == 1
    )
    comparison = cross_turn_destruction_comparison_evidence(
        turn_order=("player-a", "player-b"),
        battle_round=2,
        active_player_id="player-b",
        scoring_player_id="player-b",
        destruction_evidence=(),
    )
    assert comparison["previous_turn_battle_round"] == 2
    assert comparison["previous_turn_active_player_id"] == "player-a"


@pytest.mark.parametrize(
    ("corruption", "expected_error"),
    [
        ("event_log", "Primary historical evidence requires EventLog"),
        ("objective_state", "Primary turn-start event requires typed objective evidence"),
        ("position_snapshot", "Primary turn-start event requires a typed position snapshot"),
        (
            "game_id",
            "Primary turn-start objective and position evidence occurrence drift",
        ),
        (
            "active_player_id",
            "Primary turn-start objective and position evidence occurrence drift",
        ),
        (
            "battle_round",
            "Primary turn-start objective and position evidence occurrence drift",
        ),
    ],
)
def test_primary_turn_start_historical_event_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    corruption: str,
    expected_error: str,
) -> None:
    objective_state, position_snapshot, _destruction = _primary_historical_evidence_fixture(
        battlefield_dominance_setup
    )
    event_log = EventLog()
    if corruption == "event_log":
        event_log = cast(EventLog, object())
    elif corruption == "objective_state":
        objective_state = cast(PrimaryObjectiveTurnStartState, object())
    elif corruption == "position_snapshot":
        position_snapshot = cast(PrimaryRulesUnitTurnStartSnapshot, object())
    elif corruption == "game_id":
        position_snapshot = replace(position_snapshot, game_id="game:drifted")
    elif corruption == "active_player_id":
        position_snapshot = replace(position_snapshot, active_player_id="player-b")
    elif corruption == "battle_round":
        position_snapshot = replace(position_snapshot, battle_round=3)
    else:
        raise AssertionError(f"unsupported historical-event corruption: {corruption}")

    with pytest.raises(GameLifecycleError, match=expected_error):
        record_primary_turn_start_evidence_event(
            event_log=event_log,
            objective_state=objective_state,
            position_snapshot=position_snapshot,
        )


def test_primary_historical_events_record_exact_typed_evidence(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    objective_state, position_snapshot, destruction = _primary_historical_evidence_fixture(
        battlefield_dominance_setup
    )
    event_log = EventLog()

    turn_start_record = record_primary_turn_start_evidence_event(
        event_log=event_log,
        objective_state=objective_state,
        position_snapshot=position_snapshot,
    )
    destruction_record = record_primary_unit_destruction_event(
        event_log=event_log,
        destruction=destruction,
    )
    turn_start_payload = cast(dict[str, JsonValue], turn_start_record.payload)
    destruction_payload = cast(dict[str, JsonValue], destruction_record.payload)

    assert turn_start_record.event_type == PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT
    assert turn_start_payload["primary_objective_turn_start_state"] == objective_state.to_payload()
    assert destruction_record.event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
    assert destruction_payload["primary_unit_destruction_state"] == destruction.to_payload()

    with pytest.raises(
        GameLifecycleError,
        match="Primary unit destruction event requires typed destruction evidence",
    ):
        record_primary_unit_destruction_event(
            event_log=event_log,
            destruction=cast(PrimaryUnitDestructionState, object()),
        )


@pytest.mark.parametrize(
    ("cap_audit", "expected_error"),
    [
        ("invalid", "Primary VP transaction cap audit must be an object"),
        (
            {"requested_amount": 0, "applied_amount": 9},
            "Primary VP transaction cap audit requires positive requested_amount",
        ),
        (
            {"requested_amount": 9, "applied_amount": 8},
            "Primary VP transaction cap audit applied_amount drifted",
        ),
        (
            {"requested_amount": 8, "applied_amount": 9},
            "Primary VP transaction cap audit applied_amount exceeds requested_amount",
        ),
    ],
)
def test_primary_victory_point_transaction_cap_audit_fails_closed(
    battlefield_dominance_setup: MissionSetup,
    cap_audit: object,
    expected_error: str,
) -> None:
    _state, policy, boundary, state_evidence, award = _primary_vp_policy_fixture(
        battlefield_dominance_setup
    )
    metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    metadata["vp_cap_audit"] = cast(JsonValue, cap_audit)
    transaction = _primary_transaction_from_award(award=award, metadata=metadata)

    with pytest.raises(GameLifecycleError, match=expected_error):
        validate_primary_victory_point_transaction(
            policy=policy,
            transaction=transaction,
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
        )


def test_primary_victory_point_transaction_validates_cap_audit_and_ledger_uniqueness(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    _state, policy, boundary, state_evidence, award = _primary_vp_policy_fixture(
        battlefield_dominance_setup
    )
    metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    metadata["vp_cap_audit"] = {
        "requested_amount": award.amount,
        "applied_amount": award.amount,
    }
    transaction = _primary_transaction_from_award(award=award, metadata=metadata)

    assert (
        validate_primary_victory_point_transaction(
            policy=policy,
            transaction=transaction,
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
        ).scoring_rule_id
        == cast(dict[str, object], award.metadata)["scoring_rule_id"]
    )

    corrupted_metadata = deepcopy(metadata)
    corrupted_metadata["primary_scoring_state_evidence_hash"] = "0" * 64
    corrupted_transaction = replace(transaction, metadata=corrupted_metadata)
    with pytest.raises(
        GameLifecycleError,
        match="Primary VP scoring-state evidence identity drifted",
    ):
        validate_primary_victory_point_transaction(
            policy=policy,
            transaction=corrupted_transaction,
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
        )

    with pytest.raises(GameLifecycleError, match="VP ledger and policy player_id drift"):
        validate_victory_point_ledger_policy(
            policy=policy,
            ledger=VictoryPointLedger.initial(player_id="player-b"),
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
        )

    forged_audit_ledger = VictoryPointLedger(
        player_id="player-a",
        victory_points=transaction.amount,
        transactions=(transaction,),
    )
    with pytest.raises(
        GameLifecycleError,
        match="cap audit drifted from chronological ledger policy",
    ):
        validate_victory_point_ledger_policy(
            policy=policy,
            ledger=forged_audit_ledger,
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
        )

    canonical_transaction = replace(transaction, metadata=award.metadata)
    duplicate = replace(
        canonical_transaction,
        transaction_id="victory-point:player-a:round-02:000002",
    )
    ledger = VictoryPointLedger(
        player_id="player-a",
        victory_points=canonical_transaction.amount + duplicate.amount,
        transactions=(canonical_transaction, duplicate),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Primary VP ledger must not repeat a scoring rule at one boundary",
    ):
        validate_victory_point_ledger_policy(
            policy=policy,
            ledger=ledger,
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=("player-a", "player-b"),
        )


def test_primary_victory_point_evidence_registry_rejects_paired_tampering(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    state, policy, boundary, state_evidence, award = _primary_vp_policy_fixture(
        battlefield_dominance_setup
    )
    tampered_metadata = deepcopy(cast(dict[str, JsonValue], award.metadata))
    tampered_metadata["primary_scoring_state_evidence_id"] = (
        "primary-scoring-state-evidence:" + "0" * 64
    )
    tampered_metadata["primary_scoring_state_evidence_hash"] = "0" * 64
    tampered_award = replace(award, metadata=tampered_metadata)

    with pytest.raises(GameLifecycleError, match="authoritative record"):
        validate_primary_victory_point_award(
            policy=policy,
            award=tampered_award,
            objective_control_records=(boundary,),
            primary_scoring_state_evidence_records=(state_evidence,),
            turn_order=state.turn_order,
            expected_boundary_active_player_id="player-a",
        )

    record_primary_scoring_state_evidence(state=state, evidence=state_evidence)
    state.award_victory_points(award)
    payload = state.to_payload()
    assert payload["primary_scoring_state_evidence_records"] == [state_evidence.to_payload()]

    tampered_payload = deepcopy(payload)
    player_ledger = next(
        ledger
        for ledger in tampered_payload["victory_point_ledgers"]
        if ledger["player_id"] == "player-a"
    )
    transaction_metadata = cast(
        dict[str, JsonValue],
        player_ledger["transactions"][0]["metadata"],
    )
    transaction_metadata["primary_scoring_state_evidence_id"] = (
        "primary-scoring-state-evidence:" + "0" * 64
    )
    transaction_metadata["primary_scoring_state_evidence_hash"] = "0" * 64
    with pytest.raises(GameLifecycleError, match="authoritative record"):
        GameState.from_payload(tampered_payload)

    missing_evidence_payload = deepcopy(payload)
    missing_evidence_payload["primary_scoring_state_evidence_records"] = []
    with pytest.raises(GameLifecycleError, match="authoritative record"):
        GameState.from_payload(missing_evidence_payload)

    nested_tamper_payload = deepcopy(payload)
    witness = nested_tamper_payload["primary_scoring_state_evidence_records"][0][
        "current_rules_unit_position_witnesses"
    ][0]
    witness["owner_player_id"] = "player-b"
    with pytest.raises(GameLifecycleError, match="hash drifted"):
        GameState.from_payload(nested_tamper_payload)


def test_end_of_battle_territory_condition_is_spatial_and_fail_closed(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    record = _control_record(setup, battle_round=5)
    clear_context = PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        spatial_evidence=_spatial_evidence(
            record=record,
            opponent_territory_ids=_territory_objective_ids(
                setup,
                owner_role="defender",
            ),
        ),
        end_of_battle=True,
    )
    blocked_spatial = replace(
        cast(PrimaryScoringSpatialEvidence, clear_context.spatial_evidence),
        enemy_units_wholly_within_own_territory=(
            PrimaryTerritoryUnitWitness(
                rules_unit_instance_id="enemy-rules-unit:one",
                model_instance_ids=("enemy-model:one",),
            ),
        ),
    )

    clear = evaluate_primary_scoring_condition(
        condition="no_enemy_units_wholly_within_own_territory_end_of_battle",
        context=clear_context,
    )
    blocked = evaluate_primary_scoring_condition(
        condition="no_enemy_units_wholly_within_own_territory_end_of_battle",
        context=replace(clear_context, spatial_evidence=blocked_spatial),
    )

    assert clear["score_count"] == 1
    assert blocked["score_count"] == 0
    assert blocked["enemy_unit_instance_ids"] == ["enemy-rules-unit:one"]
    with pytest.raises(GameLifecycleError, match="requires spatial evidence"):
        evaluate_primary_scoring_condition(
            condition="no_enemy_units_wholly_within_own_territory_end_of_battle",
            context=replace(clear_context, spatial_evidence=None),
        )


def test_condition_named_time_windows_fail_closed_outside_their_window(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    attacker_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("attacker-home")
    )
    defender_home_id = next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id.endswith("defender-home")
    )
    non_home_ids = tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_marker_id != attacker_home_id
    )
    controlled_ids = (attacker_home_id, *non_home_ids)

    def context_for_round(battle_round: int) -> PrimaryScoringConditionContext:
        record = _control_record(
            setup,
            battle_round=battle_round,
            controlled_by_a=controlled_ids,
        )
        return PrimaryScoringConditionContext(
            record=record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
            spatial_evidence=_spatial_evidence(
                record=record,
                opponent_territory_ids=_territory_objective_ids(
                    setup,
                    owner_role="defender",
                ),
            ),
        )

    outside_window_cases = (
        ("each_non_home_objective_controlled_round_five", context_for_round(4)),
        (
            "control_more_objectives_than_opponent_first_and_second_battle_round",
            context_for_round(3),
        ),
        (
            "control_more_objectives_than_opponent_from_battle_round_two",
            context_for_round(1),
        ),
        ("control_two_or_more_objectives_from_battle_round_two", context_for_round(1)),
        ("each_non_home_objective_controlled_first_battle_round", context_for_round(2)),
        (
            "each_non_home_objective_controlled_battle_rounds_two_and_three",
            context_for_round(4),
        ),
        (
            "each_non_home_objective_controlled_battle_round_four_onwards",
            context_for_round(3),
        ),
        ("control_opponent_home_objective_end_of_battle", context_for_round(5)),
        (
            "no_enemy_units_wholly_within_own_territory_end_of_battle",
            context_for_round(5),
        ),
    )
    assert defender_home_id in controlled_ids
    for condition, context in outside_window_cases:
        evidence = evaluate_primary_scoring_condition(
            condition=condition,
            context=context,
        )
        assert evidence["score_count"] == 0, condition


def test_primary_condition_context_rejects_partial_or_drifted_evidence(
    battlefield_dominance_setup: MissionSetup,
) -> None:
    setup = battlefield_dominance_setup
    exact_record = _control_record(setup, battle_round=2)
    partial_record = replace(exact_record, results=exact_record.results[:-1])

    with pytest.raises(GameLifecycleError, match="exactly the MissionSetup objectives"):
        PrimaryScoringConditionContext(
            record=partial_record,
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
        )
    unsupported_result = ObjectiveControlResult.unsupported(
        objective_id=exact_record.results[0].objective_id,
        unsupported_reason="unsupported:test",
    )
    with pytest.raises(GameLifecycleError, match="unsupported objective-control"):
        PrimaryScoringConditionContext(
            record=replace(
                exact_record,
                results=(unsupported_result, *exact_record.results[1:]),
            ),
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
        )
    context = PrimaryScoringConditionContext(
        record=exact_record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )
    spatial = _spatial_evidence(
        record=exact_record,
        opponent_territory_ids=_territory_objective_ids(
            setup,
            owner_role="defender",
        ),
    )
    with pytest.raises(GameLifecycleError, match="spatial evidence context drift"):
        PrimaryScoringConditionContext(
            record=replace(
                exact_record,
                record_id="phase17n-primary-control-record:stale",
            ),
            mission_setup=setup,
            turn_order=("player-a", "player-b"),
            player_id="player-a",
            spatial_evidence=spatial,
        )
    under_provisioned = replace(
        spatial,
        requested_condition_ids=("each_controlled_objective_in_opponent_territory",),
        table_quarter_unit_witnesses=(),
        enemy_units_wholly_within_own_territory=(),
    )
    with pytest.raises(GameLifecycleError, match="was not provisioned"):
        evaluate_primary_scoring_condition(
            condition=(
                "three_or_more_friendly_units_wholly_within_three_different_table_quarters_"
                "not_within_six_of_center"
            ),
            context=PrimaryScoringConditionContext(
                record=exact_record,
                mission_setup=setup,
                turn_order=("player-a", "player-b"),
                player_id="player-a",
                spatial_evidence=under_provisioned,
            ),
        )
    with pytest.raises(GameLifecycleError, match="turn-start objective snapshot"):
        evaluate_primary_scoring_condition(
            condition="each_newly_controlled_non_home_objective_this_turn",
            context=context,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported primary scoring condition"):
        evaluate_primary_scoring_condition(
            condition="source_text_guess",
            context=context,
        )


def _primary_vp_policy_fixture(
    mission_setup: MissionSetup,
) -> tuple[
    GameState,
    MissionScoringPolicy,
    ObjectiveControlRecord,
    PrimaryScoringStateEvidence,
    VictoryPointAward,
]:
    controlled_by_a = tuple(
        marker.objective_marker_id
        for marker in mission_setup.objective_markers
        if marker.objective_marker_id.endswith(("attacker-home", "central", "east"))
    )
    boundary = _control_record(
        mission_setup,
        battle_round=2,
        controlled_by_a=controlled_by_a,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
    )
    policies = mission_scoring_policies_from_setup(mission_setup)
    policy = policies.policy_for_player("player-a")
    state, boundary, state_evidence = _primary_scoring_state_evidence(
        mission_setup=mission_setup,
        record=boundary,
    )
    award = next(
        candidate
        for candidate in policies.primary_awards_from_objective_control(
            record=boundary,
            authoritative_state=state,
        )
        if cast(dict[str, object], candidate.metadata)["scoring_rule_id"]
        == "battlefield-dominance-each-objective"
    )
    binding = validate_primary_victory_point_award(
        policy=policy,
        award=award,
        objective_control_records=(boundary,),
        primary_scoring_state_evidence_records=(state_evidence,),
        turn_order=("player-a", "player-b"),
        expected_boundary_active_player_id="player-a",
    )
    assert binding.scoring_rule_id == "battlefield-dominance-each-objective"
    return state, policy, boundary, state_evidence, award


def _primary_transaction_from_award(
    *,
    award: VictoryPointAward,
    metadata: JsonValue,
) -> VictoryPointTransaction:
    _ledger, transaction = VictoryPointLedger.initial(player_id=award.player_id).award(
        award,
        metadata=metadata,
    )
    return transaction


def _primary_historical_evidence_fixture(
    mission_setup: MissionSetup,
) -> tuple[
    PrimaryObjectiveTurnStartState,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryUnitDestructionState,
]:
    objective_record = _control_record(
        mission_setup,
        battle_round=2,
        timing=ObjectiveControlTiming.TURN_START,
        phase=BattlePhase.COMMAND,
    )
    objective_state = PrimaryObjectiveTurnStartState(
        state_id="primary-turn-start:historical-player-a:round-2",
        game_id=objective_record.game_id,
        player_id="player-a",
        active_player_id="player-a",
        battle_round=2,
        source_objective_control_record=objective_record,
        controlled_objective_ids=(),
        source_id="source:primary-turn-start:historical-player-a:round-2",
    )
    position_snapshot = PrimaryRulesUnitTurnStartSnapshot(
        snapshot_id="primary-position:historical-player-a:round-2",
        game_id=objective_record.game_id,
        active_player_id="player-a",
        battle_round=2,
        rules_unit_memberships=(),
        source_id="source:primary-position:historical-player-a:round-2",
    )
    destruction = PrimaryUnitDestructionState(
        destruction_id="primary-destruction:historical-coherency",
        game_id=objective_record.game_id,
        destroying_player_id=None,
        destruction_attribution=None,
        source_model_destroyed_event_id=None,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=("primary-departure:historical-coherency",),
        unattributed_cause=PrimaryUnattributedDestructionCause.UNIT_COHERENCY,
        source_mutation_id="end-turn-cleanup:historical-coherency",
        destroyed_player_id="player-b",
        active_player_id="player-a",
        battle_round=2,
        phase=BattlePhase.COMMAND.value,
        destroyed_unit_instance_id="enemy-unit:historical-coherency",
        started_turn_terrain_feature_ids=(),
        started_turn_objective_marker_ids=(),
        source_id="source:primary-destruction:historical-coherency",
    )
    return objective_state, position_snapshot, destruction


def _control_record(
    mission_setup: MissionSetup,
    *,
    battle_round: int,
    controlled_by_a: tuple[str, ...] = (),
    controlled_by_b: tuple[str, ...] = (),
    timing: ObjectiveControlTiming = ObjectiveControlTiming.TURN_END,
    phase: BattlePhase = BattlePhase.FIGHT,
) -> ObjectiveControlRecord:
    controlled_by_a_set = set(controlled_by_a)
    controlled_by_b_set = set(controlled_by_b)
    if controlled_by_a_set.intersection(controlled_by_b_set):
        raise AssertionError("test objective cannot be controlled by both players")
    results: list[ObjectiveControlResult] = []
    for marker in mission_setup.objective_markers:
        if marker.objective_marker_id in controlled_by_a_set:
            results.append(_controlled_result(marker.objective_marker_id, "player-a"))
        elif marker.objective_marker_id in controlled_by_b_set:
            results.append(_controlled_result(marker.objective_marker_id, "player-b"))
        else:
            results.append(
                ObjectiveControlResult(
                    objective_id=marker.objective_marker_id,
                    status=ObjectiveControlStatus.UNCONTROLLED,
                    controlled_by_player_id=None,
                    scores=(),
                )
            )
    return ObjectiveControlRecord(
        record_id=f"phase17n-primary-control-record:{battle_round}",
        game_id="phase17n-primary-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=timing,
        phase=phase.value,
        battlefield_id="phase17n-primary-battlefield",
        results=tuple(results),
    )


def _primary_scoring_state_evidence(
    *,
    mission_setup: MissionSetup,
    record: ObjectiveControlRecord,
) -> tuple[GameState, ObjectiveControlRecord, PrimaryScoringStateEvidence]:
    expected_results_by_objective_id = {
        result.objective_id: (result.status, result.controlled_by_player_id)
        for result in record.results
    }
    mission_markers_by_id = {
        marker.objective_marker_id: marker for marker in mission_setup.objective_markers
    }
    if set(expected_results_by_objective_id) != set(mission_markers_by_id):
        raise AssertionError(
            "Primary scoring evidence fixture requires one result per mission objective."
        )
    controlled_objective_ids_by_player: dict[str, list[str]] = {
        "player-a": [],
        "player-b": [],
    }
    for result in record.results:
        if result.status is ObjectiveControlStatus.UNCONTROLLED:
            continue
        if (
            result.status is not ObjectiveControlStatus.CONTROLLED
            or result.controlled_by_player_id not in controlled_objective_ids_by_player
        ):
            raise AssertionError(
                "Primary scoring evidence fixture supports controlled or uncontrolled "
                "mission objectives for the fixture players."
            )
        controlled_objective_ids_by_player[result.controlled_by_player_id].append(
            result.objective_id
        )
    if len(controlled_objective_ids_by_player["player-b"]) > 1:
        raise AssertionError(
            "Primary scoring evidence fixture provisions one player-b scoring unit."
        )
    state = battle_state(
        player_a_units=tuple(
            default_unit_selection(f"phase17n-primary-control-unit-{index + 1}")
            for index in range(max(1, len(controlled_objective_ids_by_player["player-a"])))
        )
    )
    if state.battlefield_state is None:
        raise AssertionError("Primary scoring evidence fixture requires battlefield state.")
    state.game_id = record.game_id
    state.mission_setup = mission_setup
    state.primary_objective_turn_start_states = []
    state.primary_terrain_trap_states = []
    state.primary_unit_destruction_states = []
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=mission_setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_id=record.battlefield_id,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    armies_by_player_id = {army.player_id: army for army in state.army_definitions}
    battlefield_state = state.battlefield_state
    for player_id in ("player-a", "player-b"):
        controlled_objective_ids = controlled_objective_ids_by_player[player_id]
        units = armies_by_player_id[player_id].units
        if len(controlled_objective_ids) > len(units):
            raise AssertionError(
                f"Primary scoring evidence fixture lacks {player_id} scoring units."
            )
        for index, unit in enumerate(units):
            placement = battlefield_state.unit_placement_by_id(unit.unit_instance_id)
            if index < len(controlled_objective_ids):
                marker = mission_markers_by_id[controlled_objective_ids[index]]
                anchor = (marker.x_inches, marker.y_inches, marker.z_inches)
            elif player_id == "player-a":
                anchor = (4.0, 4.0, 0.0)
            else:
                anchor = (
                    mission_setup.battlefield_width_inches - 4.0,
                    mission_setup.battlefield_depth_inches - 4.0,
                    0.0,
                )
            battlefield_state = battlefield_state.with_unit_placement(
                _primary_scoring_unit_placement_at_anchor(
                    placement,
                    anchor=anchor,
                )
            )
    state.battlefield_state = battlefield_state
    state.battle_round = record.battle_round
    state.active_player_id = record.active_player_id
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase(record.phase))
    authoritative_record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=record.timing,
            phase=BattlePhase(record.phase),
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        )
    )
    authoritative_results_by_objective_id = {
        result.objective_id: (result.status, result.controlled_by_player_id)
        for result in authoritative_record.results
    }
    if authoritative_results_by_objective_id != expected_results_by_objective_id:
        raise AssertionError(
            "Primary scoring evidence physical fixture did not resolve the requested "
            "objective controllers."
        )
    state.record_objective_control_record(authoritative_record)
    evidence = build_primary_scoring_state_evidence(
        state=state,
        record=authoritative_record,
        end_of_battle=False,
    )
    return state, authoritative_record, evidence


def _primary_scoring_unit_placement_at_anchor(
    placement: UnitPlacement,
    *,
    anchor: tuple[float, float, float],
) -> UnitPlacement:
    model_offsets = (
        (-1.4, -1.4),
        (1.4, -1.4),
        (0.0, 0.0),
        (-1.4, 1.4),
        (1.4, 1.4),
    )
    if len(placement.model_placements) != len(model_offsets):
        raise AssertionError("Primary scoring evidence fixture requires five-model scoring units.")
    anchor_x, anchor_y, anchor_z = anchor
    return placement.with_model_placements(
        tuple(
            model_placement.with_pose(
                Pose.at(
                    anchor_x + offset_x,
                    anchor_y + offset_y,
                    anchor_z,
                    facing_degrees=model_placement.pose.facing.degrees,
                )
            )
            for model_placement, (offset_x, offset_y) in zip(
                placement.model_placements,
                model_offsets,
                strict=True,
            )
        )
    )


def _controlled_result(objective_id: str, player_id: str) -> ObjectiveControlResult:
    return ObjectiveControlResult(
        objective_id=objective_id,
        status=ObjectiveControlStatus.CONTROLLED,
        controlled_by_player_id=player_id,
        scores=(ObjectiveControlScore(player_id=player_id, score=1),),
    )


def _territory_objective_ids(
    mission_setup: MissionSetup,
    *,
    owner_role: str,
) -> tuple[str, ...]:
    territory = next(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == owner_role
    )
    return tuple(
        marker.objective_marker_id
        for marker in mission_setup.objective_markers
        if territory.contains_point(marker.x_inches, marker.y_inches)
    )


def _spatial_evidence(
    *,
    record: ObjectiveControlRecord,
    opponent_territory_ids: tuple[str, ...],
) -> PrimaryScoringSpatialEvidence:
    return PrimaryScoringSpatialEvidence(
        game_id=record.game_id,
        battlefield_id=record.battlefield_id,
        battle_round=record.battle_round,
        active_player_id=record.active_player_id,
        phase=record.phase,
        timing=record.timing,
        objective_control_record_id=record.record_id,
        objective_control_record_hash=objective_control_record_hash(record),
        player_id="player-a",
        requested_condition_ids=tuple(sorted(PRIMARY_SCORING_SPATIAL_CONDITIONS)),
        table_quarter_unit_witnesses=tuple(
            sorted(
                (
                    PrimaryTableQuarterUnitWitness(
                        rules_unit_instance_id=f"friendly-rules-unit:{index}",
                        quarter_id=quarter_id,
                        model_instance_ids=(f"friendly-model:{index}",),
                    )
                    for index, quarter_id in enumerate(TABLE_QUARTER_IDS, start=1)
                ),
                key=lambda witness: (
                    witness.quarter_id,
                    witness.rules_unit_instance_id,
                ),
            )
        ),
        enemy_units_wholly_within_own_territory=(),
        opponent_territory_objective_ids=opponent_territory_ids,
    )


def test_phase17n_locate_and_deny_choice_uses_exact_terrain_sets_and_persists_markers() -> None:
    state = _phase17n_locate_choice_state()
    decisions = DecisionController()

    request = locate_and_deny_setup_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-locate-request",
    )
    assert request is not None
    assert request.actor_id == "player-a"
    assert DecisionRequest.from_payload(request.to_payload()) == request
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    assert choice.primary_mission_id == "primary-locate-and-deny"
    assert len(request.options) == comb(len(choice.legal_target_ids), 5)
    assert all(
        len(PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids) == 5
        for option in request.options
    )

    drifted = replace(request, actor_id="player-b")
    invalid = invalid_primary_mission_choice_request_status(
        state=state,
        decisions=decisions,
        request=drifted,
    )
    assert invalid is not None
    assert cast(dict[str, object], invalid.payload)["invalid_reason"] == (
        "primary_mission_choice_request_drift"
    )

    result = DecisionResult.for_request(
        result_id="phase17n-locate-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    markers = state.primary_mission_progress_state.markers
    assert len(markers) == 5
    assert all(marker.owner_player_id == "player-a" for marker in markers)
    assert all(marker.marker_kind == PRIMARY_OPERATION_MARKER_KIND for marker in markers)
    assert all(marker.status is PrimaryMissionMarkerStatus.ACTIVE for marker in markers)
    assert {marker.terrain_feature_id for marker in markers} == set(
        PrimaryMissionChoiceData.from_payload(result.payload).selected_target_ids
    )
    assert (
        locate_and_deny_setup_choice_request(
            state=state,
            decisions=decisions,
            request_id="phase17n-locate-duplicate",
        )
        is None
    )
    assert decisions.event_log.records[-1].event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
    assert EventLog.from_payload(decisions.event_log.to_payload()).to_payload() == (
        decisions.event_log.to_payload()
    )


def test_phase17n_locate_restore_rejects_consistently_omitted_required_marker() -> None:
    state = _phase17n_locate_choice_state()
    decisions = DecisionController()
    request = locate_and_deny_setup_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-locate-forgery-request",
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17n-locate-forgery-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    event = decisions.event_log.records[-1]
    payload = dict(cast(dict[str, JsonValue], event.payload))
    choice = PrimaryMissionChoiceData.from_payload(payload["choice"])
    selected_target_ids = choice.selected_target_ids[:-1]
    retained_markers = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.terrain_feature_id in selected_target_ids
    )
    payload["choice"] = validate_json_value(
        replace(
            choice,
            selected_target_ids=selected_target_ids,
        ).to_payload()
    )
    payload["created_markers"] = validate_json_value(
        [
            marker_payload
            for marker_payload in cast(list[JsonValue], payload["created_markers"])
            if cast(dict[str, JsonValue], marker_payload)["terrain_feature_id"]
            in selected_target_ids
        ]
    )
    forged_state = deepcopy(state)
    assert forged_state.mission_setup is not None
    forged_state.battlefield_state = BattlefieldRuntimeState(
        battlefield_id="phase17n-locate-forgery-battlefield",
        battlefield_width_inches=forged_state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=forged_state.mission_setup.battlefield_depth_inches,
        placed_armies=(),
        terrain_features=forged_state.mission_setup.terrain_features,
    )
    forged_state.primary_mission_progress_state = replace(
        state.primary_mission_progress_state,
        markers=retained_markers,
    )
    forged_event = replace(event, payload=validate_json_value(payload))

    with pytest.raises(
        GameLifecycleError,
        match="Locate and Deny choice policy reconstruction drifted",
    ):
        validate_primary_mission_progress_state(
            forged_state,
            event_records=(*decisions.event_log.records[:-1], forged_event),
            decision_records=decisions.records,
        )


def test_phase17n_punishment_choice_supports_preferred_fallback_and_empty_candidates() -> None:
    state, decisions, enemy_ids = _phase17n_punishment_choice_state()
    fallback_state = deepcopy(state)
    _phase17n_clear_turn_start_contributors(fallback_state)

    fallback_request = punishment_choice_request(
        state=fallback_state,
        decisions=DecisionController(),
        request_id="phase17n-punishment-fallback",
    )
    assert fallback_request is not None
    fallback_choice = PrimaryMissionChoiceData.from_payload(fallback_request.payload)
    assert fallback_choice.used_fallback_candidates
    assert fallback_choice.legal_target_ids == enemy_ids
    assert len(fallback_request.options) == len(enemy_ids)
    assert all(
        len(PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids) == 1
        for option in fallback_request.options
    )

    empty_state = deepcopy(fallback_state)
    assert empty_state.battlefield_state is not None
    battlefield = empty_state.battlefield_state
    for enemy_id in enemy_ids:
        placement = battlefield.unit_placement_by_id(enemy_id)
        battlefield = battlefield.with_removed_models(
            tuple(
                model_placement.model_instance_id for model_placement in placement.model_placements
            )
        )
    empty_state.battlefield_state = battlefield
    _phase17n_refresh_turn_start_snapshot(empty_state)
    empty_decisions = DecisionController()
    assert (
        punishment_choice_request(
            state=empty_state,
            decisions=empty_decisions,
            request_id="phase17n-punishment-empty",
        )
        is None
    )
    automatic = empty_state.primary_mission_progress_state.condemned_selections[0]
    assert automatic.candidate_rules_unit_instance_ids == ()
    assert automatic.selected_rules_unit_instance_ids == ()
    automatic_event = empty_decisions.event_log.records[-1]
    assert automatic_event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
    assert cast(dict[str, object], automatic_event.payload)["automatic"] is True

    request = punishment_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-punishment-request",
    )
    assert request is not None
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    assert not choice.used_fallback_candidates
    assert choice.legal_target_ids == enemy_ids
    assert sorted(
        len(PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids)
        for option in request.options
    ) == [1, 1, 1, 2, 2, 2, 3]
    selected_option = next(
        option
        for option in request.options
        if len(PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids) == 3
    )
    result = DecisionResult.for_request(
        result_id="phase17n-punishment-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    selection = state.primary_mission_progress_state.condemned_selections[0]
    assert selection.selected_rules_unit_instance_ids == enemy_ids
    assert (selection.minimum_selection_count, selection.maximum_selection_count) == (1, 3)
    assert (
        PrimaryMissionProgressState.from_payload(state.primary_mission_progress_state.to_payload())
        == state.primary_mission_progress_state
    )
    assert (
        punishment_choice_request(
            state=state,
            decisions=decisions,
            request_id="phase17n-punishment-duplicate",
        )
        is None
    )


def test_phase17n_punishment_restore_uses_turn_start_presence_after_candidate_departure() -> None:
    state, decisions, enemy_ids = _phase17n_punishment_choice_state()
    request = punishment_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-punishment-late-restore-request",
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17n-punishment-late-restore-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    assert state.battlefield_state is not None
    departed_unit_id = enemy_ids[-1]
    placement = state.battlefield_state.unit_placement_by_id(departed_unit_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    state.battlefield_state = state.battlefield_state.without_unit_placement(departed_unit_id)
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=departed_unit_id,
        affected_component_unit_instance_ids=(departed_unit_id,),
        departed_component_unit_instance_ids=(departed_unit_id,),
        removed_model_instance_ids=removed_model_ids,
        removal_kind=BattlefieldRemovalKind.TEMPORARILY_REMOVED,
        occurrence_id="phase17n-punishment-later-departure",
        source_id="phase17n-punishment-later-departure-source",
    )
    assert departure is not None
    record_primary_battlefield_departure_event(
        event_log=decisions.event_log,
        departure=departure,
    )

    restored_state = GameState.from_payload(state.to_payload())
    restored_log = EventLog.from_payload(decisions.event_log.to_payload())
    validate_primary_mission_progress_state(
        restored_state,
        event_records=restored_log.records,
        decision_records=decisions.records,
    )
    assert (
        restored_state.primary_mission_progress_state.condemned_selections[
            0
        ].candidate_rules_unit_instance_ids
        == enemy_ids
    )


def test_phase17n_punishment_pending_choice_rejects_attached_unit_split() -> None:
    state, decisions, attached_id, component_ids = _phase17n_punishment_attached_choice_state()
    request = punishment_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-punishment-attached-split-request",
    )
    assert request is not None
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    assert attached_id in choice.legal_target_ids
    assert not set(component_ids).intersection(choice.legal_target_ids)
    progress_before = state.primary_mission_progress_state

    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-b",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=component_ids,
        event_log=decisions.event_log,
    )
    invalid = invalid_primary_mission_choice_request_status(
        state=state,
        decisions=decisions,
        request=request,
    )

    assert invalid is not None
    assert cast(dict[str, JsonValue], invalid.payload)["invalid_reason"] == (
        "primary_mission_choice_request_drift"
    )
    assert state.primary_mission_progress_state == progress_before


def test_phase17n_punishment_restore_rejects_consistently_omitted_candidate() -> None:
    state, decisions, _enemy_ids = _phase17n_punishment_choice_state()
    request = punishment_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-punishment-forgery-request",
    )
    assert request is not None
    option = next(
        value
        for value in request.options
        if len(PrimaryMissionChoiceData.from_payload(value.payload).selected_target_ids) == 1
    )
    result = DecisionResult.for_request(
        result_id="phase17n-punishment-forgery-result",
        request=request,
        selected_option_id=option.option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    selection = state.primary_mission_progress_state.condemned_selections[0]
    omitted_id = next(
        candidate_id
        for candidate_id in reversed(selection.candidate_rules_unit_instance_ids)
        if candidate_id not in selection.selected_rules_unit_instance_ids
    )
    forged_candidates = tuple(
        candidate_id
        for candidate_id in selection.candidate_rules_unit_instance_ids
        if candidate_id != omitted_id
    )
    forged_selection_id = primary_condemned_selection_id(
        game_id=selection.game_id,
        owner_player_id=selection.owner_player_id,
        mission_id=selection.mission_id,
        source_rule_id=selection.source_rule_id,
        source_descriptor_id=selection.source_descriptor_id,
        battle_round=selection.battle_round,
        active_player_id=selection.active_player_id,
        candidate_policy_id=selection.candidate_policy_id,
        candidate_rules_unit_instance_ids=forged_candidates,
        candidate_evidence_ids=selection.candidate_evidence_ids,
        selected_rules_unit_instance_ids=selection.selected_rules_unit_instance_ids,
        minimum_selection_count=selection.minimum_selection_count,
        maximum_selection_count=len(forged_candidates),
        used_fallback_candidates=selection.used_fallback_candidates,
        selection_request_id=selection.selection_request_id,
        selection_result_id=selection.selection_result_id,
        source_event_id=selection.source_event_id,
    )
    forged_selection = replace(
        selection,
        selection_id=forged_selection_id,
        candidate_rules_unit_instance_ids=forged_candidates,
        maximum_selection_count=len(forged_candidates),
    )
    event = decisions.event_log.records[-1]
    payload = dict(cast(dict[str, JsonValue], event.payload))
    choice = PrimaryMissionChoiceData.from_payload(payload["choice"])
    payload["choice"] = validate_json_value(
        replace(choice, legal_target_ids=forged_candidates).to_payload()
    )
    payload["condemned_selection"] = validate_json_value(forged_selection.to_payload())
    forged_state = deepcopy(state)
    forged_state.primary_mission_progress_state = replace(
        state.primary_mission_progress_state,
        condemned_selections=(forged_selection,),
    )
    forged_event = replace(event, payload=validate_json_value(payload))

    with pytest.raises(GameLifecycleError, match="Condemned candidate reconstruction drifted"):
        validate_primary_mission_progress_state(
            forged_state,
            event_records=(*decisions.event_log.records[:-1], forged_event),
            decision_records=decisions.records,
        )


def test_phase17n_unrelated_primary_mission_boundaries_do_not_consume_request_ids() -> None:
    state = battle_state()
    decisions = DecisionController()
    assert state.active_player_id is not None
    assert state.mission_setup is not None
    assert (
        state.mission_setup.primary_mission_id_for_player(state.active_player_id)
        == "primary-immovable-object"
    )
    assert state.decision_request_count == 0

    BattleRoundFlow(phase_handlers={BattlePhase.COMMAND: CommandPhaseHandler()}).advance(
        state=state, decisions=decisions
    )
    assert state.decision_request_count == 0

    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    BattleRoundFlow(phase_handlers={BattlePhase.FIGHT: FightPhaseHandler()}).advance(
        state=state, decisions=decisions
    )
    assert state.decision_request_count == 0
    assert decisions.queue.pending_requests == ()


def test_phase17n_consecrate_choice_consumes_or_suppresses_each_designation() -> None:
    state, decisions, designation_id, target_id = _phase17n_consecrate_choice_state()
    declined_state = deepcopy(state)
    decline_decisions = DecisionController.from_payload(decisions.to_payload())
    request = consecrate_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-consecrate-request",
    )
    assert request is not None
    choices = tuple(
        PrimaryMissionChoiceData.from_payload(option.payload) for option in request.options
    )
    assert {choice.selected_target_ids for choice in choices} == {(), (target_id,)}
    selected_option = next(
        option
        for option in request.options
        if PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids == (target_id,)
    )
    result = DecisionResult.for_request(
        result_id="phase17n-consecrate-result",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    designation = state.primary_mission_progress_state.consecration_designations[0]
    assert designation.designation_id == designation_id
    assert designation.status is PrimaryConsecrationStatus.CONSUMED
    marker = state.primary_mission_progress_state.markers[0]
    choice_descriptor = primary_mission_choice_rule_for_id("consecrate-objective-at-turn-end")
    assert marker.objective_marker_id == target_id
    assert marker.marker_kind == PRIMARY_OPERATION_MARKER_KIND
    assert marker.source_designation_id == designation_id
    assert marker.source_destruction_id == designation.source_destruction_id
    assert marker.source_rule_id == choice_descriptor.source_id
    assert marker.source_descriptor_id == choice_descriptor.choice_rule_id
    restored_progress = PrimaryMissionProgressState.from_payload(
        state.primary_mission_progress_state.to_payload()
    )
    assert restored_progress == state.primary_mission_progress_state
    assert restored_progress.markers[0].marker_kind == PRIMARY_OPERATION_MARKER_KIND
    validate_primary_mission_progress_state(
        state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )

    consumer_state = deepcopy(state)
    _phase17n_enter_battle_turn_end(consumer_state, active_player_id="player-b")
    extract_action = _phase17n_completed_sensor_action(
        action_id="phase17n-consecrate-operation-marker-consumer",
        mission_action_id=SENSOR_SWEEP_EXTRACT_ACTION_ID,
        player_id="player-b",
        target_id=target_id,
    )
    consumer_state.mission_action_states = [extract_action]
    consumer_request = sensor_sweep_marker_removal_choice_request(
        state=consumer_state,
        decisions=DecisionController(),
        action_id=extract_action.action_id,
        request_id="phase17n-consecrate-operation-marker-consumer-request",
    )
    assert consumer_request is not None
    assert PrimaryMissionChoiceData.from_payload(consumer_request.payload).legal_target_ids == (
        marker.marker_id,
    )

    decline_request = consecrate_choice_request(
        state=declined_state,
        decisions=decline_decisions,
        request_id="phase17n-consecrate-decline-request",
    )
    assert decline_request is not None
    decline_option = next(
        option
        for option in decline_request.options
        if not PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids
    )
    decline_result = DecisionResult.for_request(
        result_id="phase17n-consecrate-decline-result",
        request=decline_request,
        selected_option_id=decline_option.option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=declined_state,
        decisions=decline_decisions,
        request=decline_request,
        result=decline_result,
    )
    declined = declined_state.primary_mission_progress_state.consecration_designations[0]
    assert declined.status is PrimaryConsecrationStatus.ACTIVE
    assert declined.was_resolved_for_turn(battle_round=1, active_player_id="player-a")
    validate_primary_mission_progress_state(
        declined_state,
        event_records=decline_decisions.event_log.records,
        decision_records=decline_decisions.records,
    )
    assert (
        consecrate_choice_request(
            state=declined_state,
            decisions=decline_decisions,
            request_id="phase17n-consecrate-suppressed",
        )
        is None
    )
    assert (
        punishment_choice_request(
            state=declined_state,
            decisions=decline_decisions,
            request_id="phase17n-nonmatching-punishment",
        )
        is None
    )


def test_phase17n_consecrate_restore_requires_decision_and_exact_boundary_evidence() -> None:
    state, decisions, _target_id = _phase17n_resolved_consecrate_choice_fixture(
        select_objective=True
    )

    with pytest.raises(
        GameLifecycleError,
        match="requires one authoritative DecisionRecord",
    ):
        validate_primary_mission_progress_state(
            state,
            event_records=decisions.event_log.records,
            decision_records=(),
        )

    records = list(decisions.event_log.records)
    choice_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
    )
    choice_event = records[choice_index]
    payload = dict(cast(dict[str, JsonValue], choice_event.payload))
    choice = PrimaryMissionChoiceData.from_payload(payload["choice"])
    forged_choice = replace(choice, evidence_ids=("forged-turn-end-record",))
    payload["choice"] = validate_json_value(forged_choice.to_payload())
    records[choice_index] = replace(
        choice_event,
        payload=validate_json_value(payload),
    )
    request_id = cast(str, payload["request_id"])
    request_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == "decision_requested"
        and cast(dict[str, JsonValue], event.payload).get("request_id") == request_id
    )
    request_event = records[request_index]
    request_payload = dict(cast(dict[str, JsonValue], request_event.payload))
    request_payload["payload"] = validate_json_value(
        replace(forged_choice, selected_target_ids=()).to_payload()
    )
    records[request_index] = replace(
        request_event,
        payload=validate_json_value(request_payload),
    )
    with pytest.raises(
        GameLifecycleError,
        match="cited objective-control record is unavailable",
    ):
        validate_primary_mission_progress_state(
            state,
            event_records=tuple(records),
        )


def test_phase17n_consecrate_restore_reconstructs_contributor_and_complete_legal_set() -> None:
    state, decisions, target_id = _phase17n_resolved_consecrate_choice_fixture(
        select_objective=True
    )
    choice_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
    )
    choice = PrimaryMissionChoiceData.from_payload(
        cast(dict[str, JsonValue], choice_event.payload)["choice"]
    )
    record_id = choice.evidence_ids[0]
    forged_state = deepcopy(state)
    record_index = next(
        index
        for index, record in enumerate(forged_state.objective_control_records)
        if record.record_id == record_id
    )
    record = forged_state.objective_control_records[record_index]
    target_result = next(result for result in record.results if result.objective_id == target_id)
    assert target_result.contributors
    wrong_unit_id = next(
        unit.unit_instance_id
        for army in forged_state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    wrong_contributors = tuple(
        replace(contributor, unit_instance_id=wrong_unit_id)
        for contributor in target_result.contributors
    )
    forged_result = ObjectiveControlResult.from_contributors(
        objective_id=target_id,
        contributors=wrong_contributors,
    )
    forged_state.objective_control_records[record_index] = replace(
        record,
        results=tuple(
            forged_result if result.objective_id == target_id else result
            for result in record.results
        ),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Consecrate choice policy reconstruction drifted",
    ):
        validate_primary_mission_progress_state(
            forged_state,
            event_records=decisions.event_log.records,
        )

    declined_state, decline_decisions, _target_id = _phase17n_resolved_consecrate_choice_fixture(
        select_objective=False
    )
    decline_records = list(decline_decisions.event_log.records)
    decline_index = next(
        index
        for index, event in enumerate(decline_records)
        if event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
    )
    decline_event = decline_records[decline_index]
    decline_payload = dict(cast(dict[str, JsonValue], decline_event.payload))
    decline_choice = PrimaryMissionChoiceData.from_payload(decline_payload["choice"])
    assert decline_choice.legal_target_ids
    assert not decline_choice.selected_target_ids
    forged_decline_choice = replace(decline_choice, legal_target_ids=())
    decline_payload["choice"] = validate_json_value(forged_decline_choice.to_payload())
    decline_records[decline_index] = replace(
        decline_event,
        payload=validate_json_value(decline_payload),
    )
    decline_request_id = cast(str, decline_payload["request_id"])
    decline_request_index = next(
        index
        for index, event in enumerate(decline_records)
        if event.event_type == "decision_requested"
        and cast(dict[str, JsonValue], event.payload).get("request_id") == decline_request_id
    )
    decline_request_event = decline_records[decline_request_index]
    decline_request_payload = dict(cast(dict[str, JsonValue], decline_request_event.payload))
    decline_request_payload["payload"] = validate_json_value(forged_decline_choice.to_payload())
    decline_records[decline_request_index] = replace(
        decline_request_event,
        payload=validate_json_value(decline_request_payload),
    )
    with pytest.raises(
        GameLifecycleError,
        match="Consecrate choice policy reconstruction drifted",
    ):
        validate_primary_mission_progress_state(
            declined_state,
            event_records=tuple(decline_records),
        )


def test_phase17n_consecrate_restore_rejects_omitted_turn_resolution() -> None:
    state, decisions, _target_id = _phase17n_resolved_consecrate_choice_fixture(
        select_objective=False
    )
    progress = state.primary_mission_progress_state
    designation = progress.consecration_designations[0]
    state.primary_mission_progress_state = replace(
        progress,
        consecration_designations=(
            replace(
                designation,
                last_resolved_battle_round=None,
                last_resolved_active_player_id=None,
                last_resolution_event_id=None,
                last_resolution_result_id=None,
            ),
        ),
    )
    omitted_choice_records = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type
        not in {
            "decision_requested",
            "decision_recorded",
            PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
        }
    )

    with pytest.raises(GameLifecycleError, match=r"Consecrate.*resolution"):
        validate_primary_mission_progress_state(
            state,
            event_records=omitted_choice_records,
            decision_records=(),
        )


def test_phase17n_consecrate_restore_rejects_omitted_required_designation() -> None:
    state, decisions, _designation_id, _target_id = _phase17n_consecrate_choice_state()
    progress = state.primary_mission_progress_state
    assert len(progress.consecration_designations) == 1
    assert len(state.primary_unit_destruction_states) == 1
    destruction = state.primary_unit_destruction_states[0]
    state.primary_mission_progress_state = replace(
        progress,
        consecration_designations=(),
    )
    retained_records = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type != "primary_consecration_unit_designated"
    )
    assert any(
        event.event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
        and cast(dict[str, JsonValue], event.payload).get("primary_unit_destruction_state")
        == destruction.to_payload()
        for event in retained_records
    )

    with pytest.raises(GameLifecycleError, match=r"Consecrate.*designation"):
        validate_primary_mission_progress_state(
            state,
            event_records=retained_records,
            decision_records=decisions.records,
            pending_decision_requests=(),
        )


def test_phase17n_consecrate_restore_rejects_wrong_subject_pending_choice() -> None:
    state, decisions, _designation_id, _target_id = _phase17n_consecrate_choice_state()
    request = consecrate_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-consecrate-wrong-subject-request",
    )
    assert request is not None
    base_choice = PrimaryMissionChoiceData.from_payload(request.payload)
    wrong_choice = replace(
        base_choice,
        subject_id="phase17n-unrelated-consecration-designation",
    )
    wrong_options = tuple(
        replace(
            option,
            option_id=primary_mission_choice_option_id(
                choice=wrong_choice,
                selected_ids=PrimaryMissionChoiceData.from_payload(
                    option.payload
                ).selected_target_ids,
            ),
            payload=validate_json_value(
                wrong_choice.with_selected_targets(
                    PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids
                ).to_payload()
            ),
        )
        for option in request.options
    )
    wrong_request = replace(
        request,
        payload=validate_json_value(wrong_choice.to_payload()),
        options=wrong_options,
    )
    decisions.request_decision(wrong_request)

    with pytest.raises(
        GameLifecycleError,
        match="Consecrate choice identity or battle context drifted",
    ):
        validate_primary_mission_progress_state(
            state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=decisions.queue.pending_requests,
        )


def test_phase17n_sensor_sweep_removes_policy_scoped_marker_and_tombstones_action() -> None:
    state = _phase17n_locate_choice_state()
    decisions = DecisionController()
    locate_request = locate_and_deny_setup_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-sensor-locate-setup",
    )
    assert locate_request is not None
    locate_result = DecisionResult.for_request(
        result_id="phase17n-sensor-locate-result",
        request=locate_request,
        selected_option_id=locate_request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=locate_request,
        result=locate_result,
    )
    _phase17n_enter_battle_turn_end(state, active_player_id="player-b")
    assert state.mission_setup is not None
    target_id = state.mission_setup.objective_markers[0].objective_marker_id
    extract_action = _phase17n_completed_sensor_action(
        action_id="phase17n-extract-sensor-action",
        mission_action_id=SENSOR_SWEEP_EXTRACT_ACTION_ID,
        player_id="player-b",
        target_id=target_id,
    )
    state.mission_action_states = [extract_action]

    friendly_state = deepcopy(state)
    _phase17n_enter_battle_turn_end(friendly_state, active_player_id="player-a")
    locate_action = _phase17n_completed_sensor_action(
        action_id="phase17n-locate-sensor-action",
        mission_action_id=SENSOR_SWEEP_LOCATE_ACTION_ID,
        player_id="player-a",
        target_id=target_id,
    )
    friendly_state.mission_action_states = [locate_action]
    friendly_request = sensor_sweep_marker_removal_choice_request(
        state=friendly_state,
        decisions=DecisionController(),
        action_id=locate_action.action_id,
        request_id="phase17n-locate-sensor-request",
    )
    assert friendly_request is not None
    assert len(friendly_request.options) == 5

    request = sensor_sweep_marker_removal_choice_request(
        state=state,
        decisions=decisions,
        action_id=extract_action.action_id,
        request_id="phase17n-extract-sensor-request",
    )
    assert request is not None
    assert request.actor_id == "player-b"
    assert len(request.options) == 5
    assert all(
        marker.owner_player_id == "player-a" and marker.mission_id == "primary-locate-and-deny"
        for marker in state.primary_mission_progress_state.markers
    )
    result = DecisionResult.for_request(
        result_id="phase17n-extract-sensor-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    removed = next(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.status is PrimaryMissionMarkerStatus.REMOVED
    )
    assert removed.removal_action_id == extract_action.action_id
    assert (
        sensor_sweep_marker_removal_choice_request(
            state=state,
            decisions=decisions,
            action_id=extract_action.action_id,
            request_id="phase17n-extract-sensor-duplicate",
        )
        is None
    )

    empty_state = deepcopy(state)
    empty_action = _phase17n_completed_sensor_action(
        action_id="phase17n-empty-sensor-action",
        mission_action_id=SENSOR_SWEEP_EXTRACT_ACTION_ID,
        player_id="player-b",
        target_id=target_id,
    )
    empty_state.mission_action_states = [empty_action]
    empty_state.primary_mission_progress_state = PrimaryMissionProgressState.empty()
    assert (
        sensor_sweep_marker_removal_choice_request(
            state=empty_state,
            decisions=DecisionController(),
            action_id=empty_action.action_id,
            request_id="phase17n-empty-sensor-request",
        )
        is None
    )


def test_phase17n_surveil_removes_operation_marker_after_heroic_intervention_move() -> None:
    state = battle_state()
    state.mission_setup = _phase17n_event_setup(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.CHARGE)
    assert state.mission_setup.primary_mission_id_for_player("player-b") == (
        "primary-surveil-the-foe"
    )
    assert state.battlefield_state is not None
    moving_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    objective = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    placement = state.battlefield_state.unit_placement_by_id(moving_unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            objective,
            offsets=((0.0, 0.0), (1.4, 0.0), (2.8, 0.0), (0.0, 1.4), (1.4, 1.4)),
        )
    )

    marker_mission_id = state.mission_setup.primary_mission_id_for_player("player-a")
    marker_source_rule_id = "phase17n-test:operation-marker-source"
    marker_source_descriptor_id = "phase17n-test:operation-marker-descriptor"
    marker_source_event_id = "phase17n-test:operation-marker-created"
    marker = PrimaryMissionMarkerState(
        marker_id=primary_mission_marker_id(
            game_id=state.game_id,
            owner_player_id="player-a",
            mission_id=marker_mission_id,
            source_rule_id=marker_source_rule_id,
            source_descriptor_id=marker_source_descriptor_id,
            marker_kind=PRIMARY_OPERATION_MARKER_KIND,
            anchor_kind=MarkerAnchorKind.OBJECTIVE,
            objective_marker_id=objective.objective_marker_id,
            terrain_feature_id=None,
            created_battle_round=1,
            created_phase=BattlePhase.COMMAND.value,
            created_active_player_id="player-a",
            source_event_id=marker_source_event_id,
            source_result_id=None,
            source_action_id=None,
            source_destruction_id=None,
            source_designation_id=None,
        ),
        game_id=state.game_id,
        owner_player_id="player-a",
        mission_id=marker_mission_id,
        source_rule_id=marker_source_rule_id,
        source_descriptor_id=marker_source_descriptor_id,
        marker_kind=PRIMARY_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=objective.objective_marker_id,
        terrain_feature_id=None,
        created_battle_round=1,
        created_phase=BattlePhase.COMMAND.value,
        created_active_player_id="player-a",
        source_event_id=marker_source_event_id,
        source_result_id=None,
        source_action_id=None,
        source_destruction_id=None,
        source_designation_id=None,
    )
    state.primary_mission_progress_state = state.primary_mission_progress_state.add_marker(marker)
    decisions = DecisionController()
    trigger = decisions.event_log.append(
        "heroic_intervention_charge_move_completed",
        {
            "game_id": state.game_id,
            "player_id": "player-b",
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "unit_instance_id": moving_unit.unit_instance_id,
        },
    )

    resolve_surveil_marker_removal_for_completed_moves(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.CHARGE,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    removed = state.primary_mission_progress_state.markers[0]
    assert removed.status is PrimaryMissionMarkerStatus.REMOVED
    assert removed.removal_event_id == trigger.event_id
    assert (
        removed.removal_source_id
        == primary_mission_state_rule_for_id(
            "surveil-remove-operation-markers-after-move"
        ).source_id
    )
    processed = cast(dict[str, JsonValue], decisions.event_log.records[-1].payload)
    assert decisions.event_log.records[-1].event_type == (
        "primary_surveil_move_marker_removal_resolved"
    )
    assert processed["moving_rules_unit_instance_id"] == moving_unit.unit_instance_id
    assert processed["removed_primary_mission_markers"] == [removed.to_payload()]
    assert (
        PrimaryMissionProgressState.from_payload(state.primary_mission_progress_state.to_payload())
        == state.primary_mission_progress_state
    )
    assert EventLog.from_payload(decisions.event_log.to_payload()).to_payload() == (
        decisions.event_log.to_payload()
    )


def test_phase17n_restore_authenticates_surveil_move_marker_removal() -> None:
    state, decisions = _phase17n_surveil_integrity_fixture()

    validate_primary_mission_progress_state(
        state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )
    validate_primary_mission_action_integrity(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )
    assert EventLog.from_payload(decisions.event_log.to_payload()).to_payload() == (
        decisions.event_log.to_payload()
    )


def test_phase17n_restore_rejects_arbitrary_surveil_removal_trigger() -> None:
    state, decisions = _phase17n_surveil_integrity_fixture()
    records = list(decisions.event_log.records)
    processed = records[-1]
    processed_payload = dict(cast(dict[str, JsonValue], processed.payload))
    trigger_id = cast(str, processed_payload["trigger_event_id"])
    trigger_index = next(
        index for index, record in enumerate(records) if record.event_id == trigger_id
    )
    records[trigger_index] = replace(
        records[trigger_index],
        event_type="phase17n_forged_non_move_event",
    )
    processed_payload["trigger_event_type"] = "phase17n_forged_non_move_event"
    records[-1] = replace(processed, payload=validate_json_value(processed_payload))

    with pytest.raises(GameLifecycleError, match="trigger type is invalid"):
        validate_primary_mission_progress_state(
            state,
            event_records=tuple(records),
            decision_records=decisions.records,
        )


def test_phase17n_restore_rejects_surveil_removal_of_own_operation_marker() -> None:
    state, decisions = _phase17n_surveil_integrity_fixture()
    removed = state.primary_mission_progress_state.markers[0]
    own_mission_id = cast(MissionSetup, state.mission_setup).primary_mission_id_for_player(
        "player-b"
    )
    own_marker = replace(
        removed,
        marker_id=primary_mission_marker_id(
            game_id=removed.game_id,
            owner_player_id="player-b",
            mission_id=own_mission_id,
            source_rule_id=removed.source_rule_id,
            source_descriptor_id=removed.source_descriptor_id,
            marker_kind=removed.marker_kind,
            anchor_kind=removed.anchor_kind,
            objective_marker_id=removed.objective_marker_id,
            terrain_feature_id=removed.terrain_feature_id,
            created_battle_round=removed.created_battle_round,
            created_phase=removed.created_phase,
            created_active_player_id=removed.created_active_player_id,
            source_event_id=removed.source_event_id,
            source_result_id=removed.source_result_id,
            source_action_id=removed.source_action_id,
            source_destruction_id=removed.source_destruction_id,
            source_designation_id=removed.source_designation_id,
        ),
        owner_player_id="player-b",
        mission_id=own_mission_id,
    )
    state.primary_mission_progress_state = replace(
        state.primary_mission_progress_state,
        markers=(own_marker,),
    )
    records = list(decisions.event_log.records)
    processed = records[-1]
    processed_payload = dict(cast(dict[str, JsonValue], processed.payload))
    processed_payload["removed_primary_mission_markers"] = validate_json_value(
        [own_marker.to_payload()]
    )
    records[-1] = replace(processed, payload=validate_json_value(processed_payload))

    with pytest.raises(GameLifecycleError, match="marker-removal set drifted"):
        validate_surveil_marker_removal_events(
            state=state,
            progress=state.primary_mission_progress_state,
            event_records=tuple(records),
        )


def test_phase17n_restore_rejects_consistent_surveil_witness_row_omission() -> None:
    state, decisions = _phase17n_surveil_integrity_fixture()
    records = list(decisions.event_log.records)
    processed = records[-1]
    payload = dict(cast(dict[str, JsonValue], processed.payload))
    witness = dict(
        cast(
            dict[str, JsonValue],
            payload["moving_rules_unit_objective_proximity_witness"],
        )
    )
    witness["objective_marker_witnesses"] = []
    payload["moving_rules_unit_objective_proximity_witness"] = witness
    payload["objective_marker_ids"] = []
    payload["removed_primary_mission_markers"] = []
    forged = replace(processed, payload=validate_json_value(payload))
    records[-1] = forged
    assert forged.history_token() != processed.history_token()

    with pytest.raises(GameLifecycleError, match="requires one processed event"):
        validate_primary_mission_progress_state(
            state,
            event_records=tuple(records),
            decision_records=decisions.records,
        )


@pytest.mark.parametrize("tamper", [("mover",), ("context",)])
def test_phase17n_restore_rejects_surveil_mover_or_context_drift(tamper: str) -> None:
    state, decisions = _phase17n_surveil_integrity_fixture()
    records = list(decisions.event_log.records)
    processed = records[-1]
    payload = dict(cast(dict[str, JsonValue], processed.payload))
    if tamper == "mover":
        payload["moving_rules_unit_instance_id"] = next(
            unit.unit_instance_id
            for army in state.army_definitions
            if army.player_id == "player-a"
            for unit in army.units
        )
        expected = "mover drifted"
    else:
        payload["phase"] = BattlePhase.SHOOTING.value
        expected = "battle context drifted"
    records[-1] = replace(processed, payload=validate_json_value(payload))

    with pytest.raises(GameLifecycleError, match=expected):
        validate_primary_mission_progress_state(
            state,
            event_records=tuple(records),
            decision_records=decisions.records,
        )


@pytest.mark.parametrize("tamper", [("partial",), ("extra",)])
def test_phase17n_restore_rejects_inexact_surveil_removal_set(tamper: str) -> None:
    state, decisions = _phase17n_surveil_integrity_fixture()
    records = list(decisions.event_log.records)
    processed = records[-1]
    payload = dict(cast(dict[str, JsonValue], processed.payload))
    removed = cast(list[JsonValue], payload["removed_primary_mission_markers"])
    payload["removed_primary_mission_markers"] = [] if tamper == "partial" else [*removed, *removed]
    records[-1] = replace(processed, payload=validate_json_value(payload))

    with pytest.raises(GameLifecycleError, match="marker-removal set drifted"):
        validate_primary_mission_progress_state(
            state,
            event_records=tuple(records),
            decision_records=decisions.records,
        )


def _phase17n_event_setup(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
) -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id=f"mission-{layout_id}",
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_player_id="player-b",
        defender_force_disposition_id=defender_force_disposition_id,
    )


def _phase17n_submit_primary_mission_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> bool:
    decisions.request_decision(request)
    if state.stage is GameLifecycleStage.SETUP:
        decisions.submit_result(result)
        return apply_primary_mission_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
        )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(result)
    return True


def _phase17n_locate_choice_state() -> GameState:
    setup = _phase17n_event_setup(
        layout_id="disruption-vs-priority-assets-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="priority-assets",
    )
    base = phase11c_config()
    config = replace(
        base,
        mission_setup=setup,
        army_muster_requests=tuple(
            replace(
                request,
                force_disposition_id=(
                    "disruption" if request.player_id == "player-a" else "priority-assets"
                ),
            )
            for request in base.army_muster_requests
        ),
    )
    return GameState.from_config(config)


def _phase17n_sensor_start_integrity_fixture(
    *, action_count: int
) -> tuple[GameState, DecisionController, tuple[MissionActionState, ...]]:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    state.mission_setup = _phase17n_event_setup(
        layout_id="disruption-vs-priority-assets-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="priority-assets",
    )
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=state.mission_setup.battlefield_depth_inches,
        terrain_features=state.mission_setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                state.mission_setup.primary_mission_assignment_for_player(
                    army.player_id
                ).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.stage = GameLifecycleStage.SETUP
    state.setup_step_index = len(state.setup_sequence) - 1
    state.battle_round = 0
    state.active_player_id = None
    state.battle_phase_index = None
    decisions = DecisionController()
    request = locate_and_deny_setup_choice_request(
        state=state,
        decisions=decisions,
        request_id="phase17n-sensor-integrity-setup-request",
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17n-sensor-integrity-setup-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    assert len(state.primary_mission_progress_state.markers) == 5

    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    units = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    assert len(units) >= action_count
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    target_id = next(
        marker.objective_marker_id
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    target_marker = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id == target_id
    )
    for unit in units[:action_count]:
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                target_marker,
                offsets=((0.0, 0.0), (0.8, 0.0), (1.6, 0.0), (0.0, 0.8), (0.8, 0.8)),
            )
        )
    actions: list[MissionActionState] = []
    for index in range(action_count):
        prior_actions = tuple(actions)
        state.mission_action_states = []
        status = request_mission_action_start(
            state=state,
            decisions=decisions,
            player_id="player-a",
            mission_action_id=SENSOR_SWEEP_LOCATE_ACTION_ID,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        assert status.decision_request is not None
        request = status.decision_request
        selected_option = next(
            option
            for option in request.options
            if cast(dict[str, JsonValue], option.payload)["unit_instance_id"]
            == units[index].unit_instance_id
            and cast(dict[str, JsonValue], option.payload)["target_id"] == target_id
        )
        result = DecisionResult.for_request(
            result_id=f"phase17n-sensor-integrity-result:{index}",
            request=request,
            selected_option_id=selected_option.option_id,
        )
        GameLifecycle(decision_controller=decisions, state=state).submit_decision(result)
        action = state.mission_action_states[-1]
        state.mission_action_states = [*prior_actions, action]
        actions.append(action)
        if prior_actions:
            records = list(decisions.event_log.records)
            start_index = max(
                event_index
                for event_index, event in enumerate(records)
                if event.event_type == "mission_action_started"
            )
            start_event = records[start_index]
            start_payload = dict(cast(dict[str, JsonValue], start_event.payload))
            start_evidence = PrimaryMissionActionStartEvidence.from_payload(
                start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY]
            )
            start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY] = validate_json_value(
                replace(
                    start_evidence,
                    prior_uses=tuple(
                        MissionActionPriorUseEvidence(
                            action_id=prior.action_id,
                            mission_action_id=prior.mission_action_id,
                            player_id=prior.player_id,
                            battle_round_started=prior.battle_round_started,
                            phase_started=prior.phase_started,
                            unit_instance_id=prior.unit_instance_id,
                            unit_identity_ids=(prior.unit_instance_id,),
                            target_id=prior.target_id,
                            target_rules_unit_identity_ids=(),
                        )
                        for prior in prior_actions
                    ),
                ).to_payload()
            )
            controller_payload = decisions.to_payload()
            controller_payload["event_log"][start_index]["payload"] = validate_json_value(
                start_payload
            )
            decisions = DecisionController.from_payload(controller_payload)
    return state, decisions, tuple(actions)


def _phase17n_resolved_sensor_choice_fixture() -> tuple[
    GameState,
    DecisionController,
    DecisionRequest,
    DecisionResult,
]:
    state, decisions, actions = _phase17n_sensor_start_integrity_fixture(action_count=1)
    action = actions[0]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=action.target_id,
        action=action,
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    assert resolved[0].status is MissionActionStatus.COMPLETED
    request = sensor_sweep_marker_removal_choice_request(
        state=state,
        decisions=decisions,
        action_id=resolved[0].action_id,
        request_id="phase17n-sensor-authority-request",
    )
    assert request is not None
    result = DecisionResult.for_request(
        result_id="phase17n-sensor-authority-result",
        request=request,
        selected_option_id=request.options[0].option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    validate_primary_mission_progress_state(
        state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )
    return state, decisions, request, result


def _phase17n_punishment_choice_state() -> tuple[GameState, DecisionController, tuple[str, ...]]:
    enemy_keys = ("enemy-1", "enemy-2", "enemy-3")
    lifecycle, units = charge_lifecycle(
        alpha_unit_ids=("alpha",),
        enemy_model_poses=tuple(Pose.at(50.0 + index, 30.0) for index in range(5)),
        game_id="phase17n-punishment-choice-game",
        enemy_unit_ids=enemy_keys,
        enemy_origins={
            key: Pose.at(45.0 + (index * 8.0), 20.0) for index, key in enumerate(enemy_keys)
        },
    )
    state = lifecycle.state
    assert state is not None
    state.mission_setup = _phase17n_event_setup(
        layout_id="purge-the-foe-vs-disruption-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="disruption",
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    assert state.battlefield_state is not None
    contributions = tuple(
        ObjectiveControlContribution(
            player_id="player-b",
            unit_instance_id=units[key].unit_instance_id,
            model_instance_id=units[key].own_models[0].model_instance_id,
            objective_control=1,
            effective_objective_control=1,
            battle_shocked=False,
            horizontal_distance_inches=1.0,
            vertical_gap_inches=0.0,
        )
        for key in enemy_keys
    )
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=contributions if index == 0 else (),
        )
        for index, marker in enumerate(state.mission_setup.objective_markers)
    )
    record = ObjectiveControlRecord(
        record_id="phase17n-punishment-turn-start-record",
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_START,
        phase=BattlePhase.COMMAND.value,
        battlefield_id=state.battlefield_state.battlefield_id,
        results=results,
    )
    state.primary_objective_turn_start_states = [
        PrimaryObjectiveTurnStartState(
            state_id=(f"primary-turn-start:{state.game_id}:round-01:player-a"),
            game_id=state.game_id,
            player_id="player-a",
            active_player_id="player-a",
            battle_round=state.battle_round,
            source_objective_control_record=record,
            controlled_objective_ids=(),
            source_id=(f"{state.game_id}:primary-turn-start:round-01:player-a"),
        )
    ]
    _phase17n_refresh_turn_start_snapshot(state)
    record_primary_turn_start_evidence_event(
        event_log=lifecycle.decision_controller.event_log,
        objective_state=state.primary_objective_turn_start_states[0],
        position_snapshot=state.primary_rules_unit_turn_start_snapshots[0],
    )
    return (
        state,
        lifecycle.decision_controller,
        tuple(units[key].unit_instance_id for key in enemy_keys),
    )


def _phase17n_punishment_attached_choice_state() -> tuple[
    GameState,
    DecisionController,
    str,
    tuple[str, ...],
]:
    state, _decisions, enemy_ids = _phase17n_punishment_choice_state()
    bodyguard_id, leader_id = enemy_ids[:2]
    component_ids = tuple(sorted((bodyguard_id, leader_id)))
    attached_id = "attached-unit:army-beta:phase17n-punishment-target"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard_id,
        leader_unit_instance_ids=(leader_id,),
        component_unit_instance_ids=component_ids,
        source_id="phase17n-punishment-attached-source",
        attachment_source_ids=("phase17n-punishment-attachment-rule",),
    )
    enemy_army = next(army for army in state.army_definitions if army.player_id == "player-b")
    unit_by_id = {unit.unit_instance_id: unit for unit in enemy_army.units}
    state.army_definitions = [
        replace(army, attached_units=(formation,)) if army.player_id == "player-b" else army
        for army in state.army_definitions
    ]
    state.starting_strength_records = sorted(
        (
            record
            for record in state.starting_strength_records
            if record.unit_instance_id not in component_ids
        ),
        key=lambda record: record.unit_instance_id,
    )
    state.starting_strength_records.append(
        StartingStrengthRecord(
            player_id="player-b",
            unit_instance_id=attached_id,
            starting_model_count=sum(
                len(unit_by_id[component_id].own_models) for component_id in component_ids
            ),
            single_model_starting_wounds=None,
            source_id=formation.source_id,
        )
    )
    state.starting_strength_records.sort(key=lambda record: record.unit_instance_id)
    state.starting_attached_unit_records = [
        StartingAttachedUnitRecord.from_formation(
            player_id="player-b",
            attached_unit=formation,
            unit_by_id=unit_by_id,
        )
    ]
    _phase17n_refresh_turn_start_snapshot(state)
    decisions = DecisionController()
    record_primary_turn_start_evidence_event(
        event_log=decisions.event_log,
        objective_state=state.primary_objective_turn_start_states[0],
        position_snapshot=state.primary_rules_unit_turn_start_snapshots[0],
    )
    return state, decisions, attached_id, component_ids


def _phase17n_clear_turn_start_contributors(state: GameState) -> None:
    evidence = state.primary_objective_turn_start_states[0]
    record = replace(
        evidence.source_objective_control_record,
        record_id="phase17n-punishment-empty-turn-start-record",
        results=tuple(
            ObjectiveControlResult.from_contributors(
                objective_id=result.objective_id,
                contributors=(),
            )
            for result in evidence.source_objective_control_record.results
        ),
    )
    state.primary_objective_turn_start_states = [
        PrimaryObjectiveTurnStartState(
            state_id="phase17n-punishment-empty-turn-start-state",
            game_id=state.game_id,
            player_id="player-a",
            active_player_id="player-a",
            battle_round=state.battle_round,
            source_objective_control_record=record,
            controlled_objective_ids=(),
            source_id="phase17n-punishment-empty-turn-start-source",
        )
    ]


def _phase17n_refresh_turn_start_snapshot(state: GameState) -> None:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=state.mission_setup.battlefield_depth_inches,
        terrain_features=state.mission_setup.terrain_features,
    )
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                state.mission_setup.primary_mission_assignment_for_player(
                    army.player_id
                ).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.primary_rules_unit_turn_start_snapshots = [
        build_primary_rules_unit_turn_start_snapshot(state=state)
    ]


def _phase17n_consecrate_choice_state() -> tuple[GameState, DecisionController, str, str]:
    state = battle_state()
    state.mission_setup = _phase17n_event_setup(
        layout_id="purge-the-foe-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="reconnaissance",
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_round = 1
    state.active_player_id = "player-a"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    decisions = DecisionController()
    unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    target = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        with_model_offsets(
            placement,
            target,
            offsets=((0.0, 0.0), (1.4, 0.0), (2.8, 0.0), (0.0, 1.4), (1.4, 1.4)),
        )
    )
    destroyed_unit = next(
        enemy
        for army in state.army_definitions
        if army.player_id == "player-b"
        for enemy in army.units
    )
    source_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=unit.unit_instance_id,
    )
    destroyed_witness = rules_unit_objective_proximity_witness(
        state=state,
        rules_unit_instance_id=destroyed_unit.unit_instance_id,
    )
    attribution = ModelDestructionAttribution.for_non_attack(
        destroying_player_id="player-a",
        source_kind=DestructionSourceKind.ABILITY,
        source_rules_unit_instance_id=unit.unit_instance_id,
        source_model_instance_id=unit.own_models[0].model_instance_id,
    )
    destroyed_model_ids = destroyed_unit.own_model_ids()
    model_event = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "model_instance_id": destroyed_model_ids[-1],
            "target_unit_instance_id": destroyed_unit.unit_instance_id,
            "source_rules_unit_objective_proximity_witness": source_witness.to_payload(),
            "destroyed_rules_unit_objective_proximity_witness": destroyed_witness.to_payload(),
            **attribution.to_payload(),
        },
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(destroyed_model_ids)
    source_base = f"core-rules:primary-unit-destruction-tracking:{model_event.event_id}"
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=destroyed_model_ids,
        source_id=source_base,
    )
    for departure in departures:
        record_primary_battlefield_departure_event(
            event_log=decisions.event_log,
            departure=departure,
        )
    destruction_ids_before = tuple(
        destruction.destruction_id for destruction in state.primary_unit_destruction_states
    )
    destruction = state.record_primary_unit_destruction(
        destruction_attribution=attribution,
        source_model_destroyed_event_id=model_event.event_id,
        source_rules_unit_objective_proximity_witness=source_witness,
        source_battlefield_departure_ids=tuple(departure.departure_id for departure in departures),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=destroyed_unit.unit_instance_id,
        source_id=f"{source_base}:{destroyed_unit.unit_instance_id}",
    )
    record_new_primary_unit_destruction_events(
        state=state,
        event_log=decisions.event_log,
        destruction_ids_before=destruction_ids_before,
    )
    designation = next(
        value
        for value in state.primary_mission_progress_state.consecration_designations
        if value.source_destruction_id == destruction.destruction_id
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    decisions.event_log.append(
        "end_boundary_objective_control_determined",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "record_ids": [record.record_id],
            "source_rule_id": (
                "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
            ),
        },
    )
    return state, decisions, designation.designation_id, target.objective_marker_id


def _phase17n_resolved_consecrate_choice_fixture(
    *,
    select_objective: bool,
) -> tuple[GameState, DecisionController, str]:
    state, decisions, _designation_id, target_id = _phase17n_consecrate_choice_state()
    request = consecrate_choice_request(
        state=state,
        decisions=decisions,
        request_id=(
            "phase17n-consecrate-authority-select-request"
            if select_objective
            else "phase17n-consecrate-authority-decline-request"
        ),
    )
    assert request is not None
    selected_target_ids = (target_id,) if select_objective else ()
    option = next(
        candidate
        for candidate in request.options
        if PrimaryMissionChoiceData.from_payload(candidate.payload).selected_target_ids
        == selected_target_ids
    )
    result = DecisionResult.for_request(
        result_id=(
            "phase17n-consecrate-authority-select-result"
            if select_objective
            else "phase17n-consecrate-authority-decline-result"
        ),
        request=request,
        selected_option_id=option.option_id,
    )
    assert _phase17n_submit_primary_mission_choice(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )
    return state, decisions, target_id


def _phase17n_enter_battle_turn_end(state: GameState, *, active_player_id: str) -> None:
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    state.battle_round = 1
    state.active_player_id = active_player_id


def _phase17n_completed_sensor_action(
    *,
    action_id: str,
    mission_action_id: str,
    player_id: str,
    target_id: str,
) -> MissionActionState:
    descriptor = mission_action_policy_for_id(mission_action_id)
    unit_id = f"{player_id}-sensor-unit"
    return MissionActionState.start(
        action_id=action_id,
        mission_action_id=descriptor.mission_action_id,
        player_id=player_id,
        unit_instance_id=unit_id,
        target_id=target_id,
        condition_target_id=None,
        mission_id=descriptor.primary_mission_id,
        battle_round=1,
        phase=descriptor.start_phase,
        start_timing=descriptor.start_timing,
        completion_timing=descriptor.completion_timing,
        eligible_unit_instance_ids=(unit_id,),
        interruption_conditions=descriptor.interruption_conditions,
        scoring_source_id=descriptor.scoring_source_id,
        victory_points=0,
    ).complete_without_award(
        battle_round=1,
        phase=BattlePhase.FIGHT.value,
        completion_timing=descriptor.completion_timing,
    )


def _phase17n_use_limit_action(
    *,
    action_id: str,
    mission_action_id: str,
    unit_instance_id: str,
    target_id: str,
    eligible_unit_instance_ids: tuple[str, ...],
) -> MissionActionState:
    descriptor = mission_action_policy_for_id(mission_action_id)
    return MissionActionState.start(
        action_id=action_id,
        mission_action_id=descriptor.mission_action_id,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=None,
        mission_id=descriptor.primary_mission_id,
        battle_round=2,
        phase=descriptor.start_phase,
        start_timing=descriptor.start_timing,
        completion_timing=descriptor.completion_timing,
        eligible_unit_instance_ids=eligible_unit_instance_ids,
        interruption_conditions=descriptor.interruption_conditions,
        scoring_source_id=descriptor.scoring_source_id,
        victory_points=0,
    )


@pytest.mark.parametrize(
    "mission_action_id",
    [
        "maintain-control",
        "secure-asset",
        "sensor-sweep-extract-relic",
        "sensor-sweep-locate-and-deny",
        "triangulate-objective",
        "vanguard-operation",
    ],
)
def test_phase17n_restore_enforces_every_once_per_turn_action_policy(
    mission_action_id: str,
) -> None:
    state = battle_state()
    unit_id = next(
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    actions = tuple(
        _phase17n_use_limit_action(
            action_id=f"phase17n-use-limit:{mission_action_id}:{index}",
            mission_action_id=mission_action_id,
            unit_instance_id=unit_id,
            target_id=f"target-{index}",
            eligible_unit_instance_ids=(unit_id,),
        )
        for index in range(2)
    )

    with pytest.raises(GameLifecycleError, match="once-per-turn use limit exceeded"):
        validate_primary_mission_action_use_limits(
            state=state,
            ordered_actions=actions,
            policies={mission_action_id: mission_action_policy_for_id(mission_action_id)},
        )


@pytest.mark.parametrize(
    "mission_action_id",
    ["commit-sabotage", "decoy-objective", "extract-intelligence"],
)
@pytest.mark.parametrize("reuse_kind", ["unit", "target"])
def test_phase17n_restore_enforces_every_per_phase_unit_and_objective_policy(
    mission_action_id: str,
    reuse_kind: str,
) -> None:
    state = battle_state(
        player_a_units=(
            default_unit_selection("intercessor-unit-1"),
            default_unit_selection("intercessor-unit-2"),
        )
    )
    unit_ids = tuple(
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    assert len(unit_ids) == 2
    selected_unit_ids = (unit_ids[0], unit_ids[0]) if reuse_kind == "unit" else unit_ids
    target_ids = ("objective-a", "objective-b")
    if reuse_kind == "target":
        target_ids = ("objective-a", "objective-a")
    actions = tuple(
        _phase17n_use_limit_action(
            action_id=f"phase17n-use-limit:{mission_action_id}:{index}",
            mission_action_id=mission_action_id,
            unit_instance_id=selected_unit_ids[index],
            target_id=target_ids[index],
            eligible_unit_instance_ids=unit_ids,
        )
        for index in range(2)
    )

    with pytest.raises(
        GameLifecycleError,
        match="per-phase unit/objective use limit exceeded",
    ):
        validate_primary_mission_action_use_limits(
            state=state,
            ordered_actions=actions,
            policies={mission_action_id: mission_action_policy_for_id(mission_action_id)},
        )


def test_phase17n_restore_rejects_sensor_sweep_started_with_only_one_eligible_marker() -> None:
    state, decisions, _actions = _phase17n_sensor_start_integrity_fixture(action_count=1)
    marker = state.primary_mission_progress_state.markers[0]
    state.primary_mission_progress_state = replace(
        state.primary_mission_progress_state,
        markers=(marker,),
    )

    with pytest.raises(GameLifecycleError, match="boundary marker inventory drifted"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=decisions.event_log.records,
        )


def test_phase17n_action_restore_uses_start_marker_snapshot_after_later_tombstones() -> None:
    state, decisions, _request, _result = _phase17n_resolved_sensor_choice_fixture()
    active_markers = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.status is PrimaryMissionMarkerStatus.ACTIVE
    )
    assert len(active_markers) == 4

    for index, marker in enumerate(active_markers[:3]):
        removal_event = decisions.event_log.append(
            "phase17n_later_primary_marker_removed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.FIGHT.value,
                "marker_id": marker.marker_id,
            },
        )
        removed = marker.removed(
            battle_round=state.battle_round,
            phase=BattlePhase.FIGHT.value,
            active_player_id=cast(str, state.active_player_id),
            source_id=f"phase17n-later-marker-removal:{index}",
            event_id=removal_event.event_id,
        )
        state.primary_mission_progress_state = replace(
            state.primary_mission_progress_state,
            markers=tuple(
                removed if candidate.marker_id == marker.marker_id else candidate
                for candidate in state.primary_mission_progress_state.markers
            ),
        )

    assert (
        sum(
            marker.status is PrimaryMissionMarkerStatus.ACTIVE
            for marker in state.primary_mission_progress_state.markers
        )
        == 1
    )
    validate_primary_mission_action_integrity(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )


def test_phase17n_restore_rejects_duplicate_sensor_sweep_start_authority() -> None:
    state, decisions, actions = _phase17n_sensor_start_integrity_fixture(action_count=2)
    assert len(actions) == 2

    with pytest.raises(
        GameLifecycleError,
        match="start evidence drifted from its boundary checkpoint",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=decisions.event_log.records,
        )


def test_phase17n_sensor_restore_rejects_coordinated_legal_option_shrink() -> None:
    state, decisions, request, result = _phase17n_resolved_sensor_choice_fixture()
    choice_event_index = next(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
        and cast(dict[str, JsonValue], event.payload).get("result_id") == result.result_id
    )
    choice_event = decisions.event_log.records[choice_event_index]
    choice_event_payload = dict(cast(dict[str, JsonValue], choice_event.payload))
    choice = PrimaryMissionChoiceData.from_payload(choice_event_payload["choice"])
    omitted_id = next(
        marker_id
        for marker_id in choice.legal_target_ids
        if marker_id not in choice.selected_target_ids
    )
    shrunken_legal_ids = tuple(
        marker_id for marker_id in choice.legal_target_ids if marker_id != omitted_id
    )
    forged_choice = replace(choice, legal_target_ids=shrunken_legal_ids)
    choice_event_payload["choice"] = validate_json_value(forged_choice.to_payload())

    forged_request_choice = replace(forged_choice, selected_target_ids=())
    forged_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                forged_request_choice.with_selected_targets(
                    PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids
                ).to_payload()
            ),
        )
        for option in request.options
        if PrimaryMissionChoiceData.from_payload(option.payload).selected_target_ids
        != (omitted_id,)
    )
    forged_request = replace(
        request,
        payload=validate_json_value(forged_request_choice.to_payload()),
        options=forged_options,
    )
    forged_result = replace(
        result,
        payload=validate_json_value(forged_choice.to_payload()),
    )
    sensor_decision_index = next(
        index
        for index, decision in enumerate(decisions.records)
        if decision.result.result_id == result.result_id
    )
    forged_sensor_decision = replace(
        decisions.records[sensor_decision_index],
        request=forged_request,
        result=forged_result,
    )
    forged_decisions = tuple(
        forged_sensor_decision if index == sensor_decision_index else decision
        for index, decision in enumerate(decisions.records)
    )

    forged_events = list(decisions.event_log.records)
    forged_events[choice_event_index] = replace(
        choice_event,
        payload=validate_json_value(choice_event_payload),
    )
    request_event_index = next(
        index
        for index, event in enumerate(forged_events)
        if event.event_type == "decision_requested"
        and cast(dict[str, JsonValue], event.payload).get("request_id") == request.request_id
    )
    forged_events[request_event_index] = replace(
        forged_events[request_event_index],
        payload=validate_json_value(forged_request.to_payload()),
    )
    record_event_index = next(
        index
        for index, event in enumerate(forged_events)
        if event.event_type == "decision_recorded"
        and cast(dict[str, JsonValue], event.payload).get("record_id")
        == forged_sensor_decision.record_id
    )
    forged_events[record_event_index] = replace(
        forged_events[record_event_index],
        payload=validate_json_value(forged_sensor_decision.to_payload()),
    )

    with pytest.raises(
        GameLifecycleError,
        match="Action-removed Primary marker event identity drift",
    ):
        validate_primary_mission_progress_state(
            state,
            event_records=tuple(forged_events),
            decision_records=forged_decisions,
        )


def test_phase17n_restore_binds_primary_action_to_exact_decision_and_event_order() -> None:
    state, decisions, _action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )

    validate_primary_mission_decision_integrity(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )
    with pytest.raises(
        GameLifecycleError,
        match="requires one authoritative DecisionRecord",
    ):
        validate_primary_mission_decision_integrity(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=(),
        )

    reordered = list(decisions.event_log.records)
    recorded_index = next(
        index for index, event in enumerate(reordered) if event.event_type == "decision_recorded"
    )
    mutation_index = next(
        index
        for index, event in enumerate(reordered)
        if event.event_type == "mission_action_started"
    )
    reordered[recorded_index], reordered[mutation_index] = (
        reordered[mutation_index],
        reordered[recorded_index],
    )
    with pytest.raises(GameLifecycleError, match="decision/mutation ordering drifted"):
        validate_primary_mission_decision_integrity(
            state=state,
            event_records=tuple(reordered),
            decision_records=decisions.records,
        )


@pytest.mark.parametrize(
    ("tamper", "expected"),
    [
        ("missing_key", "battlefield boundary payload keys drifted"),
        ("extra_key", "battlefield boundary payload keys drifted"),
        ("terrain_omission", "checkpoint-backed battlefield authority drifted"),
    ],
)
def test_phase17n_action_restore_rejects_battlefield_boundary_drift(
    tamper: str,
    expected: str,
) -> None:
    state, decisions, _action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    records = list(decisions.event_log.records)
    start_index = next(
        index for index, event in enumerate(records) if event.event_type == "mission_action_started"
    )
    start_event = records[start_index]
    start_payload = dict(cast(dict[str, JsonValue], start_event.payload))
    evidence_payload = dict(
        cast(
            dict[str, JsonValue],
            start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY],
        )
    )
    authority_payload = dict(cast(dict[str, JsonValue], evidence_payload["start_authority"]))
    boundary_payload = dict(cast(dict[str, JsonValue], authority_payload["battlefield_boundary"]))
    if tamper == "missing_key":
        boundary_payload.pop("battlefield_width_inches")
    elif tamper == "extra_key":
        boundary_payload["unexpected"] = "forged"
    else:
        terrain_features = cast(list[JsonValue], boundary_payload["terrain_features"])
        assert terrain_features
        boundary_payload["terrain_features"] = terrain_features[1:]
    authority_payload["battlefield_boundary"] = validate_json_value(boundary_payload)
    evidence_payload["start_authority"] = validate_json_value(authority_payload)
    start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY] = validate_json_value(evidence_payload)
    records[start_index] = replace(
        start_event,
        payload=validate_json_value(start_payload),
    )

    with pytest.raises(GameLifecycleError, match=expected):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(records),
        )


def test_phase17n_action_restore_rejects_coordinated_nonselected_option_shrink() -> None:
    state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="decoy-objective",
        current_phase=BattlePhase.FIGHT,
        player_unit_count=2,
    )
    decision = decisions.records[0]
    request = decision.request
    assert len(request.options) == 2
    assert len(action.eligible_unit_instance_ids) == 2
    omitted_unit_id = next(
        unit_id
        for unit_id in action.eligible_unit_instance_ids
        if unit_id != action.unit_instance_id
    )
    forged_eligible_ids = (action.unit_instance_id,)
    retained_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                {
                    **cast(dict[str, JsonValue], option.payload),
                    "eligible_unit_instance_ids": list(forged_eligible_ids),
                }
            ),
        )
        for option in request.options
        if cast(dict[str, JsonValue], option.payload)["unit_instance_id"] != omitted_unit_id
    )
    assert len(retained_options) == 1
    request_payload = dict(cast(dict[str, JsonValue], request.payload))
    request_payload["legal_option_ids"] = [option.option_id for option in retained_options]
    forged_request = replace(
        request,
        payload=validate_json_value(request_payload),
        options=retained_options,
    )
    selected_option = next(
        option
        for option in retained_options
        if option.option_id == decision.result.selected_option_id
    )
    forged_result = replace(decision.result, payload=selected_option.payload)
    forged_decision = replace(
        decision,
        request=forged_request,
        result=forged_result,
    )

    start_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "mission_action_started"
    )
    start_payload = dict(cast(dict[str, JsonValue], start_event.payload))
    evidence = PrimaryMissionActionStartEvidence.from_payload(
        start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY]
    )
    forged_authority = replace(
        evidence.start_authority,
        request_payload_json=canonical_json(forged_request.payload),
        options=tuple(
            MissionActionStartAuthorityOptionEvidence(
                option_id=option.option_id,
                label=option.label,
                payload_json=canonical_json(option.payload),
            )
            for option in retained_options
        ),
    )
    forged_evidence = replace(
        evidence,
        eligible_unit_instance_ids=forged_eligible_ids,
        start_authority=forged_authority,
    )
    forged_action = replace(
        action,
        eligible_unit_instance_ids=forged_eligible_ids,
    )
    forged_state = deepcopy(state)
    forged_state.mission_action_states = [forged_action]
    start_payload["mission_action_state"] = validate_json_value(forged_action.to_payload())
    start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY] = validate_json_value(
        forged_evidence.to_payload()
    )

    forged_events = list(decisions.event_log.records)
    for index, event in enumerate(forged_events):
        if event.event_type == "decision_requested":
            forged_events[index] = replace(
                event,
                payload=validate_json_value(forged_request.to_payload()),
            )
        elif event.event_type == "decision_recorded":
            forged_events[index] = replace(
                event,
                payload=validate_json_value(forged_decision.to_payload()),
            )
        elif event.event_type == "mission_action_started":
            forged_events[index] = replace(
                event,
                payload=validate_json_value(start_payload),
            )

    with pytest.raises(
        GameLifecycleError,
        match=r"Primary Mission Action .*inventory drifted",
    ):
        validate_primary_mission_action_integrity(
            state=forged_state,
            event_records=tuple(forged_events),
        )


def test_phase17n_action_restore_rejects_extra_opportunity_option_family() -> None:
    state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="decoy-objective",
        current_phase=BattlePhase.FIGHT,
    )
    decision = decisions.records[0]
    request = decision.request
    selected_option = request.option_by_id(decision.result.selected_option_id)
    forged_action_id = "forged-secondary-action"
    forged_option_id = f"start:{forged_action_id}:{action.unit_instance_id}:{action.target_id}"
    action_option_ids = sorted(
        [
            *(option.option_id for option in request.options),
            forged_option_id,
        ]
    )
    updated_options = tuple(
        replace(
            option,
            payload=validate_json_value(
                {
                    **cast(dict[str, JsonValue], option.payload),
                    "mission_action_opportunity": True,
                    "legal_action_option_ids": action_option_ids,
                }
            ),
        )
        for option in request.options
    )
    forged_option_payload = {
        **cast(dict[str, JsonValue], selected_option.payload),
        "mission_action_id": forged_action_id,
        "mission_id": "forged-secondary",
        "mission_kind": "secondary",
        "mission_action_opportunity": True,
        "legal_action_option_ids": action_option_ids,
    }
    forged_option = replace(
        selected_option,
        option_id=forged_option_id,
        label="Forged secondary action",
        payload=validate_json_value(forged_option_payload),
    )
    request_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": action.player_id,
        "battle_round": action.battle_round_started,
        "phase": action.phase_started,
        "mission_action_opportunity": True,
        "legal_mission_action_ids": validate_json_value(
            sorted([action.mission_action_id, forged_action_id])
        ),
        "legal_action_option_ids": validate_json_value(action_option_ids),
        "legal_option_ids": validate_json_value(
            sorted([*action_option_ids, DECLINE_MISSION_ACTION_START_OPTION_ID])
        ),
    }
    decline_option = replace(
        selected_option,
        option_id=DECLINE_MISSION_ACTION_START_OPTION_ID,
        label="Continue to shooting",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": action.player_id,
                "battle_round": action.battle_round_started,
                "phase": action.phase_started,
                "mission_action_opportunity": True,
                "legal_action_option_ids": action_option_ids,
            }
        ),
    )
    forged_request = replace(
        request,
        payload=validate_json_value(request_payload),
        options=(*updated_options, forged_option, decline_option),
    )
    forged_selected_option = forged_request.option_by_id(decision.result.selected_option_id)
    forged_result = replace(decision.result, payload=forged_selected_option.payload)
    forged_decision = replace(
        decision,
        request=forged_request,
        result=forged_result,
    )

    start_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "mission_action_started"
    )
    start_payload = dict(cast(dict[str, JsonValue], start_event.payload))
    evidence = PrimaryMissionActionStartEvidence.from_payload(
        start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY]
    )
    forged_evidence = replace(
        evidence,
        start_authority=replace(
            evidence.start_authority,
            request_kind="opportunity",
            request_payload_json=canonical_json(forged_request.payload),
            options=tuple(
                MissionActionStartAuthorityOptionEvidence(
                    option_id=option.option_id,
                    label=option.label,
                    payload_json=canonical_json(option.payload),
                )
                for option in forged_request.options
            ),
        ),
    )
    start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY] = validate_json_value(
        forged_evidence.to_payload()
    )

    forged_events = list(decisions.event_log.records)
    for index, event in enumerate(forged_events):
        if event.event_type == "decision_requested":
            forged_events[index] = replace(
                event,
                payload=validate_json_value(forged_request.to_payload()),
            )
        elif event.event_type == "decision_recorded":
            forged_events[index] = replace(
                event,
                payload=validate_json_value(forged_decision.to_payload()),
            )
        elif event.event_type == "mission_action_started":
            forged_events[index] = replace(
                event,
                payload=validate_json_value(start_payload),
            )

    with pytest.raises(
        GameLifecycleError,
        match="complete start authority inventory drifted",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(forged_events),
            decision_records=(forged_decision,),
        )


@pytest.mark.parametrize(
    (
        "mission_action_id",
        "layout_id",
        "attacker_force_disposition_id",
        "defender_force_disposition_id",
    ),
    [
        (
            "extract-intelligence",
            "reconnaissance-vs-reconnaissance-layout-1",
            "reconnaissance",
            "reconnaissance",
        ),
        (
            "triangulate-objective",
            "purge-the-foe-vs-reconnaissance-layout-1",
            "reconnaissance",
            "purge-the-foe",
        ),
    ],
)
def test_phase17n_round_two_action_start_evidence_rejects_round_one_replay(
    mission_action_id: str,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
) -> None:
    state, decisions, _action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id=layout_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_force_disposition_id=defender_force_disposition_id,
        player_id="player-a",
        mission_action_id=mission_action_id,
        current_phase=BattlePhase.FIGHT,
    )
    start_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "mission_action_started"
    )
    start_payload = cast(dict[str, JsonValue], start_event.payload)
    evidence = PrimaryMissionActionStartEvidence.from_payload(
        start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY]
    )
    runtime_action = mission_action_for_state(
        state=state,
        mission_action_id=mission_action_id,
    )

    with pytest.raises(GameLifecycleError, match="started before battle round two"):
        validate_primary_mission_action_start_evidence(
            state=state,
            action=runtime_action,
            policy=mission_action_policy_for_id(mission_action_id),
            evidence=replace(evidence, battle_round=1),
            expected_active_marker_ids=evidence.active_primary_mission_marker_ids,
            expected_prior_uses=evidence.prior_uses,
        )


def _phase17n_surveil_action_start_evidence_fixture() -> tuple[
    GameState,
    PrimaryMissionActionStartEvidence,
]:
    state, decisions, _action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="disruption",
        player_id="player-a",
        mission_action_id="surveil-enemy-unit",
        current_phase=BattlePhase.SHOOTING,
    )
    start_event = next(
        event
        for event in decisions.event_log.records
        if event.event_type == "mission_action_started"
    )
    start_payload = cast(dict[str, JsonValue], start_event.payload)
    return state, PrimaryMissionActionStartEvidence.from_payload(
        start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY]
    )


def test_phase17n_surveil_start_rejects_history_and_geometry_drift() -> None:
    state, evidence = _phase17n_surveil_action_start_evidence_fixture()
    surveil = evidence.surveil_target_evidence
    assert surveil is not None
    runtime_action = mission_action_for_state(
        state=state,
        mission_action_id=evidence.mission_action_id,
    )
    prior = MissionActionPriorUseEvidence(
        action_id="phase17n-prior-surveil",
        mission_action_id=evidence.mission_action_id,
        player_id=evidence.player_id,
        battle_round_started=evidence.battle_round,
        phase_started=evidence.phase,
        unit_instance_id="phase17n-other-observer",
        unit_identity_ids=("phase17n-other-observer",),
        target_id=evidence.target_id,
        target_rules_unit_identity_ids=surveil.target_rules_unit_identity_ids,
    )
    forged_evidence = replace(evidence, prior_uses=(prior,))

    with pytest.raises(GameLifecycleError, match="already surveilled"):
        validate_primary_mission_action_start_evidence(
            state=state,
            action=runtime_action,
            policy=mission_action_policy_for_id(evidence.mission_action_id),
            evidence=forged_evidence,
            expected_active_marker_ids=forged_evidence.active_primary_mission_marker_ids,
            expected_prior_uses=forged_evidence.prior_uses,
            validate_request_authority=False,
        )

    for forged_surveil in (
        replace(surveil, observer_component_unit_instance_ids_within_18=()),
        replace(
            surveil,
            observer_component_unit_instance_ids_with_line_of_sight=(),
        ),
    ):
        forged_evidence = replace(evidence, surveil_target_evidence=forged_surveil)
        with pytest.raises(
            GameLifecycleError,
            match="Surveil Primary Mission Action geometry drifted",
        ):
            validate_primary_mission_action_start_evidence(
                state=state,
                action=runtime_action,
                policy=mission_action_policy_for_id(evidence.mission_action_id),
                evidence=forged_evidence,
                expected_active_marker_ids=(forged_evidence.active_primary_mission_marker_ids),
                expected_prior_uses=forged_evidence.prior_uses,
                validate_request_authority=False,
            )


def test_phase17n_vanguard_start_replay_requires_selected_terrain_intersection() -> None:
    state, decisions, _action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="vanguard-operation",
        current_phase=BattlePhase.FIGHT,
    )
    records = list(decisions.event_log.records)
    start_index = next(
        index for index, event in enumerate(records) if event.event_type == "mission_action_started"
    )
    start_event = records[start_index]
    start_payload = dict(cast(dict[str, JsonValue], start_event.payload))
    evidence = PrimaryMissionActionStartEvidence.from_payload(
        start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY]
    )
    start_payload[PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY] = validate_json_value(
        replace(evidence, terrain_intersections=()).to_payload()
    )
    records[start_index] = replace(
        start_event,
        payload=validate_json_value(start_payload),
    )

    with pytest.raises(GameLifecycleError, match="boundary checkpoint"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(records),
        )


def test_phase17n_turn_end_action_commits_marker_with_completion_event_authority() -> None:
    state, decisions, action, target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )

    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert len(resolved) == 1
    assert resolved[0].status is MissionActionStatus.COMPLETED
    marker = state.primary_mission_progress_state.markers[0]
    completion_event = decisions.event_log.records[-1]
    assert completion_event.event_type == "mission_action_completed"
    assert marker.source_event_id == completion_event.event_id
    assert marker.source_action_id == action.action_id
    assert (
        cast(dict[str, JsonValue], completion_event.payload)["primary_mission_marker"]
        == marker.to_payload()
    )
    validate_primary_mission_action_integrity(
        state=state,
        event_records=decisions.event_log.records,
    )
    restored_state = deepcopy(state)
    restored_state.mission_action_states = [
        MissionActionState.from_payload(value.to_payload()) for value in state.mission_action_states
    ]
    restored_state.primary_mission_progress_state = PrimaryMissionProgressState.from_payload(
        state.primary_mission_progress_state.to_payload()
    )
    restored_log = EventLog.from_payload(decisions.event_log.to_payload())
    validate_primary_mission_progress_state(
        restored_state,
        event_records=restored_log.records,
        decision_records=decisions.records,
    )
    validate_primary_mission_action_integrity(
        state=restored_state,
        event_records=restored_log.records,
    )
    assert restored_log.to_payload() == decisions.event_log.to_payload()
    lifecycle_state = deepcopy(state)
    assert lifecycle_state.battlefield_state is not None
    assert lifecycle_state.mission_setup is not None
    lifecycle_state.battlefield_state = replace(
        lifecycle_state.battlefield_state,
        battlefield_width_inches=lifecycle_state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=lifecycle_state.mission_setup.battlefield_depth_inches,
        terrain_features=lifecycle_state.mission_setup.terrain_features,
    )
    lifecycle_state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                lifecycle_state.mission_setup.primary_mission_assignment_for_player(
                    army.player_id
                ).force_disposition_id
            ),
        )
        for army in lifecycle_state.army_definitions
    ]
    lifecycle_state.primary_objective_turn_start_states = []
    lifecycle_state.primary_rules_unit_turn_start_snapshots = []
    restored_lifecycle = GameLifecycle.from_payload(
        GameLifecycle(decision_controller=decisions, state=lifecycle_state).to_payload()
    )
    assert restored_lifecycle.state is not None
    assert restored_lifecycle.state.primary_mission_progress_state == (
        lifecycle_state.primary_mission_progress_state
    )
    with pytest.raises(GameLifecycleError, match="terminal event authentication"):
        validate_primary_mission_action_integrity(
            state=restored_state,
            event_records=restored_log.records[:-1],
        )


def test_phase17n_restore_rejects_tampered_action_completion_result_and_record_hash() -> None:
    state, decisions, action, target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )
    resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    records = list(decisions.event_log.records)
    completion_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == "mission_action_completed"
    )
    completion_event = records[completion_index]
    completion_payload = dict(cast(dict[str, JsonValue], completion_event.payload))
    evidence = PrimaryMissionActionCompletionEvidence.from_payload(
        completion_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY]
    )

    result_payload = dict(completion_payload)
    result_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY] = validate_json_value(
        replace(evidence, completion_condition_met=False).to_payload()
    )
    result_records = list(records)
    result_records[completion_index] = replace(
        completion_event,
        payload=validate_json_value(result_payload),
    )
    with pytest.raises(GameLifecycleError, match="completion result drifted"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(result_records),
        )

    hash_payload = dict(completion_payload)
    hash_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY] = validate_json_value(
        replace(evidence, objective_control_record_hash="forged-record-hash").to_payload()
    )
    hash_records = list(records)
    hash_records[completion_index] = replace(
        completion_event,
        payload=validate_json_value(hash_payload),
    )
    with pytest.raises(GameLifecycleError, match="objective boundary drifted"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(hash_records),
        )


@pytest.mark.parametrize(
    "failure_kind",
    ["uncontrolled", "non_lineage_contributor"],
)
def test_phase17n_restore_rejects_forged_objective_completion_without_source_condition(
    failure_kind: str,
) -> None:
    state, decisions, action, target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="priority-assets",
        defender_force_disposition_id="purge-the-foe",
        player_id="player-a",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
        player_unit_count=2,
        completion_control_kind=failure_kind,
    )
    if failure_kind == "non_lineage_contributor":
        contributor_id = next(
            unit.unit_instance_id
            for army in state.army_definitions
            if army.player_id == action.player_id
            for unit in army.units
            if unit.unit_instance_id != action.unit_instance_id
        )
    else:
        contributor_id = None
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
        contributing_unit_instance_id=contributor_id,
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    assert resolved[0].interrupted_reason == "completion_condition_failed"
    terminal_index = next(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_type == "mission_action_completion_failed"
    )
    terminal = decisions.event_log.records[terminal_index]
    terminal_payload = dict(cast(dict[str, JsonValue], terminal.payload))
    evidence = PrimaryMissionActionCompletionEvidence.from_payload(
        terminal_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY]
    )
    assert evidence.completion_condition_met is False
    assert evidence.objective_control_result is not None
    if failure_kind == "uncontrolled":
        assert evidence.objective_control_result.controlled_by_player_id != action.player_id
    else:
        assert evidence.objective_control_result.controlled_by_player_id == action.player_id
        assert evidence.action_unit_contributor_unit_instance_ids == ()
        assert evidence.action_unit_contributor_model_instance_ids == ()

    forged_completed = action.complete_without_award(
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        completion_timing=action.completion_timing,
    )
    marker = _phase17n_forged_completion_marker(
        state=state,
        action=forged_completed,
        source_event_id=terminal.event_id,
    )
    state.mission_action_states = [forged_completed]
    state.primary_mission_progress_state = state.primary_mission_progress_state.add_marker(marker)
    terminal_payload["mission_action_state"] = validate_json_value(forged_completed.to_payload())
    terminal_payload["primary_mission_marker"] = validate_json_value(marker.to_payload())
    records = list(decisions.event_log.records)
    records[terminal_index] = replace(
        terminal,
        event_type="mission_action_completed",
        payload=validate_json_value(terminal_payload),
    )

    with pytest.raises(
        GameLifecycleError,
        match="terminal status contradicts completion evidence",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(records),
        )


def test_phase17n_restore_rejects_coordinated_completed_to_failed_action_rewrite() -> None:
    state, decisions, action, target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    assert resolved[0].status is MissionActionStatus.COMPLETED
    assert len(state.primary_mission_progress_state.markers) == 1
    forged_failed = action.fail_completion()
    state.mission_action_states = [forged_failed]
    state.primary_mission_progress_state = replace(
        state.primary_mission_progress_state,
        markers=(),
    )
    records = list(decisions.event_log.records)
    terminal_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == "mission_action_completed"
    )
    terminal = records[terminal_index]
    terminal_payload = dict(cast(dict[str, JsonValue], terminal.payload))
    terminal_payload["mission_action_state"] = validate_json_value(forged_failed.to_payload())
    terminal_payload.pop("primary_mission_marker")
    records[terminal_index] = replace(
        terminal,
        event_type="mission_action_completion_failed",
        payload=validate_json_value(terminal_payload),
    )

    with pytest.raises(
        GameLifecycleError,
        match="terminal status contradicts completion evidence",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(records),
        )


def test_phase17n_restore_requires_action_start_before_objective_boundary() -> None:
    state, decisions, action, target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )
    resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    records = list(decisions.event_log.records)
    boundary_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == "end_boundary_objective_control_determined"
    )
    boundary = records.pop(boundary_index)
    start_index = next(
        index for index, event in enumerate(records) if event.event_type == "mission_action_started"
    )
    records.insert(start_index, boundary)

    with pytest.raises(GameLifecycleError, match="objective boundary event ordering drifted"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(records),
        )


def test_phase17n_vanguard_completion_evidence_requires_enemy_terrain_row() -> None:
    state, decisions, action, target_id = shared_started_primary_action_fixture(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="vanguard-operation",
        current_phase=BattlePhase.FIGHT,
        vanguard_enemy_position="inside",
    )
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    assert resolved[0].status is MissionActionStatus.INTERRUPTED
    assert resolved[0].interrupted_reason == "completion_condition_failed"
    records = list(decisions.event_log.records)
    completion_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == "mission_action_completion_failed"
    )
    completion_event = records[completion_index]
    completion_payload = dict(cast(dict[str, JsonValue], completion_event.payload))
    evidence = PrimaryMissionActionCompletionEvidence.from_payload(
        completion_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY]
    )
    assert any(
        row.owner_player_id != action.player_id and row.logical_terrain_area_id == target_id
        for row in evidence.terrain_intersections
    )
    completion_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY] = validate_json_value(
        replace(
            evidence,
            terrain_intersections=tuple(
                row
                for row in evidence.terrain_intersections
                if not (
                    row.owner_player_id != action.player_id
                    and row.logical_terrain_area_id == target_id
                )
            ),
        ).to_payload()
    )
    records[completion_index] = replace(
        completion_event,
        payload=validate_json_value(completion_payload),
    )

    with pytest.raises(GameLifecycleError, match="Vanguard terrain boundary inventory drifted"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(records),
        )


def test_phase17n_reconciliation_interrupts_post_start_charge_move_once() -> None:
    state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.CHARGE,
    )
    assert state.battlefield_state is not None
    unit_placement = state.battlefield_state.unit_placement_by_id(action.unit_instance_id)
    model_placement = unit_placement.model_placements[0]
    displacement = ModelDisplacementRecord(
        model_instance_id=model_placement.model_instance_id,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
        start_pose=model_placement.pose,
        end_pose=Pose.at(
            model_placement.pose.position.x + 1.0,
            model_placement.pose.position.y,
            model_placement.pose.position.z,
            facing_degrees=model_placement.pose.facing.degrees,
        ),
    )
    evidence = decisions.event_log.append(
        "charge_move_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.CHARGE.value,
            "unit_instance_id": action.unit_instance_id,
            "transition_batch": BattlefieldTransitionBatch(
                displacements=(displacement,)
            ).to_payload(),
        },
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(
        unit_placement.with_model_placements(
            tuple(
                placement.with_pose(displacement.end_pose)
                if placement.model_instance_id == displacement.model_instance_id
                else placement
                for placement in unit_placement.model_placements
            )
        )
    )

    interrupted = reconcile_primary_mission_action_interruptions(
        state=state,
        decisions=decisions,
    )

    assert len(interrupted) == 1
    assert interrupted[0].status is MissionActionStatus.INTERRUPTED
    assert interrupted[0].interrupted_reason == "unit_moved"
    terminal = decisions.event_log.records[-1]
    assert terminal.event_type == "mission_action_interrupted"
    terminal_payload = cast(dict[str, JsonValue], terminal.payload)
    assert terminal_payload["source_evidence_event_id"] == evidence.event_id
    assert terminal_payload["source_evidence_event_type"] == evidence.event_type
    assert reconcile_primary_mission_action_interruptions(state=state, decisions=decisions) == ()
    assert (
        sum(
            record.event_type == "mission_action_interrupted"
            for record in decisions.event_log.records
        )
        == 1
    )
    validate_primary_mission_action_integrity(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
    )
    forged_payload = dict(terminal_payload)
    forged_payload.pop("source_evidence_event_id")
    forged_payload.pop("source_evidence_event_type")
    forged_terminal = replace(
        terminal,
        payload=validate_json_value(forged_payload),
    )
    with pytest.raises(GameLifecycleError, match="without causal evidence"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=(*decisions.event_log.records[:-1], forged_terminal),
        )


def test_phase17n_restore_rejects_partial_model_destruction_as_action_interruption() -> None:
    state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(action.unit_instance_id)
    model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    assert len(model_ids) > 1
    evidence = decisions.event_log.append(
        "model_destroyed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "model_instance_id": model_ids[0],
        },
    )
    for model_id in model_ids[1:]:
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "model_instance_id": model_id,
            },
        )
    state.battlefield_state = state.battlefield_state.without_unit_placement(
        action.unit_instance_id
    )
    interrupted = action.interrupt(reason="unit_destroyed")
    state.replace_mission_action_state(interrupted)
    descriptor = mission_action_policy_for_id(action.mission_action_id)
    decisions.event_log.append(
        "mission_action_interrupted",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": action.player_id,
            "phase": BattlePhase.FIGHT.value,
            "action_id": action.action_id,
            "mission_action_id": action.mission_action_id,
            "unit_instance_id": action.unit_instance_id,
            "mission_action_state": interrupted.to_payload(),
            "interrupted_reason": interrupted.interrupted_reason,
            "source_evidence_event_id": evidence.event_id,
            "source_evidence_event_type": evidence.event_type,
            "source_id": descriptor.source_id,
        },
    )

    with pytest.raises(GameLifecycleError, match="whole-lineage completion evidence"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=decisions.event_log.records,
        )


def test_phase17n_action_destruction_replay_cites_canonical_completion_event() -> None:
    state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    _phase17n_refresh_turn_start_snapshot(state)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    turn_start_record = ObjectiveControlRecord(
        record_id="phase17n-action-destruction-turn-start-record",
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=action.player_id,
        timing=ObjectiveControlTiming.TURN_START,
        phase=BattlePhase.COMMAND.value,
        battlefield_id=state.battlefield_state.battlefield_id,
        results=tuple(
            ObjectiveControlResult.from_contributors(
                objective_id=marker.objective_marker_id,
                contributors=(),
            )
            for marker in state.mission_setup.objective_markers
        ),
    )
    state.primary_objective_turn_start_states = [
        PrimaryObjectiveTurnStartState(
            state_id=(
                f"primary-turn-start:{state.game_id}:round-{state.battle_round:02d}:"
                f"{action.player_id}"
            ),
            game_id=state.game_id,
            player_id=action.player_id,
            active_player_id=action.player_id,
            battle_round=state.battle_round,
            source_objective_control_record=turn_start_record,
            controlled_objective_ids=(),
            source_id=(
                f"{state.game_id}:primary-turn-start:round-{state.battle_round:02d}:"
                f"{action.player_id}"
            ),
        )
    ]
    action_unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == action.unit_instance_id
    )
    model_ids = action_unit.own_model_ids()
    model_events = tuple(
        decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.FIGHT.value,
                "model_instance_id": model_id,
            },
        )
        for model_id in model_ids
    )
    _phase17n_set_model_wounds(state, model_ids=model_ids, wounds_remaining=0)
    state.battlefield_state = state.battlefield_state.with_removed_models(model_ids)
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=model_ids,
        source_id="phase17n-action-canonical-destruction",
    )
    for departure in departures:
        record_primary_battlefield_departure_event(
            event_log=decisions.event_log,
            departure=departure,
        )
    destroying_player_id = next(
        player_id for player_id in state.player_ids if player_id != action.player_id
    )
    destruction = state.record_primary_unit_destruction(
        destruction_attribution=ModelDestructionAttribution.for_non_attack(
            destroying_player_id=destroying_player_id,
            source_kind=DestructionSourceKind.ABILITY,
            source_rules_unit_instance_id=None,
            source_model_instance_id=None,
        ),
        source_model_destroyed_event_id=model_events[-1].event_id,
        source_rules_unit_objective_proximity_witness=None,
        source_battlefield_departure_ids=tuple(departure.departure_id for departure in departures),
        unattributed_cause=None,
        source_mutation_id=None,
        destroyed_unit_instance_id=action.unit_instance_id,
        source_id="phase17n-action-canonical-destruction-completion",
    )
    completion_event = record_primary_unit_destruction_event(
        event_log=decisions.event_log,
        destruction=destruction,
    )

    interrupted = reconcile_primary_mission_action_interruptions(
        state=state,
        decisions=decisions,
    )

    assert len(interrupted) == 1
    terminal_payload = cast(dict[str, JsonValue], decisions.event_log.records[-1].payload)
    assert terminal_payload["source_evidence_event_id"] == completion_event.event_id
    assert terminal_payload["source_evidence_event_type"] == (
        PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
    )
    restored_state = GameState.from_payload(state.to_payload())
    restored_log = EventLog.from_payload(decisions.event_log.to_payload())
    validate_primary_mission_action_integrity(
        state=restored_state,
        event_records=restored_log.records,
    )


def test_phase17n_reconciliation_ignores_remain_stationary_pile_in_and_consolidate() -> None:
    for event_type, displacement_kind, movement_action in (
        ("movement_activation_completed", None, "remain_stationary"),
        ("fight_movement_completed", ModelDisplacementKind.PILE_IN, None),
        ("fight_movement_completed", ModelDisplacementKind.CONSOLIDATE, None),
    ):
        state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
            layout_id="purge-the-foe-vs-priority-assets-layout-1",
            attacker_force_disposition_id="purge-the-foe",
            defender_force_disposition_id="priority-assets",
            player_id="player-b",
            mission_action_id="maintain-control",
            current_phase=BattlePhase.FIGHT,
        )
        payload: dict[str, JsonValue] = {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.FIGHT.value,
            "unit_instance_id": action.unit_instance_id,
        }
        if movement_action is not None:
            payload["movement_phase_action"] = movement_action
        if displacement_kind is not None:
            assert state.battlefield_state is not None
            placement = state.battlefield_state.unit_placement_by_id(
                action.unit_instance_id
            ).model_placements[0]
            payload["transition_batch"] = validate_json_value(
                BattlefieldTransitionBatch(
                    displacements=(
                        ModelDisplacementRecord(
                            model_instance_id=placement.model_instance_id,
                            displacement_kind=displacement_kind,
                            start_pose=placement.pose,
                            end_pose=Pose.at(
                                placement.pose.position.x + 0.5,
                                placement.pose.position.y,
                                placement.pose.position.z,
                                facing_degrees=placement.pose.facing.degrees,
                            ),
                        ),
                    )
                ).to_payload()
            )
        decisions.event_log.append(event_type, payload)

        assert (
            reconcile_primary_mission_action_interruptions(
                state=state,
                decisions=decisions,
            )
            == ()
        )
        assert state.mission_action_states[0].status is MissionActionStatus.STARTED


@pytest.mark.parametrize(
    ("removal_kind", "expected_reason"),
    [
        (BattlefieldRemovalKind.DESTROYED, "unit_destroyed"),
        (BattlefieldRemovalKind.INTO_RESERVES, "unit_left_battlefield"),
    ],
)
def test_phase17n_reconciliation_distinguishes_destruction_and_departure(
    removal_kind: BattlefieldRemovalKind,
    expected_reason: str,
) -> None:
    state, decisions, action, _target_id = _phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(action.unit_instance_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    if removal_kind is BattlefieldRemovalKind.DESTROYED:
        _phase17n_set_model_wounds(
            state,
            model_ids=removed_model_ids,
            wounds_remaining=0,
        )
        state.battlefield_state = state.battlefield_state.with_removed_models(removed_model_ids)
    else:
        state.battlefield_state = state.battlefield_state.without_unit_placement(
            action.unit_instance_id
        )
        state.record_reserve_state(
            ReserveState.entered_during_battle(
                player_id=action.player_id,
                unit_instance_id=action.unit_instance_id,
                reserve_kind=ReserveKind.STRATEGIC_RESERVES,
                battle_round=state.battle_round,
                phase=BattlePhase.FIGHT,
                source_rule_ids=("phase17n-departure-reserve-authority",),
            )
        )
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=action.unit_instance_id,
        affected_component_unit_instance_ids=(action.unit_instance_id,),
        departed_component_unit_instance_ids=(action.unit_instance_id,),
        removed_model_instance_ids=removed_model_ids,
        removal_kind=removal_kind,
        occurrence_id=f"phase17n-departure:{removal_kind.value}",
        source_id=f"phase17n-departure-source:{removal_kind.value}",
    )
    assert departure is not None
    evidence = record_primary_battlefield_departure_event(
        event_log=decisions.event_log,
        departure=departure,
    )

    interrupted = reconcile_primary_mission_action_interruptions(
        state=state,
        decisions=decisions,
    )

    assert len(interrupted) == 1
    assert interrupted[0].interrupted_reason == expected_reason
    terminal_payload = cast(dict[str, JsonValue], decisions.event_log.records[-1].payload)
    assert terminal_payload["source_evidence_event_id"] == evidence.event_id
    validate_primary_mission_action_integrity(
        state=state,
        event_records=decisions.event_log.records,
    )


def _phase17n_started_primary_action_fixture(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    player_id: str,
    mission_action_id: str,
    current_phase: BattlePhase,
    player_unit_count: int = 1,
    completion_control_kind: str | None = None,
) -> tuple[GameState, DecisionController, MissionActionState, str]:
    if player_unit_count == 1:
        state = battle_state()
    elif player_unit_count == 2 and player_id == "player-a":
        state = battle_state(
            player_a_units=(
                default_unit_selection("intercessor-unit-1"),
                default_unit_selection("intercessor-unit-2"),
            )
        )
    else:
        raise AssertionError("Phase 17N action fixture supports one unit or two player-a units.")
    state.mission_setup = _phase17n_event_setup(
        layout_id=layout_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_force_disposition_id=defender_force_disposition_id,
    )
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=state.mission_setup.battlefield_width_inches,
        battlefield_depth_inches=state.mission_setup.battlefield_depth_inches,
        terrain_features=state.mission_setup.terrain_features,
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.active_player_id = player_id
    runtime_action = mission_action_for_state(
        state=state,
        mission_action_id=mission_action_id,
    )
    state.battle_round = (
        2
        if runtime_action.start_timing == "shooting_phase_action_start_from_battle_round_two"
        else 1
    )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    units = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == player_id
        for unit in army.units
    )
    assert len(units) == player_unit_count
    unit = units[0]
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    if runtime_action.target_policy == "terrain_area_in_enemy_territory":
        opponent_id = next(
            candidate_id for candidate_id in state.player_ids if candidate_id != player_id
        )
        target_area = next(
            area
            for area in mission_logical_terrain_areas(state.mission_setup)
            if logical_terrain_area_within_player_territory(
                area,
                mission_setup=state.mission_setup,
                player_id=opponent_id,
            )
        )
        target_id = target_area.logical_terrain_area_id
        min_x, min_y, max_x, max_y = target_area.bounds()
        target_x = (min_x + max_x) / 2.0
        target_y = (min_y + max_y) / 2.0
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            target_x + (index * 0.1),
                            target_y,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )
    elif runtime_action.target_policy == "visible_enemy_unit_within_18_not_surveilled_this_turn":
        target_unit = next(
            enemy
            for army in state.army_definitions
            if army.player_id != player_id
            for enemy in army.units
        )
        target_id = target_unit.unit_instance_id
        target_placement = state.battlefield_state.unit_placement_by_id(target_id)
        target_pose = target_placement.model_placements[0].pose
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            target_pose.position.x - 6.0 - (index * 0.1),
                            target_pose.position.y,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )
    else:
        target_marker = next(
            marker
            for marker in state.mission_setup.objective_markers
            if marker.objective_role is ObjectiveMarkerRole.CENTRAL
        )
        target_id = target_marker.objective_marker_id
        placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                target_marker,
                offsets=((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)),
            )
        )
        additional_targets = tuple(
            marker
            for marker in state.mission_setup.objective_markers
            if marker.objective_role is ObjectiveMarkerRole.CENTRAL
            and marker.objective_marker_id != target_id
        )
        assert len(additional_targets) >= len(units) - 1
        selected_additional_targets = additional_targets[: len(units) - 1]
        for additional_unit, additional_target in zip(
            units[1:], selected_additional_targets, strict=True
        ):
            additional_placement = state.battlefield_state.unit_placement_by_id(
                additional_unit.unit_instance_id
            )
            state.battlefield_state = state.battlefield_state.with_unit_placement(
                with_model_offsets(
                    additional_placement,
                    additional_target,
                    offsets=(
                        (0.0, 0.0),
                        (1.0, 0.0),
                        (2.0, 0.0),
                        (0.0, 1.0),
                        (1.0, 1.0),
                    ),
                )
            )
    if completion_control_kind is not None:
        if completion_control_kind not in {"uncontrolled", "non_lineage_contributor"}:
            raise AssertionError("Unsupported completion-control fixture kind.")
        target_marker = next(
            marker
            for marker in state.mission_setup.objective_markers
            if marker.objective_marker_id == target_id
        )
        if completion_control_kind == "non_lineage_contributor":
            if len(units) != 2:
                raise AssertionError("Non-lineage control fixture requires two player units.")
            contributor_placement = state.battlefield_state.unit_placement_by_id(
                units[1].unit_instance_id
            )
            state.battlefield_state = state.battlefield_state.with_unit_placement(
                with_model_offsets(
                    contributor_placement,
                    target_marker,
                    offsets=tuple(
                        ((index % 3) * 0.5, (index // 3) * 0.5)
                        for index, _model in enumerate(contributor_placement.model_placements)
                    ),
                )
            )
    decisions = DecisionController()
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id=player_id,
        mission_action_id=mission_action_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert status.decision_request is not None
    request = status.decision_request
    selected_option = next(
        option
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
        and cast(dict[str, JsonValue], option.payload)["unit_instance_id"] == unit.unit_instance_id
        and cast(dict[str, JsonValue], option.payload)["target_id"] == target_id
    )
    result = DecisionResult.for_request(
        result_id=f"phase17n-action-result:{mission_action_id}:{player_id}",
        request=request,
        selected_option_id=selected_option.option_id,
    )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(result)
    action = state.mission_action_states[-1]
    state.battle_phase_index = state.battle_phase_sequence.index(current_phase)
    if completion_control_kind == "uncontrolled":
        state.battle_shocked_unit_ids = [action.unit_instance_id]
        state.battle_shocked_unit_states = [
            BattleShockedUnitState(
                player_id=action.player_id,
                unit_instance_id=action.unit_instance_id,
                model_instance_ids=unit.own_model_ids(),
                source_result_id="phase17n-completion-control-battle-shock",
                battle_round_started=state.battle_round,
                expires_at_player_command_phase_start=action.player_id,
                expires_at_battle_round=state.battle_round + 1,
            )
        ]
    elif completion_control_kind == "non_lineage_contributor":
        action_placement = state.battlefield_state.unit_placement_by_id(action.unit_instance_id)
        removed_model_ids = tuple(
            model.model_instance_id for model in action_placement.model_placements
        )
        state.battlefield_state = state.battlefield_state.without_unit_placement(
            action.unit_instance_id
        )
        departure = record_primary_battlefield_departure(
            state=state,
            rules_unit_instance_id=action.unit_instance_id,
            affected_component_unit_instance_ids=(action.unit_instance_id,),
            departed_component_unit_instance_ids=(action.unit_instance_id,),
            removed_model_instance_ids=removed_model_ids,
            removal_kind=BattlefieldRemovalKind.TEMPORARILY_REMOVED,
            occurrence_id="phase17n-completion-control-departure",
            source_id="phase17n-completion-control-departure-source",
        )
        if departure is None:
            raise AssertionError("Completion-control departure evidence was not recorded.")
        record_primary_battlefield_departure_event(
            event_log=decisions.event_log,
            departure=departure,
        )
    return state, decisions, action, target_id


def _phase17n_action_turn_end_record(
    *,
    state: GameState,
    decisions: DecisionController,
    controlled_target_id: str,
    action: MissionActionState,
    contributing_unit_instance_id: str | None = None,
) -> ObjectiveControlRecord:
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    record = shared_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=controlled_target_id,
        action=action,
    )
    if contributing_unit_instance_id is not None:
        target_result = next(
            result for result in record.results if result.objective_id == controlled_target_id
        )
        if not any(
            contribution.unit_instance_id == contributing_unit_instance_id
            and contribution.effective_objective_control > 0
            for contribution in target_result.contributors
        ):
            raise AssertionError("Completion-control contributor did not resolve at target.")
    return record


def _phase17n_forged_completion_marker(
    *,
    state: GameState,
    action: MissionActionState,
    source_event_id: str,
) -> PrimaryMissionMarkerState:
    descriptor = mission_action_policy_for_id(action.mission_action_id)
    marker_id = primary_mission_marker_id(
        game_id=state.game_id,
        owner_player_id=action.player_id,
        mission_id=action.mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.mission_action_id,
        marker_kind="operation",
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=action.target_id,
        terrain_feature_id=None,
        created_battle_round=state.battle_round,
        created_phase=BattlePhase.FIGHT.value,
        created_active_player_id=action.player_id,
        source_event_id=source_event_id,
        source_result_id=None,
        source_action_id=action.action_id,
        source_destruction_id=None,
        source_designation_id=None,
    )
    return PrimaryMissionMarkerState(
        marker_id=marker_id,
        game_id=state.game_id,
        owner_player_id=action.player_id,
        mission_id=action.mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.mission_action_id,
        marker_kind="operation",
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=action.target_id,
        terrain_feature_id=None,
        created_battle_round=state.battle_round,
        created_phase=BattlePhase.FIGHT.value,
        created_active_player_id=action.player_id,
        source_event_id=source_event_id,
        source_result_id=None,
        source_action_id=action.action_id,
        source_destruction_id=None,
        source_designation_id=None,
    )


def _phase17n_set_model_wounds(
    state: GameState,
    *,
    model_ids: tuple[str, ...],
    wounds_remaining: int,
) -> None:
    requested_ids = set(model_ids)
    state.army_definitions = [
        replace(
            army,
            units=tuple(
                replace(
                    unit,
                    own_models=tuple(
                        replace(model, wounds_remaining=wounds_remaining)
                        if model.model_instance_id in requested_ids
                        else model
                        for model in unit.own_models
                    ),
                )
                if requested_ids.intersection(unit.own_model_ids())
                else unit
                for unit in army.units
            ),
        )
        for army in state.army_definitions
    ]


def _phase17n_surveil_integrity_fixture() -> tuple[GameState, DecisionController]:
    state, decisions, action, target_id = _phase17n_started_primary_action_fixture(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="decoy-objective",
        current_phase=BattlePhase.FIGHT,
    )
    record = _phase17n_action_turn_end_record(
        state=state,
        decisions=decisions,
        controlled_target_id=target_id,
        action=action,
    )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1

    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    moving_unit = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-b"
        for unit in army.units
    )
    objective = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_marker_id == target_id
    )
    placement = state.battlefield_state.unit_placement_by_id(moving_unit.unit_instance_id)
    anchor = placement.model_placements[0].pose.position
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=moving_unit.unit_instance_id,
        suffix="surveil-marker-removal",
        pose_transform=lambda pose: Pose.at(
            pose.position.x + objective.x_inches - anchor.x,
            pose.position.y + objective.y_inches - anchor.y,
            pose.position.z + objective.z_inches - anchor.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
    resolve_surveil_marker_removal_for_completed_moves(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.MOVEMENT,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert state.primary_mission_progress_state.markers[0].status is (
        PrimaryMissionMarkerStatus.REMOVED
    )
    assert decisions.event_log.records[-1].event_type == (
        "primary_surveil_move_marker_removal_resolved"
    )
    return state, decisions
