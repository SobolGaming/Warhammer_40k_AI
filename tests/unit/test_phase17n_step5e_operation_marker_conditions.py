from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17n_step5e_operation_marker_conditions import (
    _OPERATION_MARKER_KIND,
    EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
    EXTRACT_INTELLIGENCE_ACTION_ID,
    FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
    MAINTAIN_CONTROL_ACTION_ID,
    NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
    OBJECTIVE_CONTROL_HORIZONTAL_INCHES,
    ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
    ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
    ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
    ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS,
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
    BattlePhase,
    DecisionController,
    DecisionResult,
    EventLog,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    JsonValue,
    MarkerAnchorKind,
    MissionActionState,
    MissionLogicalTerrainArea,
    MissionSetup,
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    Pose,
    PrimaryComponentTurnStartMembership,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    PrimaryRulesUnitTurnStartMembership,
    PrimaryScoringConditionContext,
    PrimaryScoringRulesUnitPositionWitness,
    RuntimeModifierRegistry,
    VictoryPointSourceKind,
    _action_marker,
    _active_maintain_control_markers,
    _assert_operation_marker_boundary_path,
    _bind_force_dispositions,
    _central_objective_ids,
    _complete_started_maintain_control,
    _completed_extract_intelligence_action,
    _expansion_objective_ids,
    _far_from_objectives,
    _first_logical_terrain_id,
    _gather_intel_setup,
    _locate_setup,
    _non_home_objective_ids,
    _objective_context,
    _objective_marker_progress,
    _place_player_unit_at,
    _place_unit_in_terrain,
    _plant_extract_intelligence_markers,
    _position_witness,
    _position_witnesses,
    _primary_awards_by_condition,
    _resolved_primary_action,
    _second_logical_terrain_id,
    _start_maintain_control,
    _terrain_marker,
    _terrain_marker_progress,
    _two_turn_maintain_control_same_central,
    _vital_link_setup,
    deepcopy,
    evaluate_operation_marker_scoring_condition,
    evaluate_primary_scoring_condition,
    extract_intelligence_marker_source_identity,
    home_objective_ids,
    locate_and_deny_marker_source_identity,
    maintain_control_marker_source_identity,
    math,
    mission_action_policy_for_id,
    mission_logical_terrain_areas,
    mission_scoring_policies_from_setup,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    phase17n_state_with_setup,
    primary_mission_marker_id,
    primary_scoring_rules_from_definition,
    pytest,
    replace,
    request_mission_action_start,
    resolve_objective_control,
    resolve_primary_mission_actions_at_turn_end,
    score_primary_objective_control_boundary,
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase17n_step5e_terrain_occupancy_requires_position_witnesses() -> None:
    setup = _locate_setup()
    with pytest.raises(GameLifecycleError, match="requires position witnesses"):
        evaluate_operation_marker_scoring_condition(
            condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
            progress=PrimaryMissionProgressState.empty(),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            end_of_battle=False,
        )


def test_phase17n_step5e_gather_intel_three_marker_threshold_is_end_of_battle_windowed() -> None:
    setup = _gather_intel_setup()
    objective_ids = _non_home_objective_ids(setup)[:3]
    three = _objective_marker_progress(
        setup,
        owner_player_id="player-a",
        mission_id="primary-gather-intel",
        source_identity=extract_intelligence_marker_source_identity(),
        objective_ids=objective_ids,
    )
    two = _objective_marker_progress(
        setup,
        owner_player_id="player-a",
        mission_id="primary-gather-intel",
        source_identity=extract_intelligence_marker_source_identity(),
        objective_ids=objective_ids[:2],
    )
    matching = evaluate_operation_marker_scoring_condition(
        condition_id=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        progress=three,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    below = evaluate_operation_marker_scoring_condition(
        condition_id=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        progress=two,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    ordinary = evaluate_operation_marker_scoring_condition(
        condition_id=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        progress=three,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=False,
    )
    wrong_identity = evaluate_operation_marker_scoring_condition(
        condition_id=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-a",
            mission_id="primary-gather-intel",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=objective_ids,
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    assert matching["score_count"] == 1
    assert below["score_count"] == 0
    assert ordinary["score_count"] == 0
    assert wrong_identity["score_count"] == 0


def test_phase17n_step5e_gather_intel_home_range_uses_extract_intel_identity() -> None:
    setup = _gather_intel_setup()
    opponent_home = home_objective_ids(setup, player_id="player-b")[0]
    far_expansion = _far_from_objectives(
        setup,
        candidate_ids=_expansion_objective_ids(setup),
        reference_ids=(opponent_home,),
    )
    on_home = evaluate_operation_marker_scoring_condition(
        condition_id=FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-a",
            mission_id="primary-gather-intel",
            source_identity=extract_intelligence_marker_source_identity(),
            objective_ids=(opponent_home,),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    far = evaluate_operation_marker_scoring_condition(
        condition_id=FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-a",
            mission_id="primary-gather-intel",
            source_identity=extract_intelligence_marker_source_identity(),
            objective_ids=(far_expansion,),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    ordinary = evaluate_operation_marker_scoring_condition(
        condition_id=FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-a",
            mission_id="primary-gather-intel",
            source_identity=extract_intelligence_marker_source_identity(),
            objective_ids=(opponent_home,),
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=False,
    )
    assert on_home["score_count"] == 1
    assert far["score_count"] == 0
    assert ordinary["score_count"] == 0


def test_phase17n_step5e_gather_intel_rejects_duplicate_objective_anchors() -> None:
    setup = _gather_intel_setup()
    objective_id = _non_home_objective_ids(setup)[0]
    with pytest.raises(GameLifecycleError, match="must not duplicate an objective"):
        evaluate_operation_marker_scoring_condition(
            condition_id=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
            progress=_objective_marker_progress(
                setup,
                owner_player_id="player-a",
                mission_id="primary-gather-intel",
                source_identity=extract_intelligence_marker_source_identity(),
                objective_ids=(objective_id, objective_id),
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=5,
            end_of_battle=True,
        )


def test_phase17n_step5e_locate_and_extract_terrain_occupancy_is_exclusive() -> None:
    setup = _locate_setup()
    terrain_id = _first_logical_terrain_id(setup)
    other_terrain_id = _second_logical_terrain_id(setup, excluded_id=terrain_id)
    occupied = _position_witnesses(
        friendly_player_id="player-a",
        enemy_player_id="player-b",
        friendly_terrain_ids=(terrain_id,),
        enemy_terrain_ids=(),
    )
    empty = _position_witnesses(
        friendly_player_id="player-a",
        enemy_player_id="player-b",
        friendly_terrain_ids=(),
        enemy_terrain_ids=(),
    )
    contested = _position_witnesses(
        friendly_player_id="player-a",
        enemy_player_id="player-b",
        friendly_terrain_ids=(terrain_id,),
        enemy_terrain_ids=(terrain_id,),
    )
    extract_occupied = _position_witnesses(
        friendly_player_id="player-b",
        enemy_player_id="player-a",
        friendly_terrain_ids=(terrain_id,),
        enemy_terrain_ids=(),
    )
    one = _terrain_marker_progress(
        setup,
        owner_player_id="player-a",
        mission_id="primary-locate-and-deny",
        source_identity=locate_and_deny_marker_source_identity(),
        terrain_ids=(terrain_id,),
    )
    two = _terrain_marker_progress(
        setup,
        owner_player_id="player-a",
        mission_id="primary-locate-and-deny",
        source_identity=locate_and_deny_marker_source_identity(),
        terrain_ids=(terrain_id, other_terrain_id),
    )
    matching = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        progress=one,
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        end_of_battle=False,
        position_witnesses=occupied,
    )
    two_remaining = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        progress=two,
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        end_of_battle=False,
        position_witnesses=occupied,
    )
    absent = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        progress=one,
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        end_of_battle=False,
        position_witnesses=empty,
    )
    enemy = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        progress=one,
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        end_of_battle=False,
        position_witnesses=contested,
    )
    extract_matching = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
        progress=one,
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
        end_of_battle=False,
        position_witnesses=extract_occupied,
    )
    eob_ordinary = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        progress=one,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=False,
    )
    eob = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        progress=one,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
        position_witnesses=occupied,
    )
    extract_eob = evaluate_operation_marker_scoring_condition(
        condition_id=ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
        progress=one,
        mission_setup=setup,
        player_id="player-b",
        battle_round=5,
        end_of_battle=True,
        position_witnesses=extract_occupied,
    )
    assert matching["score_count"] == 1
    assert two_remaining["score_count"] == 0
    assert absent["score_count"] == 0
    assert enemy["score_count"] == 0
    assert extract_matching["score_count"] == 1
    assert eob_ordinary["score_count"] == 0
    assert eob["score_count"] == 1
    assert extract_eob["score_count"] == 1


