from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.charge_target_continuation import (
    DECLINE_CHARGE_TARGETS_OPTION_ID,
    SELECT_CHARGE_TARGETS_DECISION_TYPE,
    charge_target_selection_request,
    current_charge_targets,
    next_charge_target_replacement,
    pending_charge,
    record_charge_target_selection,
)
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.target_replacement import replacement_selection

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def decision_dispatch_handlers(host: GameLifecycle) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validator(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        state = host._require_state()  # pyright: ignore[reportPrivateUsage]
        try:
            _validate_charge_target_choice(host, request, result)
        except (GameLifecycleError, DecisionError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={"invalid_reason": "charge_target_selection_context_drift"},
            )
        return None

    def applier(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        payload = record.request.option_by_id(result.selected_option_id).payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Charge target choice requires an object.")
        targets = payload["target_ids"]
        if result.selected_option_id == DECLINE_CHARGE_TARGETS_OPTION_ID:
            target_ids = None
        else:
            if not isinstance(targets, list) or any(type(target) is not str for target in targets):
                raise GameLifecycleError("Charge target choice requires target IDs.")
            target_ids = tuple(str(target) for target in targets)
        record_charge_target_selection(
            state=host._require_state(),  # pyright: ignore[reportPrivateUsage]
            decisions=host.decision_controller,
            request=record.request,
            result=result,
            target_ids=target_ids,
        )
        return host.advance_until_decision_or_terminal()

    return (
        DecisionDispatchHandler(
            decision_type=SELECT_CHARGE_TARGETS_DECISION_TYPE,
            pre_validator=pre_validator,
            applier=applier,
        ),
    )


def validate_charge_replacement(
    host: GameLifecycle,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    state = host._require_state()  # pyright: ignore[reportPrivateUsage]
    try:
        current = next_charge_target_replacement(
            state=state,
            handler=host._charge_phase_handler,  # pyright: ignore[reportPrivateUsage]
        )
        if current is None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Charge replacement is no longer available.",
                payload={"invalid_reason": "target_replacement_context_drift"},
            )
        replacement_selection(request=request, result=result, current=current)
    except (GameLifecycleError, DecisionError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=str(exc),
            payload={"invalid_reason": "target_replacement_context_drift"},
        )
    return None


def apply_charge_replacement(
    host: GameLifecycle,
    record: DecisionRecord,
    result: DecisionResult,
) -> LifecycleStatus:
    state = host._require_state()  # pyright: ignore[reportPrivateUsage]
    current = next_charge_target_replacement(
        state=state,
        handler=host._charge_phase_handler,  # pyright: ignore[reportPrivateUsage]
    )
    if current is None:
        raise GameLifecycleError("Prevalidated Charge replacement disappeared.")
    targets = replacement_selection(request=record.request, result=result, current=current)
    host.decision_controller.event_log.append(
        "target_replacement_resolved",
        {
            "context": current.to_payload(),
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "replacement_target_ids": None if targets is None else list(targets),
        },
    )
    record_charge_target_selection(
        state=state,
        decisions=host.decision_controller,
        request=record.request,
        result=result,
        target_ids=targets,
    )
    return host.advance_until_decision_or_terminal()


def _validate_charge_target_choice(
    host: GameLifecycle, request: DecisionRequest, result: DecisionResult
) -> None:
    state = host._require_state()  # pyright: ignore[reportPrivateUsage]
    if pending_charge(state).target_selection is not None:
        raise GameLifecycleError("Charge targets have already been selected.")
    budget, reachable = current_charge_targets(
        state=state,
        handler=host._charge_phase_handler,  # pyright: ignore[reportPrivateUsage]
    )
    expected = charge_target_selection_request(
        state=state,
        request_id=request.request_id,
        budget=budget,
        reachable=reachable,
    )
    if expected != request:
        raise GameLifecycleError("Charge target selection context drift.")
    result.validate_for_request(expected)
