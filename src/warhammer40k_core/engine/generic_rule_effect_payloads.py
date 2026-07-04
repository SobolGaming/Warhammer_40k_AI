from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError


def generic_rule_effect_payload_grants_ability(
    effect_payload: Mapping[str, JsonValue],
    *,
    ability: str,
) -> bool:
    if effect_payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return False
    rule_effect = effect_payload.get("effect")
    if not isinstance(rule_effect, dict):
        raise GameLifecycleError("Generic RuleIR effect payload requires effect object.")
    return rule_effect_grants_ability(rule_effect, ability=ability)


def rule_effect_grants_ability(
    rule_effect: Mapping[str, JsonValue],
    *,
    ability: str,
) -> bool:
    return (
        rule_effect.get("kind") == "grant_ability"
        and rule_effect_ability_parameter(rule_effect) == ability
    )


def rule_effect_ability_parameter(rule_effect: Mapping[str, JsonValue]) -> str | None:
    if rule_effect.get("kind") != "grant_ability":
        return None
    raw_parameters = rule_effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic grant_ability effect parameters must be a list.")
    for parameter in raw_parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Generic grant_ability effect parameter must be an object.")
        if parameter.get("key") != "ability":
            continue
        value = parameter.get("value")
        if type(value) is not str:
            raise GameLifecycleError("Generic grant_ability ability parameter must be a string.")
        return value
    return None
