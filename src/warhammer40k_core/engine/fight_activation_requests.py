from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import FightPolicyDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FightEligibilityContext,
    FightPhaseState,
    eligible_pass_option_payload,
    fight_activation_option_id,
    fight_activation_option_payload,
    legal_fight_types_for_context,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatus

FIGHT_ACTIVATION_REQUIRED_STATUS = "fight_activation_required"


def request_fight_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
) -> LifecycleStatus:
    request = build_fight_activation_request(
        state=state,
        fight_state=fight_state,
        contexts=contexts,
        pass_available=pass_available,
        policy=policy,
        request_id=state.next_decision_request_id(),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "fight_activation_selection_requested",
        fight_activation_selection_requested_payload(
            state=state,
            fight_state=fight_state,
            contexts=contexts,
            pass_available=pass_available,
            request_id=request.request_id,
        ),
    )
    forced_payload: JsonValue = (
        None
        if fight_state.forced_activation_context is None
        else validate_json_value(fight_state.forced_activation_context.to_payload())
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.FIGHT.value,
            "phase_body_status": FIGHT_ACTIVATION_REQUIRED_STATUS,
            "battle_round": state.battle_round,
            "active_player_id": fight_state.active_player_id,
            "player_id": fight_state.fight_order_state.next_player_id,
            "ordering_band": fight_state.current_ordering_band.value,
            "eligible_unit_ids": [context.unit_instance_id for context in contexts],
            "eligible_pass_available": pass_available,
            **({} if forced_payload is None else {"forced_activation_context": forced_payload}),
        },
    )


def build_fight_activation_request(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
    request_id: str,
) -> DecisionRequest:
    forced_payload: JsonValue = (
        None
        if fight_state.forced_activation_context is None
        else validate_json_value(fight_state.forced_activation_context.to_payload())
    )
    return DecisionRequest(
        request_id=request_id,
        decision_type=FIGHT_ACTIVATION_DECISION_TYPE,
        actor_id=fight_state.fight_order_state.next_player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": fight_state.active_player_id,
                "player_id": fight_state.fight_order_state.next_player_id,
                "step_states": [step.to_payload() for step in fight_state.step_states],
                "ordering_band": fight_state.current_ordering_band.value,
                "eligible_contexts": [context.to_payload() for context in contexts],
                "eligible_pass_available": pass_available,
                **({} if forced_payload is None else {"forced_activation_context": forced_payload}),
            }
        ),
        options=_fight_activation_options(
            state=state,
            fight_state=fight_state,
            contexts=contexts,
            pass_available=pass_available,
            policy=policy,
        ),
    )


def fight_activation_selection_requested_payload(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    request_id: str,
) -> JsonValue:
    forced_payload: JsonValue = (
        None
        if fight_state.forced_activation_context is None
        else validate_json_value(fight_state.forced_activation_context.to_payload())
    )
    return validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.FIGHT.value,
            "active_player_id": fight_state.active_player_id,
            "player_id": fight_state.fight_order_state.next_player_id,
            "ordering_band": fight_state.current_ordering_band.value,
            "request_id": request_id,
            "eligible_unit_ids": [context.unit_instance_id for context in contexts],
            "eligible_pass_available": pass_available,
            "phase_body_status": FIGHT_ACTIVATION_REQUIRED_STATUS,
            **({} if forced_payload is None else {"forced_activation_context": forced_payload}),
        }
    )


def _fight_activation_options(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for context in contexts:
        for fight_type in legal_fight_types_for_context(context=context, policy=policy):
            options.append(
                DecisionOption(
                    option_id=fight_activation_option_id(
                        unit_instance_id=context.unit_instance_id,
                        fight_type=fight_type,
                    ),
                    label=f"{context.unit_instance_id} {fight_type.value}",
                    payload=fight_activation_option_payload(
                        state=state,
                        fight_state=fight_state,
                        context=context,
                        fight_type=fight_type,
                    ),
                )
            )
    if pass_available:
        options.append(
            DecisionOption(
                option_id=ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
                label="Eligible To Fight Pass",
                payload=eligible_pass_option_payload(
                    state=state,
                    fight_state=fight_state,
                    player_id=fight_state.fight_order_state.next_player_id,
                    contexts=contexts,
                    policy=policy,
                ),
            )
        )
    return tuple(options)


__all__ = (
    "FIGHT_ACTIVATION_REQUIRED_STATUS",
    "build_fight_activation_request",
    "fight_activation_selection_requested_payload",
    "request_fight_activation",
)
