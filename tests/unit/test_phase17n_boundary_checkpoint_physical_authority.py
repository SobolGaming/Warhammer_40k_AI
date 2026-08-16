from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
    phase17n_accepted_action_opportunity_decline_fixture,
    phase17n_action_turn_end_record,
    phase17n_started_primary_action_fixture,
)

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_decisions import (
    apply_mission_decision,
    request_mission_action_opportunity,
    request_mission_action_start,
)
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.shooting import ShootingPhaseState
from warhammer40k_core.engine.primary_battlefield_departure import (
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_primary_battlefield_departure_event,
)
from warhammer40k_core.engine.primary_mission_action_integrity import (
    validate_primary_mission_action_integrity,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PrimaryMissionActionCompletionEvidence,
)
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_action_start_authority import (
    terrain_intersections_from_model_inventory,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint import (
    capture_primary_mission_boundary_checkpoint,
    record_primary_mission_boundary_checkpoint,
    terrain_model_inventory_from_checkpoint,
    validate_primary_mission_boundary_checkpoint_source_registry,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    validate_primary_mission_boundary_physical_authority,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


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
        vanguard_enemy_position="near_outside",
    )
    target_area = _target_area(state=state, target_id=target_id)
    _, target_min_y, _, _ = target_area.bounds()
    enemy_unit_id = next(
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id != action.player_id
        for unit in army.units
    )
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=enemy_unit_id,
        suffix="vanguard-enemy-inside",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            target_min_y + 1.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
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
        vanguard_enemy_position="inside",
    )
    target_area = _target_area(state=state, target_id=target_id)
    _, min_y, _, max_y = target_area.bounds()
    enemy_unit_id = next(
        unit.unit_instance_id
        for army in state.army_definitions
        if army.player_id != action.player_id
        for unit in army.units
    )
    append_authenticated_normal_move(
        state=state,
        decisions=decisions,
        unit_instance_id=enemy_unit_id,
        suffix="vanguard-enemy-outside",
        pose_transform=lambda pose: Pose.at(
            pose.position.x,
            min_y - 2.0,
            pose.position.z,
            facing_degrees=pose.facing.degrees,
        ),
    )
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


def _target_area(*, state: GameState, target_id: str) -> MissionLogicalTerrainArea:
    assert state.mission_setup is not None
    return next(
        area
        for area in mission_logical_terrain_areas(state.mission_setup)
        if area.logical_terrain_area_id == target_id
    )


def _resolve_vanguard_failure(
    *,
    state: GameState,
    decisions: DecisionController,
    action: MissionActionState,
    target_id: str,
) -> None:
    record = phase17n_action_turn_end_record(
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
    assert resolved[0].status is MissionActionStatus.INTERRUPTED
    assert resolved[0].interrupted_reason == "completion_condition_failed"


def _forge_vanguard_success(
    *,
    state: GameState,
    decisions: DecisionController,
    action: MissionActionState,
    unit_instance_id: str,
    pose_transform: Callable[[Pose], Pose],
) -> tuple[EventRecord, ...]:
    battlefield = state.battlefield_state
    assert battlefield is not None
    placement = battlefield.unit_placement_by_id(unit_instance_id)
    state.battlefield_state = battlefield.with_unit_placement(
        placement.with_model_placements(
            tuple(row.with_pose(pose_transform(row.pose)) for row in placement.model_placements)
        )
    )
    records = list(decisions.event_log.records)
    terminal_index = next(
        index
        for index, event in enumerate(records)
        if event.event_type == "mission_action_completion_failed"
    )
    terminal = records[terminal_index]
    terminal_payload = dict(cast(dict[str, JsonValue], terminal.payload))
    evidence = PrimaryMissionActionCompletionEvidence.from_payload(
        terminal_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY]
    )
    checkpoint_reference = evidence.boundary_checkpoint
    assert checkpoint_reference is not None
    checkpoint_index = next(
        index
        for index, event in enumerate(records)
        if event.event_id == checkpoint_reference.checkpoint_event_id
    )
    checkpoint_event = records[checkpoint_index]
    assert checkpoint_event.event_type == PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(checkpoint_event.payload)
    current_checkpoint = capture_primary_mission_boundary_checkpoint(
        state=state,
        boundary_kind="turn_end",
        player_id=action.player_id,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    current_rows = {row.model_instance_id: row for row in current_checkpoint.model_states}
    affected_ids = {
        row.model_instance_id
        for row in state.battlefield_state.unit_placement_by_id(unit_instance_id).model_placements
    }
    forged_checkpoint = PrimaryMissionBoundaryCheckpoint.create(
        boundary_kind=checkpoint.boundary_kind,
        game_id=checkpoint.game_id,
        player_id=checkpoint.player_id,
        active_player_id=checkpoint.active_player_id,
        battle_round=checkpoint.battle_round,
        phase=checkpoint.phase,
        battlefield_id=checkpoint.battlefield_id,
        model_states=tuple(
            current_rows[row.model_instance_id] if row.model_instance_id in affected_ids else row
            for row in checkpoint.model_states
        ),
        attached_unit_formation_jsons=checkpoint.attached_unit_formation_jsons,
        battle_shocked_unit_instance_ids=checkpoint.battle_shocked_unit_instance_ids,
        advanced_unit_state_jsons=checkpoint.advanced_unit_state_jsons,
        fell_back_unit_state_jsons=checkpoint.fell_back_unit_state_jsons,
        shot_unit_instance_ids=checkpoint.shot_unit_instance_ids,
        objective_control_modifier_sources=checkpoint.objective_control_modifier_sources,
        active_primary_marker_jsons=checkpoint.active_primary_marker_jsons,
        active_secondary_mission_ids=checkpoint.active_secondary_mission_ids,
        mission_action_prior_use_jsons=checkpoint.mission_action_prior_use_jsons,
    )
    inventory = terrain_model_inventory_from_checkpoint(forged_checkpoint)
    forged_evidence = replace(
        evidence,
        terrain_model_inventory=inventory,
        terrain_intersections=terrain_intersections_from_model_inventory(inventory),
        boundary_checkpoint=forged_checkpoint.reference(event_id=checkpoint_event.event_id),
        completion_condition_met=True,
    )
    forged_action = action.complete_without_award(
        battle_round=state.battle_round,
        phase=BattlePhase.FIGHT.value,
        completion_timing=action.completion_timing,
    )
    state.mission_action_states = [forged_action]
    terminal_payload["mission_action_state"] = validate_json_value(forged_action.to_payload())
    terminal_payload[PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY] = validate_json_value(
        forged_evidence.to_payload()
    )
    records[checkpoint_index] = replace(
        checkpoint_event,
        payload=validate_json_value(forged_checkpoint.to_payload()),
    )
    records[terminal_index] = replace(
        terminal,
        event_type="mission_action_completed",
        payload=validate_json_value(terminal_payload),
    )
    return tuple(records)
