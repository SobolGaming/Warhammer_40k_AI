"""Generic successful-wound producer with an authenticated source grant."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.additional_attack_mortal_permissions import (
    additional_attack_mortal_permissions,
)
from warhammer40k_core.engine.attack_mortal_origins import attack_mortal_origin
from warhammer40k_core.engine.attack_sequence_model import AttackResolutionContextPayload
from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.deferred_mortal_wounds import DeferredMortalWounds
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def defer_additional_attack_mortals(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> AttackSequence:
    current = attack_sequence
    for wounded_sequence, context in wounded_contexts:
        origin = attack_mortal_origin(
            state=state,
            attack_sequence=wounded_sequence,
            attack_context=context,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if not context["wound_roll"]["successful"]:
            raise GameLifecycleError("Additional attack mortals require a successful wound.")
        for permission in additional_attack_mortal_permissions(
            state=state,
            attacking_unit_instance_id=current.attacking_unit_instance_id,
            attacker_player_id=current.attacker_player_id,
            attacker_model_instance_id=origin.source_model_instance_id,
            source_phase=current.source_phase,
            weapon_profile=origin.weapon_profile,
        ):
            payload = permission.effect_payload
            if not isinstance(payload, dict):
                raise GameLifecycleError("Additional attack mortal permission must be an object.")
            deferred = DeferredMortalWounds(
                source_rule_id=permission.source_rule_id,
                source_model_instance_id=origin.source_model_instance_id,
                source_weapon_profile=origin.weapon_profile,
                target_unit_instance_id=context["target_unit_instance_id"],
                attack_context_id=context["attack_context_id"],
                mortal_wounds=cast(int, payload["mortal_wounds"]),
                source_permission=permission,
            )
            decisions.event_log.append(
                "additional_attack_mortal_wounds_deferred",
                validate_json_value(
                    {
                        "sequence_id": current.sequence_id,
                        "attack_context_id": context["attack_context_id"],
                        "source_rule_id": permission.source_rule_id,
                        "originating_pool_index": origin.pool_index,
                        "originating_attack_index": origin.attack_index,
                        "source_weapon_instance_id": origin.weapon_instance_id,
                        "source_permission": permission.to_payload(),
                        "attack_context": context,
                        "deferred_mortal_wounds": deferred.to_payload(),
                    }
                ),
            )
            current = current.with_deferred_mortal_wounds(deferred)
    return current
