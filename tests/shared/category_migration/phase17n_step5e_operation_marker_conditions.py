from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest

from tests.phase17n_primary_mission_helpers import (
    phase17n_event_setup,
    phase17n_started_primary_action_fixture,
    phase17n_state_with_setup,
)
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventLog, JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_policies import mission_action_policy_for_id
from warhammer40k_core.engine.mission_decisions import request_mission_action_start
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    primary_mission_marker_id,
)
from warhammer40k_core.engine.primary_scoring_action_conditions import (
    EXTRACT_INTELLIGENCE_ACTION_ID,
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
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.primary_scoring_operation_marker_conditions import (
    EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE,
    FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE,
    MAINTAIN_CONTROL_ACTION_ID,
    NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD,
    ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN,
    ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
    ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN,
    ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE,
    PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS,
    THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE,
    evaluate_operation_marker_scoring_condition,
    extract_intelligence_marker_source_identity,
    locate_and_deny_marker_source_identity,
    maintain_control_marker_source_identity,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitness,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryComponentTurnStartMembership,
    PrimaryRulesUnitTurnStartMembership,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.geometry.measurement import OBJECTIVE_CONTROL_HORIZONTAL_INCHES
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)

_OPERATION_MARKER_KIND = "operation"


def _gather_intel_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="reconnaissance-vs-reconnaissance-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="reconnaissance",
    )


def _vital_link_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
    )


def _locate_setup() -> MissionSetup:
    return phase17n_event_setup(
        layout_id="disruption-vs-priority-assets-layout-1",
        attacker_force_disposition_id="disruption",
        defender_force_disposition_id="priority-assets",
    )


def _objective_context(
    *,
    setup: MissionSetup,
    battle_round: int,
    end_of_battle: bool = False,
) -> PrimaryScoringConditionContext:
    results = tuple(
        ObjectiveControlResult.from_contributors(
            objective_id=marker.objective_marker_id,
            contributors=(),
        )
        for marker in setup.objective_markers
    )
    record = ObjectiveControlRecord(
        record_id=f"step5e-objective-record-round-{battle_round}",
        game_id="step5e-objective-game",
        battle_round=battle_round,
        active_player_id="player-a",
        timing=ObjectiveControlTiming.TURN_END,
        phase=BattlePhase.FIGHT.value,
        battlefield_id="step5e-objective-battlefield",
        results=results,
    )
    return PrimaryScoringConditionContext(
        record=record,
        mission_setup=setup,
        turn_order=("player-a", "player-b"),
        player_id="player-a",
        end_of_battle=end_of_battle,
    )


def _primary_awards_by_condition(
    state: GameState,
    *,
    player_id: str,
    battle_round: int | None = None,
) -> dict[str, int]:
    awards: dict[str, int] = {}
    for ledger in state.victory_point_ledgers:
        for transaction in ledger.transactions:
            if (
                transaction.player_id != player_id
                or transaction.source_kind is not VictoryPointSourceKind.PRIMARY
                or type(transaction.metadata) is not dict
            ):
                continue
            if battle_round is not None and transaction.battle_round != battle_round:
                continue
            condition = transaction.metadata.get("scoring_rule_condition")
            if type(condition) is not str:
                continue
            awards[condition] = transaction.amount
    return awards


def _assert_operation_marker_boundary_path(
    *,
    state: GameState,
    record: ObjectiveControlRecord,
    player_id: str,
    condition_id: str,
    expected_vp: int,
    end_of_battle: bool,
    require_restore: bool = True,
) -> None:
    event_log = EventLog()
    score_primary_objective_control_boundary(
        state=state,
        record=record,
        end_of_battle=end_of_battle,
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
        end_of_battle=end_of_battle,
        event_log=event_log,
    )
    assert [ledger.to_payload() for ledger in state.victory_point_ledgers] == ledgers_payload
    assert [
        evidence.to_payload() for evidence in state.primary_scoring_state_evidence_records
    ] == evidence_payload
    if not require_restore:
        return
    restored = GameState.from_payload(state.to_payload())
    assert restored.to_payload() == state.to_payload()
    replayed_log = EventLog.from_payload(event_log.to_payload())
    assert replayed_log.to_payload() == event_log.to_payload()
    assert any(
        event.event_type == PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT
        for event in replayed_log.records
    )


