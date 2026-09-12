"""Resolve the individual skill and hit modifiers at an authoritative attack boundary."""

from __future__ import annotations

from hashlib import sha256
from typing import TYPE_CHECKING

from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm, RollModifier
from warhammer40k_core.engine.core_stratagem_effects import (
    SMOKESCREEN_EFFECT_KIND,
    SMOKESCREEN_HIT_ROLL_MODIFIER,
    effect_kind,
    effect_payload_int,
    unit_effects_grant_benefit_of_cover,
)
from warhammer40k_core.engine.event_log import canonical_json, validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.psychic_modifier_selection import AttackModifierSnapshot

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def attack_modifier_snapshots(
    *,
    state: GameState,
    pool: RangedAttackPool,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[AttackModifierSnapshot, ...]:
    from warhammer40k_core.engine.attack_sequence_hit_wound import (
        _benefit_of_cover_ballistic_skill_penalty,
        _unit_instance_id_for_model,
    )
    from warhammer40k_core.engine.runtime_modifiers import HitRollModifierContext
    from warhammer40k_core.engine.shooting_targets import (
        BENEFIT_OF_COVER_RULE_ID,
        PLUNGING_FIRE_RULE_ID,
    )
    from warhammer40k_core.engine.stealth import rules_unit_stealth_sources

    snapshots = [
        AttackModifierSnapshot("skill", item) for item in pool.weapon_profile.skill_modifiers
    ]
    skill_deltas = (
        (
            BENEFIT_OF_COVER_RULE_ID,
            _benefit_of_cover_ballistic_skill_penalty(
                state=state, pool=pool, runtime_modifier_registry=runtime_modifier_registry
            ),
        ),
        (PLUNGING_FIRE_RULE_ID, -1 if PLUNGING_FIRE_RULE_ID in pool.targeting_rule_ids else 0),
    )
    for rule_id, delta in skill_deltas:
        if delta:
            snapshots.append(
                AttackModifierSnapshot(
                    "skill",
                    ModifierTerm(ModifierOperation.ADD, delta).bind(
                        modifier_id=(
                            f"{rule_id}:{
                                sha256(
                                    canonical_json(
                                        validate_json_value(
                                            {
                                                'effects': [
                                                    effect.to_payload()
                                                    for effect in state.persisting_effects_for_unit(
                                                        pool.target_unit_instance_id
                                                    )
                                                    if unit_effects_grant_benefit_of_cover(
                                                        (effect,)
                                                    )
                                                ],
                                                'stealth': rules_unit_stealth_sources(
                                                    state=state,
                                                    target_unit_instance_id=pool.target_unit_instance_id,
                                                    runtime_modifier_registry=runtime_modifier_registry,
                                                ),
                                            }
                                        )
                                    ).encode()
                                ).hexdigest()
                            }"
                            if rule_id == BENEFIT_OF_COVER_RULE_ID
                            else rule_id
                        ),
                        source_id=rule_id,
                        characteristic=pool.weapon_profile.skill.characteristic,
                    ),
                )
            )
    snapshots.extend(AttackModifierSnapshot("hit_roll", item) for item in pool.hit_roll_modifiers)
    snapshots.extend(
        AttackModifierSnapshot(
            "hit_roll",
            RollModifier(
                modifier_id=f"persisting:{effect.effect_id}:hit",
                source_id=effect.source_rule_id,
                operand=effect_payload_int(
                    effect, "hit_roll_modifier", SMOKESCREEN_HIT_ROLL_MODIFIER
                ),
            ),
        )
        for effect in state.persisting_effects_for_unit(pool.target_unit_instance_id)
        if effect_kind(effect) == SMOKESCREEN_EFFECT_KIND
    )
    snapshots.extend(
        AttackModifierSnapshot("hit_roll", item)
        for item in runtime_modifier_registry.hit_roll_modifiers(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=_unit_instance_id_for_model(
                    state=state, model_instance_id=pool.attacker_model_instance_id
                ),
                attacker_model_instance_id=pool.attacker_model_instance_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                weapon_profile=pool.weapon_profile,
                source_phase=source_phase,
            )
        )
        if item.operand != 0
    )
    ids = [item.modifier_id for item in snapshots]
    if len(ids) != len(set(ids)):
        raise GameLifecycleError("Attack modifier source identities collide.")
    return tuple(sorted(snapshots, key=lambda item: item.modifier_id))
