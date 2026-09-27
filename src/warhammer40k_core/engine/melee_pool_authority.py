"""Authenticate committed melee pools from the pre-target selection inventory."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.melee_weapon_commitment import (
    MeleeAttackBudget,
    identifier,
    object_payload,
    requires_melee_commitment,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.weapon_abilities import cleave_attack_bonus
from warhammer40k_core.engine.weapon_declaration import RangedAttackPool
from warhammer40k_core.engine.weapon_selection_context import (
    WeaponSelectionContext,
    WeaponSelectionContextPayload,
    rebind_selection_targets,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import MeleeDeclarationProposal
    from warhammer40k_core.engine.game_state import GameState


def commitment_inventory(rows: tuple[JsonValue, ...], state: GameState) -> tuple[JsonValue, ...]:
    """Freeze Cleave inputs before targets/dice; fixed-only history stays unchanged."""
    if not requires_melee_commitment(rows):
        return rows
    enriched: list[JsonValue] = []
    for raw in rows:
        row = object_payload(raw)
        context_payload = row["weapon_ability_selection_context"]
        facts: dict[str, JsonValue] = {}
        if context_payload is not None:
            context = WeaponSelectionContext.from_payload(
                cast(WeaponSelectionContextPayload, object_payload(context_payload))
            )
            for target_id, _ in context.target_profiles:
                target = rules_unit_view_by_id(state=state, unit_instance_id=target_id)
                facts[target_id] = {
                    "canonical_unit_instance_id": target.unit_instance_id,
                    "alive_model_ids": [model.model_instance_id for model in target.alive_models()],
                    "keywords": list(target.keywords),
                }
        enriched.append({**row, "melee_target_facts": facts})
    return tuple(enriched)


def validate_committed_pools(
    *,
    proposal: MeleeDeclarationProposal,
    rows: tuple[dict[str, JsonValue], ...],
    budgets: dict[str, MeleeAttackBudget],
    pools: tuple[RangedAttackPool, ...],
) -> None:
    by_weapon = {identifier(row, "weapon_instance_id"): row for row in rows}
    if len(pools) != sum(len(d.target_allocations) for d in proposal.declarations):
        raise GameLifecycleError("Melee declaration has unowned attack pools.")
    for declaration in proposal.declarations:
        weapon_id = declaration.weapon_instance_id
        if weapon_id is None or weapon_id not in by_weapon:
            raise GameLifecycleError("Melee pool has no committed physical source.")
        row = by_weapon[weapon_id]
        context = WeaponSelectionContext.from_payload(
            cast(
                WeaponSelectionContextPayload,
                object_payload(row["weapon_ability_selection_context"]),
            )
        )
        facts = object_payload(row["melee_target_facts"])
        mapping = {
            target_id: identifier(object_payload(facts[target_id]), "canonical_unit_instance_id")
            for target_id, _ in context.target_profiles
        }
        weapon_pools = tuple(pool for pool in pools if pool.weapon_instance_id == weapon_id)
        if len(weapon_pools) != len(declaration.target_allocations):
            raise GameLifecycleError("Melee split pool inventory drifted.")
        total = None
        for allocation in declaration.target_allocations:
            aliases = sorted(
                target
                for target, canonical in mapping.items()
                if canonical == allocation.target_unit_instance_id
            )
            if not aliases:
                raise GameLifecycleError("Melee pool target is outside its accepted inventory.")
            target_id = aliases[0]
            profile = context.selected_profile(target_id, declaration.selected_weapon_ability_ids)
            if total is None:
                total = budgets[weapon_id].attacks_for(profile)
            target = object_payload(facts[target_id])
            models, keywords = target["alive_model_ids"], target["keywords"]
            if (
                not isinstance(models, list)
                or not isinstance(keywords, list)
                or any(type(value) is not str for value in (*models, *keywords))
                or len(set(cast(list[str], models))) != len(models)
            ):
                raise GameLifecycleError("Melee target facts are malformed.")
            expected_attacks = (
                total
                + cleave_attack_bonus(
                    profile,
                    single_target=True,
                    target_model_count=len(models),
                    target_keywords=tuple(cast(list[str], keywords)),
                )
                if len(declaration.target_allocations) == 1
                else allocation.attacks
            )
            expected_context = None
            if declaration.selected_weapon_ability_ids:
                expected_context = (
                    context
                    if target_id == allocation.target_unit_instance_id
                    else rebind_selection_targets(context, mapping)
                )
            matches = [
                pool
                for pool in weapon_pools
                if pool.target_unit_instance_id == allocation.target_unit_instance_id
            ]
            if len(matches) != 1:
                raise GameLifecycleError("Melee accepted pool target drifted.")
            pool = matches[0]
            if (
                pool.attacks != expected_attacks
                or (allocation.attacks is not None and pool.attacks != allocation.attacks)
                or pool.attacker_model_instance_id != declaration.attacker_model_instance_id
                or pool.wargear_id != declaration.wargear_id
                or pool.weapon_profile_id != declaration.weapon_profile_id
                or pool.weapon_profile != profile
                or pool.selected_weapon_ability_ids != declaration.selected_weapon_ability_ids
                or pool.weapon_selection_context != expected_context
                or pool.shooting_type is not ShootingType.NORMAL
                or pool.hit_roll_modifier != 0
                or pool.hit_roll_modifiers
                or pool.firing_deck_source_unit_instance_id is not None
                or pool.firing_deck_source_model_instance_id is not None
            ):
                raise GameLifecycleError(
                    "Melee pool differs from committed source and attack budget."
                )
        if len(weapon_pools) > 1 and sum(pool.attacks for pool in weapon_pools) != total:
            raise GameLifecycleError("Melee split failed per-weapon conservation.")
