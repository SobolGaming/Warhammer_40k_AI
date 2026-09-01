from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence import AttackSequence
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_attached_units_2026_09,
)

BODYGUARD_UNIT_DESTROYED_SOURCE_ID = core_attached_units_2026_09.BODYGUARD_UNIT_DESTROYED_SOURCE_ID

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def validate_attached_rules_unit_identity_after_destruction(
    *,
    state: GameState,
    rules_unit_instance_id: str,
) -> None:
    """Prove that destruction did not split a battle-start Attached Unit.

    ``BODYGUARD_UNIT_DESTROYED_SOURCE_ID`` keeps the original Attached Unit as one rules
    unit after its Bodyguard models are destroyed. The formation and its
    attached Starting Strength therefore remain authoritative until the last
    model that started in the unit is destroyed; dead physical components stay
    in the explicit battle-start lineage and simply stop contributing living
    models, keywords, and abilities.
    """
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=rules_unit_instance_id,
    )
    if not rules_unit.is_attached_rules_unit:
        return
    attached_id = rules_unit.unit_instance_id
    starting_matches = tuple(
        record
        for record in state.starting_attached_unit_records
        if record.attached_unit_instance_id == attached_id
    )
    if len(starting_matches) != 1:
        raise GameLifecycleError(
            "Attached rules-unit identity requires exactly one battle-start lineage record."
        )
    starting_record = starting_matches[0]
    if starting_record.player_id != rules_unit.owner_player_id:
        raise GameLifecycleError("Attached rules-unit battle-start owner drifted.")
    if starting_record.component_unit_instance_ids != tuple(
        sorted(rules_unit.component_unit_instance_ids)
    ):
        raise GameLifecycleError("Attached rules-unit component lineage drifted.")
    formation = rules_unit.attached_unit
    if formation is None:
        raise GameLifecycleError("Attached rules-unit formation identity is missing.")
    if (
        formation.bodyguard_unit_instance_id != starting_record.bodyguard_unit_instance_id
        or formation.leader_unit_instance_ids != starting_record.leader_unit_instance_ids
        or formation.support_unit_instance_ids != starting_record.support_unit_instance_ids
        or formation.source_id != starting_record.source_id
    ):
        raise GameLifecycleError("Attached rules-unit formation drifted from battle-start lineage.")
    starting_strength_ids = {record.unit_instance_id for record in state.starting_strength_records}
    if attached_id not in starting_strength_ids:
        raise GameLifecycleError("Attached rules-unit Starting Strength identity is missing.")
    if starting_strength_ids.intersection(starting_record.component_unit_instance_ids):
        raise GameLifecycleError(
            "Attached rules-unit physical components must not own separate Starting Strength."
        )


def reconcile_after_attack_sequence(
    state: GameState,
    attack_sequence: AttackSequence,
) -> None:
    """Validate every participating rules-unit identity after an attack sequence."""
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Attached-unit reconciliation requires AttackSequence.")
    candidate_ids = {
        attack_sequence.attacking_unit_instance_id,
        *(pool.target_unit_instance_id for pool in attack_sequence.attack_pools),
    }
    validated_ids: set[str] = set()
    for candidate_id in sorted(candidate_ids):
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=candidate_id)
        if rules_unit.unit_instance_id in validated_ids:
            continue
        validated_ids.add(rules_unit.unit_instance_id)
        validate_attached_rules_unit_identity_after_destruction(
            state=state,
            rules_unit_instance_id=rules_unit.unit_instance_id,
        )


__all__ = (
    "BODYGUARD_UNIT_DESTROYED_SOURCE_ID",
    "reconcile_after_attack_sequence",
    "validate_attached_rules_unit_identity_after_destruction",
)
