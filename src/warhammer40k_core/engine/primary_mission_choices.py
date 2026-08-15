from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    PrimaryMissionChoiceRuleDescriptor,
    mission_action_policy_for_id,
    primary_mission_choice_rule_for_id,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    CONSECRATE_CHOICE_KIND,
    LOCATE_AND_DENY_CHOICE_KIND,
    PUNISHMENT_CHOICE_KIND,
    SENSOR_SWEEP_CHOICE_KIND,
    PrimaryMissionChoiceData,
    PrimaryMissionChoicePayload,
)
from warhammer40k_core.engine.primary_mission_choice_policy import (
    resolve_locate_and_deny_choice_policy,
    resolve_punishment_choice_policy,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryCondemnedSelectionState,
    PrimaryConsecrationDesignationState,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    is_consecrated_objective_marker,
    primary_condemned_selection_id,
    primary_mission_marker_id,
)
from warhammer40k_core.engine.primary_scoring_conditions import home_objective_ids
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    current_rules_unit_views_for_identity,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.start_battle_hooks import (
    StartBattleHookBinding,
    StartBattleRequestContext,
    StartBattleResultContext,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE: Final = "select_primary_mission_choice"
PRIMARY_MISSION_CHOICE_RESOLVED_EVENT: Final = "primary_mission_choice_resolved"

LOCATE_AND_DENY_CHOICE_RULE_ID: Final = "locate-and-deny-operation-marker-setup"
PUNISHMENT_CHOICE_RULE_ID: Final = "punishment-condemn-enemy-units"
CONSECRATE_CHOICE_RULE_ID: Final = "consecrate-objective-at-turn-end"
SENSOR_SWEEP_LOCATE_ACTION_ID: Final = "sensor-sweep-locate-and-deny"
SENSOR_SWEEP_EXTRACT_ACTION_ID: Final = "sensor-sweep-extract-relic"

PRIMARY_OPERATION_MARKER_KIND: Final = "operation"

_LOCATE_HOOK_ID: Final = "primary-mission-choice:locate-and-deny:start-battle"
_LOCATE_REQUEST_PRIORITY: Final = 50
_EVENT_PAYLOAD_KEYS: Final = (
    "choice",
    "request_id",
    "result_id",
    "selected_option_id",
    "automatic",
    "created_markers",
    "condemned_selection",
    "updated_designation",
    "removed_marker",
)


def locate_and_deny_start_battle_binding() -> StartBattleHookBinding:
    descriptor = _locate_descriptor()
    return StartBattleHookBinding(
        hook_id=_LOCATE_HOOK_ID,
        source_id=descriptor.source_id,
        request_handler=_locate_start_battle_request_handler,
        result_handler=_locate_start_battle_result_handler,
        request_priority=_LOCATE_REQUEST_PRIORITY,
    )


def locate_and_deny_setup_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str | None = None,
) -> DecisionRequest | None:
    _require_state_and_decisions(state=state, decisions=decisions)
    descriptor = _locate_descriptor()
    player_ids = _players_assigned_mission(state, descriptor.primary_mission_id)
    for player_id in player_ids:
        if _choice_event_exists(
            decisions=decisions,
            game_id=state.game_id,
            player_id=player_id,
            source_descriptor_id=descriptor.choice_rule_id,
        ):
            continue
        return _locate_request_for_player(
            state=state,
            player_id=player_id,
            descriptor=descriptor,
            request_id=request_id,
        )
    return None


def punishment_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str | None = None,
) -> DecisionRequest | None:
    _require_state_and_decisions(state=state, decisions=decisions)
    descriptor = _punishment_descriptor()
    if state.active_player_id is None or (
        _mission_setup(state).primary_mission_id_for_player(state.active_player_id)
        != descriptor.primary_mission_id
    ):
        return None
    player_id = _active_assigned_player(state, descriptor)
    if _condemned_selection_for_current_turn(state=state, descriptor=descriptor) is not None:
        return None
    choice = _punishment_choice_data(
        state=state,
        player_id=player_id,
        descriptor=descriptor,
    )
    if not choice.legal_target_ids:
        _record_automatic_empty_punishment(
            state=state,
            decisions=decisions,
            choice=choice,
            descriptor=descriptor,
        )
        return None
    selected_sets = tuple(
        subset
        for count in range(1, min(descriptor.maximum_selections, len(choice.legal_target_ids)) + 1)
        for subset in combinations(choice.legal_target_ids, count)
    )
    if choice.used_fallback_candidates:
        selected_sets = tuple(combinations(choice.legal_target_ids, 1))
    return _choice_request(
        state=state,
        request_id=request_id,
        choice=choice,
        selected_target_sets=selected_sets,
    )


