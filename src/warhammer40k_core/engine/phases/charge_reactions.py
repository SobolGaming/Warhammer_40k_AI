from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import parameterized_decision_option
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.reaction_queue import ReactionQueue
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierRegistry
from warhammer40k_core.engine.stratagems import (
    CORE_HEROIC_INTERVENTION_HANDLER_ID,
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    StratagemCatalogIndex,
    StratagemEligibilityContext,
    StratagemTargetProposal,
    stratagem_target_proposal_from_index,
    stratagem_target_proposal_request_payload,
    stratagem_window_declined_for_context,
)
from warhammer40k_core.engine.timing_windows import (
    ReactionWindow,
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)


def request_end_opponent_charge_heroic_intervention_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    if reaction_queue is None:
        return None
    active_player_id = _active_player_id(state)
    for player_id in state.player_ids:
        if player_id == active_player_id:
            continue
        window_id = (
            f"heroic-intervention-end-charge-round-{state.battle_round:02d}-"
            f"active-{active_player_id}-player-{player_id}"
        )
        trigger_payload = validate_json_value(
            {
                "trigger_window": "end_opponent_charge_phase",
                "timing_window_id": window_id,
                "active_player_id": active_player_id,
                "reacting_player_id": player_id,
            }
        )
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player_id,
            trigger_kind=TimingTriggerKind.END_PHASE,
            timing_window_id=window_id,
            trigger_payload=trigger_payload,
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        proposal = stratagem_target_proposal_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            handler_id=CORE_HEROIC_INTERVENTION_HANDLER_ID,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
            require_legal_affordable_target=True,
        )
        if proposal is None:
            continue
        reaction_window = ReactionWindow(
            timing_window=TimingWindow(
                window_id=window_id,
                descriptor=TimingWindowDescriptor(
                    descriptor_id="core-heroic-intervention-end-opponent-charge",
                    trigger_kind=TimingTriggerKind.END_PHASE,
                    source_rule_id=CORE_HEROIC_INTERVENTION_HANDLER_ID,
                    phase=BattlePhase.CHARGE,
                    source_step="charge_phase_end_reactions",
                    metadata=trigger_payload,
                ),
                game_id=state.game_id,
                battle_round=state.battle_round,
                active_player_id=active_player_id,
                phase=BattlePhase.CHARGE,
            ),
            eligible_player_ids=(player_id,),
        )
        triggered = reaction_queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=reaction_window,
            parent_phase=BattlePhase.CHARGE,
            parent_step="charge_phase_end_reactions",
            resume_token=f"{window_id}-resume",
            actor_id=player_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            options=(parameterized_decision_option(),),
            payload_factory=_stratagem_target_proposal_payload_factory(proposal),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=triggered.decision_request,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "heroic_intervention_reaction_pending",
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "reacting_player_id": player_id,
                "request_id": triggered.decision_request.request_id,
            },
        )
    return None


def _stratagem_target_proposal_payload_factory(
    proposal: StratagemTargetProposal,
) -> Callable[[str, str, str], JsonValue]:
    if type(proposal) is not StratagemTargetProposal:
        raise GameLifecycleError(
            "Stratagem target proposal payload factory requires a StratagemTargetProposal."
        )

    def payload_factory(request_id: str, decision_type: str, actor_id: str) -> JsonValue:
        return stratagem_target_proposal_request_payload(
            proposal,
            request_id=request_id,
            decision_type=decision_type,
            actor_id=actor_id,
            allow_decline=True,
        )

    return payload_factory


def _active_player_id(state: GameState) -> str:
    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Heroic Intervention timing requires an active player.")
    return active_player_id
