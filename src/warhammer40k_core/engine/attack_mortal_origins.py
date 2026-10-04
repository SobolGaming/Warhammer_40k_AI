"""Physical contribution identity for deferred mortals from gathered attack dice."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.post_roll_weapon_profile_modifiers import (
    PostRollWeaponProfileModifierContext,
    ResolvedAttackRollValues,
    modified_post_roll_weapon_profile,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_model import AttackResolutionContextPayload
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


@dataclass(frozen=True, slots=True)
class AttackMortalOrigin:
    pool_index: int
    attack_index: int
    weapon_instance_id: str
    source_model_instance_id: str
    weapon_profile: WeaponProfile


def attack_mortal_origin(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> AttackMortalOrigin:
    pool_index = attack_context["pool_index"]
    attack_index = attack_context["attack_index"]
    group = attack_sequence.current_gathered_group
    if group is not None:
        if pool_index != group.primary_pool_index:
            raise GameLifecycleError("Attack mortal origin gathered pool drift.")
        offset = 0
        for contribution in group.contributions:
            if offset <= attack_index < offset + contribution.attacks:
                pool_index = contribution.pool_index
                attack_index -= offset
                break
            offset += contribution.attacks
        else:
            raise GameLifecycleError("Attack mortal origin contribution is absent.")
    if not 0 <= pool_index < len(attack_sequence.attack_pools):
        raise GameLifecycleError("Attack mortal origin physical pool is absent.")
    pool = attack_sequence.attack_pools[pool_index]
    if not 0 <= attack_index < pool.attacks:
        raise GameLifecycleError("Attack mortal origin physical attack is absent.")
    hit = attack_context["hit_roll"]
    wound = attack_context["wound_roll"]
    profile = modified_post_roll_weapon_profile(
        bindings=runtime_modifier_registry.post_roll_weapon_profile_modifier_bindings,
        context=PostRollWeaponProfileModifierContext(
            state=state,
            source_phase=attack_sequence.source_phase,
            attack_context_id=attack_context["attack_context_id"],
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            hit_roll=ResolvedAttackRollValues(
                unmodified_roll=hit["unmodified_roll"],
                final_roll=hit["final_roll"],
                successful=hit["successful"],
                critical=hit["critical"],
                skipped=hit["skipped"],
            ),
            wound_roll=ResolvedAttackRollValues(
                unmodified_roll=wound["unmodified_roll"],
                final_roll=wound["final_roll"],
                successful=wound["successful"],
                critical=wound["critical"],
                skipped=wound["skipped"],
            ),
            weapon_profile=pool.weapon_profile,
        ),
    )
    return AttackMortalOrigin(
        pool_index=pool_index,
        attack_index=attack_index,
        weapon_instance_id=pool.weapon_instance_id,
        source_model_instance_id=pool.attacker_model_instance_id,
        weapon_profile=profile,
    )
