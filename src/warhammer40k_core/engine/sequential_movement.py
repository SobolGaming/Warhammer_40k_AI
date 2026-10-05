"""Shared physical occupancy while completing one witnessed model move at a time."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.volume import Model


def sequential_friendly_models(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    witness: PathWitness,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    """Earlier paths have completed; later paths still occupy their starting poses.

    The complete submitted witness is retained across attached component consumers.
    This builds validation geometry only: authoritative battlefield mutation remains
    atomic after every path, terrain and whole-group endpoint requirement passes.
    """
    if type(scenario) is not BattlefieldScenario or type(witness) is not PathWitness:
        raise GameLifecycleError("Sequential movement requires a scenario and complete witness.")
    friendly_models: list[Model] = []
    for army in scenario.battlefield_state.placed_armies:
        if army.player_id != player_id:
            continue
        for unit in army.unit_placements:
            for placement in unit.model_placements:
                model_id = placement.model_instance_id
                if model_id == moving_model_instance_id:
                    continue
                if not scenario.model_is_present_at_placement(placement):
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return sequential_peer_models(
        friendly_models=tuple(friendly_models),
        witness=witness,
        moving_model_instance_id=moving_model_instance_id,
    )


def sequential_peer_models(
    *,
    friendly_models: tuple[Model, ...],
    witness: PathWitness,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    """Share exact occupancy between live paths and accepted historical queries."""
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Sequential movement requires a complete witness.")
    ordered_ids = tuple(model_id for model_id, _poses in witness.model_paths)
    if moving_model_instance_id not in ordered_ids:
        raise GameLifecycleError("Sequential movement model is absent from the complete witness.")
    completed_ids = frozenset(ordered_ids[: ordered_ids.index(moving_model_instance_id)])
    paths = dict(witness.model_paths)
    return tuple(
        replace(
            model,
            pose=paths[model.model_id][-1]
            if model.model_id in completed_ids
            else paths[model.model_id][0],
        )
        if model.model_id in paths
        else model
        for model in sorted(friendly_models, key=lambda item: item.model_id)
        if model.model_id != moving_model_instance_id
    )
