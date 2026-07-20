from __future__ import annotations

from warhammer40k_core.engine.catalog_conditional_leader_queries import (
    conditional_granted_ability_effects_for_unit,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.engine.unit_abilities import unit_has_infiltrators


def rules_unit_has_infiltrators(*, state: GameState, view: RulesUnitView) -> bool:
    return all(
        _component_has_infiltrators(state=state, view=view, component_index=index)
        for index in range(len(view.components))
    )


def rules_unit_has_mixed_infiltrators(*, state: GameState, view: RulesUnitView) -> bool:
    states = tuple(
        _component_has_infiltrators(state=state, view=view, component_index=index)
        for index in range(len(view.components))
    )
    return any(states) and not all(states)


def _component_has_infiltrators(
    *,
    state: GameState,
    view: RulesUnitView,
    component_index: int,
) -> bool:
    component = view.components[component_index]
    return unit_has_infiltrators(component.unit) or bool(
        conditional_granted_ability_effects_for_unit(
            state=state,
            rules_unit_instance_id=view.unit_instance_id,
            component_unit_instance_id=component.unit.unit_instance_id,
            ability="infiltrators",
        )
    )