def _resolved_primary_action(
    *,
    layout_id: str,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    player_id: str,
    mission_action_id: str,
    target_objective_id: str | None = None,
) -> tuple[GameState, ObjectiveControlRecord]:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id=layout_id,
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_force_disposition_id=defender_force_disposition_id,
        player_id=player_id,
        mission_action_id=mission_action_id,
        current_phase=BattlePhase.FIGHT,
        target_objective_id=target_objective_id,
    )
    _bind_force_dispositions(state)
    if target_id != action.target_id:
        raise AssertionError("Step 5E Action turn-end target drifted.")
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
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    return state, record


def _two_turn_maintain_control_same_central() -> tuple[
    GameState,
    ObjectiveControlRecord,
    str,
    tuple[str, ...],
]:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id=MAINTAIN_CONTROL_ACTION_ID,
        current_phase=BattlePhase.FIGHT,
        target_objective_id=None,
    )
    _bind_force_dispositions(state)
    if target_id != action.target_id:
        raise AssertionError("Step 5E accumulated Maintain Control target drifted.")
    first_record = _complete_started_maintain_control(
        state=state,
        decisions=decisions,
        store_record=True,
    )
    assert first_record is not None
    score_primary_objective_control_boundary(
        state=state,
        record=first_record,
        end_of_battle=False,
        event_log=decisions.event_log,
    )
    first_markers = _active_maintain_control_markers(state)
    assert len(first_markers) == 1
    assert first_markers[0].objective_marker_id == target_id

    state.battle_round = 2
    _start_maintain_control(
        state=state,
        decisions=decisions,
        unit_instance_id=action.unit_instance_id,
        target_id=target_id,
        result_id="phase17n-action-result:maintain-control:player-b:round-2",
    )
    record = _complete_started_maintain_control(
        state=state,
        decisions=decisions,
        store_record=True,
    )
    assert record is not None
    markers = _active_maintain_control_markers(state)
    assert len(markers) == 2
    marker_ids = tuple(marker.marker_id for marker in markers)
    assert marker_ids[0] != marker_ids[1]
    assert {marker.objective_marker_id for marker in markers} == {target_id}
    return state, record, target_id, marker_ids


def _complete_started_maintain_control(
    *,
    state: GameState,
    decisions: DecisionController,
    store_record: bool,
) -> ObjectiveControlRecord | None:
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    if store_record:
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
    else:
        record = resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.TURN_END,
                phase=BattlePhase.FIGHT,
                ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
            )
        )
    resolved = resolve_primary_mission_actions_at_turn_end(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.FIGHT,
        turn_end_record=record,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert len(resolved) == 1
    return record if store_record else None


def _start_maintain_control(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    target_id: str,
    result_id: str,
) -> None:
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id="player-b",
        mission_action_id=MAINTAIN_CONTROL_ACTION_ID,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    request = status.decision_request
    assert request is not None
    selected_option = next(
        option
        for option in request.options
        if option.option_id != "continue_to_shooting"
        and cast(dict[str, JsonValue], option.payload)["unit_instance_id"] == unit_instance_id
        and cast(dict[str, JsonValue], option.payload)["target_id"] == target_id
    )
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=selected_option.option_id,
    )
    GameLifecycle(decision_controller=decisions, state=state).submit_decision(result)


def _active_maintain_control_markers(state: GameState) -> tuple[PrimaryMissionMarkerState, ...]:
    identity = maintain_control_marker_source_identity()
    matching = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.status is PrimaryMissionMarkerStatus.ACTIVE
        and (marker.source_rule_id, marker.source_descriptor_id) == identity
    )
    return tuple(sorted(matching, key=lambda marker: marker.marker_id))


def _place_player_unit_at(
    state: GameState,
    *,
    player_id: str,
    x_inches: float,
    y_inches: float,
) -> None:
    assert state.battlefield_state is not None
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
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


def _bind_force_dispositions(state: GameState) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5E fixture requires MissionSetup.")
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=setup.primary_mission_assignment_for_player(
                army.player_id
            ).force_disposition_id,
        )
        for army in state.army_definitions
    ]


def _plant_extract_intelligence_markers(
    state: GameState,
    *,
    objective_ids: tuple[str, ...],
    start_index: int = 1,
    replace_progress: bool = True,
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise AssertionError("Step 5E extract-intelligence fixture requires MissionSetup.")
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == "player-a"
        for candidate in army.units
    )
    identity = extract_intelligence_marker_source_identity()
    progress = (
        PrimaryMissionProgressState.empty()
        if replace_progress
        else state.primary_mission_progress_state
    )
    for offset, objective_id in enumerate(objective_ids):
        index = start_index + offset
        action = _completed_extract_intelligence_action(
            setup,
            unit_instance_id=unit.unit_instance_id,
            target_id=objective_id,
            action_index=index,
        )
        state.mission_action_states.append(action)
        progress = progress.add_marker(
            _action_marker(
                game_id=state.game_id,
                owner_player_id="player-a",
                mission_id="primary-gather-intel",
                source_identity=identity,
                objective_id=objective_id,
                index=index,
                source_action_id=action.action_id,
                created_battle_round=2,
                created_phase=BattlePhase.FIGHT.value,
            )
        )
    state.replace_primary_mission_progress_state(progress)


