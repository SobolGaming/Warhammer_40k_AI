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


def test_phase17n_step5e_operation_marker_conditions_are_registered() -> None:
    assert (
        PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    )


def test_phase17n_step5e_promotes_operation_marker_primary_missions() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    for mission_id in (
        "primary-gather-intel",
        "primary-extract-relic",
        "primary-locate-and-deny",
        "primary-vital-link",
    ):
        rules = primary_scoring_rules_from_definition(primary_by_id[mission_id])
        assert rules
        assert all(rule.condition in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS for rule in rules)


def test_phase17n_step5e_operation_marker_conditions_require_state_evidence() -> None:
    setup = _gather_intel_setup()
    context = _objective_context(setup=setup, battle_round=5, end_of_battle=True)
    with pytest.raises(GameLifecycleError, match="requires state evidence"):
        evaluate_primary_scoring_condition(
            condition=THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
            context=context,
        )


def test_phase17n_step5e_vital_link_counts_markers_in_range_of_controlled_centrals() -> None:
    setup = _vital_link_setup()
    centrals = _central_objective_ids(setup)
    far_expansion = _far_from_objectives(
        setup,
        candidate_ids=_expansion_objective_ids(setup),
        reference_ids=centrals,
    )
    on_controlled = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-vital-link",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=centrals[:1],
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
        end_of_battle=False,
        controlled_objective_ids=centrals[:1],
    )
    uncontrolled = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-vital-link",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=centrals[:1],
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
        end_of_battle=False,
        controlled_objective_ids=(),
    )
    two_markers = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-vital-link",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=centrals[:2] if len(centrals) >= 2 else centrals,
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
        end_of_battle=False,
        controlled_objective_ids=centrals,
    )
    far = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-vital-link",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=(far_expansion,),
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
        end_of_battle=False,
        controlled_objective_ids=centrals,
    )
    assert on_controlled["score_count"] == 1
    assert uncontrolled["score_count"] == 0
    assert two_markers["score_count"] == min(2, len(centrals))
    assert far["score_count"] == 0


def test_phase17n_step5e_vital_link_counts_accumulated_markers_on_same_central() -> None:
    setup = _vital_link_setup()
    central_id = _central_objective_ids(setup)[0]
    matching = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-vital-link",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=(central_id, central_id),
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
        controlled_objective_ids=(central_id,),
    )
    lost_control = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-vital-link",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=(central_id, central_id),
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
        controlled_objective_ids=(),
    )
    assert matching["score_count"] == 2
    matching_ids = matching["operation_marker_ids"]
    assert type(matching_ids) is list
    assert len(matching_ids) == 2
    assert matching_ids[0] != matching_ids[1]
    assert matching["objective_marker_ids"] == [central_id, central_id]
    assert lost_control["score_count"] == 0
    assert lost_control["operation_marker_ids"] == []


def test_phase17n_step5e_no_enemy_operation_markers_counts_any_opponent_operation_kind() -> None:
    setup = _gather_intel_setup()
    empty = evaluate_operation_marker_scoring_condition(
        condition_id=NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
        progress=PrimaryMissionProgressState.empty(),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )
    opponent_extract = evaluate_operation_marker_scoring_condition(
        condition_id=NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-gather-intel",
            source_identity=extract_intelligence_marker_source_identity(),
            objective_ids=_non_home_objective_ids(setup)[:1],
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )
    opponent_maintain = evaluate_operation_marker_scoring_condition(
        condition_id=NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
        progress=_objective_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-gather-intel",
            source_identity=maintain_control_marker_source_identity(),
            objective_ids=_non_home_objective_ids(setup)[:1],
        ),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )
    assert empty["score_count"] == 1
    assert opponent_extract["score_count"] == 0
    assert opponent_maintain["score_count"] == 0


def test_phase17n_step5e_scores_vital_link_marker_bonus_through_shared_boundary() -> None:
    state, record = _resolved_primary_action(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id=MAINTAIN_CONTROL_ACTION_ID,
    )
    _assert_operation_marker_boundary_path(
        state=state,
        record=record,
        player_id="player-b",
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        expected_vp=1,
        end_of_battle=False,
    )


