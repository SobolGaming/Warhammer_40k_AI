from __future__ import annotations

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    mission_action_policy_descriptors,
    mission_action_policy_for_id,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_ACTION_MARKER_EFFECTS,
    PrimaryMissionActionCompletionEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
    capture_primary_mission_action_completion_evidence,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryMissionMarkerState,
    PrimaryMissionProgressState,
    primary_mission_marker_id,
)


def resolve_primary_mission_actions_at_turn_end(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    turn_end_record: ObjectiveControlRecord,
) -> tuple[MissionActionState, ...]:
    _validate_boundary(
        state=state,
        decisions=decisions,
        completed_phase=completed_phase,
        turn_end_record=turn_end_record,
    )
    policy_ids = {
        descriptor.mission_action_id for descriptor in mission_action_policy_descriptors()
    }
    pending = tuple(
        action
        for action in state.mission_action_states
        if action.status is MissionActionStatus.STARTED
        and action.mission_action_id in policy_ids
        and action.player_id == state.active_player_id
        and action.battle_round_started == state.battle_round
        and action.completion_timing == "turn_end"
    )
    resolved: list[MissionActionState] = []
    for action in pending:
        policy = mission_action_policy_for_id(action.mission_action_id)
        completion_evidence = capture_primary_mission_action_completion_evidence(
            state=state,
            action=action,
            policy=policy,
            completed_phase=completed_phase,
            objective_control_record=turn_end_record,
        )
        if not completion_evidence.completion_condition_met:
            failed = action.fail_completion()
            event_payload = _completion_event_payload(
                state=state,
                action=failed,
                policy=policy,
                completed_phase=completed_phase,
                marker=None,
                completion_evidence=completion_evidence,
            )
            state.replace_mission_action_state(failed)
            decisions.event_log.append("mission_action_completion_failed", event_payload)
            resolved.append(failed)
            continue
        completed = action.complete_without_award(
            battle_round=state.battle_round,
            phase=completed_phase.value,
            completion_timing=action.completion_timing,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        )
        completion_event_id = _next_event_id(decisions)
        marker = _marker_for_completed_action(
            state=state,
            action=completed,
            policy=policy,
            completed_phase=completed_phase,
            source_event_id=completion_event_id,
        )
        progress = _progress_with_optional_marker(
            progress=state.primary_mission_progress_state,
            marker=marker,
        )
        event_payload = _completion_event_payload(
            state=state,
            action=completed,
            policy=policy,
            completed_phase=completed_phase,
            marker=marker,
            completion_evidence=completion_evidence,
        )

        # Every fallible transition is computed above.  The two authoritative
        # aggregates are then committed as one engine-owned resolution step.
        state.replace_mission_action_state_with_primary_progress(
            action_state=completed,
            progress=progress,
        )
        event = decisions.event_log.append("mission_action_completed", event_payload)
        if event.event_id != completion_event_id:
            raise GameLifecycleError("Primary Action completion event identity drifted.")
        resolved.append(completed)
    return tuple(resolved)


def _marker_for_completed_action(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    completed_phase: BattlePhase,
    source_event_id: str,
) -> PrimaryMissionMarkerState | None:
    if policy.effect_descriptor not in PRIMARY_MISSION_ACTION_MARKER_EFFECTS:
        return None
    if state.active_player_id is None:
        raise GameLifecycleError("Primary Mission Action marker requires active player.")
    marker_id = primary_mission_marker_id(
        game_id=state.game_id,
        owner_player_id=action.player_id,
        mission_id=action.mission_id,
        source_rule_id=policy.source_id,
        source_descriptor_id=policy.mission_action_id,
        marker_kind="operation",
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=action.target_id,
        terrain_feature_id=None,
        created_battle_round=state.battle_round,
        created_phase=completed_phase.value,
        created_active_player_id=state.active_player_id,
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
        source_rule_id=policy.source_id,
        source_descriptor_id=policy.mission_action_id,
        marker_kind="operation",
        anchor_kind=MarkerAnchorKind.OBJECTIVE,
        objective_marker_id=action.target_id,
        terrain_feature_id=None,
        created_battle_round=state.battle_round,
        created_phase=completed_phase.value,
        created_active_player_id=state.active_player_id,
        source_event_id=source_event_id,
        source_result_id=None,
        source_action_id=action.action_id,
        source_destruction_id=None,
        source_designation_id=None,
    )


def _progress_with_optional_marker(
    *,
    progress: PrimaryMissionProgressState,
    marker: PrimaryMissionMarkerState | None,
) -> PrimaryMissionProgressState:
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Primary Action completion requires mission progress state.")
    if marker is None:
        return progress
    return progress.add_marker(marker)


def _completion_event_payload(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    completed_phase: BattlePhase,
    marker: PrimaryMissionMarkerState | None,
    completion_evidence: PrimaryMissionActionCompletionEvidence,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": action.player_id,
        "battle_round": state.battle_round,
        "phase": completed_phase.value,
        "mission_action_id": action.mission_action_id,
        "action_id": action.action_id,
        "mission_action_state": validate_json_value(action.to_payload()),
        "source_id": policy.source_id,
        PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY: completion_evidence.to_payload(),
    }
    if action.status is MissionActionStatus.COMPLETED:
        payload["primary_mission_marker"] = (
            None if marker is None else validate_json_value(marker.to_payload())
        )
    return payload


def _next_event_id(decisions: DecisionController) -> str:
    return f"event-{len(decisions.event_log.records) + 1:06d}"


def _validate_boundary(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_phase: BattlePhase,
    turn_end_record: ObjectiveControlRecord,
) -> None:
    if type(state) is not GameState or type(decisions) is not DecisionController:
        raise GameLifecycleError("Primary Action resolution requires engine-owned state.")
    if type(completed_phase) is not BattlePhase:
        raise GameLifecycleError("Primary Action resolution requires BattlePhase.")
    if type(turn_end_record) is not ObjectiveControlRecord:
        raise GameLifecycleError("Primary Action resolution requires objective-control record.")
    if (
        turn_end_record.game_id != state.game_id
        or turn_end_record.battle_round != state.battle_round
        or turn_end_record.active_player_id != state.active_player_id
        or turn_end_record.phase != completed_phase.value
        or turn_end_record.timing is not ObjectiveControlTiming.TURN_END
    ):
        raise GameLifecycleError("Primary Action turn-end objective record drifted.")


__all__ = ("resolve_primary_mission_actions_at_turn_end",)
