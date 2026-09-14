"""Explicit fixture choices through the common finite-decision facade."""

from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import LifecycleStatus


def choose_charge_targets(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    target_ids: tuple[str, ...],
    result_id: str,
) -> LifecycleStatus:
    assert request.decision_type == "select_charge_targets"
    option = next(
        option
        for option in request.options
        if isinstance(option.payload, dict) and option.payload["target_ids"] == list(target_ids)
    )
    return lifecycle.submit_decision(
        FiniteOptionSubmission(
            request_id=request.request_id, selected_option_id=option.option_id, result_id=result_id
        ).to_result(request)
    )
