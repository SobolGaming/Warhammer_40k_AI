from __future__ import annotations

from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
    apply_source_backed_attack_dice_reroll_decision,
)
from warhammer40k_core.engine.catalog_selected_target_battle_shock_continuation import (
    CatalogSelectedTargetBattleShockRuntime,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.fight_order import FightPhaseState
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def apply_fight_dice_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
    selected_target_runtime: CatalogSelectedTargetBattleShockRuntime,
) -> LifecycleStatus | None:
    if type(state.fight_phase_state) is not FightPhaseState:
        raise GameLifecycleError("Fight phase state is unavailable.")
    handled, status = selected_target_runtime.apply_reroll_if_applicable(
        state=state,
        decisions=decisions,
        result=result,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if handled:
        return status
    attack_sequence = state.fight_phase_state.attack_sequence
    if attack_sequence is None:
        raise GameLifecycleError("Fight dice reroll requires an active attack sequence.")
    apply_source_backed_attack_dice_reroll_decision(
        state=state,
        result=result,
        decisions=decisions,
        attack_sequence=attack_sequence,
        expected_phase=BattlePhase.FIGHT,
        phase_label="Fight",
        runtime_modifier_registry=runtime_modifier_registry,
    )
    return None


__all__ = ("apply_fight_dice_reroll_decision",)
