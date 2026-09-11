from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatePayload
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_marker_history import primary_marker_removal_event_index
from warhammer40k_core.engine.primary_mission_state import (
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.primary_scoring_state_evidence import PrimaryScoringStateEvidence


def validate_primary_mission_history_at_commit(
    *,
    state: GameState,
    evidence: PrimaryScoringStateEvidence,
    events: tuple[EventRecord, ...],
    commit_index: int,
) -> None:
    """Bind mission state to the chosen commit, including changes later in the same turn end."""
    indexes = {event.event_id: index for index, event in enumerate(events)}

    def before_commit(event_id: str) -> bool:
        if event_id not in indexes:
            raise GameLifecycleError("Primary scoring mission history lacks its source event.")
        return indexes[event_id] < commit_index

    markers: list[PrimaryMissionMarkerState] = []
    for marker in state.primary_mission_progress_state.markers:
        if not before_commit(marker.source_event_id):
            continue
        removal_index = primary_marker_removal_event_index(marker=marker, event_records=events)
        if removal_index is not None and removal_index >= commit_index:
            marker = replace(
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
        markers.append(marker)
    designations: list[PrimaryConsecrationDesignationState] = []
    for designation in state.primary_mission_progress_state.consecration_designations:
        if not before_commit(designation.source_event_id):
            continue
        original = replace(
            designation,
            status=PrimaryConsecrationStatus.ACTIVE,
            consumed_marker_id=None,
            consumed_battle_round=None,
            consumed_phase=None,
            consumed_active_player_id=None,
            consumption_source_id=None,
            consumption_event_id=None,
            consumption_result_id=None,
            last_resolved_battle_round=None,
            last_resolved_active_player_id=None,
            last_resolution_event_id=None,
            last_resolution_result_id=None,
        )
        for event in events[:commit_index]:
            if event.event_type != "primary_mission_choice_resolved" or not isinstance(
                event.payload, dict
            ):
                continue
            raw = event.payload.get("updated_designation")
            if isinstance(raw, dict) and raw.get("designation_id") == designation.designation_id:
                original = PrimaryConsecrationDesignationState.from_payload(raw)
        designations.append(original)
    expected = PrimaryMissionProgressState(
        markers=tuple(markers),
        condemned_selections=tuple(
            selection
            for selection in state.primary_mission_progress_state.condemned_selections
            if before_commit(selection.source_event_id)
        ),
        consecration_designations=tuple(designations),
    )
    if expected != evidence.primary_mission_progress_state:
        raise GameLifecycleError("Primary scoring mission progress drifted from its commit event.")
    for action in evidence.primary_mission_action_states:
        snapshots = tuple(
            raw
            for event in events[:commit_index]
            if event.event_type
            in {
                "mission_action_started",
                "mission_action_completed",
                "mission_action_interrupted",
                "mission_action_completion_failed",
            }
            and isinstance(event.payload, dict)
            and isinstance(raw := event.payload.get("mission_action_state"), dict)
            and raw.get("action_id") == action.action_id
        )
        if (
            not snapshots
            or MissionActionState.from_payload(cast(MissionActionStatePayload, snapshots[-1]))
            != action
        ):
            raise GameLifecycleError("Primary scoring Action drifted from its commit event.")
