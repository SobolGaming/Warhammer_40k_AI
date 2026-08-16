from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.mission_action_policies import (
    primary_mission_state_rule_for_id,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_mission_marker_integrity import (
    SURVEIL_MOVE_COMPLETION_EVENT_TYPES,
    SURVEIL_MOVE_PROCESSED_EVENT,
    surveil_move_event_unit_id,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    primary_consecration_designation_id,
)
from warhammer40k_core.engine.rules_units import (
    current_rules_unit_views_for_identity,
    rules_unit_identities_share_lineage,
    rules_unit_view_by_id,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_CONSECRATION_STATE_RULE_ID = "consecrate-destroyer-becomes-consecration-unit"
_SURVEIL_STATE_RULE_ID = "surveil-remove-operation-markers-after-move"


def record_consecration_designation_for_destruction(
    *, state: GameState, destruction: PrimaryUnitDestructionState
) -> PrimaryConsecrationDesignationState | None:
    if type(destruction) is not PrimaryUnitDestructionState:
        raise GameLifecycleError("Consecration designation requires destruction evidence.")
    mission_setup = state.mission_setup
    attribution = destruction.destruction_attribution
    if (
        mission_setup is None
        or attribution is None
        or attribution.source_rules_unit_instance_id is None
        or destruction.source_model_destroyed_event_id is None
    ):
        return None
    player_id = attribution.destroying_player_id
    descriptor = primary_mission_state_rule_for_id(_CONSECRATION_STATE_RULE_ID)
    if mission_setup.primary_mission_id_for_player(player_id) != descriptor.primary_mission_id:
        return None
    source_rules_unit_id = attribution.source_rules_unit_instance_id
    if any(
        designation.owner_player_id == player_id
        and designation.status is PrimaryConsecrationStatus.ACTIVE
        and rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=designation.rules_unit_instance_id,
            second_unit_instance_id=source_rules_unit_id,
        )
        for designation in state.primary_mission_progress_state.consecration_designations
    ):
        return None
    current_views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=source_rules_unit_id,
    )
    if len(current_views) != 1:
        raise GameLifecycleError("Consecration destroyer identity is ambiguous.")
    source_event_id = destruction.source_model_destroyed_event_id
    designation_id = primary_consecration_designation_id(
        game_id=state.game_id,
        owner_player_id=player_id,
        mission_id=descriptor.primary_mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.state_rule_id,
        rules_unit_instance_id=current_views[0].unit_instance_id,
        component_unit_instance_ids=current_views[0].component_unit_instance_ids,
        source_destruction_id=destruction.destruction_id,
        created_battle_round=destruction.battle_round,
        created_phase=destruction.phase,
        created_active_player_id=destruction.active_player_id,
        source_event_id=source_event_id,
    )
    designation = PrimaryConsecrationDesignationState(
        designation_id=designation_id,
        game_id=state.game_id,
        owner_player_id=player_id,
        mission_id=descriptor.primary_mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.state_rule_id,
        rules_unit_instance_id=current_views[0].unit_instance_id,
        component_unit_instance_ids=current_views[0].component_unit_instance_ids,
        source_destruction_id=destruction.destruction_id,
        created_battle_round=destruction.battle_round,
        created_phase=destruction.phase,
        created_active_player_id=destruction.active_player_id,
        source_event_id=source_event_id,
    )
    state.replace_primary_mission_progress_state(
        state.primary_mission_progress_state.add_consecration_designation(designation)
    )
    return designation


def resolve_surveil_marker_removal_for_completed_moves(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    mission_setup = state.mission_setup
    if mission_setup is None or state.battlefield_state is None:
        return
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Surveil marker removal requires RuntimeModifierRegistry.")
    trigger_records = tuple(
        record
        for record in decisions.event_log.records
        if record.event_type in SURVEIL_MOVE_COMPLETION_EVENT_TYPES
        and not _surveil_move_already_processed(
            decisions=decisions,
            trigger_event_id=record.event_id,
        )
    )
    if not trigger_records:
        return
    descriptor = primary_mission_state_rule_for_id(_SURVEIL_STATE_RULE_ID)
    for trigger in trigger_records:
        payload = trigger.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Move completion event payload must be an object.")
        if (
            payload.get("game_id") != state.game_id
            or payload.get("battle_round") != state.battle_round
            or payload.get("phase") != completed_phase.value
        ):
            continue
        if (
            trigger.event_type == "movement_activation_completed"
            and payload.get("movement_phase_action") == "remain_stationary"
        ):
            continue
        unit_id = surveil_move_event_unit_id(payload)
        if unit_id is None:
            continue
        mover = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        if (
            mission_setup.primary_mission_id_for_player(mover.owner_player_id)
            != descriptor.primary_mission_id
        ):
            continue
        mover_id = mover.unit_instance_id
        objective_proximity_witness = rules_unit_objective_proximity_witness(
            state=state,
            rules_unit_instance_id=mover_id,
        )
        objective_ids = objective_proximity_witness.objective_marker_ids
        removed: list[PrimaryMissionMarkerState] = []
        for marker in state.primary_mission_progress_state.markers:
            if (
                marker.status is not PrimaryMissionMarkerStatus.ACTIVE
                or marker.owner_player_id == mover.owner_player_id
                or marker.marker_kind != "operation"
                or marker.objective_marker_id not in objective_ids
            ):
                continue
            removed_marker = marker.removed(
                battle_round=state.battle_round,
                phase=completed_phase.value,
                active_player_id=_active_player_id(state),
                source_id=descriptor.source_id,
                event_id=trigger.event_id,
            )
            state.replace_primary_mission_progress_state(
                state.primary_mission_progress_state.replace_marker(removed_marker)
            )
            removed.append(removed_marker)
        decisions.event_log.append(
            SURVEIL_MOVE_PROCESSED_EVENT,
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": completed_phase.value,
                "player_id": mover.owner_player_id,
                "moving_rules_unit_instance_id": mover_id,
                "moving_rules_unit_objective_proximity_witness": (
                    objective_proximity_witness.to_payload()
                ),
                "objective_marker_ids": list(objective_ids),
                "removed_primary_mission_markers": [marker.to_payload() for marker in removed],
                "trigger_event_id": trigger.event_id,
                "trigger_event_type": trigger.event_type,
                "source_id": descriptor.source_id,
            },
        )


def _surveil_move_already_processed(
    *, decisions: DecisionController, trigger_event_id: str
) -> bool:
    return any(
        record.event_type == SURVEIL_MOVE_PROCESSED_EVENT
        and isinstance(record.payload, dict)
        and record.payload.get("trigger_event_id") == trigger_event_id
        for record in decisions.event_log.records
    )


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Primary mission state runtime requires active player.")
    return state.active_player_id


__all__ = (
    "record_consecration_designation_for_destruction",
    "resolve_surveil_marker_removal_for_completed_moves",
)
