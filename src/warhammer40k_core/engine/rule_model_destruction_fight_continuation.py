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
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
)
from warhammer40k_core.engine.rules_units import rules_unit_identities_share_lineage

ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND = "attack_sequence_model_destroyed"


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
    _schedule_fight_on_death_activation(
        state=state,
        decisions=decisions,
        request_id=result.request_id,
        result_id=result.result_id,
        completion_context=completion_context,
        allow_active_continuation=True,
    )


def schedule_attack_sequence_fight_on_death_after_completed_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_activation: FightActivationSelection,
    completed_fight_on_death_context: dict[str, JsonValue] | None,
) -> bool:
    if type(completed_activation) is not FightActivationSelection:
        raise GameLifecycleError(
            "Attack-sequence Fight On Death scheduling requires FightActivationSelection."
        )
    attacking_unit_instance_id = _completed_attack_source_unit_instance_id(
        completed_activation=completed_activation,
        completion_context=completed_fight_on_death_context,
    )
    if attacking_unit_instance_id is None:
        return False
    for record in decisions.records:
        context = fight_on_death_completion_context_for_activation(
            state=state,
            activation_result_id=record.result.result_id,
        )
        if context is None or context.get("context_kind") != (
            ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND
        ):
            continue
        attack_context = _payload_object(context, key="attack_context")
        candidate_attacking_unit_id = _payload_string(
            attack_context,
            key="attacking_unit_instance_id",
        )
        if not rules_unit_identities_share_lineage(
            state=state,
            first_unit_instance_id=attacking_unit_instance_id,
            second_unit_instance_id=candidate_attacking_unit_id,
        ):
            continue
        _schedule_fight_on_death_activation(
            state=state,
            decisions=decisions,
            request_id=record.request.request_id,
            result_id=record.result.result_id,
            completion_context=context,
            allow_active_continuation=False,
        )
        return True
    return False


def fight_on_death_completion_requires_rule_finalization(
    completion_context: dict[str, JsonValue],
) -> bool:
    context_kind = completion_context.get("context_kind")
    if context_kind == RULE_MODEL_DESTRUCTION_CONTEXT_KIND:
        return True
    if context_kind == ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND:
        return False
    raise GameLifecycleError("Fight On Death completion context kind is unsupported.")


def _schedule_fight_on_death_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    result_id: str,
    completion_context: dict[str, JsonValue],
    allow_active_continuation: bool,
) -> None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Fight On Death scheduling requires fight phase state.")
    if fight_state.active_activation is not None:
        if not allow_active_continuation:
            raise GameLifecycleError(
                "Attack-sequence Fight On Death cannot replace an active activation."
            )
        active_activation = fight_state.active_activation
        bound_context = fight_on_death_completion_context_for_activation(
            state=state,
            activation_result_id=active_activation.result_id,
        )
        if bound_context != completion_context:
            raise GameLifecycleError("Fight On Death active continuation context drift.")
        decisions.event_log.append(
            "fight_on_death_active_activation_continued",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "activation_selection": active_activation.to_payload(),
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
        return
    activation = FightActivationSelection(
        player_id=_payload_string(completion_context, key="destroyed_model_controller_player_id"),
        battle_round=state.battle_round,
        unit_instance_id=_payload_string(completion_context, key="target_unit_instance_id"),
        ordering_band=fight_state.current_ordering_band,
        fight_type=FightTypeKind.NORMAL,
        eligibility_reasons=(FightEligibilityKind.CURRENTLY_ENGAGED,),
        request_id=request_id,
        result_id=result_id,
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


def _completed_attack_source_unit_instance_id(
    *,
    completed_activation: FightActivationSelection,
    completion_context: dict[str, JsonValue] | None,
) -> str | None:
    if completion_context is None:
        return completed_activation.unit_instance_id
    context_kind = completion_context.get("context_kind")
    if context_kind == RULE_MODEL_DESTRUCTION_CONTEXT_KIND:
        return None
    if context_kind != ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND:
        raise GameLifecycleError("Fight On Death completion context kind is unsupported.")
    attack_context = _payload_object(completion_context, key="attack_context")
    return _payload_string(attack_context, key="attacking_unit_instance_id")


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


def _payload_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Fight On Death payload {key} must be an object.")
    return value
