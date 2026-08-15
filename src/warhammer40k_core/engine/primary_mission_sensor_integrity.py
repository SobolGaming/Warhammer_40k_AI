from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.actions import MissionActionState
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_policies import MissionActionPolicyDescriptor
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    SENSOR_SWEEP_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choices import (
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    sensor_sweep_markers_for_policy,
)
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_DECISION_REQUESTED_EVENT = "decision_requested"
_MISSION_ACTION_COMPLETED_EVENT = "mission_action_completed"


def validate_sensor_sweep_choice_historical_policy(
    *,
    state: GameState,
    progress: PrimaryMissionProgressState,
    marker: PrimaryMissionMarkerState,
    action: MissionActionState,
    descriptor: MissionActionPolicyDescriptor,
    choice: PrimaryMissionChoiceData,
    choice_event: EventRecord,
    choice_event_payload: dict[str, JsonValue],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    creation_index_by_marker_id: dict[str, int],
) -> None:
    """Reconstruct Sensor Sweep's exact marker inventory at its request boundary."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Sensor Sweep integrity requires GameState.")
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("Sensor Sweep integrity requires mission progress state.")
    if type(marker) is not PrimaryMissionMarkerState:
        raise GameLifecycleError("Sensor Sweep integrity requires a marker.")
    if type(action) is not MissionActionState:
        raise GameLifecycleError("Sensor Sweep integrity requires an Action state.")
    if type(descriptor) is not MissionActionPolicyDescriptor:
        raise GameLifecycleError("Sensor Sweep integrity requires an Action descriptor.")
    if type(choice) is not PrimaryMissionChoiceData or type(choice_event) is not EventRecord:
        raise GameLifecycleError("Sensor Sweep integrity requires a typed choice event.")
    if type(event_records) is not tuple or any(
        type(event) is not EventRecord for event in event_records
    ):
        raise GameLifecycleError("Sensor Sweep integrity requires typed event records.")
    if choice_event.event_id != marker.removal_event_id:
        raise GameLifecycleError("Sensor Sweep choice/removal event identity drifted.")

    request_index = _request_event_index(
        choice=choice,
        request_id=choice_event_payload.get("request_id"),
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    choice_index = event_index_by_id[choice_event.event_id]
    completion_index = _completed_action_event_index(
        action=action,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    if not completion_index < request_index < choice_index:
        raise GameLifecycleError("Sensor Sweep completion/request/choice ordering drifted.")

    active_markers = tuple(
        _marker_creation_snapshot(candidate)
        for candidate in progress.markers
        if _marker_was_active_at_index(
            marker=candidate,
            authority_index=request_index,
            event_index_by_id=event_index_by_id,
            creation_index_by_marker_id=creation_index_by_marker_id,
        )
    )
    legal_marker_ids = tuple(
        sorted(
            candidate.marker_id
            for candidate in sensor_sweep_markers_for_policy(
                markers=active_markers,
                action=action,
                descriptor=descriptor,
            )
        )
    )
    if (
        choice_event_payload.get("removed_marker") != marker.to_payload()
        or choice_event_payload.get("result_id") != marker.removal_result_id
        or choice_event_payload.get("automatic") is not False
        or choice_event_payload.get("created_markers") != []
        or choice_event_payload.get("condemned_selection") is not None
        or choice_event_payload.get("updated_designation") is not None
        or choice.choice_kind != SENSOR_SWEEP_CHOICE_KIND
        or choice.player_id != action.player_id
        or choice.primary_mission_id != action.mission_id
        or choice.source_descriptor_id != descriptor.mission_action_id
        or choice.source_rule_id != descriptor.source_id
        or choice.battle_round != action.completed_battle_round
        or choice.phase != action.completed_phase
        or choice.subject_id is not None
        or choice.source_action_id != action.action_id
        or choice.legal_target_ids != legal_marker_ids
        or choice.selected_target_ids != (marker.marker_id,)
        or choice.evidence_ids != (action.action_id,)
        or choice.used_fallback_candidates
    ):
        raise GameLifecycleError("Action-removed Primary marker event identity drift.")


def _request_event_index(
    *,
    choice: PrimaryMissionChoiceData,
    request_id: JsonValue | None,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
    if type(request_id) is not str or not request_id.strip():
        raise GameLifecycleError("Sensor Sweep choice requires a request identifier.")
    request_choice = replace(choice, selected_target_ids=()).to_payload()
    matches = tuple(
        event
        for event in event_records
        if event.event_type == _DECISION_REQUESTED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request_id
        and event.payload.get("decision_type") == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
        and event.payload.get("actor_id") == choice.player_id
        and event.payload.get("payload") == request_choice
    )
    if len(matches) != 1:
        raise GameLifecycleError("Sensor Sweep choice requires one exact request event.")
    return event_index_by_id[matches[0].event_id]


def _completed_action_event_index(
    *,
    action: MissionActionState,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
    matches = tuple(
        event
        for event in event_records
        if event.event_type == _MISSION_ACTION_COMPLETED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("mission_action_state") == action.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Sensor Sweep choice requires one completed Action event.")
    return event_index_by_id[matches[0].event_id]


def _marker_was_active_at_index(
    *,
    marker: PrimaryMissionMarkerState,
    authority_index: int,
    event_index_by_id: dict[str, int],
    creation_index_by_marker_id: dict[str, int],
) -> bool:
    creation_index = creation_index_by_marker_id.get(marker.marker_id)
    if creation_index is None:
        raise GameLifecycleError("Sensor Sweep marker is missing creation authority.")
    if creation_index >= authority_index:
        return False
    if marker.status is PrimaryMissionMarkerStatus.ACTIVE:
        return True
    removal_event_id = marker.removal_event_id
    if removal_event_id is None:
        raise GameLifecycleError("Removed Sensor Sweep marker lacks removal authority.")
    removal_index = event_index_by_id.get(removal_event_id)
    if removal_index is None:
        raise GameLifecycleError("Removed Sensor Sweep marker cites an unknown event.")
    return removal_index > authority_index


def _marker_creation_snapshot(marker: PrimaryMissionMarkerState) -> PrimaryMissionMarkerState:
    return replace(
        marker,
        status=PrimaryMissionMarkerStatus.ACTIVE,
        removed_battle_round=None,
        removed_phase=None,
        removed_active_player_id=None,
        removal_source_id=None,
        removal_event_id=None,
        removal_result_id=None,
        removal_action_id=None,
    )


__all__ = ("validate_sensor_sweep_choice_historical_policy",)
