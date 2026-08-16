from __future__ import annotations

from dataclasses import replace
from itertools import combinations
from typing import TYPE_CHECKING, Final, cast

from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_policies import (
    MissionActionPolicyDescriptor,
    mission_action_policy_descriptors,
)
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    START_MISSION_ACTION_DECISION_TYPE,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    MissionActionStartAuthorityEvidence,
    PrimaryMissionActionStartEvidence,
    canonical_json_object,
)
from warhammer40k_core.engine.primary_mission_action_options import (
    primary_mission_action_target_kind,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import (
    CONSECRATE_CHOICE_KIND,
    LOCATE_AND_DENY_CHOICE_KIND,
    PUNISHMENT_CHOICE_KIND,
    SENSOR_SWEEP_CHOICE_KIND,
    PrimaryMissionChoiceData,
)
from warhammer40k_core.engine.primary_mission_choices import (
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    primary_mission_choice_option_id,
)
from warhammer40k_core.engine.primary_mission_state import PrimaryCondemnedSelectionState

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


_DECISION_REQUESTED_EVENT: Final = "decision_requested"
_DECISION_RECORDED_EVENT: Final = "decision_recorded"
_MISSION_ACTION_STARTED_EVENT: Final = "mission_action_started"
_MISSION_ACTION_ID_PREFIX: Final = "mission-action:"
_PRIMARY_MISSION_KIND: Final = "primary"

_ACTION_START_EVENT_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "mission_action_id",
        "target_id",
        "condition_target_id",
        "target_policy",
        "mission_action_start_evidence",
        "mission_action_state",
    }
)
_ACTION_RESULT_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "mission_action_id",
        "mission_id",
        "mission_kind",
        "unit_instance_id",
        "target_id",
        "condition_target_id",
        "target_kind",
        "target_policy",
        "start_timing",
        "completion_timing",
        "eligible_unit_instance_ids",
        "interruption_conditions",
        "scoring_source_id",
        "victory_points",
    }
)
_ACTION_OPPORTUNITY_RESULT_KEYS: Final = frozenset(
    {*_ACTION_RESULT_KEYS, "mission_action_opportunity", "legal_action_option_ids"}
)
_DIRECT_ACTION_REQUEST_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "mission_action_id",
        "legal_option_ids",
    }
)
_ACTION_OPPORTUNITY_REQUEST_KEYS: Final = frozenset(
    {
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "mission_action_opportunity",
        "legal_mission_action_ids",
        "legal_action_option_ids",
        "legal_option_ids",
    }
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


def validate_primary_mission_decision_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Authenticate Phase 17N Step 4 mutations against accepted decisions."""

    events, decisions, event_index_by_id = _validated_integrity_inputs(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_mission_action_start_decisions(
        state=state,
        event_records=events,
        decision_records=decisions,
        event_index_by_id=event_index_by_id,
        policies=_mission_action_policies(),
    )
    _validate_primary_choice_decisions(
        state=state,
        event_records=events,
        decision_records=decisions,
        event_index_by_id=event_index_by_id,
    )


def validate_primary_mission_action_start_decision_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Authenticate every source-backed Step 4 Mission Action start decision."""

    events, decisions, event_index_by_id = _validated_integrity_inputs(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_mission_action_start_decisions(
        state=state,
        event_records=events,
        decision_records=decisions,
        event_index_by_id=event_index_by_id,
        policies=_mission_action_policies(),
    )


def validate_primary_mission_choice_decision_integrity(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    """Authenticate every explicit or automatic Step 4 Primary choice resolution."""

    events, decisions, event_index_by_id = _validated_integrity_inputs(
        state=state,
        event_records=event_records,
        decision_records=decision_records,
    )
    _validate_primary_choice_decisions(
        state=state,
        event_records=events,
        decision_records=decisions,
        event_index_by_id=event_index_by_id,
    )


def _validate_mission_action_start_decisions(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
    policies: dict[str, MissionActionPolicyDescriptor],
) -> None:
    actions: list[MissionActionState] = []
    for action in state.mission_action_states:
        if type(action) is not MissionActionState:
            raise GameLifecycleError("Primary Mission Action decision state is untyped.")
        if action.mission_action_id in policies:
            actions.append(action)
    action_by_id = {action.action_id: action for action in actions}
    if len(action_by_id) != len(actions):
        raise GameLifecycleError("Primary Mission Action decision identities are duplicated.")

    start_by_action_id: dict[str, EventRecord] = {}
    for event in event_records:
        if event.event_type != _MISSION_ACTION_STARTED_EVENT:
            continue
        payload = _object(event.payload, label="Mission Action start event")
        nested = _object(
            payload.get("mission_action_state"),
            label="Mission Action start event state",
        )
        mission_action_id = nested.get("mission_action_id")
        if type(mission_action_id) is not str:
            raise GameLifecycleError("Mission Action start event mission_action_id is invalid.")
        if mission_action_id not in policies:
            continue
        action_id = _identifier(
            nested.get("action_id"),
            label="Primary Mission Action start action_id",
        )
        if action_id in start_by_action_id:
            raise GameLifecycleError("Primary Mission Action has duplicate start events.")
        start_by_action_id[action_id] = event

    if frozenset(start_by_action_id) != frozenset(action_by_id):
        raise GameLifecycleError(
            "Primary Mission Action state and start-event decision closure drifted."
        )

    for action in actions:
        start_event = start_by_action_id[action.action_id]
        policy = policies[action.mission_action_id]
        start_snapshot = replace(
            action,
            status=MissionActionStatus.STARTED,
            completed_battle_round=None,
            completed_phase=None,
            interrupted_reason=None,
            score_transaction_id=None,
        )
        result_id = _action_result_id(action.action_id)
        decision = _unique_decision_for_result(
            decision_records=decision_records,
            result_id=result_id,
            label="Primary Mission Action start",
        )
        start_evidence = _validate_action_start_event(
            state=state,
            action=start_snapshot,
            policy=policy,
            event=start_event,
        )
        _validate_action_decision(
            state=state,
            action=start_snapshot,
            policy=policy,
            decision=decision,
            start_authority=start_evidence.start_authority,
        )
        _validate_decision_event_closure(
            decision=decision,
            mutation_event=start_event,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            label="Primary Mission Action start",
        )

    for decision in decision_records:
        if decision.result.decision_type != START_MISSION_ACTION_DECISION_TYPE:
            continue
        result_payload = _object(
            decision.result.payload,
            label="Mission Action DecisionResult payload",
        )
        mission_action_id = result_payload.get("mission_action_id")
        if mission_action_id not in policies:
            continue
        expected_action_id = f"{_MISSION_ACTION_ID_PREFIX}{decision.result.result_id}"
        if expected_action_id not in action_by_id:
            raise GameLifecycleError(
                "Accepted Primary Mission Action decision has no persisted Action state."
            )


def _validate_action_start_event(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    event: EventRecord,
) -> PrimaryMissionActionStartEvidence:
    payload = _object(event.payload, label="Primary Mission Action start event")
    if frozenset(payload) != _ACTION_START_EVENT_KEYS:
        raise GameLifecycleError("Primary Mission Action start event payload fields drifted.")
    evidence = PrimaryMissionActionStartEvidence.from_payload(
        payload.get("mission_action_start_evidence")
    )
    if (
        payload.get("game_id") != state.game_id
        or payload.get("player_id") != action.player_id
        or payload.get("battle_round") != action.battle_round_started
        or payload.get("phase") != action.phase_started
        or payload.get("mission_action_id") != action.mission_action_id
        or payload.get("target_id") != action.target_id
        or payload.get("condition_target_id") != action.condition_target_id
        or payload.get("target_policy") != policy.target_policy
        or payload.get("mission_action_state") != action.to_payload()
    ):
        raise GameLifecycleError("Primary Mission Action start event decision payload drifted.")
    if (
        evidence.game_id != state.game_id
        or evidence.player_id != action.player_id
        or evidence.active_player_id != action.player_id
        or evidence.battle_round != action.battle_round_started
        or evidence.phase != action.phase_started
        or evidence.mission_action_id != action.mission_action_id
        or evidence.mission_id != action.mission_id
        or evidence.source_id != policy.source_id
        or evidence.eligible_unit_policy != policy.eligible_unit_policy
        or evidence.target_policy != policy.target_policy
        or evidence.use_limit != policy.use_limit
        or evidence.effect_descriptor != policy.effect_descriptor
        or evidence.unit_instance_id != action.unit_instance_id
        or evidence.eligible_unit_instance_ids != action.eligible_unit_instance_ids
        or evidence.target_id != action.target_id
        or evidence.condition_target_id != action.condition_target_id
    ):
        raise GameLifecycleError("Primary Mission Action start evidence identity drifted.")
    return evidence


def _validate_action_decision(
    *,
    state: GameState,
    action: MissionActionState,
    policy: MissionActionPolicyDescriptor,
    decision: DecisionRecord,
    start_authority: MissionActionStartAuthorityEvidence,
) -> None:
    request = decision.request
    result = decision.result
    expected_option_id = (
        f"start:{action.mission_action_id}:{action.unit_instance_id}:{action.target_id}"
    )
    if (
        request.decision_type != START_MISSION_ACTION_DECISION_TYPE
        or result.decision_type != START_MISSION_ACTION_DECISION_TYPE
        or request.actor_id != action.player_id
        or result.actor_id != action.player_id
        or result.selected_option_id != expected_option_id
    ):
        raise GameLifecycleError("Primary Mission Action DecisionRecord identity drifted.")

    result_payload = _object(result.payload, label="Primary Mission Action result payload")
    opportunity = frozenset(result_payload) == _ACTION_OPPORTUNITY_RESULT_KEYS
    if not opportunity and frozenset(result_payload) != _ACTION_RESULT_KEYS:
        raise GameLifecycleError("Primary Mission Action result payload fields drifted.")
    expected_result: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "player_id": action.player_id,
        "battle_round": action.battle_round_started,
        "phase": action.phase_started,
        "mission_action_id": action.mission_action_id,
        "mission_id": action.mission_id,
        "mission_kind": _PRIMARY_MISSION_KIND,
        "unit_instance_id": action.unit_instance_id,
        "target_id": action.target_id,
        "condition_target_id": action.condition_target_id,
        "target_kind": primary_mission_action_target_kind(policy.target_policy),
        "target_policy": policy.target_policy,
        "start_timing": action.start_timing,
        "completion_timing": action.completion_timing,
        "eligible_unit_instance_ids": list(action.eligible_unit_instance_ids),
        "interruption_conditions": list(action.interruption_conditions),
        "scoring_source_id": action.scoring_source_id,
        "victory_points": action.victory_points,
    }
    if any(result_payload.get(key) != value for key, value in expected_result.items()):
        raise GameLifecycleError("Primary Mission Action result payload identity drifted.")
    _validate_action_request(
        decision=decision,
        result_payload=result_payload,
        opportunity=opportunity,
        start_authority=start_authority,
    )


def _validate_action_request(
    *,
    decision: DecisionRecord,
    result_payload: dict[str, JsonValue],
    opportunity: bool,
    start_authority: MissionActionStartAuthorityEvidence,
) -> None:
    request = decision.request
    request_payload = _object(request.payload, label="Primary Mission Action request payload")
    actual_options = tuple(
        (
            option.option_id,
            option.label,
            canonical_json_object(option.payload),
        )
        for option in request.options
    )
    expected_options = tuple(
        (option.option_id, option.label, option.payload_json) for option in start_authority.options
    )
    if (
        start_authority.request_kind != ("opportunity" if opportunity else "direct")
        or canonical_json_object(request.payload) != start_authority.request_payload_json
        or actual_options != expected_options
    ):
        raise GameLifecycleError("Primary Mission Action complete start authority drifted.")
    option_ids = [option.option_id for option in request.options]
    if len(option_ids) != len(set(option_ids)):
        raise GameLifecycleError("Primary Mission Action request option IDs are duplicated.")
    selected_options = tuple(
        option
        for option in request.options
        if option.option_id == decision.result.selected_option_id
    )
    if len(selected_options) != 1:
        raise GameLifecycleError("Primary Mission Action selected request option drifted.")
    selected_payload = _object(
        selected_options[0].payload,
        label="Primary Mission Action selected option payload",
    )
    if selected_payload != result_payload:
        raise GameLifecycleError("Primary Mission Action selected option/result payload drifted.")
    shared = (
        "game_id",
        "player_id",
        "battle_round",
        "phase",
    )
    if any(request_payload.get(key) != result_payload.get(key) for key in shared):
        raise GameLifecycleError("Primary Mission Action request/result context drifted.")

    if opportunity:
        if frozenset(request_payload) != _ACTION_OPPORTUNITY_REQUEST_KEYS:
            raise GameLifecycleError("Primary Mission Action opportunity request fields drifted.")
        action_option_ids = [
            option_id
            for option_id in option_ids
            if option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
        ]
        if option_ids.count(DECLINE_MISSION_ACTION_START_OPTION_ID) != 1:
            raise GameLifecycleError("Primary Mission Action opportunity decline option drifted.")
        mission_action_ids = sorted(
            {
                _identifier(
                    _object(option.payload, label="Mission Action option payload").get(
                        "mission_action_id"
                    ),
                    label="Mission Action option mission_action_id",
                )
                for option in request.options
                if option.option_id != DECLINE_MISSION_ACTION_START_OPTION_ID
            }
        )
        if (
            request_payload.get("mission_action_opportunity") is not True
            or result_payload.get("mission_action_opportunity") is not True
            or request_payload.get("legal_mission_action_ids") != mission_action_ids
            or request_payload.get("legal_action_option_ids") != action_option_ids
            or result_payload.get("legal_action_option_ids") != action_option_ids
            or request_payload.get("legal_option_ids") != sorted(option_ids)
            or decision.result.selected_option_id not in action_option_ids
        ):
            raise GameLifecycleError("Primary Mission Action opportunity request closure drifted.")
        return

    if frozenset(request_payload) != _DIRECT_ACTION_REQUEST_KEYS:
        raise GameLifecycleError("Primary Mission Action direct request fields drifted.")
    if (
        request_payload.get("mission_action_id") != result_payload.get("mission_action_id")
        or request_payload.get("legal_option_ids") != option_ids
        or DECLINE_MISSION_ACTION_START_OPTION_ID in option_ids
    ):
        raise GameLifecycleError("Primary Mission Action direct request closure drifted.")


def _validate_primary_choice_decisions(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    choice_events = tuple(
        event
        for event in event_records
        if event.event_type == PRIMARY_MISSION_CHOICE_RESOLVED_EVENT
    )
    authenticated_result_ids: set[str] = set()
    for event in choice_events:
        payload = _object(event.payload, label="Primary mission choice event")
        if frozenset(payload) != _CHOICE_EVENT_KEYS:
            raise GameLifecycleError("Primary mission choice event payload fields drifted.")
        choice = PrimaryMissionChoiceData.from_payload(payload.get("choice"))
        if choice.game_id != state.game_id or choice.player_id not in state.player_ids:
            raise GameLifecycleError("Primary mission choice event game or player drifted.")
        automatic = payload.get("automatic")
        if type(automatic) is not bool:
            raise GameLifecycleError("Primary mission choice automatic flag is invalid.")
        if automatic:
            _validate_automatic_empty_punishment(
                event=event,
                payload=payload,
                choice=choice,
                event_records=event_records,
                decision_records=decision_records,
            )
            continue
        decision = _choice_decision_for_event(
            payload=payload,
            choice=choice,
            decision_records=decision_records,
        )
        if decision.result.result_id in authenticated_result_ids:
            raise GameLifecycleError("Primary mission choice DecisionRecord is reused.")
        authenticated_result_ids.add(decision.result.result_id)
        _validate_decision_event_closure(
            decision=decision,
            mutation_event=event,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
            label="Primary mission choice",
        )

    for decision in decision_records:
        if decision.result.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE:
            continue
        if decision.result.result_id not in authenticated_result_ids:
            raise GameLifecycleError(
                "Accepted Primary mission choice has no authenticated resolution event."
            )


def _choice_decision_for_event(
    *,
    payload: dict[str, JsonValue],
    choice: PrimaryMissionChoiceData,
    decision_records: tuple[DecisionRecord, ...],
) -> DecisionRecord:
    request_id = _identifier(payload.get("request_id"), label="Primary mission choice request_id")
    result_id = _identifier(payload.get("result_id"), label="Primary mission choice result_id")
    selected_option_id = _identifier(
        payload.get("selected_option_id"),
        label="Primary mission choice selected_option_id",
    )
    decision = _unique_decision_for_result(
        decision_records=decision_records,
        result_id=result_id,
        label="Primary mission choice",
    )
    request = decision.request
    result = decision.result
    expected_request_choice = replace(choice, selected_target_ids=())
    expected_option_id = primary_mission_choice_option_id(
        choice=expected_request_choice,
        selected_ids=choice.selected_target_ids,
    )
    if (
        request.request_id != request_id
        or result.request_id != request_id
        or request.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
        or result.decision_type != SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
        or request.actor_id != choice.player_id
        or result.actor_id != choice.player_id
        or result.selected_option_id != selected_option_id
        or selected_option_id != expected_option_id
        or request.payload != expected_request_choice.to_payload()
        or result.payload != choice.to_payload()
    ):
        raise GameLifecycleError("Primary mission choice DecisionRecord provenance drifted.")
    _validate_primary_choice_request_options(
        request=request,
        choice=expected_request_choice,
    )
    return decision


def _validate_primary_choice_request_options(
    *,
    request: object,
    choice: PrimaryMissionChoiceData,
) -> None:
    from warhammer40k_core.engine.decision_request import DecisionRequest

    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Primary mission choice request is invalid.")
    selected_sets = _primary_choice_selected_target_sets(choice)
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
        raise GameLifecycleError("Primary mission choice finite option inventory drifted.")


def _primary_choice_selected_target_sets(
    choice: PrimaryMissionChoiceData,
) -> tuple[tuple[str, ...], ...]:
    legal_ids = choice.legal_target_ids
    if choice.choice_kind == LOCATE_AND_DENY_CHOICE_KIND:
        selection_count = min(5, len(legal_ids))
        return tuple(combinations(legal_ids, selection_count))
    if choice.choice_kind == PUNISHMENT_CHOICE_KIND:
        maximum = 1 if choice.used_fallback_candidates else min(3, len(legal_ids))
        return tuple(
            selected
            for count in range(1, maximum + 1)
            for selected in combinations(legal_ids, count)
        )
    if choice.choice_kind == CONSECRATE_CHOICE_KIND:
        return (*((target_id,) for target_id in legal_ids), ())
    if choice.choice_kind == SENSOR_SWEEP_CHOICE_KIND:
        return tuple((target_id,) for target_id in legal_ids)
    raise GameLifecycleError("Primary mission choice kind is unsupported.")


def _validate_automatic_empty_punishment(
    *,
    event: EventRecord,
    payload: dict[str, JsonValue],
    choice: PrimaryMissionChoiceData,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
) -> None:
    if (
        choice.choice_kind != PUNISHMENT_CHOICE_KIND
        or choice.legal_target_ids
        or choice.selected_target_ids
        or payload.get("request_id") is not None
        or payload.get("result_id") is not None
        or payload.get("selected_option_id") is not None
        or payload.get("created_markers") != []
        or payload.get("updated_designation") is not None
        or payload.get("removed_marker") is not None
    ):
        raise GameLifecycleError("Automatic Primary mission choice is not an empty Punishment.")
    selection = PrimaryCondemnedSelectionState.from_payload(payload.get("condemned_selection"))
    if (
        selection.game_id != choice.game_id
        or selection.owner_player_id != choice.player_id
        or selection.mission_id != choice.primary_mission_id
        or selection.source_rule_id != choice.source_rule_id
        or selection.source_descriptor_id != choice.source_descriptor_id
        or selection.candidate_rules_unit_instance_ids != choice.legal_target_ids
        or selection.candidate_evidence_ids != choice.evidence_ids
        or selection.selected_rules_unit_instance_ids != choice.selected_target_ids
        or selection.used_fallback_candidates != choice.used_fallback_candidates
        or selection.selection_request_id is not None
        or selection.selection_result_id is not None
        or selection.source_event_id != event.event_id
    ):
        raise GameLifecycleError("Automatic empty Punishment state provenance drifted.")
    choice_payload = choice.to_payload()
    if any(
        record.request.decision_type == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
        and (record.request.payload == choice_payload or record.result.payload == choice_payload)
        for record in decision_records
    ):
        raise GameLifecycleError("Automatic empty Punishment has an attached DecisionRecord.")
    if any(
        _event_contains_choice_decision_payload(record, choice_payload=choice_payload)
        for record in event_records
    ):
        raise GameLifecycleError("Automatic empty Punishment has attached decision events.")


def _event_contains_choice_decision_payload(
    event: EventRecord,
    *,
    choice_payload: object,
) -> bool:
    if event.event_type == _DECISION_REQUESTED_EVENT:
        payload = event.payload
        return (
            isinstance(payload, dict)
            and payload.get("decision_type") == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
            and payload.get("payload") == choice_payload
        )
    if event.event_type != _DECISION_RECORDED_EVENT or not isinstance(event.payload, dict):
        return False
    request = event.payload.get("request")
    result = event.payload.get("result")
    return (
        isinstance(request, dict)
        and request.get("decision_type") == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
        and request.get("payload") == choice_payload
    ) or (
        isinstance(result, dict)
        and result.get("decision_type") == SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE
        and result.get("payload") == choice_payload
    )


def _validate_decision_event_closure(
    *,
    decision: DecisionRecord,
    mutation_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    label: str,
) -> None:
    requested_events = tuple(
        event
        for event in event_records
        if event.event_type == _DECISION_REQUESTED_EVENT
        and event.payload == decision.request.to_payload()
    )
    recorded_events = tuple(
        event
        for event in event_records
        if event.event_type == _DECISION_RECORDED_EVENT and event.payload == decision.to_payload()
    )
    if len(requested_events) != 1 or len(recorded_events) != 1:
        raise GameLifecycleError(f"{label} requires exact requested and recorded decision events.")
    if not (
        event_index_by_id[requested_events[0].event_id]
        < event_index_by_id[recorded_events[0].event_id]
        < event_index_by_id[mutation_event.event_id]
    ):
        raise GameLifecycleError(f"{label} decision/mutation ordering drifted.")


def _unique_decision_for_result(
    *,
    decision_records: tuple[DecisionRecord, ...],
    result_id: str,
    label: str,
) -> DecisionRecord:
    matches = tuple(
        decision for decision in decision_records if decision.result.result_id == result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError(f"{label} requires one authoritative DecisionRecord.")
    return matches[0]


def _action_result_id(action_id: str) -> str:
    if not action_id.startswith(_MISSION_ACTION_ID_PREFIX):
        raise GameLifecycleError("Primary Mission Action action_id lacks result provenance.")
    return _identifier(
        action_id[len(_MISSION_ACTION_ID_PREFIX) :],
        label="Primary Mission Action result_id",
    )


def _validated_integrity_inputs(
    *,
    state: object,
    event_records: object,
    decision_records: object,
) -> tuple[tuple[EventRecord, ...], tuple[DecisionRecord, ...], dict[str, int]]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Primary mission decision integrity requires GameState.")
    events = _event_records(event_records)
    decisions = _decision_records(decision_records)
    event_index_by_id = {record.event_id: index for index, record in enumerate(events)}
    if len(event_index_by_id) != len(events):
        raise GameLifecycleError("Primary mission decision event identities are duplicated.")
    decision_by_record_id = {record.record_id: record for record in decisions}
    if len(decision_by_record_id) != len(decisions):
        raise GameLifecycleError("Primary mission DecisionRecord identities are duplicated.")
    return events, decisions, event_index_by_id


def _mission_action_policies() -> dict[str, MissionActionPolicyDescriptor]:
    return {
        descriptor.mission_action_id: descriptor
        for descriptor in mission_action_policy_descriptors()
    }


def _event_records(value: object) -> tuple[EventRecord, ...]:
    if type(value) is not tuple or any(
        type(record) is not EventRecord for record in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Primary mission decision integrity requires EventRecords.")
    return cast(tuple[EventRecord, ...], value)


def _decision_records(value: object) -> tuple[DecisionRecord, ...]:
    if type(value) is not tuple or any(
        type(record) is not DecisionRecord for record in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Primary mission decision integrity requires DecisionRecords.")
    return cast(tuple[DecisionRecord, ...], value)


def _object(value: object, *, label: str) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise GameLifecycleError(f"{label} must be a JSON object.")
    return cast(dict[str, JsonValue], value)


def _identifier(value: object, *, label: str) -> str:
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"{label} must be a non-empty identifier.")
    return value


__all__ = (
    "validate_primary_mission_action_start_decision_integrity",
    "validate_primary_mission_choice_decision_integrity",
    "validate_primary_mission_decision_integrity",
)
