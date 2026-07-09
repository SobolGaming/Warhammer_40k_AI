from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.core_stratagem_effects import SMOKESCREEN_EFFECT_KIND
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)
from warhammer40k_core.engine.target_restriction_hooks import (
    ShootingTargetRestrictionContext,
    ShootingTargetRestrictionHookBinding,
    TargetRestriction,
)
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleEffectSpecPayload,
    RuleIRError,
    parameter_payload,
)

GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID = (
    "generic_rule_ir:persisted-shooting-target-range-restriction"
)
GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID = (
    "generic_rule_ir:persisted-shooting-target-range-restriction"
)
GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE = (
    "generic_persisted_shooting_target_range"
)


@dataclass(frozen=True, slots=True)
class _TargetRangeRestrictionEffect:
    effect: PersistingEffect
    max_range_inches: float
    payload: dict[str, JsonValue]


def shooting_target_restriction_hook_bindings() -> tuple[ShootingTargetRestrictionHookBinding, ...]:
    return (
        ShootingTargetRestrictionHookBinding(
            hook_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
            source_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID,
            handler=generic_persisted_shooting_target_range_restriction,
        ),
    )


def generic_persisted_shooting_target_range_restriction(
    context: ShootingTargetRestrictionContext,
) -> TargetRestriction | None:
    if type(context) is not ShootingTargetRestrictionContext:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires a shooting target "
            "context."
        )
    effects = _target_range_restriction_effects(context)
    if not effects:
        return None
    for effect_context in effects:
        if target_within_shooting_selection_range(
            scenario=_battlefield_scenario(context.state),
            attacking_unit_instance_id=context.attacking_unit_instance_id,
            attacker_model_instance_id=context.attacker_model_instance_id,
            target_unit_instance_id=context.target_unit_instance_id,
            max_range_inches=effect_context.max_range_inches,
        ):
            continue
        return TargetRestriction(
            hook_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_HOOK_ID,
            source_id=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_SOURCE_ID,
            violation_code=GENERIC_PERSISTED_SHOOTING_TARGET_RANGE_RESTRICTION_VIOLATION_CODE,
            message=(
                "Target can only be selected by attacks from models within "
                f'{_format_inches(effect_context.max_range_inches)}".'
            ),
            replay_payload=_restriction_replay_payload(
                effect_context=effect_context,
                attacker_model_instance_id=context.attacker_model_instance_id,
                attacking_unit_instance_id=context.attacking_unit_instance_id,
                target_unit_instance_id=context.target_unit_instance_id,
            ),
        )
    return None


def _target_range_restriction_effects(
    context: ShootingTargetRestrictionContext,
) -> tuple[_TargetRangeRestrictionEffect, ...]:
    effects: list[_TargetRangeRestrictionEffect] = []
    for effect in context.state.persisting_effects_for_unit(context.target_unit_instance_id):
        payload_value = effect.effect_payload
        if not isinstance(payload_value, dict):
            continue
        payload = payload_value
        max_range_inches = _targeting_max_range_inches_or_none(payload)
        if max_range_inches is None:
            continue
        effects.append(
            _TargetRangeRestrictionEffect(
                effect=effect,
                max_range_inches=max_range_inches,
                payload=payload,
            )
        )
    return tuple(sorted(effects, key=lambda effect_context: effect_context.effect.effect_id))


def _targeting_max_range_inches_or_none(payload: dict[str, JsonValue]) -> float | None:
    if "targeting_max_range_inches" in payload:
        if payload.get("effect_kind") != SMOKESCREEN_EFFECT_KIND:
            raise GameLifecycleError(
                "Generic persisted shooting target range restriction requires smokescreen "
                "effect_kind for top-level range payloads."
            )
        return _targeting_max_range_value(payload["targeting_max_range_inches"])
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    return _generic_rule_targeting_max_range_inches_or_none(payload)


def _generic_rule_targeting_max_range_inches_or_none(
    payload: dict[str, JsonValue],
) -> float | None:
    effect = _generic_rule_effect(payload)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return None
    parameters = parameter_payload(effect.parameters)
    if parameters.get("status") != "shooting_target_range_restriction":
        return None
    value = parameters.get("targeting_max_range_inches")
    if value is None:
        return None
    return _targeting_max_range_value(value)


def _generic_rule_effect(payload: dict[str, JsonValue]) -> RuleEffectSpec:
    effect_payload = payload.get("effect")
    if not isinstance(effect_payload, dict):
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires generic effect payload."
        )
    try:
        return RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, effect_payload))
    except RuleIRError as exc:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction effect payload is invalid."
        ) from exc


def _targeting_max_range_value(value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction max range must be numeric."
        )
    max_range_inches = float(value)
    if max_range_inches <= 0.0:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction max range must be positive."
        )
    return max_range_inches


def _battlefield_scenario(state: object) -> BattlefieldScenario:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires GameState."
        )
    if state.battlefield_state is None:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction requires battlefield state."
        )
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _restriction_replay_payload(
    *,
    effect_context: _TargetRangeRestrictionEffect,
    attacker_model_instance_id: str | None,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
) -> JsonValue:
    payload = effect_context.payload
    replay_payload: dict[str, JsonValue] = {
        "restriction_kind": "persisted_shooting_target_range",
        "persisting_effect_id": effect_context.effect.effect_id,
        "persisting_effect_source_rule_id": effect_context.effect.source_rule_id,
        "persisting_effect_kind": _payload_string(payload, "effect_kind"),
        "source_effect_kind": _source_effect_kind(payload),
        "stratagem_id": _optional_payload_string(payload, "stratagem_id"),
        "stratagem_use_id": _optional_payload_string(payload, "stratagem_use_id"),
        "attacker_model_instance_id": attacker_model_instance_id,
        "attacking_unit_instance_id": attacking_unit_instance_id,
        "target_unit_instance_id": target_unit_instance_id,
        "max_range_inches": effect_context.max_range_inches,
    }
    if payload.get("effect_kind") == GENERIC_RULE_EFFECT_KIND:
        replay_payload["generic_rule_source_id"] = _optional_payload_string(payload, "source_id")
        replay_payload["generic_rule_clause_id"] = _optional_payload_string(payload, "clause_id")
        replay_payload["generic_rule_effect"] = validate_json_value(payload.get("effect"))
    return validate_json_value(replay_payload)


def _source_effect_kind(payload: dict[str, JsonValue]) -> str | None:
    source_effect_kind = _optional_payload_string(payload, "source_effect_kind")
    if source_effect_kind is not None:
        return source_effect_kind
    if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    parameters = parameter_payload(_generic_rule_effect(payload).parameters)
    value = parameters.get("source_effect_kind")
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(
            "Generic persisted shooting target range restriction source_effect_kind must be a "
            "string."
        )
    return value


def _payload_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(
            f"Generic persisted shooting target range restriction payload {key} must be a string."
        )
    return value


def _optional_payload_string(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(
            f"Generic persisted shooting target range restriction payload {key} must be a string."
        )
    return value


def _format_inches(value: float) -> str:
    return f"{value:g}"