def consecrate_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> DecisionRequest | None:
    _require_state_and_decisions(state=state, decisions=decisions)
    descriptor = _consecrate_descriptor()
    if state.active_player_id is None or (
        _mission_setup(state).primary_mission_id_for_player(state.active_player_id)
        != descriptor.primary_mission_id
    ):
        return None
    player_id = _active_assigned_player(state, descriptor)
    designation = _next_consecration_designation(
        state=state,
        player_id=player_id,
        descriptor=descriptor,
    )
    if designation is None:
        return None
    record = _current_objective_control_record(
        state=state,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    target_ids = _eligible_consecration_objective_ids(
        state=state,
        player_id=player_id,
        designation=designation,
        descriptor=descriptor,
        record=record,
    )
    choice = PrimaryMissionChoiceData(
        game_id=state.game_id,
        choice_kind=CONSECRATE_CHOICE_KIND,
        player_id=player_id,
        primary_mission_id=descriptor.primary_mission_id,
        source_descriptor_id=descriptor.choice_rule_id,
        source_rule_id=descriptor.source_id,
        battle_round=state.battle_round,
        phase=_current_phase(state),
        subject_id=designation.designation_id,
        source_action_id=None,
        legal_target_ids=target_ids,
        selected_target_ids=(),
        evidence_ids=(record.record_id,),
        used_fallback_candidates=False,
    )
    return _choice_request(
        state=state,
        request_id=request_id,
        choice=choice,
        selected_target_sets=(*((target_id,) for target_id in target_ids), ()),
    )


def sensor_sweep_marker_removal_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
    action_id: str,
    request_id: str | None = None,
) -> DecisionRequest | None:
    _require_state_and_decisions(state=state, decisions=decisions)
    action = _completed_sensor_sweep_action(state=state, action_id=action_id)
    descriptor = _sensor_sweep_descriptor(action)
    if any(
        marker.removal_action_id == action.action_id
        for marker in state.primary_mission_progress_state.markers
    ):
        return None
    markers = _sensor_sweep_markers(
        progress=state.primary_mission_progress_state,
        action=action,
        descriptor=descriptor,
    )
    if not markers:
        return None
    choice = PrimaryMissionChoiceData(
        game_id=state.game_id,
        choice_kind=SENSOR_SWEEP_CHOICE_KIND,
        player_id=action.player_id,
        primary_mission_id=descriptor.primary_mission_id,
        source_descriptor_id=descriptor.mission_action_id,
        source_rule_id=descriptor.source_id,
        battle_round=state.battle_round,
        phase=_current_phase(state),
        subject_id=None,
        source_action_id=action.action_id,
        legal_target_ids=tuple(marker.marker_id for marker in markers),
        selected_target_ids=(),
        evidence_ids=(action.action_id,),
        used_fallback_candidates=False,
    )
    return _choice_request(
        state=state,
        request_id=request_id,
        choice=choice,
        selected_target_sets=tuple((marker.marker_id,) for marker in markers),
    )


def invalid_primary_mission_choice_request_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> LifecycleStatus | None:
    _require_state_and_decisions(state=state, decisions=decisions)
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Primary mission choice drift validation requires a request.")
    if request.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
        return None
    try:
        authoritative = _authoritative_choice_request(
            state=state,
            decisions=decisions,
            request=request,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    except (DecisionError, GameLifecycleError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Primary mission choice request is stale or invalid.",
            payload={
                "invalid_reason": "primary_mission_choice_request_drift",
                "field": "authoritative_request",
                "detail": str(exc),
            },
        )
    if authoritative != request:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Primary mission choice request is stale or invalid.",
            payload={
                "invalid_reason": "primary_mission_choice_request_drift",
                "field": "authoritative_request",
                "detail": "Primary mission choice request drifted.",
            },
        )
    return None


def apply_primary_mission_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> bool:
    _require_state_and_decisions(state=state, decisions=decisions)
    if type(request) is not DecisionRequest or type(result) is not DecisionResult:
        raise GameLifecycleError("Primary mission choice application requires typed records.")
    if request.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
        return False
    invalid = invalid_primary_mission_choice_request_status(
        state=state,
        decisions=decisions,
        request=request,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if invalid is not None:
        raise GameLifecycleError(invalid.message)
    try:
        result.validate_for_request(request)
    except DecisionError as exc:
        raise GameLifecycleError("Primary mission choice result is invalid.") from exc
    choice = PrimaryMissionChoiceData.from_payload(result.payload)
    if choice.choice_kind == LOCATE_AND_DENY_CHOICE_KIND:
        _apply_locate_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            choice=choice,
        )
    elif choice.choice_kind == PUNISHMENT_CHOICE_KIND:
        _apply_punishment_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            choice=choice,
        )
    elif choice.choice_kind == CONSECRATE_CHOICE_KIND:
        _apply_consecrate_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            choice=choice,
        )
    elif choice.choice_kind == SENSOR_SWEEP_CHOICE_KIND:
        _apply_sensor_sweep_choice(
            state=state,
            decisions=decisions,
            request=request,
            result=result,
            choice=choice,
        )
    else:
        raise GameLifecycleError("Primary mission choice kind is unsupported.")
    return True


def _locate_start_battle_request_handler(
    context: StartBattleRequestContext,
) -> DecisionRequest | None:
    if type(context) is not StartBattleRequestContext:
        raise GameLifecycleError("Locate and Deny setup requires start-battle context.")
    return locate_and_deny_setup_choice_request(
        state=context.state,
        decisions=context.decisions,
        request_id=context.authoritative_request_id,
    )


