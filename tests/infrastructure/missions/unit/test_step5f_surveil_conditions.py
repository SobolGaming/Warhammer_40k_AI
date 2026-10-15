from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17n_step5f_surveil_conditions import (
    _ATTACHED_BODYGUARD,
    _ATTACHED_LEADER,
    _ATTACHED_SECOND_LEADER,
    _ATTACHED_UNIT,
    _ENEMY_UNIT_ONE,
    _ENEMY_UNIT_TWO,
    _FRIENDLY_UNIT,
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
    NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    PRIMARY_SCORING_SURVEIL_CONDITIONS,
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    SURVEIL_ENEMY_UNIT_ACTION_ID,
    AttachedUnitFormation,
    BattlefieldRemovalKind,
    BattlePhase,
    DecisionController,
    DecisionResult,
    EventLog,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    JsonValue,
    MarkerAnchorKind,
    MissionActionState,
    MissionActionStatus,
    MissionSetup,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerRole,
    Pose,
    PrimaryBattlefieldDepartureState,
    PrimaryComponentTurnStartMembership,
    PrimaryMissionMarkerState,
    PrimaryMissionProgressState,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
    PrimaryScoringConditionContext,
    PrimaryScoringRulesUnitPositionWitness,
    RuntimeModifierRegistry,
    StartingAttachedUnitRecord,
    StartingStrengthRecord,
    VictoryPointSourceKind,
    _assert_surveil_boundary_path,
    _attach_first_two_enemy_units,
    _attached_component_loss_departure,
    _bind_force_dispositions,
    _central_objective_id,
    _complete_surveil_against_target,
    _completed_surveil_action,
    _depart_rules_unit,
    _destroy_component_for_scoring,
    _non_home_objective_ids,
    _objective_context,
    _operation_marker_progress,
    _place_enemy_components_at,
    _place_enemy_components_on_marker,
    _place_friendly_within_surveil_range,
    _position_witness,
    _primary_awards_by_condition,
    _reevaluate_surveil_from_state_evidence,
    _resolved_lineage,
    _resolved_surveil_action,
    _resolved_surveil_attached_component_loss,
    _started_surveil_action,
    _started_surveil_attached_component_loss,
    _started_surveil_lifecycle_state,
    _surveil_setup,
    battle_state,
    build_primary_rules_unit_turn_start_snapshot,
    deepcopy,
    default_unit_selection,
    destroy_model_by_rule,
    evaluate_primary_scoring_condition,
    evaluate_surveil_scoring_condition,
    mission_action_policy_for_id,
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    phase17n_state_with_setup,
    primary_battlefield_departure_id,
    primary_mission_marker_id,
    primary_scoring_rules_from_definition,
    pytest,
    record_primary_battlefield_departure,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    replace,
    request_mission_action_start,
    rules_unit_view_by_id,
    score_primary_objective_control_boundary,
    surveil_enemy_unit_source_identity,
    warhammer_event_companion_2026_07_mission_pack,
    with_model_offsets,
)


def test_phase17n_step5f_surveil_conditions_are_registered() -> None:
    assert PRIMARY_SCORING_SURVEIL_CONDITIONS <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    assert ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION in SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS


def test_phase17n_step5f_promotes_surveil_the_foe() -> None:
    package = warhammer_event_companion_2026_07_mission_pack()
    primary_by_id = {primary.primary_mission_id: primary for primary in package.primary_missions}
    rules = primary_scoring_rules_from_definition(primary_by_id["primary-surveil-the-foe"])
    assert {rule.condition for rule in rules} <= SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS
    assert ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION in {rule.condition for rule in rules}
    assert NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD in {rule.condition for rule in rules}


def test_phase17n_step5f_surveil_conditions_require_state_evidence() -> None:
    setup = _surveil_setup()
    context = _objective_context(setup=setup, battle_round=1)
    with pytest.raises(GameLifecycleError, match="requires state evidence"):
        evaluate_primary_scoring_condition(
            condition=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
            context=context,
        )


def test_phase17n_step5f_surveilled_units_require_position_witnesses() -> None:
    setup = _surveil_setup()
    with pytest.raises(GameLifecycleError, match="requires position witnesses"):
        evaluate_surveil_scoring_condition(
            condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
            actions=(_completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE),),
            progress=PrimaryMissionProgressState.empty(),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
        )


def test_phase17n_step5f_no_surveilled_units_score_zero_without_witnesses() -> None:
    setup = _surveil_setup()
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(),
        progress=PrimaryMissionProgressState.empty(),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
    )
    assert evidence["score_count"] == 0
    assert evidence["surveilled_unit_instance_ids"] == []
    assert evidence["excepted_unit_instance_ids"] == []


def test_phase17n_step5f_partial_exception_still_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(
            _completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE, action_index=1),
            _completed_surveil_action(setup, target_id=_ENEMY_UNIT_TWO, action_index=2),
        ),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ENEMY_UNIT_ONE,
                objective_ids=(objective_id,),
            ),
            _position_witness(unit_instance_id=_ENEMY_UNIT_TWO),
        ),
    )
    assert evidence["score_count"] == 1
    assert evidence["surveilled_unit_instance_ids"] == [_ENEMY_UNIT_ONE, _ENEMY_UNIT_TWO]
    assert evidence["excepted_unit_instance_ids"] == [_ENEMY_UNIT_ONE]


