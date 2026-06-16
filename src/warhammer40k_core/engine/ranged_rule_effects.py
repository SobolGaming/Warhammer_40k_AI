from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

DETECTION_RANGE_BONUS_EFFECT_KIND = "detection_range_bonus"
RANGED_ATTACKS_KEEP_HIDDEN_EFFECT_KIND = "ranged_attacks_keep_hidden"
CHARACTER_TARGET_AP_BONUS_EFFECT_KIND = "character_target_ap_bonus"


def detection_range_bonus_payload(
    *,
    bonus_inches: int,
    source_rule_kind: str,
    source_unit_instance_id: str | None = None,
    source_decision_request_id: str | None = None,
    source_decision_result_id: str | None = None,
    stratagem_use_id: str | None = None,
    expires_when_source_unit_has_shot: bool = False,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": DETECTION_RANGE_BONUS_EFFECT_KIND,
            "bonus_inches": _validate_positive_int("bonus_inches", bonus_inches),
            "source_rule_kind": _validate_identifier("source_rule_kind", source_rule_kind),
            "source_unit_instance_id": _validate_optional_identifier(
                "source_unit_instance_id",
                source_unit_instance_id,
            ),
            "source_decision_request_id": _validate_optional_identifier(
                "source_decision_request_id",
                source_decision_request_id,
            ),
            "source_decision_result_id": _validate_optional_identifier(
                "source_decision_result_id",
                source_decision_result_id,
            ),
            "stratagem_use_id": _validate_optional_identifier(
                "stratagem_use_id",
                stratagem_use_id,
            ),
            "expires_when_source_unit_has_shot": _validate_bool(
                "expires_when_source_unit_has_shot",
                expires_when_source_unit_has_shot,
            ),
        }
    )


def ranged_attacks_keep_hidden_payload(
    *,
    enhancement_id: str,
    assignment_source_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": RANGED_ATTACKS_KEEP_HIDDEN_EFFECT_KIND,
            "enhancement_id": _validate_identifier("enhancement_id", enhancement_id),
            "assignment_source_id": _validate_identifier(
                "assignment_source_id",
                assignment_source_id,
            ),
        }
    )


def character_target_ap_bonus_payload(
    *,
    enhancement_id: str,
    assignment_source_id: str,
    ap_bonus: int,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": CHARACTER_TARGET_AP_BONUS_EFFECT_KIND,
            "enhancement_id": _validate_identifier("enhancement_id", enhancement_id),
            "assignment_source_id": _validate_identifier(
                "assignment_source_id",
                assignment_source_id,
            ),
            "ap_bonus": _validate_positive_int("ap_bonus", ap_bonus),
        }
    )


def detection_range_bonus_inches_for_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    source_unit_has_shot: bool = False,
) -> int:
    if type(effects) is not tuple:
        raise GameLifecycleError("Detection range effect lookup requires an effect tuple.")
    bonus = 0
    for effect in effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Detection range effect lookup requires PersistingEffect.")
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != DETECTION_RANGE_BONUS_EFFECT_KIND:
            continue
        if payload.get("expires_when_source_unit_has_shot") is True and source_unit_has_shot:
            continue
        raw_bonus = payload.get("bonus_inches")
        if type(raw_bonus) is not int:
            raise GameLifecycleError("Detection range bonus payload requires bonus_inches.")
        bonus += _validate_positive_int("bonus_inches", raw_bonus)
    return bonus


def weapon_profile_with_character_target_ap_effects(
    profile: WeaponProfile,
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
    target_keywords: tuple[str, ...],
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Character-target AP effects require a WeaponProfile.")
    if type(effects) is not tuple:
        raise GameLifecycleError("Character-target AP effects require an effect tuple.")
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    if "CHARACTER" not in {_canonical_keyword(keyword) for keyword in target_keywords}:
        return profile
    total_bonus = 0
    source_ids: set[str] = set()
    for effect in effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Character-target AP effects require PersistingEffect values.")
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != CHARACTER_TARGET_AP_BONUS_EFFECT_KIND:
            continue
        raw_bonus = payload.get("ap_bonus")
        if type(raw_bonus) is not int:
            raise GameLifecycleError("Character-target AP payload requires ap_bonus.")
        total_bonus += _validate_positive_int("ap_bonus", raw_bonus)
        source_ids.add(effect.source_rule_id)
    if total_bonus == 0:
        return profile
    modified_ap = profile.armor_penetration.final - total_bonus
    return replace(
        profile,
        armor_penetration=CharacteristicValue.from_raw(
            Characteristic.ARMOR_PENETRATION,
            modified_ap,
        ),
        source_ids=tuple(sorted({*profile.source_ids, *source_ids})),
    )


def _canonical_keyword(keyword: str) -> str:
    return _validate_identifier("keyword", keyword).replace("_", " ").replace("-", " ").upper()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
