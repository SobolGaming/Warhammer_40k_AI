from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.ruleset_descriptor import MovementMode, movement_mode_from_token
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

CATALOG_IR_FIGHT_END_TRIGGERED_MOVEMENT_CONSUMER_ID = "catalog-ir:fight-end-triggered-movement"


@dataclass(frozen=True, slots=True)
class CatalogFightEndTriggeredMovementDescriptor:
    normal_effect: RuleEffectSpec
    fall_back_effect: RuleEffectSpec
    distance_dice_quantity: int
    distance_dice_sides: int
    distance_bonus: int

    def __post_init__(self) -> None:
        if type(self.normal_effect) is not RuleEffectSpec:
            raise GameLifecycleError("Fight-end movement normal effect is invalid.")
        if type(self.fall_back_effect) is not RuleEffectSpec:
            raise GameLifecycleError("Fight-end movement Fall Back effect is invalid.")
        for field_name, value in (
            ("distance_dice_quantity", self.distance_dice_quantity),
            ("distance_dice_sides", self.distance_dice_sides),
            ("distance_bonus", self.distance_bonus),
        ):
            minimum = 0 if field_name == "distance_bonus" else 1
            if type(value) is not int or value < minimum:
                raise GameLifecycleError(f"Fight-end movement {field_name} is invalid.")

    def effect_for_engagement_state(self, *, is_engaged: bool) -> RuleEffectSpec:
        if type(is_engaged) is not bool:
            raise GameLifecycleError("Fight-end movement engagement state must be boolean.")
        return self.fall_back_effect if is_engaged else self.normal_effect

    def movement_mode_for_engagement_state(self, *, is_engaged: bool) -> MovementMode:
        effect = self.effect_for_engagement_state(is_engaged=is_engaged)
        return movement_mode_from_token(parameter_payload(effect.parameters)["movement_mode"])


def clause_is_fight_end_triggered_movement(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Fight-end movement classifier requires RuleClause.")
    return _descriptor_or_none(clause) is not None


def fight_end_triggered_movement_descriptor(
    clause: RuleClause,
) -> CatalogFightEndTriggeredMovementDescriptor:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Fight-end movement classifier requires RuleClause.")
    descriptor = _descriptor_or_none(clause)
    if descriptor is None:
        raise GameLifecycleError("RuleClause is not supported Fight-end triggered movement.")
    return descriptor


def effect_is_fight_end_triggered_movement(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Fight-end movement classifier requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.OUT_OF_PHASE_ACTION:
        return False
    parameters = parameter_payload(effect.parameters)
    common = {
        "action": "move",
        "action_group": "fight_end_conditional_move",
        "distance_bonus": 3,
        "distance_dice_quantity": 1,
        "distance_dice_sides": 3,
        "movement_kind": "triggered",
        "optional": True,
    }
    expected_keys = {*common, "engagement_state", "movement_mode"}
    if set(parameters) != expected_keys:
        return False
    if any(parameters.get(key) != value for key, value in common.items()):
        return False
    return (parameters.get("engagement_state"), parameters.get("movement_mode")) in {
        ("not_within", "normal"),
        ("within", "fall_back"),
    }


def _descriptor_or_none(
    clause: RuleClause,
) -> CatalogFightEndTriggeredMovementDescriptor | None:
    if not clause.is_supported or clause.trigger is None:
        return None
    if clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return None
    if parameter_payload(clause.trigger.parameters) != {
        "edge": "end",
        "owner": "either_player",
        "phase": "fight",
        "subject": "this_unit",
        "timing_window": "end_fight_phase",
    }:
        return None
    if clause.target is None or clause.target.kind is not RuleTargetKind.THIS_UNIT:
        return None
    if clause.target.parameters or clause.duration is not None or len(clause.conditions) != 1:
        return None
    condition = clause.conditions[0]
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return None
    if parameter_payload(condition.parameters) != {
        "gate_subject": "this_unit",
        "relationship": "eligible_to_fight_this_phase",
    }:
        return None
    if len(clause.effects) != 2:
        return None
    normal_effect = _effect_for_mode(clause.effects, movement_mode="normal")
    fall_back_effect = _effect_for_mode(clause.effects, movement_mode="fall_back")
    if normal_effect is None or fall_back_effect is None:
        return None
    return CatalogFightEndTriggeredMovementDescriptor(
        normal_effect=normal_effect,
        fall_back_effect=fall_back_effect,
        distance_dice_quantity=1,
        distance_dice_sides=3,
        distance_bonus=3,
    )


def _effect_for_mode(
    effects: tuple[RuleEffectSpec, ...], *, movement_mode: str
) -> RuleEffectSpec | None:
    matching = tuple(
        effect
        for effect in effects
        if effect_is_fight_end_triggered_movement(effect)
        and parameter_payload(effect.parameters).get("movement_mode") == movement_mode
    )
    return matching[0] if len(matching) == 1 else None