def test_phase17n_step5e_vital_link_scores_accumulated_same_central_markers() -> None:
    state, record, target_id, marker_ids = _two_turn_maintain_control_same_central()
    _assert_operation_marker_boundary_path(
        state=state,
        record=record,
        player_id="player-b",
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        expected_vp=2,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-b", battle_round=2)
    assert awards[EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE] == 2
    assert awards["control_one_or_more_central_objectives"] == 2
    round_total = sum(
        transaction.amount
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if (
            transaction.player_id == "player-b"
            and transaction.source_kind is VictoryPointSourceKind.PRIMARY
            and transaction.battle_round == 2
        )
    )
    assert round_total == 4
    evidence = next(
        row
        for row in state.primary_scoring_state_evidence_records
        if row.objective_control_record_id == record.record_id
    )
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5E accumulated Vital Link scoring requires MissionSetup.")
    reevaluated = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=evidence.primary_mission_progress_state,
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
        controlled_objective_ids=tuple(
            result.objective_id
            for result in record.results
            if result.controlled_by_player_id == "player-b"
        ),
    )
    assert reevaluated["score_count"] == 2
    assert reevaluated["operation_marker_ids"] == list(marker_ids)
    assert reevaluated["objective_marker_ids"] == [target_id, target_id]

    lost_control = deepcopy(state)
    lost_control.battle_round = 3
    _place_player_unit_at(lost_control, player_id="player-b", x_inches=2.0, y_inches=2.0)
    lost_record = lost_control.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    score_primary_objective_control_boundary(
        state=lost_control,
        record=lost_record,
        end_of_battle=False,
        event_log=EventLog(),
    )
    lost_awards = _primary_awards_by_condition(
        lost_control,
        player_id="player-b",
        battle_round=3,
    )
    assert all(
        result.objective_id != target_id or result.controlled_by_player_id != "player-b"
        for result in lost_record.results
    )
    assert EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE not in lost_awards

    remaining_id = marker_ids[0]
    removed_marker = next(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.marker_id == marker_ids[1]
    )
    reduced_progress = state.primary_mission_progress_state.replace_marker(
        removed_marker.removed(
            battle_round=2,
            phase=BattlePhase.FIGHT.value,
            active_player_id="player-b",
            source_id=maintain_control_marker_source_identity()[0],
            event_id="step5e-vital-link-accumulated-tombstone",
        )
    )
    reduced = evaluate_operation_marker_scoring_condition(
        condition_id=EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
        progress=reduced_progress,
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
        controlled_objective_ids=(target_id,),
    )
    assert reduced["score_count"] == 1
    assert reduced["operation_marker_ids"] == [remaining_id]


def test_phase17n_step5e_scores_locate_and_extract_occupancy_through_shared_boundary() -> None:
    setup = _locate_setup()
    terrain = mission_logical_terrain_areas(setup)[0]
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=1,
    )
    _place_unit_in_terrain(state, player_id="player-a", terrain=terrain)
    state.replace_primary_mission_progress_state(
        _terrain_marker_progress(
            setup,
            owner_player_id="player-a",
            mission_id="primary-locate-and-deny",
            source_identity=locate_and_deny_marker_source_identity(),
            terrain_ids=(terrain.logical_terrain_area_id,),
            game_id=state.game_id,
        )
    )
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    _assert_operation_marker_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
        expected_vp=4,
        end_of_battle=False,
    )

    extract_state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-b",
        phase=BattlePhase.FIGHT,
        battle_round=1,
    )
    _place_unit_in_terrain(extract_state, player_id="player-b", terrain=terrain)
    extract_state.replace_primary_mission_progress_state(
        _terrain_marker_progress(
            setup,
            owner_player_id="player-a",
            mission_id="primary-locate-and-deny",
            source_identity=locate_and_deny_marker_source_identity(),
            terrain_ids=(terrain.logical_terrain_area_id,),
            game_id=extract_state.game_id,
        )
    )
    extract_record = extract_state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    _assert_operation_marker_boundary_path(
        state=extract_state,
        record=extract_record,
        player_id="player-b",
        condition_id=ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
        expected_vp=4,
        end_of_battle=False,
    )


__all__: list[str] = []
__all__ += ["EXTRACT_INTELLIGENCE_ACTION_ID", "DecisionController", "DecisionResult"]
__all__ += ["FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE", "GameLifecycle"]
__all__ += ["GameState", "JsonValue", "MarkerAnchorKind", "MissionActionState"]
__all__ += ["OBJECTIVE_CONTROL_HORIZONTAL_INCHES", "MissionLogicalTerrainArea", "MissionSetup"]
__all__ += ["ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE"]
__all__ += ["ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE", "ObjectiveControlContext"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "Pose"]
__all__ += ["PrimaryComponentTurnStartMembership", "PrimaryMissionMarkerState"]
__all__ += ["PrimaryMissionMarkerStatus", "PrimaryRulesUnitTurnStartMembership"]
__all__ += ["PrimaryScoringConditionContext", "PrimaryScoringRulesUnitPositionWitness"]
__all__ += ["_OPERATION_MARKER_KIND", "_action_marker", "_active_maintain_control_markers"]
__all__ += ["_bind_force_dispositions", "_complete_started_maintain_control"]
__all__ += ["_completed_extract_intelligence_action", "_first_logical_terrain_id"]
__all__ += ["_plant_extract_intelligence_markers", "_position_witness", "_position_witnesses"]
__all__ += ["_second_logical_terrain_id", "_start_maintain_control", "_terrain_marker", "cast"]
__all__ += ["home_objective_ids", "math", "mission_action_policy_for_id"]
__all__ += ["mission_scoring_policies_from_setup", "phase17n_event_setup"]
__all__ += ["phase17n_started_primary_action_fixture", "primary_mission_marker_id", "replace"]
__all__ += ["request_mission_action_start", "resolve_objective_control"]
__all__ += ["resolve_primary_mission_actions_at_turn_end"]
