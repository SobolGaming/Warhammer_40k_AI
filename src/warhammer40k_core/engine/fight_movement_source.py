from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.fight_rules_unit_movement_types import (
    FightRulesUnitPlacement,
)
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import RulesUnitView
from warhammer40k_core.geometry.pathing import PathValidationResult, PathWitness
from warhammer40k_core.geometry.volume import Model as GeometryModel


def fight_movement_source_model_placements(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[ModelPlacement, ...]:
    """Return the living placements that may move for one Fight rules unit."""
    living_model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    placements: list[ModelPlacement] = []
    for component in rules_unit.components:
        living_component_model_ids = living_model_ids.intersection(component.unit.own_model_ids())
        unit_placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if unit_placement is None:
            if living_component_model_ids:
                raise GameLifecycleError(
                    "Fight movement requires every living component to be placed."
                )
            continue
        placed_living = tuple(
            placement
            for placement in unit_placement.model_placements
            if placement.model_instance_id in living_component_model_ids
        )
        if {
            placement.model_instance_id for placement in placed_living
        } != living_component_model_ids:
            raise GameLifecycleError("Fight movement living model placement inventory drift.")
        placements.extend(placed_living)
    if not placements:
        raise GameLifecycleError("Fight movement requires living movable models.")
    return tuple(sorted(placements, key=lambda placement: placement.model_instance_id))


def fight_movement_source_geometry_models(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in fight_movement_source_model_placements(
            scenario=scenario,
            rules_unit=rules_unit,
        )
    )


def retained_fight_movement_source_geometry_models(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[GeometryModel, ...]:
    """Return retained destroyed source bases that remain fixed during movement."""
    living_model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    placements: list[ModelPlacement] = []
    for component in rules_unit.components:
        unit_placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if unit_placement is None:
            if any(model.is_alive for model in component.unit.own_models):
                raise GameLifecycleError(
                    "Fight movement requires every living component to be placed."
                )
            continue
        placements.extend(
            placement
            for placement in unit_placement.model_placements
            if placement.model_instance_id not in living_model_ids
            and scenario.model_is_present_at_placement(placement)
        )
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in sorted(placements, key=lambda value: value.model_instance_id)
    )


def retained_fight_movement_source_path_violations(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    witness: PathWitness | None,
    movement_mode: MovementMode,
    displacement_kind: ModelDisplacementKind,
    maximum_distance_inches: float,
) -> tuple[PathValidationResult, ...]:
    """Validate fixed retained bases without adding them to the movement witness."""
    if witness is None:
        return ()
    fixed_models = retained_fight_movement_source_geometry_models(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if not fixed_models:
        return ()
    invalid_results: list[PathValidationResult] = []
    for placement in fight_movement_source_model_placements(
        scenario=scenario,
        rules_unit=rules_unit,
    ):
        owning_components = tuple(
            component
            for component in rules_unit.components
            if placement.model_instance_id in component.unit.own_model_ids()
        )
        if len(owning_components) != 1:
            raise GameLifecycleError("Fight movement source model ownership drift.")
        component = owning_components[0]
        moving_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        model_witness = PathWitness.for_paths(
            (
                (
                    placement.model_instance_id,
                    witness.poses_for_model(placement.model_instance_id),
                ),
            )
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=component.unit.keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
            movement_phase_action=None,
            displacement_kind=displacement_kind,
        )
        result = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
            friendly_models=fixed_models,
            movement_distance_budget_inches=maximum_distance_inches,
        ).validate()
        if not result.is_valid:
            invalid_results.append(result)
    return tuple(invalid_results)


def fight_movement_source_component_placement(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> UnitPlacement:
    if rules_unit.is_attached_rules_unit:
        raise GameLifecycleError("Standalone Fight movement requires a physical rules unit.")
    placement = scenario.battlefield_state.unit_placement_by_id(rules_unit.unit_instance_id)
    movable_ids = {
        model_placement.model_instance_id
        for model_placement in fight_movement_source_model_placements(
            scenario=scenario,
            rules_unit=rules_unit,
        )
    }
    return placement.with_model_placements(
        tuple(
            model_placement
            for model_placement in placement.model_placements
            if model_placement.model_instance_id in movable_ids
        )
    )


def fight_movement_source_rules_unit_placement(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> FightRulesUnitPlacement:
    movable_model_ids = {
        placement.model_instance_id
        for placement in fight_movement_source_model_placements(
            scenario=scenario,
            rules_unit=rules_unit,
        )
    }
    components: list[UnitPlacement] = []
    for component in rules_unit.components:
        placement = scenario.battlefield_state.unit_placement_or_none(
            component.unit.unit_instance_id
        )
        if placement is None:
            continue
        selected = tuple(
            model_placement
            for model_placement in placement.model_placements
            if model_placement.model_instance_id in movable_model_ids
        )
        if selected:
            components.append(placement.with_model_placements(selected))
    return FightRulesUnitPlacement(
        rules_unit_instance_id=rules_unit.unit_instance_id,
        component_unit_placements=tuple(components),
    )


def fight_movement_source_scenario(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
    component_unit_placements: tuple[UnitPlacement, ...],
) -> BattlefieldScenario:
    """Build the resolver view with only living source models as movable models.

    Retained destroyed models belonging to other rules units remain present as
    collision geometry and, for a selectable mixed target rules unit, measurement
    geometry. Retained destroyed source placements are validated separately as fixed
    friendly bases.
    """
    attempted_by_component_id = {
        placement.unit_instance_id: placement for placement in component_unit_placements
    }
    if len(attempted_by_component_id) != len(component_unit_placements):
        raise GameLifecycleError("Fight movement scenario component IDs must be unique.")
    expected_source_placements = fight_movement_source_model_placements(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    expected_model_ids_by_component = {
        component.unit.unit_instance_id: {
            placement.model_instance_id
            for placement in expected_source_placements
            if placement.unit_instance_id == component.unit.unit_instance_id
        }
        for component in rules_unit.components
    }
    expected_component_ids = {
        component_id
        for component_id, model_ids in expected_model_ids_by_component.items()
        if model_ids
    }
    if set(attempted_by_component_id) != expected_component_ids:
        raise GameLifecycleError("Fight movement scenario component inventory drift.")
    for component_id, placement in attempted_by_component_id.items():
        if {
            model.model_instance_id for model in placement.model_placements
        } != expected_model_ids_by_component[component_id]:
            raise GameLifecycleError("Fight movement scenario model inventory drift.")
    battlefield = scenario.battlefield_state
    for component in rules_unit.components:
        component_id = component.unit.unit_instance_id
        attempted = attempted_by_component_id.get(component_id)
        if attempted is None:
            if battlefield.is_unit_placed(component_id):
                battlefield = battlefield.without_unit_placement(component_id)
            continue
        battlefield = battlefield.with_unit_placement(attempted)
    source_model_ids = {model.model_instance_id for model in rules_unit.own_models}
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=battlefield,
        present_destroyed_model_ids=tuple(
            model_id
            for model_id in scenario.present_destroyed_model_ids
            if model_id not in source_model_ids
        ),
    )


def merge_fight_movement_source_placement(
    *,
    current: UnitPlacement,
    attempted: UnitPlacement,
) -> UnitPlacement:
    if (
        current.army_id != attempted.army_id
        or current.player_id != attempted.player_id
        or current.unit_instance_id != attempted.unit_instance_id
    ):
        raise GameLifecycleError("Fight movement application placement identity drift.")
    attempted_by_model_id = {
        placement.model_instance_id: placement for placement in attempted.model_placements
    }
    current_model_ids = {placement.model_instance_id for placement in current.model_placements}
    if set(attempted_by_model_id) - current_model_ids:
        raise GameLifecycleError("Fight movement application model identity drift.")
    return current.with_model_placements(
        tuple(
            attempted_by_model_id.get(placement.model_instance_id, placement)
            for placement in current.model_placements
        )
    )


def require_fight_movement_source_matches_current(
    *,
    current: UnitPlacement,
    expected: UnitPlacement,
) -> None:
    if (
        current.army_id != expected.army_id
        or current.player_id != expected.player_id
        or current.unit_instance_id != expected.unit_instance_id
    ):
        raise GameLifecycleError("Rules-unit Fight movement application context drift.")
    current_by_model_id = {
        placement.model_instance_id: placement for placement in current.model_placements
    }
    if any(
        current_by_model_id.get(placement.model_instance_id) != placement
        for placement in expected.model_placements
    ):
        raise GameLifecycleError("Rules-unit Fight movement application context drift.")
