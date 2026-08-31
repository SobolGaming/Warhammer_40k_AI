from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.model_destruction_cause_authority import (
    ModelDestructionCauseAuthority,
    model_destruction_cause_authority_by_id_or_none,
)
from warhammer40k_core.engine.model_destruction_cause_producers import (
    attack_damage_model_destruction_cause_id,
    reserve_attack_damage_model_destruction_cause,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_owner_player_id

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


def reserved_attack_damage_parent_cause_ids(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
) -> tuple[str, ...]:
    return _reserved_attack_damage_authority(
        state=state,
        attack_sequence=attack_sequence,
        damage=damage,
    ).parent_cause_ids


def reserved_attack_damage_destruction_attribution(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
) -> ModelDestructionAttribution:
    authority = _reserved_attack_damage_authority(
        state=state,
        attack_sequence=attack_sequence,
        damage=damage,
    )
    if not authority.parent_cause_ids:
        current_pool = attack_sequence.current_pool()
        return ModelDestructionAttribution.for_attack(
            destroying_player_id=attack_sequence.attacker_player_id,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacking_model_instance_id=current_pool.attacker_model_instance_id,
            weapon_profile=current_pool.weapon_profile,
            attack_context_id=attack_sequence.attack_context_id(),
        )
    if len(authority.parent_cause_ids) != 1:
        raise GameLifecycleError("Deadly Demise destruction requires one parent authority.")
    parent = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=authority.parent_cause_ids[0],
    )
    if parent is None:
        raise GameLifecycleError("Deadly Demise parent destruction authority is missing.")
    return ModelDestructionAttribution.for_non_attack(
        destroying_player_id=rules_unit_owner_player_id(
            state=state,
            unit_instance_id=parent.rules_unit_instance_id,
        ),
        source_kind=DestructionSourceKind.DEADLY_DEMISE,
        source_rules_unit_instance_id=parent.rules_unit_instance_id,
        source_model_instance_id=parent.model_instance_id,
    )


def _reserved_attack_damage_authority(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    damage: DamageApplication,
) -> ModelDestructionCauseAuthority:
    cause_id = attack_damage_model_destruction_cause_id(
        state=state,
        attack_sequence=attack_sequence,
        model_instance_id=damage.model_instance_id,
    )
    authority = model_destruction_cause_authority_by_id_or_none(
        state=state,
        cause_id=cause_id,
    )
    if authority is None or authority.source_authority_finalized:
        raise GameLifecycleError("Resumed attack destruction requires its pending cause authority.")
    return authority


__all__ = (
    "reserve_attack_deadly_demise_secondary_authorities",
    "reserve_destroyed_attack_damage_authority",
    "reserved_attack_damage_destruction_attribution",
    "reserved_attack_damage_parent_cause_ids",
)
