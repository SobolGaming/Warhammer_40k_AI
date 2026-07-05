from __future__ import annotations

from collections.abc import Iterable, Mapping

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import ArmyDefinition
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

_validate_identifier = IdentifierValidator(GameLifecycleError)


def payload_object(value: object, *, field_name: str = "payload") -> dict[str, JsonValue]:
    payload = validate_json_value(value)
    if not isinstance(payload, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return payload


def event_payload_object(
    record: EventRecord,
    *,
    field_name: str = "event payload",
) -> dict[str, JsonValue]:
    if type(record) is not EventRecord:
        raise GameLifecycleError(f"{field_name} requires EventRecord.")
    return payload_object(record.payload, field_name=field_name)


def payload_string(
    payload: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str | None = None,
) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        label = key if field_name is None else f"{field_name} {key}"
        raise GameLifecycleError(f"{label} must be a string.")
    return value


def payload_identifier(
    payload: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str | None = None,
) -> str:
    label = key if field_name is None else f"{field_name} {key}"
    return _validate_identifier(label, payload.get(key))


def payload_int(
    payload: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str | None = None,
) -> int:
    value = payload.get(key)
    if type(value) is not int:
        label = key if field_name is None else f"{field_name} {key}"
        raise GameLifecycleError(f"{label} must be an integer.")
    return value


def payload_bool(
    payload: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str | None = None,
) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        label = key if field_name is None else f"{field_name} {key}"
        raise GameLifecycleError(f"{label} must be a bool.")
    return value


def payload_string_tuple(
    payload: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str | None = None,
) -> tuple[str, ...]:
    value = payload.get(key)
    label = key if field_name is None else f"{field_name} {key}"
    if not isinstance(value, list):
        raise GameLifecycleError(f"{label} must be a list.")
    values: list[str] = []
    for item in value:
        if type(item) is not str or not item.strip():
            raise GameLifecycleError(f"{label} must contain non-empty strings.")
        values.append(item)
    return tuple(values)


def payload_identifier_tuple(
    payload: Mapping[str, JsonValue],
    key: str,
    *,
    field_name: str | None = None,
) -> tuple[str, ...]:
    value = payload.get(key)
    label = key if field_name is None else f"{field_name} {key}"
    if not isinstance(value, list):
        raise GameLifecycleError(f"{label} must be a list.")
    return tuple(_validate_identifier(f"{label} value", item) for item in value)


def canonical_keyword(value: str) -> str:
    keyword = _validate_identifier("keyword", value)
    normalized = keyword.replace("\u2019", "").replace("'", "")
    return " ".join(normalized.replace("_", " ").replace("-", " ").upper().split())


def army_for_player(
    armies: Iterable[ArmyDefinition],
    *,
    player_id: str,
    context: str = "Faction content",
) -> ArmyDefinition:
    requested_player_id = _validate_identifier("player_id", player_id)
    for army in armies:
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError(f"{context} army lookup requires ArmyDefinition values.")
        if army.player_id == requested_player_id:
            return army
    raise GameLifecycleError(f"{context} army not found for player {requested_player_id}.")
