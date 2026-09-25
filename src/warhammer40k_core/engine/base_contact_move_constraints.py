"""Owning Fight and Surge endpoint restrictions for contact feasibility proofs."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import (
    ConsolidationModeKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.geometry.movement_reachability import MovementGoal, MovementReachabilityQuery
from warhammer40k_core.geometry.volume import Model


def contact_move_constraints(
    query: MovementReachabilityQuery,
    *,
    ruleset: RulesetDescriptor,
    enemy_groups: tuple[tuple[Model, ...], ...],
    selected_groups: tuple[tuple[Model, ...], ...],
    mode: MovementMode,
    consolidation_mode: ConsolidationModeKind | None = None,
    surge: bool = False,
) -> MovementReachabilityQuery:
    """Apply rules-unit target obligations without changing measurement semantics.

    Peer endpoints are fixed by the actual submitted whole-unit witness. A unit
    engagement obligation is imposed on this model only when no peer fulfils it.
    Objective Consolidation forbids every enemy engagement, which precludes
    enemy base contact even when the actual overhang is outside Engagement Range.
    """
    if not (surge or mode in {MovementMode.PILE_IN, MovementMode.CONSOLIDATE}):
        return query
    engagement = ruleset.engagement_policy

    def goal(models: tuple[Model, ...]) -> MovementGoal:
        return MovementGoal(
            models=models,
            horizontal_inches=engagement.horizontal_inches,
            vertical_inches=engagement.vertical_inches,
        )

    enemies = tuple(goal(group) for group in enemy_groups)
    source = query.path_context.moving_model
    if consolidation_mode is ConsolidationModeKind.OBJECTIVE:
        return replace(query, forbidden_goals=enemies)
    selected = tuple(m for group in selected_groups for m in group)
    if not selected:
        from warhammer40k_core.engine.phase import GameLifecycleError

        raise GameLifecycleError("Contact feasibility requires the move's selected targets.")
    if surge:
        selected_ids = {m.model_id for m in selected}
        return replace(
            query,
            required_if_reachable_goals=(goal(selected),),
            forbidden_goals=tuple(
                g for g in enemies if not any(m.model_id in selected_ids for m in g.models)
            ),
        )
    closest = min(source.range_to(m) for m in selected)
    # Pile In compares the union of selected units. Consolidation additionally
    # requires approaching a closest selected unit (including all exact ties).
    closest_models = tuple(
        m
        for group in selected_groups
        if min(source.range_to(m) for m in group) <= closest + 1e-9
        for m in group
    )
    closer = selected if mode is MovementMode.PILE_IN else closest_models
    continuing = tuple(g for g in enemies if g.contains(source))
    required: list[MovementGoal] = []
    if mode is MovementMode.PILE_IN:
        required.append(goal(selected))
    elif consolidation_mode is ConsolidationModeKind.ENGAGING:
        required.extend(goal(group) for group in selected_groups)
    required = [g for g in required if not any(g.contains(peer) for peer in query.coherent_models)]
    return replace(
        query,
        required_goals=(*continuing, *required),
        closer_target_groups=(closer,),
        required_if_reachable_goals=(goal(closest_models),)
        if mode is MovementMode.CONSOLIDATE
        else (),
    )
