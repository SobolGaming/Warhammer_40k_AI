from __future__ import annotations

from tests.shared.category_migration.phase17n_step5b_marker_conditions import (
    PRIMARY_OPERATION_MARKER_KIND,
    PRIMARY_SCORING_DECOY_OPPONENT_TERRITORY_OBJECTIVE_CONDITION,
    PRIMARY_SCORING_MARKER_CONDITIONS,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    BattlefieldRegionKind,
    BattlePhase,
    DecisionResult,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    MarkerAnchorKind,
    MissionSetup,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    PrimaryConsecrationDesignationState,
    PrimaryMissionChoiceData,
    PrimaryMissionMarkerState,
    PrimaryMissionProgressState,
    PrimaryScoringConditionContext,
    RuntimeModifierRegistry,
    VictoryPointSourceKind,
    _action_marker,
    _action_marker_progress,
    _bind_force_dispositions,
    _consecrate_setup,
    _consecrated_progress,
    _consecration_designation,
    _marker,
    _non_home_objective_ids,
    _objective_context,
    _opponent_territory_non_home_objective_ids,
    _primary_awards_by_condition,
    _resolved_primary_action,
    _smoke_setup,
    active_decoy_objective_ids,
    consecrated_marker_source_identity,
    decoy_marker_source_identity,
    evaluate_marker_scoring_condition,
    evaluate_primary_scoring_condition,
    home_objective_ids,
    mission_scoring_policies_from_setup,
    phase17n_consecrate_pending_fixture,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    primary_consecration_designation_id,
    primary_mission_marker_id,
    primary_scoring_rules_from_definition,
    pytest,
    replace,
    resolve_primary_mission_actions_at_turn_end,
    score_primary_objective_control_boundary,
    triangulated_marker_source_identity,
    warhammer_event_companion_2026_07_mission_pack,
)


def test_phase17n_step5b_marker_conditions_are_registered() -> None:
    assert PRIMARY_SCORING_MARKER_CONDITIONS <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    assert (
        PRIMARY_SCORING_DECOY_OPPONENT_TERRITORY_OBJECTIVE_CONDITION
        in PRIMARY_SCORING_SPATIAL_CONDITIONS
    )


def test_phase17n_step5b_promotes_marker_primary_missions() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    for mission_id in (
        "primary-consecrate",
        "primary-smoke-and-mirrors",
        "primary-triangulation",
    ):
        rules = primary_scoring_rules_from_definition(primary_by_id[mission_id])
        assert rules
        assert all(rule.condition in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS for rule in rules)


def test_phase17n_step5b_marker_conditions_require_state_evidence() -> None:
    setup = _consecrate_setup()
    context = _objective_context(setup=setup, battle_round=2)
    with pytest.raises(GameLifecycleError, match="requires state evidence"):
        evaluate_primary_scoring_condition(
            condition="one_or_two_objectives_consecrated",
            context=context,
        )


def test_phase17n_step5b_consecrated_thresholds_are_exclusive() -> None:
    setup = _consecrate_setup()
    objective_ids = _non_home_objective_ids(setup)[:3]
    two = evaluate_marker_scoring_condition(
        condition_id="one_or_two_objectives_consecrated",
        progress=_consecrated_progress(setup, objective_ids[:2]),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )
    three_on_two = evaluate_marker_scoring_condition(
        condition_id="three_or_more_objectives_consecrated",
        progress=_consecrated_progress(setup, objective_ids[:2]),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )
    three = evaluate_marker_scoring_condition(
        condition_id="three_or_more_objectives_consecrated",
        progress=_consecrated_progress(setup, objective_ids),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )
    one_or_two_on_three = evaluate_marker_scoring_condition(
        condition_id="one_or_two_objectives_consecrated",
        progress=_consecrated_progress(setup, objective_ids),
        mission_setup=setup,
        player_id="player-a",
        battle_round=2,
        end_of_battle=False,
    )

    assert two["score_count"] == 1
    assert three_on_two["score_count"] == 0
    assert three["score_count"] == 1
    assert one_or_two_on_three["score_count"] == 0


