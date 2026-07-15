from __future__ import annotations

from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_target_resolution import unit_has_required_keywords
from warhammer40k_core.engine.rules_unit_geometry import geometry_models_for_rules_unit
from warhammer40k_core.engine.rules_units import (
    rules_unit_view_by_id,
    rules_unit_views_from_armies,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.rules.rule_ir import RuleConditionKind, RuleTargetKind

TARGET_ALLEGIANCE_ENEMY = "enemy"
TARGET_ALLEGIANCE_FRIENDLY = "friendly"
TARGET_CONSTRAINT_NOT_BELOW_HALF_STRENGTH = "target_not_below_half_strength"


def generic_rule_parameters_from_effect_payload(
    effect_payload: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return generic_rule_parameters_from_payload_object(effect_payload, object_label="effect")


def generic_rule_parameters_from_payload_object(
    payload: dict[str, JsonValue],
    *,
    object_label: str,
) -> dict[str, JsonValue]:
    raw_parameters = payload.get("parameters")
    if not isinstance(raw_parameters, list):
        raise GameLifecycleError(f"Generic RuleIR {object_label} parameters must be a list.")
    parameters: dict[str, JsonValue] = {}
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            raise GameLifecycleError("Generic RuleIR parameter must be an object.")
        key = raw_parameter.get("key")
        if type(key) is not str:
            raise GameLifecycleError("Generic RuleIR parameter key must be a string.")
        parameter_key = _validate_identifier("parameter key", key)
        if parameter_key in parameters:
            raise GameLifecycleError("Generic RuleIR parameters must not duplicate keys.")
        if "value" not in raw_parameter:
            raise GameLifecycleError("Generic RuleIR parameter requires value.")
        parameters[parameter_key] = validate_json_value(raw_parameter["value"])
    return parameters


def generic_rule_conditions_from_payload(
    payload: dict[str, JsonValue],
) -> tuple[dict[str, JsonValue], ...]:
    raw_conditions = payload.get("conditions")
    if raw_conditions is None:
        return ()
    if not isinstance(raw_conditions, list):
        raise GameLifecycleError("Generic RuleIR conditions must be a list.")
    conditions: list[dict[str, JsonValue]] = []
    for raw_condition in raw_conditions:
        if not isinstance(raw_condition, dict):
            raise GameLifecycleError("Generic RuleIR condition must be an object.")
        kind = raw_condition.get("kind")
        if type(kind) is not str:
            raise GameLifecycleError("Generic RuleIR condition kind must be a string.")
        condition = validate_json_value(
            {
                "kind": _validate_identifier("condition kind", kind),
                "parameters": generic_rule_parameters_from_payload_object(
                    raw_condition,
                    object_label="condition",
                ),
            }
        )
        if not isinstance(condition, dict):
            raise GameLifecycleError("Generic RuleIR condition payload must be an object.")
        conditions.append(condition)
    return tuple(conditions)


def generic_rule_source_model_instance_id_from_payload(
    payload: dict[str, JsonValue],
) -> str | None:
    context_payload = payload.get("context")
    if context_payload is None:
        return None
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Generic RuleIR context payload must be an object.")
    source_model_id = context_payload.get("source_model_instance_id")
    if source_model_id is None:
        return None
    if type(source_model_id) is not str:
        raise GameLifecycleError("Generic RuleIR source_model_instance_id must be a string.")
    return _validate_identifier("source_model_instance_id", source_model_id)


def generic_rule_target_constraint_values(
    *,
    parameters: dict[str, JsonValue],
    conditions: tuple[dict[str, JsonValue], ...],
) -> tuple[str, ...]:
    values: list[str] = []
    parameter_value = parameters.get("target_constraint")
    if parameter_value is not None:
        if type(parameter_value) is not str:
            raise GameLifecycleError("Generic RuleIR target_constraint must be a string.")
        values.append(_validate_identifier("target_constraint", parameter_value))
    for condition_parameters in _target_constraint_condition_parameters(conditions):
        condition_value = condition_parameters.get("target_constraint")
        if condition_value is None:
            continue
        if type(condition_value) is not str:
            raise GameLifecycleError("Generic RuleIR target_constraint must be a string.")
        values.append(_validate_identifier("target_constraint", condition_value))
    return tuple(dict.fromkeys(values))


def generic_rule_target_allegiance_values(
    *,
    parameters: dict[str, JsonValue],
    conditions: tuple[dict[str, JsonValue], ...],
) -> tuple[str, ...]:
    values: list[str] = []
    parameter_value = parameters.get("target_allegiance")
    if parameter_value is not None:
        if type(parameter_value) is not str:
            raise GameLifecycleError("Generic RuleIR target_allegiance must be a string.")
        values.append(_validate_identifier("target_allegiance", parameter_value))
    for condition_parameters in _target_constraint_condition_parameters(conditions):
        condition_value = condition_parameters.get("target_allegiance")
        if condition_value is None:
            continue
        if type(condition_value) is not str:
            raise GameLifecycleError("Generic RuleIR target_allegiance must be a string.")
        values.append(_validate_identifier("target_allegiance", condition_value))
    return tuple(dict.fromkeys(values))


def generic_rule_source_model_applies(
    *,
    target_kind: RuleTargetKind | None,
    source_model_instance_id: str | None,
    attacker_model_instance_id: str | None,
    requires_source_model_instance_id: bool,
) -> bool:
    if target_kind is not RuleTargetKind.THIS_MODEL:
        return True
    if source_model_instance_id is None:
        if requires_source_model_instance_id:
            raise GameLifecycleError(
                "Generic RuleIR THIS_MODEL effect requires source_model_instance_id."
            )
        return True
    if attacker_model_instance_id is None:
        return False
    return source_model_instance_id == attacker_model_instance_id


def generic_rule_conditions_require_source_model_instance_id(
    conditions: tuple[dict[str, JsonValue], ...],
) -> bool:
    for condition_parameters in _target_constraint_condition_parameters(conditions):
        relationship = condition_parameters.get("relationship")
        if relationship == "this_model_makes_attack":
            return True
    return False


def generic_rule_target_allegiance_applies(
    *,
    state: object,
    allegiances: tuple[str, ...],
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
) -> bool:
    if not allegiances:
        return True
    if target_unit_instance_id is None:
        return False
    unique_allegiances = set(allegiances)
    if len(unique_allegiances) != 1:
        raise GameLifecycleError("Generic RuleIR target_allegiance constraints conflict.")
    allegiance = allegiances[0]
    attacker_owner = _unit_owner(state=state, unit_instance_id=attacking_unit_instance_id)
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_instance_id)
    if allegiance == TARGET_ALLEGIANCE_ENEMY:
        return attacker_owner != target_owner
    if allegiance == TARGET_ALLEGIANCE_FRIENDLY:
        return attacker_owner == target_owner
    raise GameLifecycleError("Unsupported generic RuleIR target_allegiance.")


def generic_rule_target_constraints_apply(
    *,
    state: object,
    constraints: tuple[str, ...],
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
    attack_strength: int | None,
    target_toughness: int | None,
) -> bool:
    for constraint in constraints:
        if constraint == "closest_eligible_target_within_18":
            if target_unit_instance_id is None:
                return False
            if not _target_is_closest_enemy_within_distance(
                state=state,
                attacking_unit_instance_id=attacking_unit_instance_id,
                target_unit_instance_id=target_unit_instance_id,
                distance_inches=18.0,
            ):
                return False
            continue
        if constraint == "attack_strength_greater_than_target_toughness":
            if attack_strength is None or target_toughness is None:
                return False
            if attack_strength <= target_toughness:
                return False
            continue
        if constraint == "eligible_unit_within_12":
            if target_unit_instance_id is None:
                return False
            if not _target_is_enemy_within_distance(
                state=state,
                attacking_unit_instance_id=attacking_unit_instance_id,
                target_unit_instance_id=target_unit_instance_id,
                distance_inches=12.0,
            ):
                return False
            continue
        if constraint == TARGET_CONSTRAINT_NOT_BELOW_HALF_STRENGTH:
            if target_unit_instance_id is None:
                return False
            if not _target_is_not_below_half_strength(
                state=state,
                target_unit_instance_id=target_unit_instance_id,
            ):
                return False
            continue
        raise GameLifecycleError("Unsupported generic RuleIR target_constraint.")
    return True


def generic_rule_target_proximity_keyword_gate_applies(
    *,
    state: object,
    parameters: dict[str, JsonValue],
    attacking_unit_instance_id: str,
    target_unit_instance_id: str | None,
) -> bool:
    if not any(
        key in parameters
        for key in (
            "target_proximity_distance_inches",
            "target_proximity_unit_allegiance",
            "target_proximity_required_keyword_sequence",
        )
    ):
        return True
    if target_unit_instance_id is None:
        return False
    distance = _target_proximity_distance(parameters)
    allegiance = _target_proximity_allegiance(parameters)
    required_keywords = _target_proximity_required_keywords(parameters)
    attacker_owner = _unit_owner(state=state, unit_instance_id=attacking_unit_instance_id)
    for candidate_unit_id in _unit_ids_by_allegiance(
        state=state,
        player_id=attacker_owner,
        allegiance=allegiance,
    ):
        if all(
            _unit_has_keyword(state=state, unit_instance_id=candidate_unit_id, keyword=keyword)
            for keyword in required_keywords
        ) and (
            _closest_unit_distance_inches(
                state=state,
                first_unit_instance_id=candidate_unit_id,
                second_unit_instance_id=target_unit_instance_id,
            )
            <= distance
        ):
            return True
    return False


def _target_constraint_condition_parameters(
    conditions: tuple[dict[str, JsonValue], ...],
) -> tuple[dict[str, JsonValue], ...]:
    parameters: list[dict[str, JsonValue]] = []
    for condition in conditions:
        if condition.get("kind") != RuleConditionKind.TARGET_CONSTRAINT.value:
            continue
        condition_parameters = condition.get("parameters")
        if not isinstance(condition_parameters, dict):
            raise GameLifecycleError("Generic RuleIR condition parameters must be an object.")
        parameters.append(condition_parameters)
    return tuple(parameters)


def _target_is_closest_enemy_within_distance(
    *,
    state: object,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    distance_inches: float,
) -> bool:
    attacker_owner = _unit_owner(state=state, unit_instance_id=attacking_unit_instance_id)
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_instance_id)
    if attacker_owner == target_owner:
        return False
    target_distance = _closest_unit_distance_inches(
        state=state,
        first_unit_instance_id=attacking_unit_instance_id,
        second_unit_instance_id=target_unit_instance_id,
    )
    if target_distance > distance_inches:
        return False
    for enemy_unit_id in _enemy_unit_ids_for_player(state=state, player_id=attacker_owner):
        candidate_distance = _closest_unit_distance_inches(
            state=state,
            first_unit_instance_id=attacking_unit_instance_id,
            second_unit_instance_id=enemy_unit_id,
        )
        if candidate_distance < target_distance:
            return False
    return True


