"""Stratagem opportunities between ordinary Charge activations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.stratagems_model import (
    StratagemCatalogIndex,
    StratagemEligibilityContext,
)
from warhammer40k_core.engine.stratagems_requests import request_phase_preselection_stratagem
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry


def charge_preselection_context(state: GameState) -> StratagemEligibilityContext | None:
    charge = state.charge_phase_state
    if (
        state.current_battle_phase is not BattlePhase.CHARGE
        or charge is None
        or charge.phase_complete
        or charge.active_selection is not None
        or charge.interruption is not None
        or charge.active_player_id != state.active_player_id
        or charge.battle_round != state.battle_round
    ):
        return None
    return StratagemEligibilityContext.from_state(
        state=state,
        player_id=charge.active_player_id,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        timing_window_id=(
            f"charge-preselection:round-{charge.battle_round}:"
            f"player-{charge.active_player_id}:selected-{len(charge.selected_unit_ids)}"
        ),
    )


def request_charge_preselection_stratagem(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    cost_modifiers: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    context = charge_preselection_context(state)
    if context is None:
        return None
    return request_phase_preselection_stratagem(
        state=state,
        decisions=decisions,
        stratagem_index=stratagem_index,
        cost_modifiers=cost_modifiers,
        context=context,
    )
