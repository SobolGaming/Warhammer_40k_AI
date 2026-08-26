from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.model_destruction_cause_producers import (
    attack_damage_model_destruction_cause_id,
    reserve_attack_damage_model_destruction_cause,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence
    from warhammer40k_core.engine.damage_allocation import DamageApplication
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState


def reserve_destroyed_attack_damage_authority(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    damage: DamageApplication | None,
    parent_cause_ids: tuple[str, ...] = (),
) -> None:
    if damage is None or not damage.destroyed:
        return
    reserve_attack_damage_model_destruction_cause(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        damage=damage,
        parent_cause_ids=parent_cause_ids,
    )


def reserve_attack_deadly_demise_secondary_authorities(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    source_damage: DamageApplication,
    secondary_damage_applications: tuple[DamageApplication, ...],
) -> tuple[str, ...]:
    parent_cause_ids = (
        attack_damage_model_destruction_cause_id(
            state=state,
            attack_sequence=attack_sequence,
            model_instance_id=source_damage.model_instance_id,
        ),
    )
    for damage in secondary_damage_applications:
        reserve_attack_damage_model_destruction_cause(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            damage=damage,
            parent_cause_ids=parent_cause_ids,
        )
    return parent_cause_ids


__all__ = (
    "reserve_attack_deadly_demise_secondary_authorities",
    "reserve_destroyed_attack_damage_authority",
)
