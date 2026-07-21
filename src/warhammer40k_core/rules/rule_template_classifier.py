from __future__ import annotations

from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameter_payload,
)
from warhammer40k_core.rules.rule_templates import (
    ALLOCATED_ATTACK_DAMAGE_MODIFIER_TEMPLATE_ID,
    AURA_TEMPLATE_ID,
    CHARACTERISTIC_MODIFIER_TEMPLATE_ID,
    CHARACTERISTIC_SET_TEMPLATE_ID,
    CONTEXTUAL_STATUS_TEMPLATE_ID,
    DESPERATE_ESCAPE_TEMPLATE_ID,
    DICE_ROLL_MODIFIER_TEMPLATE_ID,
    DICE_ROLL_OVERRIDE_TEMPLATE_ID,
    DISTANCE_PREDICATE_TEMPLATE_ID,
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
    MOVEMENT_DISTANCE_TEMPLATE_ID,
    OUT_OF_PHASE_ACTION_TEMPLATE_ID,
    PLACEMENT_TEMPLATE_ID,
    REROLL_PERMISSION_TEMPLATE_ID,
    RESOURCE_MODIFIER_TEMPLATE_ID,
    RETURN_ON_DEATH_TEMPLATE_ID,
    SELECTED_TARGET_TEMPLATE_ID,
    TIMING_WINDOW_TEMPLATE_ID,
    TRACKED_TARGET_SELECTION_TEMPLATE_ID,
    WEAPON_ABILITY_GRANT_TEMPLATE_ID,
    rule_template_by_id,
)


def template_id_for_clause(
    *,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
) -> str | None:
    candidates: list[str] = []
    if _is_allocated_attack_damage_modifier_clause(
        trigger=trigger,
        conditions=conditions,
        target=target,
        effects=effects,
    ):
        candidates.append(ALLOCATED_ATTACK_DAMAGE_MODIFIER_TEMPLATE_ID)
    if any(condition.kind is RuleConditionKind.AURA for condition in conditions):
        candidates.append(AURA_TEMPLATE_ID)
    for effect in effects:
        if effect.kind is RuleEffectKind.GRANT_WEAPON_ABILITY:
            candidates.append(WEAPON_ABILITY_GRANT_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.GRANT_ABILITY:
            candidates.append(GRANT_ABILITY_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS:
            candidates.append(CONTEXTUAL_STATUS_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.FORCE_DESPERATE_ESCAPE_TESTS:
            candidates.append(DESPERATE_ESCAPE_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_DICE_ROLL:
            candidates.append(DICE_ROLL_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.OVERRIDE_DICE_ROLL_RESULT:
            candidates.append(DICE_ROLL_OVERRIDE_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.REROLL_PERMISSION:
            candidates.append(REROLL_PERMISSION_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
            candidates.append(CHARACTERISTIC_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SET_CHARACTERISTIC:
            candidates.append(CHARACTERISTIC_SET_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.MODIFY_MOVE_DISTANCE:
            candidates.append(MOVEMENT_DISTANCE_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.OUT_OF_PHASE_ACTION:
            candidates.append(OUT_OF_PHASE_ACTION_TEMPLATE_ID)
        elif effect.kind in {
            RuleEffectKind.MODIFY_COMMAND_POINTS,
            RuleEffectKind.ADD_VICTORY_POINTS,
        }:
            candidates.append(RESOURCE_MODIFIER_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.RETURN_DESTROYED_TARGET:
            candidates.append(RETURN_ON_DEATH_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.SELECT_TRACKED_TARGET:
            candidates.append(TRACKED_TARGET_SELECTION_TEMPLATE_ID)
        elif effect.kind is RuleEffectKind.INFLICT_MORTAL_WOUNDS:
            candidates.append(TIMING_WINDOW_TEMPLATE_ID)
        elif effect.kind in {
            RuleEffectKind.PLACEMENT_PERMISSION,
            RuleEffectKind.PLACEMENT_RESTRICTION,
        }:
            candidates.append(PLACEMENT_TEMPLATE_ID)
    if target is not None:
        candidates.append(SELECTED_TARGET_TEMPLATE_ID)
    for condition in conditions:
        if condition.kind is RuleConditionKind.KEYWORD_GATE:
            candidates.append(KEYWORD_GATE_TEMPLATE_ID)
        elif condition.kind is RuleConditionKind.DISTANCE_PREDICATE:
            candidates.append(DISTANCE_PREDICATE_TEMPLATE_ID)
    if trigger is not None:
        candidates.append(TIMING_WINDOW_TEMPLATE_ID)
    if not candidates:
        return None
    template_id = candidates[0]
    rule_template_by_id(template_id)
    return template_id


def _is_allocated_attack_damage_modifier_clause(
    *,
    trigger: RuleTrigger | None,
    conditions: tuple[RuleCondition, ...],
    target: RuleTargetSpec | None,
    effects: tuple[RuleEffectSpec, ...],
) -> bool:
    if (
        trigger is None
        or trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or parameter_payload(trigger.parameters)
        != {
            "edge": "during",
            "subject": "incoming_attack",
            "timing_window": "attack_allocated",
        }
        or conditions
        or target is None
        or target.kind is not RuleTargetKind.THIS_MODEL
        or target.parameters
        or len(effects) != 1
    ):
        return False
    effect = effects[0]
    parameters = parameter_payload(effect.parameters)
    return (
        effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC
        and parameters.get("characteristic") == "damage"
        and type(parameters.get("delta")) is int
        and set(parameters) == {"characteristic", "delta"}
    )
