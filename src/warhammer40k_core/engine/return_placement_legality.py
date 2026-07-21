from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import model_is_within_battlefield_footprint
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

_OVERLAP_EPSILON = 1e-9


def validate_returned_model_endpoints(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    placements: tuple[ModelPlacement, ...],
    placement_label: str,
) -> None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Returned-model placement validation requires GameState.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Returned-model placement validation requires ruleset.")
    if not placements:
        raise GameLifecycleError("Returned-model placement validation requires placements.")
    if state.battlefield_state is None:
        raise GameLifecycleError("Returned-model placement validation requires battlefield_state.")
    scenario = BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )
    returning_ids = {placement.model_instance_id for placement in placements}
    if len(returning_ids) != len(placements):
        raise GameLifecycleError("Returned-model placements must be unique.")
    returned_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in placements
    )
    blockers = tuple(
        model for model in scenario.placed_geometry_models() if model.model_id not in returning_ids
    )
    for model in returned_models:
        if not model_is_within_battlefield_footprint(
            model,
            battlefield_width_inches=state.battlefield_state.battlefield_width_inches,
            battlefield_depth_inches=state.battlefield_state.battlefield_depth_inches,
        ):
            raise GameLifecycleError(f"{placement_label} crosses the battlefield edge.")
        for blocker in blockers:
            if _models_overlap(model, blocker):
                raise GameLifecycleError(f"{placement_label} overlaps another model.")
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=_unit_for_model(state=state, model_instance_id=model.model_id),
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=state.battlefield_state.terrain_features,
            violation_code="return_terrain_endpoint_illegal",
            placement_label=placement_label,
        )
        if terrain_violation is not None:
            raise GameLifecycleError(terrain_violation.message)
    for index, first in enumerate(returned_models):
        for second in returned_models[index + 1 :]:
            if _models_overlap(first, second):
                raise GameLifecycleError(f"{placement_label} models overlap each other.")


def _models_overlap(first: Model, second: Model) -> bool:
    return first.base_overlaps(second) and (
        first.volume.vertical_gap_to(first.pose, second.volume, second.pose) <= _OVERLAP_EPSILON
    )


def _unit_for_model(*, state: GameState, model_instance_id: str) -> UnitInstance:
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == model_instance_id for model in unit.own_models):
                return unit
    raise GameLifecycleError("Returned-model placement references an unknown model.")


__all__ = ("validate_returned_model_endpoints",)
