from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.fight_on_death import model_is_present_on_battlefield
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def geometry_models_for_fight_unit(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
    state: GameState | None = None,
) -> tuple[GeometryModel, ...]:
    try:
        placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError("Fight unit placement is unavailable.") from exc
    return geometry_models_for_fight_unit_placement(
        scenario=scenario,
        unit_placement=placement,
        state=state,
    )


def geometry_model_for_fight_unit_model(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    model_instance_id: str,
) -> GeometryModel:
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placement in unit_placement.model_placements:
        if placement.model_instance_id != model_id:
            continue
        return geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
    raise GameLifecycleError("Fight model placement was not found.")


def geometry_models_for_fight_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    state: GameState | None = None,
) -> tuple[GeometryModel, ...]:
    models: list[GeometryModel] = []
    unit = scenario.unit_instance_for_placement(unit_placement)
    model_by_id = {model.model_instance_id: model for model in unit.own_models}
    for placement in unit_placement.model_placements:
        model = model_by_id.get(placement.model_instance_id)
        if model is None:
            continue
        scenario_presence = scenario.model_is_present_on_battlefield(model.model_instance_id)
        if state is not None and scenario_presence != model_is_present_on_battlefield(
            state=state,
            model_instance_id=model.model_instance_id,
        ):
            raise GameLifecycleError("Fight geometry battlefield presence snapshot drift.")
        if not scenario_presence:
            continue
        models.append(geometry_model_for_placement(model=model, placement=placement))
    return tuple(models)


def model_in_base_contact_with_enemy(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    model: GeometryModel,
    player_id: str,
    base_contact_epsilon: float,
    state: GameState | None,
) -> bool:
    del ruleset_descriptor
    return any(
        model.range_to(enemy_model) <= base_contact_epsilon
        for enemy_model in enemy_geometry_models_for_player(
            scenario=scenario,
            player_id=player_id,
            state=state,
        )
    )


def model_engaged_with_any(
    *,
    model: GeometryModel,
    target_models: tuple[GeometryModel, ...],
    ruleset_descriptor: RulesetDescriptor,
) -> bool:
    return any(
        model.is_within_engagement_range(
            target_model,
            horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
            vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
        )
        for target_model in target_models
    )


def closest_model_distance_to_units(
    *,
    scenario: BattlefieldScenario,
    model_instance_id: str,
    model_pose: Pose,
    target_unit_instance_ids: tuple[str, ...],
    state: GameState | None,
) -> float:
    model = geometry_model_for_fight_model_pose(
        scenario=scenario,
        unit_placement=scenario.battlefield_state.unit_placement_by_id(
            unit_id_for_fight_model(
                scenario=scenario,
                model_instance_id=model_instance_id,
            )
        ),
        model_instance_id=model_instance_id,
        pose=model_pose,
    )
    distances = [
        model.range_to(target_model)
        for target_id in target_unit_instance_ids
        for target_model in geometry_models_for_fight_unit(
            scenario=scenario,
            unit_instance_id=target_id,
            state=state,
        )
    ]
    if not distances:
        raise GameLifecycleError("Fight movement target distances require target models.")
    return min(distances)


def geometry_model_for_fight_model_pose(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    model_instance_id: str,
    pose: Pose,
) -> GeometryModel:
    selected = next(
        (
            placement
            for placement in unit_placement.model_placements
            if placement.model_instance_id == model_instance_id
        ),
        None,
    )
    if selected is None:
        raise GameLifecycleError("Fight movement model placement was not found.")
    return geometry_model_for_placement(
        model=scenario.model_instance_for_placement(selected),
        placement=selected.with_pose(pose),
    )


def closest_fight_unit_distance_inches(
    *,
    scenario: BattlefieldScenario,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
    state: GameState | None = None,
) -> float:
    first_models = geometry_models_for_fight_unit(
        scenario=scenario,
        unit_instance_id=first_unit_instance_id,
        state=state,
    )
    second_models = geometry_models_for_fight_unit(
        scenario=scenario,
        unit_instance_id=second_unit_instance_id,
        state=state,
    )
    if not first_models or not second_models:
        raise GameLifecycleError("Fight unit distance requires placed models.")
    return min(first.range_to(second) for first in first_models for second in second_models)


def enemy_fight_unit_ids_within_distance(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    distance_inches: float,
    state: GameState | None = None,
) -> tuple[str, ...]:
    return tuple(
        enemy_id
        for enemy_id in enemy_unit_ids_for_fight_placement(
            scenario=scenario,
            unit_placement=unit_placement,
        )
        if closest_fight_unit_distance_inches(
            scenario=scenario,
            first_unit_instance_id=unit_placement.unit_instance_id,
            second_unit_instance_id=enemy_id,
            state=state,
        )
        <= distance_inches
    )


def enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    state: GameState | None = None,
) -> tuple[GeometryModel, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    return tuple(
        model
        for placed_army in scenario.battlefield_state.placed_armies
        if placed_army.player_id != requested_player_id
        for unit_placement in placed_army.unit_placements
        for model in geometry_models_for_fight_unit_placement(
            scenario=scenario,
            unit_placement=unit_placement,
            state=state,
        )
    )


def enemy_unit_ids_for_fight_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[str, ...]:
    return tuple(
        unit.unit_instance_id
        for army in scenario.armies
        if army.player_id != unit_placement.player_id
        for unit in army.units
        if scenario.battlefield_state.is_unit_placed(unit.unit_instance_id)
    )


def unit_id_for_fight_model(*, scenario: BattlefieldScenario, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in scenario.armies:
        for unit in army.units:
            if requested_model_id in unit.own_model_ids():
                return unit.unit_instance_id
    raise GameLifecycleError("Fight model owner unit was not found.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
