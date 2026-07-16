from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import LifecycleStatus
from warhammer40k_core.engine.stratagems import stratagem_cost_increase_made_use_unaffordable

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.decision_result import DecisionResult
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry


def invalid_status_is_unaffordable_cost_increase(
    *,
    invalid_status: LifecycleStatus | None,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> bool:
    return (
        invalid_status is not None
        and isinstance(invalid_status.payload, dict)
        and invalid_status.payload.get("invalid_reason") == "insufficient_command_points"
        and stratagem_cost_increase_made_use_unaffordable(
            state=state,
            result=result,
            decisions=decisions,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
    )
