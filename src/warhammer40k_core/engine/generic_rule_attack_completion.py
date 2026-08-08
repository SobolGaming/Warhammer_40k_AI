from __future__ import annotations

from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND, PersistingEffect
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleDuration,
    RuleDurationKind,
    RuleDurationPayload,
    parameter_payload,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState

ATTACKING_UNIT_ATTACKS_DURATION_ENDPOINT = "attacking_unit_attacks"


def expire_attack_sequence_scoped_generic_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    source_phase: BattlePhase,
    attack_sequence: AttackSequence,
    attack_sequence_completed_event_id: str,
) -> tuple[PersistingEffect, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Generic attack completion requires GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Generic attack completion requires DecisionController.")
    if type(source_phase) is not BattlePhase:
        raise GameLifecycleError("Generic attack completion requires BattlePhase.")
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Generic attack completion requires AttackSequence.")
    effect_ids = tuple(
        effect.effect_id
        for effect in state.persisting_effects
        if _generic_effect_attack_sequence_id(effect) == attack_sequence.sequence_id
    )
    removed = state.remove_persisting_effects_by_id(effect_ids)
    if not removed:
        return ()
    decisions.event_log.append(
        "generic_rule_attack_sequence_effects_expired",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "attack_sequence_id": attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": attack_sequence_completed_event_id,
                "expired_effect_ids": [effect.effect_id for effect in removed],
                "source_rule_ids": sorted({effect.source_rule_id for effect in removed}),
            }
        ),
    )
    return removed


def _generic_effect_attack_sequence_id(effect: PersistingEffect) -> str | None:
    if type(effect) is not PersistingEffect:
        raise GameLifecycleError("Generic attack completion requires PersistingEffect values.")
    payload = effect.effect_payload
    if not isinstance(payload, dict) or payload.get("effect_kind") != GENERIC_RULE_EFFECT_KIND:
        return None
    duration_payload = payload.get("duration")
    if duration_payload is None:
        return None
    if not isinstance(duration_payload, dict):
        raise GameLifecycleError("Generic RuleIR duration payload must be an object.")
    duration = RuleDuration.from_payload(cast(RuleDurationPayload, duration_payload))
    if duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT:
        return None
    if (
        parameter_payload(duration.parameters).get("endpoint")
        != ATTACKING_UNIT_ATTACKS_DURATION_ENDPOINT
    ):
        return None
    context_payload = payload.get("context")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Attack-scoped generic RuleIR effect requires context.")
    trigger_payload = context_payload.get("trigger_payload")
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Attack-scoped generic RuleIR effect requires trigger payload.")
    attack_sequence_id = trigger_payload.get("attack_sequence_id")
    if type(attack_sequence_id) is not str or not attack_sequence_id.strip():
        raise GameLifecycleError("Attack-scoped generic RuleIR effect requires attack_sequence_id.")
    return attack_sequence_id