def _locate_start_battle_result_handler(context: StartBattleResultContext) -> bool:
    if type(context) is not StartBattleResultContext:
        raise GameLifecycleError("Locate and Deny setup requires start-battle result context.")
    request = context.request
    if request.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
        return False
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    if choice.choice_kind != LOCATE_AND_DENY_CHOICE_KIND:
        return False
    return apply_primary_mission_choice(
        state=context.state,
        decisions=context.decisions,
        request=request,
        result=context.result,
    )


def _locate_request_for_player(
    *,
    state: GameState,
    player_id: str,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    request_id: str | None,
) -> DecisionRequest:
    mission_setup = _mission_setup(state)
    policy = resolve_locate_and_deny_choice_policy(
        mission_setup=mission_setup,
        player_id=player_id,
        maximum_selections=descriptor.maximum_selections,
    )
    selected_sets = tuple(combinations(policy.eligible_terrain_area_ids, policy.selection_count))
    choice = PrimaryMissionChoiceData(
        game_id=state.game_id,
        choice_kind=LOCATE_AND_DENY_CHOICE_KIND,
        player_id=player_id,
        primary_mission_id=descriptor.primary_mission_id,
        source_descriptor_id=descriptor.choice_rule_id,
        source_rule_id=descriptor.source_id,
        battle_round=None,
        phase=None,
        subject_id=None,
        source_action_id=None,
        legal_target_ids=policy.eligible_terrain_area_ids,
        selected_target_ids=(),
        evidence_ids=policy.evidence_terrain_area_ids,
        used_fallback_candidates=False,
    )
    return _choice_request(
        state=state,
        request_id=request_id,
        choice=choice,
        selected_target_sets=selected_sets,
    )


def _punishment_choice_data(
    *,
    state: GameState,
    player_id: str,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
) -> PrimaryMissionChoiceData:
    policy = resolve_punishment_choice_policy(
        state=state,
        player_id=player_id,
        battle_round=state.battle_round,
        candidate_presence_context="live_request",
    )
    return PrimaryMissionChoiceData(
        game_id=state.game_id,
        choice_kind=PUNISHMENT_CHOICE_KIND,
        player_id=player_id,
        primary_mission_id=descriptor.primary_mission_id,
        source_descriptor_id=descriptor.choice_rule_id,
        source_rule_id=descriptor.source_id,
        battle_round=state.battle_round,
        phase=_current_phase(state),
        subject_id=None,
        source_action_id=None,
        legal_target_ids=policy.candidate_rules_unit_instance_ids,
        selected_target_ids=(),
        evidence_ids=policy.candidate_evidence_ids,
        used_fallback_candidates=policy.used_fallback_candidates,
    )


def _authoritative_choice_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> DecisionRequest:
    choice = PrimaryMissionChoiceData.from_payload(request.payload)
    if choice.selected_target_ids:
        raise GameLifecycleError("Primary mission request payload cannot preselect targets.")
    if choice.choice_kind == LOCATE_AND_DENY_CHOICE_KIND:
        authoritative = locate_and_deny_setup_choice_request(
            state=state,
            decisions=decisions,
            request_id=request.request_id,
        )
    elif choice.choice_kind == PUNISHMENT_CHOICE_KIND:
        descriptor = _punishment_descriptor()
        player_id = _active_assigned_player(state, descriptor)
        if _condemned_selection_for_current_turn(state=state, descriptor=descriptor) is not None:
            authoritative = None
        else:
            current = _punishment_choice_data(
                state=state,
                player_id=player_id,
                descriptor=descriptor,
            )
            if not current.legal_target_ids:
                authoritative = None
            else:
                subsets = tuple(
                    subset
                    for count in range(
                        1,
                        min(descriptor.maximum_selections, len(current.legal_target_ids)) + 1,
                    )
                    for subset in combinations(current.legal_target_ids, count)
                )
                if current.used_fallback_candidates:
                    subsets = tuple(combinations(current.legal_target_ids, 1))
                authoritative = _choice_request(
                    state=state,
                    request_id=request.request_id,
                    choice=current,
                    selected_target_sets=subsets,
                )
    elif choice.choice_kind == CONSECRATE_CHOICE_KIND:
        authoritative = consecrate_choice_request(
            state=state,
            decisions=decisions,
            request_id=request.request_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    elif choice.choice_kind == SENSOR_SWEEP_CHOICE_KIND:
        if choice.source_action_id is None:
            raise GameLifecycleError("Sensor Sweep request is missing action provenance.")
        authoritative = sensor_sweep_marker_removal_choice_request(
            state=state,
            decisions=decisions,
            action_id=choice.source_action_id,
            request_id=request.request_id,
        )
    else:
        raise GameLifecycleError("Primary mission choice kind is unsupported.")
    if authoritative is None:
        raise GameLifecycleError("Primary mission choice no longer has an opportunity.")
    return authoritative


def _apply_locate_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    choice: PrimaryMissionChoiceData,
) -> None:
    descriptor = _locate_descriptor()
    _assert_choice_source(choice=choice, descriptor=descriptor)
    event_id = _next_event_id(decisions)
    progress = state.primary_mission_progress_state
    markers: list[PrimaryMissionMarkerState] = []
    for terrain_id in choice.selected_target_ids:
        marker = _new_marker(
            state=state,
            owner_player_id=choice.player_id,
            mission_id=choice.primary_mission_id,
            source_rule_id=choice.source_rule_id,
            source_descriptor_id=choice.source_descriptor_id,
            marker_kind=PRIMARY_OPERATION_MARKER_KIND,
            anchor_kind=MarkerAnchorKind.TERRAIN_FEATURE,
            objective_marker_id=None,
            terrain_feature_id=terrain_id,
            source_event_id=event_id,
            source_result_id=result.result_id,
        )
        progress = progress.add_marker(marker)
        markers.append(marker)
    _commit_choice_event(
        state=state,
        decisions=decisions,
        progress=progress,
        choice=choice,
        request=request,
        result=result,
        event_id=event_id,
        created_markers=tuple(markers),
    )


