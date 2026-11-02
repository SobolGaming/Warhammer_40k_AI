"""Finite optional effects at captured movement-completion occurrences."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Protocol

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_dispatch import DecisionDispatchHandler
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionError, DecisionOption, DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_resources import resolve_faction_resource_refund_roll
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.move_completion_rule_hooks import MoveCompletionRuleBinding
from warhammer40k_core.engine.move_completion_triggers import move_context_for_trigger
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_trigger_state import RuleTriggerKind, rule_trigger_history
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext

SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE = "select_move_completion_effect"
RESOLVED_EVENT = "move_completion_effect_resolved"


@dataclass(frozen=True, slots=True)
class MoveCompletionEffectGrant:
    label: str
    effect_payload: JsonValue
    expiration: EffectExpiration
    decision_effect_payload: JsonValue = None

    def __post_init__(self) -> None:
        if type(self.label) is not str or not self.label:
            raise GameLifecycleError("Move completion grant requires a label.")
        if type(self.expiration) is not EffectExpiration:
            raise GameLifecycleError("Move completion grant requires a typed expiration.")
        validate_json_value(self.effect_payload)
        validate_json_value(self.decision_effect_payload)


def optional_move_completion_effect_binding(
    *,
    hook_id: str,
    source_rule_id: str,
    owns_trigger: Callable[[UnitMoveCompletedContext], bool],
    grant_for: Callable[[UnitMoveCompletedContext], MoveCompletionEffectGrant | None],
) -> MoveCompletionRuleBinding:
    """Capture stable source ownership; recheck mutable eligibility before offering."""

    def participants(context: UnitMoveCompletedContext) -> tuple[SequencingParticipant, ...]:
        if not owns_trigger(context):
            return ()
        return (
            SequencingParticipant(
                participant_id=f"{hook_id}:{context.trigger_event_id}",
                player_id=context.triggering_player_id,
                source_rule_id=source_rule_id,
                requirement=SequencingRequirement.OPTIONAL,
                payload={
                    "hook_id": hook_id,
                    "trigger_event_id": context.trigger_event_id,
                    "unit_instance_id": context.triggering_unit_instance_id,
                },
            ),
        )

    def resume(
        context: UnitMoveCompletedContext, participant: SequencingParticipant
    ) -> TimingRuleCandidate | None:
        decisions = _decisions(context)
        if participant not in participants(context):
            raise GameLifecycleError("Move completion effect source ownership drift.")
        resolved = tuple(
            event
            for event in decisions.event_log.records
            if event.event_type == RESOLVED_EVENT
            and isinstance(event.payload, dict)
            and event.payload.get("participant_id") == participant.participant_id
        )
        if resolved:
            if len(resolved) != 1:
                raise GameLifecycleError("Move completion effect resolved more than once.")
            return None
        # Historical trigger validation must not create a new choice in a later window.
        payload = context.trigger_event_payload
        if (
            payload.get("battle_round") != context.state.battle_round
            or context.completed_phase is not context.state.current_battle_phase
            or payload.get("active_player_id") != context.state.effective_active_player_id()
        ):
            return None
        grant = grant_for(context)
        if grant is None:
            return None
        request = _request(context, participant, grant)
        return TimingRuleCandidate(
            participant=participant,
            request_template=request,
            activate=partial(_activate, context, participant, grant, request),
        )

    def candidates(context: UnitMoveCompletedContext) -> tuple[TimingRuleCandidate, ...]:
        return tuple(
            candidate
            for participant in participants(context)
            if (candidate := resume(context, participant)) is not None
        )

    return MoveCompletionRuleBinding(
        hook_id=hook_id,
        source_rule_id=source_rule_id,
        candidates=candidates,
        participants_at_trigger=participants,
        resume=resume,
    )


def _decisions(context: UnitMoveCompletedContext) -> DecisionController:
    if context.decisions is None:
        raise GameLifecycleError("Move completion effect requires decisions.")
    return context.decisions


def _request(
    context: UnitMoveCompletedContext,
    participant: SequencingParticipant,
    grant: MoveCompletionEffectGrant,
) -> DecisionRequest:
    payload: dict[str, JsonValue] = {
        "game_id": context.state.game_id,
        "battle_round": context.state.battle_round,
        "phase": context.completed_phase.value,
        "active_player_id": context.state.active_player_id,
        "trigger_event_id": context.trigger_event_id,
        "participant_id": participant.participant_id,
        "source_rule_id": participant.source_rule_id,
        "unit_instance_id": context.triggering_unit_instance_id,
        "effect_payload": grant.effect_payload,
        "expiration": validate_json_value(grant.expiration.to_payload()),
        "decision_effect_payload": grant.decision_effect_payload,
    }
    return DecisionRequest(
        request_id=f"{participant.participant_id}:choice",
        decision_type=SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE,
        actor_id=participant.player_id,
        payload=payload,
        options=(
            DecisionOption("use", grant.label, {"selected": True}),
            DecisionOption("decline", "Decline", {"selected": False}),
        ),
    )


def _activate(
    context: UnitMoveCompletedContext,
    participant: SequencingParticipant,
    grant: MoveCompletionEffectGrant,
    request: DecisionRequest,
) -> DecisionRequest | None:
    decisions = _decisions(context)
    if participant.player_id is None:
        raise GameLifecycleError("Optional move effect requires its player owner.")
    records = tuple(
        row for row in decisions.records if row.request.request_id == request.request_id
    )
    if not records:
        return request
    if len(records) != 1 or records[0].request != request:
        raise GameLifecycleError("Move completion effect recorded request drift.")
    record = records[0]
    record.result.validate_for_request(request)
    effects: list[PersistingEffect] = []
    if record.result.selected_option_id == "use":
        state = context.state
        effect = PersistingEffect(
            effect_id=f"{record.result.result_id}:move-effect",
            source_rule_id=participant.source_rule_id,
            owner_player_id=participant.player_id,
            target_unit_instance_ids=(context.triggering_unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=context.completed_phase,
            expiration=grant.expiration,
            effect_payload=grant.effect_payload,
        )
        spend = None
        if grant.decision_effect_payload is not None:
            spend = PersistingEffect(
                effect_id=f"{record.result.result_id}:move-effect:decision",
                source_rule_id=participant.source_rule_id,
                owner_player_id=participant.player_id,
                target_unit_instance_ids=(context.triggering_unit_instance_id,),
                started_battle_round=state.battle_round,
                started_phase=context.completed_phase,
                expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
                effect_payload=grant.decision_effect_payload,
            )
        if any(
            row.effect_id in {effect.effect_id, None if spend is None else spend.effect_id}
            for row in state.persisting_effects
        ):
            raise GameLifecycleError("Move completion effect identity is already recorded.")
        state.record_persisting_effect(effect)
        effects.append(effect)
        if spend is not None:
            state.record_persisting_effect(spend)
            resolve_faction_resource_refund_roll(
                state=state, decisions=decisions, spend_effect=spend
            )
            effects.append(spend)
    decisions.event_log.append(
        RESOLVED_EVENT,
        {
            "game_id": context.state.game_id,
            "participant_id": participant.participant_id,
            "trigger_event_id": context.trigger_event_id,
            "request_id": request.request_id,
            "result_id": record.result.result_id,
            "selected": record.result.selected_option_id == "use",
            "effects": [validate_json_value(effect.to_payload()) for effect in effects],
        },
    )
    return None


class MoveCompletionEffectHost(Protocol):
    decision_controller: DecisionController

    def _require_state(self) -> GameState: ...
    def advance_until_decision_or_terminal(self) -> LifecycleStatus: ...


def decision_dispatch_handlers(
    host: MoveCompletionEffectHost,
) -> tuple[DecisionDispatchHandler, ...]:
    def pre_validate(request: DecisionRequest, result: DecisionResult) -> LifecycleStatus | None:

        state = host._require_state()  # pyright: ignore[reportPrivateUsage]
        try:
            result.validate_for_request(request)
            _validate_pending(state, host.decision_controller, request)
        except (GameLifecycleError, DecisionError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message=str(exc),
                payload={"reason": "invalid_move_completion_effect"},
            )
        return None

    def apply(record: DecisionRecord, result: DecisionResult) -> LifecycleStatus:
        return host.advance_until_decision_or_terminal()

    return (
        DecisionDispatchHandler(
            decision_type=SELECT_MOVE_COMPLETION_EFFECT_DECISION_TYPE,
            pre_validator=pre_validate,
            applier=apply,
        ),
    )


def _validate_pending(
    state: GameState, decisions: DecisionController, request: DecisionRequest
) -> None:
    from warhammer40k_core.engine.faction_content.unit_move_completed import (
        move_completion_rule_registry,
    )

    if not isinstance(request.payload, dict):
        raise GameLifecycleError("Move completion effect requires an object payload.")
    triggers = tuple(
        trigger
        for trigger in rule_trigger_history(decisions).ready()
        if trigger.kind is RuleTriggerKind.MOVE_COMPLETION
        and isinstance(trigger.context, dict)
        and trigger.context.get("trigger_event_id") == request.payload.get("trigger_event_id")
    )
    if len(triggers) != 1:
        raise GameLifecycleError("Move completion effect has no live trigger.")
    context = move_context_for_trigger(
        state=state,
        decisions=decisions,
        trigger=triggers[0],
        runtime_modifiers=RuntimeModifierRegistry.empty(),
        ability_indexes={},
    )
    requests = tuple(
        candidate.request_template
        for candidate in move_completion_rule_registry().candidates_for(context)
        if candidate.request_template is not None
    )
    if request not in requests:
        raise GameLifecycleError("Move completion effect eligibility or request drift.")
