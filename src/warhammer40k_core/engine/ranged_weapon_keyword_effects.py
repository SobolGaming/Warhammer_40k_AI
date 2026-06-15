from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.core.weapon_profiles import (
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
    weapon_keyword_from_token,
)
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

RANGED_WEAPON_KEYWORD_GRANT_EFFECT_KIND = "ranged_weapon_keyword_grant"
RANGED_WEAPON_KEYWORD_GRANT_KEY = "granted_weapon_keywords"


def ranged_weapon_keyword_grant_payload(
    *,
    granted_keywords: tuple[WeaponKeyword, ...],
    source_movement_request_id: str,
    source_movement_result_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": RANGED_WEAPON_KEYWORD_GRANT_EFFECT_KIND,
            RANGED_WEAPON_KEYWORD_GRANT_KEY: [
                keyword.value
                for keyword in _validate_weapon_keyword_tuple(
                    "granted_keywords",
                    granted_keywords,
                )
            ],
            "source_movement_request_id": _validate_identifier(
                "source_movement_request_id",
                source_movement_request_id,
            ),
            "source_movement_result_id": _validate_identifier(
                "source_movement_result_id",
                source_movement_result_id,
            ),
        }
    )


def weapon_profile_with_ranged_keyword_effects(
    profile: WeaponProfile,
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Ranged weapon keyword effects require a WeaponProfile.")
    if type(effects) is not tuple:
        raise GameLifecycleError("Ranged weapon keyword effects require an effect tuple.")
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    granted_keywords: set[WeaponKeyword] = set()
    source_ids: set[str] = set()
    for effect in effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError(
                "Ranged weapon keyword effects require PersistingEffect values."
            )
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != RANGED_WEAPON_KEYWORD_GRANT_EFFECT_KIND:
            continue
        raw_keywords = payload.get(RANGED_WEAPON_KEYWORD_GRANT_KEY)
        if not isinstance(raw_keywords, list):
            raise GameLifecycleError("Ranged weapon keyword grant payload is missing keywords.")
        granted_keywords.update(
            _validate_weapon_keyword_tuple(
                "ranged weapon keyword grant",
                tuple(cast(tuple[object, ...], tuple(raw_keywords))),
            )
        )
        source_ids.add(effect.source_rule_id)
    if not granted_keywords:
        return profile
    merged_keywords = tuple(
        sorted({*profile.keywords, *granted_keywords}, key=lambda keyword: keyword.value)
    )
    merged_source_ids = tuple(sorted({*profile.source_ids, *source_ids}))
    return replace(profile, keywords=merged_keywords, source_ids=merged_source_ids)


def _validate_weapon_keyword_tuple(
    field_name: str,
    values: object,
) -> tuple[WeaponKeyword, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    keywords: list[WeaponKeyword] = []
    seen: set[WeaponKeyword] = set()
    for raw_value in cast(tuple[object, ...], values):
        keyword = _weapon_keyword_from_value(field_name, raw_value)
        if keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords, key=lambda keyword: keyword.value))


def _weapon_keyword_from_value(field_name: str, value: object) -> WeaponKeyword:
    if type(value) is WeaponKeyword:
        return value
    if type(value) is str:
        try:
            return weapon_keyword_from_token(value)
        except WeaponProfileError as exc:
            raise GameLifecycleError(f"{field_name} contains an unsupported keyword.") from exc
    raise GameLifecycleError(f"{field_name} values must be WeaponKeyword values or strings.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped
