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


def placed_alive_geometry_models_for_rules_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    """Return geometry for the placed living models in a rules unit."""
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Placed alive rules-unit geometry requires battlefield state.")
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    alive_model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    if not alive_model_ids.intersection(battlefield.placed_model_ids()):
        return ()
    return tuple(
        model
        for model in geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
        if model.model_id in alive_model_ids
    )


def placed_alive_geometry_models_for_component_unit(
    *,
    state: GameState,
    component_unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    """Return placed living geometry owned by one physical rules-unit component."""
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=component_unit_instance_id,
    )
    matching_components = tuple(
        component
        for component in rules_unit.components
        if component.unit.unit_instance_id == component_unit_instance_id
    )
    if len(matching_components) != 1:
        raise GameLifecycleError(
            "Component-unit geometry requires a physical component unit instance ID."
        )
    alive_model_ids = {
        model.model_instance_id
        for model in matching_components[0].unit.own_models
        if model.is_alive
    }
    if not alive_model_ids:
        return ()
    return tuple(
        model
        for model in placed_alive_geometry_models_for_rules_unit(
            state=state,
            unit_instance_id=rules_unit.unit_instance_id,
        )
        if model.model_id in alive_model_ids
    )
