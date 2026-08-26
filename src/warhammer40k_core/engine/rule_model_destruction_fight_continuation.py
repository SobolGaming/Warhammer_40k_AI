from __future__ import annotations

from warhammer40k_core.engine import rule_model_destruction
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_activation_units import (
    finalize_rule_destructions_after_fight_activation,
)
from warhammer40k_core.engine.fight_on_death import (
    fight_on_death_completion_contexts_for_activation,
    fight_on_death_completion_contexts_for_rules_unit,
    fight_on_death_model_ids_awaiting_attack,
    remove_models_awaiting_fight_on_death,
)
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_deadly_demise_continuation import (
    RULE_MODEL_DESTRUCTION_CONTEXT_KIND,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND = "attack_sequence_model_destroyed"


def apply_rule_destruction_fight_on_death_reaction(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
) -> LifecycleStatus | None:
    completion_context = rule_model_destruction.apply_rule_model_destruction_reaction_decision(
        state=state,
        decisions=decisions,
        result=result,
    )
    if completion_context is None:
        return None
    return _continue_or_defer_rule_fight_on_death(
        state=state,
        decisions=decisions,
        completion_context=completion_context,
    )


def fight_on_death_completion_requires_rule_finalization(
    completion_context: dict[str, JsonValue],
) -> bool:
    context_kind = completion_context.get("context_kind")
    if context_kind == RULE_MODEL_DESTRUCTION_CONTEXT_KIND:
        return True
    if context_kind == ATTACK_SEQUENCE_MODEL_DESTROYED_CONTEXT_KIND:
        return False
    raise GameLifecycleError("Fight On Death completion context kind is unsupported.")


def _continue_or_defer_rule_fight_on_death(
    *,
    state: GameState,
    decisions: DecisionController,
    completion_context: dict[str, JsonValue],
) -> LifecycleStatus | None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Rule Fight On Death requires fight phase state.")
    active_activation = fight_state.active_activation
    if active_activation is None:
        contexts = fight_on_death_completion_contexts_for_rules_unit(
            state=state,
            unit_instance_id=_payload_string(
                completion_context,
                key="rules_unit_instance_id",
            ),
        )
        if sum(context == completion_context for context in contexts) != 1:
            raise GameLifecycleError("Deferred rule Fight On Death context drift.")
        return None
    bound_contexts = fight_on_death_completion_contexts_for_activation(
        state=state,
        activation_result_id=active_activation.result_id,
    )
    if sum(context == completion_context for context in bound_contexts) != 1:
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
    return None


def finalize_next_rule_fight_on_death_at_phase_end(
    *,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | bool:
    rules_unit_ids = tuple(
        sorted(
            {
                rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=state.unit_instance_id_for_model(model_id),
                ).unit_instance_id
                for model_id in fight_on_death_model_ids_awaiting_attack(state=state)
            }
        )
    )
    for rules_unit_id in rules_unit_ids:
        completion_contexts = tuple(
            context
            for context in fight_on_death_completion_contexts_for_rules_unit(
                state=state,
                unit_instance_id=rules_unit_id,
            )
            if fight_on_death_completion_requires_rule_finalization(context)
        )
        if not completion_contexts:
            continue
        ordered_contexts = _ordered_rule_completion_contexts(completion_contexts)
        _remove_awaiting_models_for_rules_unit(
            state=state,
            decisions=decisions,
            unit_instance_id=rules_unit_id,
            reason="phase_end",
        )
        status = finalize_rule_destructions_after_fight_activation(
            state=state,
            decisions=decisions,
            contexts=ordered_contexts,
            rules_unit_instance_id=rules_unit_id,
        )
        return True if status is None else status
    return False


def remove_remaining_fight_on_death_models_at_phase_end(
    *,
    state: GameState,
    decisions: DecisionController,
) -> tuple[str, ...]:
    removed_model_ids = remove_models_awaiting_fight_on_death(state=state)
    if removed_model_ids:
        decisions.event_log.append(
            "fight_on_death_models_removed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "model_instance_ids": list(removed_model_ids),
                    "reason": "phase_end",
                }
            ),
        )
    return removed_model_ids


def remove_rule_fight_on_death_contexts_for_completed_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    activation: FightActivationSelection,
) -> tuple[dict[str, JsonValue], ...]:
    completion_contexts = tuple(
        context
        for context in fight_on_death_completion_contexts_for_rules_unit(
            state=state,
            unit_instance_id=activation.unit_instance_id,
        )
        if fight_on_death_completion_requires_rule_finalization(context)
    )
    ordered_contexts = _ordered_rule_completion_contexts(completion_contexts)
    _remove_awaiting_models_for_rules_unit(
        state=state,
        decisions=decisions,
        unit_instance_id=activation.unit_instance_id,
        reason="unit_fight_completed",
    )
    return ordered_contexts


def _remove_awaiting_models_for_rules_unit(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    reason: str,
) -> tuple[str, ...]:
    removed_model_ids = remove_models_awaiting_fight_on_death(
        state=state,
        unit_instance_id=unit_instance_id,
    )
    if removed_model_ids:
        decisions.event_log.append(
            "fight_on_death_models_removed",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.FIGHT.value,
                    "unit_instance_id": unit_instance_id,
                    "model_instance_ids": list(removed_model_ids),
                    "reason": reason,
                }
            ),
        )
    return removed_model_ids


def _ordered_rule_completion_contexts(
    contexts: tuple[dict[str, JsonValue], ...],
) -> tuple[dict[str, JsonValue], ...]:
    continuation_contexts = tuple(
        context for context in contexts if context.get("completion_continuation") is not None
    )
    if len(continuation_contexts) > 1:
        raise GameLifecycleError("Fight On Death cleanup has multiple rule continuations.")
    if not continuation_contexts:
        return contexts
    continuation = continuation_contexts[0]
    return (*tuple(context for context in contexts if context is not continuation), continuation)


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Rule Fight On Death payload {key} must be a string.")
    return value
