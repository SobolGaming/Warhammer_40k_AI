"""Read-only rendering of fixed and random profile characteristics."""

from __future__ import annotations

from typing import NotRequired, TypedDict

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.dice import DiceExpressionPayload
from warhammer40k_core.core.random_profile_values import (
    ProfileCharacteristicValue,
    RandomProfileValue,
)
from warhammer40k_core.engine.phase import GameLifecycleError


class RedactionDisplayPayload(TypedDict):
    hidden: bool
    reason: str | None


class CharacteristicDisplayPayload(TypedDict):
    characteristic: str
    label: str
    value_kind: str
    raw: int | None
    base: int | None
    final: int | None
    display_value: str | None
    applied_modifier_ids: list[str]
    redaction: RedactionDisplayPayload
    random_expression: NotRequired[DiceExpressionPayload]


def characteristic_display_payload(
    *,
    value: ProfileCharacteristicValue,
    label: str,
    use_base_values: bool,
) -> CharacteristicDisplayPayload:
    if isinstance(value, RandomProfileValue):
        evaluation = None if use_base_values else value.evaluation
        return {
            "characteristic": value.characteristic.value,
            "label": label,
            "value_kind": value.value_kind.value,
            "raw": None if evaluation is None else evaluation.raw,
            "base": None if evaluation is None else evaluation.base,
            "final": None if evaluation is None else evaluation.final,
            "display_value": value.expression.canonical()
            if evaluation is None
            else _characteristic_display_value(
                characteristic=value.characteristic,
                value=evaluation.final,
                is_dash=evaluation.is_dash,
            ),
            "random_expression": value.expression.to_payload(),
            "applied_modifier_ids": []
            if evaluation is None
            else list(evaluation.applied_modifier_ids),
            "redaction": visible_redaction(),
        }
    if type(value) is not CharacteristicValue:
        raise GameLifecycleError("Characteristic display requires CharacteristicValue.")
    final = value.base if use_base_values else value.final
    return {
        "characteristic": value.characteristic.value,
        "label": label,
        "value_kind": value.value_kind.value,
        "raw": value.raw,
        "base": value.base,
        "final": final,
        "display_value": _characteristic_display_value(
            characteristic=value.characteristic,
            value=final,
            is_dash=value.is_dash,
        ),
        "applied_modifier_ids": [] if use_base_values else list(value.applied_modifier_ids),
        "redaction": visible_redaction(),
    }


def _characteristic_display_value(
    *,
    characteristic: Characteristic,
    value: int,
    is_dash: bool,
) -> str:
    if is_dash:
        return "-"
    if characteristic is Characteristic.MOVEMENT:
        return f'{value}"'
    if characteristic in {
        Characteristic.SAVE,
        Characteristic.INVULNERABLE_SAVE,
        Characteristic.LEADERSHIP,
    }:
        return f"{value}+"
    return str(value)


def visible_redaction() -> RedactionDisplayPayload:
    return {"hidden": False, "reason": None}
