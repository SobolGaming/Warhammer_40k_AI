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


def test_phase17n_step5f_surveilled_unit_not_near_marked_objective_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=(_position_witness(unit_instance_id=_ENEMY_UNIT_ONE),),
    )
    assert evidence["score_count"] == 1
    assert evidence["surveilled_unit_instance_ids"] == [_ENEMY_UNIT_ONE]
    assert evidence["excepted_unit_instance_ids"] == []
    assert evidence["operation_objective_ids"] == [objective_id]


def test_phase17n_step5f_surveilled_unit_near_marked_objective_is_excepted() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ENEMY_UNIT_ONE,
                objective_ids=(objective_id,),
            ),
        ),
    )
    assert evidence["score_count"] == 0
    assert evidence["excepted_unit_instance_ids"] == [_ENEMY_UNIT_ONE]


def test_phase17n_step5f_all_surveilled_units_near_marked_objectives_are_excepted() -> None:
    setup = _surveil_setup()
    first_id, second_id = _non_home_objective_ids(setup)[:2]
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(
            _completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE, action_index=1),
            _completed_surveil_action(setup, target_id=_ENEMY_UNIT_TWO, action_index=2),
        ),
        progress=_operation_marker_progress(setup, objective_ids=(first_id, second_id)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ENEMY_UNIT_ONE,
                objective_ids=(first_id,),
            ),
            _position_witness(
                unit_instance_id=_ENEMY_UNIT_TWO,
                objective_ids=(second_id,),
            ),
        ),
    )
    assert evidence["score_count"] == 0
    assert evidence["excepted_unit_instance_ids"] == [_ENEMY_UNIT_ONE, _ENEMY_UNIT_TWO]


def test_phase17n_step5f_missing_witness_is_not_in_marked_objective_range() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ENEMY_UNIT_ONE),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        position_witnesses=(),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert evidence["resolved_lineages"] == [
        {
            "historical_unit_instance_id": _ENEMY_UNIT_ONE,
            "frozen_component_unit_instance_ids": [],
            "current_witness_unit_instance_ids": [],
        }
    ]


def test_phase17n_step5f_attached_component_loss_survivor_in_marked_range_is_excepted() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_component_loss_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ATTACHED_LEADER,
                objective_ids=(objective_id,),
            ),
        ),
    )
    assert evidence["score_count"] == 0
    assert evidence["surveilled_unit_instance_ids"] == [_ATTACHED_UNIT]
    assert evidence["excepted_unit_instance_ids"] == [_ATTACHED_UNIT]
    assert evidence["resolved_lineages"] == [
        {
            "historical_unit_instance_id": _ATTACHED_UNIT,
            "frozen_component_unit_instance_ids": sorted([_ATTACHED_BODYGUARD, _ATTACHED_LEADER]),
            "current_witness_unit_instance_ids": [_ATTACHED_LEADER],
        }
    ]


def test_phase17n_step5f_attached_component_loss_leader_destroyed_bodyguard_survives_in_range() -> (
    None
):
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_component_loss_departure(departed_ids=(_ATTACHED_LEADER,)),),
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ATTACHED_BODYGUARD,
                objective_ids=(objective_id,),
            ),
        ),
    )
    assert evidence["score_count"] == 0
    assert evidence["excepted_unit_instance_ids"] == [_ATTACHED_UNIT]
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [_ATTACHED_BODYGUARD]


def test_phase17n_step5f_attached_component_loss_survivor_outside_marked_range_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_component_loss_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
        position_witnesses=(_position_witness(unit_instance_id=_ATTACHED_LEADER),),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [_ATTACHED_LEADER]


def test_phase17n_step5f_attached_component_loss_without_operation_marker_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
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
                objective_ids=(objective_id,),
            ),
        ),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [_ATTACHED_LEADER]


