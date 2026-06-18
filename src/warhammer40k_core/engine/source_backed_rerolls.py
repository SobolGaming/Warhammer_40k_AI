from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import RerollPermission, RerollPermissionPayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError

SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND = "source_backed_reroll_permission"


def source_backed_reroll_permission_effect_payload(
    *,
    target_unit_instance_ids: tuple[str, ...],
    permission: RerollPermission,
    source_payload: JsonValue,
) -> JsonValue:
    if type(permission) is not RerollPermission:
        raise GameLifecycleError("Source-backed reroll effect requires RerollPermission.")
    return validate_json_value(
        {
            "effect_kind": SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND,
            "target_unit_instance_ids": list(
                _validate_identifier_tuple("target_unit_instance_ids", target_unit_instance_ids)
            ),
            "permission": validate_json_value(permission.to_payload()),
            "source_payload": validate_json_value(source_payload),
        }
    )


def source_backed_reroll_permission_for_unit(
    *,
    state: object,
    player_id: str,
    unit_instance_id: str,
    roll_type: str,
    timing_window: str,
) -> RerollPermission | None:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Source-backed reroll lookup requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    requested_roll_type = _validate_identifier("roll_type", roll_type)
    requested_timing_window = _validate_identifier("timing_window", timing_window)
    permissions: list[RerollPermission] = []
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        if effect.owner_player_id != requested_player_id:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") != SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND:
            continue
        permission = _reroll_permission_from_effect_payload(payload)
        if permission.owning_player_id != requested_player_id:
            raise GameLifecycleError("Source-backed reroll owner drift.")
        if permission.eligible_roll_type != requested_roll_type:
            continue
        if permission.timing_window != requested_timing_window:
            continue
        permissions.append(permission)
    if len(permissions) > 1:
        raise GameLifecycleError("Multiple source-backed reroll permissions are available.")
    return permissions[0] if permissions else None


def source_payload_from_reroll_effect_payload(effect_payload: JsonValue) -> dict[str, JsonValue]:
    payload = _payload_object(effect_payload)
    if payload.get("effect_kind") != SOURCE_BACKED_REROLL_PERMISSION_EFFECT_KIND:
        raise GameLifecycleError("Source-backed reroll effect_kind drift.")
    source_payload = payload.get("source_payload")
    if not isinstance(source_payload, dict):
        raise GameLifecycleError("Source-backed reroll source_payload must be an object.")
    return source_payload


def _reroll_permission_from_effect_payload(
    payload: dict[str, JsonValue],
) -> RerollPermission:
    permission_payload = payload.get("permission")
    if not isinstance(permission_payload, dict):
        raise GameLifecycleError("Source-backed reroll permission must be an object.")
    return RerollPermission.from_payload(cast(RerollPermissionPayload, permission_payload))


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Source-backed reroll payload must be an object.")
    return payload


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Source-backed reroll {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Source-backed reroll {field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Source-backed reroll {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for raw_value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(field_name, raw_value)
        if identifier in seen:
            raise GameLifecycleError(f"Source-backed reroll {field_name} must be unique.")
        seen.add(identifier)
        identifiers.append(identifier)
    if not identifiers:
        raise GameLifecycleError(f"Source-backed reroll {field_name} must not be empty.")
    return tuple(identifiers)
