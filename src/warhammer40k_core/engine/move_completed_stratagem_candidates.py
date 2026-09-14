"""Catalog-driven Stratagem occurrences at a completed Charge move."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext

if TYPE_CHECKING:
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


def charge_move_stratagem_candidates(
    context: UnitMoveCompletedContext,
    *,
    stratagem_index: StratagemCatalogIndex,
    cost_modifiers: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.stratagem_timing_candidates import stratagem_timing_candidates
    from warhammer40k_core.engine.stratagems import StratagemEligibilityContext

    if (
        context.completed_phase is not BattlePhase.CHARGE
        or context.movement_action != "charge_move"
    ):
        return ()
    decisions = context.decisions
    if decisions is None:
        raise GameLifecycleError("Charge completion Stratagems require decisions.")
    return stratagem_timing_candidates(
        state=context.state,
        decisions=decisions,
        index=stratagem_index,
        context=StratagemEligibilityContext.from_state(
            state=context.state,
            player_id=context.triggering_player_id,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
            timing_window_id=f"charge-move-completed:{context.trigger_event_id}",
            trigger_payload={
                "triggering_unit_instance_id": context.triggering_unit_instance_id,
                "trigger_event_id": context.trigger_event_id,
            },
        ),
        cost_modifiers=cost_modifiers,
        requested_event_type="move_completed_stratagem_window_opened",
    )
