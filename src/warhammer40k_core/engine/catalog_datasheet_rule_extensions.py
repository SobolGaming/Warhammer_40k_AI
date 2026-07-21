from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CHARGE_AFTER_MOVEMENT_ACTIONS_TEMPLATE_ID = "phase17n:charge-after-movement-actions"
CONDITIONAL_LEADING_FIXED_ADVANCE_TEMPLATE_ID = "phase17n:conditional-leading-fixed-advance"
CONDITIONAL_LEADING_WEAPON_RANGE_TEMPLATE_ID = "phase17n:conditional-leading-weapon-range-modifier"
CONDITIONAL_LEADING_CHARGE_AFTER_MOVEMENT_ACTION_TEMPLATE_ID = (
    "phase17n:conditional-leading-charge-after-movement-action"
)
MOVEMENT_TARGET_PAIR_TEMPLATE_ID = "phase17n:movement-start-or-end-friendly-enemy-target-pair"
COMMAND_RESTORATION_TEMPLATE_ID = "phase17n:command-phase-friendly-unit-restoration"

EXACT_EXTENDED_DATASHEET_TEMPLATE_IDS = frozenset(
    {
        CHARGE_AFTER_MOVEMENT_ACTIONS_TEMPLATE_ID,
        CONDITIONAL_LEADING_FIXED_ADVANCE_TEMPLATE_ID,
        CONDITIONAL_LEADING_WEAPON_RANGE_TEMPLATE_ID,
        CONDITIONAL_LEADING_CHARGE_AFTER_MOVEMENT_ACTION_TEMPLATE_ID,
        MOVEMENT_TARGET_PAIR_TEMPLATE_ID,
        COMMAND_RESTORATION_TEMPLATE_ID,
    }
)


@dataclass(frozen=True, slots=True)
class CatalogChargeAfterMovementActionsDescriptor:
    abilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogConditionalLeadingFixedAdvanceDescriptor:
    fixed_advance_inches: int
    movement_bonus_inches: int
    ignores_vertical_distance: bool


@dataclass(frozen=True, slots=True)
class CatalogConditionalLeadingWeaponRangeDescriptor:
    range_bonus_inches: int
    required_weapon_keyword: str


@dataclass(frozen=True, slots=True)
class CatalogConditionalLeadingChargeAfterMovementActionDescriptor:
    movement_action_effect_kind: str


@dataclass(frozen=True, slots=True)
class CatalogMovementTargetPairDescriptor:
    distance_inches: int
    required_keyword_sequence: tuple[str, ...]
    excluded_keywords: tuple[str, ...]
    weapon_ability: str
    weapon_ability_value: int


@dataclass(frozen=True, slots=True)
class CatalogCommandRestorationDescriptor:
    distance_inches: int
    required_keyword_sequence: tuple[str, ...]
    heal_expression: str
    returned_models: int


def clause_uses_exact_extended_datasheet_template(clause: RuleClause) -> bool:
    return clause.template_id in EXACT_EXTENDED_DATASHEET_TEMPLATE_IDS


def extended_datasheet_descriptor_for_clause(clause: RuleClause) -> object | None:
    for classifier in (
        charge_after_movement_actions_descriptor_for_clause,
        conditional_leading_fixed_advance_descriptor_for_clause,
        conditional_leading_weapon_range_descriptor_for_clause,
        conditional_leading_charge_after_movement_action_descriptor_for_clause,
        movement_target_pair_descriptor_for_clause,
        command_restoration_descriptor_for_clause,
    ):
        descriptor = classifier(clause)
        if descriptor is not None:
            return descriptor
    return None


def charge_after_movement_actions_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogChargeAfterMovementActionsDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != CHARGE_AFTER_MOVEMENT_ACTIONS_TEMPLATE_ID
        or clause.trigger is not None
        or clause.conditions
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.PERMANENT
        or clause.duration.parameters
        or len(clause.effects) != 2
    ):
        return None
    abilities: list[str] = []
    for effect in clause.effects:
        parameters = parameter_payload(effect.parameters)
        ability = parameters.get("ability")
        if (
            effect.kind is not RuleEffectKind.GRANT_ABILITY
            or ability not in {"can_advance_and_charge", "can_fall_back_and_charge"}
            or parameters.get("target_scope") != "this_unit"
            or set(parameters) != {"ability", "target_scope"}
        ):
            return None
        abilities.append(str(ability))
    if set(abilities) != {"can_advance_and_charge", "can_fall_back_and_charge"}:
        return None
    return CatalogChargeAfterMovementActionsDescriptor(abilities=tuple(sorted(abilities)))


