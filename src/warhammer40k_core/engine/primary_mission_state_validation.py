from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    PrimaryMissionChoiceRuleDescriptor,
    PrimaryMissionStateRuleDescriptor,
    mission_action_policy_for_id,
    primary_mission_choice_rule_for_id,
    primary_mission_choice_rules_for_mission,
    primary_mission_state_rule_for_id,
    primary_mission_state_rules_for_mission,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import mission_logical_terrain_areas
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_CONSECRATION_UNIT_DESIGNATED_EVENT,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PrimaryMissionActionCompletionEvidence,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    CONSECRATE_CHOICE_KIND,
    LOCATE_AND_DENY_CHOICE_KIND,
    PUNISHMENT_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choice_policy import (
    resolve_locate_and_deny_choice_policy,
    resolve_punishment_choice_policy,
)
from warhammer40k_core.engine.primary_mission_choices import (
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
)
from warhammer40k_core.engine.primary_mission_marker_integrity import (
    SURVEIL_MOVE_PROCESSED_EVENT,
    validate_surveil_marker_removal_events,
)
from warhammer40k_core.engine.primary_mission_sensor_integrity import (
    validate_sensor_sweep_choice_historical_policy,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryCondemnedSelectionState,
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
)
from warhammer40k_core.engine.scoring import PrimaryUnitDestructionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_record import DecisionRecord
    from warhammer40k_core.engine.decision_request import DecisionRequest
    from warhammer40k_core.engine.game_state import GameState


_MISSION_ACTION_COMPLETED_EVENT: Final = "mission_action_completed"
_MODEL_DESTROYED_EVENT: Final = "model_destroyed"

_ACTION_MARKER_EFFECTS: Final = frozenset(
    {
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
        "objective_becomes_decoy_if_action_unit_controls_target_at_turn_end",
        "objective_becomes_triangulated_if_action_unit_controls_target_at_turn_end",
        "objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end",
    }
)
_ACTION_MARKER_REMOVAL_EFFECTS: Final = frozenset(
    {
        "remove_one_friendly_operation_marker_if_action_unit_controls_selected_central_objective_at_turn_end",
        "remove_one_opponent_operation_marker_if_action_unit_controls_selected_central_objective_at_turn_end",
    }
)
_CHOICE_MARKER_EFFECTS: Final = frozenset(
    {"place_one_friendly_operation_marker_in_each_selected_terrain_area"}
)
_CONDEMNED_CHOICE_EFFECTS: Final = frozenset({"selected_enemy_units_become_condemned"})
_CONSECRATION_STATE_EFFECTS: Final = frozenset({"unit_becomes_consecration_unit"})
_CONSECRATION_CHOICE_EFFECTS: Final = frozenset(
    {"place_friendly_operation_marker_consecrate_objective_and_consume_unit_status"}
)
_STATE_MARKER_REMOVAL_EFFECTS: Final = frozenset(
    {"remove_all_opponent_operation_markers_from_each_in_range_objective"}
)

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


@dataclass(frozen=True, slots=True)
class _StateGraph:
    state: GameState
    game_id: str
    player_ids: frozenset[str]
    mission_setup: MissionSetup
    mission_by_player_id: dict[str, str]
    source_package_id: str
    objective_marker_ids: frozenset[str]
    logical_terrain_area_ids: frozenset[str]
    battlefield_terrain_feature_ids: frozenset[str]
    owner_by_rules_unit_id: dict[str, str]
    components_by_rules_unit_id: dict[str, tuple[str, ...]]
    actions_by_id: dict[str, MissionActionState]
    destructions_by_id: dict[str, PrimaryUnitDestructionState]


@dataclass(frozen=True, slots=True)
class _EventGraph:
    records: tuple[EventRecord, ...]
    by_id: dict[str, EventRecord]
    index_by_id: dict[str, int]


def validate_primary_mission_progress_state(
    state: GameState,
    *,
    event_records: tuple[EventRecord, ...] | None = None,
    decision_records: tuple[DecisionRecord, ...] | None = None,
    pending_decision_requests: tuple[DecisionRequest, ...] | None = None,
) -> PrimaryMissionProgressState:
    """Validate the persistent Primary-mission progress graph.

    ``event_records=None`` is the explicit GameState construction context, where
    only state-owned evidence is available. Supplying event records additionally
    authenticates every mutation edge and rejects omitted persisted progress;
    supplying decision records closes every nonautomatic player choice to its
    accepted request/result pair, while pending requests authenticate an
    in-progress Consecrate turn-end choice queue.
    """
    progress = state.primary_mission_progress_state
    if type(progress) is not PrimaryMissionProgressState:
        raise GameLifecycleError("GameState requires typed primary mission progress state.")
    has_progress = bool(
        progress.markers or progress.condemned_selections or progress.consecration_designations
    )
    graph = _state_graph(state=state, require_mission=has_progress)
    if graph is not None:
        _validate_state_progress(progress=progress, graph=graph)
    elif has_progress:
        raise GameLifecycleError("Primary mission progress requires mission battlefield state.")

    if event_records is not None:
        event_graph = _event_graph(event_records)
        if graph is None:
            _reject_orphan_progress_events(event_graph)
        else:
            _validate_event_progress(
                progress=progress,
                graph=graph,
                event_graph=event_graph,
            )
        from warhammer40k_core.engine.primary_mission_consecrate_integrity import (
            validate_primary_mission_consecrate_integrity,
        )

        validate_primary_mission_consecrate_integrity(
            state=state,
            event_records=event_graph.records,
            pending_decision_requests=pending_decision_requests,
        )
        if decision_records is not None:
            from warhammer40k_core.engine.primary_mission_decision_integrity import (
                validate_primary_mission_choice_decision_integrity,
            )

            validate_primary_mission_choice_decision_integrity(
                state=state,
                event_records=event_graph.records,
                decision_records=decision_records,
            )
    return progress


