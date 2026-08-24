from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import cast

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.dice import (
    DiceRollSpecError,
    RandomCharacteristicRoll,
    RandomCharacteristicRollPayload,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.advance_hooks import (
    AdvanceMoveContext,
    AdvanceMoveGrant,
    AdvanceMoveHookBinding,
)
from warhammer40k_core.engine.catalog_attack_context_rule_runtime import (
    CatalogDatasheetClauseSource,
    current_source_model_ids,
    source_applies_to_rules_unit,
)
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    CatalogMovementActionGrantDescriptor,
    CatalogRandomMovementAttackBoostDescriptor,
)
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_frequency import (
    optional_ability_frequency_usage,
    optional_ability_frequency_usage_unavailable_reason,
)
from warhammer40k_core.engine.rule_ir_weapon_modifiers import (
    rule_ir_modified_weapon_profile,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    WeaponProfileModifierBinding,
    WeaponProfileModifierContext,
)
from warhammer40k_core.rules.rule_ir import parameter_payload

CATALOG_MOVEMENT_ACTION_GRANT_EFFECT_KIND = "catalog_movement_action_grant"
CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND = "catalog_random_movement_attack_boost"


def movement_action_grant_movement_binding(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogMovementActionGrantDescriptor,
) -> MovementBudgetModifierBinding:
    return MovementBudgetModifierBinding(
        modifier_id=f"{source.binding_id}:movement-action-grant",
        source_id=source.rule_ir.source_id,
        handler=_movement_action_grant_movement_handler(source, descriptor),
    )


def movement_action_grant_advance_binding(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogMovementActionGrantDescriptor,
) -> AdvanceMoveHookBinding:
    return AdvanceMoveHookBinding(
        hook_id=f"{source.binding_id}:movement-action-grant",
        source_id=source.rule_ir.source_id,
        handler=_movement_action_grant_handler(source, descriptor),
    )


