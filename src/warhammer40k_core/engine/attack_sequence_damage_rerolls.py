# ruff: noqa: F403, F405
# pyright: reportUnknownVariableType=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_imports import *

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import (
        _source_backed_attack_kind_for_phase,
        _source_backed_reroll_already_answered,
    )
    from warhammer40k_core.engine.attack_sequence_state import _runtime_modifier_registry
    from warhammer40k_core.engine.game_state import GameState

__all__ = ("_request_source_backed_damage_reroll_if_available",)


def _request_source_backed_damage_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    weapon_profile_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> LifecycleStatus | None:
    if source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return None
    if roll_state.rerolls or roll_state.original_result.spec.reroll_forbidden_rule_ids:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    roll_type = roll_state.original_result.spec.roll_type
    permission_contexts = unified_attack_reroll_permission_contexts_for_unit(
        state=state,
        player_id=actor_id,
        attacking_unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        source_phase=source_phase,
        attack_kind=_source_backed_attack_kind_for_phase(source_phase),
        roll_type=roll_type,
        registry=_runtime_modifier_registry(runtime_modifier_registry),
    )
    permission_context = select_source_backed_reroll_permission_context(permission_contexts)
    if permission_context is None:
        return None
    permission = permission_context.permission
    if _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        source_id=permission.source_id,
    ):
        return None
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=actor_id,
        permission=permission,
        extra_payload={
            "source_rule_id": permission.source_id,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "unit_instance_id": attacking_unit_instance_id,
                "target_unit_instance_id": target_unit_instance_id,
                "attack_context_id": attack_context_id,
                "weapon_profile_id": weapon_profile_id,
                "damage_roll_state": validate_json_value(roll_state.to_payload()),
                "source_payload": validate_json_value(permission_context.source_payload),
            },
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": source_phase.value,
            "phase_body_status": "attack_damage_source_backed_reroll_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_type,
            "affected_unit_instance_id": attacking_unit_instance_id,
            "target_unit_instance_id": target_unit_instance_id,
            "attack_context_id": attack_context_id,
            "pending_request_id": request.request_id,
        },
    )
