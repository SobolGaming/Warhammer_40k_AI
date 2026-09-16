"""Authenticate Surge's trigger and finite commitment before queue pop and restore."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phase_movement_history import surge_locked
from warhammer40k_core.engine.surge_choices import selected_surge_target, surge_choice_context
from warhammer40k_core.engine.surge_movement import surge_ineligibility, validate_surge_target
from warhammer40k_core.engine.triggered_movement import (
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND,
    TriggeredMovementDescriptor,
    TriggeredMovementDescriptorPayload,
    TriggeredMovementEligibleUnit,
    TriggeredMovementEligibleUnitPayload,
    TriggeredMovementKind,
    is_triggered_movement_distance_reroll_request,
    is_triggered_movement_proposal_request,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def require_surge_trigger(
    *,
    state: GameState,
    decisions: DecisionController | None,
    descriptor: TriggeredMovementDescriptor,
) -> None:
    if descriptor.movement_kind is not TriggeredMovementKind.SURGE:
        return
    if decisions is None:
        raise GameLifecycleError("Surge requires recorded trigger authority.")
    if (
        state.current_battle_phase is not descriptor.trigger_timing.phase
        or state.active_player_id is None
    ):
        raise GameLifecycleError("Surge granting trigger escaped its phase occurrence.")
    validate_surge_trigger_occurrence(
        events=decisions.event_log.records,
        descriptor=descriptor,
        battle_round=state.battle_round,
        turn_player_id=state.active_player_id,
    )


def validate_surge_trigger_occurrence(
    *,
    events: tuple[EventRecord, ...],
    descriptor: TriggeredMovementDescriptor,
    battle_round: int,
    turn_player_id: str,
) -> None:
    matches = tuple(
        event
        for event in events
        if event.event_id == descriptor.trigger_timing.source_event_id
        or (
            event.event_type == "stratagem_used"
            and isinstance(event.payload, dict)
            and event.payload.get("use_id") == descriptor.trigger_timing.source_event_id
            and event.payload.get("source_id") == descriptor.source_rule_id
        )
    )
    if len(matches) != 1 or not isinstance(matches[0].payload, dict):
        raise GameLifecycleError("Surge requires its recorded granting trigger.")
    payload = matches[0].payload
    if (
        payload.get("battle_round") != battle_round
        or payload.get("phase") != descriptor.trigger_timing.phase.value
    ):
        raise GameLifecycleError("Surge granting trigger escaped its phase occurrence.")
    if payload.get("active_player_id") != turn_player_id:
        raise GameLifecycleError("Surge granting trigger belongs to another turn.")


def validate_surge_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult | None = None,
) -> None:
    payload: JsonValue = request.payload
    proposal = is_triggered_movement_proposal_request(request)
    if (
        not proposal
        and request.decision_type != SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
        and not is_triggered_movement_distance_reroll_request(request)
    ):
        return
    if proposal:
        payload = MovementProposalRequest.from_decision_request_payload(payload).context
    if not isinstance(payload, dict) or not isinstance(payload.get("descriptor"), dict):
        return
    descriptor = TriggeredMovementDescriptor.from_payload(
        cast(TriggeredMovementDescriptorPayload, payload["descriptor"])
    )
    if descriptor.movement_kind is not TriggeredMovementKind.SURGE and not any(
        record.request.request_id == payload.get("selection_request_id")
        and record.request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
        and isinstance(record.request.payload, dict)
        and isinstance(record.request.payload.get("descriptor"), dict)
        and cast(dict[str, JsonValue], record.request.payload["descriptor"]).get("movement_kind")
        == TriggeredMovementKind.SURGE.value
        for record in decisions.records
    ):
        return
    require_surge_trigger(state=state, decisions=decisions, descriptor=descriptor)
    selections: tuple[dict[str, JsonValue], ...]
    if proposal or request.decision_type != SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE:
        selections = (
            validate_surge_selection_chain(decisions, payload, descriptor, request=request),
        )
    elif result is not None:
        result.validate_for_request(request)
        if not isinstance(result.payload, dict):
            raise GameLifecycleError("Surge selection requires an object.")
        selections = (result.payload,)
    else:
        selections = tuple(
            option.payload for option in request.options if isinstance(option.payload, dict)
        )
    for selection in selections:
        if selection.get("declined"):
            continue
        unit_id = selection.get("unit_instance_id")
        if not isinstance(unit_id, str):
            raise GameLifecycleError("Surge selection has no source unit.")
        reason = surge_ineligibility(state, unit_id)
        if reason is not None:
            raise GameLifecycleError(reason)
        validate_surge_target(
            scenario=battlefield_scenario_for_state(state=state),
            unit_instance_id=unit_id,
            target_id=selected_surge_target(selection, descriptor),
        )
        if selection.get("take_to_the_skies"):
            raise GameLifecycleError("Surge cannot take to the skies.")


def validate_surge_selection_chain(
    decisions: DecisionController,
    context: dict[str, JsonValue],
    descriptor: TriggeredMovementDescriptor,
    *,
    request: DecisionRequest,
) -> dict[str, JsonValue]:
    matches = tuple(
        record
        for record in decisions.records
        if record.request.request_id == context.get("selection_request_id")
        and record.result.result_id == context.get("selection_result_id")
        and record.result.selected_option_id == context.get("selection_option_id")
        and record.request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE
    )
    if len(matches) != 1 or not isinstance(matches[0].result.payload, dict):
        raise GameLifecycleError("Surge lost its original finite selection.")
    selected = matches[0].result.payload
    if selected_surge_target(context, descriptor) != selected_surge_target(selected, descriptor):
        raise GameLifecycleError("Surge target differs from its original finite choice.")
    _validate_surge_granted_descriptor(
        decisions=decisions,
        selection=matches[0],
        request=request,
        context=context,
        descriptor=descriptor,
    )
    return selected


def _validate_surge_granted_descriptor(
    *,
    decisions: DecisionController,
    selection: DecisionRecord,
    request: DecisionRequest,
    context: dict[str, JsonValue],
    descriptor: TriggeredMovementDescriptor,
) -> None:
    grant = selection.request.payload
    chosen = selection.result.payload
    if (
        not isinstance(grant, dict)
        or not isinstance(grant.get("descriptor"), dict)
        or not isinstance(chosen, dict)
        or not isinstance(chosen.get("eligible_unit"), dict)
    ):
        raise GameLifecycleError("Surge original grant is malformed.")
    original = TriggeredMovementDescriptor.from_payload(
        cast(TriggeredMovementDescriptorPayload, grant["descriptor"])
    )
    unit = TriggeredMovementEligibleUnit.from_payload(
        cast(TriggeredMovementEligibleUnitPayload, chosen["eligible_unit"])
    )
    if context.get("selected_unit") != unit.to_payload():
        raise GameLifecycleError("Surge selected unit differs from its recorded grant.")
    expected = original
    pending_reroll = is_triggered_movement_distance_reroll_request(request)
    reroll_fields = {
        "distance_reroll_request_id",
        "distance_reroll_result_id",
        "distance_roll_state",
    }
    if unit.distance_reroll_permission is None or pending_reroll:
        if reroll_fields & context.keys():
            raise GameLifecycleError("Surge has ungranted distance reroll evidence.")
    else:
        matches = tuple(
            record
            for record in decisions.records
            if record.request.request_id == context.get("distance_reroll_request_id")
            and record.result.result_id == context.get("distance_reroll_result_id")
            and is_triggered_movement_distance_reroll_request(record.request)
        )
        if len(matches) != 1:
            raise GameLifecycleError("Surge lost its recorded distance reroll decision.")
        record = matches[0]
        _validate_surge_reroll_request(record.request, selection, original, unit)
        events = decisions.event_log.records
        selection_index = _surge_event_index(events, "decision_recorded", selection.to_payload())
        reroll_index = _surge_event_index(events, "decision_recorded", record.to_payload())
        proposal_index = _surge_event_index(events, "decision_requested", request.to_payload())
        if not selection_index < reroll_index < proposal_index:
            raise GameLifecycleError("Surge distance reroll decision order drifted.")
        game_id = grant.get("game_id")
        initial = unit.distance_roll_state
        if not isinstance(game_id, str) or initial is None:
            raise GameLifecycleError("Surge distance reroll source is missing.")
        # Reconstruct only the recorded dice transition on an isolated event log.
        # No proposal-supplied total or roll-state copy can enlarge the grant.
        boundary = reroll_index + 1
        manager = DiceRollManager(
            game_id,
            event_log=EventLog.from_payload([event.to_payload() for event in events[:boundary]]),
        )
        rolled = manager.resolve_reroll(
            initial, request=record.request, result=record.result, record_decision=False
        )
        generated = manager.event_log.records[boundary:]
        if (
            boundary + len(generated) > proposal_index
            or generated != events[boundary : boundary + len(generated)]
            or context.get("distance_roll_state") != rolled.to_payload()
        ):
            raise GameLifecycleError("Surge distance reroll evidence differs from recorded dice.")
        expected = replace(
            original,
            max_distance_inches=float(rolled.current_total + unit.distance_roll_bonus_inches),
        )
    if descriptor != expected:
        raise GameLifecycleError("Surge descriptor differs from its recorded grant.")
    if pending_reroll:
        _validate_surge_reroll_request(request, selection, original, unit)


def _validate_surge_reroll_request(
    request: DecisionRequest,
    selection: DecisionRecord,
    descriptor: TriggeredMovementDescriptor,
    unit: TriggeredMovementEligibleUnit,
) -> None:
    if unit.distance_roll_state is None or unit.distance_reroll_permission is None:
        raise GameLifecycleError("Surge has no recorded distance reroll permission.")
    expected = DiceRollManager(0).build_reroll_request(
        unit.distance_roll_state,
        request_id=request.request_id,
        actor_id=selection.result.actor_id,
        permission=unit.distance_reroll_permission,
        extra_payload={
            **surge_choice_context(selection.result.payload, descriptor),
            "context_kind": TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND,
            "descriptor": validate_json_value(descriptor.to_payload()),
            "selected_unit": validate_json_value(unit.to_payload()),
            "selection_request_id": selection.request.request_id,
            "selection_result_id": selection.result.result_id,
            "selection_option_id": selection.result.selected_option_id,
            "take_to_the_skies": False,
        },
    )
    if request != expected:
        raise GameLifecycleError("Surge distance reroll request differs from its recorded grant.")


def _surge_event_index(events: tuple[EventRecord, ...], event_type: str, payload: object) -> int:
    matches = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == event_type and event.payload == payload
    )
    if len(matches) != 1:
        raise GameLifecycleError("Surge distance reroll lost its recorded event authority.")
    return matches[0]


def invalid_surge_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    selection = result.payload
    unit_id: JsonValue
    if is_triggered_movement_proposal_request(request):
        unit_id = MovementProposalRequest.from_decision_request_payload(
            request.payload
        ).unit_instance_id
    else:
        unit_id = (
            selection.get("unit_instance_id")
            if isinstance(selection, dict) and not selection.get("declined")
            else None
        )
    if isinstance(unit_id, str) and surge_locked(state, unit_id):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="surge_movement_locked_this_phase",
            payload={"invalid_reason": "surge_movement_locked_this_phase"},
        )
    try:
        validate_surge_request(state=state, decisions=decisions, request=request, result=result)
    except (DecisionError, GameLifecycleError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "surge_authority_drift"},
        )
    return None


def validate_restored_surge(*, state: GameState, decisions: DecisionController) -> None:
    from warhammer40k_core.engine.surge_history import validate_surge_history

    for request in decisions.queue.pending_requests:
        validate_surge_request(state=state, decisions=decisions, request=request)
    validate_surge_history(state=state, decisions=decisions)
