from __future__ import annotations

import math
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_MOVEMENT_END_REACTIVE_NORMAL_MOVE_CONSUMER_ID = (
    "catalog-ir:movement-end-reactive-normal-move"
)


@dataclass(frozen=True, slots=True)
class CatalogMovementEndReactiveNormalMoveDescriptor:
    effect: RuleEffectSpec
    trigger_distance_inches: float
    fixed_distance_inches: float | None
    distance_dice_quantity: int | None
    distance_dice_sides: int | None
    distance_bonus: int

    def __post_init__(self) -> None:
        if type(self.effect) is not RuleEffectSpec:
            raise GameLifecycleError("Movement-end reactive move effect is invalid.")
        if type(self.trigger_distance_inches) not in {int, float}:
            raise GameLifecycleError("Movement-end reactive trigger distance is invalid.")
        if (
            not math.isfinite(float(self.trigger_distance_inches))
            or float(self.trigger_distance_inches) <= 0.0
        ):
            raise GameLifecycleError("Movement-end reactive trigger distance must be positive.")
        object.__setattr__(self, "trigger_distance_inches", float(self.trigger_distance_inches))
        if type(self.distance_bonus) is not int or self.distance_bonus < 0:
            raise GameLifecycleError("Movement-end reactive move distance_bonus is invalid.")
        has_fixed_distance = self.fixed_distance_inches is not None
        has_dice_distance = (
            self.distance_dice_quantity is not None or self.distance_dice_sides is not None
        )
        if has_fixed_distance == has_dice_distance:
            raise GameLifecycleError(
                "Movement-end reactive move requires exactly one fixed or dice distance."
            )
        if has_fixed_distance:
            fixed_distance = self.fixed_distance_inches
            if type(fixed_distance) not in {int, float}:
                raise GameLifecycleError(
                    "Movement-end reactive move fixed_distance_inches is invalid."
                )
            fixed_distance_inches = float(cast(int | float, fixed_distance))
            if not math.isfinite(fixed_distance_inches) or fixed_distance_inches <= 0.0:
                raise GameLifecycleError(
                    "Movement-end reactive move fixed_distance_inches is invalid."
                )
            if self.distance_bonus != 0:
                raise GameLifecycleError(
                    "Movement-end reactive fixed distance must not include a bonus."
                )
            object.__setattr__(self, "fixed_distance_inches", fixed_distance_inches)
            return
        if type(self.distance_dice_quantity) is not int or self.distance_dice_quantity < 1:
            raise GameLifecycleError(
                "Movement-end reactive move distance_dice_quantity is invalid."
            )
        if type(self.distance_dice_sides) is not int or self.distance_dice_sides < 2:
            raise GameLifecycleError("Movement-end reactive move distance_dice_sides is invalid.")