def _target_is_enemy_within_distance(
    *,
    state: object,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    distance_inches: float,
) -> bool:
    attacker_owner = _unit_owner(state=state, unit_instance_id=attacking_unit_instance_id)
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_instance_id)
    if attacker_owner == target_owner:
        return False
    return (
        _closest_unit_distance_inches(
            state=state,
            first_unit_instance_id=attacking_unit_instance_id,
            second_unit_instance_id=target_unit_instance_id,
        )
        <= distance_inches
    )


def _target_is_not_below_half_strength(
    *,
    state: object,
    target_unit_instance_id: str,
) -> bool:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR half-strength gate requires GameState.")
    target_unit_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_id,
    )
    context = BelowHalfStrengthContext.from_rules_unit(
        rules_unit=target_rules_unit,
        starting_strength=state.starting_strength_record_for_unit(target_unit_id),
        current_model_ids=tuple(
            model.model_instance_id for model in target_rules_unit.alive_models()
        ),
    )
    return not context.is_below_half_strength


def _enemy_unit_ids_for_player(*, state: object, player_id: str) -> tuple[str, ...]:
    return _placed_rules_unit_ids_by_allegiance(
        state=state,
        player_id=player_id,
        allegiance=TARGET_ALLEGIANCE_ENEMY,
    )


