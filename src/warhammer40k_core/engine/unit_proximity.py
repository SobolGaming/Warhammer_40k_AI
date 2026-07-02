from __future__ import annotations

from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.volume import Model as GeometryModel


def unit_within_enemy_engagement_range(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    if type(state) is not GameState:
        raise GameLifecycleError("Engagement range check requires GameState.")
    owner = _owner_for_unit(tuple(state.army_definitions), unit_instance_id=unit_instance_id)
    unit_models = _unit_geometry_models(state=state, unit_instance_id=unit_instance_id)
    for army in state.army_definitions:
        if army.player_id == owner:
            continue
        for enemy_unit in army.units:
            enemy_models = _unit_geometry_models(
                state=state,
                unit_instance_id=enemy_unit.unit_instance_id,
            )
            if _any_models_within_engagement_range(unit_models, enemy_models):
                return True
    return False


def _unit_geometry_models(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Unit geometry lookup requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    unit_placement = state.battlefield_state.unit_placement_or_none(unit_instance_id)
    if unit_placement is None:
        return ()
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
        if scenario.model_instance_for_placement(model_placement).is_alive
    )


def _any_models_within_engagement_range(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> bool:
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(second_model):
                return True
    return False


def _owner_for_unit(armies: tuple[ArmyDefinition, ...], *, unit_instance_id: str) -> str:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in armies:
        if any(unit.unit_instance_id == requested_unit_id for unit in army.units):
            return army.player_id
    raise GameLifecycleError("Unit owner is unknown.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
