# pyright: reportPrivateUsage=false
from __future__ import annotations

from collections.abc import Mapping
from functools import partial

from warhammer40k_core.engine.decision_request import parameterized_decision_option
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.phases.movement_reactions import (
    _active_player_end_movement_overwatch_trigger_unit_ids,
    _fire_overwatch_end_movement_trigger_payload,
    _stratagem_target_proposal_payload_factory,
)
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagem_timing_candidates import stratagem_timing_candidates
from warhammer40k_core.engine.stratagems import (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    CORE_RAPID_INGRESS_HANDLER_ID,
    GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    StratagemTargetProposal,
    stratagem_target_proposal_from_index,
    stratagem_window_declined_for_context,
)
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext


def core_movement_end_candidates(
    context: TurnEndRequestContext,
    *,
    indexes: Mapping[str, StratagemCatalogIndex],
    cost_modifiers: StratagemCostModifierRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    state, decisions = context.state, context.decisions
    if context.completed_phase is not BattlePhase.MOVEMENT:
        return ()
    active = state.active_player_id
    movement = state.movement_phase_state
    if active is None or movement is None:
        raise GameLifecycleError("Movement-end rules require their completed movement state.")
    identifier = f"end-movement-ingress-round-{state.battle_round:02d}-player-{active}"
    eligibility = StratagemEligibilityContext.from_state(
        state=state,
        player_id=active,
        trigger_kind=TimingTriggerKind.END_PHASE,
        timing_window_id=identifier,
        trigger_payload={"trigger_window": "end_movement_phase", "timing_window_id": identifier},
    )
    candidates = list(
        stratagem_timing_candidates(
            state=state,
            decisions=decisions,
            index=StratagemCatalogIndex.from_records(
                tuple(
                    record
                    for record in indexes[active].all_records()
                    if record.definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID
                )
            ),
            context=eligibility,
            cost_modifiers=cost_modifiers,
            requested_event_type="end_movement_stratagem_requested",
        )
    )
    moved_ids = _active_player_end_movement_overwatch_trigger_unit_ids(
        state=state,
        decisions=decisions,
        movement_state=movement,
    )
    for player in state.player_ids:
        if player == active:
            continue
        for unit_id in moved_ids:
            window_id = (
                f"fire-overwatch-end-movement-round-{state.battle_round:02d}-"
                f"unit-{unit_id}-player-{player}"
            )
            trigger_payload = _fire_overwatch_end_movement_trigger_payload(
                moved_unit_instance_id=unit_id,
                timing_window_id=window_id,
            )
            eligibility = StratagemEligibilityContext.from_state(
                state=state,
                player_id=player,
                trigger_kind=TimingTriggerKind.END_PHASE,
                timing_window_id=window_id,
                trigger_payload=trigger_payload,
            )
            candidate = _parameterized_candidate(
                context,
                eligibility=eligibility,
                index=indexes[player],
                cost_modifiers=cost_modifiers,
                handler_id=CORE_FIRE_OVERWATCH_HANDLER_ID,
                descriptor_id="core-fire-overwatch-end-opponent-movement",
                source_step="end_movement_phase_reactions",
                status_name="fire_overwatch_reaction_pending",
            )
            if candidate is not None:
                candidates.append(candidate)
        window_id = f"rapid-ingress-end-movement-round-{state.battle_round:02d}-player-{player}"
        eligibility = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player,
            trigger_kind=TimingTriggerKind.END_PHASE,
            timing_window_id=window_id,
        )
        candidate = _parameterized_candidate(
            context,
            eligibility=eligibility,
            index=indexes[player],
            cost_modifiers=cost_modifiers,
            handler_id=CORE_RAPID_INGRESS_HANDLER_ID,
            descriptor_id="core-rapid-ingress-end-movement",
            source_step="move_units",
            status_name="rapid_ingress_reaction_pending",
        )
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _parameterized_candidate(
    context: TurnEndRequestContext,
    *,
    eligibility: StratagemEligibilityContext,
    index: StratagemCatalogIndex,
    cost_modifiers: StratagemCostModifierRegistry,
    handler_id: str,
    descriptor_id: str,
    source_step: str,
    status_name: str,
) -> TimingRuleCandidate | None:
    if stratagem_window_declined_for_context(decisions=context.decisions, context=eligibility):
        return None
    proposal = stratagem_target_proposal_from_index(
        state=context.state,
        index=index,
        context=eligibility,
        handler_id=handler_id,
        stratagem_cost_modifier_registry=cost_modifiers,
    )
    if proposal is None:
        return None
    return TimingRuleCandidate(
        participant=SequencingParticipant(
            participant_id=f"stratagem:{eligibility.timing_window_id}:{eligibility.player_id}:{proposal.catalog_record.record_id}",
            player_id=eligibility.player_id,
            source_rule_id=proposal.catalog_record.definition.source_id,
            requirement=SequencingRequirement.OPTIONAL,
            payload=validate_json_value(
                {
                    "catalog_record_id": proposal.catalog_record.record_id,
                    "context": eligibility.to_payload(),
                }
            ),
        ),
        activate=partial(
            _activate_parameterized, context, proposal, descriptor_id, source_step, status_name
        ),
    )


def _activate_parameterized(
    context: TurnEndRequestContext,
    proposal: StratagemTargetProposal,
    descriptor_id: str,
    source_step: str,
    status_name: str,
) -> LifecycleStatus:
    state, eligibility = context.state, proposal.context
    queue = context.reaction_queue
    window_id = eligibility.timing_window_id
    if queue is None or window_id is None:
        raise GameLifecycleError(
            "Movement-end reaction requires its engine queue and timing occurrence."
        )
    reaction = queue.emit_decision_request(
        state=state,
        decisions=context.decisions,
        reaction_window=ReactionWindow(
            timing_window=TimingWindow(
                window_id=window_id,
                game_id=state.game_id,
                battle_round=state.battle_round,
                active_player_id=state.active_player_id,
                phase=BattlePhase.MOVEMENT,
                descriptor=TimingWindowDescriptor(
                    descriptor_id=descriptor_id,
                    trigger_kind=TimingTriggerKind.END_PHASE,
                    source_rule_id=proposal.catalog_record.definition.handler_id,
                    phase=BattlePhase.MOVEMENT,
                    source_step=source_step,
                    metadata=eligibility.trigger_payload,
                ),
            ),
            eligible_player_ids=(proposal.player_id,),
        ),
        parent_phase=BattlePhase.MOVEMENT,
        parent_step="end_movement_phase_reactions",
        resume_token=f"{window_id}-resume",
        actor_id=proposal.player_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        options=(parameterized_decision_option(),),
        payload_factory=_stratagem_target_proposal_payload_factory(proposal),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=reaction.decision_request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": status_name,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "reacting_player_id": proposal.player_id,
        },
    )
