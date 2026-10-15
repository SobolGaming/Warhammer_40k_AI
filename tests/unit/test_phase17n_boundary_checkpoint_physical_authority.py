from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase17n_boundary_checkpoint_physical_authority import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    BattlefieldRemovalKind,
    BattlePhase,
    Callable,
    DecisionController,
    DecisionResult,
    EventRecord,
    GameLifecycle,
    GameLifecycleError,
    GameState,
    JsonValue,
    MissionActionState,
    MissionActionStatus,
    MissionLogicalTerrainArea,
    Pose,
    PrimaryMissionActionCompletionEvidence,
    PrimaryMissionBoundaryCheckpoint,
    RuntimeModifierRegistry,
    SecondaryMissionCardState,
    ShootingPhaseState,
    UnitInstance,
    _forge_vanguard_success,
    _resolve_vanguard_failure,
    _target_area,
    active_secondary_mission_card_states_from_checkpoint,
    append_authenticated_normal_move,
    apply_mission_decision,
    capture_primary_mission_boundary_checkpoint,
    deepcopy,
    mission_logical_terrain_areas,
    phase17n_accepted_action_opportunity_decline_fixture,
    phase17n_action_turn_end_record,
    phase17n_started_primary_action_fixture,
    primary_mission_boundary_state_from_checkpoint,
    pytest,
    record_primary_battlefield_departure,
    record_primary_battlefield_departure_event,
    record_primary_mission_boundary_checkpoint,
    replace,
    request_mission_action_opportunity,
    request_mission_action_start,
    resolve_primary_mission_actions_at_turn_end,
    terrain_intersections_from_model_inventory,
    terrain_model_inventory_from_checkpoint,
    validate_json_value,
    validate_primary_mission_action_integrity,
    validate_primary_mission_boundary_checkpoint_source_registry,
    validate_primary_mission_boundary_physical_authority,
)


def test_checkpoint_snapshots_all_players_active_secondary_cards_and_rebuilds_fight_state() -> None:
    state, _decisions, action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    player_a_card = replace(
        SecondaryMissionCardState.active_fixed(
            player_id="player-a",
            secondary_mission_id="engage-on-all-fronts",
        ),
        selection_payload={"selected_quarter_id": "north-east"},
    )
    player_b_card = replace(
        SecondaryMissionCardState.active_fixed(
            player_id="player-b",
            secondary_mission_id="cleanse",
        ),
        selection_payload={"selected_objective_id": "objective-1"},
    )
    expected_cards = (player_a_card, player_b_card)
    state.secondary_mission_card_states = list(expected_cards)
    checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="objective_control",
        player_id=action.player_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    assert active_secondary_mission_card_states_from_checkpoint(checkpoint) == expected_cards
    assert checkpoint.active_secondary_mission_ids == (player_b_card.secondary_mission_id,)

    state.secondary_mission_card_states = [
        card.score(transaction_id=f"later-score-{card.player_id}") for card in expected_cards
    ]
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    boundary_state = primary_mission_boundary_state_from_checkpoint(
        state=state,
        checkpoint=checkpoint,
    )

    assert boundary_state.current_battle_phase is BattlePhase.FIGHT
    assert tuple(boundary_state.secondary_mission_card_states) == expected_cards
    assert boundary_state.transport_cargo_states == []


@pytest.mark.parametrize(
    "removal_kind",
    [BattlefieldRemovalKind.DESTROYED, BattlefieldRemovalKind.INTO_RESERVES],
)
def test_action_checkpoint_rejects_unit_restored_after_prior_departure(
    removal_kind: BattlefieldRemovalKind,
) -> None:
    state, decisions, action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(action.unit_instance_id)
    removed_model_ids = tuple(row.model_instance_id for row in placement.model_placements)
    state.battlefield_state = battlefield.without_unit_placement(action.unit_instance_id)
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=action.unit_instance_id,
        affected_component_unit_instance_ids=(action.unit_instance_id,),
        departed_component_unit_instance_ids=(action.unit_instance_id,),
        removed_model_instance_ids=removed_model_ids,
        removal_kind=removal_kind,
        occurrence_id=f"phase17n-boundary-prior-{removal_kind.value}",
        source_id=f"phase17n-boundary-prior-source-{removal_kind.value}",
    )
    assert departure is not None
    departure_event = record_primary_battlefield_departure_event(
        event_log=decisions.event_log,
        departure=departure,
    )

    # The tampered payload restores the unit and rewrites the complete Action graph as though
    # it was still alive and placed. The earlier engine-owned departure remains the authority root.
    state.battlefield_state = battlefield
    forged_events = [
        departure_event,
        *(
            event
            for event in decisions.event_log.records
            if event.event_id != departure_event.event_id
        ),
    ]

    with pytest.raises(GameLifecycleError, match="contradicts preceding physical history"):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=tuple(forged_events),
            decision_records=decisions.records,
        )


