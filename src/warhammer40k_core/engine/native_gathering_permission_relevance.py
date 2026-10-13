"""Pre-roll permission relevance from the real consumers' operation inventories."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.catalog_modifier_ignore import ModifierIgnoreKind
from warhammer40k_core.engine.event_log import JsonValue

if TYPE_CHECKING:
    from warhammer40k_core.core.random_profile_values import ProfileCharacteristicValue
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.generic_rule_effect_targets import GenericAttackEffect
    from warhammer40k_core.engine.psychic_modifier_selection import AttackModifierSnapshot
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.weapon_declaration import RangedAttackPool


def attacker_permission_kinds_for_gathering(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    pool: RangedAttackPool,
    hit_snapshots: tuple[AttackModifierSnapshot, ...],
    wound_inventory: list[JsonValue],
    generic_sources: tuple[GenericAttackEffect, ...],
) -> tuple[ModifierIgnoreKind, ...]:
    """An empty real consumer must not acquire a new permission-schema requirement."""
    from warhammer40k_core.engine.attack_damage_modifier_selection import (
        damage_characteristic_operations,
    )
    from warhammer40k_core.engine.attack_sequence_hit_wound import _melta_damage_modifier
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.engine.weapon_abilities import LANCE_RULE_ID
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    profile = pool.weapon_profile
    target = rules_unit_view_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    damage_operations = damage_characteristic_operations(
        profile.damage_profile,
        melta_bonus=_melta_damage_modifier(
            pool, target_keywords=target.keywords, name_keywords=target.datasheet_name_keywords
        ),
    )
    operations = (
        (
            ModifierIgnoreKind.BALLISTIC_SKILL_CHARACTERISTIC
            if profile.skill.characteristic is Characteristic.BALLISTIC_SKILL
            else ModifierIgnoreKind.WEAPON_SKILL_CHARACTERISTIC,
            any(item.kind == "skill" for item in hit_snapshots),
        ),
        (ModifierIgnoreKind.HIT_ROLL, any(item.kind == "hit_roll" for item in hit_snapshots)),
        (ModifierIgnoreKind.STRENGTH_CHARACTERISTIC, _has_profile_operations(profile.strength)),
        (
            ModifierIgnoreKind.WOUND_ROLL,
            bool(wound_inventory) or LANCE_RULE_ID in pool.targeting_rule_ids,
        ),
        (
            ModifierIgnoreKind.ARMOR_PENETRATION_CHARACTERISTIC,
            _has_profile_operations(profile.armor_penetration)
            or bool(registry.post_roll_weapon_profile_modifier_bindings)
            or _save_provider_may_modify(registry, Characteristic.ARMOR_PENETRATION)
            or any(
                effect.effect_kind is RuleEffectKind.MODIFY_CHARACTERISTIC
                and effect.parameters.get("characteristic")
                == Characteristic.ARMOR_PENETRATION.value
                for effect in generic_sources
            ),
        ),
        (
            ModifierIgnoreKind.DAMAGE_CHARACTERISTIC,
            bool(damage_operations)
            or bool(registry.allocated_attack_damage_modifier_bindings)
            or bool(registry.failed_save_damage_replacement_bindings)
            or bool(registry.post_roll_weapon_profile_modifier_bindings),
        ),
        (
            ModifierIgnoreKind.DAMAGE_ROLL,
            profile.damage_profile.dice_expression is not None
            and (
                bool(registry.damage_roll_modifier_bindings)
                or any(
                    _generic_damage_source_may_apply(effect, pool, attacking_unit_instance_id)
                    for effect in generic_sources
                )
            ),
        ),
    )
    # Future providers retain possible relevance; their applicability is not
    # inferred by invoking a handler with invented allocation/save/roll data.
    return tuple(kind for kind, present in operations if present)


def _generic_damage_source_may_apply(
    effect: GenericAttackEffect, pool: RangedAttackPool, attacking_unit_instance_id: str
) -> bool:
    """Pure real-source inventory, sharing the actual Damage owner's roll/role gates.

    Unknown parameter shapes stay possible until the original occurrence decoder
    validates them. No future numeric consumer or fabricated roll is invoked.
    """
    from warhammer40k_core.engine.generic_rule_attack_hooks import _roll_type_matches
    from warhammer40k_core.engine.generic_rule_effect_targets import generic_effect_role_applies
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    if effect.effect_kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return False
    roll_type = effect.parameters.get("roll_type")
    if type(roll_type) is str and not _roll_type_matches(effect.parameters, expected="damage"):
        return False
    delta = effect.parameters.get("delta")
    # The matcher authenticated this exact singleton component application.
    # Its own role must retain that identity inside an attached rules unit.
    application_unit_id = effect.effective_target_unit_instance_ids[0]
    return generic_effect_role_applies(
        effect=effect,
        role=effect.role,
        attacking_unit_instance_id=(
            application_unit_id if effect.role == "attacker" else attacking_unit_instance_id
        ),
        target_unit_instance_id=(
            application_unit_id if effect.role == "target" else pool.target_unit_instance_id
        ),
        legacy_attacker_role_allowed=lambda _effect: type(delta) is not int or delta >= 0,
        legacy_target_role_allowed=lambda _effect: type(delta) is not int or delta <= 0,
    )


def _has_profile_operations(value: ProfileCharacteristicValue) -> bool:
    from warhammer40k_core.engine.attack_modifier_evaluation import profile_modifier_trace

    # Random values have no source scalar until the actual consumer rolls them.
    if isinstance(value, RandomProfileValue):
        return bool(value.modifiers)
    return bool(profile_modifier_trace(value).modifiers)


def generic_source_inventory(effect: GenericAttackEffect) -> dict[str, JsonValue]:
    return {
        "role": effect.role,
        "source_id": effect.source_id,
        "rule_id": effect.rule_id,
        "rule_ir_hash": effect.rule_ir_hash,
        "clause_id": effect.clause_id,
        "effect_index": effect.effect_index,
        "target_kind": None if effect.target_kind is None else effect.target_kind.value,
        "parameters": effect.parameters,
        "conditions": cast(list[JsonValue], list(effect.conditions)),
        "source_model_instance_id": effect.source_model_instance_id,
    }


def unused_attacker_ignore_sources(
    *,
    effects: tuple[GenericAttackEffect, ...],
    active_kinds: tuple[ModifierIgnoreKind, ...],
) -> list[dict[str, JsonValue]]:
    """Omit only known empty-consumer grants from comparison, retaining raw proof."""
    from warhammer40k_core.engine.catalog_modifier_ignore_sources import (
        explicit_modifier_ignore_kinds_for_gathering,
    )
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    result: list[dict[str, JsonValue]] = []
    for effect in effects:
        if (
            effect.role != "attacker"
            or effect.effect_kind is not RuleEffectKind.GRANT_ABILITY
            or effect.parameters.get("ability") != "modifier_ignore_permission"
        ):
            continue
        kinds = explicit_modifier_ignore_kinds_for_gathering(effect.parameters)
        if kinds is not None and set(kinds).isdisjoint(active_kinds):
            result.append(generic_source_inventory(effect))
    return result


def target_permission_kinds_for_gathering(
    *,
    state: GameState,
    registry: RuntimeModifierRegistry,
    pool: RangedAttackPool,
    model_instance_id: str,
) -> tuple[ModifierIgnoreKind, ...]:
    """Use real Wound subjects and model traces; retain later Save possibilities."""
    from warhammer40k_core.engine.damage_allocation import allocation_context_for_unit, model_by_id
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_rule_characteristic_operations,
        generic_rule_matching_unit_effects,
    )
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    model = model_by_id(state=state, model_instance_id=model_instance_id)
    allocation = allocation_context_for_unit(
        state=state, target_unit_instance_id=pool.target_unit_instance_id
    )
    wound_models = allocation.attached_unit_bodyguard_model_ids or allocation.alive_model_ids
    toughness = model.characteristic(Characteristic.TOUGHNESS)
    toughness_operations = False
    if model_instance_id in wound_models:
        if isinstance(toughness, RandomProfileValue):
            toughness_operations = (
                bool(toughness.modifiers)
                or bool(registry.unit_characteristic_modifier_bindings)
                or bool(
                    generic_rule_characteristic_operations(
                        state=state,
                        unit_instance_id=pool.target_unit_instance_id,
                        characteristic=Characteristic.TOUGHNESS,
                        model_instance_id=model_instance_id,
                    )
                )
            )
        else:
            from warhammer40k_core.engine.attack_modifier_evaluation import profile_modifier_trace
            from warhammer40k_core.engine.runtime_modifiers import UnitCharacteristicModifierContext

            trace = profile_modifier_trace(toughness)
            toughness_operations = bool(
                (
                    *trace.modifiers,
                    *registry.unit_characteristic_operations(
                        UnitCharacteristicModifierContext(
                            state=state,
                            unit_instance_id=pool.target_unit_instance_id,
                            characteristic=Characteristic.TOUGHNESS,
                            base_value=trace.source_value,
                            current_value=toughness.final,
                            model_instance_id=model_instance_id,
                        )
                    ),
                )
            )
    save_operations = _save_provider_may_modify(registry, Characteristic.SAVE) or any(
        value.characteristic is Characteristic.SAVE
        and not value.is_dash
        and _has_profile_operations(value)
        for value in model.characteristics
    )
    invulnerable_operations = _save_provider_may_modify(
        registry, Characteristic.INVULNERABLE_SAVE
    ) or any(
        value.characteristic is Characteristic.INVULNERABLE_SAVE
        and not value.is_dash
        and _has_profile_operations(value)
        for value in model.characteristics
    )
    has_invulnerable_option = any(
        value.characteristic is Characteristic.INVULNERABLE_SAVE and not value.is_dash
        for value in model.characteristics
    )
    if has_invulnerable_option:
        invulnerable_operations = invulnerable_operations or any(
            effect.parameters.get("characteristic") == Characteristic.INVULNERABLE_SAVE.value
            and effect.source_model_instance_id == model_instance_id
            for effect in generic_rule_matching_unit_effects(
                state=state,
                unit_instance_id=pool.target_unit_instance_id,
                effect_kind=RuleEffectKind.SET_CHARACTERISTIC,
            )
        )
    operations = (
        (ModifierIgnoreKind.TOUGHNESS_CHARACTERISTIC, toughness_operations),
        (ModifierIgnoreKind.SAVE_CHARACTERISTIC, save_operations),
        (ModifierIgnoreKind.INVULNERABLE_SAVE_CHARACTERISTIC, invulnerable_operations),
        # Save rolls may contain nonzero inherent AP/Cover and later generic
        # operations. No empty Save-roll inventory is inferred from a model trace.
        (ModifierIgnoreKind.SAVE_ROLL, True),
    )
    return tuple(kind for kind, present in operations if present)


def _save_provider_may_modify(
    registry: RuntimeModifierRegistry, characteristic: Characteristic
) -> bool:
    # Pure declared output inventory: never call a Save handler before an actual
    # allocation with a fabricated SaveOption. Unknown producers stay possible.
    return any(
        binding.gathering_modified_characteristics is None
        or characteristic in binding.gathering_modified_characteristics
        for binding in registry.save_option_modifier_bindings
    )


def unused_attack_characteristic_sources(
    effects: tuple[GenericAttackEffect, ...],
    *,
    pool: RangedAttackPool,
) -> list[dict[str, JsonValue]]:
    """Project known direct properties onto their real attack subjects/consumers.

    Movement/Leadership/OC have separate unit consumers. T/Save/InvSave/Wounds
    belong to this attack's target; their attacker-role copies are unused here.
    Attacks is already consumed into each pool's physical quantity. The other
    weapon properties share the dispatcher's exact profile gates.
    Unknown/malformed properties/operands and Detection Range stay conservative.
    Raw effects, physical ownership, indirect providers and occurrence guards
    remain authoritative; no handler or future roll/allocation is invented.
    """
    from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
        rule_ir_weapon_characteristic_applies,
    )
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    result: list[dict[str, JsonValue]] = []
    for effect in effects:
        if effect.effect_kind is not RuleEffectKind.MODIFY_CHARACTERISTIC:
            continue
        token = effect.parameters.get("characteristic")
        if type(token) is not str or type(effect.parameters.get("delta")) is not int:
            continue
        try:
            characteristic = Characteristic(token)
        except ValueError:
            # An unproved future property never acquires a comparison waiver.
            continue
        if characteristic in {
            Characteristic.MOVEMENT,
            Characteristic.LEADERSHIP,
            Characteristic.OBJECTIVE_CONTROL,
        }:
            unused = True
        elif characteristic in {
            Characteristic.TOUGHNESS,
            Characteristic.SAVE,
            Characteristic.INVULNERABLE_SAVE,
            Characteristic.WOUNDS,
        }:
            unused = effect.role == "attacker"
        elif characteristic is Characteristic.DETECTION_RANGE:
            continue
        elif characteristic is Characteristic.ATTACKS:
            # Pool creation has already resolved this physical weapon's count.
            # Keep its raw owner/effect proof without a later roll distinction.
            unused = True
        else:
            unused = not rule_ir_weapon_characteristic_applies(
                characteristic=characteristic, profile=pool.weapon_profile
            )
        if unused:
            result.append(generic_source_inventory(effect))
    return result


def unused_fixed_damage_roll_sources(
    effects: tuple[GenericAttackEffect, ...], *, pool: RangedAttackPool
) -> list[dict[str, JsonValue]]:
    """Fixed Damage has no Damage-roll consumer; retain exact raw source proof.

    Only known supported roll/operand shapes leave comparison. Unknown shapes
    stay conservative. Real random Damage retains every future source without
    inventing a scalar or invoking the occurrence decoder before its real roll.
    Damage-characteristic/Melta/allocation/replacement operations are separate.
    """
    from warhammer40k_core.engine.generic_rule_attack_hooks import _roll_type_matches
    from warhammer40k_core.rules.rule_ir import RuleEffectKind

    if pool.weapon_profile.damage_profile.dice_expression is not None:
        return []
    return [
        generic_source_inventory(effect)
        for effect in effects
        if effect.effect_kind is RuleEffectKind.MODIFY_DICE_ROLL
        and type(effect.parameters.get("roll_type")) is str
        and cast(str, effect.parameters["roll_type"]).strip()
        and type(effect.parameters.get("delta")) is int
        and _roll_type_matches(effect.parameters, expected="damage")
    ]
