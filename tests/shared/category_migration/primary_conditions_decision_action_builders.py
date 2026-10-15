from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_conditions_bindings import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY,
    PRIMARY_OPERATION_MARKER_KIND,
    SENSOR_SWEEP_LOCATE_ACTION_ID,
    AttachedUnitFormation,
    BattlefieldRemovalKind,
    BattlePhase,
    BattleShockedUnitState,
    DecisionController,
    DecisionRequest,
    DecisionResult,
    GameLifecycle,
    GameLifecycleStage,
    GameState,
    JsonValue,
    MarkerAnchorKind,
    MissionActionPriorUseEvidence,
    MissionActionState,
    MissionActionStatus,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    Pose,
    PrimaryMissionActionStartEvidence,
    PrimaryMissionChoiceData,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryObjectiveTurnStartState,
    RuntimeModifierRegistry,
    StartingAttachedUnitRecord,
    StartingStrengthRecord,
    append_authenticated_normal_move,
    battle_state,
    cast,
    consecrate_choice_request,
    default_unit_selection,
    locate_and_deny_setup_choice_request,
    logical_terrain_area_within_player_territory,
    mission_action_for_state,
    mission_action_policy_for_id,
    mission_logical_terrain_areas,
    phase11c_config,
    primary_mission_marker_id,
    record_completed_command_occurrences_for_fixture,
    record_primary_battlefield_departure,
    record_primary_battlefield_departure_event,
    record_primary_turn_start_evidence_event,
    replace,
    request_mission_action_start,
    resolve_primary_mission_actions_at_turn_end,
    resolve_surveil_markers_for_fixture,
    sensor_sweep_marker_removal_choice_request,
    shared_action_turn_end_record,
    validate_json_value,
    validate_primary_mission_progress_state,
    with_model_offsets,
)
from tests.shared.category_migration.phase17n_primary_scoring_conditions_common_fixtures import (
    _phase17n_event_setup,
    _phase17n_refresh_turn_start_snapshot,
    _phase17n_submit_primary_mission_choice,
)


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
    state = battle_state(
        game_id="phase17n-punishment-choice-game",
        player_a_units=(default_unit_selection("alpha"),),
        player_b_units=tuple(default_unit_selection(key) for key in enemy_keys),
    )
    decisions = DecisionController()
    units = {
        unit.unit_instance_id.split(":", maxsplit=1)[1]: unit
        for army in state.army_definitions
        for unit in army.units
    }
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
        event_log=decisions.event_log,
        objective_state=state.primary_objective_turn_start_states[0],
        position_snapshot=state.primary_rules_unit_turn_start_snapshots[0],
    )
    return (
        state,
        decisions,
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
    from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
    from tests.setup_completion_helpers import (
        record_existing_primary_turn_start_evidence_events_for_fixture,
    )
    from warhammer40k_core.engine.model_destruction_triggers import (
        advance_model_destruction_triggers,
    )
    from warhammer40k_core.engine.unit_destroyed_hooks import UnitDestroyedHookRegistry

    _phase17n_refresh_turn_start_snapshot(state)
    record_existing_primary_turn_start_evidence_events_for_fixture(state, decisions=decisions)
    for model_id in destroyed_unit.own_model_ids():
        destroy_rule_model_for_fixture(
            state=state,
            decisions=decisions,
            model_id=model_id,
            destroying_player_id="player-a",
            source_unit_id=unit.unit_instance_id,
            source_model_id=unit.own_models[0].model_instance_id,
        )
    assert (
        advance_model_destruction_triggers(
            state=state, decisions=decisions, registry=UnitDestroyedHookRegistry.empty()
        )
        is None
    )
    destruction = next(
        value
        for value in state.primary_unit_destruction_states
        if value.destroyed_unit_instance_id == destroyed_unit.unit_instance_id
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
    movement_legal_formation: bool = False,
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
                offsets=(
                    (
                        (0.0, 0.0),
                        (1.5, 0.0),
                        (3.0, 0.0),
                        (0.75, 1.5),
                        (2.25, 1.5),
                    )
                    if movement_legal_formation
                    else ((0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0))
                ),
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
    fixture_config = phase11c_config(
        game_id=state.game_id,
        player_a_units=(
            (
                default_unit_selection("intercessor-unit-1"),
                default_unit_selection("intercessor-unit-2"),
            )
            if player_unit_count == 2
            else None
        ),
    )
    record_completed_command_occurrences_for_fixture(
        state,
        decisions=decisions,
        config=fixture_config,
    )
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


def _phase17n_surveil_move_marker_state() -> tuple[GameState, str, str]:
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
    return state, moving_unit.unit_instance_id, objective.objective_marker_id


def _phase17n_surveil_integrity_fixture(
    *, resolve_marker_rules: bool = True
) -> tuple[GameState, DecisionController]:
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
    if not resolve_marker_rules:
        return state, decisions
    resolve_surveil_markers_for_fixture(
        state=state,
        decisions=decisions,
        completed_phase=BattlePhase.MOVEMENT,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    assert state.primary_mission_progress_state.markers[0].status is (
        PrimaryMissionMarkerStatus.REMOVED
    )
    assert any(
        event.event_type == "primary_surveil_move_marker_removal_resolved"
        for event in decisions.event_log.records
    )
    return state, decisions


__all__: list[str] = []
__all__ += ["AttachedUnitFormation", "BattlePhase", "BattleShockedUnitState"]
__all__ += ["DECLINE_MISSION_ACTION_START_OPTION_ID", "BattlefieldRemovalKind"]
__all__ += ["DecisionController", "DecisionRequest", "DecisionResult", "GameLifecycle"]
__all__ += ["GameLifecycleStage", "GameState", "JsonValue", "MarkerAnchorKind"]
__all__ += ["MissionActionPriorUseEvidence", "MissionActionState", "MissionActionStatus"]
__all__ += ["ObjectiveControlContribution", "ObjectiveControlRecord", "ObjectiveControlResult"]
__all__ += ["ObjectiveControlTiming", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY", "PRIMARY_OPERATION_MARKER_KIND", "Pose"]
__all__ += ["PrimaryMissionActionStartEvidence", "PrimaryMissionChoiceData"]
__all__ += ["PrimaryMissionMarkerState", "PrimaryMissionMarkerStatus"]
__all__ += ["PrimaryObjectiveTurnStartState", "RuntimeModifierRegistry"]
__all__ += ["SENSOR_SWEEP_LOCATE_ACTION_ID", "StartingAttachedUnitRecord"]
__all__ += ["StartingStrengthRecord", "_phase17n_action_turn_end_record"]
__all__ += ["_phase17n_completed_sensor_action", "_phase17n_consecrate_choice_state"]
__all__ += ["_phase17n_event_setup", "_phase17n_forged_completion_marker"]
__all__ += ["_phase17n_locate_choice_state", "_phase17n_punishment_attached_choice_state"]
__all__ += ["_phase17n_punishment_choice_state", "_phase17n_refresh_turn_start_snapshot"]
__all__ += ["_phase17n_resolved_consecrate_choice_fixture"]
__all__ += ["_phase17n_resolved_sensor_choice_fixture"]
__all__ += ["_phase17n_sensor_start_integrity_fixture"]
__all__ += ["_phase17n_started_primary_action_fixture", "_phase17n_submit_primary_mission_choice"]
__all__ += ["_phase17n_surveil_action_start_evidence_fixture"]
__all__ += ["_phase17n_surveil_integrity_fixture", "_phase17n_surveil_move_marker_state"]
__all__ += ["_phase17n_use_limit_action", "append_authenticated_normal_move", "battle_state"]
__all__ += ["cast", "consecrate_choice_request", "default_unit_selection"]
__all__ += ["locate_and_deny_setup_choice_request"]
__all__ += ["logical_terrain_area_within_player_territory", "mission_action_for_state"]
__all__ += ["mission_action_policy_for_id", "mission_logical_terrain_areas", "phase11c_config"]
__all__ += ["primary_mission_marker_id", "record_completed_command_occurrences_for_fixture"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_turn_start_evidence_event", "replace", "request_mission_action_start"]
__all__ += ["resolve_primary_mission_actions_at_turn_end", "resolve_surveil_markers_for_fixture"]
__all__ += ["sensor_sweep_marker_removal_choice_request", "shared_action_turn_end_record"]
__all__ += ["validate_json_value", "validate_primary_mission_progress_state"]
__all__ += ["with_model_offsets"]
