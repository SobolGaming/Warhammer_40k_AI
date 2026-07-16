from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import PlacementError, geometry_model_for_placement
from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def geometry_models_for_rules_unit(
    *, state: GameState, unit_instance_id: str
) -> tuple[GeometryModel, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Rules-unit geometry requires battlefield state.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    models_by_id = {model.model_instance_id: model for model in rules_unit.own_models}
    geometry_models: list[GeometryModel] = []
    for component in rules_unit.components:
        try:
            unit_placement = battlefield.unit_placement_by_id(component.unit.unit_instance_id)
        except PlacementError as exc:
            if any(model.is_alive for model in component.unit.own_models):
                raise GameLifecycleError(
                    "Rules-unit geometry requires placed alive units."
                ) from exc
            continue
        for placement in unit_placement.model_placements:
            model = models_by_id.get(placement.model_instance_id)
            if model is None or not model_is_present_on_battlefield(
                state=state,
                model_instance_id=placement.model_instance_id,
            ):
                continue
            geometry_models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(geometry_models)