def test_phase17n_step5f_attached_component_loss_without_placed_survivor_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_component_loss_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
        position_witnesses=(),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert evidence["resolved_lineages"] == [
        {
            "historical_unit_instance_id": _ATTACHED_UNIT,
            "frozen_component_unit_instance_ids": sorted([_ATTACHED_BODYGUARD, _ATTACHED_LEADER]),
            "current_witness_unit_instance_ids": [],
        }
    ]


def test_phase17n_step5f_attached_component_loss_all_survivors_in_marked_range_are_excepted() -> (
    None
):
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(
            _attached_component_loss_departure(
                component_ids=(_ATTACHED_BODYGUARD, _ATTACHED_LEADER, _ATTACHED_SECOND_LEADER),
                departed_ids=(_ATTACHED_BODYGUARD,),
            ),
        ),
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ATTACHED_LEADER,
                objective_ids=(objective_id,),
            ),
            _position_witness(
                unit_instance_id=_ATTACHED_SECOND_LEADER,
                objective_ids=(objective_id,),
            ),
        ),
    )
    assert evidence["score_count"] == 0
    assert evidence["excepted_unit_instance_ids"] == [_ATTACHED_UNIT]
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [
        _ATTACHED_LEADER,
        _ATTACHED_SECOND_LEADER,
    ]


def test_phase17n_step5f_attached_component_loss_partial_survivor_range_still_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(
            _attached_component_loss_departure(
                component_ids=(_ATTACHED_BODYGUARD, _ATTACHED_LEADER, _ATTACHED_SECOND_LEADER),
                departed_ids=(_ATTACHED_BODYGUARD,),
            ),
        ),
        position_witnesses=(
            _position_witness(
                unit_instance_id=_ATTACHED_LEADER,
                objective_ids=(objective_id,),
            ),
            _position_witness(unit_instance_id=_ATTACHED_SECOND_LEADER),
        ),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [
        _ATTACHED_LEADER,
        _ATTACHED_SECOND_LEADER,
    ]


def test_phase17n_step5f_ignores_wrong_action_player_round_and_status() -> None:
    setup = _surveil_setup()
    started = _started_surveil_action(setup, target_id=_ENEMY_UNIT_ONE, action_index=1)
    other_player = _completed_surveil_action(
        setup,
        target_id=_ENEMY_UNIT_ONE,
        action_index=2,
        player_id="player-b",
    )
    other_round = _completed_surveil_action(
        setup,
        target_id=_ENEMY_UNIT_ONE,
        action_index=3,
        battle_round=2,
    )
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(started, other_player, other_round),
        progress=PrimaryMissionProgressState.empty(),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
    )
    assert evidence["score_count"] == 0


@pytest.mark.parametrize("destroyed_component", ["bodyguard", "leader"])
def test_phase17n_step5f_attached_component_loss_survivor_on_objective_uses_lineage(
    destroyed_component: str,
) -> None:
    state, record, attached_id, _survivor_id, objective_id = (
        _resolved_surveil_attached_component_loss(
            destroyed_component=destroyed_component,
            place_on_objective=True,
        )
    )
    _assert_surveil_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        expected_vp=4,
    )
    evidence = _reevaluate_surveil_from_state_evidence(state, progress=None)
    assert evidence["score_count"] == 1
    assert evidence["surveilled_unit_instance_ids"] == [attached_id]
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["historical_unit_instance_id"] == attached_id
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [attached_id]
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5F attached fixture requires MissionSetup.")
    excepted = _reevaluate_surveil_from_state_evidence(
        state,
        progress=_operation_marker_progress(
            setup,
            objective_ids=(objective_id,),
            game_id=state.game_id,
        ),
    )
    assert excepted["score_count"] == 0
    assert excepted["excepted_unit_instance_ids"] == [attached_id]
    assert _resolved_lineage(excepted)["current_witness_unit_instance_ids"] == [attached_id]