def test_action_checkpoint_rejects_coordinated_position_rewrite_after_move() -> None:
    state, decisions, action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    # Build the move as prior history, then attach the deliberately stale Action graph.
    # Its later physical-checkpoint validator must reject that coordinated forgery.
    assert state.mission_action_states == [action]
    state.mission_action_states = []
    prior_event_count = len(decisions.event_log.records)
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=action.unit_instance_id,
        suffix="action-start-position",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            pose.position.y - 6.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
    state.mission_action_states = [action]
    physical_events = decisions.event_log.records[prior_event_count:]
    action_events = decisions.event_log.records[:prior_event_count]

    # The full Action request/record/start graph still cites the original on-objective checkpoint,
    # while the exact movement ledger and restored state leave the unit outside that checkpoint.
    with pytest.raises(
        GameLifecycleError,
        match=r"(?:contradicts preceding movement history|physical history .* drifted)",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=(*physical_events, *action_events),
            decision_records=decisions.records,
        )


def test_checkpoint_cannot_reset_prior_authenticated_movement_authority() -> None:
    state, decisions, action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    battlefield_at_a = state.battlefield_state
    assert battlefield_at_a is not None
    checkpoint_at_a = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="action_request",
        player_id=action.player_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=action.unit_instance_id,
        suffix="checkpoint-reset",
        pose_transform=lambda pose: Pose.at(
            pose.position.x + 1.0,
            pose.position.y,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )

    # Both forged boundaries claim the pre-move A position. The later boundary must not be
    # allowed to trust the first forged boundary as a new physical-history root.
    decisions.event_log.append(
        PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        checkpoint_at_a.to_payload(),
    )
    later_event = decisions.event_log.append(
        PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        checkpoint_at_a.to_payload(),
    )
    state.battlefield_state = battlefield_at_a
    records = decisions.event_log.records
    later_index = next(
        index for index, event in enumerate(records) if event.event_id == later_event.event_id
    )

    with pytest.raises(
        GameLifecycleError,
        match="contradicts preceding movement history",
    ):
        validate_primary_mission_boundary_physical_authority(
            state=state,
            event_records=records,
            decision_records=decisions.records,
            checkpoint_index=later_index,
            checkpoint=checkpoint_at_a,
        )


