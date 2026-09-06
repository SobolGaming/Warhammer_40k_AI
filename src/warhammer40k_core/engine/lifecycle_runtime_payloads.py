from __future__ import annotations

from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


def payload_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


def runtime_mortal_wound_source_context_phase(source_context: JsonValue) -> BattlePhase:
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Runtime mortal wound FNP source context must be an object.")
    phase_value = source_context.get("phase")
    if phase_value is None:
        resolution_payload = source_context.get("resolution_payload")
        if isinstance(resolution_payload, dict):
            phase_value = resolution_payload.get("phase")
    if type(phase_value) is not str:
        raise GameLifecycleError("Runtime mortal wound FNP source context is missing phase.")
    try:
        return BattlePhase(phase_value)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported runtime mortal wound FNP phase: {phase_value}."
        ) from exc
