from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    validate_destruction_reaction_context_matches_sequence,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus


def invalid_destruction_reaction_context_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    attack_sequence: AttackSequence | None,
) -> LifecycleStatus | None:
    if rule_model_destruction.is_rule_model_destruction_reaction_request(request):
        return rule_model_destruction.invalid_rule_model_destruction_reaction_status(
            state=state,
            request=request,
            result=result,
        )
    request_payload = request.payload
    if not isinstance(request_payload, Mapping):
        raise GameLifecycleError("Destruction reaction request payload must be an object.")
    destruction_context = request_payload.get("destruction_context")
    if not isinstance(destruction_context, Mapping):
        raise GameLifecycleError("Destruction reaction context must be an object.")
    if attack_sequence is None:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Destruction reaction has no active attack sequence.",
            payload={
                "invalid_reason": "invalid_destruction_reaction_result",
                "field": "attack_sequence",
            },
        )
    try:
        validate_destruction_reaction_context_matches_sequence(
            attack_sequence=attack_sequence,
            destruction_context=validate_json_value(destruction_context),
        )
    except GameLifecycleError as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Destruction reaction context no longer matches state.",
            payload={
                "invalid_reason": "invalid_destruction_reaction_result",
                "field": "destruction_context",
                "diagnostic": str(exc),
            },
        )
    return None
