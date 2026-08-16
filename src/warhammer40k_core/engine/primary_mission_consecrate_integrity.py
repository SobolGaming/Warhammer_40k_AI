from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_policies import (
    PrimaryMissionChoiceRuleDescriptor,
    PrimaryMissionStateRuleDescriptor,
    primary_mission_choice_rule_for_id,
    primary_mission_state_rule_for_id,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_CONSECRATION_UNIT_DESIGNATED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    CONSECRATE_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choice_policy import (
    ConsecrateChoicePolicy,
    resolve_consecrate_choice_policy,
)
from warhammer40k_core.engine.primary_mission_choices import (
    CONSECRATE_CHOICE_RULE_ID,
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    PRIMARY_OPERATION_MARKER_KIND,
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    primary_mission_choice_option_id,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    is_consecrated_objective_marker,
    primary_consecration_designation_id,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_DECISION_REQUESTED_EVENT: Final = "decision_requested"
_DECISION_RECORDED_EVENT: Final = "decision_recorded"
_MODEL_DESTROYED_EVENT: Final = "model_destroyed"
_OBJECTIVE_CONTROL_BOUNDARY_EVENT: Final = "end_boundary_objective_control_determined"
_OBJECTIVE_CONTROL_SOURCE_RULE_ID: Final = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
)
_CONSECRATION_STATE_RULE_ID: Final = "consecrate-destroyer-becomes-consecration-unit"
_CHOICE_EVENT_KEYS: Final = frozenset(
    {
        "choice",
        "request_id",
        "result_id",
        "selected_option_id",
        "automatic",
        "created_markers",
        "condemned_selection",
        "updated_designation",
        "removed_marker",
    }
)


def validate_primary_mission_consecrate_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...] | None = None,
) -> None:
    """Authenticate every persisted Consecrate resolution against its boundary.

    Restoration must use the immutable turn-end objective-control record and
    designation lineage. Current model positions, current Attached Unit views,
    and markers created after a historical choice are deliberately irrelevant.
    """

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Consecrate integrity requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Consecrate integrity requires typed event records.")
    if pending_decision_requests is not None and (
        type(pending_decision_requests) is not tuple
        or any(type(request) is not DecisionRequest for request in pending_decision_requests)
    ):
        raise GameLifecycleError("Consecrate integrity requires typed pending requests.")
    events_by_id = {record.event_id: record for record in event_records}
    if len(events_by_id) != len(event_records):
        raise GameLifecycleError("Consecrate integrity event IDs must be unique.")
    event_index_by_id = {record.event_id: index for index, record in enumerate(event_records)}
    descriptor = primary_mission_choice_rule_for_id(CONSECRATE_CHOICE_RULE_ID)
    _validate_descriptor(descriptor)
    progress = state.primary_mission_progress_state
    current_designations = {
        designation.designation_id: designation
        for designation in progress.consecration_designations
    }
    if len(current_designations) != len(progress.consecration_designations):
        raise GameLifecycleError("Consecrate designation IDs must be unique.")
    current_markers = {marker.marker_id: marker for marker in progress.markers}
    if len(current_markers) != len(progress.markers):
        raise GameLifecycleError("Consecrate marker IDs must be unique.")
    _validate_designation_reverse_closure(
        state=state,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
        current_designations=current_designations,
    )
    reconstructed_designations = {
        designation_id: _initial_designation_snapshot(designation)
        for designation_id, designation in current_designations.items()
    }

    for choice_index, event in enumerate(event_records):
        if event.event_type != PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
            continue
        payload = _event_payload(event, label="Primary mission choice event")
        if frozenset(payload) != _CHOICE_EVENT_KEYS:
            raise GameLifecycleError("Primary mission choice event payload fields drifted.")
        choice = PrimaryMissionChoiceData.from_payload(payload.get("choice"))
        if choice.choice_kind != CONSECRATE_CHOICE_KIND:
            continue
        _validate_choice_event(
            state=state,
            descriptor=descriptor,
            event=event,
            choice_index=choice_index,
            payload=payload,
            choice=choice,
            event_records=event_records,
            events_by_id=events_by_id,
            event_index_by_id=event_index_by_id,
            current_designations=current_designations,
            reconstructed_designations=reconstructed_designations,
            current_markers=current_markers,
        )

    for designation_id, current in current_designations.items():
        if reconstructed_designations[designation_id] != current:
            raise GameLifecycleError(
                "Consecrate persisted designation does not match its resolution history."
            )
    _validate_resolution_completeness(
        state=state,
        descriptor=descriptor,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
        current_designations=current_designations,
        current_markers=current_markers,
        pending_decision_requests=(
            () if pending_decision_requests is None else pending_decision_requests
        ),
    )