def _completed_extract_intelligence_action(
    setup: MissionSetup,
    *,
    unit_instance_id: str,
    target_id: str,
    action_index: int,
) -> MissionActionState:
    policy = mission_action_policy_for_id(EXTRACT_INTELLIGENCE_ACTION_ID)
    started = MissionActionState.start(
        action_id=f"step5e-extract-intelligence-{action_index:02d}",
        mission_action_id=EXTRACT_INTELLIGENCE_ACTION_ID,
        player_id="player-a",
        unit_instance_id=unit_instance_id,
        target_id=target_id,
        condition_target_id=None,
        mission_id=setup.primary_mission_id_for_player("player-a"),
        battle_round=2,
        phase=BattlePhase.SHOOTING.value,
        start_timing=policy.start_timing,
        completion_timing=policy.completion_timing,
        eligible_unit_instance_ids=(unit_instance_id,),
        interruption_conditions=policy.interruption_conditions,
        scoring_source_id=policy.scoring_source_id,
        victory_points=0,
    )
    return started.complete_without_award(
        battle_round=2,
        phase=BattlePhase.FIGHT.value,
        completion_timing=policy.completion_timing,
    )


def _place_unit_in_terrain(
    state: GameState,
    *,
    player_id: str,
    terrain: MissionLogicalTerrainArea,
) -> None:
    assert state.battlefield_state is not None
    min_x, min_y, max_x, max_y = terrain.bounds()
    target_x = (min_x + max_x) / 2.0
    target_y = (min_y + max_y) / 2.0
    unit = next(
        candidate
        for army in state.army_definitions
        if army.player_id == player_id
        for candidate in army.units
    )
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


def _objective_marker_progress(
    setup: MissionSetup,
    *,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    objective_ids: tuple[str, ...],
) -> PrimaryMissionProgressState:
    if setup.primary_mission_id_for_player(owner_player_id) != mission_id:
        raise AssertionError("Step 5E marker fixture mission assignment drifted.")
    progress = PrimaryMissionProgressState.empty()
    for index, objective_id in enumerate(objective_ids, start=1):
        progress = progress.add_marker(
            _action_marker(
                game_id="phase11c-game",
                owner_player_id=owner_player_id,
                mission_id=mission_id,
                source_identity=source_identity,
                objective_id=objective_id,
                index=index,
                source_action_id=f"step5e-action-{index:02d}",
            )
        )
    return progress


def _terrain_marker_progress(
    setup: MissionSetup,
    *,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    terrain_ids: tuple[str, ...],
    game_id: str = "phase11c-game",
) -> PrimaryMissionProgressState:
    if setup.primary_mission_id_for_player(owner_player_id) != mission_id:
        raise AssertionError("Step 5E terrain-marker fixture mission assignment drifted.")
    progress = PrimaryMissionProgressState.empty()
    for index, terrain_id in enumerate(terrain_ids, start=1):
        progress = progress.add_marker(
            _terrain_marker(
                game_id=game_id,
                owner_player_id=owner_player_id,
                mission_id=mission_id,
                source_identity=source_identity,
                terrain_id=terrain_id,
                index=index,
            )
        )
    return progress


def _action_marker(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    objective_id: str,
    index: int,
    source_action_id: str,
    created_battle_round: int = 1,
    created_phase: str = BattlePhase.FIGHT.value,
) -> PrimaryMissionMarkerState:
    source_event_id = f"step5e-marker-event-{index:02d}"
    marker_id = primary_mission_marker_id(
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_identity[0],
        source_descriptor_id=source_identity[1],
        marker_kind=_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=objective_id,
        terrain_feature_id=None,
        created_battle_round=created_battle_round,
        created_phase=created_phase,
        created_active_player_id=owner_player_id,
        source_event_id=source_event_id,
        source_result_id=None,
        source_action_id=source_action_id,
        source_destruction_id=None,
        source_designation_id=None,
    )
    return PrimaryMissionMarkerState(
        marker_id=marker_id,
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_identity[0],
        source_descriptor_id=source_identity[1],
        marker_kind=_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=objective_id,
        terrain_feature_id=None,
        created_battle_round=created_battle_round,
        created_phase=created_phase,
        created_active_player_id=owner_player_id,
        source_event_id=source_event_id,
        source_result_id=None,
        source_action_id=source_action_id,
        source_destruction_id=None,
        source_designation_id=None,
    )


