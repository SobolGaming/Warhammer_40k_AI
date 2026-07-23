from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence import (
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    apply_attack_weapon_group_decision,
    apply_post_roll_attack_pool_decision,
    apply_resolve_target_unit_decision,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def apply_fight_attack_sequence_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.attack_sequence is None:
        raise GameLifecycleError("Fight attack sequence selection requires attack_sequence.")
    if result.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        attack_sequence = apply_resolve_target_unit_decision(
            decisions=decisions,
            attack_sequence=fight_state.attack_sequence,
            result=result,
        )
    elif result.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        attack_sequence = apply_attack_weapon_group_decision(
            decisions=decisions,
            attack_sequence=fight_state.attack_sequence,
            result=result,
        )
    elif result.decision_type == SELECT_POST_ROLL_ATTACK_POOL_DECISION_TYPE:
        attack_sequence = apply_post_roll_attack_pool_decision(
            decisions=decisions,
            attack_sequence=fight_state.attack_sequence,
            result=result,
        )
    else:
        raise GameLifecycleError("Unsupported fight attack sequence selection decision type.")
    state.replace_fight_phase_state(
        fight_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=fight_state.allocated_model_ids_this_phase,
        )
    )
