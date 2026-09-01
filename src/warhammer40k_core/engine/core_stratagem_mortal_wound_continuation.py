from __future__ import annotations

from typing import Literal

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.stratagems_effect_handlers import (
    apply_crushing_impact_mortal_wound_decision,
    apply_explosives_mortal_wound_feel_no_pain_decision,
)

_CRUSHING_IMPACT_SOURCE_KINDS = frozenset({"crushing_impact_self", "crushing_impact_enemy"})


def apply_core_stratagem_mortal_wound_decision_if_applicable(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    source_context: JsonValue,
) -> LifecycleStatus | None | Literal[False]:
    if not isinstance(source_context, dict):
        return False
    source_kind = source_context.get("source_kind")
    if source_kind in _CRUSHING_IMPACT_SOURCE_KINDS:
        return apply_crushing_impact_mortal_wound_decision(
            state=state,
            decisions=decisions,
            result=result,
        )
    if source_kind == "explosives":
        return apply_explosives_mortal_wound_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            result=result,
        )
    return False