def test_phase17n_step5f_same_turn_marker_removal_allows_scoring() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    active = _operation_marker_progress(setup, objective_ids=(objective_id,))
    removed = active.replace_marker(
        active.markers[0].removed(
            battle_round=1,
            phase=BattlePhase.FIGHT.value,
            active_player_id="player-a",
            source_id=surveil_enemy_unit_source_identity()[0],
            event_id="step5f-surveil-marker-tombstone",
        )
    )
    actions = (_completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE),)
    witnesses = (
        _position_witness(
            unit_instance_id=_ENEMY_UNIT_ONE,
            objective_ids=(objective_id,),
        ),
    )
    blocked = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=actions,
        progress=active,
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=witnesses,
    )
    allowed = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=actions,
        progress=removed,
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=witnesses,
    )
    assert blocked["score_count"] == 0
    assert allowed["score_count"] == 1
    assert allowed["operation_marker_ids"] == []


def test_phase17n_step5f_rejects_conflicting_descendant_component_mapping() -> None:
    setup = _surveil_setup()
    with pytest.raises(GameLifecycleError, match="component identity drifted"):
        evaluate_surveil_scoring_condition(
            condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
            actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
            progress=PrimaryMissionProgressState.empty(),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
            departures=(_attached_component_loss_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
            position_witnesses=(
                _position_witness(
                    unit_instance_id=_ATTACHED_LEADER,
                    component_ids=(_ATTACHED_LEADER, _ENEMY_UNIT_TWO),
                ),
            ),
        )


def test_phase17n_step5f_source_identity_drift_is_fail_closed() -> None:
    setup = _surveil_setup()
    drifted = replace(
        _completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE),
        scoring_source_id="primary-smoke-and-mirrors",
    )
    with pytest.raises(GameLifecycleError, match="source identity drifted"):
        evaluate_surveil_scoring_condition(
            condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
            actions=(drifted,),
            progress=PrimaryMissionProgressState.empty(),
            mission_setup=setup,
            player_id="player-a",
            battle_round=1,
        )


def test_phase17n_step5f_scores_surveil_through_shared_boundary() -> None:
    state, record = _resolved_surveil_action()
    _assert_surveil_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        expected_vp=4,
    )


def test_phase17n_step5f_no_enemy_operation_markers_still_score_from_battle_round_two() -> None:
    setup = _surveil_setup()
    state = phase17n_state_with_setup(
        setup=setup,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT,
        battle_round=2,
    )
    _bind_force_dispositions(state)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    _assert_surveil_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
        expected_vp=5,
    )
    awards = _primary_awards_by_condition(state, player_id="player-a")
    assert ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION not in awards


__all__: list[str] = []
__all__ += ["AttachedUnitFormation", "BattlefieldRemovalKind"]
__all__ += ["DECLINE_MISSION_ACTION_START_OPTION_ID", "DecisionController", "DecisionResult"]
__all__ += ["EventLog", "GameLifecycle", "GameLifecycleStage", "GameState", "JsonValue"]
__all__ += ["MarkerAnchorKind", "MissionActionState", "MissionActionStatus", "MissionSetup"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveMarkerDefinition"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "ObjectiveMarkerRole", "Pose"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryComponentTurnStartMembership"]
__all__ += ["PrimaryMissionMarkerState", "PrimaryObjectiveMarkerWitness"]
__all__ += ["PrimaryRulesUnitTurnStartMembership", "PrimaryScoringConditionContext"]
__all__ += ["SURVEIL_ENEMY_UNIT_ACTION_ID", "PrimaryScoringRulesUnitPositionWitness"]
__all__ += ["StartingAttachedUnitRecord", "StartingStrengthRecord", "VictoryPointSourceKind"]
__all__ += ["_ATTACHED_SECOND_LEADER", "_FRIENDLY_UNIT", "_attach_first_two_enemy_units"]
__all__ += ["_complete_surveil_against_target", "_depart_rules_unit"]
__all__ += ["_destroy_component_for_scoring", "_non_home_objective_ids"]
__all__ += ["_place_enemy_components_at", "_place_enemy_components_on_marker"]
__all__ += ["_place_friendly_within_surveil_range", "_reevaluate_surveil_from_state_evidence"]
__all__ += ["_resolved_lineage", "_resolved_surveil_attached_component_loss"]
__all__ += ["_started_surveil_action", "_started_surveil_attached_component_loss"]
__all__ += ["_started_surveil_lifecycle_state", "battle_state"]
__all__ += ["build_primary_rules_unit_turn_start_snapshot", "cast", "deepcopy"]
__all__ += ["default_unit_selection", "destroy_model_by_rule", "mission_action_policy_for_id"]
__all__ += ["phase17n_event_setup", "phase17n_started_primary_action_fixture"]
__all__ += ["primary_battlefield_departure_id", "primary_mission_marker_id"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "request_mission_action_start"]
__all__ += ["rules_unit_view_by_id", "score_primary_objective_control_boundary"]
__all__ += ["with_model_offsets"]
