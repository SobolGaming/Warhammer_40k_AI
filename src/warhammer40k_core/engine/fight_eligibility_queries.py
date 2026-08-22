from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import FightPolicyDescriptor
from warhammer40k_core.engine.fight_order import (
    FightPhaseState,
    fight_eligibility_reasons_for_unit,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_identity_history_contains

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def unit_was_eligible_to_fight_this_phase(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    unit_instance_id: str,
    policy: FightPolicyDescriptor,
) -> bool:
    if type(fight_state) is not FightPhaseState:
        raise GameLifecycleError("Fight eligibility history requires FightPhaseState.")
    if unit_was_selected_to_fight_this_phase(
        state=state,
        fight_state=fight_state,
        unit_instance_id=unit_instance_id,
    ):
        return True
    return bool(
        fight_eligibility_reasons_for_unit(
            state=state,
            fight_state=fight_state,
            unit_instance_id=unit_instance_id,
            policy=policy,
        )
    )


def unit_was_selected_to_fight_this_phase(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    unit_instance_id: str,
) -> bool:
    if type(fight_state) is not FightPhaseState:
        raise GameLifecycleError("Fight selection history requires FightPhaseState.")
    return rules_unit_identity_history_contains(
        state=state,
        identity_ids=fight_state.fight_order_state.selected_to_fight_unit_ids,
        unit_instance_id=unit_instance_id,
    )