def clause_is_movement_end_reactive_normal_move(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Movement-end reactive move classifier requires RuleClause.")
    return _descriptor_or_none(clause) is not None


def movement_end_reactive_normal_move_descriptor(
    clause: RuleClause,
) -> CatalogMovementEndReactiveNormalMoveDescriptor:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Movement-end reactive move classifier requires RuleClause.")
    descriptor = _descriptor_or_none(clause)
    if descriptor is None:
        raise GameLifecycleError("RuleClause is not a supported movement-end reactive move.")
    return descriptor


def effect_is_movement_end_reactive_normal_move(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Movement-end reactive move classifier requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.OUT_OF_PHASE_ACTION:
        return False
    parameters = parameter_payload(effect.parameters)
    common = {
        "action": "move",
        "action_group": "movement_end_reactive_normal_move",
        "movement_kind": "triggered",
        "movement_mode": "normal",
        "optional": True,
    }
    distance_parameters = {key: value for key, value in parameters.items() if key not in common}
    if {key: parameters.get(key) for key in common} != common:
        return False
    if set(parameters) == {*common, "distance_inches"}:
        distance_inches = distance_parameters.get("distance_inches")
        return (
            type(distance_inches) in {int, float}
            and math.isfinite(float(cast(int | float, distance_inches)))
            and float(cast(int | float, distance_inches)) > 0.0
        )
    if set(parameters) != {
        *common,
        "distance_bonus",
        "distance_dice_quantity",
        "distance_dice_sides",
    }:
        return False
    distance_bonus = distance_parameters.get("distance_bonus")
    dice_quantity = distance_parameters.get("distance_dice_quantity")
    dice_sides = distance_parameters.get("distance_dice_sides")
    return (
        type(distance_bonus) is int
        and distance_bonus >= 0
        and type(dice_quantity) is int
        and dice_quantity >= 1
        and type(dice_sides) is int
        and dice_sides >= 2
    )


def _descriptor_or_none(
    clause: RuleClause,
) -> CatalogMovementEndReactiveNormalMoveDescriptor | None:
    if not clause.is_supported or clause.trigger is None:
        return None
    if clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    if parameter_payload(clause.trigger.parameters) != {
        "edge": "after",
        "owner": "opponent",
        "phase": "movement",
        "subject": "enemy_unit",
        "timing_window": "enemy_unit_move_end",
    }:
        return None
    if clause.target is None or clause.target.kind is not RuleTargetKind.THIS_UNIT:
        return None
    if clause.target.parameters or clause.duration is not None or len(clause.conditions) != 2:
        return None
    trigger_distance = clause.conditions[0]
    engagement_gate = clause.conditions[1]
    if trigger_distance.kind is not RuleConditionKind.DISTANCE_PREDICATE:
        return None
    trigger_parameters = parameter_payload(trigger_distance.parameters)
    if set(trigger_parameters) != {
        "distance_inches",
        "object_kind",
        "object_reference",
        "predicate",
        "qualifier",
        "range_kind",
        "subject",
    }:
        return None
    distance_inches = trigger_parameters.get("distance_inches")
    if type(distance_inches) not in {int, float}:
        return None
    numeric_distance_inches = cast(int | float, distance_inches)
    if float(numeric_distance_inches) <= 0.0:
        return None
    if {key: value for key, value in trigger_parameters.items() if key != "distance_inches"} != {
        "object_kind": "unit",
        "object_reference": "this",
        "predicate": "within",
        "qualifier": None,
        "range_kind": "numeric_range",
        "subject": "enemy_unit",
    }:
        return None
    if engagement_gate.kind is not RuleConditionKind.DISTANCE_PREDICATE:
        return None
    if parameter_payload(engagement_gate.parameters) != {
        "distance_inches": None,
        "negated": True,
        "object_allegiance": "enemy",
        "object_kind": "unit",
        "object_quantity": "one_or_more",
        "predicate": "within_engagement_range",
        "qualifier": None,
        "range_kind": "engagement_range",
        "subject": "this_unit",
    }:
        return None
    if len(clause.effects) != 1:
        return None
    effect = clause.effects[0]
    if not effect_is_movement_end_reactive_normal_move(effect):
        return None
    effect_parameters = parameter_payload(effect.parameters)
    fixed_distance = effect_parameters.get("distance_inches")
    if fixed_distance is not None:
        fixed_distance_inches: float | None = float(cast(int | float, fixed_distance))
        distance_dice_quantity: int | None = None
        distance_dice_sides: int | None = None
        distance_bonus = 0
    else:
        fixed_distance_inches = None
        distance_dice_quantity = cast(int, effect_parameters["distance_dice_quantity"])
        distance_dice_sides = cast(int, effect_parameters["distance_dice_sides"])
        distance_bonus = cast(int, effect_parameters["distance_bonus"])
    return CatalogMovementEndReactiveNormalMoveDescriptor(
        effect=effect,
        trigger_distance_inches=float(numeric_distance_inches),
        fixed_distance_inches=fixed_distance_inches,
        distance_dice_quantity=distance_dice_quantity,
        distance_dice_sides=distance_dice_sides,
        distance_bonus=distance_bonus,
    )
