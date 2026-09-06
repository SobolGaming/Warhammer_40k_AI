from __future__ import annotations

from typing import cast

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, battle_phase_kind_from_token
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleIR


def validate_rule_ir(value: object) -> RuleIR:
    if type(value) is not RuleIR:
        raise GameLifecycleError("Rule execution requires a compiled RuleIR.")
    return value


def validate_effect_kind_tuple(
    field_name: str,
    values: object,
) -> tuple[RuleEffectKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[RuleEffectKind] = []
    seen: set[RuleEffectKind] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not RuleEffectKind:
            raise GameLifecycleError(f"{field_name} values must be RuleEffectKind.")
        if value in seen:
            raise GameLifecycleError(f"{field_name} values must not be duplicated.")
        seen.add(value)
        validated.append(value)
    return tuple(sorted(validated, key=lambda kind: kind.value))


def validate_json_object_tuple(
    field_name: str,
    values: object,
) -> tuple[dict[str, JsonValue], ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[dict[str, JsonValue]] = []
    for value in cast(tuple[object, ...], values):
        validated.append(json_object(value))
    return tuple(validated)


def json_object(value: object) -> dict[str, JsonValue]:
    validated = validate_json_value(value)
    if not isinstance(validated, dict):
        raise GameLifecycleError("Rule execution payload must be a JSON object.")
    return validated


validate_identifier = IdentifierValidator(GameLifecycleError)


def validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return validate_identifier(field_name, value)


def validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate values.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < min_length:
        raise GameLifecycleError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(identifiers))
    return tuple(identifiers)


def validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be positive.")
    return value


def validate_optional_phase(
    field_name: str,
    value: object | None,
) -> BattlePhaseKind | None:
    if value is None:
        return None
    try:
        return battle_phase_kind_from_token(value)
    except ValueError as exc:
        raise GameLifecycleError(f"{field_name} must be a BattlePhaseKind.") from exc
