from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest
from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    phase17n_state_with_setup,
)

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
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
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

_ENEMY_UNIT_ONE = "army-bravo:intercessor-unit-1"
_ENEMY_UNIT_TWO = "army-bravo:intercessor-unit-2"
_FRIENDLY_UNIT = "army-alpha:intercessor-unit-1"


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


def _position_witness(
    *,
    unit_instance_id: str,
    objective_ids: tuple[str, ...] = (),
    owner_player_id: str = "player-b",
) -> PrimaryScoringRulesUnitPositionWitness:
    model_id = f"{unit_instance_id}:model-1"
    return PrimaryScoringRulesUnitPositionWitness(
        owner_player_id=owner_player_id,
        rules_unit_membership=PrimaryRulesUnitTurnStartMembership(
            rules_unit_instance_id=unit_instance_id,
            component_memberships=(
                PrimaryComponentTurnStartMembership(
                    unit_instance_id=unit_instance_id,
                    evaluated_model_instance_ids=(model_id,),
                    logical_terrain_area_ids=(),
                    objective_marker_witnesses=tuple(
                        PrimaryObjectiveMarkerWitness(
                            objective_marker_id=objective_id,
                            model_instance_ids=(model_id,),
                        )
                        for objective_id in objective_ids
                    ),
                ),
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