def _apply_punishment_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    choice: PrimaryMissionChoiceData,
) -> None:
    descriptor = _punishment_descriptor()
    _assert_choice_source(choice=choice, descriptor=descriptor)
    event_id = _next_event_id(decisions)
    selection = _condemned_selection(
        choice=choice,
        descriptor=descriptor,
        request_id=request.request_id,
        result_id=result.result_id,
        source_event_id=event_id,
    )
    progress = state.primary_mission_progress_state.add_condemned_selection(selection)
    _commit_choice_event(
        state=state,
        decisions=decisions,
        progress=progress,
        choice=choice,
        request=request,
        result=result,
        event_id=event_id,
        condemned_selection=selection,
    )


def _apply_consecrate_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    choice: PrimaryMissionChoiceData,
) -> None:
    descriptor = _consecrate_descriptor()
    _assert_choice_source(choice=choice, descriptor=descriptor)
    if choice.subject_id is None:
        raise GameLifecycleError("Consecrate choice is missing designation provenance.")
    designation = _designation_by_id(
        state.primary_mission_progress_state,
        designation_id=choice.subject_id,
    )
    event_id = _next_event_id(decisions)
    progress = state.primary_mission_progress_state
    marker: PrimaryMissionMarkerState | None = None
    if not choice.selected_target_ids:
        updated = designation.resolved_without_consumption(
            battle_round=state.battle_round,
            active_player_id=choice.player_id,
            event_id=event_id,
            result_id=result.result_id,
        )
    else:
        objective_id = choice.selected_target_ids[0]
        marker = _new_marker(
            state=state,
            owner_player_id=choice.player_id,
            mission_id=designation.mission_id,
            source_rule_id=descriptor.source_id,
            source_descriptor_id=descriptor.choice_rule_id,
            marker_kind=PRIMARY_OPERATION_MARKER_KIND,
            anchor_kind=MarkerAnchorKind.OBJECTIVE,
            objective_marker_id=objective_id,
            terrain_feature_id=None,
            source_event_id=event_id,
            source_result_id=result.result_id,
            source_destruction_id=designation.source_destruction_id,
            source_designation_id=designation.designation_id,
        )
        progress = progress.add_marker(marker)
        updated = designation.consumed(
            marker_id=marker.marker_id,
            battle_round=state.battle_round,
            phase=_current_phase(state),
            active_player_id=choice.player_id,
            source_id=descriptor.source_id,
            event_id=event_id,
            result_id=result.result_id,
        )
    progress = progress.replace_consecration_designation(updated)
    _commit_choice_event(
        state=state,
        decisions=decisions,
        progress=progress,
        choice=choice,
        request=request,
        result=result,
        event_id=event_id,
        created_markers=(() if marker is None else (marker,)),
        updated_designation=updated,
    )


def _apply_sensor_sweep_choice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    choice: PrimaryMissionChoiceData,
) -> None:
    if choice.source_action_id is None or len(choice.selected_target_ids) != 1:
        raise GameLifecycleError("Sensor Sweep choice payload is incomplete.")
    action = _completed_sensor_sweep_action(
        state=state,
        action_id=choice.source_action_id,
    )
    descriptor = _sensor_sweep_descriptor(action)
    _assert_action_choice_source(choice=choice, descriptor=descriptor)
    marker = _marker_by_id(
        state.primary_mission_progress_state,
        marker_id=choice.selected_target_ids[0],
    )
    event_id = _next_event_id(decisions)
    removed = marker.removed(
        battle_round=state.battle_round,
        phase=_current_phase(state),
        active_player_id=choice.player_id,
        source_id=descriptor.source_id,
        event_id=event_id,
        result_id=result.result_id,
        action_id=action.action_id,
    )
    progress = state.primary_mission_progress_state.replace_marker(removed)
    _commit_choice_event(
        state=state,
        decisions=decisions,
        progress=progress,
        choice=choice,
        request=request,
        result=result,
        event_id=event_id,
        removed_marker=removed,
    )


