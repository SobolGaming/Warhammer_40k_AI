from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


def movement_bonus_inches_from_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> int:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    total = 0
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement bonus effect payload must be an object.")
        raw_bonus = payload.get("movement_bonus_inches")
        if raw_bonus is None:
            continue
        if type(raw_bonus) is not int:
            raise GameLifecycleError("movement_bonus_inches effect value must be an int.")
        if raw_bonus < 0:
            raise GameLifecycleError("movement_bonus_inches effect value must not be negative.")
        total += raw_bonus
    return total


def fire_overwatch_forbidden_by_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> bool:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Fire Overwatch effect payload must be an object.")
        raw_forbidden = payload.get("fire_overwatch_forbidden")
        if raw_forbidden is None:
            continue
        if type(raw_forbidden) is not bool:
            raise GameLifecycleError("fire_overwatch_forbidden effect value must be a bool.")
        if raw_forbidden:
            return True
    return False


def charge_transit_through_non_vehicle_monster_models_allowed(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> bool:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement transit effect payload must be an object.")
        if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            continue
        rule_effect = payload.get("effect")
        if not isinstance(rule_effect, dict):
            raise GameLifecycleError("Generic movement transit payload requires effect object.")
        if rule_effect.get("kind") != "movement_transit_permission":
            continue
        parameters = _parameter_mapping(rule_effect)
        if parameters.get("permission") != "move_through_models":
            continue
        if "charge" not in _string_sequence_parameter(parameters, "movement_modes"):
            continue
        if parameters.get("model_allegiance") not in {"any", "enemy"}:
            continue
        excluded_keywords = set(
            _string_sequence_parameter(parameters, "excluded_model_keyword_any")
        )
        if {"MONSTER", "VEHICLE"}.issubset(excluded_keywords):
            return True
    return False


def embark_transport_forbidden_effect_source_ids(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> tuple[str, ...]:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    source_ids: list[str] = []
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Embark restriction effect payload must be an object.")
        raw_forbidden = payload.get("embark_transport_forbidden")
        if raw_forbidden is None:
            continue
        if type(raw_forbidden) is not bool:
            raise GameLifecycleError("embark_transport_forbidden effect value must be a bool.")
        if raw_forbidden:
            source_ids.append(effect.source_rule_id)
    return tuple(sorted(source_ids))


def embark_transport_forbidden_by_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> bool:
    return bool(
        embark_transport_forbidden_effect_source_ids(
            effects,
            owner_player_id=owner_player_id,
        )
    )


def _validated_effects(effects: tuple[PersistingEffect, ...]) -> tuple[PersistingEffect, ...]:
    if type(effects) is not tuple:
        raise GameLifecycleError("Rule effect helpers require a tuple of effects.")
    for effect in effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Rule effect helpers require PersistingEffect values.")
    return effects


def _parameter_mapping(rule_effect: dict[str, JsonValue]) -> dict[str, JsonValue]:
    raw_parameters = rule_effect.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError("Generic movement transit effect parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic movement transit effect parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic movement transit effect parameter key is invalid.")
        parameters[_validate_identifier("generic effect parameter key", key)] = validate_json_value(
            raw_parameter.get("value")
        )
    return parameters


def _string_sequence_parameter(parameters: dict[str, JsonValue], key: str) -> tuple[str, ...]:
    value = parameters.get(key)
    if not isinstance(value, list):
        raise GameLifecycleError(f"Generic movement transit effect {key} must be a list.")
    values: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(
                f"Generic movement transit effect {key} entries must be strings."
            )
        values.append(_validate_identifier(f"generic effect {key} entry", item))
    return tuple(values)


_validate_identifier = IdentifierValidator(GameLifecycleError)