def _terrain_marker(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    source_identity: tuple[str, str],
    terrain_id: str,
    index: int,
) -> PrimaryMissionMarkerState:
    source_event_id = f"step5e-terrain-marker-event-{index:02d}"
    source_result_id = f"step5e-terrain-result-{index:02d}"
    marker_id = primary_mission_marker_id(
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_identity[0],
        source_descriptor_id=source_identity[1],
        marker_kind=_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.TERRAIN_FEATURE,
        objective_marker_id=None,
        terrain_feature_id=terrain_id,
        created_battle_round=None,
        created_phase=None,
        created_active_player_id=None,
        source_event_id=source_event_id,
        source_result_id=source_result_id,
        source_action_id=None,
        source_destruction_id=None,
        source_designation_id=None,
    )
    return PrimaryMissionMarkerState(
        marker_id=marker_id,
        game_id=game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_identity[0],
        source_descriptor_id=source_identity[1],
        marker_kind=_OPERATION_MARKER_KIND,
        anchor_kind=MarkerAnchorKind.TERRAIN_FEATURE,
        objective_marker_id=None,
        terrain_feature_id=terrain_id,
        created_battle_round=None,
        created_phase=None,
        created_active_player_id=None,
        source_event_id=source_event_id,
        source_result_id=source_result_id,
        source_action_id=None,
        source_destruction_id=None,
        source_designation_id=None,
    )


def _position_witnesses(
    *,
    friendly_terrain_ids: tuple[str, ...],
    enemy_terrain_ids: tuple[str, ...],
    friendly_player_id: str = "player-a",
    enemy_player_id: str = "player-b",
) -> tuple[PrimaryScoringRulesUnitPositionWitness, ...]:
    return (
        _position_witness(
            owner_player_id=friendly_player_id,
            unit_instance_id="army-alpha:intercessor-unit-1",
            terrain_ids=friendly_terrain_ids,
        ),
        _position_witness(
            owner_player_id=enemy_player_id,
            unit_instance_id="army-bravo:intercessor-unit-1",
            terrain_ids=enemy_terrain_ids,
        ),
    )


def _position_witness(
    *,
    owner_player_id: str,
    unit_instance_id: str,
    terrain_ids: tuple[str, ...],
) -> PrimaryScoringRulesUnitPositionWitness:
    return PrimaryScoringRulesUnitPositionWitness(
        owner_player_id=owner_player_id,
        rules_unit_membership=PrimaryRulesUnitTurnStartMembership(
            rules_unit_instance_id=unit_instance_id,
            component_memberships=(
                PrimaryComponentTurnStartMembership(
                    unit_instance_id=unit_instance_id,
                    evaluated_model_instance_ids=(f"{unit_instance_id}:model-1",),
                    logical_terrain_area_ids=terrain_ids,
                    objective_marker_witnesses=(),
                ),
            ),
        ),
    )


def _non_home_objective_ids(setup: MissionSetup) -> tuple[str, ...]:
    home_roles = {ObjectiveMarkerRole.ATTACKER_HOME, ObjectiveMarkerRole.DEFENDER_HOME}
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role not in home_roles
    )


def _central_objective_ids(setup: MissionSetup) -> tuple[str, ...]:
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )


def _expansion_objective_ids(setup: MissionSetup) -> tuple[str, ...]:
    return tuple(
        marker.objective_marker_id
        for marker in setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.EXPANSION
    )


def _far_from_objectives(
    setup: MissionSetup,
    *,
    candidate_ids: tuple[str, ...],
    reference_ids: tuple[str, ...],
) -> str:
    coordinates = {
        marker.objective_marker_id: (marker.x_inches, marker.y_inches)
        for marker in setup.objective_markers
    }
    for candidate_id in candidate_ids:
        source = coordinates[candidate_id]
        if all(
            math.hypot(
                source[0] - coordinates[reference_id][0],
                source[1] - coordinates[reference_id][1],
            )
            > OBJECTIVE_CONTROL_HORIZONTAL_INCHES
            for reference_id in reference_ids
        ):
            return candidate_id
    raise AssertionError("Step 5E fixture could not find a far objective.")


