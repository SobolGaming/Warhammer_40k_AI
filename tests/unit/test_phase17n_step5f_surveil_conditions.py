from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import (
    battle_state,
    default_unit_selection,
    with_model_offsets,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    phase17n_state_with_setup,
)

from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    request_mission_action_start,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_primary_battlefield_departure_event,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryMissionMarkerState,
    PrimaryMissionProgressState,
    primary_mission_marker_id,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS,
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_operation_marker_conditions import (
    NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitness,
)
from warhammer40k_core.engine.primary_scoring_surveil_conditions import (
    ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
    PRIMARY_SCORING_SURVEIL_CONDITIONS,
    SURVEIL_ENEMY_UNIT_ACTION_ID,
    evaluate_surveil_scoring_condition,
    surveil_enemy_unit_source_identity,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryComponentTurnStartMembership,
    PrimaryObjectiveMarkerWitness,
    PrimaryRulesUnitTurnStartMembership,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

_ENEMY_UNIT_ONE = "army-bravo:intercessor-unit-1"
_ENEMY_UNIT_TWO = "army-bravo:intercessor-unit-2"
_FRIENDLY_UNIT = "army-alpha:intercessor-unit-1"
_ATTACHED_UNIT = "attached-unit:army-bravo:surveil-formation"
_ATTACHED_LEADER = "army-bravo:captain-1"
_ATTACHED_SECOND_LEADER = "army-bravo:lieutenant-1"
_ATTACHED_BODYGUARD = "army-bravo:intercessor-bodyguard"


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


def test_phase17n_step5f_attached_split_survivor_in_marked_range_is_excepted() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_split_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
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


def test_phase17n_step5f_attached_split_leader_destroyed_bodyguard_survives_in_range() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_split_departure(departed_ids=(_ATTACHED_LEADER,)),),
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


def test_phase17n_step5f_attached_split_survivor_outside_marked_range_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_split_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
        position_witnesses=(_position_witness(unit_instance_id=_ATTACHED_LEADER),),
    )
    assert evidence["score_count"] == 1
    assert evidence["excepted_unit_instance_ids"] == []
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [_ATTACHED_LEADER]


def test_phase17n_step5f_attached_split_without_operation_marker_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=PrimaryMissionProgressState.empty(),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_split_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
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