def _record_automatic_empty_punishment(
    *,
    state: GameState,
    decisions: DecisionController,
    choice: PrimaryMissionChoiceData,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
) -> None:
    event_id = _next_event_id(decisions)
    selection = _condemned_selection(
        choice=choice,
        descriptor=descriptor,
        request_id=None,
        result_id=None,
        source_event_id=event_id,
    )
    progress = state.primary_mission_progress_state.add_condemned_selection(selection)
    _commit_choice_event(
        state=state,
        decisions=decisions,
        progress=progress,
        choice=choice,
        request=None,
        result=None,
        event_id=event_id,
        condemned_selection=selection,
        automatic=True,
    )


def _condemned_selection(
    *,
    choice: PrimaryMissionChoiceData,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    request_id: str | None,
    result_id: str | None,
    source_event_id: str,
) -> PrimaryCondemnedSelectionState:
    if choice.used_fallback_candidates:
        minimum = maximum = 1
        policy_id = _required_optional_identifier(
            "Punishment fallback_target_policy",
            descriptor.fallback_target_policy,
        )
    elif choice.legal_target_ids:
        minimum = descriptor.minimum_selections
        maximum = min(descriptor.maximum_selections, len(choice.legal_target_ids))
        policy_id = descriptor.target_policy
    else:
        minimum = maximum = 0
        policy_id = descriptor.target_policy
    battle_round = _required_positive_int("Punishment battle_round", choice.battle_round)
    selection_id = primary_condemned_selection_id(
        game_id=choice.game_id,
        owner_player_id=choice.player_id,
        mission_id=choice.primary_mission_id,
        source_rule_id=choice.source_rule_id,
        source_descriptor_id=choice.source_descriptor_id,
        battle_round=battle_round,
        active_player_id=choice.player_id,
        candidate_policy_id=policy_id,
        candidate_rules_unit_instance_ids=choice.legal_target_ids,
        candidate_evidence_ids=choice.evidence_ids,
        selected_rules_unit_instance_ids=choice.selected_target_ids,
        minimum_selection_count=minimum,
        maximum_selection_count=maximum,
        used_fallback_candidates=choice.used_fallback_candidates,
        selection_request_id=request_id,
        selection_result_id=result_id,
        source_event_id=source_event_id,
    )
    return PrimaryCondemnedSelectionState(
        selection_id=selection_id,
        game_id=choice.game_id,
        owner_player_id=choice.player_id,
        mission_id=choice.primary_mission_id,
        source_rule_id=choice.source_rule_id,
        source_descriptor_id=choice.source_descriptor_id,
        battle_round=battle_round,
        active_player_id=choice.player_id,
        candidate_policy_id=policy_id,
        candidate_rules_unit_instance_ids=choice.legal_target_ids,
        candidate_evidence_ids=choice.evidence_ids,
        selected_rules_unit_instance_ids=choice.selected_target_ids,
        minimum_selection_count=minimum,
        maximum_selection_count=maximum,
        used_fallback_candidates=choice.used_fallback_candidates,
        selection_request_id=request_id,
        selection_result_id=result_id,
        source_event_id=source_event_id,
    )


def _new_marker(
    *,
    state: GameState,
    owner_player_id: str,
    mission_id: str,
    source_rule_id: str,
    source_descriptor_id: str,
    marker_kind: str,
    anchor_kind: MarkerAnchorKind,
    objective_marker_id: str | None,
    terrain_feature_id: str | None,
    source_event_id: str,
    source_result_id: str,
    source_destruction_id: str | None = None,
    source_designation_id: str | None = None,
) -> PrimaryMissionMarkerState:
    created_in_battle = state.stage is GameLifecycleStage.BATTLE
    created_battle_round = state.battle_round if created_in_battle else None
    created_phase = _current_phase(state) if created_in_battle else None
    created_active_player_id = state.active_player_id if created_in_battle else None
    marker_id = primary_mission_marker_id(
        game_id=state.game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        marker_kind=marker_kind,
        anchor_kind=anchor_kind,
        objective_marker_id=objective_marker_id,
        terrain_feature_id=terrain_feature_id,
        created_battle_round=created_battle_round,
        created_phase=created_phase,
        created_active_player_id=created_active_player_id,
        source_event_id=source_event_id,
        source_result_id=source_result_id,
        source_action_id=None,
        source_destruction_id=source_destruction_id,
        source_designation_id=source_designation_id,
    )
    return PrimaryMissionMarkerState(
        marker_id=marker_id,
        game_id=state.game_id,
        owner_player_id=owner_player_id,
        mission_id=mission_id,
        source_rule_id=source_rule_id,
        source_descriptor_id=source_descriptor_id,
        marker_kind=marker_kind,
        anchor_kind=anchor_kind,
        objective_marker_id=objective_marker_id,
        terrain_feature_id=terrain_feature_id,
        created_battle_round=created_battle_round,
        created_phase=created_phase,
        created_active_player_id=created_active_player_id,
        source_event_id=source_event_id,
        source_result_id=source_result_id,
        source_action_id=None,
        source_destruction_id=source_destruction_id,
        source_designation_id=source_designation_id,
    )


