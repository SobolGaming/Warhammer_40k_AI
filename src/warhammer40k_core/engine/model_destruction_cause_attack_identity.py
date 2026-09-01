from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseKind,
    model_destruction_cause_id,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def attack_damage_model_destruction_producer_id_for_context(
    *,
    sequence_id: str,
    attack_context_id: str,
) -> str:
    if type(sequence_id) is not str or not sequence_id.strip():
        raise GameLifecycleError("Attack destruction sequence ID is invalid.")
    if type(attack_context_id) is not str or not attack_context_id.strip():
        raise GameLifecycleError("Attack destruction context ID is invalid.")
    return f"{sequence_id}:damage:{attack_context_id}"


def attack_damage_model_destruction_cause_id_for_context(
    *,
    state: GameState,
    sequence_id: str,
    attack_context_id: str,
    model_instance_id: str,
) -> str:
    return model_destruction_cause_id(
        game_id=state.game_id,
        cause_kind=ModelDestructionCauseKind.ATTACK_DAMAGE,
        producer_id=attack_damage_model_destruction_producer_id_for_context(
            sequence_id=sequence_id,
            attack_context_id=attack_context_id,
        ),
        model_instance_id=model_instance_id,
    )


__all__ = (
    "attack_damage_model_destruction_cause_id_for_context",
    "attack_damage_model_destruction_producer_id_for_context",
)
