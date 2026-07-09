from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView, rules_unit_view_from_armies
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.volume import Model


def target_within_shooting_selection_range(
    *,
    scenario: BattlefieldScenario,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    max_range_inches: object,
    attacker_model_instance_id: str | None = None,
) -> bool:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Shooting selection range query requires BattlefieldScenario.")
    attacking_unit_id = _validate_identifier(
        "attacking_unit_instance_id",
        attacking_unit_instance_id,
    )
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    attacker_model_id = _validate_optional_identifier(
        "attacker_model_instance_id",
        attacker_model_instance_id,
    )
    if not isinstance(max_range_inches, int | float) or type(max_range_inches) is bool:
        raise GameLifecycleError("Shooting selection range query requires numeric max range.")
    resolved_max_range = float(max_range_inches)
    if resolved_max_range <= 0.0:
        raise GameLifecycleError("Shooting selection range query requires positive max range.")
    target_rules_unit = rules_unit_view_from_armies(
        armies=scenario.armies,
        unit_instance_id=target_unit_id,
    )
    if attacker_model_id is None:
        target_distance = _closest_distance_between_unit_and_rules_unit(
            scenario=scenario,
            first_unit_id=attacking_unit_id,
            second_rules_unit=target_rules_unit,
        )
        return target_distance <= resolved_max_range
    attacker_placement = unit_placement_or_none(scenario, attacking_unit_id)
    if attacker_placement is None:
        raise GameLifecycleError("Shooting selection range query attacking unit is not placed.")
    target_placements = unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if target_placements is None:
        raise GameLifecycleError("Shooting selection range query target unit is not placed.")
    attacker_models = attacker_geometry_models(
        scenario=scenario,
        attacker_placement=attacker_placement,
        attacker_model_instance_id=attacker_model_id,
    )
    target_models = geometry_models_for_unit_placements(
        scenario=scenario,
        unit_placements=target_placements,
    )
    return bool(
        target_in_range_model_ids(
            attacker_models=attacker_models,
            target_models=target_models,
            range_inches=resolved_max_range,
        )
    )


def unit_placement_or_none(
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> UnitPlacement | None:
    return scenario.battlefield_state.unit_placement_or_none(unit_instance_id)


def unit_placements_for_rules_unit_or_none(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[UnitPlacement, ...] | None:
    placements: list[UnitPlacement] = []
    for component in rules_unit.components:
        placement = unit_placement_or_none(scenario, component.unit.unit_instance_id)
        if placement is None:
            if any(model.is_alive for model in component.unit.own_models):
                return None
            continue
        placements.append(placement)
    if not placements:
        return None
    return tuple(placements)


def geometry_models_for_unit_placements(
    *,
    scenario: BattlefieldScenario,
    unit_placements: tuple[UnitPlacement, ...],
) -> tuple[Model, ...]:
    return tuple(
        geometry_model
        for unit_placement in unit_placements
        for geometry_model in geometry_models_for_unit_placement(
            scenario=scenario,
            unit_placement=unit_placement,
        )
    )


def geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[Model, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for model_placement in unit_placement.model_placements
    )


def attacker_geometry_models(
    *,
    scenario: BattlefieldScenario,
    attacker_placement: UnitPlacement,
    attacker_model_instance_id: str | None,
) -> tuple[Model, ...]:
    models = geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=attacker_placement,
    )
    if attacker_model_instance_id is None:
        return models
    selected = tuple(model for model in models if model.model_id == attacker_model_instance_id)
    if not selected:
        raise GameLifecycleError("Selected attacker model is not placed in the attacker unit.")
    return selected


def target_in_range_model_ids(
    *,
    attacker_models: tuple[Model, ...],
    target_models: tuple[Model, ...],
    range_inches: int | float,
) -> tuple[str, ...]:
    ids: set[str] = set()
    for attacker_model in attacker_models:
        for target_model in target_models:
            if attacker_model.range_to(target_model) <= float(range_inches):
                ids.add(target_model.model_id)
    return tuple(sorted(ids))


def _closest_distance_between_unit_and_rules_unit(
    *,
    scenario: BattlefieldScenario,
    first_unit_id: str,
    second_rules_unit: RulesUnitView,
) -> float:
    first_placement = scenario.battlefield_state.unit_placement_by_id(first_unit_id)
    second_placements = unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=second_rules_unit,
    )
    if second_placements is None:
        raise GameLifecycleError("Distance to rules unit requires placed target models.")
    first_models = geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=first_placement,
    )
    second_models = geometry_models_for_unit_placements(
        scenario=scenario,
        unit_placements=second_placements,
    )
    distances = tuple(
        DistanceMeasurementContext.from_models(first_model, second_model).closest_distance_inches()
        for first_model in first_models
        for second_model in second_models
    )
    if not distances:
        raise GameLifecycleError("Distance between units requires placed models.")
    return min(distances)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