def _commit_choice_event(
    *,
    state: GameState,
    decisions: DecisionController,
    progress: PrimaryMissionProgressState,
    choice: PrimaryMissionChoiceData,
    request: DecisionRequest | None,
    result: DecisionResult | None,
    event_id: str,
    created_markers: tuple[PrimaryMissionMarkerState, ...] = (),
    condemned_selection: PrimaryCondemnedSelectionState | None = None,
    updated_designation: PrimaryConsecrationDesignationState | None = None,
    removed_marker: PrimaryMissionMarkerState | None = None,
    automatic: bool = False,
) -> None:
    payload = validate_json_value(
        {
            "choice": choice.to_payload(),
            "request_id": None if request is None else request.request_id,
            "result_id": None if result is None else result.result_id,
            "selected_option_id": None if result is None else result.selected_option_id,
            "automatic": automatic,
            "created_markers": [marker.to_payload() for marker in created_markers],
            "condemned_selection": (
                None if condemned_selection is None else condemned_selection.to_payload()
            ),
            "updated_designation": (
                None if updated_designation is None else updated_designation.to_payload()
            ),
            "removed_marker": None if removed_marker is None else removed_marker.to_payload(),
        }
    )
    event = decisions.event_log.append(PRIMARY_MISSION_CHOICE_RESOLVED_EVENT, payload)
    if event.event_id != event_id:
        raise GameLifecycleError("Primary mission choice event identity drift.")
    state.replace_primary_mission_progress_state(progress)


def _choice_request(
    *,
    state: GameState,
    request_id: str | None,
    choice: PrimaryMissionChoiceData,
    selected_target_sets: tuple[tuple[str, ...], ...],
) -> DecisionRequest:
    if not selected_target_sets:
        raise GameLifecycleError("Primary mission choice requires at least one finite option.")
    resolved_request_id = state.next_decision_request_id() if request_id is None else request_id
    return DecisionRequest(
        request_id=resolved_request_id,
        decision_type=SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
        actor_id=choice.player_id,
        payload=validate_json_value(choice.to_payload()),
        options=tuple(
            DecisionOption(
                option_id=_choice_option_id(choice=choice, selected_ids=selected_ids),
                label=_choice_option_label(choice=choice, selected_ids=selected_ids),
                payload=validate_json_value(
                    choice.with_selected_targets(selected_ids).to_payload()
                ),
            )
            for selected_ids in selected_target_sets
        ),
    )


def _choice_option_id(
    *,
    choice: PrimaryMissionChoiceData,
    selected_ids: tuple[str, ...],
) -> str:
    digest = canonical_payload_sha256(
        {
            "game_id": choice.game_id,
            "choice_kind": choice.choice_kind,
            "player_id": choice.player_id,
            "source_descriptor_id": choice.source_descriptor_id,
            "subject_id": choice.subject_id,
            "source_action_id": choice.source_action_id,
            "selected_target_ids": list(selected_ids),
        }
    )
    return f"primary-mission-choice:{digest}"


def _choice_option_label(
    *,
    choice: PrimaryMissionChoiceData,
    selected_ids: tuple[str, ...],
) -> str:
    if not selected_ids:
        return "Decline this choice"
    return f"Select {', '.join(selected_ids)}"


def _next_consecration_designation(
    *,
    state: GameState,
    player_id: str,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
) -> PrimaryConsecrationDesignationState | None:
    candidates = tuple(
        designation
        for designation in state.primary_mission_progress_state.consecration_designations
        if designation.owner_player_id == player_id
        and designation.mission_id == descriptor.primary_mission_id
        and designation.status is PrimaryConsecrationStatus.ACTIVE
        and not designation.was_resolved_for_turn(
            battle_round=state.battle_round,
            active_player_id=player_id,
        )
    )
    return None if not candidates else min(candidates, key=lambda value: value.designation_id)


def _eligible_consecration_objective_ids(
    *,
    state: GameState,
    player_id: str,
    designation: PrimaryConsecrationDesignationState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
    record: ObjectiveControlRecord,
) -> tuple[str, ...]:
    mission_setup = _mission_setup(state)
    excluded_ids = set(home_objective_ids(mission_setup, player_id=player_id))
    source_identity = (descriptor.source_id, descriptor.choice_rule_id)
    excluded_ids.update(
        marker.objective_marker_id
        for marker in state.primary_mission_progress_state.markers
        if is_consecrated_objective_marker(marker, source_identity)
        and marker.objective_marker_id is not None
    )
    views = current_rules_unit_views_for_identity(
        state=state,
        unit_instance_id=designation.rules_unit_instance_id,
    )
    return tuple(
        result.objective_id
        for result in record.results
        if result.objective_id not in excluded_ids
        and any(_result_has_rules_unit(result=result, view=view) for view in views)
    )


def _result_has_rules_unit(
    *,
    result: ObjectiveControlResult,
    view: RulesUnitView,
) -> bool:
    component_ids = set(view.component_unit_instance_ids)
    return any(
        contribution.player_id == view.owner_player_id
        and contribution.unit_instance_id in component_ids
        for contribution in result.contributors
    )


def _current_objective_control_record(
    *,
    state: GameState,
    timing: ObjectiveControlTiming,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    return resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=timing,
            phase=_current_phase(state),
            ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
            runtime_modifier_registry=runtime_modifier_registry,
        )
    )


