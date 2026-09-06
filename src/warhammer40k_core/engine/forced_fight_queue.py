"""Shared forced-Fight execution, including lossless ordinary Fight suspension."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import FightPolicyDescriptor
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import FightPhaseState, eligible_fight_contexts_for_player
from warhammer40k_core.engine.fights_first import FightsFirstRegistry
from warhammer40k_core.engine.forced_fight_context import ForcedFightActivationContext
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.phases.fight import FightPhaseHandler
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


def install_forced_fight_queue(
    *,
    state: GameState,
    decisions: DecisionController,
    context: ForcedFightActivationContext,
    policy: FightPolicyDescriptor,
    suspended_state: FightPhaseState | None = None,
) -> None:
    if state.fight_phase_state != suspended_state:
        raise GameLifecycleError("Forced Fight queue cannot overwrite a different Fight state.")
    if state.active_player_id is None:
        raise GameLifecycleError("Forced Fight queue requires an active player.")
    registry = (
        FightsFirstRegistry.from_state(state)
        if suspended_state is None
        else suspended_state.fight_order_state.fights_first_registry
    )
    fight_state = FightPhaseState.for_forced_activations(
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        policy=policy,
        context=context,
        fights_first_registry=registry,
        suspended_state=suspended_state,
    )
    state.replace_fight_phase_state(fight_state)
    decisions.event_log.append(
        "forced_fight_activation_queue_started",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": context.source_phase.value,
                "active_player_id": state.active_player_id,
                "phase_body_status": "forced_fight_activation_queue_started",
                "forced_activation_context": context.to_payload(),
                **(
                    {"fights_first_registry": registry.to_payload()}
                    if suspended_state is None
                    else {"suspended_state": suspended_state.to_payload()}
                ),
            }
        ),
    )


def resume_suspended_fight_state(completed: FightPhaseState) -> FightPhaseState | None:
    if completed.forced_activation_context is None:
        raise GameLifecycleError("Forced Fight completion requires its source context.")
    if (
        completed.active_activation is not None
        or completed.attack_sequence is not None
        or completed.pending_completed_attack_sequence is not None
    ):
        raise GameLifecycleError("Forced Fight cannot resume with an unresolved activation.")
    suspended = completed.suspended_state
    if suspended is None:
        return None
    original_order = suspended.fight_order_state
    selected = completed.fight_order_state.selected_to_fight_unit_ids
    if set(selected).intersection(original_order.selected_to_fight_unit_ids):
        raise GameLifecycleError("Forced Fight cannot select an ordinary activation twice.")
    return replace(
        suspended,
        fight_order_state=replace(
            original_order,
            selected_to_fight_unit_ids=(*original_order.selected_to_fight_unit_ids, *selected),
            activation_selections=(
                *original_order.activation_selections,
                *completed.fight_order_state.activation_selections,
            ),
        ),
        allocated_model_ids_this_phase=tuple(
            sorted(
                {
                    *suspended.allocated_model_ids_this_phase,
                    *completed.allocated_model_ids_this_phase,
                }
            )
        ),
        overrun_pile_in_completed_activation_result_ids=tuple(
            sorted(
                {
                    *suspended.overrun_pile_in_completed_activation_result_ids,
                    *completed.overrun_pile_in_completed_activation_result_ids,
                }
            )
        ),
    )


def advance_forced_fight_activations(
    handler: FightPhaseHandler,
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None = None,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.fight_activation_requests import (
        request_fight_activation as _request_fight_activation,
    )
    from warhammer40k_core.engine.phases.fight import (
        advance_fight_phase_body,
        fight_policy_for_handler,
        require_fight_state,
    )

    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.forced_activation_context is None:
        return None
    policy = fight_policy_for_handler(handler)
    for _iteration in range(64):
        current = require_fight_state(state)
        forced_context = current.forced_activation_context
        if forced_context is None:
            raise GameLifecycleError("Forced Fight activation context was lost.")
        if (
            current.pending_completed_attack_sequence is not None
            or current.attack_sequence is not None
            or current.active_activation is not None
        ):
            status = advance_fight_phase_body(
                handler=handler,
                state=state,
                decisions=decisions,
                reaction_queue=reaction_queue,
                policy=policy,
            )
            if status is not None:
                return status
            continue
        contexts = eligible_fight_contexts_for_player(
            state=state,
            fight_state=current,
            player_id=forced_context.selecting_player_id,
            policy=policy,
        )
        if contexts:
            return _request_fight_activation(
                state=state,
                decisions=decisions,
                fight_state=current,
                contexts=contexts,
                pass_available=False,
                policy=policy,
            )
        resumed = resume_suspended_fight_state(current)
        decisions.event_log.append(
            "forced_fight_activation_queue_completed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": forced_context.source_phase.value,
                    "active_player_id": current.active_player_id,
                    "phase_body_status": "forced_fight_activation_queue_completed",
                    "forced_activation_context": validate_json_value(forced_context.to_payload()),
                    **({} if resumed is None else {"resumed_state": resumed.to_payload()}),
                    "activation_selections": [
                        selection.to_payload()
                        for selection in current.fight_order_state.activation_selections
                    ],
                }
            ),
        )
        state.replace_fight_phase_state(resumed)
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "phase": forced_context.source_phase.value,
                "phase_body_status": "forced_fight_activation_queue_completed",
                "forced_activation_context": validate_json_value(forced_context.to_payload()),
            },
        )
    raise GameLifecycleError("Forced Fight activations exceeded deterministic guard.")
