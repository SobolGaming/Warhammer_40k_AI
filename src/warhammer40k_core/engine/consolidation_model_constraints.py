"""Shared per-model Consolidation obligations over physical rules-unit geometry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import (
    CoherencyPolicyKind,
    ConsolidationModeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.consolidation_objectives import consolidation_objective_by_id
from warhammer40k_core.engine.fight_geometry import geometry_models_for_fight_unit
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_from_armies
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import FightMovementProposal
    from warhammer40k_core.engine.game_state import GameState


def consolidation_model_violation(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    proposal_request: MovementProposalRequest,
    proposal: FightMovementProposal,
    before: tuple[ModelPlacement, ...],
    after: tuple[ModelPlacement, ...],
    state: GameState | None,
) -> str | None:
    from warhammer40k_core.engine.fight_resolution import fight_objective_markers_from_context

    targets: dict[str, tuple[Model, ...]] = {}
    for target_id in proposal.consolidate_target_unit_instance_ids:
        target = rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=target_id)
        targets[target.unit_instance_id] = tuple(
            model
            for component_id in target.component_unit_instance_ids
            for model in geometry_models_for_fight_unit(
                scenario=scenario, unit_instance_id=component_id
            )
        )
    objective = (
        consolidation_objective_by_id(
            objective_id=proposal.objective_id,
            markers=fight_objective_markers_from_context(proposal_request),
            state=state,
        )
        if proposal.consolidation_mode is ConsolidationModeKind.OBJECTIVE
        else None
    )
    after_by_id = {item.model_instance_id: item for item in after}
    for placement in before:
        final = after_by_id[placement.model_instance_id]
        if final.pose == placement.pose:
            continue
        model_instance = scenario.model_instance_for_placement(placement)
        start = geometry_model_for_placement(model=model_instance, placement=placement)
        end = geometry_model_for_placement(model=model_instance, placement=final)
        if objective is not None:
            if measure_model_to_objective(model=end, objective=objective).within_control_range:
                continue
            before_distance = measure_model_to_objective(
                model=start, objective=objective
            ).closest_distance_inches
            after_distance = measure_model_to_objective(
                model=end, objective=objective
            ).closest_distance_inches
            if after_distance >= before_distance - 1e-9:
                return "objective_consolidation_model_not_closer"
            goal = _objective_goal(objective)
        else:
            distances = {
                unit_id: min(start.range_to(model) for model in models)
                for unit_id, models in targets.items()
            }
            if not distances:
                raise GameLifecycleError("Consolidation requires selected target geometry.")
            closest = min(distances.values())
            closest_models = tuple(
                model
                for unit_id, models in targets.items()
                if distances[unit_id] <= closest + 1e-9
                for model in models
            )
            if min(end.range_to(model) for model in closest_models) >= closest - 1e-9:
                return "moved_model_not_closer_to_closest_selected_unit"
            goal = MovementGoal(
                models=closest_models,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            )
            if goal.contains(end):
                continue
        query = _query(
            scenario=scenario,
            ruleset=ruleset_descriptor,
            proposal=proposal,
            placement=placement,
            start=start,
            after=after,
            goal=goal,
            state=state,
        )
        result = movement_reachability(query)
        if result.status is MovementReachabilityStatus.REACHABLE:
            return "consolidation_model_must_reach_required_endpoint"
        if result.status is MovementReachabilityStatus.UNRESOLVED:
            return "consolidation_reachability_unresolved"
    return None


def _objective_goal(objective: ObjectiveGeometry) -> MovementGoal:
    marker = objective.marker
    if marker is None:
        return MovementGoal(polygons=objective.footprint_polygons, vertical_inches=5.0)
    return MovementGoal(
        disk=(
            Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
            CircularBase(radius=marker.marker_diameter_inches / 2),
        ),
        horizontal_inches=marker.control_horizontal_inches,
        vertical_inches=marker.control_vertical_inches,
    )


def _query(
    *,
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    proposal: FightMovementProposal,
    placement: ModelPlacement,
    start: Model,
    after: tuple[ModelPlacement, ...],
    goal: MovementGoal,
    state: GameState | None,
) -> MovementReachabilityQuery:
    from warhammer40k_core.engine.fight_resolution import fight_terrain_volumes_for_features
    from warhammer40k_core.engine.fight_rules_unit_movement import (
        rules_unit_fight_movement_maximum_distance_inches,
    )

    battlefield = scenario.battlefield_state
    owner = scenario.unit_instance_for_placement(
        battlefield.unit_placement_by_id(placement.unit_instance_id)
    )
    legality = MovementLegalityContext.from_keywords(
        keywords=owner.keywords,
        ruleset_descriptor=ruleset,
        movement_mode=MovementMode.CONSOLIDATE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )
    witness = PathWitness.for_paths(((start.model_id, (start.pose, start.pose)),))
    after_by_id = {item.model_instance_id: item for item in after}
    friends: list[Model] = []
    enemies: dict[str, list[Model]] = {}
    for army in battlefield.placed_armies:
        for unit in army.unit_placements:
            rules_unit = rules_unit_view_from_armies(
                armies=scenario.armies, unit_instance_id=unit.unit_instance_id
            )
            for item in unit.model_placements:
                if item.model_instance_id == start.model_id:
                    continue
                final = after_by_id.get(item.model_instance_id, item)
                model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(item), placement=final
                )
                if item.player_id == placement.player_id:
                    friends.append(model)
                else:
                    enemies.setdefault(rules_unit.unit_instance_id, []).append(model)
    enemy_goals = tuple(
        MovementGoal(
            models=tuple(models),
            horizontal_inches=ruleset.engagement_policy.horizontal_inches,
            vertical_inches=ruleset.engagement_policy.vertical_inches,
        )
        for models in enemies.values()
    )
    coherency = ruleset.coherency_policy
    peers = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(item), placement=item
        )
        for item in after
        if item.model_instance_id != start.model_id
        and scenario.model_instance_for_placement(item).is_alive
    )
    neighbor_count = coherency.required_neighbors_small_unit
    if (
        coherency.large_unit_model_count_threshold is not None
        and len(peers) + 1 >= coherency.large_unit_model_count_threshold
    ):
        neighbor_count = coherency.required_neighbors_large_unit
    if coherency.policy_kind is CoherencyPolicyKind.NEIGHBOR_COUNT and (
        neighbor_count is None
        or coherency.max_horizontal_inches is None
        or coherency.max_vertical_inches is None
    ):
        raise GameLifecycleError("Consolidation requires complete neighbor coherency policy.")
    return MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=start,
            witness=witness,
            battlefield_width_inches=battlefield.battlefield_width_inches,
            battlefield_depth_inches=battlefield.battlefield_depth_inches,
            friendly_models=tuple(friends),
            enemy_models=tuple(model for models in enemies.values() for model in models),
            terrain=(),
            movement_distance_budget_inches=(
                3.0
                if state is None
                else rules_unit_fight_movement_maximum_distance_inches(
                    state=state,
                    unit_instance_id=proposal.unit_instance_id,
                    proposal_kind=ProposalKind.CONSOLIDATE,
                )
            ),
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=start,
            witness=witness,
            terrain=fight_terrain_volumes_for_features(battlefield.terrain_features),
            terrain_features=battlefield.terrain_features,
        ),
        goal=goal,
        maximum_target_range_inches=(
            min(start.range_to(model) for model in goal.models) - 1e-9 if goal.models else None
        ),
        required_goals=tuple(item for item in enemy_goals if item.contains(start))
        if proposal.consolidation_mode is ConsolidationModeKind.ONGOING
        else (),
        forbidden_goals=enemy_goals
        if proposal.consolidation_mode is ConsolidationModeKind.OBJECTIVE
        else (),
        coherent_models=peers,
        coherency_neighbor_count=1 if neighbor_count is None else neighbor_count,
        coherency_horizontal_inches=0.0
        if coherency.max_horizontal_inches is None
        else coherency.max_horizontal_inches,
        coherency_vertical_inches=0.0
        if coherency.max_vertical_inches is None
        else coherency.max_vertical_inches,
        coherency_max_span_inches=coherency.max_unit_span_inches,
        coherency_all_models_distance_inches=coherency.max_all_models_distance_inches,
    )