@pytest.mark.parametrize("destroyed_component", ["bodyguard", "leader"])
def test_phase17n_step5f_attached_component_loss_survivor_off_objective_still_scores(
    destroyed_component: str,
) -> None:
    state, record, attached_id, _survivor_id, _objective_id = (
        _resolved_surveil_attached_component_loss(
            destroyed_component=destroyed_component,
            place_on_objective=False,
        )
    )
    _assert_surveil_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        expected_vp=4,
    )
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5F attached fixture requires MissionSetup.")
    evidence = _reevaluate_surveil_from_state_evidence(
        state,
        progress=_operation_marker_progress(
            setup,
            objective_ids=(_central_objective_id(setup),),
            game_id=state.game_id,
        ),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["historical_unit_instance_id"] == attached_id
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [attached_id]


def test_phase17n_step5f_attached_component_loss_without_survivor_scores_through_boundary() -> None:
    state, record, attached_id, _survivor_id, _objective_id = (
        _resolved_surveil_attached_component_loss(
            destroyed_component="bodyguard",
            place_on_objective=True,
            depart_survivor=True,
        )
    )
    _assert_surveil_boundary_path(
        state=state,
        record=record,
        player_id="player-a",
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        expected_vp=4,
    )
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5F attached fixture requires MissionSetup.")
    evidence = _reevaluate_surveil_from_state_evidence(
        state,
        progress=_operation_marker_progress(
            setup,
            objective_ids=(_central_objective_id(setup),),
            game_id=state.game_id,
        ),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["historical_unit_instance_id"] == attached_id
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [attached_id]


__all__: list[str] = []
__all__ += ["AttachedUnitFormation", "BattlePhase", "BattlefieldRemovalKind"]
__all__ += ["DECLINE_MISSION_ACTION_START_OPTION_ID", "DecisionController", "DecisionResult"]
__all__ += ["EventLog", "GameLifecycle", "GameLifecycleError", "GameLifecycleStage", "GameState"]
__all__ += ["JsonValue", "MarkerAnchorKind", "MissionActionState", "MissionActionStatus"]
__all__ += ["NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD", "MissionSetup", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlResult", "ObjectiveControlTiming", "ObjectiveMarkerDefinition"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_SURVEIL_CONDITIONS", "Pose", "PrimaryBattlefieldDepartureState"]
__all__ += ["PrimaryComponentTurnStartMembership", "PrimaryMissionMarkerState"]
__all__ += ["PrimaryObjectiveMarkerWitness", "PrimaryRulesUnitTurnStartMembership"]
__all__ += ["PrimaryScoringConditionContext", "PrimaryScoringRulesUnitPositionWitness"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS", "RuntimeModifierRegistry"]
__all__ += ["SURVEIL_ENEMY_UNIT_ACTION_ID", "StartingAttachedUnitRecord"]
__all__ += ["_FRIENDLY_UNIT", "StartingStrengthRecord", "VictoryPointSourceKind"]
__all__ += ["_attach_first_two_enemy_units", "_bind_force_dispositions"]
__all__ += ["_complete_surveil_against_target", "_depart_rules_unit"]
__all__ += ["_destroy_component_for_scoring", "_objective_context", "_place_enemy_components_at"]
__all__ += ["_place_enemy_components_on_marker", "_place_friendly_within_surveil_range"]
__all__ += ["_primary_awards_by_condition", "_resolved_surveil_action"]
__all__ += ["_started_surveil_attached_component_loss", "_started_surveil_lifecycle_state"]
__all__ += ["battle_state", "build_primary_rules_unit_turn_start_snapshot", "cast", "deepcopy"]
__all__ += ["default_unit_selection", "destroy_model_by_rule"]
__all__ += ["evaluate_primary_scoring_condition", "mission_action_policy_for_id"]
__all__ += ["phase17n_event_setup", "phase17n_started_primary_action_fixture"]
__all__ += ["phase17n_state_with_setup", "primary_battlefield_departure_id"]
__all__ += ["primary_mission_marker_id", "primary_scoring_rules_from_definition"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "replace"]
__all__ += ["request_mission_action_start", "rules_unit_view_by_id"]
__all__ += ["score_primary_objective_control_boundary", "surveil_enemy_unit_source_identity"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack", "with_model_offsets"]
