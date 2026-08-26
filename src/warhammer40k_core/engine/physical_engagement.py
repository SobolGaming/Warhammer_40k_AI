from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_from_armies,
    rules_unit_views_from_armies,
)
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def current_physically_engaged_enemy_rules_unit_ids(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[str, ...]:
    """Return canonical enemy rules units in physical Engagement Range now."""

    _require_game_state(state)
    return scenario_physically_engaged_enemy_rules_unit_ids(
        scenario=battlefield_scenario_for_state(state=state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=unit_instance_id,
    )


def current_rules_unit_is_physically_engaged(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    """Return whether any battlefield-present opposing bases establish Engagement."""

    _require_game_state(state)
    return bool(
        current_physically_engaged_enemy_rules_unit_ids(
            state=state,
            unit_instance_id=unit_instance_id,
        )
    )


def current_closest_physical_enemy_distance_inches(
    *,
    state: GameState,
    unit_instance_id: str,
) -> float | None:
    _require_game_state(state)
    return scenario_closest_physical_enemy_distance_inches(
        scenario=battlefield_scenario_for_state(state=state),
        unit_instance_id=unit_instance_id,
    )


def scenario_physically_engaged_enemy_rules_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
) -> tuple[str, ...]:
    _require_scenario(scenario)
    _require_ruleset_descriptor(ruleset_descriptor)
    source_id = _validate_identifier("unit_instance_id", unit_instance_id)
    source_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=source_id,
    )
    if not source_models:
        return ()
    return tuple(
        sorted(
            candidate_id
            for candidate_id in scenario_physical_enemy_rules_unit_ids(
                scenario=scenario,
                unit_instance_id=source_id,
            )
            if _geometry_models_are_physically_engaged(
                first_models=source_models,
                second_models=physical_geometry_models_for_rules_unit(
                    scenario=scenario,
                    unit_instance_id=candidate_id,
                ),
                ruleset_descriptor=ruleset_descriptor,
            )
        )
    )


def scenario_physical_enemy_rules_unit_ids(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[str, ...]:
    _require_scenario(scenario)
    source = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return tuple(
        sorted(
            candidate.unit_instance_id
            for candidate in rules_unit_views_from_armies(armies=scenario.armies)
            if candidate.owner_player_id != source.owner_player_id
            and physical_geometry_models_for_rules_unit(
                scenario=scenario,
                unit_instance_id=candidate.unit_instance_id,
            )
        )
    )


def scenario_rules_units_are_physically_engaged(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> bool:
    _require_scenario(scenario)
    _require_ruleset_descriptor(ruleset_descriptor)
    first = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=_validate_identifier(
            "first_unit_instance_id",
            first_unit_instance_id,
        ),
    )
    second = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=_validate_identifier(
            "second_unit_instance_id",
            second_unit_instance_id,
        ),
    )
    if first.owner_player_id == second.owner_player_id:
        return False
    return _geometry_models_are_physically_engaged(
        first_models=physical_geometry_models_for_rules_unit(
            scenario=scenario,
            unit_instance_id=first.unit_instance_id,
        ),
        second_models=physical_geometry_models_for_rules_unit(
            scenario=scenario,
            unit_instance_id=second.unit_instance_id,
        ),
        ruleset_descriptor=ruleset_descriptor,
    )


def scenario_closest_physical_enemy_distance_inches(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> float | None:
    _require_scenario(scenario)
    source_id = _validate_identifier("unit_instance_id", unit_instance_id)
    source = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=source_id,
    )
    source_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=source.unit_instance_id,
    )
    distances = tuple(
        source_model.range_to(enemy_model)
        for candidate in rules_unit_views_from_armies(armies=scenario.armies)
        if candidate.owner_player_id != source.owner_player_id
        for source_model in source_models
        for enemy_model in physical_geometry_models_for_rules_unit(
            scenario=scenario,
            unit_instance_id=candidate.unit_instance_id,
        )
    )
    return None if not distances else min(distances)


def physical_geometry_models_for_rules_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[GeometryModel, ...]:
    """Return every battlefield-present base, including retained destroyed bases."""

    _require_scenario(scenario)
    rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    removed_model_ids = frozenset(scenario.battlefield_state.removed_model_ids)
    geometry_models: list[GeometryModel] = []
    for component in rules_unit.components:
        placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if placement is None:
            continue
        placed_model_ids = {
            model_placement.model_instance_id for model_placement in placement.model_placements
        }
        missing_living_ids = {
            model.model_instance_id
            for model in component.unit.own_models
            if model.is_alive
            and model.model_instance_id not in placed_model_ids
            and model.model_instance_id not in removed_model_ids
        }
        if missing_living_ids:
            raise GameLifecycleError(
                "Physical Engagement geometry is missing a living model placement."
            )
        geometry_models.extend(
            geometry_model_for_placement(
                model=scenario.model_instance_for_placement(model_placement),
                placement=model_placement,
            )
            for model_placement in placement.model_placements
            if scenario.model_is_present_at_placement(model_placement)
        )
    return tuple(sorted(geometry_models, key=lambda model: model.model_id))


def _geometry_models_are_physically_engaged(
    *,
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    policy = ruleset_descriptor.engagement_policy
    return any(
        first.is_within_engagement_range(
            second,
            horizontal_inches=policy.horizontal_inches,
            vertical_inches=policy.vertical_inches,
        )
        for first in first_models
        for second in second_models
    )


def _require_game_state(state: object) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Physical Engagement requires GameState.")


def _require_scenario(scenario: object) -> None:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Physical Engagement requires BattlefieldScenario.")


def _require_ruleset_descriptor(ruleset_descriptor: object) -> None:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Physical Engagement requires RulesetDescriptor.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "current_closest_physical_enemy_distance_inches",
    "current_physically_engaged_enemy_rules_unit_ids",
    "current_rules_unit_is_physically_engaged",
    "physical_geometry_models_for_rules_unit",
    "scenario_closest_physical_enemy_distance_inches",
    "scenario_physical_enemy_rules_unit_ids",
    "scenario_physically_engaged_enemy_rules_unit_ids",
    "scenario_rules_units_are_physically_engaged",
)
