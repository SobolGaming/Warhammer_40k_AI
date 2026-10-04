"""Resolve all queued attack mortals after ordinary damage, through shared allocation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_damage_helpers import (
    emit_deferred_mortal_wounds_applied,
)
from warhammer40k_core.engine.damage_allocation import (
    MortalWoundApplicationProgress,
    continue_mortal_wound_application,
    unit_owner_player_id,
)
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.mortal_wound_destruction_evidence import (
    MortalWoundDestructionEvidence,
)
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.dice import DiceRollManager
    from warhammer40k_core.engine.game_state import GameState


def apply_deferred_attack_mortals(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    if not attack_sequence.deferred_mortal_wounds:
        return attack_sequence, None
    for deferred_index, deferred in enumerate(attack_sequence.deferred_mortal_wounds):
        sequence_after_current_target = attack_sequence.with_pending_deferred_mortal_wounds(
            attack_sequence.deferred_mortal_wounds[deferred_index + 1 :]
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{attack_sequence.sequence_id}:{deferred.application_suffix}:"
                f"{deferred.attack_context_id}:mortal-wounds"
            ),
            source_rule_id=deferred.source_rule_id,
            source_context=validate_json_value(
                {
                    "source_kind": deferred.source_kind,
                    "source_permission": (
                        None
                        if deferred.source_permission is None
                        else deferred.source_permission.to_payload()
                    ),
                    "sequence_id": attack_sequence.sequence_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "target_unit_instance_id": deferred.target_unit_instance_id,
                    "attack_context_ids": [deferred.attack_context_id],
                }
            ),
            target_unit_instance_id=deferred.target_unit_instance_id,
            defender_player_id=unit_owner_player_id(
                state=state,
                unit_instance_id=deferred.target_unit_instance_id,
            ),
            mortal_wounds=deferred.mortal_wounds,
            spill_over=deferred.source_permission is not None,
            destruction_evidence=MortalWoundDestructionEvidence.for_attack_state(
                state=state,
                destroying_player_id=attack_sequence.attacker_player_id,
                attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
                attacking_model_instance_id=deferred.source_model_instance_id,
                weapon_profile=deferred.source_weapon_profile,
                attack_context_id=deferred.attack_context_id,
                action_phase=attack_sequence.source_phase,
                source_step=deferred.source_kind,
            ),
            priority_model_ids=deferred.priority_model_ids,
        )
        routed = continue_mortal_wound_application(
            state=state,
            decisions=decisions,
            request_id=state.next_decision_request_id(),
            progress=progress,
            dice_manager=manager,
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return (
                sequence_after_current_target,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=routed.request,
                    payload={
                        "phase": attack_sequence.source_phase.value,
                        "decision_type": routed.request.decision_type,
                        "sequence_id": attack_sequence.sequence_id,
                        "source_rule_id": deferred.source_rule_id,
                    },
                ),
            )
        if routed.application is None:
            raise GameLifecycleError("Deferred mortal wounds did not produce application.")
        emit_deferred_mortal_wounds_applied(
            decisions=decisions,
            attack_sequence=attack_sequence,
            target_unit_id=deferred.target_unit_instance_id,
            attack_context_ids=(deferred.attack_context_id,),
            mortal_wounds=deferred.mortal_wounds,
            application=routed.application,
            source_rule_id=deferred.source_rule_id,
            source_kind=deferred.source_kind,
        )
    return attack_sequence.without_deferred_mortal_wounds(), None
