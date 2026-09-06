"""P12 consumes the same source-backed objective geometry as Objective Control."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    ObjectiveModelDistance,
    measure_model_to_objective,
)
from warhammer40k_core.engine.objective_geometry_sources import mission_objective_geometries
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def consolidation_objectives(
    *, markers: tuple[ObjectiveMarker, ...], state: GameState | None
) -> tuple[ObjectiveGeometry, ...]:
    if state is not None and state.mission_setup is not None:
        return mission_objective_geometries(state)
    return tuple(ObjectiveGeometry.from_marker(marker) for marker in markers)


def consolidation_objective_by_id(
    *, objective_id: str | None, markers: tuple[ObjectiveMarker, ...], state: GameState | None
) -> ObjectiveGeometry:
    for objective in consolidation_objectives(markers=markers, state=state):
        if objective.objective_id == objective_id:
            return objective
    raise GameLifecycleError(
        "Consolidation objective identity is not in the authoritative context."
    )


def consolidation_objective_distances(
    *,
    scenario: BattlefieldScenario,
    placements: tuple[ModelPlacement, ...],
    objective: ObjectiveGeometry,
) -> tuple[ObjectiveModelDistance, ...]:
    return tuple(
        measure_model_to_objective(
            model=geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            ),
            objective=objective,
        )
        for placement in placements
    )


def legal_consolidation_objective_ids(
    *,
    scenario: BattlefieldScenario,
    placements: tuple[ModelPlacement, ...],
    markers: tuple[ObjectiveMarker, ...],
    state: GameState | None,
) -> tuple[str, ...]:
    return tuple(
        objective.objective_id
        for objective in consolidation_objectives(markers=markers, state=state)
        if any(
            distance.closest_distance_inches <= 3.0
            for distance in consolidation_objective_distances(
                scenario=scenario,
                placements=placements,
                objective=objective,
            )
        )
    )