def test_phase17n_step5f_attached_split_without_placed_survivor_scores() -> None:
    setup = _surveil_setup()
    objective_id = _central_objective_id(setup)
    evidence = evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=(_completed_surveil_action(setup, target_id=_ATTACHED_UNIT),),
        progress=_operation_marker_progress(setup, objective_ids=(objective_id,)),
        mission_setup=setup,
        player_id="player-a",
        battle_round=1,
        departures=(_attached_split_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
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


def test_phase17n_step5f_attached_split_all_survivors_in_marked_range_are_excepted() -> None:
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
            _attached_split_departure(
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


def test_phase17n_step5f_attached_split_partial_survivor_range_still_scores() -> None:
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
            _attached_split_departure(
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
            departures=(_attached_split_departure(departed_ids=(_ATTACHED_BODYGUARD,)),),
            position_witnesses=(
                _position_witness(
                    unit_instance_id=_ATTACHED_LEADER,
                    component_ids=(_ATTACHED_LEADER, _ENEMY_UNIT_TWO),
                ),
            ),
        )


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


@pytest.mark.parametrize("destroyed_component", ["bodyguard", "leader"])
def test_phase17n_step5f_attached_split_survivor_on_objective_uses_lineage(
    destroyed_component: str,
) -> None:
    state, record, attached_id, survivor_id, objective_id = _resolved_surveil_attached_split(
        destroyed_component=destroyed_component,
        place_on_objective=True,
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
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [survivor_id]
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
    assert _resolved_lineage(excepted)["current_witness_unit_instance_ids"] == [survivor_id]


@pytest.mark.parametrize("destroyed_component", ["bodyguard", "leader"])
def test_phase17n_step5f_attached_split_survivor_off_objective_still_scores(
    destroyed_component: str,
) -> None:
    state, record, attached_id, survivor_id, _objective_id = _resolved_surveil_attached_split(
        destroyed_component=destroyed_component,
        place_on_objective=False,
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
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == [survivor_id]


def test_phase17n_step5f_attached_split_without_survivor_scores_through_boundary() -> None:
    state, record, attached_id, _survivor_id, _objective_id = _resolved_surveil_attached_split(
        destroyed_component="bodyguard",
        place_on_objective=True,
        depart_survivor=True,
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
    assert _resolved_lineage(evidence)["current_witness_unit_instance_ids"] == []


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


def _surveil_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="disruption",
    )


def _resolved_surveil_action() -> tuple[GameState, ObjectiveControlRecord]:
    state, _action, _target_id = _started_surveil_lifecycle_state()
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    return state, record


def _started_surveil_lifecycle_state() -> tuple[GameState, MissionActionState, str]:
    state, _decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="disruption-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="disruption",
        player_id="player-a",
        mission_action_id=SURVEIL_ENEMY_UNIT_ACTION_ID,
        current_phase=BattlePhase.FIGHT,
    )
    _bind_force_dispositions(state)
    if action.status is not MissionActionStatus.COMPLETED:
        raise AssertionError("Step 5F Surveil Action must complete immediately.")
    if action.target_id != target_id:
        raise AssertionError("Step 5F Surveil Action target drifted.")
    return state, action, target_id


def _resolved_surveil_attached_split(
    *,
    destroyed_component: str,
    place_on_objective: bool,
    depart_survivor: bool = False,
) -> tuple[GameState, ObjectiveControlRecord, str, str, str]:
    state, _decisions, attached_id, survivor_id, objective_id = _started_surveil_attached_split(
        destroyed_component=destroyed_component,
        place_on_objective=place_on_objective,
        depart_survivor=depart_survivor,
    )
    _bind_force_dispositions(state)
    record = state.record_objective_control_boundary(
        completed_phase=BattlePhase.FIGHT,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    return state, record, attached_id, survivor_id, objective_id


def _started_surveil_attached_split(
    *,
    destroyed_component: str,
    place_on_objective: bool,
    depart_survivor: bool,
) -> tuple[GameState, DecisionController, str, str, str]:
    setup = _surveil_setup()
    state = battle_state(
        player_b_units=(
            default_unit_selection("intercessor-unit-3"),
            default_unit_selection("intercessor-unit-4"),
        )
    )
    state.mission_setup = setup
    if state.battlefield_state is None:
        raise AssertionError("Step 5F attached fixture requires battlefield state.")
    state.battlefield_state = replace(
        state.battlefield_state,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.active_player_id = "player-a"
    state.battle_round = 1
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    attached_id, bodyguard_id, leader_id = _attach_first_two_enemy_units(state)
    if destroyed_component == "bodyguard":
        destroyed_id = bodyguard_id
        survivor_id = leader_id
    elif destroyed_component == "leader":
        destroyed_id = leader_id
        survivor_id = bodyguard_id
    else:
        raise AssertionError(f"unsupported destroyed component: {destroyed_component}")
    objective = next(
        marker
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    if place_on_objective:
        _place_enemy_components_on_marker(
            state,
            component_ids=(bodyguard_id, leader_id),
            marker=objective,
        )
    else:
        _place_enemy_components_at(
            state,
            component_ids=(bodyguard_id, leader_id),
            x_inches=6.0,
            y_inches=6.0,
        )
    _place_friendly_within_surveil_range(state, target_unit_id=bodyguard_id)
    decisions, action = _complete_surveil_against_target(state, target_id=attached_id)
    if action.status is not MissionActionStatus.COMPLETED:
        raise AssertionError("Step 5F attached Surveil Action must complete immediately.")
    if action.target_id != attached_id:
        raise AssertionError("Step 5F attached Surveil Action target drifted.")
    _destroy_component_for_scoring(
        state=state,
        decisions=decisions,
        component_id=destroyed_id,
        attached_id=attached_id,
    )
    state.recover_starting_strength_after_attached_unit_split(
        player_id="player-b",
        attached_unit_instance_id=attached_id,
        surviving_unit_instance_ids=(survivor_id,),
        event_log=decisions.event_log,
    )
    if depart_survivor:
        _depart_rules_unit(
            state=state,
            decisions=decisions,
            rules_unit_instance_id=survivor_id,
        )
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    return state, decisions, attached_id, survivor_id, objective.objective_marker_id


def _complete_surveil_against_target(
    state: GameState,
    *,
    target_id: str,
) -> tuple[DecisionController, MissionActionState]:
    friendly = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    decisions = DecisionController()
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id="player-a",
        mission_action_id=SURVEIL_ENEMY_UNIT_ACTION_ID,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    if status.decision_request is None:
        raise AssertionError("Step 5F attached fixture requires a Surveil DecisionRequest.")
    request = status.decision_request
    selected_option = next(
        option
        for option in request.options
        if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
        and cast(dict[str, JsonValue], option.payload)["unit_instance_id"]
        == friendly.unit_instance_id
        and cast(dict[str, JsonValue], option.payload)["target_id"] == target_id
    )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(
        DecisionResult.for_request(
            result_id="phase17n-action-result:surveil-enemy-unit:player-a:attached",
            request=request,
            selected_option_id=selected_option.option_id,
        )
    )
    return decisions, state.mission_action_states[-1]


def _attach_first_two_enemy_units(state: GameState) -> tuple[str, str, str]:
    enemy_army = next(army for army in state.army_definitions if army.player_id == "player-b")
    if len(enemy_army.units) < 2:
        raise AssertionError("Step 5F attached fixture requires two enemy units.")
    bodyguard = enemy_army.units[0]
    leader = enemy_army.units[1]
    component_ids = tuple(sorted((bodyguard.unit_instance_id, leader.unit_instance_id)))
    attached_id = f"attached-unit:{enemy_army.army_id}:phase17n-step5f-surveil"
    formation = AttachedUnitFormation(
        attached_unit_instance_id=attached_id,
        bodyguard_unit_instance_id=bodyguard.unit_instance_id,
        leader_unit_instance_ids=(leader.unit_instance_id,),
        component_unit_instance_ids=component_ids,
        source_id="phase17n-step5f-attached-source",
        attachment_source_ids=("phase17n-step5f-attachment-rule",),
    )
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
    return attached_id, bodyguard.unit_instance_id, leader.unit_instance_id


def _place_enemy_components_on_marker(
    state: GameState,
    *,
    component_ids: tuple[str, ...],
    marker: ObjectiveMarkerDefinition,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 5F attached fixture requires battlefield state.")
    for index, component_id in enumerate(component_ids):
        x_shift = float(index) * 2.0
        placement = state.battlefield_state.unit_placement_by_id(component_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            with_model_offsets(
                placement,
                marker,
                offsets=(
                    (x_shift, 0.0),
                    (x_shift + 1.0, 0.0),
                    (x_shift + 2.0, 0.0),
                    (x_shift, 1.0),
                    (x_shift + 1.0, 1.0),
                ),
            )
        )


def _place_enemy_components_at(
    state: GameState,
    *,
    component_ids: tuple[str, ...],
    x_inches: float,
    y_inches: float,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 5F attached fixture requires battlefield state.")
    for component_id in component_ids:
        placement = state.battlefield_state.unit_placement_by_id(component_id)
        state.battlefield_state = state.battlefield_state.with_unit_placement(
            replace(
                placement,
                model_placements=tuple(
                    replace(
                        model_placement,
                        pose=Pose.at(
                            x_inches + (index * 0.1),
                            y_inches,
                            model_placement.pose.position.z,
                            facing_degrees=model_placement.pose.facing.degrees,
                        ),
                    )
                    for index, model_placement in enumerate(placement.model_placements)
                ),
            )
        )


def _place_friendly_within_surveil_range(state: GameState, *, target_unit_id: str) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 5F attached fixture requires battlefield state.")
    friendly = next(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    target_pose = (
        state.battlefield_state.unit_placement_by_id(target_unit_id).model_placements[0].pose
    )
    placement = state.battlefield_state.unit_placement_by_id(friendly.unit_instance_id)
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


def _destroy_component_for_scoring(
    *,
    state: GameState,
    decisions: DecisionController,
    component_id: str,
    attached_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 5F attached fixture requires battlefield state.")
    placement = state.battlefield_state.unit_placement_by_id(component_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(removed_model_ids)
    departures = record_primary_destroyed_model_departures(
        state=state,
        destroyed_model_instance_ids=removed_model_ids,
        source_id=f"step5f-attached-destroy:{component_id}",
        occurrence_id=f"step5f-attached-destroy:{component_id}",
    )
    if not departures:
        raise AssertionError("Step 5F attached fixture requires destroyed-component departure.")
    for departure in departures:
        if departure.rules_unit_instance_id != attached_id:
            raise AssertionError(
                "Step 5F attached destruction must keep the Attached Unit identity."
            )
        if component_id not in departure.departed_component_unit_instance_ids:
            raise AssertionError(
                "Step 5F attached destruction must depart the destroyed component."
            )
        record_primary_battlefield_departure_event(
            event_log=decisions.event_log,
            departure=departure,
        )


def _depart_rules_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    rules_unit_instance_id: str,
) -> None:
    if state.battlefield_state is None:
        raise AssertionError("Step 5F attached fixture requires battlefield state.")
    placement = state.battlefield_state.unit_placement_by_id(rules_unit_instance_id)
    removed_model_ids = tuple(
        model_placement.model_instance_id for model_placement in placement.model_placements
    )
    state.battlefield_state = state.battlefield_state.with_removed_models(removed_model_ids)
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=rules_unit_instance_id,
        affected_component_unit_instance_ids=(rules_unit_instance_id,),
        departed_component_unit_instance_ids=(rules_unit_instance_id,),
        removed_model_instance_ids=removed_model_ids,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=f"step5f-attached-survivor-destroyed:{rules_unit_instance_id}",
        source_id=f"step5f-attached-survivor-destroyed:{rules_unit_instance_id}",
    )
    if departure is None:
        raise AssertionError("Step 5F attached fixture requires survivor departure.")
    record_primary_battlefield_departure_event(
        event_log=decisions.event_log,
        departure=departure,
    )


def _resolved_lineage(evidence: dict[str, JsonValue]) -> dict[str, JsonValue]:
    rows = evidence["resolved_lineages"]
    if type(rows) is not list or not rows:
        raise AssertionError("Step 5F evidence requires resolved_lineages.")
    row = rows[0]
    if type(row) is not dict:
        raise AssertionError("Step 5F resolved lineage must be an object.")
    return row


def _reevaluate_surveil_from_state_evidence(
    state: GameState,
    *,
    progress: PrimaryMissionProgressState | None,
) -> dict[str, JsonValue]:
    if not state.primary_scoring_state_evidence_records:
        raise AssertionError("Step 5F attached fixture requires scoring state evidence.")
    evidence = state.primary_scoring_state_evidence_records[-1]
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5F attached fixture requires MissionSetup.")
    return evaluate_surveil_scoring_condition(
        condition_id=ENEMY_UNIT_SURVEILLED_MARKER_EXCEPTION,
        actions=evidence.primary_mission_action_states,
        progress=evidence.primary_mission_progress_state if progress is None else progress,
        mission_setup=setup,
        player_id="player-a",
        battle_round=evidence.battle_round,
        departures=evidence.primary_battlefield_departure_states,
        position_witnesses=evidence.current_rules_unit_position_witnesses,
    )


def _assert_surveil_boundary_path(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    player_id: str,
    condition_id: str,
    expected_vp: int,
) -> None:
    event_log = EventLog()
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=event_log,
    )
    awards = _primary_awards_by_condition(state, player_id=player_id)
    assert awards[condition_id] == expected_vp
    matching_rows = tuple(
        transaction
        for ledger in state.victory_point_ledgers
        for transaction in ledger.transactions
        if (
            type(transaction.metadata) is dict
            and transaction.metadata.get("scoring_rule_condition") == condition_id
        )
    )
    assert matching_rows
    assert all(row.player_id == player_id for row in matching_rows)
    assert all(
        type(row.metadata) is dict
        and type(row.metadata.get("primary_scoring_state_evidence_id")) is str
        and type(row.metadata.get("primary_scoring_state_evidence_hash")) is str
        for row in matching_rows
    )
    ledgers_payload = [ledger.to_payload() for ledger in state.victory_point_ledgers]
    evidence_payload = [
        evidence.to_payload() for evidence in state.primary_scoring_state_evidence_records
    ]
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=False,
        event_log=event_log,
    )
    assert [ledger.to_payload() for ledger in state.victory_point_ledgers] == ledgers_payload
    assert [
        evidence.to_payload() for evidence in state.primary_scoring_state_evidence_records
    ] == evidence_payload
    restored = GameState.from_payload(deepcopy(state.to_payload()))
    assert restored.to_payload() == state.to_payload()
    replayed_log = EventLog.from_payload(event_log.to_payload())
    assert replayed_log.to_payload() == event_log.to_payload()
    assert any(
        event.event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
        for event in replayed_log.records
    )


def _bind_force_dispositions(state: GameState) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5F fixture requires MissionSetup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]


def _primary_awards_by_condition(state: GameState, *, player_id: str) -> dict[str, int]:
    awards: dict[str, int] = {}
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if (
                transaction.player_id != player_id
                or transaction.source_kind is not VictoryPointSourceKind.PRIMARY
                or type(transaction.metadata) is not dict
            ):
                continue
            condition = transaction.metadata.get("scoring_rule_condition")
            if type(condition) is not str:
                continue
            awards[condition] = transaction.amount
    return awards


def _completed_surveil_action(
    setup: MissionSetup,
    *,
    target_id: str,
    action_index: int = 1,
    battle_round: int = 1,
    player_id: str = "player-a",
) -> MissionActionState:
    started = _started_surveil_action(
        setup,
        target_id=target_id,
        action_index=action_index,
        battle_round=battle_round,
        player_id=player_id,
    )
    return started.complete_without_award(
        battle_round=battle_round,
        phase=BattlePhase.SHOOTING.value,
        completion_timing=started.completion_timing,
    )


def _started_surveil_action(
    setup: MissionSetup,
    *,
    target_id: str,
    action_index: int,
    battle_round: int = 1,
    player_id: str = "player-a",
) -> MissionActionState:
    policy = mission_action_policy_for_id(SURVEIL_ENEMY_UNIT_ACTION_ID)
    return MissionActionState.start(
        action_id=f"step5f-action-{action_index:02d}",
        mission_action_id=SURVEIL_ENEMY_UNIT_ACTION_ID,
        player_id=player_id,
        unit_instance_id=_FRIENDLY_UNIT,
        target_id=target_id,
        condition_target_id=None,
        mission_id=setup.primary_mission_id_for_player(player_id),
        battle_round=battle_round,
        phase=BattlePhase.SHOOTING.value,
        start_timing=policy.start_timing,
        completion_timing=policy.completion_timing,
        eligible_unit_instance_ids=(_FRIENDLY_UNIT,),
        interruption_conditions=(),
        scoring_source_id=policy.scoring_source_id,
        victory_points=0,
    )


def _operation_marker_progress(
    setup: MissionSetup,
    *,
    objective_ids: tuple[str, ...],
    game_id: str = "phase11c-game",
) -> PrimaryMissionProgressState:
    identity = surveil_enemy_unit_source_identity()
    progress = PrimaryMissionProgressState.empty()
    for index, objective_id in enumerate(objective_ids, start=1):
        source_event_id = f"step5f-marker-event-{index:02d}"
        marker_id = primary_mission_marker_id(
            game_id=game_id,
            owner_player_id="player-a",
            mission_id="primary-surveil-the-foe",
            source_rule_id=identity[0],
            source_descriptor_id=identity[1],
            marker_kind="operation",
            anchor_kind=MarkerAnchorKind.OBJECTIVE,
            objective_marker_id=objective_id,
            terrain_feature_id=None,
            created_battle_round=1,
            created_phase=BattlePhase.SHOOTING.value,
            created_active_player_id="player-a",
            source_event_id=source_event_id,
            source_result_id=None,
            source_action_id=None,
            source_destruction_id=None,
            source_designation_id=None,
        )
        progress = progress.add_marker(
            PrimaryMissionMarkerState(
                marker_id=marker_id,
                game_id=game_id,
                owner_player_id="player-a",
                mission_id="primary-surveil-the-foe",
                source_rule_id=identity[0],
                source_descriptor_id=identity[1],
                marker_kind="operation",
                anchor_kind=MarkerAnchorKind.OBJECTIVE,
                objective_marker_id=objective_id,
                terrain_feature_id=None,
                created_battle_round=1,
                created_phase=BattlePhase.SHOOTING.value,
                created_active_player_id="player-a",
                source_event_id=source_event_id,
                source_result_id=None,
                source_action_id=None,
                source_destruction_id=None,
                source_designation_id=None,
            )
        )
    return progress


def _attached_split_departure(
    *,
    departed_ids: tuple[str, ...],
    component_ids: tuple[str, ...] = (_ATTACHED_BODYGUARD, _ATTACHED_LEADER),
    occurrence_id: str = "step5f-attached-split",
) -> PrimaryBattlefieldDepartureState:
    components = tuple(sorted(component_ids))
    departed = tuple(sorted(departed_ids))
    affected = tuple(component_id for component_id in components if component_id in set(departed))
    removed_model_ids = tuple(f"{component_id}-model-{occurrence_id}" for component_id in affected)
    source_id = f"{occurrence_id}-source"
    departure_id = primary_battlefield_departure_id(
        game_id="step5f-game",
        rules_unit_instance_id=_ATTACHED_UNIT,
        affected_component_unit_instance_ids=affected,
        departed_component_unit_instance_ids=departed,
        removed_model_instance_ids=removed_model_ids,
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )
    return PrimaryBattlefieldDepartureState(
        departure_id=departure_id,
        game_id="step5f-game",
        owner_player_id="player-b",
        rules_unit_instance_id=_ATTACHED_UNIT,
        component_unit_instance_ids=components,
        affected_component_unit_instance_ids=affected,
        departed_component_unit_instance_ids=departed,
        removed_model_instance_ids=removed_model_ids,
        battle_round=1,
        active_player_id="player-a",
        phase=BattlePhase.FIGHT.value,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        occurrence_id=occurrence_id,
        source_id=source_id,
    )


def _position_witness(
    *,
    unit_instance_id: str,
    objective_ids: tuple[str, ...] = (),
    owner_player_id: str = "player-b",
    component_ids: tuple[str, ...] | None = None,
) -> PrimaryScoringRulesUnitPositionWitness:
    components = (unit_instance_id,) if component_ids is None else component_ids
    return PrimaryScoringRulesUnitPositionWitness(
        owner_player_id=owner_player_id,
        rules_unit_membership=PrimaryRulesUnitTurnStartMembership(
            rules_unit_instance_id=unit_instance_id,
            component_memberships=tuple(
                PrimaryComponentTurnStartMembership(
                    unit_instance_id=component_id,
                    evaluated_model_instance_ids=(f"{component_id}:model-1",),
                    logical_terrain_area_ids=(),
                    objective_marker_witnesses=tuple(
                        PrimaryObjectiveMarkerWitness(
                            objective_marker_id=objective_id,
                            model_instance_ids=(f"{component_id}:model-1",),
                        )
                        for objective_id in objective_ids
                    ),
                )
                for component_id in components
            ),
        ),
    )


def _objective_context(
    *,
    setup: MissionSetup,
    battle_round: int,
) -> PrimaryScoringConditionContext:
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=(),
        )
        for marker in setup.objective_markers
    )
    record = ObjectiveControlRecord(
        record_id=f"step5f-objective-record-round-{battle_round}",
        game_id="step5f-objective-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5f-objective-battlefield",
        results=results,
    )
    return PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
    )


def _central_objective_id(setup: MissionSetup) -> str:
    return next(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )


def _non_home_objective_ids(setup: MissionSetup) -> tuple[str, ...]:
    home_roles = {ObjectiveMarkerRole.ATTACKER_HOME, ObjectiveMarkerRole.DEFENDER_HOME}
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role not in home_roles
    )