def test_phase17n_step5b_triangulated_thresholds_are_windowed() -> None:
    setup = _consecrate_setup()
    objective_ids = _non_home_objective_ids(setup)[:3]
    progress = _action_marker_progress(
        setup,
        owner_player_id="player-b",
        mission_id="primary-triangulation",
        source_identity=triangulated_marker_source_identity(),
        objective_ids=objective_ids[:1],
    )
    round_two = evaluate_marker_scoring_condition(
        condition_id="exactly_one_triangulated_objective",
        progress=progress,
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
    )
    round_one = evaluate_marker_scoring_condition(
        condition_id="exactly_one_triangulated_objective",
        progress=progress,
        mission_setup=setup,
        player_id="player-b",
        battle_round=1,
        end_of_battle=False,
    )
    exactly_two = evaluate_marker_scoring_condition(
        condition_id="exactly_two_triangulated_objectives",
        progress=_action_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-triangulation",
            source_identity=triangulated_marker_source_identity(),
            objective_ids=objective_ids[:2],
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
    )
    three_or_more = evaluate_marker_scoring_condition(
        condition_id="three_or_more_triangulated_objectives",
        progress=_action_marker_progress(
            setup,
            owner_player_id="player-b",
            mission_id="primary-triangulation",
            source_identity=triangulated_marker_source_identity(),
            objective_ids=objective_ids,
        ),
        mission_setup=setup,
        player_id="player-b",
        battle_round=2,
        end_of_battle=False,
    )

    assert round_two["score_count"] == 1
    assert round_one["score_count"] == 0
    assert exactly_two["score_count"] == 1
    assert three_or_more["score_count"] == 1


def test_phase17n_step5b_ignores_removed_opponent_and_operation_markers() -> None:
    setup = _smoke_setup()
    objective_ids = _non_home_objective_ids(setup)
    decoy_identity = decoy_marker_source_identity()
    active = _action_marker(
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_identity,
        objective_id=objective_ids[0],
        index=1,
    )
    removed = _action_marker(
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_identity,
        objective_id=objective_ids[1],
        index=2,
    ).removed(
        battle_round=2,
        phase=BattlePhase.FIGHT.value,
        active_player_id="player-a",
        source_id="step5b-removal-source",
        event_id="step5b-removal-event",
    )
    opponent = _action_marker(
        owner_player_id="player-b",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_identity,
        objective_id=objective_ids[2],
        index=3,
    )
    operation = _action_marker(
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=("step5b-operation-source", "extract-intelligence"),
        objective_id=objective_ids[3],
        index=4,
    )
    progress = PrimaryMissionProgressState.empty()
    for marker in (active, removed, opponent, operation):
        progress = progress.add_marker(marker)

    assert active_decoy_objective_ids(
        progress,
        player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        mission_setup=setup,
    ) == (objective_ids[0],)


