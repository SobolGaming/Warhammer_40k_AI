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


def test_checkpoint_physical_chain_allows_monotonic_midbattle_model_additions() -> None:
    state, decisions, action, _target_id = phase17n_started_primary_action_fixture(
        layout_id="purge-the-foe-vs-priority-assets-layout-1",
        attacker_force_disposition_id="purge-the-foe",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="maintain-control",
        current_phase=BattlePhase.FIGHT,
    )
    source_army = next(
        army for army in state.army_definitions if army.player_id == action.player_id
    )
    source_unit = source_army.units[0]
    source_model_id_prefix = f"{source_unit.unit_instance_id}:"
    pre_add_checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(
        next(
            event.payload
            for event in decisions.event_log.records
            if event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
        )
    )

    def added_unit(suffix: str) -> UnitInstance:
        unit_id = f"{source_unit.unit_instance_id}-{suffix}"
        return replace(
            source_unit,
            unit_instance_id=unit_id,
            own_models=tuple(
                replace(
                    model,
                    model_instance_id=(
                        f"{unit_id}:{model.model_instance_id.removeprefix(source_model_id_prefix)}"
                    ),
                )
                for model in source_unit.own_models
            ),
        )

    between_unit = added_unit("midbattle-between-checkpoints")
    state.add_unit_to_army(
        player_id=action.player_id,
        unit=between_unit,
        source_id="phase17n-midbattle-between-checkpoints",
    )
    checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="action_request",
        player_id=action.player_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    checkpoint_event = decisions.event_log.append(
        PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        checkpoint.to_payload(),
    )

    after_unit = added_unit("midbattle-after-last-checkpoint")
    state.add_unit_to_army(
        player_id=action.player_id,
        unit=after_unit,
        source_id="phase17n-midbattle-after-last-checkpoint",
    )
    checkpoint_index = next(
        index
        for index, event in enumerate(decisions.event_log.records)
        if event.event_id == checkpoint_event.event_id
    )

    validate_primary_mission_boundary_physical_authority(
        state=state,
        event_records=decisions.event_log.records,
        decision_records=decisions.records,
        checkpoint_index=checkpoint_index,
        checkpoint=checkpoint,
    )

    regressed_event = decisions.event_log.append(
        PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
        pre_add_checkpoint.to_payload(),
    )
    regressed_index = len(decisions.event_log.records) - 1
    assert decisions.event_log.records[regressed_index].event_id == regressed_event.event_id
    with pytest.raises(GameLifecycleError, match="model authority inventory regressed"):
        validate_primary_mission_boundary_physical_authority(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            checkpoint_index=regressed_index,
            checkpoint=pre_add_checkpoint,
        )


def test_restore_rejects_orphan_turn_end_checkpoint_after_vanguard_consumer() -> None:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="vanguard-operation",
        current_phase=BattlePhase.FIGHT,
        vanguard_enemy_position="inside",
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
    _resolve_vanguard_failure(
        state=state,
        decisions=decisions,
        action=action,
        target_id=target_id,
    )
    record_primary_mission_boundary_checkpoint(
        state=state,
        event_log=decisions.event_log,
        boundary_kind="turn_end",
        player_id="player-b",
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )

    with pytest.raises(GameLifecycleError, match="turn-end checkpoint is orphaned"):
        validate_primary_mission_boundary_checkpoint_source_registry(
            state=state,
            event_records=decisions.event_log.records,
            decision_records=decisions.records,
            pending_decision_requests=decisions.queue.pending_requests,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )


def test_vanguard_failure_cannot_be_rewritten_by_moving_enemy_only_in_checkpoint() -> None:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="vanguard-operation",
        current_phase=BattlePhase.FIGHT,
        vanguard_enemy_position="inside",
    )
    target_area = _target_area(state=state, target_id=target_id)
    _, target_min_y, _, _ = target_area.bounds()
    enemy_unit_id = next(
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id != action.player_id
        for unit in army.units
    )
    # The accepted Action checkpoint anchors the enemy inside the target area.
    _resolve_vanguard_failure(
        state=state,
        decisions=decisions,
        action=action,
        target_id=target_id,
    )
    forged_events = _forge_vanguard_success(
        state=state,
        decisions=decisions,
        action=action,
        unit_instance_id=enemy_unit_id,
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            target_min_y - 2.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )

    with pytest.raises(
        GameLifecycleError,
        match=r"(?:contradicts preceding movement history|physical history .* drifted)",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=forged_events,
            decision_records=decisions.records,
        )


def test_vanguard_actor_cannot_be_placed_inside_only_in_terminal_checkpoint() -> None:
    state, decisions, action, target_id = phase17n_started_primary_action_fixture(
        layout_id="reconnaissance-vs-priority-assets-layout-1",
        attacker_force_disposition_id="reconnaissance",
        defender_force_disposition_id="priority-assets",
        player_id="player-b",
        mission_action_id="vanguard-operation",
        current_phase=BattlePhase.FIGHT,
        vanguard_enemy_position="near_outside",
    )
    target_area = _target_area(state=state, target_id=target_id)
    _, min_y, _, max_y = target_area.bounds()
    # Enemy models start outside; only the acting unit needs a recorded move.
    # Isolate the checkpoint forgery from the independent move-interruption guard.
    # Full restore rejects suppressed interruptions in the Order 77 regression.
    assert state.mission_action_states == [action]
    state.mission_action_states = []
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=action.unit_instance_id,
        suffix="vanguard-actor-outside",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            max_y + 2.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
    state.mission_action_states = [action]
    _resolve_vanguard_failure(
        state=state,
        decisions=decisions,
        action=action,
        target_id=target_id,
    )
    forged_events = _forge_vanguard_success(
        state=state,
        decisions=decisions,
        action=action,
        unit_instance_id=action.unit_instance_id,
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            (min_y + max_y) / 2.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )

    with pytest.raises(
        GameLifecycleError,
        match=r"(?:contradicts preceding movement history|physical history .* drifted)",
    ):
        validate_primary_mission_action_integrity(
            state=state,
            event_records=forged_events,
            decision_records=decisions.records,
        )


__all__: list[str] = []
__all__ += ["BattlefieldRemovalKind", "Callable", "DecisionController", "DecisionResult"]
__all__ += ["EventRecord", "GameLifecycle", "GameState", "JsonValue", "MissionActionState"]
__all__ += ["MissionActionStatus", "MissionLogicalTerrainArea"]
__all__ += ["PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY"]
__all__ += ["PrimaryMissionActionCompletionEvidence", "SecondaryMissionCardState"]
__all__ += ["ShootingPhaseState", "active_secondary_mission_card_states_from_checkpoint"]
__all__ += ["apply_mission_decision", "cast", "deepcopy", "mission_logical_terrain_areas"]
__all__ += ["phase17n_accepted_action_opportunity_decline_fixture"]
__all__ += ["phase17n_action_turn_end_record", "primary_mission_boundary_state_from_checkpoint"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["request_mission_action_opportunity", "request_mission_action_start"]
__all__ += ["resolve_primary_mission_actions_at_turn_end"]
__all__ += ["terrain_intersections_from_model_inventory"]
__all__ += ["terrain_model_inventory_from_checkpoint", "validate_json_value"]