def _unit_ids_by_allegiance(
    *,
    state: object,
    player_id: str,
    allegiance: str,
) -> tuple[str, ...]:
    return _placed_rules_unit_ids_by_allegiance(
        state=state,
        player_id=player_id,
        allegiance=allegiance,
    )


def _placed_rules_unit_ids_by_allegiance(
    *,
    state: object,
    player_id: str,
    allegiance: str,
) -> tuple[str, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR target proximity gate requires GameState.")
    requested_player_id = _validate_identifier("player_id", player_id)
    if allegiance not in {TARGET_ALLEGIANCE_FRIENDLY, TARGET_ALLEGIANCE_ENEMY}:
        raise GameLifecycleError("Unsupported generic RuleIR target proximity allegiance.")
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Generic RuleIR target proximity gate requires battlefield_state.")
    placed_model_ids = frozenset(battlefield.placed_model_ids())
    return tuple(
        view.unit_instance_id
        for view in rules_unit_views_from_armies(armies=tuple(state.army_definitions))
        if (view.owner_player_id == requested_player_id)
        == (allegiance == TARGET_ALLEGIANCE_FRIENDLY)
        and any(
            model.is_alive and model.model_instance_id in placed_model_ids
            for model in view.own_models
        )
    )


def _unit_owner(*, state: object, unit_instance_id: str) -> str:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR target constraints require GameState.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return rules_unit_view_by_id(
        state=state,
        unit_instance_id=requested_unit_id,
    ).owner_player_id


def _closest_unit_distance_inches(
    *,
    state: object,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> float:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR target constraints require GameState.")
    first_models = geometry_models_for_rules_unit(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_models = geometry_models_for_rules_unit(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    if not first_models or not second_models:
        raise GameLifecycleError("Generic RuleIR target constraint requires placed models.")
    return min(
        DistanceMeasurementContext.from_models(first_model, second_model).closest_distance_inches()
        for first_model in first_models
        for second_model in second_models
    )


def _unit_has_keyword(*, state: object, unit_instance_id: str, keyword: str) -> bool:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic RuleIR keyword gate requires GameState.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=_validate_identifier("unit_instance_id", unit_instance_id),
    )
    return unit_has_required_keywords(
        unit_keywords=rules_unit.keywords,
        faction_keywords=rules_unit.faction_keywords,
        required_keywords=(_validate_identifier("keyword", keyword),),
    )


def _target_proximity_distance(parameters: dict[str, JsonValue]) -> float:
    value = parameters.get("target_proximity_distance_inches")
    if type(value) not in {int, float}:
        raise GameLifecycleError("Generic RuleIR target_proximity_distance_inches must be numeric.")
    distance = float(cast(int | float, value))
    if distance < 0.0:
        raise GameLifecycleError(
            "Generic RuleIR target_proximity_distance_inches must not be negative."
        )
    return distance


def _target_proximity_allegiance(parameters: dict[str, JsonValue]) -> str:
    value = parameters.get("target_proximity_unit_allegiance")
    if type(value) is not str:
        raise GameLifecycleError(
            "Generic RuleIR target_proximity_unit_allegiance must be a string."
        )
    allegiance = _validate_identifier("target_proximity_unit_allegiance", value)
    if allegiance not in {TARGET_ALLEGIANCE_FRIENDLY, TARGET_ALLEGIANCE_ENEMY}:
        raise GameLifecycleError("Unsupported generic RuleIR target proximity allegiance.")
    return allegiance


def _target_proximity_required_keywords(parameters: dict[str, JsonValue]) -> tuple[str, ...]:
    value = parameters.get("target_proximity_required_keyword_sequence")
    if not isinstance(value, list):
        raise GameLifecycleError(
            "Generic RuleIR target_proximity_required_keyword_sequence must be a list."
        )
    keywords: list[str] = []
    for item in cast(list[object], value):
        if type(item) is not str:
            raise GameLifecycleError(
                "Generic RuleIR target_proximity_required_keyword_sequence must contain strings."
            )
        keywords.append(_validate_identifier("target_proximity_required_keyword_sequence", item))
    if not keywords:
        raise GameLifecycleError(
            "Generic RuleIR target_proximity_required_keyword_sequence must not be empty."
        )
    return tuple(keywords)


_validate_identifier = IdentifierValidator(GameLifecycleError)
