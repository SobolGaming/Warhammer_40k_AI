from __future__ import annotations

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fight_phase_end_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    invalid_fight_phase_end_faction_rule_status,
)
from warhammer40k_core.engine.fight_phase_start_hooks import (
    SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
    invalid_fight_phase_start_faction_rule_status,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

FIGHT_PHASE_FACTION_RULE_DECISION_TYPES = frozenset(
    (
        SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE,
        SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE,
    )
)


def invalid_fight_phase_faction_rule_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_START_OPTION_DECISION_TYPE:
        return invalid_fight_phase_start_faction_rule_status(
            state=state,
            request=request,
            result=result,
        )
    if request.decision_type == SELECT_FACTION_RULE_FIGHT_PHASE_END_OPTION_DECISION_TYPE:
        return invalid_fight_phase_end_faction_rule_status(
            state=state,
            request=request,
            result=result,
        )
    if request.decision_type in FIGHT_PHASE_FACTION_RULE_DECISION_TYPES:
        raise GameLifecycleError("Unsupported Fight phase faction-rule decision type.")
    return None