def test_phase17n_step5e_scores_gather_intel_end_of_battle_through_shared_boundary() -> None:
    state, _ordinary_record = _resolved_primary_action(
        layout_id="reconnaissance-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id=EXTRACT_INTELLIGENCE_ACTION_ID,
    )
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5E Gather Intel EOB fixture requires MissionSetup.")
    existing_objectives = {
        marker.objective_marker_id
        for marker in state.primary_mission_progress_state.markers
        if marker.objective_marker_id is not None
    }
    extra_ids = tuple(
        objective_id
        for objective_id in _non_home_objective_ids(setup)
        if objective_id not in existing_objectives
    )[:2]
    opponent_home = home_objective_ids(setup, player_id="player-b")[0]
    _plant_extract_intelligence_markers(
        state,
        objective_ids=(*extra_ids, opponent_home),
        start_index=2,
        replace_progress=False,
    )
    policies = mission_scoring_policies_from_setup(setup)
    state.battle_round = policies.game_length_battle_rounds
    state.active_player_id = state.turn_order[-1]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    _assert_operation_marker_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
        expected_vp=5,
        end_of_battle=True,
        require_restore=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert awards[FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE] == 5


__all__: list[str] = []
__all__ += ["DecisionController", "DecisionResult"]
__all__ += ["EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE", "EventLog"]
__all__ += ["MAINTAIN_CONTROL_ACTION_ID", "GameLifecycle", "GameState", "JsonValue"]
__all__ += ["MarkerAnchorKind", "MissionActionState", "MissionLogicalTerrainArea", "MissionSetup"]
__all__ += ["NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD", "OBJECTIVE_CONTROL_HORIZONTAL_INCHES"]
__all__ += ["ObjectiveControlContext", "ObjectiveControlRecord", "ObjectiveControlResult"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS", "Pose"]
__all__ += ["PrimaryComponentTurnStartMembership", "PrimaryMissionMarkerState"]
__all__ += ["PrimaryMissionMarkerStatus", "PrimaryRulesUnitTurnStartMembership"]
__all__ += ["PrimaryScoringConditionContext", "PrimaryScoringRulesUnitPositionWitness"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "VictoryPointSourceKind"]
__all__ += ["_OPERATION_MARKER_KIND", "_action_marker", "_active_maintain_control_markers"]
__all__ += ["_bind_force_dispositions", "_central_objective_ids"]
__all__ += ["_complete_started_maintain_control", "_completed_extract_intelligence_action"]
__all__ += ["_objective_context", "_place_player_unit_at", "_place_unit_in_terrain"]
__all__ += ["_position_witness", "_start_maintain_control", "_terrain_marker"]
__all__ += ["_two_turn_maintain_control_same_central", "_vital_link_setup", "cast", "deepcopy"]
__all__ += ["evaluate_primary_scoring_condition", "math", "mission_action_policy_for_id"]
__all__ += ["mission_logical_terrain_areas", "phase17n_event_setup"]
__all__ += ["phase17n_started_primary_action_fixture", "phase17n_state_with_setup"]
__all__ += ["primary_mission_marker_id", "primary_scoring_rules_from_definition", "replace"]
__all__ += ["request_mission_action_start", "resolve_objective_control"]
__all__ += ["resolve_primary_mission_actions_at_turn_end"]
__all__ += ["score_primary_objective_control_boundary"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