def _state_graph(*, state: GameState, require_mission: bool) -> _StateGraph | None:
    mission_setup = state.mission_setup
    battlefield_state = state.battlefield_state
    if mission_setup is None or battlefield_state is None:
        if require_mission:
            raise GameLifecycleError(
                "Primary mission progress requires MissionSetup and battlefield state."
            )
        return None
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Primary mission progress requires typed MissionSetup.")
    player_ids = frozenset(state.player_ids)
    mission_by_player_id = {
        assignment.player_id: assignment.primary_mission_id
        for assignment in mission_setup.primary_mission_assignments
    }
    if frozenset(mission_by_player_id) != player_ids:
        raise GameLifecycleError("Primary mission assignments drifted from game players.")
    owner_by_rules_unit_id, components_by_rules_unit_id = _rules_unit_identity_maps(state)
    actions_by_id = _unique_typed_map(
        state.mission_action_states,
        value_type=MissionActionState,
        id_attribute="action_id",
        label="Primary mission Action links",
    )
    destructions_by_id = _unique_typed_map(
        state.primary_unit_destruction_states,
        value_type=PrimaryUnitDestructionState,
        id_attribute="destruction_id",
        label="Primary mission destruction links",
    )
    return _StateGraph(
        state=state,
        game_id=state.game_id,
        player_ids=player_ids,
        mission_setup=mission_setup,
        mission_by_player_id=mission_by_player_id,
        source_package_id=mission_setup.source_id,
        objective_marker_ids=frozenset(
            marker.objective_marker_id for marker in mission_setup.objective_markers
        ),
        logical_terrain_area_ids=frozenset(
            area.logical_terrain_area_id for area in mission_logical_terrain_areas(mission_setup)
        ),
        battlefield_terrain_feature_ids=frozenset(
            feature.feature_id for feature in battlefield_state.terrain_features
        ),
        owner_by_rules_unit_id=owner_by_rules_unit_id,
        components_by_rules_unit_id=components_by_rules_unit_id,
        actions_by_id=actions_by_id,
        destructions_by_id=destructions_by_id,
    )