def test_secondary_action_checkpoint_cannot_reset_authenticated_movement_on_restore() -> None:
    state, _discarded_decisions, _discarded_action, _target_id = (
        phase17n_started_primary_action_fixture(
            layout_id="purge-the-foe-vs-priority-assets-layout-1",
            attacker_force_disposition_id="priority-assets",
            defender_force_disposition_id="purge-the-foe",
            player_id="player-a",
            mission_action_id="maintain-control",
            current_phase=BattlePhase.FIGHT,
            player_unit_count=2,
        )
    )
    setup = state.mission_setup
    assert setup is not None
    state.army_definitions = [
        replace(
            army,
            force_disposition_id=(
                setup.primary_mission_assignment_for_player(army.player_id).force_disposition_id
            ),
        )
        for army in state.army_definitions
    ]
    state.primary_objective_turn_start_states = []
    state.primary_rules_unit_turn_start_snapshots = []
    state.mission_action_states = []
    # This fixture resets its preliminary Action setup before recording the tested history.
    state.persisting_effects = []
    state.decision_request_count = 0
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    state.replace_shooting_phase_state(
        ShootingPhaseState(
            battle_round=state.battle_round,
            active_player_id="player-a",
        )
    )
    state.record_secondary_mission_card_state(
        SecondaryMissionCardState.active_tactical(
            player_id="player-a",
            secondary_mission_id="cleanse",
            battle_round=state.battle_round,
            source_result_id="phase17n-checkpoint-reset-held-cleanse",
        )
    )
    state_at_a = deepcopy(state)
    history_decisions = DecisionController()
    action_unit, primary_unit = tuple(
        unit
        for army in state.army_definitions
        if army.player_id == "player-a"
        for unit in army.units
    )
    append_authenticated_normal_move(
        state=state,
        decisions=history_decisions,
        unit_instance_id=primary_unit.unit_instance_id,
        suffix="secondary-checkpoint-reset",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            pose.position.y - 6.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
    authenticated_history_payload = history_decisions.to_payload()
    hidden_history_payload = deepcopy(authenticated_history_payload)
    for history_index, event in enumerate(hidden_history_payload["event_log"]):
        event["event_type"] = "phase17n_checkpoint_reset_placeholder"
        event["payload"] = {"history_index": history_index}
    decisions = DecisionController.from_payload(hidden_history_payload)

    # The coordinated restore puts the later state back at A. The first boundary at A is still
    # genuinely owned by a held Secondary Action request and accepted Secondary Action result.
    state.battlefield_state = state_at_a.battlefield_state
    opportunity = request_mission_action_opportunity(
        state=state,
        decisions=decisions,
        player_id="player-a",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    opportunity_request = opportunity.decision_request if opportunity is not None else None
    assert opportunity_request is not None
    secondary_option = next(
        option
        for option in opportunity_request.options
        if option.option_id.startswith(f"start:cleanse-objective:{action_unit.unit_instance_id}:")
    )
    secondary_payload = cast(dict[str, JsonValue], secondary_option.payload)
    assert secondary_payload["mission_kind"] == "secondary"
    secondary_result = DecisionResult.for_request(
        result_id="phase17n-secondary-checkpoint-reset-result",
        request=opportunity_request,
        selected_option_id=secondary_option.option_id,
    )
    secondary_record = decisions.submit_result(secondary_result)
    apply_mission_decision(
        state=state,
        request=secondary_record.request,
        result=secondary_result,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    primary_status = request_mission_action_start(
        state=state,
        decisions=decisions,
        player_id="player-a",
        mission_action_id="maintain-control",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    primary_request = primary_status.decision_request
    assert primary_request is not None
    primary_option = next(
        option
        for option in primary_request.options
        if option.option_id.startswith(f"start:maintain-control:{primary_unit.unit_instance_id}:")
    )
    primary_result = DecisionResult.for_request(
        result_id="phase17n-primary-after-secondary-checkpoint-reset-result",
        request=primary_request,
        selected_option_id=primary_option.option_id,
    )
    primary_record = decisions.submit_result(primary_result)
    apply_mission_decision(
        state=state,
        request=primary_record.request,
        result=primary_result,
        decisions=decisions,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    forged_payload = GameLifecycle(decision_controller=decisions, state=state).to_payload()
    history_count = len(authenticated_history_payload["event_log"])
    forged_payload["decisions"]["event_log"][:history_count] = authenticated_history_payload[
        "event_log"
    ]
    with pytest.raises(
        GameLifecycleError,
        match="contradicts preceding movement history",
    ):
        GameLifecycle.from_payload(forged_payload)


def test_restore_rejects_action_checkpoint_with_unauthenticated_request() -> None:
    state, decisions, request, _result = phase17n_accepted_action_opportunity_decline_fixture()
    record_primary_mission_boundary_checkpoint(
        state=state,
        event_log=decisions.event_log,
        boundary_kind="action_request",
        player_id="player-b",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    forged_request = replace(
        request,
        request_id="phase17n-unauthenticated-checkpoint-request",
    )
    decisions.event_log.append("decision_requested", forged_request.to_payload())

    with pytest.raises(GameLifecycleError, match="lacks exact decision authority"):
        validate_primary_mission_boundary_checkpoint_source_registry(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=decisions.queue.pending_requests,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )


def test_restore_rejects_event_between_action_checkpoint_and_request() -> None:
    state, decisions, _request, _result = phase17n_accepted_action_opportunity_decline_fixture()
    payload = deepcopy(decisions.to_payload())
    events = payload["event_log"]
    assert events[0]["event_type"] == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    assert events[1]["event_type"] == "decision_requested"
    events.insert(
        1,
        {
            "event_id": "event-000002",
            "event_type": "phase17n_unrelated_audit_event",
            "payload": {"game_id": state.game_id},
        },
    )
    for index, event in enumerate(events, start=1):
        event["event_id"] = f"event-{index:06d}"
    forged_decisions = DecisionController.from_payload(payload)

    with pytest.raises(GameLifecycleError, match="Action checkpoint is orphaned"):
        validate_primary_mission_boundary_checkpoint_source_registry(
            state=state,
            event_records=forged_decisions.event_log.records,
            decision_records=forged_decisions.records,
            pending_decision_requests=forged_decisions.queue.pending_requests,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )


def test_restore_rejects_action_checkpoint_active_player_drift() -> None:
    state, decisions, _request, _result = phase17n_accepted_action_opportunity_decline_fixture()
    records = list(decisions.event_log.records)
    checkpoint_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    )
    checkpoint_event = records[checkpoint_index]
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(checkpoint_event.payload)
    forged_checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=next(
            player_id for player_id in state.player_ids if player_id != checkpoint.active_player_id
        ),
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=checkpoint.model_states,
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_card_jsons=checkpoint.active_secondary_mission_card_jsons,
        completed_mission_action_state_jsons=checkpoint.completed_mission_action_state_jsons,
        primary_unit_destruction_state_jsons=checkpoint.primary_unit_destruction_state_jsons,
        starting_strength_record_jsons=checkpoint.starting_strength_record_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )
    records[checkpoint_index] = replace(
        checkpoint_event,
        payload=validate_json_value(forged_checkpoint.to_payload()),
    )

    with pytest.raises(GameLifecycleError, match="checkpoint ownership drifted"):
        validate_primary_mission_boundary_checkpoint_source_registry(
            state=state,
            event_records=tuple(records),
            decision_records=decisions.records,
            pending_decision_requests=decisions.queue.pending_requests,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )


__all__: list[str] = []
__all__ += ["Callable", "EventRecord", "GameState", "MissionActionState", "MissionActionStatus"]
__all__ += ["PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY", "MissionLogicalTerrainArea"]
__all__ += ["PrimaryMissionActionCompletionEvidence", "UnitInstance", "_forge_vanguard_success"]
__all__ += ["_resolve_vanguard_failure", "_target_area", "mission_logical_terrain_areas"]
__all__ += ["phase17n_action_turn_end_record", "resolve_primary_mission_actions_at_turn_end"]
__all__ += ["terrain_intersections_from_model_inventory"]
__all__ += ["terrain_model_inventory_from_checkpoint"]
