"""State-only shooting restrictions shared by shooting and source-backed consumers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_prevents_rules_unit_from_shooting_this_phase,
)


def shooting_state_restriction_reason(
    *, state: GameState, rules_unit: RulesUnitView, player_id: str
) -> str | None:
    from warhammer40k_core.engine.firing_deck_restrictions import firing_deck_prevents_shooting
    from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason

    if firing_deck_prevents_shooting(state=state, rules_unit=rules_unit):
        return "firing_deck"
    reason = large_model_activity_reason(state, rules_unit.unit_instance_id, "ranged_attacks")
    if reason is not None:
        return reason
    if mission_action_prevents_rules_unit_from_shooting_this_phase(
        state=state, player_id=player_id, unit_instance_id=rules_unit.unit_instance_id
    ):
        return "started_action"
    for unit_id in (rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids):
        history = state.fell_back_unit_state_for_unit(
            player_id=player_id, battle_round=state.battle_round, unit_instance_id=unit_id
        )
        if history is not None and not history.can_shoot:
            return "fell_back"
    return None
