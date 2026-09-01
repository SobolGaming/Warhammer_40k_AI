from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def is_battle_shocked(state: GameState, unit_instance_id: str) -> bool:
    return rules_unit_is_battle_shocked(
        state=state,
        unit_instance_id=unit_instance_id,
    )
