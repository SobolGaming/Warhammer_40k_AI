from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
    phase17n_action_turn_end_record,
    phase17n_started_primary_action_fixture,
)

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
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
    terrain_model_inventory_from_checkpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
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
