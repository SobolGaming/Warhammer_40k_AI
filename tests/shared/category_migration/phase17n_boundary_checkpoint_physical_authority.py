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
from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
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
    active_secondary_mission_card_states_from_checkpoint,
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
from warhammer40k_core.engine.primary_mission_boundary_state import (
    primary_mission_boundary_state_from_checkpoint,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import SecondaryMissionCardState
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose


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
        active_secondary_mission_card_jsons=checkpoint.active_secondary_mission_card_jsons,
        completed_mission_action_state_jsons=checkpoint.completed_mission_action_state_jsons,
        primary_unit_destruction_state_jsons=checkpoint.primary_unit_destruction_state_jsons,
        starting_strength_record_jsons=checkpoint.starting_strength_record_jsons,
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


__all__: list[str] = []
__all__ += ["BattlePhase", "BattlefieldRemovalKind", "Callable", "DecisionController"]
__all__ += ["DecisionResult", "EventRecord", "GameLifecycle", "GameLifecycleError", "GameState"]
__all__ += ["JsonValue", "MissionActionState", "MissionActionStatus", "MissionLogicalTerrainArea"]
__all__ += ["PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY"]
__all__ += ["PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT", "Pose"]
__all__ += ["PrimaryMissionActionCompletionEvidence", "PrimaryMissionBoundaryCheckpoint"]
__all__ += ["RuntimeModifierRegistry", "SecondaryMissionCardState", "ShootingPhaseState"]
__all__ += ["UnitInstance", "_forge_vanguard_success", "_resolve_vanguard_failure"]
__all__ += ["_target_area", "active_secondary_mission_card_states_from_checkpoint"]
__all__ += ["append_authenticated_normal_move", "apply_mission_decision"]
__all__ += ["capture_primary_mission_boundary_checkpoint", "cast", "deepcopy"]
__all__ += ["mission_logical_terrain_areas"]
__all__ += ["phase17n_accepted_action_opportunity_decline_fixture"]
__all__ += ["phase17n_action_turn_end_record", "phase17n_started_primary_action_fixture"]
__all__ += ["primary_mission_boundary_state_from_checkpoint", "pytest"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_mission_boundary_checkpoint", "replace"]
__all__ += ["request_mission_action_opportunity", "request_mission_action_start"]
__all__ += ["resolve_primary_mission_actions_at_turn_end"]
__all__ += ["terrain_intersections_from_model_inventory"]
__all__ += ["terrain_model_inventory_from_checkpoint", "validate_json_value"]
__all__ += ["validate_primary_mission_action_integrity"]
__all__ += ["validate_primary_mission_boundary_checkpoint_source_registry"]
__all__ += ["validate_primary_mission_boundary_physical_authority"]
