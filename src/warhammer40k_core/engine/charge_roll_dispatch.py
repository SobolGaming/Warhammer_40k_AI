"""Charge reroll dispatch shared by lifecycle submission and restoration."""

from __future__ import annotations

# This dispatch module shares the lifecycle's configured phase owners.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.catalog_selected_target_charge_effects import (
    selected_target_charge_constraint_for_unit,
)
from warhammer40k_core.engine.charge_roll_flow import pending_charge_roll
from warhammer40k_core.engine.charge_roll_permissions import charge_reroll_permission_for_unit
from warhammer40k_core.engine.charge_roll_reroll_requests import build_charge_roll_reroll_request
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.lifecycle import GameLifecycle
    from warhammer40k_core.engine.phases.charge import ChargePhaseHandler


def invalid_charge_reroll(
    lifecycle: GameLifecycle, request: DecisionRequest, result: DecisionResult
) -> LifecycleStatus | None:
    if not is_charge_reroll(request) and not has_recorded_charge_reroll(
        request=request, decisions=lifecycle.decision_controller
    ):
        return None
    state = lifecycle._require_state()
    if request.actor_id is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Charge reroll actor is missing.",
            payload={"invalid_reason": "charge_reroll_actor_missing"},
        )
    try:
        result.validate_for_request(request)
        validate_charge_reroll(
            state=state,
            decisions=lifecycle.decision_controller,
            request=request,
            handler=lifecycle._charge_phase_handler,
        )
    except (DecisionError, GameLifecycleError, KeyError, TypeError, ValueError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=f"Charge reroll authority is invalid: {exc}",
            payload={"invalid_reason": "charge_reroll_authority_drift"},
        )
    return None


def validate_restored_charge_rerolls(
    *, state: GameState, decisions: DecisionController, handler: ChargePhaseHandler
) -> None:
    phase = state.charge_phase_state
    if (
        phase is not None
        and phase.active_selection is not None
        and phase.move_pending_distance_state() is None
        and not any(
            request.decision_type == "select_charge_declaration_grant"
            for request in decisions.queue.pending_requests
        )
    ):
        pending_charge_roll(state=state, decisions=decisions)
    for request in decisions.queue.pending_requests:
        if is_charge_reroll(request) or has_recorded_charge_reroll(
            request=request, decisions=decisions
        ):
            validate_charge_reroll(
                state=state, decisions=decisions, request=request, handler=handler
            )


def is_charge_reroll(request: DecisionRequest) -> bool:
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    if request.decision_type == DICE_REROLL_DECISION_TYPE:
        return "charge_context" in payload
    context = payload.get("stratagem_context")
    if request.decision_type == "use_stratagem" and isinstance(context, dict):
        trigger = context.get("trigger_payload")
        return isinstance(trigger, dict) and trigger.get("charge_action_id") is not None
    return False


def has_recorded_charge_reroll(*, request: DecisionRequest, decisions: DecisionController) -> bool:
    for event in decisions.event_log.records:
        payload = event.payload
        if (
            event.event_type == "decision_requested"
            and isinstance(payload, dict)
            and payload.get("request_id") == request.request_id
        ):
            from warhammer40k_core.engine.decision_request import DecisionRequestPayload

            recorded = DecisionRequest.from_payload(cast(DecisionRequestPayload, payload))
            if is_charge_reroll(recorded):
                return True
    return False


def validate_charge_reroll(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    handler: ChargePhaseHandler,
) -> None:
    if (
        sum(
            event.event_type == "decision_requested" and event.payload == request.to_payload()
            for event in decisions.event_log.records
        )
        != 1
    ):
        raise GameLifecycleError("Charge reroll request differs from its recorded authority.")
    if request.actor_id is None:
        raise GameLifecycleError("Charge reroll actor is missing.")
    ability_index = handler.ability_index_for_player(request.actor_id)
    roll_request, initial = pending_charge_roll(state=state, decisions=decisions)
    if request.actor_id != roll_request.player_id:
        raise GameLifecycleError("Charge reroll actor differs from selected charger.")
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Charge reroll context is malformed.")
    if request.decision_type == DICE_REROLL_DECISION_TYPE:
        context = payload.get("charge_context")
        if not isinstance(context, dict):
            raise GameLifecycleError("Charge reroll source is malformed.")
        from warhammer40k_core.engine.phases.charge import legal_charge_target_unit_instance_ids

        if handler.ruleset_descriptor is None:
            raise GameLifecycleError("Charge reroll requires a ruleset.")
        permission = charge_reroll_permission_for_unit(
            state=state,
            player_id=request.actor_id,
            unit_instance_id=roll_request.unit_instance_id,
            ability_index=ability_index,
        )
        if permission is None:
            raise GameLifecycleError("Charge reroll source is no longer available.")
        expected = build_charge_roll_reroll_request(
            state=state,
            decisions=decisions,
            request_id=request.request_id,
            roll_request=roll_request,
            roll_state=initial,
            permission=permission,
            selected_target_constraint=selected_target_charge_constraint_for_unit(
                state=state, unit_instance_id=roll_request.unit_instance_id
            ),
            legal_target_unit_instance_ids=legal_charge_target_unit_instance_ids(
                state=state,
                unit_instance_id=roll_request.unit_instance_id,
                ruleset_descriptor=handler.ruleset_descriptor,
                charge_target_restriction_hooks=handler.charge_target_restriction_hooks,
            ),
        )
        if request != expected:
            raise GameLifecycleError("Charge reroll permission, dice or target authority drift.")
        return
    context = payload.get("stratagem_context")
    if not isinstance(context, dict) or not isinstance(context.get("trigger_payload"), dict):
        raise GameLifecycleError("Charge Command Re-roll context is malformed.")
    trigger = cast(dict[str, JsonValue], context["trigger_payload"])
    if (
        trigger.get("charge_action_id") != roll_request.request_id
        or trigger.get("affected_unit_instance_id") != roll_request.unit_instance_id
        or trigger.get("dice_roll_state") != validate_json_value(initial.to_payload())
    ):
        raise GameLifecycleError("Charge Command Re-roll dice or action authority drift.")
