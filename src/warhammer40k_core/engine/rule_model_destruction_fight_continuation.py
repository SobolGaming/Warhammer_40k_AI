from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import FightEligibilityKind, FightTypeKind
from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_on_death import (
    fight_on_death_completion_context_for_activation,
    remove_models_awaiting_fight_on_death,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


def apply_rule_destruction_reaction_and_schedule_fight_on_death(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> None:
    completion_context = rule_model_destruction.apply_rule_model_destruction_reaction_decision(
        state=state,
        decisions=decisions,
        result=result,
    )
    if completion_context is None:
        return
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Rule Fight On Death requires fight phase state.")
    if fight_state.active_activation is not None:
        raise GameLifecycleError("Rule Fight On Death cannot replace an active fight activation.")
    activation = FightActivationSelection(
        player_id=_payload_string(completion_context, key="destroyed_model_controller_player_id"),
        battle_round=state.battle_round,
        unit_instance_id=_payload_string(completion_context, key="target_unit_instance_id"),
        ordering_band=fight_state.current_ordering_band,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.replace_fight_phase_state(fight_state.with_active_activation(activation))
    decisions.event_log.append(
        "fight_on_death_activation_started",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "activation_selection": activation.to_payload(),
                "model_instance_id": _payload_string(
                    completion_context,
                    key="model_instance_id",
                ),
                "model_destroyed_event_id": _payload_string(
                    completion_context,
                    key="model_destroyed_event_id",
                ),
            }
        ),
    )


def remove_rule_fight_on_death_models_for_completed_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
    unit_attacked: bool,
) -> dict[str, JsonValue] | None:
    completion_context = fight_on_death_completion_context_for_activation(
        state=state,
        activation_result_id=activation.result_id,
    )
    removed_model_ids = remove_models_awaiting_fight_on_death(
        state=state,
        unit_instance_id=activation.unit_instance_id,
    )
    if removed_model_ids:
        decisions.event_log.append(
            "fight_on_death_models_removed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "unit_instance_id": activation.unit_instance_id,
                    "model_instance_ids": list(removed_model_ids),
                    "reason": "unit_attacked" if unit_attacked else "no_legal_attack",
                }
            ),
        )
    return completion_context


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Rule Fight On Death payload {key} must be a string.")
    return value
