from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.fight_on_death import (
    fight_on_death_model_ids_awaiting_attack,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    placed_alive_rules_unit_views,
    rules_unit_view_by_id,
)

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


def fight_present_rules_unit_views(*, state: GameState) -> tuple[RulesUnitView, ...]:
    """Enumerate rules units with living or Fight On Death-present models."""
    present_by_id = {
        view.unit_instance_id: view for view in placed_alive_rules_unit_views(state=state)
    }
    for model_id in fight_on_death_model_ids_awaiting_attack(state=state):
        physical_unit_id = state.unit_instance_id_for_model(model_id)
        view = rules_unit_view_by_id(state=state, unit_instance_id=physical_unit_id)
        if view.component_unit_id_for_model(model_id) != physical_unit_id:
            raise GameLifecycleError("Fight On Death present model rules-unit identity drift.")
        present_by_id[view.unit_instance_id] = view
    return tuple(present_by_id[unit_id] for unit_id in sorted(present_by_id))
