from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.healing import (
    SELECT_HEALING_MODEL_DECISION_TYPE,
    HealingEffect,
    apply_recorded_healing_model_decision,
    healing_effect_from_request,
    invalid_healing_model_decision_status,
)
from warhammer40k_core.engine.healing_revival import (
    SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    apply_recorded_healing_revival_placement_decision,
    healing_effect_from_revival_request,
    invalid_healing_revival_placement_status,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

HEALING_DECISION_TYPES = frozenset(
    (
        SELECT_HEALING_MODEL_DECISION_TYPE,
        SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    )
)
PARAMETERIZED_HEALING_DECISION_TYPES = frozenset((SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,))


def invalid_healing_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    if request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
        return invalid_healing_model_decision_status(
            state=state,
            request=request,
            result=result,
        )
    if request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
        return invalid_healing_revival_placement_status(
            state=state,
            request=request,
            result=result,
            ruleset_descriptor=ruleset_descriptor,
        )
    raise GameLifecycleError("Unsupported healing decision type.")


def apply_recorded_healing_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    request: DecisionRequest,
    result: DecisionResult,
) -> tuple[HealingEffect, DecisionRequest | None]:
    if request.decision_type == SELECT_HEALING_MODEL_DECISION_TYPE:
        effect = healing_effect_from_request(request=request)
        return apply_recorded_healing_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            request=request,
            result=result,
            effect=effect,
        )
    if request.decision_type == SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE:
        effect = healing_effect_from_revival_request(request=request)
        return apply_recorded_healing_revival_placement_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            request=request,
            result=result,
            effect=effect,
        )
    raise GameLifecycleError("Unsupported healing decision type.")


__all__ = (
    "HEALING_DECISION_TYPES",
    "PARAMETERIZED_HEALING_DECISION_TYPES",
    "apply_recorded_healing_decision",
    "invalid_healing_decision_status",
)
