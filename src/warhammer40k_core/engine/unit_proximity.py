from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
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
    source_view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    engagement_policy = state.runtime_ruleset_descriptor().engagement_policy
    unit_models = _geometry_models_for_alive_models(
        state=state,
        models=source_view.alive_models(),
    )
    for enemy_view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if enemy_view.owner_player_id == source_view.owner_player_id:
            continue
        enemy_models = _geometry_models_for_alive_models(
            state=state,
            models=enemy_view.alive_models(),
        )
        if _any_models_within_engagement_range(
            unit_models,
            enemy_models,
            horizontal_inches=engagement_policy.horizontal_inches,
            vertical_inches=engagement_policy.vertical_inches,
        ):
            return True
    return False


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
    source_models = _geometry_models_for_alive_models(
        state=state,
        models=source_view.alive_models(),
    )
    if not source_models:
        return False
    for army in state.army_definitions:
        if army.player_id != source_view.owner_player_id:
            continue
        for unit in army.units:
            component_keywords = {*unit.keywords, *unit.faction_keywords}
            if not required_keywords.issubset(component_keywords):
                continue
            candidate_models = _geometry_models_for_alive_models(
                state=state,
                models=tuple(model for model in unit.own_models if model.is_alive),
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
    source_models = _geometry_models_for_alive_models(
        state=state,
        models=source_view.alive_models(),
    )
    if not source_models:
        return False
    for candidate_view in rules_unit_views_from_armies(armies=tuple(state.army_definitions)):
        if candidate_view.owner_player_id != source_view.owner_player_id:
            continue
        candidate_keywords = {*candidate_view.keywords, *candidate_view.faction_keywords}
        if not required_keywords.issubset(candidate_keywords):
            continue
        candidate_models = _geometry_models_for_alive_models(
            state=state,
            models=candidate_view.alive_models(),
        )
        if any(
            source_model.range_to(candidate_model) <= float(max_range_inches)
            for source_model in source_models
            for candidate_model in candidate_models
        ):
            return True
    return False


def _geometry_models_for_alive_models(
    *,
    state: GameState,
    models: tuple[ModelInstance, ...],
) -> tuple[GeometryModel, ...]:
    if state.battlefield_state is None:
        raise GameLifecycleError("Model geometry lookup requires battlefield_state.")
    placed_model_ids = frozenset(state.battlefield_state.placed_model_ids())
    placed_models = tuple(
        model for model in models if model.is_alive and model.model_instance_id in placed_model_ids
    )
    return tuple(
        geometry_model_for_placement(
            model=model,
            placement=state.battlefield_state.model_placement_by_id(model.model_instance_id),
        )
        for model in placed_models
    )


def _any_models_within_engagement_range(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    *,
    horizontal_inches: float,
    vertical_inches: float,
) -> bool:
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(
                second_model,
                horizontal_inches=horizontal_inches,
                vertical_inches=vertical_inches,
            ):
                return True
    return False


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
