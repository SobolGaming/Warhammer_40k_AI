# pyright: reportPrivateUsage=false
"""Shooting decision preflight, shared by every lifecycle adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_TYPE_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.shooting import (
    invalid_catalog_post_shoot_decision_status as invalid_post_shoot_status,
)
from warhammer40k_core.engine.shooting_phase_start_hooks import (
    SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.shooting_unit_selected_hooks import (
    SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def pre_validate_shooting_decision(
    *, lifecycle: GameLifecycle, request: DecisionRequest, result: DecisionResult
) -> LifecycleStatus | None:
    state = lifecycle._require_state()
    if request.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
        result.validate_for_request(request)
        return lifecycle._shooting_phase_handler.invalid_shooting_unit_selection_status(
            state=state,
            request=request,
            result=result,
        )
    if request.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE:
        result.validate_for_request(request)
        invalid_status = lifecycle._shooting_phase_handler.invalid_shooting_type_selection_status(
            state=state,
            request=request,
            result=result,
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
        invalid_status = (
            lifecycle._shooting_phase_handler.invalid_shooting_unit_selected_grant_status(
                state=state,
                request=request,
                result=result,
            )
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
        result.validate_for_request(request)
        if lifecycle._result_resolves_active_reaction_frame(result):
            lifecycle.reaction_queue.validate_result(result)
        invalid_status = lifecycle._shooting_phase_handler.invalid_declaration_submission_status(
            state=state,
            request=request,
            result=result,
            decisions=lifecycle.decision_controller,
        )
        if invalid_status is not None:
            return invalid_status
    if request.decision_type == SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE:
        invalid_status = (
            lifecycle._shooting_phase_handler.invalid_shooting_phase_start_faction_rule_status(
                state=state,
                request=request,
                result=result,
                decisions=lifecycle.decision_controller,
            )
        )
        if invalid_status is not None:
            return invalid_status
    invalid_status = invalid_post_shoot_status(state=state, request=request, result=result)
    if invalid_status is not None:
        return invalid_status
    return None
