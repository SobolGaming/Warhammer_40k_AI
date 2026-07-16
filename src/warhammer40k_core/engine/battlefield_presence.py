from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.fight_on_death import (
    fight_on_death_model_ids_awaiting_attack,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def battlefield_scenario_for_state(*, state: GameState) -> BattlefieldScenario:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Battlefield scenario requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
        present_destroyed_model_ids=fight_on_death_model_ids_awaiting_attack(state=state),
    )
