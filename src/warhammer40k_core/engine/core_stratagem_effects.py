from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

GO_TO_GROUND_EFFECT_KIND = "core_stratagem:go_to_ground"
SMOKESCREEN_EFFECT_KIND = "core_stratagem:smokescreen"
FIRE_OVERWATCH_EFFECT_KIND = "core_stratagem:fire_overwatch"

GO_TO_GROUND_INVULNERABLE_SAVE = 6
SMOKESCREEN_HIT_ROLL_MODIFIER = -1


def effect_kind(effect: PersistingEffect) -> str:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Core stratagem effect lookup requires PersistingEffect.")
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Core stratagem effect payload must be an object.")
    raw_kind = payload.get("effect_kind")
    if type(raw_kind) is not str:
        raise GameLifecycleError("Core stratagem effect payload requires effect_kind.")
    return raw_kind


def effect_payload_bool(effect: PersistingEffect, key: str) -> bool:
    payload = _effect_payload(effect)
    value = payload.get(key, False)
    if type(value) is not bool:
        raise GameLifecycleError(f"Core stratagem effect payload {key} must be a bool.")
    return value


def effect_payload_int(effect: PersistingEffect, key: str, default: int) -> int:
    payload = _effect_payload(effect)
    value = payload.get(key, default)
    if type(value) is not int:
        raise GameLifecycleError(f"Core stratagem effect payload {key} must be an int.")
    return value


def unit_effects_grant_benefit_of_cover(effects: tuple[PersistingEffect, ...]) -> bool:
    _validate_effect_tuple(effects)
    return any(
        effect_kind(effect) in {GO_TO_GROUND_EFFECT_KIND, SMOKESCREEN_EFFECT_KIND}
        and effect_payload_bool(effect, "benefit_of_cover")
        for effect in effects
    )


def unit_effects_deny_benefit_of_cover(effects: tuple[PersistingEffect, ...]) -> bool:
    _validate_effect_tuple(effects)
    return any(effect_payload_bool(effect, "benefit_of_cover_denied") for effect in effects)


def unit_effect_hit_roll_modifier(effects: tuple[PersistingEffect, ...]) -> int:
    _validate_effect_tuple(effects)
    modifier = 0
    for effect in effects:
        if effect_kind(effect) != SMOKESCREEN_EFFECT_KIND:
            continue
        modifier += effect_payload_int(
            effect,
            "hit_roll_modifier",
            SMOKESCREEN_HIT_ROLL_MODIFIER,
        )
    return modifier


def unit_effect_invulnerable_save(effects: tuple[PersistingEffect, ...]) -> int | None:
    _validate_effect_tuple(effects)
    saves: list[int] = []
    for effect in effects:
        if effect_kind(effect) != GO_TO_GROUND_EFFECT_KIND:
            continue
        saves.append(
            effect_payload_int(
                effect,
                "invulnerable_save",
                GO_TO_GROUND_INVULNERABLE_SAVE,
            )
        )
    if not saves:
        return None
    return min(saves)


def _effect_payload(effect: PersistingEffect) -> dict[str, JsonValue]:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Core stratagem effect lookup requires PersistingEffect.")
    payload = effect.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Core stratagem effect payload must be an object.")
    return payload


def _validate_effect_tuple(effects: object) -> tuple[PersistingEffect, ...]:
    if type(effects) is not tuple:
        raise GameLifecycleError("Core stratagem effects must be a tuple.")
    effect_tuple = cast(tuple[object, ...], effects)
    for effect in effect_tuple:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Core stratagem effects must contain PersistingEffect.")
    return cast(tuple[PersistingEffect, ...], effect_tuple)
