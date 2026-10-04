"""Structured source classification carried by provider-authorized damage outcomes."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.ability_damage_source import (
    AbilityDamageClassification,
    AbilityDamageSource,
    AbilityDamageSourceError,
    AbilityDamageSourcePayload,
)

ABILITY_DAMAGE_SOURCE_KEY = "ability_damage_source"


def ability_damage_source_context(
    *, source: AbilityDamageSource, source_context: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    """Preserve a provider's classified ability outcome; this grants no activation."""
    if type(source) is not AbilityDamageSource:
        raise GameLifecycleError("Ability damage requires a typed source descriptor.")
    if source_context.get("source_rule_id") != source.source_rule_id:
        raise GameLifecycleError("Ability damage source identity drifted.")
    if ABILITY_DAMAGE_SOURCE_KEY in source_context:
        raise GameLifecycleError("Ability damage source was configured twice.")
    return {**source_context, ABILITY_DAMAGE_SOURCE_KEY: cast(JsonValue, source.to_payload())}


def ability_damage_is_psychic_attack(
    source_context: JsonValue, *, source_rule_id: str | None = None
) -> bool:
    if not isinstance(source_context, dict) or ABILITY_DAMAGE_SOURCE_KEY not in source_context:
        return False
    payload = source_context[ABILITY_DAMAGE_SOURCE_KEY]
    if not isinstance(payload, dict):
        raise GameLifecycleError("Ability damage source context must contain a descriptor.")
    try:
        source = AbilityDamageSource.from_payload(cast(AbilityDamageSourcePayload, payload))
    except AbilityDamageSourceError as exc:
        raise GameLifecycleError("Ability damage source context is malformed.") from exc
    if source_context.get("source_rule_id") != source.source_rule_id:
        raise GameLifecycleError("Ability damage source context identity drifted.")
    if source_rule_id is not None and source.source_rule_id != source_rule_id:
        raise GameLifecycleError("Ability damage application source identity drifted.")
    return source.classification is AbilityDamageClassification.PSYCHIC_ATTACK


def source_permission_damage_context(
    *, permission: PersistingEffect | None, source_context: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    if permission is None:
        return source_context
    payload = permission.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Ability damage permission payload must be an object.")
    if ABILITY_DAMAGE_SOURCE_KEY not in payload:
        return source_context
    context = {
        **source_context,
        "source_rule_id": permission.source_rule_id,
        ABILITY_DAMAGE_SOURCE_KEY: payload[ABILITY_DAMAGE_SOURCE_KEY],
    }
    ability_damage_is_psychic_attack(context)
    return context
