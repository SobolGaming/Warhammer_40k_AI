from __future__ import annotations

from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

MOVEMENT_KEYWORD_GRANT_EFFECT_KIND = "movement_keyword_grant"
MOVEMENT_KEYWORD_GRANT_KEY = "granted_keywords"


def movement_keyword_grant_payload(
    *,
    granted_keywords: tuple[str, ...],
    source_decision_request_id: str,
    source_decision_result_id: str,
    stratagem_use_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "effect_kind": MOVEMENT_KEYWORD_GRANT_EFFECT_KIND,
            MOVEMENT_KEYWORD_GRANT_KEY: list(
                _validate_keyword_tuple("granted_keywords", granted_keywords)
            ),
            "source_decision_request_id": _validate_identifier(
                "source_decision_request_id",
                source_decision_request_id,
            ),
            "source_decision_result_id": _validate_identifier(
                "source_decision_result_id",
                source_decision_result_id,
            ),
            "stratagem_use_id": _validate_identifier("stratagem_use_id", stratagem_use_id),
        }
    )


def movement_keywords_granted_by_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> tuple[str, ...]:
    if type(effects) is not tuple:
        raise GameLifecycleError("Movement keyword grants require a tuple of effects.")
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    keywords: set[str] = set()
    for effect in effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Movement keyword grants require PersistingEffect values.")
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != MOVEMENT_KEYWORD_GRANT_EFFECT_KIND:
            continue
        raw_keywords = payload.get(MOVEMENT_KEYWORD_GRANT_KEY)
        if not isinstance(raw_keywords, list):
            raise GameLifecycleError("Movement keyword grant payload is missing keywords.")
        keywords.update(
            _validate_keyword_tuple(
                "movement keyword grant",
                tuple(cast(tuple[object, ...], tuple(raw_keywords))),
            )
        )
    return tuple(sorted(keywords))


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for raw_value in cast(tuple[object, ...], values):
        keyword = _validate_identifier(field_name, raw_value).strip().upper()
        if keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


_validate_identifier = IdentifierValidator(GameLifecycleError)
