from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

CATALOG_SELECTED_TARGET_TEST_MODIFIER_HOOK_ID = "catalog-ir:selected-target-test-roll-modifier"
BATTLE_SHOCK_TEST_ROLL_TYPE = "battle_shock"
LEADERSHIP_TEST_ROLL_TYPE = "leadership"
_SUPPORTED_TEST_ROLL_TYPES = frozenset({BATTLE_SHOCK_TEST_ROLL_TYPE, LEADERSHIP_TEST_ROLL_TYPE})


def selected_target_test_roll_modifiers(
    *,
    state: GameState,
    unit_instance_id: str,
    roll_type: str,
) -> tuple[RollModifier, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Selected-target test modifiers require a GameState.")
    target_id = IdentifierValidator(GameLifecycleError)(
        "unit_instance_id",
        unit_instance_id,
    )
    if roll_type not in _SUPPORTED_TEST_ROLL_TYPES:
        raise GameLifecycleError("Selected-target test modifier roll_type is unsupported.")
    modifiers = tuple(
        modifier
        for effect in state.persisting_effects_for_unit(target_id)
        if (
            modifier := selected_target_test_roll_modifier_from_effect(
                effect=effect,
                roll_type=roll_type,
            )
        )
        is not None
    )
    modifier_ids = tuple(modifier.modifier_id for modifier in modifiers)
    if len(modifier_ids) != len(set(modifier_ids)):
        raise GameLifecycleError("Selected-target test modifier IDs must be unique.")
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))


def selected_target_test_roll_modifier_from_effect(
    *,
    effect: PersistingEffect,
    roll_type: str,
) -> RollModifier | None:
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    catalog_selected_target = payload.get("catalog_selected_target")
    if catalog_selected_target is None:
        return None
    if not isinstance(catalog_selected_target, dict):
        raise GameLifecycleError("Catalog selected-target effect metadata must be an object.")
    effect_payload = payload.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError("Catalog selected-target effect payload must be an object.")
    rule_effect = RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, effect_payload))
    if rule_effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return None
    parameters = parameter_payload(rule_effect.parameters)
    if parameters.get("roll_type") != roll_type:
        return None
    if parameters.get("target_scope") != "selected_unit":
        raise GameLifecycleError("Selected-target test modifier target scope is invalid.")
    delta = parameters.get("delta")
    if type(delta) is not int:
        raise GameLifecycleError("Selected-target test modifier delta must be an int.")
    return RollModifier(
        modifier_id=f"{effect.effect_id}:{roll_type}",
        source_id=effect.source_rule_id,
        operand=delta,
    )
