from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine import attached_unit_reconciliation as _aur
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
    AttackSequenceCompletedHookRegistry,
    attack_sequence_completed_event_id,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.fight_order import FightActivationSelection
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.stratagems import StratagemCatalogIndex


def advance_fight_attack_sequence_until_completion(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    stratagem_index: StratagemCatalogIndex,
    hooks: AttackSequenceCompletedHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | FightActivationSelection:
    fight_state = state.fight_phase_state
    if fight_state is None or fight_state.attack_sequence is None:
        raise GameLifecycleError("Fight attack sequence advance requires attack_sequence.")
    completed_candidate = fight_state.attack_sequence
    attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=completed_candidate,
        already_allocated_model_ids=fight_state.allocated_model_ids_this_phase,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    updated_state = fight_state.with_attack_sequence_update(
        attack_sequence=attack_sequence,
        allocated_model_ids_this_phase=allocated_model_ids,
    )
    state.replace_fight_phase_state(updated_state)
    if status is not None:
        return status
    if attack_sequence is not None:
        raise GameLifecycleError("Fight attack sequence completion state drift.")
    state.replace_fight_phase_state(
        updated_state.with_pending_completed_attack_sequence(completed_candidate)
    )
    return continue_completed_fight_attack_sequence(
        state=state,
        decisions=decisions,
        hooks=hooks,
        runtime_modifier_registry=runtime_modifier_registry,
        completed_sequence=completed_candidate,
    )


def continue_completed_fight_attack_sequence(
    *,
    state: GameState,
    decisions: DecisionController,
    hooks: AttackSequenceCompletedHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | FightActivationSelection:
    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Fight completion continuation requires AttackSequence.")
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Fight completion continuation requires fight phase state.")
    if fight_state.pending_completed_attack_sequence != completed_sequence:
        raise GameLifecycleError("Fight completed attack sequence continuation drift.")
    activation = fight_state.active_activation
    if activation is None:
        raise GameLifecycleError("Completed melee attack sequence has no active activation.")
    hook_status = hooks.resolve_completed_sequence(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=runtime_modifier_registry,
            source_phase=BattlePhase.FIGHT,
            attack_sequence=completed_sequence,
            attack_sequence_completed_event_id=attack_sequence_completed_event_id(
                decisions=decisions,
                attack_sequence=completed_sequence,
            ),
        )
    )
    if hook_status is not None:
        return hook_status
    _aur.reconcile_after_attack_sequence(
        state,
        decisions.event_log,
        completed_sequence,
        deferred_rules_unit_instance_ids=(activation.unit_instance_id,),
    )
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Fight completion reconciliation lost fight phase state.")
    state.replace_fight_phase_state(fight_state.with_pending_completed_attack_sequence(None))
    decisions.event_log.append(
        "melee_attack_sequence_completed",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.FIGHT.value,
                "phase_body_status": "melee_attack_sequence_completed",
                "activation_selection": activation.to_payload(),
            }
        ),
    )
    return activation


__all__ = (
    "advance_fight_attack_sequence_until_completion",
    "continue_completed_fight_attack_sequence",
)
