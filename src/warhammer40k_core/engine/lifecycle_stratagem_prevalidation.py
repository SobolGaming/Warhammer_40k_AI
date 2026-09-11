from __future__ import annotations

# This extracted validator shares the lifecycle's configured engine owners.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing_submission_authority import (
    validate_loaded_timing_batch_authority,
)
from warhammer40k_core.engine.stratagem_timing_candidates import (
    validate_pending_timing_stratagem_request,
)
from warhammer40k_core.engine.stratagems import (
    invalid_stratagem_use_status,
    is_stratagem_window_decline_result,
    stratagem_window_decline_allowed,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def prevalidate_stratagem_decision(
    lifecycle: GameLifecycle, request: DecisionRequest, result: DecisionResult
) -> LifecycleStatus | None:
    state = lifecycle._require_state()
    result.validate_for_request(request)
    if lifecycle._result_resolves_active_reaction_frame(result):
        lifecycle.reaction_queue.validate_result(result)
    try:
        batch = validate_pending_timing_stratagem_request(
            decisions=lifecycle.decision_controller,
            request=request,
        )
        if batch is not None:
            validate_loaded_timing_batch_authority(
                state=state,
                decisions=lifecycle.decision_controller,
                batch=batch,
                config=lifecycle._require_config(),
                reaction_queue=lifecycle.reaction_queue,
                runtime_bundle_provider=lifecycle._require_runtime_content_bundle,
                shooting_handler_provider=lambda: lifecycle._shooting_phase_handler,
            )
    except (
        DecisionError,
        GameLifecycleError,
    ):
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Stratagem timing request is no longer authoritative.",
            payload={"invalid_reason": "stratagem_timing_authority_drift"},
        )
    if is_stratagem_window_decline_result(result):
        if not stratagem_window_decline_allowed(request=request, result=result):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Stratagem window decline is not allowed for this request.",
                payload={"invalid_reason": "decline_not_allowed"},
            )
        return None
    return invalid_stratagem_use_status(
        state=state,
        request=request,
        result=result,
        decisions=lifecycle.decision_controller,
        stratagem_cost_modifier_registry=lifecycle._require_runtime_content_bundle().stratagem_cost_modifier_registry,
    )
