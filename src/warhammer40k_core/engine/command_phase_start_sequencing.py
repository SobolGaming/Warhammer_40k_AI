from __future__ import annotations

from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind
from warhammer40k_core.engine.command_phase_start_hooks import (
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    CommandPhaseStartEffectContext,
    CommandPhaseStartHookBinding,
    CommandPhaseStartHookRegistry,
    CommandPhaseStartRequestContext,
    provider_disposition,
    provider_snapshot,
    require_request_provider_side_effects,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def command_start_timing_context(
    state: GameState, *, battle_round: int, active_player_id: str
) -> SequencingConflictContext:
    identifier = f"command-start:{state.game_id}:{battle_round}:{active_player_id}"
    window_id = (
        f"timing-window:{state.game_id}:round-{battle_round:02d}:"
        f"turn:{active_player_id}:phase:command:start"
    )
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=active_player_id,
        timing_window=TimingWindow(
            window_id=(
                f"timing-window:{state.game_id}:round-{battle_round:02d}:"
                f"turn:{active_player_id}:phase:command:start"
            ),
            game_id=state.game_id,
            battle_round=battle_round,
            active_player_id=active_player_id,
            phase=BattlePhaseKind.COMMAND,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{window_id}:descriptor",
                trigger_kind=TimingTriggerKind.START_PHASE,
                source_rule_id="core-rules-lifecycle-timing",
                source_step="command",
                phase=BattlePhaseKind.COMMAND,
            ),
        ),
    )


def command_start_candidates(
    context: CommandPhaseStartEffectContext, registry: CommandPhaseStartHookRegistry
) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        TimingRuleCandidate(
            participant=replace(
                candidate.participant,
                payload={
                    "provider_hook_id": binding.hook_id,
                    "provider_source_id": binding.source_id,
                    "source_occurrence": candidate.participant.payload,
                },
            ),
            activate=partial(_activate, context, registry, binding, candidate),
            request_template=candidate.request_template,
        )
        for candidate, binding in registry.candidate_entries_for(context)
    )


def resolve_command_start_candidates(
    context: CommandPhaseStartEffectContext, registry: CommandPhaseStartHookRegistry
) -> LifecycleStatus | None:
    from warhammer40k_core.engine import command_phase_start_authority as authority

    outcome = resolve_timing_rule_candidates(
        decisions=context.decisions,
        context=command_start_timing_context(
            context.state,
            battle_round=context.state.battle_round,
            active_player_id=context.active_player_id,
        ),
        discover=partial(command_start_candidates, context, registry),
        next_request_id=context.state.next_decision_request_id,
    )
    if type(outcome) is DecisionRequest:
        context.decisions.request_decision(outcome)
        context.decisions.event_log.append(
            authority.COMMAND_START_ORDER_REQUESTED_EVENT,
            {
                **authority.authority_common_payload(state=context.state, registry=registry),
                "request_id": outcome.request_id,
                "request_payload_hash": authority.payload_hash(outcome.to_payload()),
            },
        )
        return _waiting(context, outcome)
    if outcome is not None and not isinstance(outcome, LifecycleStatus):
        raise GameLifecycleError("Command-start scheduler returned an invalid status.")
    return outcome


def _activate(
    context: CommandPhaseStartEffectContext,
    registry: CommandPhaseStartHookRegistry,
    binding: CommandPhaseStartHookBinding,
    candidate: TimingRuleCandidate,
) -> DecisionRequest | LifecycleStatus | None:
    from warhammer40k_core.engine import command_phase_start_authority as authority

    before = provider_snapshot(context)
    outcome = candidate.activate()
    if type(outcome) is DecisionRequest:
        if outcome.decision_type != SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE:
            raise GameLifecycleError("Command-start requests must use the finite decision type.")
        if candidate.request_template is None or binding.result_handler is None:
            raise GameLifecycleError("Command-start request lacks its source provider.")
        require_request_provider_side_effects(
            context=CommandPhaseStartRequestContext(
                state=context.state,
                decisions=context.decisions,
                active_player_id=context.active_player_id,
            ),
            before=before,
            request=outcome,
        )
        context.decisions.request_decision(outcome)
        context.decisions.event_log.append(
            authority.COMMAND_START_FINITE_REQUESTED_EVENT,
            {
                **authority.authority_common_payload(state=context.state, registry=registry),
                "decision_type": outcome.decision_type,
                "request_id": outcome.request_id,
                "request_payload_hash": authority.payload_hash(outcome.to_payload()),
                "provider_hook_id": binding.hook_id,
                "provider_source_id": binding.source_id,
            },
        )
        return _waiting(context, outcome)
    disposition = provider_disposition(context=context, binding=binding, before=before)
    if type(outcome) is LifecycleStatus:
        authority.record_effect_pause(
            state=context.state,
            decisions=context.decisions,
            registry=registry,
            binding=binding,
            status=outcome,
            dispositions=(disposition,),
        )
        return outcome
    if outcome is not None:
        raise GameLifecycleError("Command-start activation returned an invalid continuation.")
    authority.require_empty_pending_queue(
        decisions=context.decisions,
        context="Completed Command-start rule retained a pending decision",
    )
    context.decisions.event_log.append(
        authority.COMMAND_START_RULE_COMPLETED_EVENT,
        {
            **authority.authority_common_payload(state=context.state, registry=registry),
            "participant_id": candidate.participant.participant_id,
            "provider_hook_id": binding.hook_id,
            "provider_source_id": binding.source_id,
            "provider_dispositions": authority.provider_dispositions_payload((disposition,)),
        },
    )
    return None


def _waiting(context: CommandPhaseStartEffectContext, request: DecisionRequest) -> LifecycleStatus:
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.COMMAND.value,
            "active_player_id": context.active_player_id,
            "phase_body_status": "command_phase_start_rule_pending",
        },
    )
