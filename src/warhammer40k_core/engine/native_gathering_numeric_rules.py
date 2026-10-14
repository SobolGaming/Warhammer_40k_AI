"""Defer source-owned numeric predicates without evaluating any random profile."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.attack_gathering_wound_rules import WoundGatheringContext
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def gathering_numeric_values(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    pool: RangedAttackPool,
) -> tuple[int | None, int | None, dict[str, JsonValue]]:
    from warhammer40k_core.engine.attack_sequence_geometry_targets import _target_unit_toughness
    from warhammer40k_core.engine.damage_allocation import allocation_context_for_unit, model_by_id

    strength_value = pool.weapon_profile.strength
    strength = (
        None
        if isinstance(strength_value, RandomProfileValue)
        else pool.weapon_profile.strength_for_interaction()
    )
    context = allocation_context_for_unit(
        state=state, target_unit_instance_id=pool.target_unit_instance_id
    )
    model_ids = context.attached_unit_bodyguard_model_ids or context.alive_model_ids
    values = tuple(
        model_by_id(state=state, model_instance_id=model_id).characteristic(
            Characteristic.TOUGHNESS
        )
        for model_id in model_ids
    )
    toughness = (
        None
        if any(isinstance(value, RandomProfileValue) for value in values)
        else _target_unit_toughness(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
            runtime_modifier_registry=registry,
        )
    )
    descriptors: dict[str, JsonValue] = {
        "strength": validate_json_value(
            (
                strength_value.without_evaluation()
                if isinstance(strength_value, RandomProfileValue)
                else strength_value
            ).to_payload()
        ),
        "target_model_toughness": [
            {
                "model_instance_id": model_id,
                "descriptor": validate_json_value(
                    (
                        value.without_evaluation()
                        if isinstance(value, RandomProfileValue)
                        else value
                    ).to_payload()
                ),
            }
            for model_id, value in zip(model_ids, values, strict=True)
        ],
    }
    return strength, toughness, descriptors


def wound_gathering_templates(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence,
    pool: RangedAttackPool,
) -> list[JsonValue]:
    context = WoundGatheringContext(
        state,
        sequence.source_phase,
        sequence.attacking_unit_instance_id,
        pool.attacker_model_instance_id,
        pool.target_unit_instance_id,
        pool.weapon_profile,
    )
    result: list[JsonValue] = []
    for binding in registry.wound_roll_modifier_bindings:
        handler = binding.gathering_handler
        if handler is None:
            raise GameLifecycleError("Wound provider has no source-owned gathering template.")
        operand = handler(context)
        if type(operand) is not int:
            raise GameLifecycleError("Wound gathering template returned a non-integer modifier.")
        if operand:
            result.append(
                {
                    "modifier_id": binding.modifier_id,
                    "source_id": binding.source_id,
                    "operand": operand,
                    "predicate": binding.gathering_predicate.value,
                }
            )
    return result


def wound_gathering_inventory(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    sequence: AttackSequence,
    pool: RangedAttackPool,
    strength: int | None,
    toughness: int | None,
) -> list[JsonValue]:
    from warhammer40k_core.engine.runtime_modifiers import WoundRollModifierContext

    if strength is None or toughness is None:
        return wound_gathering_templates(
            state=state, registry=registry, sequence=sequence, pool=pool
        )
    return [
        validate_json_value(item.to_payload())
        for item in registry.wound_roll_modifiers(
            WoundRollModifierContext(
                state,
                sequence.source_phase,
                sequence.attacking_unit_instance_id,
                pool.attacker_model_instance_id,
                pool.target_unit_instance_id,
                pool.weapon_profile,
                strength,
                toughness,
            )
        )
    ]
