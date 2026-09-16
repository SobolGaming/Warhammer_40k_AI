"""Keep flight commitments attached to their original finite decisions."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.take_to_the_skies import flight_selection, validate_flight_context

if TYPE_CHECKING:
    from warhammer40k_core.engine.charge_declaration import ChargeRollRequest
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def validate_charge_flight(*, roll: ChargeRollRequest, decisions: DecisionController) -> None:
    matches = tuple(
        record
        for record in decisions.records
        if record.request.request_id == roll.source_decision_request_id
        and record.result.result_id == roll.source_decision_result_id
    )
    if len(matches) != 1 or flight_selection(matches[0].result.payload) != roll.take_to_the_skies:
        raise GameLifecycleError("Charge flight differs from its original finite choice.")


def validate_reactive_flight(
    *, state: GameState, decisions: DecisionController, request: DecisionRequest
) -> None:
    from warhammer40k_core.engine.triggered_movement import (
        TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND,
        is_triggered_movement_proposal_request,
    )

    context = request.payload
    if is_triggered_movement_proposal_request(request):
        context = MovementProposalRequest.from_decision_request_payload(request.payload).context
    elif (
        not isinstance(context, dict)
        or context.get("context_kind") != TRIGGERED_MOVEMENT_DISTANCE_REROLL_CONTEXT_KIND
    ):
        return
    if not isinstance(context, dict):
        raise GameLifecycleError("Reactive flight requires its selection context.")
    matches = tuple(
        record
        for record in decisions.records
        if record.request.request_id == context.get("selection_request_id")
        and record.result.result_id == context.get("selection_result_id")
        and record.result.selected_option_id == context.get("selection_option_id")
    )
    if len(matches) != 1:
        raise GameLifecycleError("Reactive flight lost its original selection.")
    payload = matches[0].result.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("descriptor"), dict):
        raise GameLifecycleError("Reactive flight selection descriptor is missing.")
    # Other displacement kinds cannot opt into Flying Models.
    if cast(dict[str, JsonValue], payload["descriptor"]).get("movement_mode") != "normal":
        if flight_selection(context):
            raise GameLifecycleError("Reactive flight requires a Normal move.")
        return
    if flight_selection(context) != flight_selection(payload):
        raise GameLifecycleError("Reactive flight differs from its original selection.")
    unit_id = payload.get("unit_instance_id")
    if not isinstance(unit_id, str):
        raise GameLifecycleError("Reactive flight selection unit is missing.")
    validate_flight_context(
        payload=payload,
        unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
        ruleset=state.runtime_ruleset_descriptor(),
    )


def invalid_flight_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.triggered_movement import SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE

    try:
        validate_charge_selection_flight(state=state, decisions=decisions)
        if request.decision_type == SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE:
            result.validate_for_request(request)
            payload = result.payload
            if (
                isinstance(payload, dict)
                and not payload.get("declined")
                and isinstance(payload.get("descriptor"), dict)
                and cast(dict[str, JsonValue], payload["descriptor"]).get("movement_mode")
                == "normal"
            ):
                unit_id = payload.get("unit_instance_id")
                if not isinstance(unit_id, str):
                    return LifecycleStatus.invalid(
                        stage=state.stage,
                        message="Flight choice unit is missing.",
                        payload={"invalid_reason": "flight_choice_authority_drift"},
                    )
                validate_flight_context(
                    payload=payload,
                    unit=rules_unit_view_by_id(state=state, unit_instance_id=unit_id),
                    ruleset=state.runtime_ruleset_descriptor(),
                )
        else:
            validate_reactive_flight(state=state, decisions=decisions, request=request)
    except (DecisionError, GameLifecycleError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "flight_choice_authority_drift"},
        )
    return None


def validate_restored_flight(*, state: GameState, decisions: DecisionController) -> None:
    from warhammer40k_core.engine.charge_declaration import (
        ChargeRollResult,
        ChargeRollResultPayload,
    )

    for event in decisions.event_log.records:
        if event.event_type in {
            "charge_roll_resolved",
            "catalog_setup_reactive_charge_roll_resolved",
        }:
            if not isinstance(event.payload, dict) or not isinstance(
                event.payload.get("roll_result"), dict
            ):
                raise GameLifecycleError("Charge flight roll evidence is missing.")
            roll = ChargeRollResult.from_payload(
                cast(ChargeRollResultPayload, event.payload["roll_result"])
            )
            validate_charge_flight(roll=roll.request, decisions=decisions)
    validate_charge_selection_flight(state=state, decisions=decisions)
    for request in decisions.queue.pending_requests:
        validate_reactive_flight(state=state, decisions=decisions, request=request)


def validate_charge_selection_flight(*, state: GameState, decisions: DecisionController) -> None:
    phase = state.charge_phase_state
    if phase is not None and phase.active_selection is not None:
        selection = phase.active_selection
        matches = tuple(
            record
            for record in decisions.records
            if record.request.request_id == selection.request_id
            and record.result.result_id == selection.result_id
        )
        if (
            len(matches) != 1
            or flight_selection(matches[0].result.payload) != selection.take_to_the_skies
        ):
            raise GameLifecycleError("Charge flight differs from its recorded selection.")
        pending = phase.move_pending_distance_state()
        if (
            pending is not None
            and pending.roll_result.request.take_to_the_skies != selection.take_to_the_skies
        ):
            raise GameLifecycleError("Charge flight differs from its committed roll.")
