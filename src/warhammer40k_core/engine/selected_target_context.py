from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

SELECTED_TARGET_UNIT_CONTEXT_KEY = "selected_target_unit_instance_ids"

_validate_identifier = IdentifierValidator(GameLifecycleError)


def selected_target_unit_ids_or_none(trigger_payload: JsonValue) -> tuple[str, ...] | None:
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_ids = trigger_payload.get(SELECTED_TARGET_UNIT_CONTEXT_KEY)
    if not isinstance(raw_unit_ids, list):
        return None
    unit_ids: list[str] = []
    seen: set[str] = set()
    for raw_unit_id in raw_unit_ids:
        if type(raw_unit_id) is not str:
            return None
        unit_id = _validate_identifier("Selected target unit id", raw_unit_id)
        if unit_id in seen:
            return None
        seen.add(unit_id)
        unit_ids.append(unit_id)
    return tuple(sorted(unit_ids))
