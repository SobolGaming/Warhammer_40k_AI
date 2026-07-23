from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        DamageApplicationPayload,
        FeelNoPainResolutionPayload,
    )

MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND = "mortal_wound"


class MortalWoundFeelNoPainContextPayload(TypedDict):
    context_kind: str
    application_id: str
    source_rule_id: str
    source_context: JsonValue
    target_unit_instance_id: str
    defender_player_id: str
    model_instance_id: str
    mortal_wounds: int
    remaining_mortal_wounds: int
    spill_over: bool
    applications: list[DamageApplicationPayload]
    feel_no_pain_resolutions: list[FeelNoPainResolutionPayload]
    ignored_mortal_wounds: int
    remaining_mortal_wounds_lost: int
    priority_model_ids: list[str]


_validate_identifier = IdentifierValidator(GameLifecycleError)


def parse_mortal_wound_feel_no_pain_context(
    payload: JsonValue,
) -> MortalWoundFeelNoPainContextPayload:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Mortal wound Feel No Pain context must be an object.")
    if payload.get("context_kind") != MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND:
        raise GameLifecycleError("Mortal wound Feel No Pain context kind is invalid.")
    applications = _list(payload, "applications")
    resolutions = _list(payload, "feel_no_pain_resolutions")
    priority_model_ids = tuple(_string_list(payload, "priority_model_ids"))
    return {
        "context_kind": MORTAL_WOUND_FEEL_NO_PAIN_CONTEXT_KIND,
        "application_id": _string(payload, "application_id"),
        "source_rule_id": _string(payload, "source_rule_id"),
        "source_context": validate_json_value(payload.get("source_context")),
        "target_unit_instance_id": _string(payload, "target_unit_instance_id"),
        "defender_player_id": _string(payload, "defender_player_id"),
        "model_instance_id": _string(payload, "model_instance_id"),
        "mortal_wounds": _int(payload, "mortal_wounds", positive=True),
        "remaining_mortal_wounds": _int(payload, "remaining_mortal_wounds"),
        "spill_over": _bool(payload, "spill_over"),
        "applications": cast(list["DamageApplicationPayload"], applications),
        "feel_no_pain_resolutions": cast(list["FeelNoPainResolutionPayload"], resolutions),
        "ignored_mortal_wounds": _int(payload, "ignored_mortal_wounds"),
        "remaining_mortal_wounds_lost": _int(payload, "remaining_mortal_wounds_lost"),
        "priority_model_ids": list(_validate_identifiers(priority_model_ids)),
    }


def _string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Mortal wound context {key} must be a string.")
    return value


def _int(payload: dict[str, JsonValue], key: str, *, positive: bool = False) -> int:
    value = payload.get(key)
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise GameLifecycleError(f"Mortal wound context {key} must be {qualifier}.")
    return value


def _bool(payload: dict[str, JsonValue], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise GameLifecycleError(f"Mortal wound context {key} must be a bool.")
    return value


def _list(payload: dict[str, JsonValue], key: str) -> list[JsonValue]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Mortal wound context {key} must be a list.")
    return value


def _string_list(payload: dict[str, JsonValue], key: str) -> list[str]:
    values = _list(payload, key)
    if any(type(value) is not str for value in values):
        raise GameLifecycleError(f"Mortal wound context {key} must contain strings.")
    return cast(list[str], values)


def _validate_identifiers(values: tuple[str, ...]) -> tuple[str, ...]:
    validated = tuple(_validate_identifier("priority_model_ids value", value) for value in values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError("priority_model_ids must not contain duplicates.")
    return tuple(sorted(validated))