def test_phase17n_step5b_enemy_home_consecration_requires_end_of_battle() -> None:
    setup = _consecrate_setup()
    enemy_home_id = home_objective_ids(setup, player_id="player-b")[0]
    progress = _consecrated_progress(setup, (enemy_home_id,))
    ordinary = evaluate_marker_scoring_condition(
        condition_id="enemy_home_objective_consecrated_end_of_battle",
        progress=progress,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=False,
    )
    end_of_battle = evaluate_marker_scoring_condition(
        condition_id="enemy_home_objective_consecrated_end_of_battle",
        progress=progress,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    assert ordinary["score_count"] == 0
    assert end_of_battle["score_count"] == 1


def test_phase17n_step5b_four_decoy_threshold_requires_end_of_battle() -> None:
    setup = _smoke_setup()
    progress = _action_marker_progress(
        setup,
        owner_player_id="player-a",
        mission_id="primary-smoke-and-mirrors",
        source_identity=decoy_marker_source_identity(),
        objective_ids=_non_home_objective_ids(setup)[:4],
    )
    ordinary = evaluate_marker_scoring_condition(
        condition_id="four_or_more_decoy_objectives_end_of_battle",
        progress=progress,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=False,
    )
    achieved = evaluate_marker_scoring_condition(
        condition_id="four_or_more_decoy_objectives_end_of_battle",
        progress=progress,
        mission_setup=setup,
        player_id="player-a",
        battle_round=5,
        end_of_battle=True,
    )
    assert ordinary["score_count"] == 0
    assert achieved["score_count"] == 1


def test_phase17n_step5b_scores_consecrated_thresholds_through_shared_boundary() -> None:
    state, decisions, request = phase17n_consecrate_pending_fixture()
    option = next(
        candidate
        for candidate in request.options
        if PrimaryMissionChoiceData.from_payload(candidate.payload).selected_target_ids
    )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(
        DecisionResult.for_request(
            result_id="step5b-consecrate-select-result",
            request=request,
            selected_option_id=option.option_id,
        )
    )
    record = state.objective_control_records[-1]
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert awards["one_or_two_objectives_consecrated"] == 3
    assert "three_or_more_objectives_consecrated" not in awards
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()
    assert restored.primary_scoring_state_evidence_records == (
        state.primary_scoring_state_evidence_records
    )
    bound_record_ids = {
        bound_record_id
        for ledger in restored.victory_point_ledgers
        for transaction in ledger.transactions
        if type(transaction.metadata) is dict
        and transaction.metadata.get("scoring_rule_condition")
        == "one_or_two_objectives_consecrated"
        for bound_record_id in (transaction.metadata.get("objective_control_record_id"),)
        if type(bound_record_id) is str
    }
    assert record.record_id in bound_record_ids


def test_phase17n_step5b_scores_triangulated_and_decoy_markers_through_shared_boundary() -> None:
    triangulation_state, triangulation_record = _resolved_primary_action(
        layout_id="purge-the-foe-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="reconnaissance",
        player_id="player-b",
        mission_action_id="triangulate-objective",
    )
    score_primary_objective_control_boundary(
        state=triangulation_state,
        record=triangulation_record,
        end_of_battle=False,
    )
    triangulation_awards = _primary_awards_by_condition(
        triangulation_state,
        player_id="player-b",
    )
    assert triangulation_awards["exactly_one_triangulated_objective"] == 3
    assert "exactly_two_triangulated_objectives" not in triangulation_awards

    smoke_setup = _smoke_setup()
    territory_ids = _opponent_territory_non_home_objective_ids(
        smoke_setup,
        player_id="player-a",
    )
    assert territory_ids
    smoke_state, smoke_record = _resolved_primary_action(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="decoy-objective",
        target_objective_id=territory_ids[0],
    )
    score_primary_objective_control_boundary(
        state=smoke_state,
        record=smoke_record,
        end_of_battle=False,
    )
    smoke_awards = _primary_awards_by_condition(smoke_state, player_id="player-a")
    assert smoke_awards["each_decoy_objective"] == 2
    assert smoke_awards["each_decoy_objective_in_opponent_territory_bonus"] == 2
    restored = GameState.from_payload(smoke_state.to_payload())
    assert restored.to_payload() == smoke_state.to_payload()


def test_phase17n_step5b_end_of_battle_marker_thresholds() -> None:
    state, _ordinary_record = _resolved_primary_action(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="reconnaissance",
        player_id="player-a",
        mission_action_id="decoy-objective",
    )
    if state.mission_setup is None:
        raise AssertionError("Step 5B EOB fixture requires MissionSetup.")
    policies = mission_scoring_policies_from_setup(state.mission_setup)
    state.battle_round = policies.game_length_battle_rounds
    state.active_player_id = state.turn_order[-1]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=True,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert "four_or_more_decoy_objectives_end_of_battle" not in awards
    assert _primary_awards_by_condition(state, player_id="player-b") == {}


def test_phase17n_step5b_decoy_territory_bonus_requires_spatial_evidence() -> None:
    setup = _smoke_setup()
    with pytest.raises(GameLifecycleError, match="requires spatial evidence"):
        evaluate_marker_scoring_condition(
            condition_id="each_decoy_objective_in_opponent_territory_bonus",
            progress=_action_marker_progress(
                setup,
                owner_player_id="player-a",
                mission_id="primary-smoke-and-mirrors",
                source_identity=decoy_marker_source_identity(),
                objective_ids=_non_home_objective_ids(setup)[:1],
            ),
            mission_setup=setup,
            player_id="player-a",
            battle_round=2,
            end_of_battle=False,
        )


__all__: list[str] = []
__all__ += ["BattlefieldRegionKind", "MarkerAnchorKind", "MissionSetup", "ObjectiveControlRecord"]
__all__ += ["PRIMARY_OPERATION_MARKER_KIND", "ObjectiveControlResult", "ObjectiveMarkerRole"]
__all__ += ["PrimaryConsecrationDesignationState", "PrimaryMissionMarkerState"]
__all__ += ["PrimaryScoringConditionContext", "VictoryPointSourceKind"]
__all__ += ["_bind_force_dispositions", "_consecration_designation", "_marker"]
__all__ += ["consecrated_marker_source_identity", "phase17n_event_setup"]
__all__ += ["phase17n_started_primary_action_fixture", "primary_consecration_designation_id"]
__all__ += ["primary_mission_marker_id", "replace", "resolve_primary_mission_actions_at_turn_end"]
