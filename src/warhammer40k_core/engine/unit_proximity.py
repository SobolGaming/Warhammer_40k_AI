from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.ability_presence import (
    AbilitySpatialRelationship,
    ability_spatial_relationship,
    active_ability_model_ids_for_unit,
)
from warhammer40k_core.engine.battlefield_state import (
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    current_rules_unit_is_physically_engaged,
)
from warhammer40k_core.engine.retained_model_presence import model_is_present_on_battlefield
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
    rules_unit_views_for_state,
)
from warhammer40k_core.engine.unit_factory import ModelInstance
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def unit_within_enemy_engagement_range(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    _require_game_state(state, operation="Engagement range check")
    return current_rules_unit_is_physically_engaged(
        state=state,
        unit_instance_id=unit_instance_id,
    )


def rules_unit_within_friendly_keyworded_models(
    *,
    state: GameState,
    source_unit_instance_id: str,
    required_keyword_sequence: tuple[str, ...],
    max_range_inches: float,
) -> bool:
    _require_game_state(state, operation="Keyworded-model proximity")
    if state.battlefield_state is None:
        raise GameLifecycleError("Keyworded-model proximity requires battlefield_state.")
    source_unit_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    required_keywords = _required_keyword_sequence(required_keyword_sequence)
    if type(max_range_inches) not in (int, float):
        raise GameLifecycleError("Keyworded-model proximity range must be numeric.")
    if max_range_inches <= 0:
        raise GameLifecycleError("Keyworded-model proximity range must be positive.")
    source_view = rules_unit_view_by_id(state=state, unit_instance_id=source_unit_id)
    source_models = _geometry_models_for_present_models(
        state=state,
        models=source_view.own_models,
    )
    for army in state.army_definitions:
        if army.player_id != source_view.owner_player_id:
            continue
        for unit in army.units:
            component_keywords = {*unit.keywords, *unit.faction_keywords}
            if not required_keywords.issubset(component_keywords):
                continue
            if not active_ability_model_ids_for_unit(state=state, unit=unit):
                continue
            candidate_view = rules_unit_view_by_id(
                state=state, unit_instance_id=unit.unit_instance_id
            )
            relationship = ability_spatial_relationship(
                state=state, source=source_view, target=candidate_view
            )
            if relationship is AbilitySpatialRelationship.OWN_ABILITY:
                return True
            if relationship is not AbilitySpatialRelationship.BATTLEFIELD:
                continue
            candidate_models = _geometry_models_for_present_models(
                state=state,
                models=unit.own_models,
            )
            if any(
                source_model.range_to(candidate_model) <= float(max_range_inches)
                for source_model in source_models
                for candidate_model in candidate_models
            ):
                return True
    return False


def rules_unit_within_friendly_keyworded_units(
    *,
    state: GameState,
    source_unit_instance_id: str,
    required_keyword_sequence: tuple[str, ...],
    max_range_inches: float,
) -> bool:
    _require_game_state(state, operation="Keyworded-unit proximity")
    if state.battlefield_state is None:
        raise GameLifecycleError("Keyworded-unit proximity requires battlefield_state.")
    source_unit_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    required_keywords = _required_keyword_sequence(required_keyword_sequence)
    if type(max_range_inches) not in (int, float):
        raise GameLifecycleError("Keyworded-unit proximity range must be numeric.")
    if max_range_inches <= 0:
        raise GameLifecycleError("Keyworded-unit proximity range must be positive.")
    source_view = rules_unit_view_by_id(state=state, unit_instance_id=source_unit_id)
    source_models = _geometry_models_for_present_models(
        state=state,
        models=source_view.own_models,
    )
    for candidate_view in rules_unit_views_for_state(state=state):
        if candidate_view.owner_player_id != source_view.owner_player_id:
            continue
        candidate_keywords = {*candidate_view.keywords, *candidate_view.faction_keywords}
        if not required_keywords.issubset(candidate_keywords):
            continue
        relationship = ability_spatial_relationship(
            state=state, source=source_view, target=candidate_view
        )
        if relationship is AbilitySpatialRelationship.OWN_ABILITY:
            return True
        if relationship is not AbilitySpatialRelationship.BATTLEFIELD:
            continue
        candidate_models = _geometry_models_for_present_models(
            state=state,
            models=candidate_view.own_models,
        )
        if any(
            source_model.range_to(candidate_model) <= float(max_range_inches)
            for source_model in source_models
            for candidate_model in candidate_models
        ):
            return True
    return False


def _geometry_models_for_present_models(
    *,
    state: GameState,
    models: tuple[ModelInstance, ...],
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Model geometry lookup requires battlefield_state.")
    placed_models = tuple(
        model
        for model in models
        if model_is_present_on_battlefield(state=state, model_instance_id=model.model_instance_id)
    )
    return tuple(
        geometry_model_for_placement(
            model=model,
            placement=state.battlefield_state.model_placement_by_id(model.model_instance_id),
        )
        for model in placed_models
    )


def _required_keyword_sequence(values: tuple[str, ...]) -> frozenset[str]:
    if type(values) is not tuple or not values:
        raise GameLifecycleError("required_keyword_sequence must be a non-empty tuple.")
    return frozenset(
        _validate_identifier("required_keyword_sequence value", value) for value in values
    )


def _require_game_state(state: object, *, operation: str) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(f"{operation} requires GameState.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
