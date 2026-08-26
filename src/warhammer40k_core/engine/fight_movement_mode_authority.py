from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    RulesetDescriptor,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.fight_movement_source import (
    fight_movement_source_model_placements,
)
from warhammer40k_core.engine.fight_resolution import (
    CONSOLIDATE_ENEMY_DISTANCE_INCHES,
    PILE_IN_TARGET_DISTANCE_INCHES,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.rules_units import (
    RulesUnitView,
    placed_alive_rules_unit_views,
    rules_unit_view_by_id,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model as GeometryModel

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def legal_pile_in_target_rules_unit_ids(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    state: GameState,
) -> tuple[str, ...]:
    rules_unit = _canonical_rules_unit(state=state, unit_instance_id=unit_instance_id)
    if not rules_unit.alive_models():
        return ()
    targetable = _targetable_enemy_rules_units(state=state, rules_unit=rules_unit)
    targetable_ids = {target.unit_instance_id for target in targetable}
    physically_engaged_ids = scenario_physically_engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    if physically_engaged_ids:
        return tuple(
            target_id for target_id in physically_engaged_ids if target_id in targetable_ids
        )
    source_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    return tuple(
        target.unit_instance_id
        for target in targetable
        if _closest_distance(
            source_models,
            physical_geometry_models_for_rules_unit(
                scenario=scenario,
                unit_instance_id=target.unit_instance_id,
            ),
        )
        <= PILE_IN_TARGET_DISTANCE_INCHES
    )


def legal_consolidation_modes(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    objective_markers: tuple[ObjectiveMarker, ...],
    state: GameState,
) -> tuple[ConsolidationModeKind, ...]:
    rules_unit = _canonical_rules_unit(state=state, unit_instance_id=unit_instance_id)
    if not rules_unit.alive_models():
        return ()
    targetable = _targetable_enemy_rules_units(state=state, rules_unit=rules_unit)
    targetable_ids = {target.unit_instance_id for target in targetable}
    physically_engaged_ids = scenario_physically_engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    if physically_engaged_ids:
        return (
            (ConsolidationModeKind.ONGOING,)
            if targetable_ids.intersection(physically_engaged_ids)
            else ()
        )
    source_models = physical_geometry_models_for_rules_unit(
        scenario=scenario,
        unit_instance_id=rules_unit.unit_instance_id,
    )
    if any(
        _closest_distance(
            source_models,
            physical_geometry_models_for_rules_unit(
                scenario=scenario,
                unit_instance_id=target.unit_instance_id,
            ),
        )
        <= CONSOLIDATE_ENEMY_DISTANCE_INCHES
        for target in targetable
    ):
        return (ConsolidationModeKind.ENGAGING,)
    source_placements = fight_movement_source_model_placements(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if any(
        min(
            placement.pose.position.distance_2d_to(
                Pose.at(marker.x_inches, marker.y_inches).position
            )
            for placement in source_placements
        )
        <= 3.0
        for marker in objective_markers
    ):
        return (ConsolidationModeKind.OBJECTIVE,)
    return ()


def _canonical_rules_unit(*, state: GameState, unit_instance_id: str) -> RulesUnitView:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=requested_id)
    if rules_unit.unit_instance_id != requested_id:
        raise GameLifecycleError("Fight movement rules-unit identity must be canonical.")
    return rules_unit


def _targetable_enemy_rules_units(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
) -> tuple[RulesUnitView, ...]:
    return tuple(
        candidate
        for candidate in placed_alive_rules_unit_views(state=state)
        if candidate.owner_player_id != rules_unit.owner_player_id
    )


def _closest_distance(
    first_models: tuple[GeometryModel, ...],
    second_models: tuple[GeometryModel, ...],
) -> float:
    if not first_models or not second_models:
        raise GameLifecycleError("Fight movement target distance requires present models.")
    return min(first.range_to(second) for first in first_models for second in second_models)


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "legal_consolidation_modes",
    "legal_pile_in_target_rules_unit_ids",
)
