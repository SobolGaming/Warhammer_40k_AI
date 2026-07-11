from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.stratagems_model import (
    ENGAGED_ENEMY_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    HIT_ENEMY_UNIT_CONTEXT_KEY,
    HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    TARGET_BINDING_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_CONTEXT_KEY,
    VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
    StratagemEligibilityContext,
    StratagemUseRecord,
)

_validate_identifier = IdentifierValidator(GameLifecycleError)


def rule_effect_source_unit_id_for_context(
    *,
    context: StratagemEligibilityContext,
    use_record: StratagemUseRecord,
    effect_payload: dict[str, JsonValue],
) -> str:
    context_key = _required_rule_effect_string_parameter(effect_payload, "source_unit_context_key")
    if context_key == TARGET_BINDING_UNIT_CONTEXT_KEY:
        return _single_target_unit_id(use_record)
    return _trigger_payload_identifier(context, key=context_key)


def effect_selection_unit_id(
    use_record: StratagemUseRecord,
    *,
    expected_selection_kind: str,
) -> str:
    selection_kind = _validate_identifier("effect_selection_kind", expected_selection_kind)
    selection = use_record.effect_selection
    if not isinstance(selection, dict):
        raise GameLifecycleError("Generic Stratagem effect requires effect selection.")
    if selection.get("effect_selection_kind") != selection_kind:
        raise GameLifecycleError("Generic Stratagem effect selection kind drift.")
    if selection_kind == HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        key = HIT_ENEMY_UNIT_CONTEXT_KEY
    elif selection_kind == ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        key = ENGAGED_ENEMY_UNIT_CONTEXT_KEY
    elif selection_kind == VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        key = VISIBLE_ENEMY_UNIT_CONTEXT_KEY
    else:
        raise GameLifecycleError("Generic Stratagem effect selection kind is unsupported.")
    value = selection.get(key)
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem effect selection is missing unit.")
    return _validate_identifier("effect_selection_unit_id", value)


def _single_target_unit_id(use_record: StratagemUseRecord) -> str:
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic Stratagem effect requires use record.")
    if len(use_record.targeted_unit_instance_ids) != 1:
        raise GameLifecycleError("Generic Stratagem effect requires one target unit.")
    return use_record.targeted_unit_instance_ids[0]


def _trigger_payload_identifier(context: StratagemEligibilityContext, *, key: str) -> str:
    requested_key = _validate_identifier("trigger_payload key", key)
    payload = context.trigger_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Generic Stratagem requires structured trigger payload.")
    value = payload.get(requested_key)
    if type(value) is not str:
        raise GameLifecycleError("Generic Stratagem trigger payload is missing a unit.")
    return _validate_identifier("trigger_payload unit id", value)


def _required_rule_effect_string_parameter(
    effect_payload: dict[str, JsonValue],
    key: str,
) -> str:
    value = _rule_effect_parameter(effect_payload, key)
    if type(value) is not str:
        raise GameLifecycleError(f"Generic Stratagem effect parameter {key} must be a string.")
    return _validate_identifier(key, value)


def _rule_effect_parameter(effect_payload: dict[str, JsonValue], key: str) -> JsonValue:
    requested_key = _validate_identifier("generic Stratagem effect parameter", key)
    effect = effect_payload.get("effect")
    if not isinstance(effect, dict):
        raise GameLifecycleError("Generic Stratagem effect payload requires effect object.")
    parameters = effect.get("parameters")
    if not isinstance(parameters, list):
        raise GameLifecycleError("Generic Stratagem effect parameters must be a list.")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            raise GameLifecycleError("Generic Stratagem effect parameter must be an object.")
        if parameter.get("key") != requested_key:
            continue
        return validate_json_value(parameter.get("value"))
    return None
