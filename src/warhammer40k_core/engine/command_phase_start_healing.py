from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.engine import command_phase_start_authority as authority
from warhammer40k_core.engine.command_phase_start_hooks import (
    CommandPhaseStartNestedPendingAuthorityContext,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.healing import (
    SELECT_HEALING_MODEL_DECISION_TYPE,
    HealingEffect,
    HealingEffectPayload,
)
from warhammer40k_core.engine.healing_revival import SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_pending_healing_source(
    context: CommandPhaseStartNestedPendingAuthorityContext,
    *,
    hook_id: str,
    source_rule_id: str,
) -> bool:
    """Authenticate later healing choices to the selected Command-start rule's output."""
    if context.request.decision_type not in (
        SELECT_HEALING_MODEL_DECISION_TYPE,
        SUBMIT_HEALING_REVIVAL_PLACEMENT_DECISION_TYPE,
    ):
        return False
    payload = context.request.payload
    if not isinstance(payload, dict) or not isinstance(payload.get("effect"), dict):
        raise GameLifecycleError("Command-start healing request lacks its effect.")
    effect = HealingEffect.from_payload(cast(HealingEffectPayload, payload["effect"]))
    source = effect.source_context
    if (
        effect.source_rule_id != source_rule_id
        or not isinstance(source, dict)
        or source.get("hook_id") != hook_id
    ):
        return False
    request_id = authority.payload_string(source, "request_id")
    result_id = authority.payload_string(source, "result_id")
    outer = authority.decision_record_by_request_id(
        context.decisions.records, request_id=request_id
    )
    if outer is None or outer.result.result_id != result_id:
        raise GameLifecycleError("Command-start healing has no accepted source choice.")
    records = context.decisions.event_log.records
    applied = tuple(
        (index, event)
        for index, event in enumerate(records)
        if event.event_type == authority.COMMAND_START_FINITE_RESULT_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request_id
        and event.payload.get("provider_hook_id") == hook_id
        and event.payload.get("provider_source_id") == source_rule_id
    )
    if len(applied) != 1:
        raise GameLifecycleError("Command-start healing source disposition is ambiguous.")
    recorded_index = authority.exact_event_index(
        records, event_type="decision_recorded", payload=outer.to_payload()
    )
    initial: list[dict[str, JsonValue]] = []
    for event in records[recorded_index + 1 : applied[0][0]]:
        if event.event_type != "decision_requested" or not isinstance(event.payload, dict):
            continue
        request_payload = event.payload.get("payload")
        if not isinstance(request_payload, dict):
            raise GameLifecycleError("Command-start source request payload is malformed.")
        retained_effect = request_payload.get("effect")
        if (
            isinstance(retained_effect, dict)
            and retained_effect.get("effect_id") == effect.effect_id
        ):
            initial.append(event.payload)
    if len(initial) != 1:
        raise GameLifecycleError("Command-start healing lacks its original provider request.")
    original_payload = initial[0]["payload"]
    if not isinstance(original_payload, dict) or not isinstance(
        original_payload.get("effect"), dict
    ):
        raise GameLifecycleError("Command-start healing initial effect is malformed.")
    original = HealingEffect.from_payload(cast(HealingEffectPayload, original_payload["effect"]))
    if replace(effect, resolved_steps=original.resolved_steps) != original:
        raise GameLifecycleError("Command-start healing source effect drifted.")
    pending_index = authority.exact_event_index(
        records, event_type="decision_requested", payload=context.request.to_payload()
    )
    steps = tuple(
        event.payload["step"]
        for event in records[recorded_index + 1 : pending_index]
        if event.event_type == "healing_step_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("effect_id") == effect.effect_id
    )
    if steps != tuple(step.to_payload() for step in effect.resolved_steps):
        raise GameLifecycleError("Command-start healing continuation steps drifted.")
    return True
