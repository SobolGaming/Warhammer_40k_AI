"""One authority entry point for finite per-move capability commitments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.flight_decision_authority import (
    invalid_flight_authority,
    validate_restored_flight,
)
from warhammer40k_core.engine.move_keyword_authority import (
    invalid_move_keyword_authority,
    validate_restored_move_keywords,
)
from warhammer40k_core.engine.phase import LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def invalid_movement_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    return invalid_flight_authority(
        state=state, decisions=decisions, request=request, result=result
    ) or invalid_move_keyword_authority(
        state=state,
        decisions=decisions,
        request=request,
        result=result,
    )


def validate_restored_movement(*, state: GameState, decisions: DecisionController) -> None:
    validate_restored_flight(state=state, decisions=decisions)
    validate_restored_move_keywords(state=state, decisions=decisions)
    from warhammer40k_core.engine.move_keyword_completion import validate_move_keyword_history

    validate_move_keyword_history(state=state, decisions=decisions)