def conditional_leading_fixed_advance_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalLeadingFixedAdvanceDescriptor | None:
    if (
        not _has_exact_leading_shape(
            clause,
            template_id=CONDITIONAL_LEADING_FIXED_ADVANCE_TEMPLATE_ID,
        )
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters) != {"endpoint": "phase"}
        or len(clause.effects) != 3
    ):
        return None
    roll, movement, transit = clause.effects
    roll_parameters = parameter_payload(roll.parameters)
    movement_parameters = parameter_payload(movement.parameters)
    transit_parameters = parameter_payload(transit.parameters)
    if (
        roll.kind is not RuleEffectKind.OVERRIDE_DICE_ROLL_RESULT
        or roll_parameters != {"fixed_result": 6, "roll_type": "advance", "skip_roll": True}
        or movement.kind is not RuleEffectKind.MODIFY_MOVE_DISTANCE
        or movement_parameters
        != {
            "characteristic": "movement",
            "delta": 6,
            "target_scope": "models_in_leading_unit",
        }
        or transit.kind is not RuleEffectKind.MOVEMENT_TRANSIT_PERMISSION
        or transit_parameters
        != {
            "movement_action": "advance",
            "permission": "ignore_vertical_distance",
            "target_scope": "models_in_leading_unit",
        }
    ):
        return None
    return CatalogConditionalLeadingFixedAdvanceDescriptor(
        fixed_advance_inches=6,
        movement_bonus_inches=0,
        ignores_vertical_distance=True,
    )


def conditional_leading_weapon_range_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalLeadingWeaponRangeDescriptor | None:
    if (
        not _has_exact_leading_shape(
            clause,
            template_id=CONDITIONAL_LEADING_WEAPON_RANGE_TEMPLATE_ID,
        )
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.WHILE_CONDITION_TRUE
        or clause.duration.parameters
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    if effect.kind is not RuleEffectKind.MODIFY_CHARACTERISTIC or parameters != {
        "characteristic": "range",
        "delta": 6,
        "required_weapon_keyword": "MELTA",
        "target_scope": "weapons_equipped_by_models_in_leading_unit",
    }:
        return None
    return CatalogConditionalLeadingWeaponRangeDescriptor(
        range_bonus_inches=6,
        required_weapon_keyword="MELTA",
    )


def conditional_leading_charge_after_movement_action_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalLeadingChargeAfterMovementActionDescriptor | None:
    if (
        not _has_exact_leading_shape(
            clause,
            template_id=CONDITIONAL_LEADING_CHARGE_AFTER_MOVEMENT_ACTION_TEMPLATE_ID,
        )
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.WHILE_CONDITION_TRUE
        or clause.duration.parameters
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    if effect.kind is not RuleEffectKind.GRANT_ABILITY or parameters != {
        "ability": "can_charge_after_movement_action",
        "movement_action_effect_kind": "catalog_movement_action_grant",
        "target_scope": "leading_unit",
    }:
        return None
    return CatalogConditionalLeadingChargeAfterMovementActionDescriptor(
        movement_action_effect_kind="catalog_movement_action_grant"
    )


def movement_target_pair_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogMovementTargetPairDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != MOVEMENT_TARGET_PAIR_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or parameter_payload(clause.trigger.parameters)
        != {
            "edges": ("start", "end"),
            "owner": "active_player",
            "phase": "movement",
            "subject": "this_model",
            "timing_window": "model_starts_or_ends_move",
        }
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.FRIENDLY_UNIT
        or parameter_payload(clause.target.parameters)
        != {
            "allegiance": "friendly",
            "paired_target": "one_visible_enemy_unit",
            "selection": "one",
        }
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters)
        != {"boundary": "start", "endpoint": "next_movement_phase"}
        or len(clause.effects) != 1
    ):
        return None
    frequency = _single_condition(clause, RuleConditionKind.FREQUENCY_LIMIT)
    distance = _single_condition(clause, RuleConditionKind.DISTANCE_PREDICATE)
    keywords = _single_condition(clause, RuleConditionKind.KEYWORD_GATE)
    visibility = _single_condition(clause, RuleConditionKind.VISIBILITY_PREDICATE)
    if (
        frequency != {"limit": 1, "period": "turn"}
        or distance
        != {
            "distance_inches": 6,
            "object_kind": "unit",
            "predicate": "within",
            "subject": "selected_friendly_unit",
        }
        or keywords
        != {
            "excluded_keywords": ("TITANIC",),
            "gate_subject": "selected_friendly_unit",
            "required_keyword_sequence": ("WRAITH CONSTRUCT",),
        }
        or visibility
        != {
            "object_reference": "this_model",
            "predicate": "visible_to",
            "subject": "selected_enemy_unit",
        }
    ):
        return None
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY or parameter_payload(
        effect.parameters
    ) != {
        "attack_role": "attacker",
        "target_scope": "selected_friendly_unit",
        "target_unit_scope": "selected_enemy_unit",
        "weapon_ability": "Sustained Hits",
        "weapon_ability_value": 1,
    }:
        return None
    return CatalogMovementTargetPairDescriptor(
        distance_inches=6,
        required_keyword_sequence=("WRAITH CONSTRUCT",),
        excluded_keywords=("TITANIC",),
        weapon_ability="Sustained Hits",
        weapon_ability_value=1,
    )