def random_movement_attack_boost_movement_binding(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> MovementBudgetModifierBinding:
    return MovementBudgetModifierBinding(
        modifier_id=f"{source.binding_id}:random-movement-attack-boost",
        source_id=source.rule_ir.source_id,
        handler=_random_movement_attack_boost_movement_handler(source, descriptor),
    )


def random_movement_attack_boost_advance_binding(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> AdvanceMoveHookBinding:
    return AdvanceMoveHookBinding(
        hook_id=f"{source.binding_id}:random-movement-attack-boost",
        source_id=source.rule_ir.source_id,
        handler=_random_movement_attack_boost_handler(source, descriptor),
    )


def random_movement_attack_boost_weapon_binding(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> WeaponProfileModifierBinding:
    return WeaponProfileModifierBinding(
        modifier_id=f"{source.binding_id}:random-movement-attack-boost",
        source_id=source.rule_ir.source_id,
        handler=_random_movement_attack_boost_weapon_handler(source, descriptor),
    )


def _movement_action_grant_movement_handler(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogMovementActionGrantDescriptor,
) -> Callable[[MovementBudgetModifierContext], float]:
    def handler(context: MovementBudgetModifierContext) -> float:
        if not source_applies_to_rules_unit(
            source=source,
            context_unit_id=context.unit_instance_id,
            state=context.state,
        ):
            return context.current_movement_inches
        rules_unit = rules_unit_view_by_id(
            state=context.state,
            unit_instance_id=context.unit_instance_id,
        )
        if context.model_instance_id not in {
            model.model_instance_id for model in rules_unit.alive_models()
        }:
            return context.current_movement_inches
        for effect in context.state.persisting_effects_for_unit(rules_unit.unit_instance_id):
            payload = effect.effect_payload
            if (
                isinstance(payload, dict)
                and payload.get("effect_kind") == CATALOG_MOVEMENT_ACTION_GRANT_EFFECT_KIND
                and payload.get("source_rule_id") == source.rule_ir.source_id
            ):
                value = payload.get("movement_characteristic")
                if type(value) is not int or value != descriptor.movement_characteristic:
                    raise GameLifecycleError(
                        "Catalog movement action grant characteristic drifted."
                    )
                return float(value)
        return context.current_movement_inches

    return handler


def _movement_action_grant_handler(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogMovementActionGrantDescriptor,
) -> Callable[[AdvanceMoveContext], AdvanceMoveGrant | None]:
    def handler(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
        if (
            context.player_id != source.player_id
            or context.movement_phase_action != descriptor.movement_action
            or not source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.unit_instance_id,
                state=context.state,
            )
        ):
            return None
        return AdvanceMoveGrant(
            hook_id=f"{source.binding_id}:movement-action-grant",
            source_id=source.rule_ir.source_id,
            label=source.record.definition.name,
            granted_ranged_weapon_keywords=(),
            automatic=False,
            replay_payload={
                "consumer_id": "catalog-ir:movement-action-grant",
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.rule_ir.source_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "rules_unit_instance_id": context.unit_instance_id,
                "clause_id": source.clause.clause_id,
            },
            unit_effect_payload={
                "effect_kind": CATALOG_MOVEMENT_ACTION_GRANT_EFFECT_KIND,
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.rule_ir.source_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "rules_unit_instance_id": context.unit_instance_id,
                "clause_id": source.clause.clause_id,
                "movement_characteristic": descriptor.movement_characteristic,
                "charge_forbidden": descriptor.charge_forbidden,
                "phase_end_mortal_wounds": {
                    "roll_expression": "D6",
                    "roll_count_scope": "each_model_in_this_unit_at_phase_end",
                    "success_value": descriptor.phase_end_roll_success_value,
                    "mortal_wounds_per_success": descriptor.mortal_wounds_per_success,
                },
            },
            unit_effect_expiration="end_turn",
        )

    return handler


def _random_movement_attack_boost_handler(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> Callable[[AdvanceMoveContext], AdvanceMoveGrant | None]:
    def handler(context: AdvanceMoveContext) -> AdvanceMoveGrant | None:
        if (
            context.player_id != source.player_id
            or context.movement_phase_action != descriptor.movement_action
            or not source_applies_to_rules_unit(
                source=source,
                context_unit_id=context.unit_instance_id,
                state=context.state,
            )
        ):
            return None
        source_model_id = _single_current_source_model_id(context, source)
        usage = optional_ability_frequency_usage(
            rule_ir=source.rule_ir,
            clause=source.clause,
            player_id=source.player_id,
            source_unit_instance_id=source.unit.unit_instance_id,
            source_model_instance_id=source_model_id,
        )
        if usage is None:
            raise GameLifecycleError("Random movement attack boost requires a frequency limit.")
        unavailable = optional_ability_frequency_usage_unavailable_reason(
            usage=usage,
            event_log=context.event_log,
        )
        if unavailable == "missing_input:event_log":
            raise GameLifecycleError(
                "Random movement attack boost requires movement decision event evidence."
            )
        if unavailable is not None:
            return None
        return AdvanceMoveGrant(
            hook_id=f"{source.binding_id}:random-movement-attack-boost",
            source_id=source.rule_ir.source_id,
            label=source.record.definition.name,
            granted_ranged_weapon_keywords=(),
            movement_bonus_dice_expression=descriptor.movement_bonus_expression,
            automatic=False,
            replay_payload={
                "consumer_id": "catalog-ir:movement-action-grant",
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.rule_ir.source_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source_model_id,
                "rules_unit_instance_id": context.unit_instance_id,
                "clause_id": source.clause.clause_id,
            },
            unit_effect_payload={
                "effect_kind": CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND,
                "catalog_record_id": source.record.record_id,
                "source_rule_id": source.rule_ir.source_id,
                "source_unit_instance_id": source.unit.unit_instance_id,
                "source_model_instance_id": source_model_id,
                "rules_unit_instance_id": context.unit_instance_id,
                "clause_id": source.clause.clause_id,
                "attacks_delta": descriptor.attacks_delta,
                "weapon_names": list(descriptor.weapon_names),
            },
            unit_effect_expiration="end_turn",
            rule_frequency_usage=usage,
        )

    return handler


def _random_movement_attack_boost_movement_handler(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> Callable[[MovementBudgetModifierContext], float]:
    def handler(context: MovementBudgetModifierContext) -> float:
        if not source_applies_to_rules_unit(
            source=source,
            context_unit_id=context.unit_instance_id,
            state=context.state,
        ) or context.model_instance_id not in set(
            current_source_model_ids(state=context.state, source=source)
        ):
            return context.current_movement_inches
        payload = _active_validated_random_boost_payload(
            state=context.state,
            rules_unit_instance_id=rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=context.unit_instance_id,
            ).unit_instance_id,
            source=source,
            descriptor=descriptor,
        )
        if payload is None:
            return context.current_movement_inches
        bonus = payload.get("movement_bonus_inches")
        if type(bonus) is not int:
            raise GameLifecycleError("Random movement attack boost roll value drifted.")
        return context.current_movement_inches + float(bonus)

    return handler


def _random_movement_attack_boost_weapon_handler(
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> Callable[[WeaponProfileModifierContext], WeaponProfile]:
    def handler(context: WeaponProfileModifierContext) -> WeaponProfile:
        if not source_applies_to_rules_unit(
            source=source,
            context_unit_id=context.attacking_unit_instance_id,
            state=context.state,
        ) or context.attacker_model_instance_id not in set(
            current_source_model_ids(state=context.state, source=source)
        ):
            return context.weapon_profile
        payload = _active_validated_random_boost_payload(
            state=context.state,
            rules_unit_instance_id=rules_unit_view_by_id(
                state=context.state,
                unit_instance_id=context.attacking_unit_instance_id,
            ).unit_instance_id,
            source=source,
            descriptor=descriptor,
        )
        if payload is None:
            return context.weapon_profile
        return rule_ir_modified_weapon_profile(
            parameters=parameter_payload(source.clause.effects[1].parameters),
            profile=context.weapon_profile,
            source_id=source.rule_ir.source_id,
        )

    return handler


def _single_current_source_model_id(
    context: AdvanceMoveContext,
    source: CatalogDatasheetClauseSource,
) -> str:
    model_ids = current_source_model_ids(state=context.state, source=source)
    if len(model_ids) != 1:
        raise GameLifecycleError(
            "Model-scoped random movement attack boost requires one current source model."
        )
    return model_ids[0]


def _active_validated_random_boost_payload(
    *,
    state: object,
    rules_unit_instance_id: str,
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> Mapping[str, object] | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Random movement attack boost requires GameState.")
    matches: list[PersistingEffect] = []
    for effect in state.persisting_effects_for_unit(rules_unit_instance_id):
        if _effect_matches_random_boost_source(effect=effect, source=source):
            matches.append(effect)
    if len(matches) > 1:
        raise GameLifecycleError("Random movement attack boost effect is duplicated.")
    if not matches:
        return None
    effect = matches[0]
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Random movement attack boost effect payload must be an object.")
    _validate_random_boost_effect(
        state=state,
        current_battle_round=state.battle_round,
        effect=effect,
        payload=payload,
        rules_unit_instance_id=rules_unit_instance_id,
        source=source,
        descriptor=descriptor,
    )
    return payload


def _effect_matches_random_boost_source(
    *,
    effect: PersistingEffect,
    source: CatalogDatasheetClauseSource,
) -> bool:
    if effect.source_rule_id == source.rule_ir.source_id:
        return True
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        return False
    return payload.get("source_rule_id") == source.rule_ir.source_id or (
        payload.get("catalog_record_id") == source.record.record_id
        and payload.get("clause_id") == source.clause.clause_id
    )


def _validate_random_boost_effect(
    *,
    state: object,
    current_battle_round: int,
    effect: PersistingEffect,
    payload: Mapping[str, object],
    rules_unit_instance_id: str,
    source: CatalogDatasheetClauseSource,
    descriptor: CatalogRandomMovementAttackBoostDescriptor,
) -> None:
    source_model_ids = current_source_model_ids(state=state, source=source)
    if len(source_model_ids) != 1:
        raise GameLifecycleError(
            "Model-scoped random movement attack boost requires one current source model."
        )
    source_model_instance_id = source_model_ids[0]
    expected_payload_values: dict[str, object] = {
        "effect_kind": CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND,
        "catalog_record_id": source.record.record_id,
        "source_rule_id": source.rule_ir.source_id,
        "source_unit_instance_id": source.unit.unit_instance_id,
        "source_model_instance_id": source_model_instance_id,
        "rules_unit_instance_id": rules_unit_instance_id,
        "clause_id": source.clause.clause_id,
        "attacks_delta": descriptor.attacks_delta,
        "weapon_names": list(descriptor.weapon_names),
    }
    if set(payload) != {
        *expected_payload_values,
        "movement_bonus_inches",
        "movement_bonus_roll",
    } or any(payload.get(key) != value for key, value in expected_payload_values.items()):
        raise GameLifecycleError("Random movement attack boost effect payload drifted.")
    if (
        effect.owner_player_id != source.player_id
        or effect.source_rule_id != source.rule_ir.source_id
        or effect.target_unit_instance_ids != (rules_unit_instance_id,)
        or effect.started_battle_round != current_battle_round
        or effect.started_phase is not BattlePhaseKind.MOVEMENT
        or effect.expiration
        != EffectExpiration.end_turn(
            battle_round=effect.started_battle_round,
            player_id=source.player_id,
        )
    ):
        raise GameLifecycleError("Random movement attack boost effect authority drifted.")
    movement_bonus = payload.get("movement_bonus_inches")
    if type(movement_bonus) is not int:
        raise GameLifecycleError("Random movement attack boost roll value drifted.")
    raw_roll = payload.get("movement_bonus_roll")
    if not isinstance(raw_roll, dict):
        raise GameLifecycleError("Random movement attack boost roll evidence must be an object.")
    try:
        roll = RandomCharacteristicRoll.from_payload(
            cast(RandomCharacteristicRollPayload, raw_roll)
        )
    except (DiceRollSpecError, KeyError, TypeError) as exc:
        raise GameLifecycleError(
            "Random movement attack boost roll evidence is malformed."
        ) from exc
    if roll.to_payload() != raw_roll:
        raise GameLifecycleError("Random movement attack boost roll evidence is non-canonical.")
    expected_scope_id = (
        f"{rules_unit_instance_id}:{effect.effect_id.removesuffix(':unit')}:movement-bonus"
    )
    expected_roll_type = (
        f"random_characteristic.movement.unit_when_selected_to_move.{expected_scope_id}"
    )
    roll_spec = roll.roll_state.original_result.spec
    if (
        not effect.effect_id.startswith(f"{source.binding_id}:random-movement-attack-boost:")
        or not effect.effect_id.endswith(":unit")
        or roll.characteristic is not Characteristic.MOVEMENT
        or roll.timing is not RandomCharacteristicTiming.UNIT_WHEN_SELECTED_TO_MOVE
        or roll.scope_id != expected_scope_id
        or roll.value != movement_bonus
        or roll_spec.expression != descriptor.movement_bonus_expression
        or roll_spec.reason != f"{source.record.definition.name} movement bonus"
        or roll_spec.roll_type != expected_roll_type
        or roll_spec.actor_id != source.player_id
        or roll_spec.reroll_forbidden_rule_ids
        or roll.roll_state.original_result.source != "rng"
        or roll.roll_state.rerolls
        or roll.roll_state.result_override is not None
    ):
        raise GameLifecycleError("Random movement attack boost roll evidence drifted.")


__all__ = (
    "CATALOG_MOVEMENT_ACTION_GRANT_EFFECT_KIND",
    "CATALOG_RANDOM_MOVEMENT_ATTACK_BOOST_EFFECT_KIND",
    "movement_action_grant_advance_binding",
    "movement_action_grant_movement_binding",
    "random_movement_attack_boost_advance_binding",
    "random_movement_attack_boost_movement_binding",
    "random_movement_attack_boost_weapon_binding",
)