def _validate_choice_event(
    *,
    state: GameState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    event: EventRecord,
    choice_index: int,
    payload: dict[str, JsonValue],
    choice: PrimaryMissionChoiceData,
    event_records: tuple[EventRecord, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    current_designations: dict[str, PrimaryConsecrationDesignationState],
    reconstructed_designations: dict[str, PrimaryConsecrationDesignationState],
    current_markers: dict[str, PrimaryMissionMarkerState],
) -> None:
    subject_id = choice.subject_id
    if subject_id is None:
        raise GameLifecycleError("Consecrate choice is missing designation provenance.")
    current_designation = current_designations.get(subject_id)
    prior_designation = reconstructed_designations.get(subject_id)
    if current_designation is None or prior_designation is None:
        raise GameLifecycleError("Consecrate choice references an unknown designation.")
    _validate_choice_identity(
        state=state,
        descriptor=descriptor,
        choice=choice,
        designation=current_designation,
    )
    if choice.battle_round is None or choice.phase is None:
        raise GameLifecycleError("Consecrate choice battle context is incomplete.")
    request_id = _required_payload_identifier(payload.get("request_id"), label="request_id")
    request_index = _choice_request_event_index(
        choice=choice,
        request_id=request_id,
        choice_index=choice_index,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    _validate_designation_lineage(
        designation=current_designation,
        authority_index=request_index,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
    )
    record = _cited_turn_end_record(state=state, choice=choice)
    _validate_boundary_event(
        record=record,
        authority_index=request_index,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    source_identity = (descriptor.source_id, descriptor.choice_rule_id)
    prior_markers = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if is_consecrated_objective_marker(marker, source_identity)
        and _marker_event_index(
            marker=marker,
            event_index_by_id=event_index_by_id,
        )
        < request_index
    )
    policy = resolve_consecrate_choice_policy(
        state=state,
        player_id=choice.player_id,
        designation=_initial_designation_snapshot(current_designation),
        descriptor=descriptor,
        objective_control_record=record,
        consecrated_markers=prior_markers,
        candidate_presence_context="historical_restore",
    )
    _validate_choice_policy(choice=choice, descriptor=descriptor, policy=policy)
    result_id = _required_payload_identifier(payload.get("result_id"), label="result_id")
    _required_payload_identifier(
        payload.get("selected_option_id"),
        label="selected_option_id",
    )
    if (
        payload.get("automatic") is not False
        or payload.get("condemned_selection") is not None
        or payload.get("removed_marker") is not None
    ):
        raise GameLifecycleError("Consecrate choice event result shape drifted.")
    created_marker_payloads = _payload_list(
        payload.get("created_markers"),
        label="created_markers",
    )
    updated = PrimaryConsecrationDesignationState.from_payload(payload.get("updated_designation"))
    if _initial_designation_snapshot(updated) != _initial_designation_snapshot(current_designation):
        raise GameLifecycleError("Consecrate updated designation lineage drifted.")

    if not choice.selected_target_ids:
        if created_marker_payloads:
            raise GameLifecycleError("Consecrate decline cannot create a marker.")
        expected = prior_designation.resolved_without_consumption(
            battle_round=choice.battle_round,
            active_player_id=choice.player_id,
            event_id=event.event_id,
            result_id=result_id,
        )
    else:
        if len(created_marker_payloads) != 1:
            raise GameLifecycleError("Consecrate selection must create exactly one marker.")
        marker = PrimaryMissionMarkerState.from_payload(created_marker_payloads[0])
        _validate_created_marker(
            marker=marker,
            current_markers=current_markers,
            designation=current_designation,
            descriptor=descriptor,
            choice=choice,
            event=event,
            result_id=result_id,
        )
        expected = prior_designation.consumed(
            marker_id=marker.marker_id,
            battle_round=choice.battle_round,
            phase=choice.phase,
            active_player_id=choice.player_id,
            source_id=descriptor.source_id,
            event_id=event.event_id,
            result_id=result_id,
        )
    if updated != expected:
        raise GameLifecycleError("Consecrate designation transition drifted.")
    reconstructed_designations[subject_id] = expected


def _validate_choice_identity(
    *,
    state: GameState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    choice: PrimaryMissionChoiceData,
    designation: PrimaryConsecrationDesignationState,
) -> None:
    if (
        choice.game_id != state.game_id
        or choice.player_id != designation.owner_player_id
        or choice.primary_mission_id != descriptor.primary_mission_id
        or choice.primary_mission_id != designation.mission_id
        or choice.source_descriptor_id != descriptor.choice_rule_id
        or choice.source_rule_id != descriptor.source_id
        or choice.subject_id != designation.designation_id
        or choice.source_action_id is not None
        or choice.battle_round is None
        or choice.phase is None
        or choice.phase != state.battle_phase_sequence[-1].value
        or choice.battle_round < designation.created_battle_round
    ):
        raise GameLifecycleError("Consecrate choice identity or battle context drifted.")
    if (
        state.mission_setup is None
        or state.mission_setup.source_id != descriptor.source_package_id
        or state.mission_setup.primary_mission_id_for_player(choice.player_id)
        != descriptor.primary_mission_id
    ):
        raise GameLifecycleError("Consecrate choice mission assignment drifted.")


def _validate_designation_reverse_closure(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    current_designations: dict[str, PrimaryConsecrationDesignationState],
) -> None:
    """Rebuild designation creation from independently retained destructions."""

    mission_setup = state.mission_setup
    if mission_setup is None:
        if current_designations:
            raise GameLifecycleError("Consecrate designations require MissionSetup.")
        return
    descriptor = primary_mission_state_rule_for_id(_CONSECRATION_STATE_RULE_ID)
    designation_by_destruction_id: dict[str, PrimaryConsecrationDesignationState] = {}
    for designation in current_designations.values():
        if designation.source_destruction_id in designation_by_destruction_id:
            raise GameLifecycleError(
                "Consecrate destruction produced duplicate designation states."
            )
        designation_by_destruction_id[designation.source_destruction_id] = designation

    destruction_by_event_index: dict[int, PrimaryUnitDestructionState] = {}
    for destruction in state.primary_unit_destruction_states:
        if type(destruction) is not PrimaryUnitDestructionState:
            raise GameLifecycleError("Consecrate reverse closure requires typed destructions.")
        attribution = destruction.destruction_attribution
        if (
            attribution is None
            or attribution.source_rules_unit_instance_id is None
            or destruction.source_model_destroyed_event_id is None
            or mission_setup.primary_mission_id_for_player(attribution.destroying_player_id)
            != descriptor.primary_mission_id
        ):
            continue
        destruction_event_index = _destruction_recorded_event_index(
            destruction=destruction,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
        if destruction_event_index in destruction_by_event_index:
            raise GameLifecycleError("Consecrate destruction event ordering is ambiguous.")
        destruction_by_event_index[destruction_event_index] = destruction

    active_component_ids_by_designation_id: dict[str, frozenset[str]] = {}
    expected_designation_ids: set[str] = set()
    for event_index, event in enumerate(event_records):
        timeline_destruction = destruction_by_event_index.get(event_index)
        if timeline_destruction is not None:
            witness = timeline_destruction.source_rules_unit_objective_proximity_witness
            attribution = timeline_destruction.destruction_attribution
            if witness is None or attribution is None:
                raise GameLifecycleError(
                    "Consecrate destruction source-unit evidence is incomplete."
                )
            component_ids = frozenset(witness.component_unit_instance_ids)
            if (
                witness.rules_unit_instance_id != attribution.source_rules_unit_instance_id
                or not component_ids
            ):
                raise GameLifecycleError("Consecrate destruction source lineage drifted.")
            if any(
                component_ids.intersection(active_components)
                for active_components in active_component_ids_by_designation_id.values()
            ):
                continue
            created_designation = designation_by_destruction_id.get(
                timeline_destruction.destruction_id
            )
            if created_designation is None:
                raise GameLifecycleError(
                    "Consecrate destruction is missing its required designation."
                )
            expected = _designation_for_destruction(
                state=state,
                descriptor=descriptor,
                destruction=timeline_destruction,
                rules_unit_instance_id=witness.rules_unit_instance_id,
                component_unit_instance_ids=tuple(sorted(component_ids)),
            )
            if _initial_designation_snapshot(created_designation) != expected:
                raise GameLifecycleError("Consecrate destruction designation identity drifted.")
            designation_event_index = _validate_designation_lineage(
                designation=created_designation,
                authority_index=len(event_records),
                event_records=event_records,
                events_by_id=events_by_id,
                event_index_by_id=event_index_by_id,
            )
            if event_index >= designation_event_index:
                raise GameLifecycleError(
                    "Consecrate destruction/designation event ordering drifted."
                )
            expected_designation_ids.add(created_designation.designation_id)
            active_component_ids_by_designation_id[created_designation.designation_id] = (
                component_ids
            )

        if event.event_type != PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
            continue
        payload = _event_payload(event, label="Primary mission choice event")
        choice = PrimaryMissionChoiceData.from_payload(payload.get("choice"))
        if choice.choice_kind != CONSECRATE_CHOICE_KIND or not choice.selected_target_ids:
            continue
        if (
            choice.subject_id is None
            or choice.subject_id not in active_component_ids_by_designation_id
        ):
            raise GameLifecycleError("Consecrate consumption has no active designation lineage.")
        del active_component_ids_by_designation_id[choice.subject_id]

    if expected_designation_ids != set(current_designations):
        raise GameLifecycleError("Consecrate designation/destruction reverse closure drifted.")


def _destruction_recorded_event_index(
    *,
    destruction: PrimaryUnitDestructionState,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
    expected_payload: dict[str, JsonValue] = {
        "game_id": destruction.game_id,
        "battle_round": destruction.battle_round,
        "active_player_id": destruction.active_player_id,
        "phase": destruction.phase,
        "source_model_destroyed_event_id": destruction.source_model_destroyed_event_id,
        "primary_unit_destruction_state": cast(dict[str, JsonValue], destruction.to_payload()),
    }
    matches = tuple(
        event
        for event in event_records
        if event.event_type == PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT
        and event.payload == expected_payload
    )
    if len(matches) != 1:
        raise GameLifecycleError("Consecrate destruction requires one exact recorded event.")
    return event_index_by_id[matches[0].event_id]


def _designation_for_destruction(
    *,
    state: GameState,
    descriptor: PrimaryMissionStateRuleDescriptor,
    destruction: PrimaryUnitDestructionState,
    rules_unit_instance_id: str,
    component_unit_instance_ids: tuple[str, ...],
) -> PrimaryConsecrationDesignationState:
    if type(descriptor) is not PrimaryMissionStateRuleDescriptor:
        raise GameLifecycleError("Consecrate state descriptor is invalid.")
    attribution = destruction.destruction_attribution
    if attribution is None or destruction.source_model_destroyed_event_id is None:
        raise GameLifecycleError("Consecrate destruction attribution is incomplete.")
    owner_player_id = attribution.destroying_player_id
    designation_id = primary_consecration_designation_id(
        game_id=state.game_id,
        owner_player_id=owner_player_id,
        mission_id=descriptor.primary_mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.state_rule_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        source_destruction_id=destruction.destruction_id,
        created_battle_round=destruction.battle_round,
        created_phase=destruction.phase,
        created_active_player_id=destruction.active_player_id,
        source_event_id=destruction.source_model_destroyed_event_id,
    )
    return PrimaryConsecrationDesignationState(
        designation_id=designation_id,
        game_id=state.game_id,
        owner_player_id=owner_player_id,
        mission_id=descriptor.primary_mission_id,
        source_rule_id=descriptor.source_id,
        source_descriptor_id=descriptor.state_rule_id,
        rules_unit_instance_id=rules_unit_instance_id,
        component_unit_instance_ids=component_unit_instance_ids,
        source_destruction_id=destruction.destruction_id,
        created_battle_round=destruction.battle_round,
        created_phase=destruction.phase,
        created_active_player_id=destruction.active_player_id,
        source_event_id=destruction.source_model_destroyed_event_id,
    )


def _validate_resolution_completeness(
    *,
    state: GameState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    event_records: tuple[EventRecord, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    current_designations: dict[str, PrimaryConsecrationDesignationState],
    current_markers: dict[str, PrimaryMissionMarkerState],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    """Require one resolution per active designation at every owner turn end."""

    if not current_designations:
        return
    designation_index_by_id = {
        designation.designation_id: _validate_designation_lineage(
            designation=designation,
            authority_index=len(event_records),
            event_records=event_records,
            events_by_id=events_by_id,
            event_index_by_id=event_index_by_id,
        )
        for designation in current_designations.values()
    }
    consumption_index_by_id = {
        designation.designation_id: (
            None
            if designation.consumption_event_id is None
            else event_index_by_id.get(designation.consumption_event_id)
        )
        for designation in current_designations.values()
    }
    if any(
        designation.consumption_event_id is not None
        and consumption_index_by_id[designation.designation_id] is None
        for designation in current_designations.values()
    ):
        raise GameLifecycleError("Consecrate consumption event authority is unavailable.")

    resolution_indices: dict[tuple[str, str], list[int]] = {}
    for index, event in enumerate(event_records):
        if event.event_type != PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
            continue
        payload = _event_payload(event, label="Primary mission choice event")
        choice = PrimaryMissionChoiceData.from_payload(payload.get("choice"))
        if choice.choice_kind != CONSECRATE_CHOICE_KIND:
            continue
        if choice.subject_id is None or len(choice.evidence_ids) != 1:
            raise GameLifecycleError("Consecrate resolution boundary identity drifted.")
        resolution_indices.setdefault(
            (choice.subject_id, choice.evidence_ids[0]),
            [],
        ).append(index)

    boundary_rows = _consecrate_turn_end_boundaries(
        state=state,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    pending_choices = tuple(
        request
        for request in pending_decision_requests
        if request.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
    )
    if len(pending_choices) > 1:
        raise GameLifecycleError("Consecrate restore has ambiguous pending choice authority.")
    pending_request = None if not pending_choices else pending_choices[0]
    pending_authorized = False

    for row_index, (record, boundary_index) in enumerate(boundary_rows):
        next_boundary_index = (
            len(event_records)
            if row_index + 1 == len(boundary_rows)
            else boundary_rows[row_index + 1][1]
        )
        required_designation_ids = tuple(
            sorted(
                designation.designation_id
                for designation in current_designations.values()
                if designation.owner_player_id == record.active_player_id
                and designation_index_by_id[designation.designation_id] < boundary_index
                and (
                    consumption_index_by_id[designation.designation_id] is None
                    or cast(int, consumption_index_by_id[designation.designation_id])
                    > boundary_index
                )
            )
        )
        if not required_designation_ids:
            continue

        resolved_prefix_length = 0
        found_gap = False
        for designation_id in required_designation_ids:
            indices = resolution_indices.get((designation_id, record.record_id), [])
            if len(indices) > 1:
                raise GameLifecycleError(
                    "Consecrate designation has duplicate turn-end resolutions."
                )
            if indices:
                resolution_index = indices[0]
                if not boundary_index < resolution_index < next_boundary_index:
                    raise GameLifecycleError("Consecrate resolution boundary ordering drifted.")
                if found_gap:
                    raise GameLifecycleError("Consecrate resolution queue ordering drifted.")
                resolved_prefix_length += 1
            else:
                found_gap = True

        if resolved_prefix_length == len(required_designation_ids):
            continue
        if pending_authorized or pending_request is None:
            raise GameLifecycleError("Consecrate turn-end resolution authority is incomplete.")
        expected_designation_id = required_designation_ids[resolved_prefix_length]
        _validate_pending_consecrate_request(
            state=state,
            descriptor=descriptor,
            request=pending_request,
            designation=current_designations[expected_designation_id],
            record=record,
            boundary_index=boundary_index,
            next_boundary_index=next_boundary_index,
            event_records=event_records,
            events_by_id=events_by_id,
            event_index_by_id=event_index_by_id,
            current_markers=current_markers,
        )
        pending_authorized = True

    if pending_request is not None and not pending_authorized:
        raw_choice = PrimaryMissionChoiceData.from_payload(pending_request.payload)
        if raw_choice.choice_kind == CONSECRATE_CHOICE_KIND:
            raise GameLifecycleError("Pending Consecrate request has no turn-end authority.")


def _consecrate_turn_end_boundaries(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> tuple[tuple[ObjectiveControlRecord, int], ...]:
    battlefield = state.battlefield_state
    mission_setup = state.mission_setup
    if battlefield is None or mission_setup is None:
        raise GameLifecycleError("Consecrate restore requires mission battlefield state.")
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    final_phase = state.battle_phase_sequence[-1].value
    rows: list[tuple[ObjectiveControlRecord, int]] = []
    for record in state.objective_control_records:
        if record.timing is not ObjectiveControlTiming.TURN_END:
            continue
        expected_record_id = (
            "objective-control:"
            f"round-{record.battle_round:02d}:"
            f"{record.active_player_id}:"
            f"{record.phase}:"
            f"{ObjectiveControlTiming.TURN_END.value}"
        )
        if (
            record.record_id != expected_record_id
            or record.game_id != state.game_id
            or record.active_player_id not in state.player_ids
            or record.phase != final_phase
            or record.battlefield_id != battlefield.battlefield_id
            or {result.objective_id for result in record.results} != expected_objective_ids
        ):
            raise GameLifecycleError("Consecrate turn-end boundary record context drifted.")
        rows.append(
            (
                record,
                _boundary_event_index(
                    record=record,
                    event_records=event_records,
                    event_index_by_id=event_index_by_id,
                ),
            )
        )
    rows.sort(key=lambda value: value[1])
    return tuple(rows)


def _validate_pending_consecrate_request(
    *,
    state: GameState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    request: DecisionRequest,
    designation: PrimaryConsecrationDesignationState,
    record: ObjectiveControlRecord,
    boundary_index: int,
    next_boundary_index: int,
    event_records: tuple[EventRecord, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
    current_markers: dict[str, PrimaryMissionMarkerState],
) -> None:
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    _validate_choice_identity(
        state=state,
        descriptor=descriptor,
        choice=choice,
        designation=designation,
    )
    if (
        request.actor_id != choice.player_id
        or choice.selected_target_ids
        or choice.evidence_ids != (record.record_id,)
    ):
        raise GameLifecycleError("Pending Consecrate request identity drifted.")
    request_index = _pending_request_event_index(
        request=request,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    if not boundary_index < request_index < next_boundary_index:
        raise GameLifecycleError("Pending Consecrate request boundary ordering drifted.")
    _validate_designation_lineage(
        designation=designation,
        authority_index=request_index,
        event_records=event_records,
        events_by_id=events_by_id,
        event_index_by_id=event_index_by_id,
    )
    cited_record = _cited_turn_end_record(state=state, choice=choice)
    if cited_record != record:
        raise GameLifecycleError("Pending Consecrate request boundary evidence drifted.")
    _validate_boundary_event(
        record=record,
        authority_index=request_index,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    source_identity = (descriptor.source_id, descriptor.choice_rule_id)
    prior_markers = tuple(
        marker
        for marker in current_markers.values()
        if is_consecrated_objective_marker(marker, source_identity)
        and _marker_event_index(marker=marker, event_index_by_id=event_index_by_id) < request_index
    )
    policy = resolve_consecrate_choice_policy(
        state=state,
        player_id=choice.player_id,
        designation=_initial_designation_snapshot(designation),
        descriptor=descriptor,
        objective_control_record=record,
        consecrated_markers=prior_markers,
        candidate_presence_context="historical_restore",
    )
    _validate_choice_policy(choice=choice, descriptor=descriptor, policy=policy)
    _validate_pending_request_options(request=request, choice=choice)


def _validate_pending_request_options(
    *,
    request: DecisionRequest,
    choice: PrimaryMissionChoiceData,
) -> None:
    selected_sets = (*((target_id,) for target_id in choice.legal_target_ids), ())
    expected = tuple(
        sorted(
            (
                (
                    primary_mission_choice_option_id(
                        choice=choice,
                        selected_ids=selected_ids,
                    ),
                    (
                        "Decline this choice"
                        if not selected_ids
                        else f"Select {', '.join(selected_ids)}"
                    ),
                    choice.with_selected_targets(selected_ids).to_payload(),
                )
                for selected_ids in selected_sets
            ),
            key=lambda value: value[0],
        )
    )
    actual = tuple((option.option_id, option.label, option.payload) for option in request.options)
    if actual != expected:
        raise GameLifecycleError("Pending Consecrate request option inventory drifted.")


def _pending_request_event_index(
    *,
    request: DecisionRequest,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
    matches = tuple(
        event
        for event in event_records
        if event.event_type == _DECISION_REQUESTED_EVENT and event.payload == request.to_payload()
    )
    if len(matches) != 1:
        raise GameLifecycleError("Pending Consecrate request event authority drifted.")
    for event in event_records:
        if event.event_type != _DECISION_RECORDED_EVENT:
            continue
        payload = _event_payload(event, label="Decision recorded event")
        recorded_request = payload.get("request")
        if (
            isinstance(recorded_request, dict)
            and recorded_request.get("request_id") == request.request_id
        ):
            raise GameLifecycleError("Pending Consecrate request was already recorded.")
    return event_index_by_id[matches[0].event_id]


def _validate_descriptor(descriptor: PrimaryMissionChoiceRuleDescriptor) -> None:
    if (
        descriptor.trigger_timing != "own_turn_end"
        or descriptor.subject_policy != "each_friendly_consecration_unit"
        or descriptor.target_policy
        != "objective_within_subject_range_excluding_home_not_consecrated"
        or descriptor.selection_policy != "optional_up_to_one_per_subject"
        or descriptor.minimum_selections != 0
        or descriptor.maximum_selections != 1
        or descriptor.fallback_target_policy is not None
        or descriptor.effect_descriptor
        != "place_friendly_operation_marker_consecrate_objective_and_consume_unit_status"
        or descriptor.effect_duration != "persistent"
    ):
        raise GameLifecycleError("Consecrate choice descriptor semantics drifted.")


def _validate_designation_lineage(
    *,
    designation: PrimaryConsecrationDesignationState,
    authority_index: int,
    event_records: tuple[EventRecord, ...],
    events_by_id: dict[str, EventRecord],
    event_index_by_id: dict[str, int],
) -> int:
    source_event = events_by_id.get(designation.source_event_id)
    if source_event is None or source_event.event_type != _MODEL_DESTROYED_EVENT:
        raise GameLifecycleError("Consecrate designation source event drifted.")
    source_index = event_index_by_id[source_event.event_id]
    initial = _initial_designation_snapshot(designation)
    expected_payload: dict[str, JsonValue] = {
        "game_id": designation.game_id,
        "battle_round": designation.created_battle_round,
        "active_player_id": designation.created_active_player_id,
        "phase": designation.created_phase,
        "player_id": designation.owner_player_id,
        "source_destruction_id": designation.source_destruction_id,
        "primary_consecration_designation_state": cast(
            dict[str, JsonValue],
            initial.to_payload(),
        ),
        "source_id": designation.source_rule_id,
    }
    designation_events = tuple(
        record
        for record in event_records
        if record.event_type == PRIMARY_CONSECRATION_UNIT_DESIGNATED_EVENT
        and record.payload == expected_payload
    )
    if len(designation_events) != 1:
        raise GameLifecycleError("Consecrate choice requires one historical designation event.")
    designation_index = event_index_by_id[designation_events[0].event_id]
    if not source_index < designation_index < authority_index:
        raise GameLifecycleError("Consecrate designation event ordering drifted.")
    return designation_index


def _cited_turn_end_record(
    *,
    state: GameState,
    choice: PrimaryMissionChoiceData,
) -> ObjectiveControlRecord:
    if len(choice.evidence_ids) != 1:
        raise GameLifecycleError("Consecrate choice must cite one turn-end objective record.")
    matches = tuple(
        record
        for record in state.objective_control_records
        if record.record_id == choice.evidence_ids[0]
    )
    if len(matches) != 1:
        raise GameLifecycleError("Consecrate cited objective-control record is unavailable.")
    record = matches[0]
    battlefield = state.battlefield_state
    mission_setup = state.mission_setup
    if battlefield is None or mission_setup is None:
        raise GameLifecycleError("Consecrate restore requires mission battlefield state.")
    expected_record_id = (
        "objective-control:"
        f"round-{record.battle_round:02d}:"
        f"{record.active_player_id}:"
        f"{record.phase}:"
        f"{ObjectiveControlTiming.TURN_END.value}"
    )
    if (
        record.record_id != expected_record_id
        or choice.evidence_ids != (expected_record_id,)
        or record.game_id != state.game_id
        or record.battle_round != choice.battle_round
        or record.active_player_id != choice.player_id
        or record.timing is not ObjectiveControlTiming.TURN_END
        or record.phase != choice.phase
        or record.battlefield_id != battlefield.battlefield_id
    ):
        raise GameLifecycleError("Consecrate cited turn-end record context drifted.")
    expected_objective_ids = {
        marker.objective_marker_id for marker in mission_setup.objective_markers
    }
    if {result.objective_id for result in record.results} != expected_objective_ids:
        raise GameLifecycleError("Consecrate objective-control battlefield inventory drifted.")
    return record


def _validate_boundary_event(
    *,
    record: ObjectiveControlRecord,
    authority_index: int,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    boundary_index = _boundary_event_index(
        record=record,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )
    if boundary_index >= authority_index:
        raise GameLifecycleError("Consecrate turn-end boundary event ordering drifted.")


def _boundary_event_index(
    *,
    record: ObjectiveControlRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
    expected_payload: dict[str, JsonValue] = {
        "game_id": record.game_id,
        "battle_round": record.battle_round,
        "phase": record.phase,
        "record_ids": [record.record_id],
        "source_rule_id": _OBJECTIVE_CONTROL_SOURCE_RULE_ID,
    }
    matches = tuple(
        event
        for event in event_records
        if event.event_type == _OBJECTIVE_CONTROL_BOUNDARY_EVENT
        and event.payload == expected_payload
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Consecrate choice requires one exact turn-end objective boundary event."
        )
    return event_index_by_id[matches[0].event_id]


def _choice_request_event_index(
    *,
    choice: PrimaryMissionChoiceData,
    request_id: str,
    choice_index: int,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> int:
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
        raise GameLifecycleError("Consecrate choice requires one exact request event.")
    request_index = event_index_by_id[matches[0].event_id]
    if request_index >= choice_index:
        raise GameLifecycleError("Consecrate request/mutation ordering drifted.")
    return request_index


def _validate_choice_policy(
    *,
    choice: PrimaryMissionChoiceData,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    policy: ConsecrateChoicePolicy,
) -> None:
    selected_count = len(choice.selected_target_ids)
    if (
        choice.legal_target_ids != policy.eligible_objective_ids
        or choice.evidence_ids != policy.evidence_ids
        or choice.used_fallback_candidates
        or selected_count < descriptor.minimum_selections
        or selected_count > descriptor.maximum_selections
    ):
        raise GameLifecycleError("Consecrate choice policy reconstruction drifted.")


def _validate_created_marker(
    *,
    marker: PrimaryMissionMarkerState,
    current_markers: dict[str, PrimaryMissionMarkerState],
    designation: PrimaryConsecrationDesignationState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    choice: PrimaryMissionChoiceData,
    event: EventRecord,
    result_id: str,
) -> None:
    current = current_markers.get(marker.marker_id)
    if current is None or _marker_creation_snapshot(current) != marker:
        raise GameLifecycleError("Consecrate event marker is omitted or drifted from state.")
    if (
        marker.game_id != choice.game_id
        or marker.owner_player_id != choice.player_id
        or marker.mission_id != choice.primary_mission_id
        or marker.source_rule_id != descriptor.source_id
        or marker.source_descriptor_id != descriptor.choice_rule_id
        or marker.marker_kind != PRIMARY_OPERATION_MARKER_KIND
        or marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE
        or marker.objective_marker_id != choice.selected_target_ids[0]
        or marker.terrain_feature_id is not None
        or marker.created_battle_round != choice.battle_round
        or marker.created_phase != choice.phase
        or marker.created_active_player_id != choice.player_id
        or marker.source_event_id != event.event_id
        or marker.source_result_id != result_id
        or marker.source_action_id is not None
        or marker.source_destruction_id != designation.source_destruction_id
        or marker.source_designation_id != designation.designation_id
        or marker.status is not PrimaryMissionMarkerStatus.ACTIVE
    ):
        raise GameLifecycleError("Consecrate created marker provenance drifted.")


def _initial_designation_snapshot(
    designation: PrimaryConsecrationDesignationState,
) -> PrimaryConsecrationDesignationState:
    return replace(
        designation,
        last_resolved_battle_round=None,
        last_resolved_active_player_id=None,
        last_resolution_event_id=None,
        last_resolution_result_id=None,
        status=PrimaryConsecrationStatus.ACTIVE,
        consumed_marker_id=None,
        consumed_battle_round=None,
        consumed_phase=None,
        consumed_active_player_id=None,
        consumption_source_id=None,
        consumption_event_id=None,
        consumption_result_id=None,
    )


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


def _marker_event_index(
    *,
    marker: PrimaryMissionMarkerState,
    event_index_by_id: dict[str, int],
) -> int:
    index = event_index_by_id.get(marker.source_event_id)
    if index is None:
        raise GameLifecycleError("Consecrate marker references an unknown creation event.")
    return index


def _event_payload(record: EventRecord, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(record.payload, dict):
        raise GameLifecycleError(f"{label} payload must be an object.")
    return record.payload


def _payload_list(value: JsonValue | None, *, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"Consecrate event {label} must be a list.")
    return value


def _required_payload_identifier(value: JsonValue | None, *, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"Consecrate choice event {label} must be an identifier.")
    return value


__all__ = ("validate_primary_mission_consecrate_integrity",)
