from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.missions import MissionActionDefinition, ObjectiveMarkerRole
from warhammer40k_core.engine.actions import (
    MISSION_ACTION_COMPLETION_CONDITION_FAILED_REASON,
    MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
    MissionActionState,
    MissionActionStatus,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_options import mission_action_for_state
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    mission_action_policy_descriptors,
)
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_area_by_id,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.primary_mission_action_interruptions import (
    validate_primary_mission_action_interruption_evidence,
)
from warhammer40k_core.engine.primary_mission_action_options import (
    primary_mission_action_target_kind,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import PrimaryMissionChoiceData
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
)
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.rules_units import current_rules_unit_views_for_identity

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_ACTION_EVENT_TYPES = frozenset(
    {
        "mission_action_started",
        "mission_action_completed",
        "mission_action_completion_failed",
        "mission_action_interrupted",
    }
)
_TERMINAL_EVENT_TYPES = frozenset(
    {
        "mission_action_completed",
        "mission_action_completion_failed",
        "mission_action_interrupted",
    }
)
_MARKER_EFFECTS = frozenset(
    {
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
        "objective_becomes_decoy_if_action_unit_controls_target_at_turn_end",
        "objective_becomes_triangulated_if_action_unit_controls_target_at_turn_end",
        "objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
    }
)
_SENSOR_EFFECTS = frozenset(
    {
        "remove_one_friendly_operation_marker_if_action_unit_controls_selected_central_objective_at_turn_end",
        "remove_one_opponent_operation_marker_if_action_unit_controls_selected_central_objective_at_turn_end",
    }
)
_PRIMARY_MISSION_CHOICE_RESOLVED_EVENT = "primary_mission_choice_resolved"
_SENSOR_SWEEP_CHOICE_KIND = "sensor_sweep_marker_removal"
_OPERATION_MARKER_KIND = "operation"
_ATTACHED_SPLIT_INTERRUPTION_EVENT_KEYS = frozenset(
    {
        "game_id",
        "battle_round",
        "active_player_id",
        "player_id",
        "phase",
        "action_id",
        "unit_instance_id",
        "surviving_unit_instance_ids",
        "mission_action_state",
        "interrupted_reason",
    }
)