def _first_logical_terrain_id(setup: MissionSetup) -> str:
    return mission_logical_terrain_areas(setup)[0].logical_terrain_area_id


def _second_logical_terrain_id(setup: MissionSetup, *, excluded_id: str) -> str:
    return next(
        area.logical_terrain_area_id
        for area in mission_logical_terrain_areas(setup)
        if area.logical_terrain_area_id != excluded_id
    )


__all__: list[str] = []
__all__ += ["BattlePhase", "DecisionController", "DecisionResult"]
__all__ += ["EACH_FRIENDLY_OPERATION_MARKER_WITHIN_CONTROLLED_CENTRAL_RANGE"]
__all__ += ["EXTRACT_INTELLIGENCE_ACTION_ID", "EventLog"]
__all__ += ["FRIENDLY_OPERATION_MARKER_WITHIN_OPPONENT_HOME_RANGE_END_OF_BATTLE", "GameLifecycle"]
__all__ += ["MAINTAIN_CONTROL_ACTION_ID", "GameLifecycleError", "GameState", "JsonValue"]
__all__ += ["MarkerAnchorKind", "MissionActionState", "MissionLogicalTerrainArea", "MissionSetup"]
__all__ += ["NO_ENEMY_OPERATION_MARKERS_ON_BATTLEFIELD", "OBJECTIVE_CONTROL_HORIZONTAL_INCHES"]
__all__ += ["ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN"]
__all__ += ["ONLY_ONE_FRIENDLY_OPERATION_MARKER_TERRAIN_END_OF_BATTLE"]
__all__ += ["ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN"]
__all__ += ["ONLY_ONE_OPPONENT_OPERATION_MARKER_TERRAIN_END_OF_BATTLE", "ObjectiveControlContext"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveControlTiming"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_SCORING_OPERATION_MARKER_CONDITIONS", "Pose"]
__all__ += ["PrimaryComponentTurnStartMembership", "PrimaryMissionMarkerState"]
__all__ += ["PrimaryMissionMarkerStatus", "PrimaryMissionProgressState"]
__all__ += ["PrimaryRulesUnitTurnStartMembership", "PrimaryScoringConditionContext"]
__all__ += ["PrimaryScoringRulesUnitPositionWitness", "RuntimeModifierRegistry"]
__all__ += ["SUPPORTED_GENERIC_PRIMARY_SCORING_CONDITIONS"]
__all__ += ["THREE_OR_MORE_FRIENDLY_OPERATION_MARKERS_END_OF_BATTLE", "VictoryPointSourceKind"]
__all__ += ["_OPERATION_MARKER_KIND", "_action_marker", "_active_maintain_control_markers"]
__all__ += ["_assert_operation_marker_boundary_path", "_bind_force_dispositions"]
__all__ += ["_central_objective_ids", "_complete_started_maintain_control"]
__all__ += ["_completed_extract_intelligence_action", "_expansion_objective_ids"]
__all__ += ["_far_from_objectives", "_first_logical_terrain_id", "_gather_intel_setup"]
__all__ += ["_locate_setup", "_non_home_objective_ids", "_objective_context"]
__all__ += ["_objective_marker_progress", "_place_player_unit_at", "_place_unit_in_terrain"]
__all__ += ["_plant_extract_intelligence_markers", "_position_witness", "_position_witnesses"]
__all__ += ["_primary_awards_by_condition", "_resolved_primary_action"]
__all__ += ["_second_logical_terrain_id", "_start_maintain_control", "_terrain_marker"]
__all__ += ["_terrain_marker_progress", "_two_turn_maintain_control_same_central"]
__all__ += ["_vital_link_setup", "cast", "deepcopy"]
__all__ += ["evaluate_operation_marker_scoring_condition", "evaluate_primary_scoring_condition"]
__all__ += ["extract_intelligence_marker_source_identity", "home_objective_ids"]
__all__ += ["locate_and_deny_marker_source_identity", "maintain_control_marker_source_identity"]
__all__ += ["math", "mission_action_policy_for_id", "mission_logical_terrain_areas"]
__all__ += ["mission_scoring_policies_from_setup", "phase17n_event_setup"]
__all__ += ["phase17n_started_primary_action_fixture", "phase17n_state_with_setup"]
__all__ += ["primary_mission_marker_id", "primary_scoring_rules_from_definition", "pytest"]
__all__ += ["replace", "request_mission_action_start", "resolve_objective_control"]
__all__ += ["resolve_primary_mission_actions_at_turn_end"]
__all__ += ["score_primary_objective_control_boundary"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
