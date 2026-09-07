"""Pre-pop and restored-history validation for the shared Psychic attack choice."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.modifiers import ModifierError
from warhammer40k_core.engine.attack_sequence_psychic_modifiers import (
    DECISION_TYPE,
    _psychic_attack_modifier_ignore_request,
    _psychic_attack_modifier_ignore_selection_for_attack,
    selection_from_payload,
)
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def validate_current_psychic_request(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    sequence = active_attack_sequence_for_state(state)
    if sequence is None:
        raise GameLifecycleError("Psychic modifier decision has no active attack.")
    previous = _psychic_attack_modifier_ignore_selection_for_attack(
        decisions=decisions,
        attack_context_id=sequence.attack_context_id(),
    )
    expected = _psychic_attack_modifier_ignore_request(
        state=state,
        pool=sequence.current_pool(),
        attacker_player_id=sequence.attacker_player_id,
        attacking_unit_instance_id=sequence.attacking_unit_instance_id,
        attack_context_id=sequence.attack_context_id(),
        source_phase=sequence.source_phase,
        runtime_modifier_registry=runtime_modifier_registry,
        previous_selection=previous,
        request_id=request.request_id,
    )
    if expected is None or canonical_json(expected.to_payload()) != canonical_json(
        request.to_payload()
    ):
        raise GameLifecycleError("Psychic modifier request source or attack context drift.")


def invalid_psychic_modifier_status(
    *,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    result: DecisionResult,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    try:
        result.validate_for_request(request)
        selection_from_payload(result.payload)
        validate_current_psychic_request(
            state=state,
            decisions=decisions,
            request=request,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    except (DecisionError, GameLifecycleError, ModifierError) as exc:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Psychic modifier selection is invalid.",
            payload={
                "invalid_reason": "psychic_modifier_source_or_context_drift",
                "detail": str(exc),
            },
        )
    return None


def validate_psychic_modifier_history(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    contexts: set[str] = set()
    for record in decisions.records:
        if record.request.decision_type != DECISION_TYPE:
            continue
        payload = record.request.payload
        if not isinstance(payload, dict) or type(payload.get("attack_context_id")) is not str:
            raise GameLifecycleError("Psychic modifier history requires an attack context.")
        context = payload["attack_context_id"]
        contexts.add(cast(str, context))
    active = active_attack_sequence_for_state(state)
    for context in sorted(contexts):
        selection = _psychic_attack_modifier_ignore_selection_for_attack(
            decisions=decisions,
            attack_context_id=context,
        )
        if selection is None:
            raise GameLifecycleError("Psychic selection history is incomplete.")
        if not selection.complete:
            if active is None or active.attack_context_id() != context:
                raise GameLifecycleError("Incomplete Psychic selection has no active attack.")
            if not any(
                request.decision_type == DECISION_TYPE
                for request in decisions.queue.pending_requests
            ):
                raise GameLifecycleError("Incomplete Psychic selection has no pending choice.")
    hit_contexts: set[str] = set()
    for event in decisions.event_log.records:
        payload = event.payload
        if event.event_type != "attack_sequence_step" or not isinstance(payload, dict):
            continue
        if payload.get("step") != "hit":
            continue
        context = payload.get("attack_context_id")
        hit = payload.get("payload")
        if not isinstance(hit, dict):
            raise GameLifecycleError("Hit event payload must be an object.")
        raw = hit.get("psychic_modifier_selection")
        if raw is None and context not in contexts:
            continue
        if not isinstance(context, str) or context not in contexts:
            raise GameLifecycleError("Hit event Psychic selection has no decision history.")
        expected = _psychic_attack_modifier_ignore_selection_for_attack(
            decisions=decisions,
            attack_context_id=context,
        )
        hit_contexts.add(context)
        selected = selection_from_payload(raw)
        if (
            selected != expected
            or not selected.complete
            or hit.get("is_psychic_attack") is not True
        ):
            raise GameLifecycleError("Hit event Psychic selection differs from its decisions.")
        expected_target = selected.skill_value(ignored_ids=selected.ignored_modifier_ids)
        if canonical_json(hit.get("target_number")) != canonical_json(expected_target) or (
            hit.get("roll_state") is not None
            and canonical_json(hit.get("modifier"))
            != canonical_json(selected.effective_hit_roll_modifier)
        ):
            raise GameLifecycleError("Hit event Psychic modifier arithmetic drift.")
    for context in contexts - hit_contexts:
        if active is None or active.attack_context_id() != context:
            raise GameLifecycleError("Psychic selection has no active attack or resolved hit.")
    for request in decisions.queue.pending_requests:
        if request.decision_type == DECISION_TYPE:
            validate_current_psychic_request(
                state=state,
                decisions=decisions,
                request=request,
                runtime_modifier_registry=runtime_modifier_registry,
            )
