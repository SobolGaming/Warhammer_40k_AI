from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


@dataclass(frozen=True, slots=True)
class MovementModelTransitPermission:
    movement_modes: tuple[str, ...]
    model_allegiance: str
    excluded_model_keyword_any: tuple[str, ...] = ()
    enemy_engagement_range_transit: bool = False
    enemy_engagement_range_end_allowed: bool = False
    desperate_escape_tests_auto_passed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "movement_modes",
            _string_tuple("MovementModelTransitPermission movement_modes", self.movement_modes),
        )
        model_allegiance = _validate_identifier("model_allegiance", self.model_allegiance)
        if model_allegiance not in {"any", "enemy", "friendly"}:
            raise GameLifecycleError("Movement model transit allegiance is unsupported.")
        object.__setattr__(self, "model_allegiance", model_allegiance)
        object.__setattr__(
            self,
            "excluded_model_keyword_any",
            _validate_keyword_tuple(self.excluded_model_keyword_any),
        )
        for field_name, value in (
            ("enemy_engagement_range_transit", self.enemy_engagement_range_transit),
            ("enemy_engagement_range_end_allowed", self.enemy_engagement_range_end_allowed),
            ("desperate_escape_tests_auto_passed", self.desperate_escape_tests_auto_passed),
        ):
            _validate_bool(f"MovementModelTransitPermission {field_name}", value)


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
    for permission in movement_model_transit_permissions_from_effects(
        effects,
        owner_player_id=owner_player_id,
        movement_mode="charge",
        model_allegiance="enemy",
    ):
        if {"MONSTER", "VEHICLE"}.issubset(set(permission.excluded_model_keyword_any)):
            return True
    return False


def movement_model_transit_permissions_from_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
    movement_mode: str,
    model_allegiance: str,
) -> tuple[MovementModelTransitPermission, ...]:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    requested_mode = _validate_identifier("movement_mode", movement_mode)
    requested_allegiance = _validate_identifier("model_allegiance", model_allegiance)
    if requested_allegiance not in {"any", "enemy", "friendly"}:
        raise GameLifecycleError("Movement model transit requested allegiance is unsupported.")
    permissions: list[MovementModelTransitPermission] = []
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
        movement_modes = _string_sequence_parameter(parameters, "movement_modes")
        if requested_mode not in movement_modes:
            continue
        effect_allegiance = parameters.get("model_allegiance")
        if effect_allegiance not in {"any", "enemy", "friendly"}:
            continue
        if (
            requested_allegiance != "any"
            and effect_allegiance != "any"
            and effect_allegiance != requested_allegiance
        ):
            continue
        permissions.append(
            MovementModelTransitPermission(
                movement_modes=movement_modes,
                model_allegiance=effect_allegiance,
                excluded_model_keyword_any=_string_sequence_parameter(
                    parameters,
                    "excluded_model_keyword_any",
                    default=(),
                ),
                enemy_engagement_range_transit=_bool_parameter(
                    parameters,
                    "enemy_engagement_range_transit",
                    default=False,
                ),
                enemy_engagement_range_end_allowed=_bool_parameter(
                    parameters,
                    "enemy_engagement_range_end_allowed",
                    default=False,
                ),
                desperate_escape_tests_auto_passed=_bool_parameter(
                    parameters,
                    "desperate_escape_tests_auto_passed",
                    default=False,
                ),
            )
        )
    return tuple(
        sorted(
            permissions,
            key=lambda permission: (
                permission.model_allegiance,
                permission.movement_modes,
                permission.excluded_model_keyword_any,
            ),
        )
    )


def movement_transit_through_terrain_features_allowed(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
    movement_mode: str,
    unit_keywords: tuple[str, ...],
) -> bool:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    requested_mode = _validate_identifier("movement_mode", movement_mode)
    keywords = _validate_keyword_tuple(unit_keywords)
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement terrain-transit effect payload must be an object.")
        if payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
            continue
        rule_effect = payload.get("effect")
        if not isinstance(rule_effect, dict):
            raise GameLifecycleError("Generic terrain-transit payload requires effect object.")
        if rule_effect.get("kind") != "movement_transit_permission":
            continue
        parameters = _parameter_mapping(rule_effect)
        if parameters.get("permission") not in {
            "move_horizontally_through_terrain_features",
            "move_through_terrain_features",
        }:
            continue
        if requested_mode not in _string_sequence_parameter(parameters, "movement_modes"):
            continue
        terrain_features = parameters.get("terrain_features")
        if terrain_features is not True:
            continue
        required_keyword = parameters.get("required_keyword")
        if required_keyword is not None:
            if type(required_keyword) is not str:
                raise GameLifecycleError(
                    "Generic terrain-transit required_keyword must be a string."
                )
            if required_keyword not in keywords:
                continue
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


def _string_sequence_parameter(
    parameters: dict[str, JsonValue],
    key: str,
    *,
    default: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    value = parameters.get(key)
    if value is None and default is not None:
        return default
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


def _string_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    tokens: list[str] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not str:
            raise GameLifecycleError(f"{field_name} entries must be strings.")
        tokens.append(_validate_identifier(field_name, value))
    if not tokens:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(tokens)


def _bool_parameter(
    parameters: dict[str, JsonValue],
    key: str,
    *,
    default: bool,
) -> bool:
    value = parameters.get(key, default)
    if type(value) is not bool:
        raise GameLifecycleError(f"Generic movement transit effect {key} must be a bool.")
    return value


def _validate_keyword_tuple(values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Rule effect keyword helpers require a tuple of keywords.")
    raw_values = cast(tuple[object, ...], values)
    keywords: list[str] = []
    for value in raw_values:
        if type(value) is not str:
            raise GameLifecycleError("Rule effect keyword helper entries must be strings.")
        keywords.append(_validate_identifier("keyword", value))
    return tuple(keywords)


def _validate_bool(field_name: str, value: object) -> None:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")


_validate_identifier = IdentifierValidator(GameLifecycleError)