def command_restoration_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogCommandRestorationDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != COMMAND_RESTORATION_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or parameter_payload(clause.trigger.parameters)
        != {
            "edge": "start",
            "owner": "active_player",
            "phase": "command",
            "subject": "this_model",
            "timing_window": "command_phase_start",
        }
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.FRIENDLY_UNIT
        or parameter_payload(clause.target.parameters)
        != {"allegiance": "friendly", "selection": "one"}
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.IMMEDIATE
        or clause.duration.parameters
        or len(clause.effects) != 2
    ):
        return None
    distance = _single_condition(clause, RuleConditionKind.DISTANCE_PREDICATE)
    keywords = _single_condition(clause, RuleConditionKind.KEYWORD_GATE)
    frequency = _single_condition(clause, RuleConditionKind.FREQUENCY_LIMIT)
    returned, healed = clause.effects
    if (
        distance
        != {
            "distance_inches": 6,
            "object_kind": "unit",
            "predicate": "within",
            "subject": "selected_friendly_unit",
        }
        or keywords
        != {
            "gate_subject": "selected_friendly_unit",
            "required_keyword_sequence": ("WRAITH CONSTRUCT",),
        }
        or frequency != {"limit": 1, "period": "turn", "scope": "selected_unit"}
        or returned.kind is not RuleEffectKind.RETURN_DESTROYED_TARGET
        or parameter_payload(returned.parameters)
        != {
            "amount": 1,
            "condition": "unit_has_destroyed_models",
            "restore_wounds_mode": "full_health",
            "target_scope": "selected_unit",
        }
        or healed.kind is not RuleEffectKind.RESTORE_LOST_WOUNDS
        or parameter_payload(healed.parameters)
        != {
            "amount_expression": "D3",
            "condition": "unit_has_no_destroyed_models",
            "maximum_models": 1,
            "target_scope": "selected_unit",
        }
    ):
        return None
    return CatalogCommandRestorationDescriptor(
        distance_inches=6,
        required_keyword_sequence=("WRAITH CONSTRUCT",),
        heal_expression="D3",
        returned_models=1,
    )


def _has_exact_leading_shape(clause: RuleClause, *, template_id: str) -> bool:
    return (
        clause.is_supported
        and clause.template_id == template_id
        and clause.trigger is None
        and clause.target is not None
        and clause.target.kind is RuleTargetKind.SELECTED_UNIT
        and parameter_payload(clause.target.parameters)
        == {"relationship": "this_model_leading_unit"}
        and len(clause.conditions) == 1
        and clause.conditions[0].kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(clause.conditions[0].parameters)
        == {"relationship": "this_model_leading_unit"}
    )


def _single_condition(clause: RuleClause, kind: RuleConditionKind) -> dict[str, object] | None:
    matches = tuple(condition for condition in clause.conditions if condition.kind is kind)
    if len(matches) != 1:
        return None
    return dict(parameter_payload(matches[0].parameters))