def _rules_unit_identity_maps(
    state: GameState,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    owner_by_id: dict[str, str] = {}
    components_by_id: dict[str, tuple[str, ...]] = {}
    for army in state.army_definitions:
        for unit in army.units:
            _record_rules_unit_identity(
                rules_unit_id=unit.unit_instance_id,
                owner_player_id=army.player_id,
                component_unit_instance_ids=(unit.unit_instance_id,),
                owner_by_id=owner_by_id,
                components_by_id=components_by_id,
            )
        for formation in army.attached_units:
            _record_rules_unit_identity(
                rules_unit_id=formation.attached_unit_instance_id,
                owner_player_id=army.player_id,
                component_unit_instance_ids=formation.component_unit_instance_ids,
                owner_by_id=owner_by_id,
                components_by_id=components_by_id,
            )
    for record in state.starting_attached_unit_records:
        _record_rules_unit_identity(
            rules_unit_id=record.attached_unit_instance_id,
            owner_player_id=record.player_id,
            component_unit_instance_ids=record.component_unit_instance_ids,
            owner_by_id=owner_by_id,
            components_by_id=components_by_id,
        )
    return owner_by_id, components_by_id


def _record_rules_unit_identity(
    *,
    rules_unit_id: str,
    owner_player_id: str,
    component_unit_instance_ids: tuple[str, ...],
    owner_by_id: dict[str, str],
    components_by_id: dict[str, tuple[str, ...]],
) -> None:
    components = tuple(sorted(component_unit_instance_ids))
    existing_owner = owner_by_id.get(rules_unit_id)
    existing_components = components_by_id.get(rules_unit_id)
    if existing_owner is not None and existing_owner != owner_player_id:
        raise GameLifecycleError("Primary mission rules-unit ownership is ambiguous.")
    if existing_components is not None and existing_components != components:
        raise GameLifecycleError("Primary mission rules-unit components are ambiguous.")
    owner_by_id[rules_unit_id] = owner_player_id
    components_by_id[rules_unit_id] = components


def _unique_typed_map[T](
    values: object,
    *,
    value_type: type[T],
    id_attribute: str,
    label: str,
) -> dict[str, T]:
    if not isinstance(values, list):
        raise GameLifecycleError(f"{label} must be a list.")
    resolved: dict[str, T] = {}
    for value in cast(list[object], values):
        if type(value) is not value_type:
            raise GameLifecycleError(f"{label} must contain typed values.")
        typed_value = value
        value_id = cast(str, getattr(typed_value, id_attribute))
        if value_id in resolved:
            raise GameLifecycleError(f"{label} must have unique identities.")
        resolved[value_id] = typed_value
    return resolved


def _validate_state_progress(
    *,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
) -> None:
    removal_action_ids: set[str] = set()
    for marker in progress.markers:
        _validate_marker(
            marker=marker,
            progress=progress,
            graph=graph,
        )
        if marker.removal_action_id is not None:
            if marker.removal_action_id in removal_action_ids:
                raise GameLifecycleError(
                    "One Primary Mission Action cannot remove multiple persistent markers."
                )
            removal_action_ids.add(marker.removal_action_id)
    for selection in progress.condemned_selections:
        _validate_condemned_selection(selection=selection, graph=graph)
    for designation in progress.consecration_designations:
        _validate_consecration_designation(
            designation=designation,
            graph=graph,
        )


def _validate_progress_identity(
    *,
    game_id: str,
    owner_player_id: str,
    mission_id: str,
    graph: _StateGraph,
    label: str,
) -> None:
    if game_id != graph.game_id:
        raise GameLifecycleError(f"{label} game_id drift.")
    assigned_mission = graph.mission_by_player_id.get(owner_player_id)
    if assigned_mission is None:
        raise GameLifecycleError(f"{label} owner is not a player in this game.")
    if mission_id != assigned_mission:
        raise GameLifecycleError(f"{label} mission drifted from its owner's Primary.")


def _validate_player_id(player_id: str | None, *, graph: _StateGraph, label: str) -> None:
    if player_id is not None and player_id not in graph.player_ids:
        raise GameLifecycleError(f"{label} is not a player in this game.")


def _validate_marker(
    *,
    marker: PrimaryMissionMarkerState,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
) -> None:
    _validate_progress_identity(
        game_id=marker.game_id,
        owner_player_id=marker.owner_player_id,
        mission_id=marker.mission_id,
        graph=graph,
        label="Primary mission marker",
    )
    _validate_player_id(
        marker.created_active_player_id,
        graph=graph,
        label="Primary mission marker creation player",
    )
    if marker.anchor_kind is MarkerAnchorKind.OBJECTIVE:
        if marker.objective_marker_id not in graph.objective_marker_ids:
            raise GameLifecycleError("Primary mission marker references an unknown objective.")
    elif marker.terrain_feature_id not in (
        graph.logical_terrain_area_ids | graph.battlefield_terrain_feature_ids
    ):
        raise GameLifecycleError("Primary mission marker references unknown battlefield terrain.")

    if marker.source_action_id is not None:
        _validate_action_created_marker(marker=marker, graph=graph)
    elif marker.source_designation_id is not None:
        _validate_designation_created_marker(
            marker=marker,
            progress=progress,
            graph=graph,
        )
    else:
        _validate_choice_created_marker(marker=marker, graph=graph)

    if marker.status is PrimaryMissionMarkerStatus.REMOVED:
        _validate_removed_marker(marker=marker, graph=graph)


def _validate_action_created_marker(
    *, marker: PrimaryMissionMarkerState, graph: _StateGraph
) -> None:
    if (
        marker.source_result_id is not None
        or marker.source_destruction_id is not None
        or marker.source_designation_id is not None
    ):
        raise GameLifecycleError("Action-created Primary marker provenance is inconsistent.")
    action = _linked_action(cast(str, marker.source_action_id), graph=graph)
    descriptor = _action_descriptor(
        descriptor_id=marker.source_descriptor_id,
        source_rule_id=marker.source_rule_id,
        mission_id=marker.mission_id,
        graph=graph,
    )
    if descriptor.effect_descriptor not in _ACTION_MARKER_EFFECTS:
        raise GameLifecycleError("Primary Mission Action does not create a persistent marker.")
    if (
        action.status is not MissionActionStatus.COMPLETED
        or action.mission_action_id != descriptor.mission_action_id
        or action.player_id != marker.owner_player_id
        or action.mission_id != marker.mission_id
        or action.scoring_source_id != marker.mission_id
        or marker.marker_kind != "operation"
        or marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE
        or action.target_id != marker.objective_marker_id
        or action.completed_battle_round != marker.created_battle_round
        or action.completed_phase != marker.created_phase
        or marker.created_active_player_id != action.player_id
    ):
        raise GameLifecycleError("Action-created Primary marker identity drift.")


def _validate_choice_created_marker(
    *, marker: PrimaryMissionMarkerState, graph: _StateGraph
) -> None:
    if marker.source_result_id is None or marker.source_destruction_id is not None:
        raise GameLifecycleError("Choice-created Primary marker provenance is incomplete.")
    descriptor = _choice_descriptor(
        descriptor_id=marker.source_descriptor_id,
        source_rule_id=marker.source_rule_id,
        mission_id=marker.mission_id,
        graph=graph,
    )
    if descriptor.effect_descriptor not in _CHOICE_MARKER_EFFECTS:
        raise GameLifecycleError("Primary mission choice does not create this marker family.")
    if (
        marker.marker_kind != "operation"
        or marker.anchor_kind is not MarkerAnchorKind.TERRAIN_FEATURE
        or marker.terrain_feature_id not in graph.logical_terrain_area_ids
        or marker.created_battle_round is not None
        or marker.created_phase is not None
        or marker.created_active_player_id is not None
    ):
        raise GameLifecycleError("Choice-created Primary marker identity drift.")


def _validate_designation_created_marker(
    *,
    marker: PrimaryMissionMarkerState,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
) -> None:
    if marker.source_result_id is None or marker.source_destruction_id is None:
        raise GameLifecycleError("Consecration marker provenance is incomplete.")
    designation = next(
        (
            value
            for value in progress.consecration_designations
            if value.designation_id == marker.source_designation_id
        ),
        None,
    )
    if designation is None:
        raise GameLifecycleError("Consecration marker references an unknown designation.")
    descriptor = _choice_descriptor(
        descriptor_id=marker.source_descriptor_id,
        source_rule_id=marker.source_rule_id,
        mission_id=marker.mission_id,
        graph=graph,
    )
    if descriptor.effect_descriptor not in _CONSECRATION_CHOICE_EFFECTS:
        raise GameLifecycleError("Primary mission choice does not create consecration markers.")
    if (
        marker.marker_kind != "operation"
        or marker.anchor_kind is not MarkerAnchorKind.OBJECTIVE
        or marker.source_destruction_id != designation.source_destruction_id
        or designation.status is not PrimaryConsecrationStatus.CONSUMED
        or marker.created_battle_round != designation.consumed_battle_round
        or marker.created_phase != designation.consumed_phase
        or marker.created_active_player_id != designation.consumed_active_player_id
        or designation.consumed_marker_id != marker.marker_id
        or designation.consumption_source_id != descriptor.source_id
        or designation.consumption_event_id != marker.source_event_id
        or designation.consumption_result_id != marker.source_result_id
    ):
        raise GameLifecycleError("Consecration marker identity drift.")


def _validate_removed_marker(*, marker: PrimaryMissionMarkerState, graph: _StateGraph) -> None:
    _validate_player_id(
        marker.removed_active_player_id,
        graph=graph,
        label="Primary mission marker removal player",
    )
    if (
        marker.created_battle_round is not None
        and marker.removed_battle_round is not None
        and marker.removed_battle_round < marker.created_battle_round
    ):
        raise GameLifecycleError("Primary mission marker removal predates its creation.")
    if marker.removal_action_id is not None:
        action = _linked_action(marker.removal_action_id, graph=graph)
        descriptor = _action_descriptor(
            descriptor_id=action.mission_action_id,
            source_rule_id=cast(str, marker.removal_source_id),
            mission_id=action.mission_id,
            graph=graph,
        )
        if descriptor.effect_descriptor not in _ACTION_MARKER_REMOVAL_EFFECTS:
            raise GameLifecycleError("Primary Mission Action cannot remove persistent markers.")
        if (
            action.status is not MissionActionStatus.COMPLETED
            or action.player_id != marker.removed_active_player_id
            or action.completed_battle_round != marker.removed_battle_round
            or action.completed_phase != marker.removed_phase
            or marker.removal_result_id is None
        ):
            raise GameLifecycleError("Action-removed Primary marker provenance drift.")
        return
    if marker.removal_result_id is not None:
        raise GameLifecycleError("State-rule marker removal cannot name a decision result.")
    state_descriptor = _state_descriptor_for_source(
        source_rule_id=cast(str, marker.removal_source_id),
        graph=graph,
    )
    if state_descriptor.effect_descriptor not in _STATE_MARKER_REMOVAL_EFFECTS:
        raise GameLifecycleError("Primary state rule cannot remove persistent markers.")


def _linked_action(action_id: str, *, graph: _StateGraph) -> MissionActionState:
    action = graph.actions_by_id.get(action_id)
    if action is None:
        raise GameLifecycleError("Primary mission marker references an unknown Action.")
    owner = graph.owner_by_rules_unit_id.get(action.unit_instance_id)
    if owner != action.player_id:
        raise GameLifecycleError("Primary Mission Action unit ownership drift.")
    if graph.mission_by_player_id.get(action.player_id) != action.mission_id:
        raise GameLifecycleError("Primary Mission Action mission assignment drift.")
    return action


def _action_descriptor(
    *,
    descriptor_id: str,
    source_rule_id: str,
    mission_id: str,
    graph: _StateGraph,
) -> MissionActionPolicyDescriptor:
    descriptor = mission_action_policy_for_id(descriptor_id)
    if (
        descriptor.source_package_id != graph.source_package_id
        or descriptor.source_id != source_rule_id
        or descriptor.primary_mission_id != mission_id
    ):
        raise GameLifecycleError("Primary Mission Action source identity drift.")
    return descriptor


def _choice_descriptor(
    *,
    descriptor_id: str,
    source_rule_id: str,
    mission_id: str,
    graph: _StateGraph,
) -> PrimaryMissionChoiceRuleDescriptor:
    descriptor = primary_mission_choice_rule_for_id(descriptor_id)
    if (
        descriptor.source_package_id != graph.source_package_id
        or descriptor.source_id != source_rule_id
        or descriptor.primary_mission_id != mission_id
    ):
        raise GameLifecycleError("Primary mission choice source identity drift.")
    return descriptor


def _state_descriptor(
    *,
    descriptor_id: str,
    source_rule_id: str,
    mission_id: str,
    graph: _StateGraph,
) -> PrimaryMissionStateRuleDescriptor:
    descriptor = primary_mission_state_rule_for_id(descriptor_id)
    if (
        descriptor.source_package_id != graph.source_package_id
        or descriptor.source_id != source_rule_id
        or descriptor.primary_mission_id != mission_id
    ):
        raise GameLifecycleError("Primary mission state-rule source identity drift.")
    return descriptor


def _state_descriptor_for_source(
    *, source_rule_id: str, graph: _StateGraph
) -> PrimaryMissionStateRuleDescriptor:
    matches = tuple(
        descriptor
        for mission_id in set(graph.mission_by_player_id.values())
        for descriptor in primary_mission_state_rules_for_mission(mission_id)
        if descriptor.source_package_id == graph.source_package_id
        and descriptor.source_id == source_rule_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Primary marker removal state rule is unknown or ambiguous.")
    return matches[0]


def _choice_descriptor_for_source(
    *,
    source_rule_id: str,
    mission_id: str,
    graph: _StateGraph,
) -> PrimaryMissionChoiceRuleDescriptor:
    matches = tuple(
        descriptor
        for descriptor in primary_mission_choice_rules_for_mission(mission_id)
        if descriptor.source_package_id == graph.source_package_id
        and descriptor.source_id == source_rule_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Primary mission choice source is unknown or ambiguous.")
    return matches[0]


def _validate_condemned_selection(
    *, selection: PrimaryCondemnedSelectionState, graph: _StateGraph
) -> None:
    _validate_progress_identity(
        game_id=selection.game_id,
        owner_player_id=selection.owner_player_id,
        mission_id=selection.mission_id,
        graph=graph,
        label="Primary condemned selection",
    )
    descriptor = _choice_descriptor(
        descriptor_id=selection.source_descriptor_id,
        source_rule_id=selection.source_rule_id,
        mission_id=selection.mission_id,
        graph=graph,
    )
    if descriptor.effect_descriptor not in _CONDEMNED_CHOICE_EFFECTS:
        raise GameLifecycleError("Primary mission choice does not condemn units.")
    expected_policy = (
        descriptor.fallback_target_policy
        if selection.used_fallback_candidates
        else descriptor.target_policy
    )
    if expected_policy is None or selection.candidate_policy_id != expected_policy:
        raise GameLifecycleError("Condemned candidate policy drift.")
    candidates = selection.candidate_rules_unit_instance_ids
    policy = resolve_punishment_choice_policy(
        state=graph.state,
        player_id=selection.owner_player_id,
        battle_round=selection.battle_round,
        candidate_presence_context="historical_restore",
    )
    if (
        candidates != policy.candidate_rules_unit_instance_ids
        or selection.candidate_evidence_ids != policy.candidate_evidence_ids
        or selection.used_fallback_candidates != policy.used_fallback_candidates
    ):
        raise GameLifecycleError("Condemned candidate reconstruction drifted.")
    expected_minimum = 1 if selection.used_fallback_candidates else descriptor.minimum_selections
    expected_maximum = (
        1
        if selection.used_fallback_candidates
        else min(descriptor.maximum_selections, len(candidates))
    )
    if not candidates:
        expected_minimum = expected_maximum = 0
    if (
        selection.minimum_selection_count != expected_minimum
        or selection.maximum_selection_count != expected_maximum
    ):
        raise GameLifecycleError("Condemned selection bounds drifted from source policy.")


def _validate_consecration_designation(
    *, designation: PrimaryConsecrationDesignationState, graph: _StateGraph
) -> None:
    _validate_progress_identity(
        game_id=designation.game_id,
        owner_player_id=designation.owner_player_id,
        mission_id=designation.mission_id,
        graph=graph,
        label="Primary consecration designation",
    )
    _validate_player_id(
        designation.created_active_player_id,
        graph=graph,
        label="Consecration creation player",
    )
    _validate_player_id(
        designation.last_resolved_active_player_id,
        graph=graph,
        label="Consecration resolution player",
    )
    _validate_player_id(
        designation.consumed_active_player_id,
        graph=graph,
        label="Consecration consumption player",
    )
    descriptor = _state_descriptor(
        descriptor_id=designation.source_descriptor_id,
        source_rule_id=designation.source_rule_id,
        mission_id=designation.mission_id,
        graph=graph,
    )
    if descriptor.effect_descriptor not in _CONSECRATION_STATE_EFFECTS:
        raise GameLifecycleError("Primary state rule does not designate consecration units.")
    destruction = graph.destructions_by_id.get(designation.source_destruction_id)
    if destruction is None:
        raise GameLifecycleError("Consecration designation references unknown destruction.")
    attribution = destruction.destruction_attribution
    source_rules_unit_id = (
        None if attribution is None else attribution.source_rules_unit_instance_id
    )
    expected_components = graph.components_by_rules_unit_id.get(designation.rules_unit_instance_id)
    if (
        destruction.game_id != designation.game_id
        or destruction.destroying_player_id != designation.owner_player_id
        or destruction.destroyed_player_id == designation.owner_player_id
        or destruction.source_model_destroyed_event_id != designation.source_event_id
        or destruction.battle_round != designation.created_battle_round
        or destruction.phase != designation.created_phase
        or destruction.active_player_id != designation.created_active_player_id
        or source_rules_unit_id is None
        or not _same_rules_unit_lineage(
            first_id=source_rules_unit_id,
            second_id=designation.rules_unit_instance_id,
            graph=graph,
        )
        or graph.owner_by_rules_unit_id.get(designation.rules_unit_instance_id)
        != designation.owner_player_id
        or expected_components != designation.component_unit_instance_ids
        or any(
            graph.owner_by_rules_unit_id.get(component_id) != designation.owner_player_id
            for component_id in designation.component_unit_instance_ids
        )
    ):
        raise GameLifecycleError("Consecration destruction attribution identity drift.")
    if (
        designation.consumed_battle_round is not None
        and designation.consumed_battle_round < designation.created_battle_round
    ):
        raise GameLifecycleError("Consecration consumption predates its designation.")
    if designation.status is PrimaryConsecrationStatus.CONSUMED:
        choice_descriptor = _choice_descriptor_for_source(
            source_rule_id=cast(str, designation.consumption_source_id),
            mission_id=designation.mission_id,
            graph=graph,
        )
        if choice_descriptor.effect_descriptor not in _CONSECRATION_CHOICE_EFFECTS:
            raise GameLifecycleError("Primary choice rule cannot consume consecration status.")


def _same_rules_unit_lineage(*, first_id: str, second_id: str, graph: _StateGraph) -> bool:
    first_components = graph.components_by_rules_unit_id.get(first_id)
    second_components = graph.components_by_rules_unit_id.get(second_id)
    return (
        first_components is not None
        and second_components is not None
        and bool(set(first_components).intersection(second_components))
    )


def _event_graph(event_records: object) -> _EventGraph:
    if type(event_records) is not tuple:
        raise GameLifecycleError("Primary mission event validation requires an event tuple.")
    records = cast(tuple[object, ...], event_records)
    if any(type(record) is not EventRecord for record in records):
        raise GameLifecycleError("Primary mission event validation requires typed events.")
    typed_records = cast(tuple[EventRecord, ...], records)
    by_id = {record.event_id: record for record in typed_records}
    if len(by_id) != len(typed_records):
        raise GameLifecycleError("Primary mission event IDs must be unique.")
    return _EventGraph(
        records=typed_records,
        by_id=by_id,
        index_by_id={record.event_id: index for index, record in enumerate(typed_records)},
    )


def _validate_event_progress(
    *,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
    event_graph: _EventGraph,
) -> None:
    creation_index_by_marker_id: dict[str, int] = {}
    for marker in progress.markers:
        creation_index = _validate_marker_creation_event(
            marker=marker,
            progress=progress,
            graph=graph,
            event_graph=event_graph,
        )
        creation_index_by_marker_id[marker.marker_id] = creation_index
    surveil_removal_index_by_marker_id = validate_surveil_marker_removal_events(
        state=graph.state,
        progress=progress,
        event_records=event_graph.records,
    )
    for marker in progress.markers:
        if marker.status is PrimaryMissionMarkerStatus.REMOVED:
            removal_index = _validate_marker_removal_event(
                marker=marker,
                progress=progress,
                graph=graph,
                event_graph=event_graph,
                creation_index_by_marker_id=creation_index_by_marker_id,
                surveil_removal_index_by_marker_id=surveil_removal_index_by_marker_id,
            )
            if removal_index <= creation_index_by_marker_id[marker.marker_id]:
                raise GameLifecycleError("Primary mission marker removal event predates creation.")
    for selection in progress.condemned_selections:
        _validate_condemned_selection_event(
            selection=selection,
            graph=graph,
            event_graph=event_graph,
        )
    for designation in progress.consecration_designations:
        _validate_consecration_events(
            designation=designation,
            progress=progress,
            graph=graph,
            event_graph=event_graph,
        )
    _validate_reverse_event_links(
        progress=progress,
        graph=graph,
        event_graph=event_graph,
    )


def _validate_marker_creation_event(
    *,
    marker: PrimaryMissionMarkerState,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
    event_graph: _EventGraph,
) -> int:
    creation_payload = _marker_creation_snapshot(marker).to_payload()
    if marker.source_action_id is not None:
        action = _linked_action(marker.source_action_id, graph=graph)
        expected_payload: dict[str, JsonValue] = {
            "game_id": marker.game_id,
            "player_id": marker.owner_player_id,
            "battle_round": cast(int, marker.created_battle_round),
            "phase": cast(str, marker.created_phase),
            "mission_action_id": action.mission_action_id,
            "action_id": action.action_id,
            "mission_action_state": cast(dict[str, JsonValue], action.to_payload()),
            "primary_mission_marker": cast(dict[str, JsonValue], creation_payload),
            "source_id": marker.source_rule_id,
        }
        matches: list[EventRecord] = []
        for record in event_graph.records:
            if record.event_type != _MISSION_ACTION_COMPLETED_EVENT or not isinstance(
                record.payload, dict
            ):
                continue
            actual_payload = dict(record.payload)
            raw_completion_evidence = actual_payload.pop(
                PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
                None,
            )
            if actual_payload != expected_payload:
                continue
            PrimaryMissionActionCompletionEvidence.from_payload(raw_completion_evidence)
            matches.append(record)
        if len(matches) != 1:
            raise GameLifecycleError("Action-created Primary marker requires one completion event.")
        return event_graph.index_by_id[matches[0].event_id]

    event, payload, choice = _choice_event(
        event_id=marker.source_event_id,
        graph=graph,
        event_graph=event_graph,
    )
    created_markers = _payload_list(payload.get("created_markers"), label="created_markers")
    if created_markers.count(cast(JsonValue, creation_payload)) != 1:
        raise GameLifecycleError("Primary marker creation event payload drift.")
    if payload.get("result_id") != marker.source_result_id:
        raise GameLifecycleError("Primary marker creation result provenance drift.")
    if marker.source_designation_id is None:
        if (
            choice.choice_kind != LOCATE_AND_DENY_CHOICE_KIND
            or choice.player_id != marker.owner_player_id
            or choice.primary_mission_id != marker.mission_id
            or choice.source_descriptor_id != marker.source_descriptor_id
            or choice.source_rule_id != marker.source_rule_id
            or choice.subject_id is not None
            or choice.source_action_id is not None
            or choice.selected_target_ids.count(cast(str, marker.terrain_feature_id)) != 1
        ):
            raise GameLifecycleError("Primary marker creation choice identity drift.")
    else:
        designation = next(
            value
            for value in progress.consecration_designations
            if value.designation_id == marker.source_designation_id
        )
        _validate_consecration_choice(
            choice=choice,
            designation=designation,
            selected_objective_id=marker.objective_marker_id,
            graph=graph,
        )
    return event_graph.index_by_id[event.event_id]


def _validate_marker_removal_event(
    *,
    marker: PrimaryMissionMarkerState,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
    event_graph: _EventGraph,
    creation_index_by_marker_id: dict[str, int],
    surveil_removal_index_by_marker_id: dict[str, int],
) -> int:
    removal_event_id = cast(str, marker.removal_event_id)
    if marker.removal_action_id is not None:
        event, payload, choice = _choice_event(
            event_id=removal_event_id,
            graph=graph,
            event_graph=event_graph,
        )
        action = _linked_action(marker.removal_action_id, graph=graph)
        descriptor = _action_descriptor(
            descriptor_id=action.mission_action_id,
            source_rule_id=cast(str, marker.removal_source_id),
            mission_id=action.mission_id,
            graph=graph,
        )
        validate_sensor_sweep_choice_historical_policy(
            state=graph.state,
            progress=progress,
            marker=marker,
            action=action,
            descriptor=descriptor,
            choice=choice,
            choice_event=event,
            choice_event_payload=payload,
            event_records=event_graph.records,
            event_index_by_id=event_graph.index_by_id,
            creation_index_by_marker_id=creation_index_by_marker_id,
        )
        return event_graph.index_by_id[event.event_id]

    processed_index = surveil_removal_index_by_marker_id.get(marker.marker_id)
    if processed_index is None:
        raise GameLifecycleError("State-removed Primary marker requires one processed event.")
    return processed_index


def _validate_condemned_selection_event(
    *,
    selection: PrimaryCondemnedSelectionState,
    graph: _StateGraph,
    event_graph: _EventGraph,
) -> None:
    _event, payload, choice = _choice_event(
        event_id=selection.source_event_id,
        graph=graph,
        event_graph=event_graph,
    )
    if (
        choice.choice_kind != PUNISHMENT_CHOICE_KIND
        or choice.player_id != selection.owner_player_id
        or choice.primary_mission_id != selection.mission_id
        or choice.source_descriptor_id != selection.source_descriptor_id
        or choice.source_rule_id != selection.source_rule_id
        or choice.battle_round != selection.battle_round
        or choice.subject_id is not None
        or choice.source_action_id is not None
        or choice.legal_target_ids != selection.candidate_rules_unit_instance_ids
        or choice.selected_target_ids != selection.selected_rules_unit_instance_ids
        or choice.evidence_ids != selection.candidate_evidence_ids
        or choice.used_fallback_candidates != selection.used_fallback_candidates
        or payload.get("request_id") != selection.selection_request_id
        or payload.get("result_id") != selection.selection_result_id
        or payload.get("automatic") != (not selection.candidate_rules_unit_instance_ids)
        or payload.get("condemned_selection") != selection.to_payload()
    ):
        raise GameLifecycleError("Condemned selection event provenance drift.")


def _validate_consecration_events(
    *,
    designation: PrimaryConsecrationDesignationState,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
    event_graph: _EventGraph,
) -> None:
    source_event = _required_event(
        event_id=designation.source_event_id,
        event_graph=event_graph,
    )
    if source_event.event_type != _MODEL_DESTROYED_EVENT:
        raise GameLifecycleError("Consecration designation source is not model_destroyed.")
    initial = _initial_designation_snapshot(designation)
    expected_payload: dict[str, JsonValue] = {
        "game_id": designation.game_id,
        "battle_round": designation.created_battle_round,
        "active_player_id": designation.created_active_player_id,
        "phase": designation.created_phase,
        "player_id": designation.owner_player_id,
        "source_destruction_id": designation.source_destruction_id,
        "primary_consecration_designation_state": cast(dict[str, JsonValue], initial.to_payload()),
        "source_id": designation.source_rule_id,
    }
    designation_events = tuple(
        record
        for record in event_graph.records
        if record.event_type == PRIMARY_CONSECRATION_UNIT_DESIGNATED_EVENT
        and record.payload == expected_payload
    )
    if len(designation_events) != 1:
        raise GameLifecycleError("Consecration designation requires one recorded event.")
    designation_index = event_graph.index_by_id[designation_events[0].event_id]
    if designation_index <= event_graph.index_by_id[source_event.event_id]:
        raise GameLifecycleError("Consecration designation event predates destruction.")

    if designation.last_resolution_event_id is not None:
        event, payload, choice = _choice_event(
            event_id=designation.last_resolution_event_id,
            graph=graph,
            event_graph=event_graph,
        )
        snapshot = _last_resolution_designation_snapshot(designation)
        _validate_consecration_choice(
            choice=choice,
            designation=designation,
            selected_objective_id=None,
            graph=graph,
        )
        if (
            payload.get("result_id") != designation.last_resolution_result_id
            or payload.get("updated_designation") != snapshot.to_payload()
            or event_graph.index_by_id[event.event_id] <= designation_index
        ):
            raise GameLifecycleError("Consecration resolution event provenance drift.")

    if designation.status is PrimaryConsecrationStatus.CONSUMED:
        event, payload, choice = _choice_event(
            event_id=cast(str, designation.consumption_event_id),
            graph=graph,
            event_graph=event_graph,
        )
        marker = next(
            value for value in progress.markers if value.marker_id == designation.consumed_marker_id
        )
        _validate_consecration_choice(
            choice=choice,
            designation=designation,
            selected_objective_id=marker.objective_marker_id,
            graph=graph,
        )
        if (
            payload.get("result_id") != designation.consumption_result_id
            or payload.get("updated_designation") != designation.to_payload()
            or event_graph.index_by_id[event.event_id] <= designation_index
        ):
            raise GameLifecycleError("Consecration consumption event provenance drift.")


def _validate_consecration_choice(
    *,
    choice: PrimaryMissionChoiceData,
    designation: PrimaryConsecrationDesignationState,
    selected_objective_id: str | None,
    graph: _StateGraph,
) -> None:
    descriptors = tuple(
        descriptor
        for descriptor in primary_mission_choice_rules_for_mission(designation.mission_id)
        if descriptor.source_package_id == graph.source_package_id
        and descriptor.effect_descriptor in _CONSECRATION_CHOICE_EFFECTS
    )
    if len(descriptors) != 1:
        raise GameLifecycleError("Consecration choice descriptor is unknown or ambiguous.")
    descriptor = descriptors[0]
    expected_selected_ids = () if selected_objective_id is None else (selected_objective_id,)
    if (
        choice.choice_kind != CONSECRATE_CHOICE_KIND
        or choice.player_id != designation.owner_player_id
        or choice.primary_mission_id != designation.mission_id
        or choice.source_descriptor_id != descriptor.choice_rule_id
        or choice.source_rule_id != descriptor.source_id
        or choice.subject_id != designation.designation_id
        or choice.source_action_id is not None
        or choice.selected_target_ids != expected_selected_ids
    ):
        raise GameLifecycleError("Consecration choice identity drift.")


def _choice_event(
    *,
    event_id: str,
    graph: _StateGraph,
    event_graph: _EventGraph,
) -> tuple[EventRecord, dict[str, JsonValue], PrimaryMissionChoiceData]:
    event = _required_event(event_id=event_id, event_graph=event_graph)
    if event.event_type != PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
        raise GameLifecycleError("Primary mission choice link references the wrong event type.")
    payload = _event_payload(event, label="Primary mission choice event")
    if frozenset(payload) != _CHOICE_EVENT_KEYS:
        raise GameLifecycleError("Primary mission choice event payload fields drifted.")
    choice = PrimaryMissionChoiceData.from_payload(payload.get("choice"))
    if choice.game_id != graph.game_id:
        raise GameLifecycleError("Primary mission choice event game identity drift.")
    return event, payload, choice


def _required_event(*, event_id: str, event_graph: _EventGraph) -> EventRecord:
    event = event_graph.by_id.get(event_id)
    if event is None:
        raise GameLifecycleError("Primary mission progress references an unknown event.")
    return event


def _event_payload(record: EventRecord, *, label: str) -> dict[str, JsonValue]:
    if not isinstance(record.payload, dict):
        raise GameLifecycleError(f"{label} payload must be an object.")
    return record.payload


def _payload_list(value: JsonValue | None, *, label: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise GameLifecycleError(f"Primary mission event {label} must be a list.")
    return value


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


def _last_resolution_designation_snapshot(
    designation: PrimaryConsecrationDesignationState,
) -> PrimaryConsecrationDesignationState:
    return replace(
        designation,
        status=PrimaryConsecrationStatus.ACTIVE,
        consumed_marker_id=None,
        consumed_battle_round=None,
        consumed_phase=None,
        consumed_active_player_id=None,
        consumption_source_id=None,
        consumption_event_id=None,
        consumption_result_id=None,
    )


def _validate_reverse_event_links(
    *,
    progress: PrimaryMissionProgressState,
    graph: _StateGraph,
    event_graph: _EventGraph,
) -> None:
    markers_by_id = {marker.marker_id: marker for marker in progress.markers}
    selections_by_id = {
        selection.selection_id: selection for selection in progress.condemned_selections
    }
    designations_by_id = {
        designation.designation_id: designation
        for designation in progress.consecration_designations
    }
    for event in event_graph.records:
        if event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
            _validate_choice_event_reverse_links(
                event=event,
                graph=graph,
                markers_by_id=markers_by_id,
                selections_by_id=selections_by_id,
                designations_by_id=designations_by_id,
            )
        elif event.event_type == _MISSION_ACTION_COMPLETED_EVENT:
            _validate_action_event_reverse_marker(event=event, markers_by_id=markers_by_id)
        elif event.event_type == PRIMARY_CONSECRATION_UNIT_DESIGNATED_EVENT:
            payload = _event_payload(event, label="Consecration designation event")
            raw = payload.get("primary_consecration_designation_state")
            designation = PrimaryConsecrationDesignationState.from_payload(raw)
            current = designations_by_id.get(designation.designation_id)
            if current is None or _initial_designation_snapshot(current) != designation:
                raise GameLifecycleError(
                    "Consecration designation event references omitted or drifted state."
                )
        elif event.event_type == SURVEIL_MOVE_PROCESSED_EVENT:
            payload = _event_payload(event, label="Surveil marker-removal event")
            for raw in _payload_list(
                payload.get("removed_primary_mission_markers"),
                label="removed_primary_mission_markers",
            ):
                marker = PrimaryMissionMarkerState.from_payload(raw)
                if markers_by_id.get(marker.marker_id) != marker:
                    raise GameLifecycleError(
                        "Processed marker-removal event references omitted or drifted state."
                    )


def _validate_choice_event_reverse_links(
    *,
    event: EventRecord,
    graph: _StateGraph,
    markers_by_id: dict[str, PrimaryMissionMarkerState],
    selections_by_id: dict[str, PrimaryCondemnedSelectionState],
    designations_by_id: dict[str, PrimaryConsecrationDesignationState],
) -> None:
    _event, payload, choice = _choice_event(
        event_id=event.event_id,
        graph=graph,
        event_graph=_EventGraph(
            records=(event,),
            by_id={event.event_id: event},
            index_by_id={event.event_id: 0},
        ),
    )
    if choice.choice_kind == LOCATE_AND_DENY_CHOICE_KIND:
        _validate_locate_choice_event(
            choice=choice,
            payload=payload,
            event_id=event.event_id,
            graph=graph,
        )
    for raw in _payload_list(payload.get("created_markers"), label="created_markers"):
        marker = PrimaryMissionMarkerState.from_payload(raw)
        current = markers_by_id.get(marker.marker_id)
        if current is None or _marker_creation_snapshot(current) != marker:
            raise GameLifecycleError(
                "Primary choice event references omitted or drifted marker state."
            )
    raw_selection = payload.get("condemned_selection")
    if raw_selection is not None:
        selection = PrimaryCondemnedSelectionState.from_payload(raw_selection)
        if selections_by_id.get(selection.selection_id) != selection:
            raise GameLifecycleError(
                "Primary choice event references omitted or drifted condemned state."
            )
    raw_designation = payload.get("updated_designation")
    if raw_designation is not None:
        designation = PrimaryConsecrationDesignationState.from_payload(raw_designation)
        current_designation = designations_by_id.get(designation.designation_id)
        if current_designation is None:
            raise GameLifecycleError("Primary choice event references omitted designation state.")
        if designation.status is PrimaryConsecrationStatus.CONSUMED:
            if current_designation != designation:
                raise GameLifecycleError("Consumed consecration event state drift.")
        elif designation.last_resolution_event_id != event.event_id:
            raise GameLifecycleError("Consecration resolution event linkage drift.")
    raw_removed_marker = payload.get("removed_marker")
    if raw_removed_marker is not None:
        marker = PrimaryMissionMarkerState.from_payload(raw_removed_marker)
        if markers_by_id.get(marker.marker_id) != marker:
            raise GameLifecycleError(
                "Primary choice event references omitted or drifted removed marker."
            )


def _validate_locate_choice_event(
    *,
    choice: PrimaryMissionChoiceData,
    payload: dict[str, JsonValue],
    event_id: str,
    graph: _StateGraph,
) -> None:
    descriptor = _choice_descriptor(
        descriptor_id=choice.source_descriptor_id,
        source_rule_id=choice.source_rule_id,
        mission_id=choice.primary_mission_id,
        graph=graph,
    )
    policy = resolve_locate_and_deny_choice_policy(
        mission_setup=graph.mission_setup,
        player_id=choice.player_id,
        maximum_selections=descriptor.maximum_selections,
    )
    markers = tuple(
        PrimaryMissionMarkerState.from_payload(raw)
        for raw in _payload_list(payload.get("created_markers"), label="created_markers")
    )
    result_id = payload.get("result_id")
    if (
        descriptor.effect_descriptor not in _CHOICE_MARKER_EFFECTS
        or choice.game_id != graph.game_id
        or graph.mission_by_player_id.get(choice.player_id) != descriptor.primary_mission_id
        or choice.battle_round is not None
        or choice.phase is not None
        or choice.subject_id is not None
        or choice.source_action_id is not None
        or choice.legal_target_ids != policy.eligible_terrain_area_ids
        or choice.evidence_ids != policy.evidence_terrain_area_ids
        or choice.used_fallback_candidates
        or len(choice.selected_target_ids) != policy.selection_count
        or tuple(marker.terrain_feature_id for marker in markers) != choice.selected_target_ids
        or type(result_id) is not str
    ):
        raise GameLifecycleError("Locate and Deny choice policy reconstruction drifted.")
    if any(
        marker.game_id != graph.game_id
        or marker.owner_player_id != choice.player_id
        or marker.mission_id != descriptor.primary_mission_id
        or marker.source_rule_id != descriptor.source_id
        or marker.source_descriptor_id != descriptor.choice_rule_id
        or marker.marker_kind != "operation"
        or marker.anchor_kind is not MarkerAnchorKind.TERRAIN_FEATURE
        or marker.objective_marker_id is not None
        or marker.created_battle_round is not None
        or marker.created_phase is not None
        or marker.created_active_player_id is not None
        or marker.source_event_id != event_id
        or marker.source_result_id != result_id
        or marker.source_action_id is not None
        or marker.source_destruction_id is not None
        or marker.source_designation_id is not None
        or marker.status is not PrimaryMissionMarkerStatus.ACTIVE
        for marker in markers
    ):
        raise GameLifecycleError("Locate and Deny marker set reconstruction drifted.")


def _validate_action_event_reverse_marker(
    *, event: EventRecord, markers_by_id: dict[str, PrimaryMissionMarkerState]
) -> None:
    if not isinstance(event.payload, dict) or "primary_mission_marker" not in event.payload:
        return
    raw_marker = event.payload.get("primary_mission_marker")
    if raw_marker is None:
        return
    marker = PrimaryMissionMarkerState.from_payload(raw_marker)
    current = markers_by_id.get(marker.marker_id)
    if current is None or _marker_creation_snapshot(current) != marker:
        raise GameLifecycleError(
            "Mission Action completion event references omitted or drifted Primary marker."
        )


def _reject_orphan_progress_events(event_graph: _EventGraph) -> None:
    for event in event_graph.records:
        if event.event_type in {
            PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
            PRIMARY_CONSECRATION_UNIT_DESIGNATED_EVENT,
            SURVEIL_MOVE_PROCESSED_EVENT,
        }:
            raise GameLifecycleError(
                "Primary mission mutation event requires persisted mission progress."
            )
        if (
            event.event_type == _MISSION_ACTION_COMPLETED_EVENT
            and isinstance(event.payload, dict)
            and event.payload.get("primary_mission_marker") is not None
        ):
            raise GameLifecycleError(
                "Primary marker completion event requires persisted marker state."
            )


__all__ = ("validate_primary_mission_progress_state",)