def validate_primary_mission_action_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
) -> None:
    """Authenticate source-backed Primary Action state against runtime and event authority."""

    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary Mission Action integrity requires GameState.")
    if type(event_records) is not tuple or any(
        type(record) is not EventRecord for record in event_records
    ):
        raise GameLifecycleError("Primary Mission Action integrity requires EventRecords.")
    event_index_by_id = {record.event_id: index for index, record in enumerate(event_records)}
    if len(event_index_by_id) != len(event_records):
        raise GameLifecycleError("Primary Mission Action event identities are duplicated.")

    policies = {
        descriptor.mission_action_id: descriptor
        for descriptor in mission_action_policy_descriptors()
    }
    actions = tuple(
        action for action in state.mission_action_states if action.mission_action_id in policies
    )
    action_by_id = {action.action_id: action for action in actions}
    if len(action_by_id) != len(actions):
        raise GameLifecycleError("Primary Mission Action identities are duplicated.")
    action_events = _action_events_by_action_id(event_records=event_records)
    for action_id, records in action_events.items():
        raw_mission_action_ids = tuple(
            _nested_action_payload(record).get("mission_action_id") for _index, record in records
        )
        if any(type(value) is not str for value in raw_mission_action_ids):
            raise GameLifecycleError("Primary Mission Action event source identity is invalid.")
        mission_action_ids = set(cast(tuple[str, ...], raw_mission_action_ids))
        if mission_action_ids.intersection(policies) and action_id not in action_by_id:
            raise GameLifecycleError("Primary Mission Action event has no persisted action state.")

    for action in actions:
        policy = policies[action.mission_action_id]
        runtime_action = mission_action_for_state(
            state=state,
            mission_action_id=action.mission_action_id,
        )
        _validate_runtime_definition(runtime_action=runtime_action, policy=policy)
        _validate_action_source_and_identity(
            state=state,
            action=action,
            runtime_action=runtime_action,
            policy=policy,
        )
        _validate_action_status(state=state, action=action, policy=policy)
        start_event, terminal_event = _validate_action_events(
            state=state,
            action=action,
            policy=policy,
            records=action_events.get(action.action_id, ()),
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
        _validate_sensor_start_policy(
            state=state,
            action=action,
            policy=policy,
            start_event=start_event,
            event_index_by_id=event_index_by_id,
        )
        _validate_marker_effect(
            state=state,
            action=action,
            policy=policy,
            completion_event=terminal_event,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
        if terminal_event is not None and (
            event_index_by_id[start_event.event_id] >= event_index_by_id[terminal_event.event_id]
        ):
            raise GameLifecycleError("Primary Mission Action terminal event ordering drifted.")

    _validate_sensor_use_limits(actions=actions, policies=policies)
    _validate_marker_action_references(
        state=state,
        action_ids=frozenset(action_by_id),
        policy_ids=frozenset(policies),
        policy_source_ids=frozenset(policy.source_id for policy in policies.values()),
    )


def _validate_runtime_definition(
    *,
    runtime_action: MissionActionDefinition,
    policy: MissionActionPolicyDescriptor,
) -> None:
    if type(runtime_action) is not MissionActionDefinition:
        raise GameLifecycleError("Primary Mission Action runtime definition is invalid.")
    expected_source_id = f"{policy.source_package_id}:action:{policy.mission_action_id}"
    actual = (
        runtime_action.mission_action_id,
        runtime_action.mission_id,
        runtime_action.mission_kind,
        runtime_action.start_phase,
        runtime_action.start_timing,
        runtime_action.completion_timing,
        runtime_action.eligible_unit_policy,
        runtime_action.target_policy,
        runtime_action.interruption_conditions,
        runtime_action.victory_points,
        runtime_action.scoring_source_id,
        runtime_action.source_id,
    )
    expected = (
        policy.mission_action_id,
        policy.primary_mission_id,
        "primary",
        policy.start_phase,
        policy.start_timing,
        policy.completion_timing,
        policy.eligible_unit_policy,
        policy.target_policy,
        policy.interruption_conditions,
        0,
        policy.scoring_source_id,
        expected_source_id,
    )
    if actual != expected:
        raise GameLifecycleError("Primary Mission Action runtime policy drifted.")


def _validate_action_source_and_identity(
    *,
    state: GameState,
    action: MissionActionState,
    runtime_action: MissionActionDefinition,
    policy: MissionActionPolicyDescriptor,
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action integrity requires MissionSetup.")
    if (
        action.player_id not in state.player_ids
        or setup.primary_mission_id_for_player(action.player_id) != policy.primary_mission_id
    ):
        raise GameLifecycleError("Primary Mission Action actor mission assignment drifted.")
    if (
        action.mission_id,
        action.phase_started,
        action.start_timing,
        action.completion_timing,
        action.interruption_conditions,
        action.scoring_source_id,
        action.victory_points,
    ) != (
        runtime_action.mission_id,
        runtime_action.start_phase,
        runtime_action.start_timing,
        runtime_action.completion_timing,
        runtime_action.interruption_conditions,
        runtime_action.scoring_source_id,
        runtime_action.victory_points,
    ):
        raise GameLifecycleError("Primary Mission Action persisted policy drifted.")
    _require_identity_owner(
        state=state,
        unit_instance_id=action.unit_instance_id,
        owner_player_id=action.player_id,
        label="acting unit",
    )
    for eligible_id in action.eligible_unit_instance_ids:
        _require_identity_owner(
            state=state,
            unit_instance_id=eligible_id,
            owner_player_id=action.player_id,
            label="eligible unit",
        )
    _validate_target_identity(state=state, action=action, policy=policy)


def _validate_target_identity(
    *, state: GameState, action: MissionActionState, policy: MissionActionPolicyDescriptor
) -> None:
    setup = state.mission_setup
    if setup is None:
        raise GameLifecycleError("Primary Mission Action target requires MissionSetup.")
    target_kind = primary_mission_action_target_kind(policy.target_policy)
    if target_kind == "objective_marker":
        matches = tuple(
            marker
            for marker in setup.objective_markers
            if marker.objective_marker_id == action.target_id
        )
        if len(matches) != 1 or action.condition_target_id != action.target_id:
            raise GameLifecycleError("Primary Mission Action objective target drifted.")
        if policy.target_policy.startswith("central_objective") and (
            matches[0].objective_role is not ObjectiveMarkerRole.CENTRAL
        ):
            raise GameLifecycleError("Primary Mission Action central objective target drifted.")
        if policy.target_policy.startswith("objective_marker_excluding_home") and (
            action.target_id in home_objective_ids(setup, player_id=action.player_id)
        ):
            raise GameLifecycleError("Primary Mission Action home objective target is invalid.")
        return
    if target_kind == "terrain_area":
        if action.condition_target_id != action.target_id:
            raise GameLifecycleError("Primary Mission Action terrain target drifted.")
        area = mission_logical_terrain_area_by_id(
            setup,
            logical_terrain_area_id=action.target_id,
        )
        opponent_ids = tuple(
            player_id for player_id in state.player_ids if player_id != action.player_id
        )
        if len(opponent_ids) != 1 or not logical_terrain_area_within_player_territory(
            area,
            mission_setup=setup,
            player_id=opponent_ids[0],
        ):
            raise GameLifecycleError(
                "Primary Mission Action terrain target is not enemy territory."
            )
        return
    if target_kind == "enemy_rules_unit":
        if action.condition_target_id is not None:
            raise GameLifecycleError("Primary Mission Action enemy target has condition drift.")
        views = current_rules_unit_views_for_identity(
            state=state,
            unit_instance_id=action.target_id,
        )
        owners = {view.owner_player_id for view in views}
        if len(owners) != 1 or action.player_id in owners:
            raise GameLifecycleError("Primary Mission Action enemy target owner drifted.")
        return
    raise GameLifecycleError("Primary Mission Action target kind is unsupported.")


def _validate_action_status(
    *, state: GameState, action: MissionActionState, policy: MissionActionPolicyDescriptor
) -> None:
    if action.battle_round_started > state.battle_round:
        raise GameLifecycleError("Primary Mission Action starts in a future battle round.")
    if policy.completion_timing == "immediate":
        if (
            action.status is not MissionActionStatus.COMPLETED
            or action.completed_battle_round != action.battle_round_started
            or action.completed_phase != action.phase_started
        ):
            raise GameLifecycleError("Immediate Primary Mission Action completion drifted.")
        return
    if policy.completion_timing != "turn_end":
        raise GameLifecycleError("Primary Mission Action completion timing is unsupported.")
    final_phase = state.battle_phase_sequence[-1].value
    if action.status is MissionActionStatus.COMPLETED:
        if (
            action.completed_battle_round != action.battle_round_started
            or action.completed_phase != final_phase
        ):
            raise GameLifecycleError("Turn-end Primary Mission Action completion drifted.")
        return
    if action.status is MissionActionStatus.INTERRUPTED:
        if action.interrupted_reason not in {
            *policy.interruption_conditions,
            MISSION_ACTION_COMPLETION_CONDITION_FAILED_REASON,
        }:
            raise GameLifecycleError("Primary Mission Action interruption reason drifted.")
        return
    if action.status is not MissionActionStatus.STARTED:
        raise GameLifecycleError("Primary Mission Action status is unsupported.")
    if (
        state.stage is not GameLifecycleStage.BATTLE
        or state.battle_round != action.battle_round_started
        or state.active_player_id != action.player_id
        or state.current_battle_phase is None
    ):
        raise GameLifecycleError("Started Primary Mission Action is stale.")
    phase_order = {phase.value: index for index, phase in enumerate(state.battle_phase_sequence)}
    if phase_order[state.current_battle_phase.value] < phase_order[action.phase_started]:
        raise GameLifecycleError("Started Primary Mission Action phase ordering drifted.")


def _action_events_by_action_id(
    *, event_records: tuple[EventRecord, ...]
) -> dict[str, tuple[tuple[int, EventRecord], ...]]:
    grouped: dict[str, list[tuple[int, EventRecord]]] = {}
    for index, record in enumerate(event_records):
        if record.event_type not in _ACTION_EVENT_TYPES:
            continue
        nested = _nested_action_payload(record)
        action_id = nested.get("action_id")
        if type(action_id) is not str:
            raise GameLifecycleError("Primary Mission Action event action_id is invalid.")
        grouped.setdefault(action_id, []).append((index, record))
    return {action_id: tuple(records) for action_id, records in grouped.items()}


def _validate_action_events(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    records: tuple[tuple[int, EventRecord], ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> tuple[EventRecord, EventRecord | None]:
    starts = tuple(
        record for _index, record in records if record.event_type == "mission_action_started"
    )
    terminals = tuple(
        record for _index, record in records if record.event_type in _TERMINAL_EVENT_TYPES
    )
    if len(starts) != 1:
        raise GameLifecycleError("Primary Mission Action requires one authenticated start event.")
    expected_started = replace(
        action,
        status=MissionActionStatus.STARTED,
        completed_battle_round=None,
        completed_phase=None,
        interrupted_reason=None,
        score_transaction_id=None,
    )
    start = starts[0]
    if _nested_action_payload(start) != expected_started.to_payload():
        raise GameLifecycleError("Primary Mission Action start event state drifted.")
    _validate_event_context(
        state=state,
        action=action,
        event=start,
        battle_round=action.battle_round_started,
        phase=action.phase_started,
    )
    start_payload = _object(start.payload, label="Primary Mission Action start event")
    if (
        start_payload.get("mission_action_id") != action.mission_action_id
        or start_payload.get("target_id") != action.target_id
        or start_payload.get("condition_target_id") != action.condition_target_id
        or start_payload.get("target_policy") != policy.target_policy
    ):
        raise GameLifecycleError("Primary Mission Action start event source drifted.")

    expected_terminal_type: str | None
    terminal_round: int | None
    terminal_phase: str | None
    if action.status is MissionActionStatus.STARTED:
        expected_terminal_type = None
        terminal_round = terminal_phase = None
    elif action.status is MissionActionStatus.COMPLETED:
        expected_terminal_type = "mission_action_completed"
        terminal_round = action.completed_battle_round
        terminal_phase = action.completed_phase
    elif action.interrupted_reason == MISSION_ACTION_COMPLETION_CONDITION_FAILED_REASON:
        expected_terminal_type = "mission_action_completion_failed"
        terminal_round = action.battle_round_started
        terminal_phase = state.battle_phase_sequence[-1].value
    else:
        expected_terminal_type = "mission_action_interrupted"
        terminal_round = action.battle_round_started
        terminal_phase = None
    if expected_terminal_type is None:
        if terminals:
            raise GameLifecycleError("Started Primary Mission Action has a terminal event.")
        return start, None
    matching = tuple(record for record in terminals if record.event_type == expected_terminal_type)
    if len(terminals) != 1 or len(matching) != 1:
        raise GameLifecycleError("Primary Mission Action terminal event authentication drifted.")
    terminal = matching[0]
    if _nested_action_payload(terminal) != action.to_payload():
        raise GameLifecycleError("Primary Mission Action terminal event state drifted.")
    terminal_payload = _object(terminal.payload, label="Primary Mission Action terminal event")
    if terminal_round is None:
        raise GameLifecycleError("Primary Mission Action terminal battle round is missing.")
    event_phase = terminal_payload.get("phase") if terminal_phase is None else terminal_phase
    if type(event_phase) is not str or event_phase not in {phase.value for phase in BattlePhase}:
        raise GameLifecycleError("Primary Mission Action terminal phase is invalid.")
    if expected_terminal_type == "mission_action_interrupted":
        phase_order = {
            phase.value: index for index, phase in enumerate(state.battle_phase_sequence)
        }
        if phase_order[event_phase] < phase_order[action.phase_started]:
            raise GameLifecycleError(
                "Primary Mission Action interruption precedes its start phase."
            )
    _validate_event_context(
        state=state,
        action=action,
        event=terminal,
        battle_round=terminal_round,
        phase=event_phase,
    )
    terminal_mission_action_id = terminal_payload.get("mission_action_id")
    if expected_terminal_type == "mission_action_interrupted":
        if (
            terminal_mission_action_id is not None
            and terminal_mission_action_id != action.mission_action_id
        ):
            raise GameLifecycleError("Primary Mission Action terminal source identity drifted.")
    elif terminal_mission_action_id != action.mission_action_id:
        raise GameLifecycleError("Primary Mission Action terminal source identity drifted.")
    if expected_terminal_type == "mission_action_interrupted":
        _validate_interruption_evidence_reference(
            state=state,
            action=action,
            start=start,
            terminal=terminal,
            terminal_payload=terminal_payload,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
    if (
        expected_terminal_type != "mission_action_interrupted"
        and policy.completion_timing == "turn_end"
        and terminal_payload.get("source_id") != policy.source_id
    ):
        raise GameLifecycleError("Primary Mission Action terminal source rule drifted.")
    if policy.completion_timing == "immediate" and (
        terminal_payload.get("target_policy") != policy.target_policy
    ):
        raise GameLifecycleError("Immediate Primary Mission Action target policy drifted.")
    return start, terminal


def _validate_interruption_evidence_reference(
    *,
    state: GameState,
    action: MissionActionState,
    start: EventRecord,
    terminal: EventRecord,
    terminal_payload: dict[str, JsonValue],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    evidence_id = terminal_payload.get("source_evidence_event_id")
    evidence_type = terminal_payload.get("source_evidence_event_type")
    if evidence_id is None and evidence_type is None:
        _validate_attached_split_interruption(
            state=state,
            action=action,
            terminal_payload=terminal_payload,
        )
        return
    if type(evidence_id) is not str or type(evidence_type) is not str:
        raise GameLifecycleError("Primary Mission Action interruption evidence is incomplete.")
    matches = tuple(record for record in event_records if record.event_id == evidence_id)
    if len(matches) != 1 or matches[0].event_type != evidence_type:
        raise GameLifecycleError("Primary Mission Action interruption evidence is unknown.")
    evidence = matches[0]
    if not (
        event_index_by_id[start.event_id]
        < event_index_by_id[evidence.event_id]
        < event_index_by_id[terminal.event_id]
    ):
        raise GameLifecycleError("Primary Mission Action interruption evidence ordering drifted.")
    validate_primary_mission_action_interruption_evidence(
        state=state,
        action=action,
        evidence_event=evidence,
    )


def _validate_attached_split_interruption(
    *,
    state: GameState,
    action: MissionActionState,
    terminal_payload: dict[str, JsonValue],
) -> None:
    if frozenset(terminal_payload) != _ATTACHED_SPLIT_INTERRUPTION_EVENT_KEYS:
        raise GameLifecycleError(
            "Primary Mission Action interruption without causal evidence is not an "
            "attached-unit split."
        )
    raw_survivor_ids = terminal_payload.get("surviving_unit_instance_ids")
    if type(raw_survivor_ids) is not list or any(
        type(unit_id) is not str for unit_id in raw_survivor_ids
    ):
        raise GameLifecycleError("Attached-unit split interruption survivor IDs are invalid.")
    survivor_ids = tuple(cast(list[str], raw_survivor_ids))
    if not survivor_ids or survivor_ids != tuple(sorted(set(survivor_ids))):
        raise GameLifecycleError("Attached-unit split interruption survivor IDs drifted.")
    attached_records = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == action.unit_instance_id
    )
    if len(attached_records) != 1:
        raise GameLifecycleError(
            "Evidence-less Primary Mission Action interruption requires one historical "
            "attached-unit identity."
        )
    attached = attached_records[0]
    component_ids = frozenset(attached.component_unit_instance_ids)
    survivor_set = frozenset(survivor_ids)
    leader_or_support_ids = frozenset(
        (*attached.leader_unit_instance_ids, *attached.support_unit_instance_ids)
    )
    if (
        action.interrupted_reason != MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
        or terminal_payload.get("unit_instance_id") != action.unit_instance_id
        or attached.player_id != action.player_id
        or terminal_payload.get("active_player_id") not in state.player_ids
        or not survivor_set < component_ids
        or (attached.bodyguard_unit_instance_id in survivor_set)
        == bool(survivor_set.intersection(leader_or_support_ids))
    ):
        raise GameLifecycleError("Attached-unit split interruption provenance drifted.")


def _validate_event_context(
    *,
    state: GameState,
    action: MissionActionState,
    event: EventRecord,
    battle_round: int,
    phase: str,
) -> None:
    payload = _object(event.payload, label="Primary Mission Action event")
    if (
        payload.get("game_id") != state.game_id
        or payload.get("battle_round") != battle_round
        or payload.get("phase") != phase
    ):
        raise GameLifecycleError("Primary Mission Action event battle context drifted.")
    player_id = payload.get("player_id")
    if player_id is not None and player_id != action.player_id:
        raise GameLifecycleError("Primary Mission Action event player drifted.")
    action_id = payload.get("action_id")
    if action_id is not None and action_id != action.action_id:
        raise GameLifecycleError("Primary Mission Action event action identity drifted.")


def _validate_marker_effect(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    completion_event: EventRecord | None,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    created = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.source_action_id == action.action_id
    )
    if (
        action.status is MissionActionStatus.COMPLETED
        and policy.effect_descriptor in _MARKER_EFFECTS
    ):
        if len(created) != 1 or completion_event is None:
            raise GameLifecycleError(
                "Primary Mission Action marker effect is missing or duplicated."
            )
        _validate_created_marker(
            state=state,
            action=action,
            policy=policy,
            marker=created[0],
            completion_event=completion_event,
        )
    elif created:
        raise GameLifecycleError("Primary Mission Action has an unexpected created marker.")

    removed = tuple(
        marker
        for marker in state.primary_mission_progress_state.markers
        if marker.removal_action_id == action.action_id
    )
    if policy.effect_descriptor not in _SENSOR_EFFECTS:
        if removed:
            raise GameLifecycleError("Primary Mission Action has an unexpected marker removal.")
        return
    if action.status is not MissionActionStatus.COMPLETED:
        if removed:
            raise GameLifecycleError("Uncompleted Sensor Sweep removed a marker.")
        return
    completion_candidate_ids = _sensor_marker_ids_at_completion(
        state=state,
        action=action,
        policy=policy,
        completion_event=completion_event,
        event_index_by_id=event_index_by_id,
    )
    if len(removed) > 1:
        raise GameLifecycleError("Sensor Sweep removed more than one operation marker.")
    if not removed:
        if completion_candidate_ids and not _sensor_effect_can_be_pending(
            state=state, action=action
        ):
            raise GameLifecycleError("Completed Sensor Sweep is missing its marker-removal effect.")
        return
    if completion_event is None:
        raise GameLifecycleError("Sensor Sweep removal lacks its completion event.")
    _validate_sensor_removal(
        state=state,
        action=action,
        policy=policy,
        marker=removed[0],
        completion_event=completion_event,
        completion_candidate_ids=completion_candidate_ids,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )


def _validate_created_marker(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    marker: PrimaryMissionMarkerState,
    completion_event: EventRecord,
) -> None:
    if (
        marker.game_id != state.game_id
        or marker.owner_player_id != action.player_id
        or marker.mission_id != policy.primary_mission_id
        or marker.source_rule_id != policy.source_id
        or marker.source_descriptor_id != policy.mission_action_id
        or marker.marker_kind != _OPERATION_MARKER_KIND
        or marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE
        or marker.objective_marker_id != action.target_id
        or marker.terrain_feature_id is not None
        or marker.created_battle_round != action.completed_battle_round
        or marker.created_phase != action.completed_phase
        or marker.created_active_player_id != action.player_id
        or marker.source_event_id != completion_event.event_id
        or marker.source_result_id is not None
        or marker.source_destruction_id is not None
        or marker.source_designation_id is not None
    ):
        raise GameLifecycleError("Primary Mission Action marker provenance drifted.")
    creation_snapshot = replace(
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
    payload = _object(completion_event.payload, label="Primary Mission Action completion event")
    if payload.get("primary_mission_marker") != creation_snapshot.to_payload():
        raise GameLifecycleError("Primary Mission Action marker event payload drifted.")


def _validate_sensor_removal(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    marker: PrimaryMissionMarkerState,
    completion_event: EventRecord,
    completion_candidate_ids: tuple[str, ...],
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    if (
        marker.status is not PrimaryMissionMarkerStatus.REMOVED
        or marker.marker_kind != _OPERATION_MARKER_KIND
        or marker.removal_source_id != policy.source_id
        or marker.removed_battle_round != action.completed_battle_round
        or marker.removed_phase != action.completed_phase
        or marker.removed_active_player_id != action.player_id
        or marker.removal_event_id is None
    ):
        raise GameLifecycleError("Sensor Sweep marker-removal provenance drifted.")
    matches = tuple(
        record for record in event_records if record.event_id == marker.removal_event_id
    )
    if len(matches) != 1 or matches[0].event_type != _PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
        raise GameLifecycleError("Sensor Sweep marker removal lacks its choice event.")
    removal_event = matches[0]
    if event_index_by_id[completion_event.event_id] >= event_index_by_id[removal_event.event_id]:
        raise GameLifecycleError("Sensor Sweep marker-removal event ordering drifted.")
    payload = _object(removal_event.payload, label="Sensor Sweep choice event")
    choice = PrimaryMissionChoiceData.from_payload(payload.get("choice"))
    if (
        choice.game_id != state.game_id
        or choice.choice_kind != _SENSOR_SWEEP_CHOICE_KIND
        or choice.player_id != action.player_id
        or choice.primary_mission_id != policy.primary_mission_id
        or choice.source_descriptor_id != policy.mission_action_id
        or choice.source_rule_id != policy.source_id
        or choice.battle_round != action.completed_battle_round
        or choice.phase != action.completed_phase
        or choice.source_action_id != action.action_id
        or choice.legal_target_ids != completion_candidate_ids
        or choice.selected_target_ids != (marker.marker_id,)
        or marker.marker_id not in choice.legal_target_ids
        or payload.get("removed_marker") != marker.to_payload()
    ):
        raise GameLifecycleError("Sensor Sweep choice-event authority drifted.")


def _sensor_marker_ids_at_completion(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    completion_event: EventRecord | None,
    event_index_by_id: dict[str, int],
) -> tuple[str, ...]:
    if completion_event is None:
        raise GameLifecycleError("Sensor Sweep completion event is missing.")
    completion_order = event_index_by_id[completion_event.event_id]
    candidates: list[str] = []
    for marker in state.primary_mission_progress_state.markers:
        if marker.marker_kind != _OPERATION_MARKER_KIND:
            continue
        creation_order = event_index_by_id.get(marker.source_event_id)
        if creation_order is None:
            raise GameLifecycleError("Sensor Sweep marker creation event is unknown.")
        removal_order = (
            None
            if marker.removal_event_id is None
            else event_index_by_id.get(marker.removal_event_id)
        )
        if marker.removal_event_id is not None and removal_order is None:
            raise GameLifecycleError("Sensor Sweep marker removal event is unknown.")
        if creation_order > completion_order or (
            removal_order is not None and removal_order <= completion_order
        ):
            continue
        if policy.effect_descriptor.startswith("remove_one_friendly_"):
            if (
                marker.owner_player_id == action.player_id
                and marker.mission_id == policy.primary_mission_id
            ):
                candidates.append(marker.marker_id)
            continue
        if policy.effect_descriptor.startswith("remove_one_opponent_"):
            if marker.owner_player_id != action.player_id:
                candidates.append(marker.marker_id)
            continue
        raise GameLifecycleError("Sensor Sweep completion policy is unsupported.")
    return tuple(sorted(candidates))


def _validate_sensor_start_policy(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    start_event: EventRecord,
    event_index_by_id: dict[str, int],
) -> None:
    if policy.effect_descriptor not in _SENSOR_EFFECTS:
        return
    if policy.use_limit != "once_per_turn":
        raise GameLifecycleError("Sensor Sweep start-policy use limit drifted.")
    if (
        len(
            _sensor_marker_ids_at_start(
                state=state,
                action=action,
                policy=policy,
                start_event=start_event,
                event_index_by_id=event_index_by_id,
            )
        )
        <= 1
    ):
        raise GameLifecycleError(
            "Sensor Sweep started without more than one eligible operation marker."
        )


def _sensor_marker_ids_at_start(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    start_event: EventRecord,
    event_index_by_id: dict[str, int],
) -> tuple[str, ...]:
    start_order = event_index_by_id[start_event.event_id]
    candidates: list[str] = []
    for marker in state.primary_mission_progress_state.markers:
        if marker.marker_kind != _OPERATION_MARKER_KIND:
            continue
        creation_order = event_index_by_id.get(marker.source_event_id)
        if creation_order is None:
            raise GameLifecycleError("Sensor Sweep marker creation event is unknown.")
        removal_order = (
            None
            if marker.removal_event_id is None
            else event_index_by_id.get(marker.removal_event_id)
        )
        if marker.removal_event_id is not None and removal_order is None:
            raise GameLifecycleError("Sensor Sweep marker removal event is unknown.")
        if creation_order >= start_order or (
            removal_order is not None and removal_order <= start_order
        ):
            continue
        if policy.effect_descriptor.startswith("remove_one_friendly_"):
            if marker.owner_player_id == action.player_id:
                candidates.append(marker.marker_id)
            continue
        if policy.effect_descriptor.startswith("remove_one_opponent_"):
            if marker.owner_player_id != action.player_id:
                candidates.append(marker.marker_id)
            continue
        raise GameLifecycleError("Sensor Sweep start policy is unsupported.")
    return tuple(sorted(candidates))


def _validate_sensor_use_limits(
    *,
    actions: tuple[MissionActionState, ...],
    policies: dict[str, MissionActionPolicyDescriptor],
) -> None:
    uses: set[tuple[str, int, str]] = set()
    for action in actions:
        policy = policies[action.mission_action_id]
        if policy.effect_descriptor not in _SENSOR_EFFECTS:
            continue
        if policy.use_limit != "once_per_turn":
            raise GameLifecycleError("Sensor Sweep start-policy use limit drifted.")
        use = (
            action.player_id,
            action.battle_round_started,
            action.mission_action_id,
        )
        if use in uses:
            raise GameLifecycleError("Sensor Sweep once-per-turn use limit was exceeded.")
        uses.add(use)


def _sensor_effect_can_be_pending(*, state: GameState, action: MissionActionState) -> bool:
    return (
        state.stage is GameLifecycleStage.BATTLE
        and state.battle_round == action.completed_battle_round
        and state.active_player_id == action.player_id
        and state.current_battle_phase is not None
        and state.current_battle_phase.value == action.completed_phase
    )


def _validate_marker_action_references(
    *,
    state: GameState,
    action_ids: frozenset[str],
    policy_ids: frozenset[str],
    policy_source_ids: frozenset[str],
) -> None:
    for marker in state.primary_mission_progress_state.markers:
        if (
            marker.source_action_id is not None
            and marker.source_descriptor_id in policy_ids
            and marker.source_action_id not in action_ids
        ):
            raise GameLifecycleError("Primary Mission Action marker references an unknown action.")
        if (
            marker.removal_action_id is not None
            and marker.removal_source_id in policy_source_ids
            and marker.removal_action_id not in action_ids
        ):
            raise GameLifecycleError("Primary Mission Action removal references an unknown action.")


def _require_identity_owner(
    *, state: GameState, unit_instance_id: str, owner_player_id: str, label: str
) -> None:
    views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    if not views or {view.owner_player_id for view in views} != {owner_player_id}:
        raise GameLifecycleError(f"Primary Mission Action {label} owner drifted.")


def _nested_action_payload(record: EventRecord) -> dict[str, JsonValue]:
    payload = _object(record.payload, label="Primary Mission Action event")
    return _object(
        payload.get("mission_action_state"),
        label="Primary Mission Action event state",
    )


def _object(value: object, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{label} must be a JSON object.")
    return cast(dict[str, JsonValue], value)


__all__ = ("validate_primary_mission_action_integrity",)
