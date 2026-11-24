"""Stratagem opportunities between ordinary Charge activations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatus
from warhammer40k_core.engine.stratagems_model import (
    NOT_SELECTED_TO_CHARGE_TARGET_POLICY_ID,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
)
from warhammer40k_core.engine.stratagems_requests import (
    create_stratagem_use_decision_request,
    stratagem_decline_option,
    stratagem_use_options_from_index,
    stratagem_window_declined_for_context,
)
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
    records = tuple(
        record
        for record in stratagem_index.records_for(TimingTriggerKind.DURING_PHASE)
        if record.definition.target_spec.target_policy_id == NOT_SELECTED_TO_CHARGE_TARGET_POLICY_ID
    )
    if not records:
        return None
    context = charge_preselection_context(state)
    if context is None:
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=StratagemCatalogIndex.from_records(records),
        context=context,
        stratagem_cost_modifier_registry=cost_modifiers,
    )
    if not options or stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"phase_body_status": "charge_preselection_stratagem_pending"},
    )
