"""Explicit Core geometry contracts; these shapes are not native datasheets."""

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model


def witnessed_query(
    source: Model,
    end: Pose,
    budget: float,
    goal: MovementGoal,
    enemies: tuple[Model, ...] = (),
) -> MovementReachabilityQuery:
    legality = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.CHARGE if enemies else MovementMode.NORMAL,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CHARGE_MOVE
        if enemies
        else ModelDisplacementKind.NORMAL_MOVE,
    )
    witness = PathWitness.for_paths(((source.model_id, (source.pose, end)),))
    return MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=source,
            witness=witness,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            enemy_models=enemies,
            movement_distance_budget_inches=budget,
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=source, witness=witness, terrain=(), terrain_features=()
        ),
        goal=goal,
        prove_coherent_endpoint_exclusion=True,
    )