def _completed_sensor_sweep_action(
    *,
    state: GameState,
    action_id: str,
) -> MissionActionState:
    requested_id = _identifier("Sensor Sweep action_id", action_id)
    matches = tuple(
        action for action in state.mission_action_states if action.action_id == requested_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Sensor Sweep action identity is unknown or ambiguous.")
    action = matches[0]
    if action.status is not MissionActionStatus.COMPLETED:
        raise GameLifecycleError("Sensor Sweep marker choice requires a completed action.")
    if action.completed_battle_round != state.battle_round:
        raise GameLifecycleError("Sensor Sweep completed action is stale.")
    return action


def _sensor_sweep_descriptor(action: MissionActionState) -> MissionActionPolicyDescriptor:
    if action.mission_action_id not in {
        SENSOR_SWEEP_LOCATE_ACTION_ID,
        SENSOR_SWEEP_EXTRACT_ACTION_ID,
    }:
        raise GameLifecycleError("Mission Action is not a supported Sensor Sweep.")
    descriptor = mission_action_policy_for_id(action.mission_action_id)
    if (
        action.mission_id != descriptor.primary_mission_id
        or action.scoring_source_id != descriptor.primary_mission_id
    ):
        raise GameLifecycleError("Sensor Sweep action source identity drift.")
    return descriptor


def _sensor_sweep_markers(
    *,
    progress: PrimaryMissionProgressState,
    action: MissionActionState,
    descriptor: MissionActionPolicyDescriptor,
) -> tuple[PrimaryMissionMarkerState, ...]:
    if descriptor.mission_action_id == SENSOR_SWEEP_LOCATE_ACTION_ID:
        return tuple(
            marker
            for marker in progress.markers
            if marker.status is PrimaryMissionMarkerStatus.ACTIVE
            and marker.marker_kind == PRIMARY_OPERATION_MARKER_KIND
            and marker.mission_id == descriptor.primary_mission_id
            and marker.owner_player_id == action.player_id
        )
    if descriptor.mission_action_id == SENSOR_SWEEP_EXTRACT_ACTION_ID:
        return tuple(
            marker
            for marker in progress.markers
            if marker.status is PrimaryMissionMarkerStatus.ACTIVE
            and marker.marker_kind == PRIMARY_OPERATION_MARKER_KIND
            and marker.owner_player_id != action.player_id
        )
    raise GameLifecycleError("Sensor Sweep marker policy is unsupported.")


def _condemned_selection_for_current_turn(
    *,
    state: GameState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
) -> PrimaryCondemnedSelectionState | None:
    matches = tuple(
        selection
        for selection in state.primary_mission_progress_state.condemned_selections
        if selection.owner_player_id == state.active_player_id
        and selection.mission_id == descriptor.primary_mission_id
        and selection.source_descriptor_id == descriptor.choice_rule_id
        and selection.battle_round == state.battle_round
    )
    if len(matches) > 1:
        raise GameLifecycleError("Punishment has duplicate current-turn selections.")
    return None if not matches else matches[0]


def _choice_event_exists(
    *,
    decisions: DecisionController,
    game_id: str,
    player_id: str,
    source_descriptor_id: str,
) -> bool:
    matches = 0
    for event in decisions.event_log.records:
        if event.event_type != PRIMARY_MISSION_CHOICE_RESOLVED_EVENT:
            continue
        raw = _payload_mapping(
            event.payload,
            label="Primary mission choice event",
            keys=_EVENT_PAYLOAD_KEYS,
        )
        choice = PrimaryMissionChoiceData.from_payload(raw["choice"])
        if (
            choice.game_id == game_id
            and choice.player_id == player_id
            and choice.source_descriptor_id == source_descriptor_id
        ):
            matches += 1
    if matches > 1:
        raise GameLifecycleError("Primary mission choice has duplicate resolution events.")
    return matches == 1


def _designation_by_id(
    progress: PrimaryMissionProgressState,
    *,
    designation_id: str,
) -> PrimaryConsecrationDesignationState:
    matches = tuple(
        designation
        for designation in progress.consecration_designations
        if designation.designation_id == designation_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Consecration designation identity is unknown or ambiguous.")
    return matches[0]


def _marker_by_id(
    progress: PrimaryMissionProgressState,
    *,
    marker_id: str,
) -> PrimaryMissionMarkerState:
    matches = tuple(marker for marker in progress.markers if marker.marker_id == marker_id)
    if len(matches) != 1:
        raise GameLifecycleError("Primary mission marker identity is unknown or ambiguous.")
    return matches[0]


def _assert_choice_source(
    *,
    choice: PrimaryMissionChoiceData,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
) -> None:
    if (
        choice.primary_mission_id != descriptor.primary_mission_id
        or choice.source_descriptor_id != descriptor.choice_rule_id
        or choice.source_rule_id != descriptor.source_id
    ):
        raise GameLifecycleError("Primary mission choice source identity drift.")


def _assert_action_choice_source(
    *,
    choice: PrimaryMissionChoiceData,
    descriptor: MissionActionPolicyDescriptor,
) -> None:
    if (
        choice.primary_mission_id != descriptor.primary_mission_id
        or choice.source_descriptor_id != descriptor.mission_action_id
        or choice.source_rule_id != descriptor.source_id
    ):
        raise GameLifecycleError("Sensor Sweep choice source identity drift.")


def _active_assigned_player(
    state: GameState,
    descriptor: PrimaryMissionChoiceRuleDescriptor,
) -> str:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Primary mission turn choice requires battle stage.")
    player_id = _required_optional_identifier(
        "Primary mission active_player_id",
        state.active_player_id,
    )
    mission_setup = _mission_setup(state)
    if mission_setup.primary_mission_id_for_player(player_id) != descriptor.primary_mission_id:
        raise GameLifecycleError("Active player is not assigned the required Primary mission.")
    return player_id


def _players_assigned_mission(state: GameState, mission_id: str) -> tuple[str, ...]:
    mission_setup = _mission_setup(state)
    return tuple(
        sorted(
            assignment.player_id
            for assignment in mission_setup.primary_mission_assignments
            if assignment.primary_mission_id == mission_id
        )
    )


def _mission_setup(state: GameState) -> MissionSetup:
    if state.mission_setup is None:
        raise GameLifecycleError("Primary mission choice requires MissionSetup.")
    return state.mission_setup


def _current_phase(state: GameState) -> str:
    if state.current_battle_phase is None:
        raise GameLifecycleError("Primary mission choice requires a battle phase.")
    return state.current_battle_phase.value


def _next_event_id(decisions: DecisionController) -> str:
    return f"event-{len(decisions.event_log.records) + 1:06d}"


def _locate_descriptor() -> PrimaryMissionChoiceRuleDescriptor:
    descriptor = primary_mission_choice_rule_for_id(LOCATE_AND_DENY_CHOICE_RULE_ID)
    if (
        descriptor.trigger_timing != "battle_start"
        or descriptor.target_policy != "terrain_area_outside_own_deployment_zone"
        or descriptor.selection_policy != "exactly_five_or_all_available_when_fewer"
        or descriptor.maximum_selections != 5
    ):
        raise GameLifecycleError("Locate and Deny choice descriptor drift.")
    return descriptor


def _punishment_descriptor() -> PrimaryMissionChoiceRuleDescriptor:
    descriptor = primary_mission_choice_rule_for_id(PUNISHMENT_CHOICE_RULE_ID)
    if (
        descriptor.trigger_timing != "own_turn_start"
        or descriptor.selection_policy
        != "one_to_three_or_exactly_one_fallback_when_no_primary_targets"
        or descriptor.minimum_selections != 1
        or descriptor.maximum_selections != 3
        or descriptor.fallback_target_policy != "enemy_battlefield_unit"
    ):
        raise GameLifecycleError("Punishment choice descriptor drift.")
    return descriptor


def _consecrate_descriptor() -> PrimaryMissionChoiceRuleDescriptor:
    descriptor = primary_mission_choice_rule_for_id(CONSECRATE_CHOICE_RULE_ID)
    if (
        descriptor.trigger_timing != "own_turn_end"
        or descriptor.subject_policy != "each_friendly_consecration_unit"
        or descriptor.selection_policy != "optional_up_to_one_per_subject"
        or descriptor.maximum_selections != 1
    ):
        raise GameLifecycleError("Consecrate choice descriptor drift.")
    return descriptor


def _require_state_and_decisions(
    *,
    state: GameState,
    decisions: DecisionController,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary mission choice requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Primary mission choice requires DecisionController.")


def _payload_mapping(
    payload: object,
    *,
    label: str,
    keys: tuple[str, ...],
) -> dict[str, object]:
    if type(payload) is not dict:
        raise GameLifecycleError(f"{label} payload must be an object.")
    raw = cast(dict[str, object], payload)
    missing = tuple(key for key in keys if key not in raw)
    if missing:
        raise GameLifecycleError(f"{label} payload is missing field: {missing[0]}.")
    unexpected = tuple(sorted(set(raw).difference(keys)))
    if unexpected:
        raise GameLifecycleError(f"{label} payload has unexpected field: {unexpected[0]}.")
    return raw


def _required_optional_identifier(label: str, value: object) -> str:
    if value is None:
        raise GameLifecycleError(f"{label} is required.")
    return _identifier(label, value)


def _required_positive_int(label: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise GameLifecycleError(f"{label} must be a positive integer.")
    return value


_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "CONSECRATE_CHOICE_KIND",
    "LOCATE_AND_DENY_CHOICE_KIND",
    "PRIMARY_MISSION_CHOICE_RESOLVED_EVENT",
    "PRIMARY_OPERATION_MARKER_KIND",
    "PUNISHMENT_CHOICE_KIND",
    "SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE",
    "SENSOR_SWEEP_CHOICE_KIND",
    "PrimaryMissionChoiceData",
    "PrimaryMissionChoicePayload",
    "apply_primary_mission_choice",
    "consecrate_choice_request",
    "invalid_primary_mission_choice_request_status",
    "locate_and_deny_setup_choice_request",
    "locate_and_deny_start_battle_binding",
    "punishment_choice_request",
    "sensor_sweep_marker_removal_choice_request",
)
