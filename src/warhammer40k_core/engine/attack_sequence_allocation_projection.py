"""Project possible wound recipients using native attack allocation priority."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_group_selection import (
    _precision_grouped_allocation_context_and_groups,
    precision_allocation_groups_for_pool,
)
from warhammer40k_core.engine.attack_sequence_grouped_allocation import (
    _alive_allocated_model_ids_for_target_unit,
)
from warhammer40k_core.engine.attack_sequence_model import PrecisionPoolSelection
from warhammer40k_core.engine.damage_allocation import (
    AttackAllocationConstraint,
    allocation_context_for_unit,
    allocation_groups_for_context,
    model_by_id,
)
from warhammer40k_core.engine.weapon_abilities import PRECISION_RULE_ID

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import AllocationGroup
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def allocation_models_reachable_by_pool(
    *,
    state: GameState,
    pool: RangedAttackPool,
    allocated_model_ids: tuple[str, ...],
    wound_slots: int | None,
    maximum_damage: int | None,
    precision_possible: bool,
    refine_save_group: Callable[[AllocationGroup], tuple[AllocationGroup, ...] | None],
    may_skip_saves: bool,
) -> set[str]:
    """Union the recipients reachable after decline or any legal Precision lead."""
    target_id = pool.target_unit_instance_id
    allocation = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=target_id,
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state, target_unit_instance_id=target_id, allocated_model_ids=allocated_model_ids
        ),
    )
    groups = allocation_groups_for_context(
        state=state, allocation_context=allocation, include_priority_tiers=True
    )

    def reachable(groups: tuple[AllocationGroup, ...], lead_id: str | None = None) -> set[str]:
        result = _reachable_allocation_models(
            state=state,
            groups=groups,
            wound_slots=wound_slots,
            maximum_damage=maximum_damage,
            refine_save_group=refine_save_group,
            lead_id=lead_id,
        )
        if may_skip_saves:
            # If every retained wound skips saves, the ordinary Save partition
            # can merge back into the initial native groups.
            result.update(
                _reachable_allocation_models(
                    state=state,
                    groups=groups,
                    wound_slots=wound_slots,
                    maximum_damage=maximum_damage,
                    refine_save_group=lambda group: (group,),
                    lead_id=lead_id,
                )
            )
        return result

    candidates = reachable(groups)
    if precision_possible:
        for lead in precision_allocation_groups_for_pool(
            state=state,
            allocation_context=replace(
                allocation,
                attacker_constraint=AttackAllocationConstraint(
                    source_rule_ids=(PRECISION_RULE_ID,), can_allocate_protected_characters=True
                ),
            ),
            pool=pool,
        ):
            _, final_groups, priority_ids = _precision_grouped_allocation_context_and_groups(
                state=state,
                target_unit_instance_id=target_id,
                allocated_model_ids=allocated_model_ids,
                precision_selection=PrecisionPoolSelection(lead.group_id, lead.model_ids, True),
            )
            candidates.update(reachable(final_groups, priority_ids[0] if priority_ids else None))
    return candidates


def _reachable_allocation_models(
    *,
    state: GameState,
    groups: tuple[AllocationGroup, ...],
    wound_slots: int | None,
    maximum_damage: int | None,
    refine_save_group: Callable[[AllocationGroup], tuple[AllocationGroup, ...] | None],
    lead_id: str | None = None,
) -> set[str]:
    from warhammer40k_core.engine.damage_allocation import allocation_order_tier

    candidates = {model_id for group in groups for model_id in group.model_ids}
    if wound_slots is None or (wound_slots > len(candidates) and maximum_damage is None):
        return candidates

    # A failed save can destroy at most its recipient. When the Damage ceiling
    # is known, each preceding model can also require more than one wound slot.
    costs = {
        model_id: 1
        if maximum_damage is None
        else (
            model_by_id(state=state, model_instance_id=model_id).current_wounds + maximum_damage - 1
        )
        // maximum_damage
        for model_id in candidates
    }
    lead = next((group for group in groups if group.group_id == lead_id), None)
    reachable: set[str] = set() if lead is None else set(lead.model_ids)
    lead_cost = sum(costs[model_id] for model_id in reachable)
    groups = tuple(group for group in groups if group.group_id != lead_id)

    # The native resolver clears each effective Save subgroup before advancing.
    # Preserve proven subgroups. An unresolved split can move healthy members
    # to a later tier, so count only its wounded members as forced early.
    effective_groups: list[AllocationGroup] = []
    unresolved: set[str] = set()
    for group in groups:
        if not 0 < len(group.wounded_model_ids) < len(group.model_ids):
            effective_groups.append(group)
            continue
        predicted = refine_save_group(group)
        if predicted is None:
            unresolved.add(group.group_id)
            effective_groups.append(group)
        else:
            effective_groups.extend(predicted)

    tier_costs = [0, 0, 0, 0]
    for group in effective_groups:
        for model_id in group.model_ids:
            wounded = (
                model_id in group.wounded_model_ids
                if group.group_id in unresolved
                else group.wounded
            )
            tier = allocation_order_tier(group.role, wounded=wounded)
            tier_costs[tier] += costs[model_id]
    for group in effective_groups:
        tier = allocation_order_tier(group.role, wounded=group.wounded)
        preceding = lead_cost + sum(tier_costs[:tier])
        wounded_cost = sum(costs[model_id] for model_id in group.wounded_model_ids)
        reachable.update(
            model_id
            for model_id in group.model_ids
            if preceding + (0 if model_id in group.wounded_model_ids else wounded_cost)
            < wound_slots
        )
    return reachable
