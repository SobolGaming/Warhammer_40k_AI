"""Attack rerolls follow the active host, including retained and out-of-phase attacks."""

from __future__ import annotations

# This dispatch adapter accesses lifecycle-owned authorities, like the other dispatch adapters.
# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING, cast

from warhammer40k_core.core.dice import DiceRollResult, DiceRollResultPayload, DiceRollState
from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
    _source_backed_attack_context_id_matches_active_pool,
    apply_source_backed_attack_dice_reroll_decision,
    build_source_backed_wound_reroll_request,
)
from warhammer40k_core.engine.attack_sequence_model import attack_sequence_wound_roll_spec
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DICE_REROLL_DECISION_TYPE
from warhammer40k_core.engine.dice_roll_history import latest_roll_state
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.lifecycle_state_queries import active_attack_sequence_for_state
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.lifecycle import GameLifecycle


def attack_reroll_dispatch_handler(lifecycle: GameLifecycle) -> DecisionDispatchHandler:
    def validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:
        if not _is_attack_reroll(lifecycle, request):
            return lifecycle._pre_validate_movement_phase_decision(request, result)
        try:
            result.validate_for_request(request)
            validate_wound_reroll_request(lifecycle, request)
        except (GameLifecycleError, DecisionError, KeyError, ValueError) as exc:
            return LifecycleStatus.invalid(
                stage=lifecycle._require_state().stage,
                message=str(exc),
                payload={"invalid_reason": "attack_reroll_context_drift"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        if not _is_attack_reroll(lifecycle, record.request):
            return lifecycle._apply_movement_phase_decision(record, result)
        state = lifecycle._require_state()
        sequence = active_attack_sequence_for_state(state)
        if sequence is None:
            raise GameLifecycleError("Attack reroll lost its active host.")
        resolves_reaction = lifecycle._result_resolves_active_reaction_frame(result)
        apply_source_backed_attack_dice_reroll_decision(
            state=state,
            result=result,
            decisions=lifecycle.decision_controller,
            attack_sequence=sequence,
            expected_phase=sequence.source_phase,
            phase_label=sequence.source_phase.value,
            runtime_modifier_registry=lifecycle._require_runtime_content_bundle().runtime_modifier_registry,
        )
        if resolves_reaction and sequence.source_phase is BattlePhase.SHOOTING:
            handled = lifecycle._continue_or_resolve_out_of_phase_reaction(
                result=result, status=None
            )
            if handled is not None:
                return handled
        status = lifecycle.advance_until_decision_or_terminal()
        if resolves_reaction and sequence.source_phase is BattlePhase.FIGHT:
            lifecycle._continue_or_resolve_fight_reaction(result=result, status=status)
        return status

    return DecisionDispatchHandler(
        decision_type=DICE_REROLL_DECISION_TYPE, pre_validator=validate, applier=apply
    )


def validate_pending_attack_rerolls(lifecycle: GameLifecycle) -> None:
    for request in lifecycle.decision_controller.queue.pending_requests:
        if _is_attack_reroll(lifecycle, request):
            validate_wound_reroll_request(lifecycle, request)


def _is_attack_reroll(lifecycle: GameLifecycle, request: DecisionRequest) -> bool:
    if request.decision_type != DICE_REROLL_DECISION_TYPE:
        return False
    if _issued_after_physical_wound(lifecycle, request):
        return True
    # A drifted pending payload cannot reclassify the originally issued choice.
    payloads = (
        request.payload,
        *(
            event.payload["payload"]
            for event in lifecycle.decision_controller.event_log.records
            if event.event_type == "decision_requested"
            and isinstance(event.payload, dict)
            and event.payload.get("request_id") == request.request_id
            and "payload" in event.payload
        ),
    )
    return any(
        isinstance(payload, dict)
        and ("attack_context" in payload or payload.get("roll_type") == "attack_sequence.wound")
        for payload in payloads
    )


def _issued_after_physical_wound(lifecycle: GameLifecycle, request: DecisionRequest) -> bool:
    """The original physical roll also binds routing when both wire copies drift."""
    last_roll_type: JsonValue = None
    for event in lifecycle.decision_controller.event_log.records:
        if not isinstance(event.payload, dict):
            continue
        if event.event_type == "dice_rolled":
            spec = event.payload.get("spec")
            if isinstance(spec, dict):
                last_roll_type = spec.get("roll_type")
        if (
            event.event_type == "decision_requested"
            and event.payload.get("request_id") == request.request_id
        ):
            return last_roll_type == "attack_sequence.wound"
    return False


def validate_wound_reroll_request(lifecycle: GameLifecycle, request: DecisionRequest) -> None:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Attack reroll requires an object payload.")
    issued = tuple(
        event.payload
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "decision_requested"
        and isinstance(event.payload, dict)
        and event.payload.get("request_id") == request.request_id
    )
    if len(issued) != 1 or canonical_json(issued[0]) != canonical_json(request.to_payload()):
        raise GameLifecycleError("Wound reroll request differs from its issued authority.")
    if payload.get("roll_type") != "attack_sequence.wound" and not _issued_after_physical_wound(
        lifecycle, request
    ):
        return
    state = lifecycle._require_state()
    decisions = lifecycle.decision_controller
    sequence = active_attack_sequence_for_state(state)
    if sequence is None:
        raise GameLifecycleError("Wound reroll requires an active attack host.")
    context = payload.get("attack_context")
    if not isinstance(context, dict) or type(context.get("attack_context_id")) is not str:
        raise GameLifecycleError("Wound reroll requires its attack context.")
    context_id = cast(str, context["attack_context_id"])
    if not _source_backed_attack_context_id_matches_active_pool(
        attack_sequence=sequence, attack_context_id=context_id
    ):
        raise GameLifecycleError("Wound reroll attack context drift.")
    # Grouped resolution restarts its pool on resume. The last physical wound,
    # rather than the persisted pool cursor, identifies the unresolved frontier.
    wounds = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "dice_rolled"
        and isinstance(event.payload, dict)
        and isinstance(event.payload.get("spec"), dict)
        and cast(dict[str, JsonValue], event.payload["spec"]).get("roll_type")
        == "attack_sequence.wound"
    )
    if not wounds:
        raise GameLifecycleError("Wound reroll has no physical dice authority.")
    physical = DiceRollResult.from_payload(cast(DiceRollResultPayload, wounds[-1].payload))
    pool = sequence.current_pool()
    if physical.spec != attack_sequence_wound_roll_spec(
        weapon_profile_id=pool.weapon_profile_id,
        attack_context_id=context_id,
        attacker_player_id=sequence.attacker_player_id,
    ):
        raise GameLifecycleError("Wound reroll physical attack identity drift.")
    roll = latest_roll_state(decisions=decisions, roll_id=physical.roll_id)
    if roll != DiceRollState.from_result(physical) or any(
        event.event_type == "attack_sequence_step"
        and isinstance(event.payload, dict)
        and event.payload.get("step") == "wound"
        and event.payload.get("attack_context_id") == context_id
        for event in decisions.event_log.records
    ):
        raise GameLifecycleError("Wound reroll no longer owns an unresolved physical die.")
    expected = build_source_backed_wound_reroll_request(
        state=state,
        decisions=decisions,
        roll_state=roll,
        pool=pool,
        attacking_unit_instance_id=sequence.attacking_unit_instance_id,
        attacker_model_instance_id=pool.attacker_model_instance_id,
        attacker_keywords=rules_unit_view_by_id(
            state=state, unit_instance_id=sequence.attacking_unit_instance_id
        ).keywords,
        attack_context_id=context_id,
        source_phase=sequence.source_phase,
        runtime_modifier_registry=lifecycle._require_runtime_content_bundle().runtime_modifier_registry,
        request_id=request.request_id,
    )
    if expected is None or canonical_json(expected.to_payload()) != canonical_json(
        request.to_payload()
    ):
        raise GameLifecycleError("Wound reroll request differs from current source authority.")
