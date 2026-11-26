from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import FightPolicyDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.effects import EffectExpiration, PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    ELIGIBLE_TO_FIGHT_PASS_OPTION_ID,
    FIGHT_ACTIVATION_DECISION_TYPE,
    FIGHTS_FIRST_EFFECT_KIND,
    FightEligibilityContext,
    FightPhaseState,
    eligible_fight_contexts_for_player,
    eligible_pass_option_payload,
    fight_activation_option_id,
    fight_activation_option_payload,
    legal_fight_types_for_context,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.stratagems_model import StratagemUseRecord

FIGHT_ACTIVATION_REQUIRED_STATUS = "fight_activation_required"


def counteroffensive_fight_context(
    *,
    state: GameState,
    fight_state: FightPhaseState,
    use: StratagemUseRecord,
    policy: FightPolicyDescriptor,
) -> FightEligibilityContext | None:
    contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=use.player_id,
        policy=policy,
        respect_ordering_band=False,
    )
    unit_id = use.target_binding.target_unit_instance_id
    return next((context for context in contexts if context.unit_instance_id == unit_id), None)


def counteroffensive_fights_first_effect(
    use: StratagemUseRecord, *, unit_id: str, active_player_id: str
) -> PersistingEffect:
    return PersistingEffect(
        effect_id=f"{use.use_id}:counteroffensive:fights-first",
        source_rule_id=use.source_id,
        owner_player_id=use.player_id,
        target_unit_instance_ids=(unit_id,),
        started_battle_round=use.battle_round,
        started_phase=use.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use.battle_round,
            phase=use.phase,
            player_id=active_player_id,
        ),
        effect_payload={
            "effect_kind": FIGHTS_FIRST_EFFECT_KIND,
            "source_rule_id": use.source_id,
            "stratagem_use_id": use.use_id,
        },
    )


def request_fight_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    fight_state: FightPhaseState,
    contexts: tuple[FightEligibilityContext, ...],
    pass_available: bool,
    policy: FightPolicyDescriptor,
    interrupt_id: str | None = None,
) -> LifecycleStatus:
    request = build_fight_activation_request(
        state=state,
        fight_state=fight_state,
        contexts=contexts,
        pass_available=pass_available,
        policy=policy,
        request_id=state.next_decision_request_id(),
        interrupt_id=interrupt_id,
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
            "battle_round": fight_state.battle_round,
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
    interrupt_id: str | None = None,
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
                "battle_round": fight_state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "active_player_id": fight_state.active_player_id,
                "player_id": fight_state.fight_order_state.next_player_id,
                "step_states": [step.to_payload() for step in fight_state.step_states],
                "ordering_band": fight_state.current_ordering_band.value,
                "eligible_contexts": [context.to_payload() for context in contexts],
                "eligible_pass_available": pass_available,
                **({} if forced_payload is None else {"forced_activation_context": forced_payload}),
                **({} if interrupt_id is None else {"interrupt_id": interrupt_id}),
            }
        ),
        options=_fight_activation_options(
            state=state,
            fight_state=fight_state,
            contexts=contexts,
            pass_available=pass_available,
            policy=policy,
            interrupt_id=interrupt_id,
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
            "battle_round": fight_state.battle_round,
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
    interrupt_id: str | None,
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
                        interrupt_id=interrupt_id,
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
