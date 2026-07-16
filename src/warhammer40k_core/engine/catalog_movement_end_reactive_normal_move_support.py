from __future__ import annotations

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
    distance_dice_quantity: int
    distance_dice_sides: int
    distance_bonus: int

    def __post_init__(self) -> None:
        if type(self.effect) is not RuleEffectSpec:
            raise GameLifecycleError("Movement-end reactive move effect is invalid.")
        if type(self.trigger_distance_inches) not in {int, float}:
            raise GameLifecycleError("Movement-end reactive trigger distance is invalid.")
        if float(self.trigger_distance_inches) <= 0.0:
            raise GameLifecycleError("Movement-end reactive trigger distance must be positive.")
        object.__setattr__(self, "trigger_distance_inches", float(self.trigger_distance_inches))
        for field_name, value in (
            ("distance_dice_quantity", self.distance_dice_quantity),
            ("distance_dice_sides", self.distance_dice_sides),
            ("distance_bonus", self.distance_bonus),
        ):
            minimum = 0 if field_name == "distance_bonus" else 1
            if type(value) is not int or value < minimum:
                raise GameLifecycleError(f"Movement-end reactive move {field_name} is invalid.")


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
    expected = {
        "action": "move",
        "action_group": "movement_end_reactive_normal_move",
        "distance_bonus": 0,
        "distance_dice_quantity": 1,
        "distance_dice_sides": 6,
        "movement_kind": "triggered",
        "movement_mode": "normal",
        "optional": True,
    }
    return parameters == expected


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
    return CatalogMovementEndReactiveNormalMoveDescriptor(
        effect=effect,
        trigger_distance_inches=float(numeric_distance_inches),
        distance_dice_quantity=cast(int, effect_parameters["distance_dice_quantity"]),
        distance_dice_sides=cast(int, effect_parameters["distance_dice_sides"]),
        distance_bonus=cast(int, effect_parameters["distance_bonus"]),
    )
