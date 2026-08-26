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


def rules_unit_has_placed_alive_model(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    model_instance_id: str | None = None,
) -> bool:
    """Return whether the rules unit has a matching living model placement."""
    battlefield = state.battlefield_state
    if battlefield is None:
        return False
    return _rules_unit_has_placed_alive_model(
        placed_model_ids=frozenset(battlefield.placed_model_ids()),
        rules_unit=rules_unit,
        model_instance_id=model_instance_id,
    )


def scenario_rules_unit_has_placed_alive_model(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
    model_instance_id: str | None = None,
) -> bool:
    """Return whether a scenario rules unit has a matching living model placement."""
    return _rules_unit_has_placed_alive_model(
        placed_model_ids=frozenset(scenario.battlefield_state.placed_model_ids()),
        rules_unit=rules_unit,
        model_instance_id=model_instance_id,
    )


def _rules_unit_has_placed_alive_model(
    *,
    placed_model_ids: frozenset[str],
    rules_unit: RulesUnitView,
    model_instance_id: str | None,
) -> bool:
    return any(
        model.is_alive
        and model.model_instance_id in placed_model_ids
        and (model_instance_id is None or model.model_instance_id == model_instance_id)
        for model in rules_unit.own_models
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
